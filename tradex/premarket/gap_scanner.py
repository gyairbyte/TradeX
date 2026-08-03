"""Pre-market gap scanner orchestration and compatibility wrappers.

The public entry point is ``scan_gaps_with_report()``. ``scan_gaps()`` and
``run_gap_alerts()`` preserve their original signatures while delegating to the
new structured report.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import DEFAULT_PROVIDER, ProviderCapabilityError
from tradex.data.history import fetch_daily_history
from tradex.market import (
    MARKET_TIMEZONE,
    get_market_session,
    is_trading_day,
    next_trading_session,
    normalize_market_datetime,
    previous_trading_session,
)
from tradex.premarket.catalysts import fetch_catalyst_context
from tradex.premarket.config import GapScanConfig
from tradex.premarket.models import (
    _OBSERVATION_COLUMNS,
    _RESULT_COLUMNS,
    DEFAULT_MIN_GAP,
    GAP_TIERS,
    DailyLiquidityBaseline,
    GapCatalystContext,
    GapScanReport,
    PremarketSnapshot,
    SpreadSnapshot,
)
from tradex.premarket.sources import (
    PREMARKET_OPEN_TIME,
    _filter_premarket_bars,
    build_premarket_snapshot,
    fetch_daily_liquidity_baseline,
    fetch_premarket_bars,
    fetch_spread_snapshot,
    resolve_premarket_provider,
)

__all__ = [
    "DEFAULT_MIN_GAP",
    "GAP_TIERS",
    "GapScanConfig",
    "_get_prev_close",
    "get_premarket_price",
    "run_gap_alerts",
    "scan_gaps",
    "scan_gaps_with_report",
]


def _get_prev_close(
    ticker: str,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> float | None:
    """Fetch the most recent regular-session closing price before ``as_of``.

    This compatibility wrapper uses the local ``fetch_daily_history`` binding so
    existing tests can patch it at ``gap_scanner.fetch_daily_history``.
    """
    as_of = as_of or datetime.now(UTC)
    ny_as_of = normalize_market_datetime(as_of)
    try:
        current_day = next_trading_session(ny_as_of).session_date
        prev = previous_trading_session(current_day)
        df = fetch_daily_history(
            ticker,
            prev.session_date,
            prev.session_date,
            provider=provider,
        )
        if df.empty or "close" not in df.columns:
            return None
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        mask = idx.date == prev.session_date
        closes = df.loc[mask, "close"].dropna()
        if closes.empty:
            return None
        return float(closes.iloc[-1])
    except ProviderCapabilityError:
        raise
    except Exception:  # noqa: BLE001
        return None


def get_premarket_price(
    ticker: str,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> float | None:
    """Fetch the latest pre-market/extended-hours price before the session open.

    Uses the local ``yf.Ticker`` binding so existing tests can patch it at
    ``gap_scanner.yf.Ticker``.
    """
    as_of = as_of or datetime.now(UTC)
    ny_as_of = normalize_market_datetime(as_of)

    p = (provider or DEFAULT_PROVIDER).lower()
    if p != "yahoo":
        raise ProviderCapabilityError(
            f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
        )

    session_date = ny_as_of.date()
    if not is_trading_day(session_date):
        return None
    session = get_market_session(session_date)
    if session is None:
        return None

    premarket_start = datetime.combine(session_date, PREMARKET_OPEN_TIME, tzinfo=MARKET_TIMEZONE)
    window_end = min(ny_as_of, session.opens_at)
    if window_end <= premarket_start:
        return None

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


def _classify_gap(gap_pct: float) -> tuple[str, str]:
    """Returns (tier, direction) for a given gap percentage."""
    direction = "up" if gap_pct > 0 else "down"
    abs_gap = abs(gap_pct)
    if abs_gap >= GAP_TIERS["massive"]:
        tier = "massive"
    elif abs_gap >= GAP_TIERS["large"]:
        tier = "large"
    elif abs_gap >= GAP_TIERS["moderate"]:
        tier = "moderate"
    else:
        tier = "small"
    return tier, direction


def _gap_note(gap_pct: float, tier: str, direction: str, catalyst_status: str | None) -> str:
    """Plain-English, non-causal context for the gap."""
    base = f"{tier.capitalize()} {direction} gap of {gap_pct:+.2f}%"
    if catalyst_status in ("earnings_today", "earnings_soon"):
        return f"{base}; earnings date noted nearby."
    if catalyst_status == "recent_headline":
        return f"{base}; recent headline present."
    if catalyst_status == "earnings_and_recent_headline":
        return f"{base}; earnings date and recent headline present."
    return f"{base}."


def _normalize_tickers(tickers: list[str]) -> list[str]:
    if not tickers:
        raise ValueError("tickers must not be empty")
    seen: set[str] = set()
    normalized: list[str] = []
    for t in tickers:
        s = str(t).strip().upper()
        if not s:
            raise ValueError("tickers must not contain empty symbols")
        if s not in seen:
            seen.add(s)
            normalized.append(s)
    return normalized


def _qualify(
    snapshot: PremarketSnapshot,
    baseline: DailyLiquidityBaseline,
    spread: SpreadSnapshot,
    catalyst: GapCatalystContext,
    prev_close: float,
    gap_pct: float,
    config: GapScanConfig,
) -> tuple[str, list[str]]:
    """Apply filter thresholds in order and return (status, filter_reasons)."""
    reasons: list[str] = []

    if prev_close <= 0 or prev_close is None or not isinstance(prev_close, (int, float)):
        return "failed", ["invalid previous close"]
    if snapshot.premarket_last is None:
        return "failed", ["no pre-market data"]

    # 3. Minimum absolute gap
    if abs(gap_pct) < config.min_abs_gap_pct:
        reasons.append(f"gap below {config.min_abs_gap_pct}%")

    # 4. Minimum price
    if config.min_price > 0 and (snapshot.premarket_last or 0) < config.min_price:
        reasons.append(f"price below ${config.min_price}")

    # 5. Data freshness
    if (
        config.max_data_age_minutes is not None
        and snapshot.data_age_minutes is not None
        and snapshot.data_age_minutes > config.max_data_age_minutes
    ):
        reasons.append(f"data age {snapshot.data_age_minutes:.1f}m exceeds {config.max_data_age_minutes}m")

    # 6. Pre-market share volume
    if config.min_premarket_volume > 0 and snapshot.premarket_volume < config.min_premarket_volume:
        reasons.append(f"pre-market volume {snapshot.premarket_volume} below {config.min_premarket_volume}")

    # 7. Pre-market dollar volume
    if (
        config.min_premarket_dollar_volume > 0
        and snapshot.premarket_dollar_volume < config.min_premarket_dollar_volume
    ):
        reasons.append(f"pre-market dollar volume below ${config.min_premarket_dollar_volume:,.0f}")

    # 8. Pre-market volume ratio
    ratio = _volume_ratio(snapshot, baseline)
    if (
        config.min_premarket_volume_ratio > 0
        and ratio is not None
        and ratio < config.min_premarket_volume_ratio
    ):
        reasons.append(f"volume ratio {ratio:.2f}x below {config.min_premarket_volume_ratio}x")

    # 9. Spread requirement and maximum spread
    if config.require_spread and not spread.available:
        reasons.append("spread data required but unavailable")
    if (
        config.max_spread_bps is not None
        and spread.spread_bps is not None
        and spread.spread_bps > config.max_spread_bps
    ):
        reasons.append(f"spread {spread.spread_bps:.1f} bps exceeds {config.max_spread_bps} bps")

    # 10. Catalyst requirement
    if config.require_catalyst and catalyst.status not in (
        "earnings_today",
        "earnings_soon",
        "recent_headline",
        "earnings_and_recent_headline",
    ):
        reasons.append("catalyst context required but not found")

    if reasons:
        return "filtered", reasons
    return "qualified", []


def _volume_ratio(snapshot: PremarketSnapshot, baseline: DailyLiquidityBaseline) -> float | None:
    if baseline.average_daily_volume > 0 and snapshot.premarket_volume > 0:
        return snapshot.premarket_volume / baseline.average_daily_volume
    return None


def _snapshot_error_observation(
    ticker: str,
    session_date: date | None,
    requested_provider: str | None,
    actual_provider: str | None,
    error: str,
) -> pd.Series:
    return pd.Series({
        "ticker": ticker,
        "session_date": session_date,
        "status": "failed",
        "requested_provider": requested_provider,
        "actual_provider": actual_provider,
        "error": error,
    })


def _build_observation(
    ticker: str,
    session_date: date | None,
    status: str,
    requested_provider: str | None,
    actual_provider: str | None,
    prev_close: float | None,
    snapshot: PremarketSnapshot | None,
    baseline: DailyLiquidityBaseline | None,
    spread: SpreadSnapshot | None,
    catalyst: GapCatalystContext | None,
    gap_pct: float | None,
    direction: str | None,
    tier: str | None,
    note: str | None,
    reasons: list[str],
    error: str | None,
) -> pd.Series:
    snap = snapshot or PremarketSnapshot(
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
    ratio = _volume_ratio(snap, baseline) if baseline else None
    return pd.Series({
        "ticker": ticker,
        "session_date": session_date,
        "status": status,
        "requested_provider": requested_provider,
        "actual_provider": actual_provider or requested_provider,
        "prev_close": prev_close,
        "pre_market": snap.premarket_last,
        "premarket_last": snap.premarket_last,
        "premarket_open": snap.premarket_open,
        "premarket_high": snap.premarket_high,
        "premarket_low": snap.premarket_low,
        "premarket_volume": snap.premarket_volume,
        "premarket_dollar_volume": snap.premarket_dollar_volume,
        "premarket_vwap": snap.premarket_vwap,
        "data_age_minutes": snap.data_age_minutes,
        "average_daily_volume": baseline.average_daily_volume if baseline else None,
        "premarket_volume_ratio": ratio,
        "spread_bps": spread.spread_bps if spread and spread.available else None,
        "spread_available": spread.available if spread else False,
        "catalyst_status": catalyst.status if catalyst else None,
        "gap_pct": gap_pct,
        "direction": direction,
        "tier": tier,
        "note": note,
        "filter_reasons": reasons,
        "error": error,
    })


def _build_result_row(obs: pd.Series) -> pd.Series:
    """Return the qualified result row matching the original ``scan_gaps`` columns."""
    return pd.Series({
        "ticker": obs["ticker"],
        "prev_close": obs["prev_close"],
        "pre_market": obs["pre_market"],
        "premarket_last": obs["premarket_last"],
        "premarket_open": obs["premarket_open"],
        "premarket_high": obs["premarket_high"],
        "premarket_low": obs["premarket_low"],
        "premarket_volume": obs["premarket_volume"],
        "premarket_dollar_volume": obs["premarket_dollar_volume"],
        "premarket_vwap": obs["premarket_vwap"],
        "data_age_minutes": obs["data_age_minutes"],
        "average_daily_volume": obs["average_daily_volume"],
        "premarket_volume_ratio": obs["premarket_volume_ratio"],
        "spread_bps": obs["spread_bps"],
        "spread_available": obs["spread_available"],
        "catalyst_status": obs["catalyst_status"],
        "gap_pct": obs["gap_pct"],
        "direction": obs["direction"],
        "tier": obs["tier"],
        "note": obs["note"],
        "filter_reasons": obs["filter_reasons"],
        "error": obs["error"],
        "requested_provider": obs["requested_provider"],
        "actual_provider": obs["actual_provider"],
    })


def _sort_results(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by absolute gap descending, then ticker ascending."""
    if df.empty:
        return df
    df = df.copy()
    df["__abs_gap__"] = df["gap_pct"].abs()
    df = df.sort_values(["__abs_gap__", "ticker"], ascending=[False, True])
    return df.drop(columns="__abs_gap__").reset_index(drop=True)


def scan_gaps_with_report(
    tickers: list[str],
    *,
    config: GapScanConfig | None = None,
    provider: str | None = None,
    earnings_source: str | None = None,
    headline_source: str | None = None,
    include_catalysts: bool = False,
    as_of: datetime | None = None,
) -> GapScanReport:
    """Scan a watchlist for pre-market gaps and return a structured report."""
    as_of = as_of or datetime.now(UTC)
    ny_as_of = normalize_market_datetime(as_of)
    session_date = ny_as_of.date()
    config = config or GapScanConfig()
    requested_tickers = _normalize_tickers(tickers)

    try:
        requested_provider = resolve_premarket_provider(provider)
    except ProviderCapabilityError as exc:
        observations = [
            _snapshot_error_observation(
                ticker=t,
                session_date=None,
                requested_provider=provider,
                actual_provider=None,
                error=str(exc),
            )
            for t in requested_tickers
        ]
        return GapScanReport(
            session_date=None,
            as_of=as_of,
            requested_provider=provider,
            actual_provider=None,
            config=config,
            requested_tickers=requested_tickers,
            results=pd.DataFrame(),
            observations=pd.DataFrame(observations),
            provider_errors={t: str(exc) for t in requested_tickers},
        )

    actual_provider: str | None = requested_provider
    provider_errors: dict[str, str] = {}

    session = get_market_session(session_date) if is_trading_day(session_date) else None
    premarket_start = datetime.combine(session_date, PREMARKET_OPEN_TIME, tzinfo=MARKET_TIMEZONE)
    outside_reason: str | None = None
    if session is None:
        outside_reason = "not an XNYS trading session"
    elif not config.allow_after_open and ny_as_of >= session.opens_at:
        outside_reason = "regular session has opened"
    elif ny_as_of < premarket_start:
        outside_reason = "before pre-market session"

    observations: list[pd.Series] = []
    results: list[pd.Series] = []

    for ticker in requested_tickers:
        if outside_reason:
            obs = _build_observation(
                ticker=ticker,
                session_date=None if session is None else session_date,
                status="outside_window",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=None,
                snapshot=None,
                baseline=None,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[outside_reason],
                error=None,
            )
            observations.append(obs)
            continue

        # 1. Previous close and liquidity baseline
        try:
            baseline = fetch_daily_liquidity_baseline(
                ticker,
                session_date,
                lookback_sessions=config.liquidity_lookback_sessions,
                provider=provider,
                as_of=as_of,
            )
            prev_close = baseline.previous_close
        except ProviderCapabilityError as e:
            actual_provider = None
            provider_errors[ticker] = str(e)
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=None,
                snapshot=None,
                baseline=None,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[],
                error=str(e),
            )
            observations.append(obs)
            continue
        except Exception as e:  # noqa: BLE001
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=None,
                snapshot=None,
                baseline=None,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[],
                error=str(e),
            )
            observations.append(obs)
            continue

        if prev_close is None or prev_close <= 0:
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=prev_close,
                snapshot=None,
                baseline=baseline,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=["invalid previous close"],
                error=None,
            )
            observations.append(obs)
            continue

        # 2. Pre-market snapshot
        try:
            bars_result = fetch_premarket_bars(
                ticker,
                provider=provider,
                as_of=as_of,
                allow_after_open=config.allow_after_open,
            )
        except ProviderCapabilityError as e:
            actual_provider = None
            provider_errors[ticker] = str(e)
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=prev_close,
                snapshot=None,
                baseline=baseline,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[],
                error=str(e),
            )
            observations.append(obs)
            continue
        except Exception as e:  # noqa: BLE001
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=prev_close,
                snapshot=None,
                baseline=baseline,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[],
                error=str(e),
            )
            observations.append(obs)
            continue

        if bars_result.error is not None or bars_result.bars.empty:
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status="failed",
                requested_provider=requested_provider,
                actual_provider=bars_result.actual_provider,
                prev_close=prev_close,
                snapshot=None,
                baseline=baseline,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=["no pre-market data"],
                error=str(bars_result.error) if bars_result.error else None,
            )
            observations.append(obs)
            continue

        snapshot = build_premarket_snapshot(
            bars_result.bars,
            ticker=ticker,
            session_date=session_date,
            as_of=as_of,
            requested_provider=requested_provider,
            actual_provider=bars_result.actual_provider,
        )

        # Optional spread and catalyst
        spread = fetch_spread_snapshot(ticker, as_of, provider=provider)
        catalyst = fetch_catalyst_context(
            ticker,
            session_date,
            as_of,
            include_catalysts=include_catalysts,
            require_catalyst=config.require_catalyst,
            lookback_hours=config.catalyst_lookback_hours,
            earnings_source=earnings_source,
            headline_source=headline_source,
        )

        gap_pct = ((snapshot.premarket_last - prev_close) / prev_close) * 100.0
        tier, direction = _classify_gap(gap_pct)
        note = _gap_note(gap_pct, tier, direction, catalyst.status if catalyst else None)

        status, reasons = _qualify(
            snapshot,
            baseline,
            spread,
            catalyst,
            prev_close,
            gap_pct,
            config,
        )

        obs = _build_observation(
            ticker=ticker,
            session_date=session_date,
            status=status,
            requested_provider=requested_provider,
            actual_provider=snapshot.actual_provider,
            prev_close=prev_close,
            snapshot=snapshot,
            baseline=baseline,
            spread=spread,
            catalyst=catalyst,
            gap_pct=gap_pct,
            direction=direction,
            tier=tier,
            note=note,
            reasons=reasons,
            error=None,
        )
        observations.append(obs)
        if status == "qualified":
            results.append(_build_result_row(obs))

    results_df = _sort_results(pd.DataFrame(results))
    observations_df = pd.DataFrame(observations)

    # Ensure columns exist with stable dtypes
    for col, dtype in _RESULT_COLUMNS.items():
        if col not in results_df.columns:
            results_df[col] = pd.Series(dtype=dtype) if dtype is not None else None
    for col, dtype in _OBSERVATION_COLUMNS.items():
        if col not in observations_df.columns:
            observations_df[col] = pd.Series(dtype=dtype) if dtype is not None else None

    return GapScanReport(
        session_date=session_date if session else None,
        as_of=as_of,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        config=config,
        requested_tickers=requested_tickers,
        results=results_df,
        observations=observations_df,
        provider_errors=provider_errors,
    )


def scan_gaps(
    tickers: list[str],
    min_gap_pct: float = DEFAULT_MIN_GAP,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Scan a watchlist for pre-market gaps above the threshold.

    This compatibility wrapper uses the local ``_get_prev_close`` and
    ``get_premarket_price`` bindings so existing callers and tests continue to
    work. It returns a DataFrame with the original columns, sorted by absolute
    gap size, largest first.
    """
    rows = []
    for ticker in tickers:
        try:
            prev_close = _get_prev_close(ticker, provider=provider, as_of=as_of)
            if prev_close is None or prev_close == 0:
                continue
            pre_price = get_premarket_price(ticker, provider=provider, as_of=as_of)
            if pre_price is None:
                continue
            gap_pct = (pre_price - prev_close) / prev_close * 100
            if abs(gap_pct) < min_gap_pct:
                continue
            tier, direction = _classify_gap(gap_pct)
            rows.append({
                "ticker": ticker,
                "prev_close": round(prev_close, 2),
                "pre_market": round(pre_price, 2),
                "gap_pct": round(gap_pct, 2),
                "direction": direction,
                "tier": tier,
                "note": _gap_note(gap_pct, tier, direction, None),
            })
        except ProviderCapabilityError:
            raise
        except Exception:  # noqa: BLE001, S112
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["__abs_gap__"] = df["gap_pct"].abs()
    df = df.sort_values("__abs_gap__", ascending=False).drop(columns="__abs_gap__").reset_index(drop=True)
    return df


def run_gap_alerts(
    tickers: list[str],
    min_gap_pct: float = 4.0,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Scan gaps and fire alerts for large/massive ones."""
    from tradex.alerts.notifier import alert_gap

    try:
        gaps = scan_gaps(tickers, min_gap_pct=min_gap_pct, provider=provider, as_of=as_of)
    except ProviderCapabilityError as e:
        print(f"[gap alert] {e}")
        return pd.DataFrame()

    print(f"[gap alert] {len(gaps)} gaps above {min_gap_pct}%")
    for _, row in gaps.iterrows():
        if row["tier"] in ("large", "massive"):
            alert_gap(
                ticker=row["ticker"],
                gap_pct=row["gap_pct"],
                direction=row["direction"],
                prev_close=row["prev_close"],
                pre_market=row["pre_market"],
            )
    return gaps
