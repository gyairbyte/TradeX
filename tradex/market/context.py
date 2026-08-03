"""Point-in-time market regime and relative-strength calculations."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import ta

from tradex.market.models import ShortContextPolicy, ShortTermMarketContext


def _require_aware(dt: datetime, name: str) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{name} must be timezone-aware; got naive {dt!r}")


def _latest_as_of(df: pd.DataFrame, as_of: datetime) -> datetime | None:
    """Return the latest timestamp in ``df`` that is <= ``as_of``.

    ``df`` must have a sorted DatetimeIndex.
    """
    if df.empty:
        return None
    pos = df.index.searchsorted(as_of, side="right") - 1
    if pos < 0:
        return None
    return df.index[pos].to_pydatetime()


def _is_stale(context_time: datetime, as_of: datetime) -> bool:
    """Return True when context_time is more than one expected trading session behind as_of."""
    try:
        bdays = len(pd.bdate_range(start=context_time.date(), end=as_of.date()))
    except Exception:  # pragma: no cover - defensive fallback  # noqa: BLE001
        bdays = (as_of.date() - context_time.date()).days + 1
    return bdays > 2


def _compute_emas(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return EMA20 and EMA50 series for a price series."""
    ema20 = ta.trend.EMAIndicator(series, window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(series, window=50).ema_indicator()
    return ema20, ema50


def _ema_slope_5(ema20: pd.Series) -> float | None:
    """EMA20 today minus EMA20 five bars earlier."""
    if len(ema20) < 6:
        return None
    today = ema20.iloc[-1]
    five_ago = ema20.iloc[-6]
    if pd.isna(today) or pd.isna(five_ago):
        return None
    return float(today - five_ago)


def _regime_state(
    close: float | None,
    ema20: float | None,
    ema50: float | None,
    ema20_slope5: float | None,
) -> tuple[bool | None, str | None]:
    """Evaluate bullish regime; return (boolean, error reason or None)."""
    if close is None or ema20 is None or ema50 is None or ema20_slope5 is None:
        return None, "insufficient_history"
    return (
        close > ema20 > ema50 and ema20_slope5 > 0,
        None,
    )


def _relative_strength_state(
    ratio_series: pd.Series,
) -> tuple[float | None, float | None, float | None, bool | None, str | None]:
    """Compute RS ratio, EMA20, 20-bar change, and positive flag.

    Returns (ratio, ema20, change20_pct, positive, reason).
    """
    if ratio_series.empty or len(ratio_series) < 21:
        return None, None, None, None, "insufficient_history"
    ratio_now = float(ratio_series.iloc[-1])
    if pd.isna(ratio_now):
        return None, None, None, None, "missing_ratio"

    ema20 = ta.trend.EMAIndicator(ratio_series, window=20).ema_indicator()
    ema20_now = float(ema20.iloc[-1])
    if pd.isna(ema20_now):
        return None, None, None, None, "insufficient_history"

    ratio_20_ago = float(ratio_series.iloc[-21])
    if pd.isna(ratio_20_ago) or ratio_20_ago == 0:
        return ratio_now, ema20_now, None, None, "missing_ratio"
    change20_pct = ratio_now / ratio_20_ago - 1.0

    positive = ratio_now > ema20_now and change20_pct > 0
    return ratio_now, ema20_now, change20_pct, positive, None


def _context_for_proxy(
    as_of: datetime,
    proxy_name: str,
    ticker_df: pd.DataFrame,
    proxy_df: pd.DataFrame,
) -> dict[str, Any]:
    """Build raw context for one proxy (market or sector).

    The returned dictionary contains the context timestamp, closes, EMAs,
    slope, regime flag, RS values, and bookkeeping flags.
    """
    proxy_time = _latest_as_of(proxy_df, as_of)
    if proxy_time is None:
        return {
            "context_time": None,
            "error": f"no {proxy_name} data at or before {as_of.isoformat()}",
            "close": None,
            "ema20": None,
            "ema50": None,
            "ema20_slope_5": None,
            "regime_bullish": None,
            "rs_ratio": None,
            "rs_ema20": None,
            "rs_change_20_pct": None,
            "rs_positive": None,
        }

    if _is_stale(proxy_time, as_of):
        return {
            "context_time": proxy_time,
            "error": f"{proxy_name} context at {proxy_time.date().isoformat()} is stale relative to {as_of.date().isoformat()}",
            "close": None,
            "ema20": None,
            "ema50": None,
            "ema20_slope_5": None,
            "regime_bullish": None,
            "rs_ratio": None,
            "rs_ema20": None,
            "rs_change_20_pct": None,
            "rs_positive": None,
        }

    # Point-in-time: proxy bars through the proxy timestamp only.
    proxy_series = proxy_df.loc[proxy_df.index <= proxy_time, "close"]
    proxy_close = float(proxy_series.iloc[-1]) if not proxy_series.empty else None

    ema20_proxy, ema50_proxy = _compute_emas(proxy_series)
    ema20_now = float(ema20_proxy.iloc[-1]) if not ema20_proxy.empty else None
    ema50_now = float(ema50_proxy.iloc[-1]) if not ema50_proxy.empty else None
    slope5 = _ema_slope_5(ema20_proxy)
    regime_bullish, regime_error = (
        _regime_state(proxy_close, ema20_now, ema50_now, slope5)
        if proxy_close is not None
        else (None, "missing_close")
    )

    # Ticker bars through the proxy timestamp for aligned closes.
    ticker_series = ticker_df.loc[ticker_df.index <= proxy_time, "close"]
    if ticker_series.empty:
        return {
            "context_time": proxy_time,
            "error": f"no ticker data aligned with {proxy_name} at {proxy_time.date().isoformat()}",
            "close": proxy_close,
            "ema20": ema20_now,
            "ema50": ema50_now,
            "ema20_slope_5": slope5,
            "regime_bullish": regime_bullish,
            "rs_ratio": None,
            "rs_ema20": None,
            "rs_change_20_pct": None,
            "rs_positive": None,
        }

    # Build the aligned ratio series on common dates up to the proxy timestamp.
    ticker_slice = ticker_df.loc[ticker_df.index <= proxy_time]
    proxy_slice = proxy_df.loc[proxy_df.index <= proxy_time]
    common = ticker_slice.index.intersection(proxy_slice.index)
    if common.empty:
        return {
            "context_time": proxy_time,
            "error": f"no common dates between ticker and {proxy_name}",
            "close": proxy_close,
            "ema20": ema20_now,
            "ema50": ema50_now,
            "ema20_slope_5": slope5,
            "regime_bullish": regime_bullish,
            "rs_ratio": None,
            "rs_ema20": None,
            "rs_change_20_pct": None,
            "rs_positive": None,
        }

    ticker_aligned = ticker_slice.loc[common, "close"]
    proxy_aligned = proxy_slice.loc[common, "close"]
    ratio_series = ticker_aligned / proxy_aligned
    ratio_series = ratio_series.dropna()

    rs_ratio, rs_ema20, rs_change20, rs_positive, rs_error = _relative_strength_state(
        ratio_series
    )

    # If the RS computation itself failed, surface that error.
    error = regime_error or rs_error or None
    return {
        "context_time": proxy_time,
        "error": error,
        "close": proxy_close,
        "ema20": ema20_now,
        "ema50": ema50_now,
        "ema20_slope_5": slope5,
        "regime_bullish": regime_bullish,
        "rs_ratio": rs_ratio,
        "rs_ema20": rs_ema20,
        "rs_change_20_pct": rs_change20,
        "rs_positive": rs_positive,
    }


def compute_short_term_context(
    as_of: datetime,
    ticker_df: pd.DataFrame,
    market_proxy: str,
    market_df: pd.DataFrame,
    sector_proxy: str | None = None,
    sector_df: pd.DataFrame | None = None,
) -> ShortTermMarketContext:
    """Compute a point-in-time ``ShortTermMarketContext`` for ``as_of``.

    ``ticker_df``, ``market_df``, and ``sector_df`` must have a sorted,
    timezone-aware ``datetime`` index and canonical OHLCV columns.
    """
    _require_aware(as_of, "as_of")
    if ticker_df.empty:
        raise ValueError("ticker_df must not be empty")

    market = _context_for_proxy(as_of, market_proxy, ticker_df, market_df)
    sector: dict[str, Any] | None = None
    if sector_proxy is not None and sector_df is not None:
        sector = _context_for_proxy(as_of, sector_proxy, ticker_df, sector_df)

    errors: dict[str, str] = {}
    available: list[str] = []
    missing: list[str] = []

    market_regime_available = market["close"] is not None and market["regime_bullish"] is not None
    if market_regime_available:
        available.append("market_regime")
    else:
        missing.append("market_regime")
        if market["error"]:
            errors["market_regime"] = market["error"]

    market_rs_available = market["rs_ratio"] is not None and market["rs_positive"] is not None
    if market_rs_available:
        available.append("market_relative_strength")
    else:
        missing.append("market_relative_strength")
        if market["error"]:
            errors["market_relative_strength"] = market["error"]

    if sector is not None:
        sector_regime_available = sector["close"] is not None and sector["regime_bullish"] is not None
        if sector_regime_available:
            available.append("sector_regime")
        else:
            missing.append("sector_regime")
            if sector["error"]:
                errors["sector_regime"] = sector["error"]

        sector_rs_available = sector["rs_ratio"] is not None and sector["rs_positive"] is not None
        if sector_rs_available:
            available.append("sector_relative_strength")
        else:
            missing.append("sector_relative_strength")
            if sector["error"]:
                errors["sector_relative_strength"] = sector["error"]
    else:
        sector_regime_available = False
        sector_rs_available = False

    context_complete = market_regime_available and market_rs_available
    if sector is not None:
        context_complete = context_complete and sector_regime_available and sector_rs_available

    return ShortTermMarketContext(
        as_of=as_of,
        market_proxy=market_proxy,
        sector_proxy=sector_proxy,
        market_regime_available=market_regime_available,
        market_regime_bullish=market["regime_bullish"],
        sector_regime_available=sector_regime_available,
        sector_regime_bullish=sector["regime_bullish"] if sector is not None else None,
        market_relative_strength_available=market_rs_available,
        market_relative_strength_positive=market["rs_positive"],
        sector_relative_strength_available=sector_rs_available,
        sector_relative_strength_positive=sector["rs_positive"] if sector is not None else None,
        market_close=market["close"],
        market_ema20=market["ema20"],
        market_ema50=market["ema50"],
        market_ema20_slope_5=market["ema20_slope_5"],
        sector_close=sector["close"] if sector is not None else None,
        sector_ema20=sector["ema20"] if sector is not None else None,
        sector_ema50=sector["ema50"] if sector is not None else None,
        sector_ema20_slope_5=sector["ema20_slope_5"] if sector is not None else None,
        market_rs_ratio=market["rs_ratio"],
        market_rs_ema20=market["rs_ema20"],
        market_rs_change_20_pct=market["rs_change_20_pct"],
        sector_rs_ratio=sector["rs_ratio"] if sector is not None else None,
        sector_rs_ema20=sector["rs_ema20"] if sector is not None else None,
        sector_rs_change_20_pct=sector["rs_change_20_pct"] if sector is not None else None,
        market_context_time=market["context_time"],
        sector_context_time=sector["context_time"] if sector is not None else None,
        available_contexts=tuple(available),
        missing_contexts=tuple(missing),
        context_complete=context_complete,
        errors=errors,
    )


def is_context_eligible(
    context: ShortTermMarketContext,
    policy: ShortContextPolicy,
) -> tuple[bool, str, list[str]]:
    """Return (eligible, status, reasons) for a context and policy.

    ``status`` is one of ``off``, ``eligible``, or ``unavailable``.
    """
    if policy == ShortContextPolicy.OFF:
        return True, "off", []

    reasons: list[str] = []

    if not context.market_regime_available or context.market_regime_bullish is None:
        return False, "unavailable", ["market regime unavailable"]
    if not context.market_regime_bullish:
        reasons.append("market regime not bullish")

    if not context.market_relative_strength_available or context.market_relative_strength_positive is None:
        return False, "unavailable", ["market relative strength unavailable"]
    if not context.market_relative_strength_positive:
        reasons.append("market relative strength not positive")

    if policy == ShortContextPolicy.MARKET_RS:
        eligible = context.market_regime_bullish and context.market_relative_strength_positive
        status = "eligible" if eligible else ("unavailable" if not reasons else "filtered")
        return eligible, status, reasons

    # MARKET_SECTOR_RS
    if not context.sector_regime_available or context.sector_regime_bullish is None:
        return False, "unavailable", ["sector regime unavailable"]
    if not context.sector_regime_bullish:
        reasons.append("sector regime not bullish")

    if not context.sector_relative_strength_available or context.sector_relative_strength_positive is None:
        return False, "unavailable", ["sector relative strength unavailable"]
    if not context.sector_relative_strength_positive:
        reasons.append("sector relative strength not positive")

    eligible = (
        context.market_regime_bullish
        and context.market_relative_strength_positive
        and context.sector_regime_bullish
        and context.sector_relative_strength_positive
    )
    status = "eligible" if eligible else ("unavailable" if not reasons else "filtered")
    return eligible, status, reasons
