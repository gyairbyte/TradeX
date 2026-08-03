"""Data-source adapters and snapshot builders for the pre-market gap scanner.

All network access is isolated in this module. The orchestrator and CLI call the
public functions here; tests mock at this boundary.
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime, time

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import DEFAULT_PROVIDER, ProviderCapabilityError
from tradex.data.history import fetch_daily_history
from tradex.market import (
    MARKET_TIMEZONE,
    get_market_session,
    is_trading_day,
    previous_trading_session,
)
from tradex.premarket.models import (
    DailyLiquidityBaseline,
    PremarketBarsResult,
    PremarketSnapshot,
    SpreadSnapshot,
)

PREMARKET_OPEN_TIME = time(4, 0)


def resolve_premarket_provider(provider: str | None) -> str:
    """Return the canonical pre-market provider name or raise ProviderCapabilityError."""
    from tradex.data.fetcher import resolve_provider

    p = resolve_provider(provider)
    if p == "yahoo":
        return p
    if p == "schwab":
        raise ProviderCapabilityError(
            f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
        )
    raise ProviderCapabilityError(
        f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Naive datetime is not accepted; provide a timezone-aware datetime.")
    return value.astimezone(UTC)


def _ny(value: datetime) -> datetime:
    from tradex.market import normalize_market_datetime

    return normalize_market_datetime(value)


def _premarket_window(session_date: date, as_of: datetime, allow_after_open: bool) -> tuple[datetime, datetime] | None:
    """Return (premarket_start, window_end) for the requested session, or None if invalid."""
    session = get_market_session(session_date)
    if session is None:
        return None
    premarket_start = datetime.combine(session_date, PREMARKET_OPEN_TIME, tzinfo=MARKET_TIMEZONE)
    if not allow_after_open and as_of >= session.opens_at:
        return None
    window_end = min(as_of, session.opens_at)
    if window_end <= premarket_start:
        return None
    return premarket_start, window_end


def _filter_premarket_bars(
    df: pd.DataFrame,
    session_date: date,
    as_of: datetime,
    allow_after_open: bool,
) -> pd.DataFrame:
    """Return canonical pre-market bars for the session ending at the earlier of as_of and the open.

    Bars are sorted ascending, deduplicated (last wins), and restricted to the
    same calendar date from 04:00 ET up to (but not including) the regular open.
    """
    if df.empty:
        return df
    session = get_market_session(session_date)
    if session is None:
        return df.iloc[0:0]

    premarket_start = datetime.combine(session_date, PREMARKET_OPEN_TIME, tzinfo=MARKET_TIMEZONE)
    window_end = min(as_of, session.opens_at)
    if window_end <= premarket_start:
        return df.iloc[0:0]

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    ny_index = df.index.tz_convert(MARKET_TIMEZONE)
    mask = (
        (ny_index.date == session_date)
        & (ny_index >= premarket_start)
        & (ny_index < session.opens_at)
        & (ny_index <= window_end)
    )
    return df.loc[mask]


def _validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with non-finite or missing OHLCV values; zero volume is valid."""
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            return df.iloc[0:0]
    subset = ["open", "high", "low", "close"]
    for col in subset:
        df = df[df[col].apply(lambda x: isinstance(x, (int, float)) and math.isfinite(x))]
    if "volume" in df.columns:
        df = df[df["volume"].apply(lambda x: isinstance(x, (int, float)) and math.isfinite(float(x)))]
    return df


def build_premarket_snapshot(
    bars: pd.DataFrame,
    ticker: str,
    session_date: date,
    as_of: datetime,
    requested_provider: str | None,
    actual_provider: str | None,
) -> PremarketSnapshot:
    """Build a PremarketSnapshot from filtered, canonical pre-market bars."""
    bars = _validate_ohlcv(bars)
    if bars.empty:
        return PremarketSnapshot(
            ticker=ticker,
            session_date=session_date,
            requested_provider=requested_provider,
            actual_provider=actual_provider,
            first_bar_time=None,
            last_bar_time=None,
            bar_count=0,
            premarket_open=None,
            premarket_high=None,
            premarket_low=None,
            premarket_last=None,
            premarket_volume=0,
            premarket_dollar_volume=0.0,
            premarket_vwap=None,
            data_age_minutes=None,
        )

    first_bar_time = bars.index[0]
    last_bar_time = bars.index[-1]
    as_of_utc = _as_utc(as_of)
    if last_bar_time.tzinfo is None:
        last_bar_time_utc = last_bar_time
    else:
        last_bar_time_utc = last_bar_time.astimezone(UTC)
    if last_bar_time_utc > as_of_utc:
        raise ValueError("Latest pre-market bar is after as_of; point-in-time filtering failed.")

    data_age_minutes = (as_of_utc - last_bar_time_utc).total_seconds() / 60.0
    premarket_open = float(bars["open"].iloc[0])
    premarket_high = float(bars["high"].max())
    premarket_low = float(bars["low"].min())
    premarket_last = float(bars["close"].iloc[-1])
    premarket_volume = int(bars["volume"].sum())

    typical = ((bars["high"] + bars["low"] + bars["close"]) / 3.0).astype(float)
    dollar_volume = float((typical * bars["volume"].astype(float)).sum())
    premarket_vwap = (dollar_volume / premarket_volume) if premarket_volume > 0 else None

    return PremarketSnapshot(
        ticker=ticker,
        session_date=session_date,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        first_bar_time=first_bar_time,
        last_bar_time=last_bar_time,
        bar_count=len(bars),
        premarket_open=premarket_open,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
        premarket_last=premarket_last,
        premarket_volume=premarket_volume,
        premarket_dollar_volume=dollar_volume,
        premarket_vwap=premarket_vwap,
        data_age_minutes=data_age_minutes,
    )


def _fetch_yahoo_premarket_bars(
    ticker: str,
    as_of: datetime,
    session_date: date,
    requested_provider: str,
    allow_after_open: bool = False,
) -> PremarketBarsResult:
    """Fetch 1-minute pre/post history from Yahoo and filter to the pre-market window."""
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="5d", interval="1m", prepost=True)
    except Exception as exc:  # noqa: BLE001
        return PremarketBarsResult(
            ticker=ticker,
            requested_provider=requested_provider,
            actual_provider=None,
            session_date=session_date,
            bars=pd.DataFrame(),
            attempts=1,
            retries=0,
            error=exc,
        )

    if df.empty:
        return PremarketBarsResult(
            ticker=ticker,
            requested_provider=requested_provider,
            actual_provider=requested_provider,
            session_date=session_date,
            bars=pd.DataFrame(),
            attempts=1,
            retries=0,
            error=None,
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    df.index = pd.to_datetime(df.index, utc=True)
    df = _filter_premarket_bars(df, session_date, as_of, allow_after_open=allow_after_open)
    return PremarketBarsResult(
        ticker=ticker,
        requested_provider=requested_provider,
        actual_provider=requested_provider,
        session_date=session_date,
        bars=df,
        attempts=1,
        retries=0,
        error=None,
    )


def fetch_premarket_bars(
    ticker: str,
    *,
    provider: str | None,
    as_of: datetime,
    allow_after_open: bool = False,
) -> PremarketBarsResult:
    """Return canonical UTC-aware pre-market bars for ``ticker`` on the session of ``as_of``.

    Only Yahoo is currently supported; other providers raise ProviderCapabilityError
    rather than falling back silently.
    """
    as_of_utc = _as_utc(as_of)
    ny_as_of = _ny(as_of_utc)
    session_date = ny_as_of.date()
    requested_provider = resolve_premarket_provider(provider)

    if not is_trading_day(session_date):
        return PremarketBarsResult(
            ticker=ticker,
            requested_provider=requested_provider,
            actual_provider=None,
            session_date=None,
            bars=pd.DataFrame(),
            attempts=0,
            retries=0,
            error=None,
        )

    window = _premarket_window(session_date, ny_as_of, allow_after_open=allow_after_open)
    if window is None:
        return PremarketBarsResult(
            ticker=ticker,
            requested_provider=requested_provider,
            actual_provider=requested_provider,
            session_date=session_date,
            bars=pd.DataFrame(),
            attempts=0,
            retries=0,
            error=None,
        )

    if requested_provider == "yahoo":
        return _fetch_yahoo_premarket_bars(ticker, as_of_utc, session_date, requested_provider, allow_after_open=allow_after_open)

    # Should be unreachable because of resolve_premarket_provider.
    raise ProviderCapabilityError(
        f"Provider '{requested_provider}' does not yet support pre-market/extended-hours quotes"
    )


def _previous_sessions(end_date: date, n: int) -> list[date]:
    """Return up to ``n`` completed XNYS session dates ending with ``end_date`` (inclusive)."""
    from tradex.market.hours import _calendar

    cal = _calendar()
    sessions: list[date] = []
    current = end_date
    for _ in range(n):
        sessions.append(current)
        try:
            current = cal.previous_session(current).date()
        except Exception:  # noqa: BLE001
            break
    sessions.reverse()
    return sessions


def compute_liquidity_baseline(
    daily_df: pd.DataFrame,
    lookback_sessions: int,
    target_session_date: date,
) -> DailyLiquidityBaseline:
    """Compute average/median daily volume and dollar volume from ``daily_df``.

    Only bars whose UTC calendar date falls on valid completed XNYS sessions are
    included, and the target session is excluded.
    """
    from tradex.market.hours import _calendar

    cal = _calendar()
    if daily_df.empty or "close" not in daily_df.columns or "volume" not in daily_df.columns:
        return DailyLiquidityBaseline(
            previous_session_date=None,
            previous_close=None,
            lookback_sessions_requested=lookback_sessions,
            lookback_sessions_available=0,
            average_daily_volume=0.0,
            median_daily_volume=0.0,
            average_daily_dollar_volume=0.0,
            median_daily_dollar_volume=0.0,
        )

    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    valid_dates = set()
    previous_session_date = None
    try:
        previous_session_date = cal.previous_session(target_session_date).date()
        valid_dates = set(_previous_sessions(previous_session_date, lookback_sessions))
    except Exception:  # noqa: BLE001
        valid_dates = set()

    df = df[~df.index.duplicated(keep="last")]
    df["session_date"] = df.index.to_series().dt.date
    df = df[df["session_date"].isin(valid_dates)]
    df = df.dropna(subset=["close", "volume"])
    df["dollar_volume"] = df["close"].astype(float) * df["volume"].astype(float)

    previous_close = None
    if previous_session_date is not None and previous_session_date in df["session_date"].values:
        prev_row = df[df["session_date"] == previous_session_date]
        if not prev_row.empty:
            previous_close = float(prev_row["close"].iloc[-1])

    volumes = df["volume"].astype(float).to_numpy()
    dollar_volumes = df["dollar_volume"].astype(float).to_numpy()

    avg_volume = float(volumes.mean()) if len(volumes) else 0.0
    median_volume = float(pd.Series(volumes).median()) if len(volumes) else 0.0
    avg_dollar = float(dollar_volumes.mean()) if len(dollar_volumes) else 0.0
    median_dollar = float(pd.Series(dollar_volumes).median()) if len(dollar_volumes) else 0.0

    return DailyLiquidityBaseline(
        previous_session_date=previous_session_date,
        previous_close=previous_close,
        lookback_sessions_requested=lookback_sessions,
        lookback_sessions_available=len(volumes),
        average_daily_volume=avg_volume,
        median_daily_volume=median_volume,
        average_daily_dollar_volume=avg_dollar,
        median_daily_dollar_volume=median_dollar,
    )


def fetch_daily_liquidity_baseline(
    ticker: str,
    session_date: date,
    *,
    lookback_sessions: int,
    provider: str | None,
    as_of: datetime | None = None,
) -> DailyLiquidityBaseline:
    """Fetch completed daily history and compute the liquidity baseline."""
    try:
        previous_session = previous_trading_session(session_date)
    except Exception:  # noqa: BLE001
        return DailyLiquidityBaseline(
            previous_session_date=None,
            previous_close=None,
            lookback_sessions_requested=lookback_sessions,
            lookback_sessions_available=0,
            average_daily_volume=0.0,
            median_daily_volume=0.0,
            average_daily_dollar_volume=0.0,
            median_daily_dollar_volume=0.0,
        )

    start_dates = _previous_sessions(previous_session.session_date, lookback_sessions)
    if not start_dates:
        return DailyLiquidityBaseline(
            previous_session_date=previous_session.session_date,
            previous_close=None,
            lookback_sessions_requested=lookback_sessions,
            lookback_sessions_available=0,
            average_daily_volume=0.0,
            median_daily_volume=0.0,
            average_daily_dollar_volume=0.0,
            median_daily_dollar_volume=0.0,
        )

    try:
        daily_df = fetch_daily_history(
            ticker,
            start=start_dates[0],
            end=previous_session.session_date,
            provider=provider,
        )
    except Exception:  # noqa: BLE001
        return DailyLiquidityBaseline(
            previous_session_date=previous_session.session_date,
            previous_close=None,
            lookback_sessions_requested=lookback_sessions,
            lookback_sessions_available=0,
            average_daily_volume=0.0,
            median_daily_volume=0.0,
            average_daily_dollar_volume=0.0,
            median_daily_dollar_volume=0.0,
        )

    return compute_liquidity_baseline(daily_df, lookback_sessions, session_date)


def _get_prev_close(ticker: str, provider: str | None = None, as_of: datetime | None = None) -> float | None:
    """Compatibility wrapper that returns only the previous close."""
    as_of = as_of or datetime.now(UTC)
    ny_as_of = _ny(as_of)
    session_date = ny_as_of.date()
    baseline = fetch_daily_liquidity_baseline(
        ticker,
        session_date,
        lookback_sessions=1,
        provider=provider,
        as_of=as_of,
    )
    return baseline.previous_close


def get_premarket_price(ticker: str, provider: str | None = None, as_of: datetime | None = None) -> float | None:
    """Compatibility wrapper that returns the latest pre-market close or None."""
    as_of = as_of or datetime.now(UTC)
    ny_as_of = _ny(as_of)
    session_date = ny_as_of.date()
    if not is_trading_day(session_date):
        return None
    window = _premarket_window(session_date, ny_as_of, allow_after_open=False)
    if window is None:
        return None

    p = (provider or DEFAULT_PROVIDER).lower()
    if p != "yahoo":
        raise ProviderCapabilityError(
            f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
        )

    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="5d", interval="1m", prepost=True)
    except Exception:  # noqa: BLE001
        return None

    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index, utc=True)
    df = _filter_premarket_bars(df, session_date, as_of, allow_after_open=False)
    if df.empty:
        return None
    return float(df["close"].iloc[-1])


def fetch_spread_snapshot(
    ticker: str,
    as_of: datetime,
    provider: str | None,
    quote: dict | None = None,
) -> SpreadSnapshot:
    """Return an actual bid/ask spread snapshot, or explicitly unavailable.

    No intrabar candle range is ever used as a spread estimate. ``quote`` is an
    optional injection for tests; live sources are only enabled when their safe
    contracts already exist in the repository.
    """
    if quote is not None:
        try:
            bid = float(quote["bid"])
            ask = float(quote["ask"])
            ts = quote.get("as_of")
            if ts is not None:
                ts = pd.to_datetime(ts, utc=True).to_pydatetime()
        except Exception as exc:  # noqa: BLE001
            return SpreadSnapshot(available=False, error=exc)
        return _build_spread(bid, ask, as_of, ts, source="injected")

    requested_provider = (provider or DEFAULT_PROVIDER).lower()
    return SpreadSnapshot(available=False, source=requested_provider, as_of=as_of)


def _build_spread(bid: float, ask: float, as_of: datetime, quote_as_of: datetime | None, source: str) -> SpreadSnapshot:
    """Validate a bid/ask pair and compute spread in basis points."""
    try:
        if not math.isfinite(bid) or not math.isfinite(ask):
            raise ValueError("Bid and ask must be finite")
        if bid <= 0 or ask <= 0:
            raise ValueError("Bid and ask must be positive")
        if ask < bid:
            raise ValueError("Ask must be greater than or equal to bid")
        if quote_as_of is not None:
            quote_utc = _as_utc(quote_as_of)
            if quote_utc > _as_utc(as_of):
                raise ValueError("Quote timestamp is after as_of")
        midpoint = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / midpoint) * 10_000.0 if midpoint > 0 else None
        return SpreadSnapshot(
            available=True,
            bid=bid,
            ask=ask,
            midpoint=midpoint,
            spread_bps=spread_bps,
            source=source,
            as_of=quote_as_of,
        )
    except Exception as exc:  # noqa: BLE001
        return SpreadSnapshot(available=False, source=source, as_of=quote_as_of, error=exc)
