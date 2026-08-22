"""Pre-market gap scanner orchestration and compatibility wrappers.

The public entry point is ``scan_gaps_with_report()``. ``scan_gaps()`` and
``run_gap_alerts()`` preserve their original signatures while delegating to the
new structured report.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import ProviderCapabilityError
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
    GAP_STATUS_BELOW_GAP_THRESHOLD,
    GAP_STATUS_CALCULATION_FAILURE,
    GAP_STATUS_CATALYST_FILTERED,
    GAP_STATUS_LIQUIDITY_FILTERED,
    GAP_STATUS_NO_PREMARKET_DATA,
    GAP_STATUS_NO_PREVIOUS_CLOSE,
    GAP_STATUS_NON_TRADING_DAY,
    GAP_STATUS_OUTSIDE_WINDOW,
    GAP_STATUS_PRICE_FILTERED,
    GAP_STATUS_PROVIDER_FAILURE,
    GAP_STATUS_QUALIFIED,
    GAP_STATUS_SPREAD_FILTERED,
    GAP_STATUS_SPREAD_UNAVAILABLE,
    GAP_STATUS_STALE_DATA,
    GAP_TIERS,
    VALID_TICKER_RE,
    DailyLiquidityBaseline,
    GapCatalystContext,
    GapScanReport,
    PremarketBarsResult,
    PremarketSnapshot,
    SpreadSnapshot,
)
from tradex.premarket.sources import (
    PREMARKET_OPEN_TIME,
    build_premarket_snapshot,
    fetch_daily_liquidity_baseline,
    fetch_premarket_bars,
    fetch_spread_snapshot,
    get_premarket_price,
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
    *,
    settings: TradeXSettings | None = None,
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
            settings=settings,
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


def _classify_gap(gap_pct: float) -> tuple[str, str]:
    """Returns (tier, direction) for a given gap percentage."""
    if gap_pct > 0:
        direction = "up"
    elif gap_pct < 0:
        direction = "down"
    else:
        direction = "flat"
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
        s = str(t).strip().upper().lstrip("$")
        if not s:
            raise ValueError("tickers must not contain empty symbols")
        if not VALID_TICKER_RE.match(s):
            raise ValueError(f"invalid ticker symbol: {t!r}")
        if s not in seen:
            seen.add(s)
            normalized.append(s)
    return normalized


def _primary_status_for_filter_reasons(reasons: list[str]) -> str:
    """Map the first applicable filter reason to a stable primary status."""
    if not reasons:
        return GAP_STATUS_QUALIFIED
    reason = reasons[0]
    if reason.startswith("gap below"):
        return GAP_STATUS_BELOW_GAP_THRESHOLD
    if reason.startswith("price below"):
        return GAP_STATUS_PRICE_FILTERED
    if (
        reason.startswith("pre-market volume")
        or reason.startswith("pre-market dollar volume")
        or reason.startswith("volume ratio")
    ):
        return GAP_STATUS_LIQUIDITY_FILTERED
    if reason.startswith("data age"):
        return GAP_STATUS_STALE_DATA
    if reason == "spread data required but unavailable":
        return GAP_STATUS_SPREAD_UNAVAILABLE
    if reason.startswith("spread"):
        return GAP_STATUS_SPREAD_FILTERED
    if reason.startswith("catalyst"):
        return GAP_STATUS_CATALYST_FILTERED
    return GAP_STATUS_BELOW_GAP_THRESHOLD


def _qualify(
    snapshot: PremarketSnapshot,
    baseline: DailyLiquidityBaseline,
    spread: SpreadSnapshot,
    catalyst: GapCatalystContext,
    prev_close: float,
    gap_pct: float,
    config: GapScanConfig,
) -> tuple[str, list[str], float | None]:
    """Apply filter thresholds and return (primary_status, filter_reasons, volume_ratio)."""
    reasons: list[str] = []

    ratio = _volume_ratio(snapshot, baseline)

    # 1. Minimum absolute gap
    if abs(gap_pct) < config.min_abs_gap_pct:
        reasons.append(f"gap below {config.min_abs_gap_pct}%")

    # 2. Minimum price
    if config.min_price > 0 and (snapshot.premarket_last or 0) < config.min_price:
        reasons.append(f"price below ${config.min_price}")

    # 3. Data freshness
    if (
        config.max_data_age_minutes is not None
        and snapshot.data_age_minutes is not None
        and snapshot.data_age_minutes > config.max_data_age_minutes
    ):
        reasons.append(
            f"data age {snapshot.data_age_minutes:.1f}m exceeds {config.max_data_age_minutes}m"
        )

    # 4. Pre-market share volume
    if config.min_premarket_volume > 0 and snapshot.premarket_volume < config.min_premarket_volume:
        reasons.append(
            f"pre-market volume {snapshot.premarket_volume} below {config.min_premarket_volume}"
        )

    # 5. Pre-market dollar volume
    if (
        config.min_premarket_dollar_volume > 0
        and snapshot.premarket_dollar_volume < config.min_premarket_dollar_volume
    ):
        reasons.append(f"pre-market dollar volume below ${config.min_premarket_dollar_volume:,.0f}")

    # 6. Pre-market volume ratio
    if config.min_premarket_volume_ratio > 0:
        if ratio is None:
            reasons.append(
                f"volume ratio unavailable (baseline avg volume {baseline.average_daily_volume})"
            )
        elif ratio < config.min_premarket_volume_ratio:
            reasons.append(f"volume ratio {ratio:.2f}x below {config.min_premarket_volume_ratio}x")

    # 7. Spread requirement and maximum spread
    if config.require_spread and not spread.available:
        reasons.append("spread data required but unavailable")
    if (
        config.max_spread_bps is not None
        and spread.spread_bps is not None
        and spread.spread_bps > config.max_spread_bps
    ):
        reasons.append(f"spread {spread.spread_bps:.1f} bps exceeds {config.max_spread_bps} bps")

    # 8. Catalyst requirement
    if config.require_catalyst and catalyst.status not in (
        "earnings_today",
        "earnings_soon",
        "recent_headline",
        "earnings_and_recent_headline",
    ):
        reasons.append("catalyst context required but not found")

    if reasons:
        return _primary_status_for_filter_reasons(reasons), reasons, ratio
    return GAP_STATUS_QUALIFIED, [], ratio


def _volume_ratio(snapshot: PremarketSnapshot, baseline: DailyLiquidityBaseline) -> float | None:
    if baseline.error is not None:
        return None
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
    return pd.Series(
        {
            "ticker": ticker,
            "session_date": session_date,
            "status": GAP_STATUS_PROVIDER_FAILURE,
            "requested_provider": requested_provider,
            "actual_provider": actual_provider,
            "error": error,
            "premarket_error": error,
        }
    )


def _premarket_move_pct(open_price: float | None, last_price: float | None) -> float | None:
    if open_price is None or last_price is None or open_price <= 0:
        return None
    return ((last_price / open_price) - 1.0) * 100.0


def _premarket_range_pct(
    prev_close: float | None, high: float | None, low: float | None
) -> float | None:
    """Return the pre-market trading range as a percentage of the previous close."""
    if prev_close is None or high is None or low is None or prev_close <= 0 or low <= 0:
        return None
    return ((high - low) / prev_close) * 100.0


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
    volume_ratio: float | None = None,
    premarket_error: str | None = None,
    calculation_error: str | None = None,
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
    ratio = (
        volume_ratio
        if volume_ratio is not None
        else (_volume_ratio(snap, baseline) if baseline else None)
    )
    move_pct = _premarket_move_pct(snap.premarket_open, snap.premarket_last)
    range_pct = _premarket_range_pct(prev_close, snap.premarket_high, snap.premarket_low)
    baseline_error = str(baseline.error) if baseline and baseline.error is not None else None
    spread_error = None
    if spread and spread.error is not None:
        spread_error = str(spread.error)
    elif spread and not spread.available:
        spread_error = "spread data unavailable"
    catalyst_error = None
    if catalyst and catalyst.error is not None:
        catalyst_error = str(catalyst.error)
    elif catalyst and catalyst.status == "unavailable":
        catalyst_error = "catalyst context unavailable"
    return pd.Series(
        {
            "ticker": ticker,
            "session_date": session_date,
            "previous_session_date": baseline.previous_session_date if baseline else None,
            "prev_close": prev_close,
            "pre_market": snap.premarket_last,
            "premarket_last": snap.premarket_last,
            "premarket_open": snap.premarket_open,
            "premarket_high": snap.premarket_high,
            "premarket_low": snap.premarket_low,
            "premarket_volume": snap.premarket_volume,
            "premarket_dollar_volume": snap.premarket_dollar_volume,
            "premarket_vwap": snap.premarket_vwap,
            "premarket_move_pct": move_pct,
            "premarket_range_pct": range_pct,
            "first_bar_time": snap.first_bar_time,
            "last_bar_time": snap.last_bar_time,
            "bar_count": snap.bar_count,
            "data_age_minutes": snap.data_age_minutes,
            "average_daily_volume": baseline.average_daily_volume if baseline else None,
            "median_daily_volume": baseline.median_daily_volume if baseline else None,
            "average_daily_dollar_volume": baseline.average_daily_dollar_volume
            if baseline
            else None,
            "median_daily_dollar_volume": baseline.median_daily_dollar_volume if baseline else None,
            "liquidity_lookback_sessions": baseline.lookback_sessions_available
            if baseline
            else None,
            "premarket_volume_ratio": ratio,
            "bid": spread.bid if spread and spread.available else None,
            "ask": spread.ask if spread and spread.available else None,
            "midpoint": spread.midpoint if spread and spread.available else None,
            "spread_bps": spread.spread_bps if spread and spread.available else None,
            "spread_source": spread.actual_source
            if spread and spread.available
            else spread.requested_source
            if spread
            else None,
            "spread_available": spread.available if spread else False,
            "catalyst_status": catalyst.status if catalyst else None,
            "earnings_date": catalyst.earnings_date if catalyst else None,
            "days_until_earnings": catalyst.days_until_earnings if catalyst else None,
            "headline_title": catalyst.headline_title if catalyst else None,
            "headline_publisher": catalyst.headline_publisher if catalyst else None,
            "headline_published_at": catalyst.headline_published_at if catalyst else None,
            "headline_source": catalyst.actual_headline_source if catalyst else None,
            "headline_url": catalyst.headline_url if catalyst else None,
            "gap_pct": gap_pct,
            "direction": direction,
            "tier": tier,
            "note": note,
            "filter_reasons": reasons,
            "error": error,
            "baseline_error": baseline_error,
            "premarket_error": premarket_error,
            "spread_error": spread_error,
            "catalyst_error": catalyst_error,
            "calculation_error": calculation_error,
            "requested_provider": requested_provider,
            "actual_provider": actual_provider,
            "status": status,
        }
    )


def _build_result_row(obs: pd.Series) -> pd.Series:
    """Return a copy of the observation as a qualified result row."""
    return obs.copy()


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
    settings: TradeXSettings | None = None,
) -> GapScanReport:
    """Scan a watchlist for pre-market gaps and return a structured report."""
    as_of = as_of or datetime.now(UTC)
    ny_as_of = normalize_market_datetime(as_of)
    session_date = ny_as_of.date()
    config = config or GapScanConfig()
    if settings is None:
        settings = load_runtime_settings()
    requested_tickers = _normalize_tickers(tickers)

    try:
        requested_provider = resolve_premarket_provider(provider, settings=settings)
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

    provider_errors: dict[str, str] = {}

    session = get_market_session(session_date) if is_trading_day(session_date) else None
    premarket_start = datetime.combine(session_date, PREMARKET_OPEN_TIME, tzinfo=MARKET_TIMEZONE)
    outside_reason: str | None = None
    outside_status = GAP_STATUS_OUTSIDE_WINDOW
    if session is None:
        outside_reason = "not an XNYS trading session"
        outside_status = GAP_STATUS_NON_TRADING_DAY
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
                status=outside_status,
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
                provider=requested_provider,
                as_of=as_of,
                settings=settings,
            )
        except Exception as e:  # noqa: BLE001
            baseline = DailyLiquidityBaseline(
                previous_session_date=None,
                previous_close=None,
                lookback_sessions_requested=config.liquidity_lookback_sessions,
                lookback_sessions_available=0,
                average_daily_volume=0.0,
                median_daily_volume=0.0,
                average_daily_dollar_volume=0.0,
                median_daily_dollar_volume=0.0,
                requested_provider=requested_provider,
                actual_provider=None,
                error=e,
            )

        if baseline.error is not None:
            provider_errors[ticker] = str(baseline.error)
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status=GAP_STATUS_PROVIDER_FAILURE,
                requested_provider=requested_provider,
                actual_provider=None,
                prev_close=None,
                snapshot=None,
                baseline=baseline,
                spread=None,
                catalyst=None,
                gap_pct=None,
                direction=None,
                tier=None,
                note=None,
                reasons=[f"baseline provider failure: {baseline.error}"],
                error=str(baseline.error),
            )
            observations.append(obs)
            continue

        prev_close = baseline.previous_close
        if prev_close is None or prev_close <= 0:
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status=GAP_STATUS_NO_PREVIOUS_CLOSE,
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
                provider=requested_provider,
                as_of=as_of,
                allow_after_open=config.allow_after_open,
                settings=settings,
            )
        except Exception as e:  # noqa: BLE001
            bars_result = PremarketBarsResult(
                ticker=ticker,
                requested_provider=requested_provider,
                actual_provider=None,
                session_date=session_date,
                bars=pd.DataFrame(),
                attempts=0,
                retries=0,
                error=e,
            )

        if bars_result.error is not None or bars_result.bars.empty:
            if bars_result.error is not None:
                error_msg = str(bars_result.error)
                provider_errors[ticker] = error_msg
                fail_status = GAP_STATUS_PROVIDER_FAILURE
                fail_reasons = [f"premarket provider failure: {error_msg}"]
            else:
                error_msg = "no pre-market data"
                fail_status = GAP_STATUS_NO_PREMARKET_DATA
                fail_reasons = ["no pre-market data"]
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status=fail_status,
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
                reasons=fail_reasons,
                error=error_msg,
                premarket_error=error_msg,
            )
            observations.append(obs)
            continue

        try:
            snapshot = build_premarket_snapshot(
                bars_result.bars,
                ticker=ticker,
                session_date=session_date,
                as_of=as_of,
                requested_provider=requested_provider,
                actual_provider=bars_result.actual_provider,
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = f"snapshot calculation failure: {exc}"
            obs = _build_observation(
                ticker=ticker,
                session_date=session_date,
                status=GAP_STATUS_CALCULATION_FAILURE,
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
                reasons=[error_msg],
                error=error_msg,
                calculation_error=error_msg,
            )
            observations.append(obs)
            continue

        # Optional spread and catalyst
        spread = fetch_spread_snapshot(ticker, as_of, provider=requested_provider)
        catalyst = fetch_catalyst_context(
            ticker,
            session_date,
            as_of,
            include_catalysts=include_catalysts,
            require_catalyst=config.require_catalyst,
            lookback_hours=config.catalyst_lookback_hours,
            earnings_source=earnings_source,
            headline_source=headline_source,
            settings=settings,
        )

        gap_pct = ((snapshot.premarket_last - prev_close) / prev_close) * 100.0
        tier, direction = _classify_gap(gap_pct)
        note = _gap_note(gap_pct, tier, direction, catalyst.status if catalyst else None)

        status, reasons, volume_ratio = _qualify(
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
            actual_provider=bars_result.actual_provider,
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
            volume_ratio=volume_ratio,
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

    actual_providers = {
        obs.get("actual_provider") for obs in observations if obs.get("actual_provider")
    }
    report_actual_provider = next(iter(sorted(actual_providers))) if actual_providers else None

    return GapScanReport(
        session_date=session_date if session else None,
        as_of=as_of,
        requested_provider=requested_provider,
        actual_provider=report_actual_provider,
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
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """Compatibility wrapper that delegates to ``scan_gaps_with_report``.

    Returns a DataFrame with the original public columns, sorted by absolute gap
    size, largest first. Naive ``as_of`` values are rejected.
    """
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("Naive datetime is not accepted; provide a timezone-aware datetime.")

    config = GapScanConfig(min_abs_gap_pct=min_gap_pct)
    report = scan_gaps_with_report(
        tickers,
        config=config,
        provider=provider,
        as_of=as_of,
        settings=settings,
    )

    if report.provider_errors:
        # Propagate an unsupported-provider failure to preserve the original contract.
        first_error = next(iter(report.provider_errors.values()))
        if "does not yet support" in first_error:
            raise ProviderCapabilityError(first_error)

    public_columns = [
        "ticker",
        "prev_close",
        "pre_market",
        "premarket_last",
        "premarket_open",
        "premarket_high",
        "premarket_low",
        "premarket_volume",
        "premarket_dollar_volume",
        "premarket_vwap",
        "gap_pct",
        "direction",
        "tier",
        "note",
        "requested_provider",
        "actual_provider",
    ]
    df = report.results.copy()
    if df.empty:
        return pd.DataFrame(columns=public_columns)
    df = df[[c for c in public_columns if c in df.columns]]
    for col in [
        "prev_close",
        "pre_market",
        "premarket_last",
        "premarket_open",
        "premarket_high",
        "premarket_low",
        "premarket_vwap",
        "gap_pct",
    ]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: round(x, 2) if pd.notna(x) and isinstance(x, (int, float)) else x
            )
    return df.reset_index(drop=True)


def run_gap_alerts(
    tickers: list[str],
    min_gap_pct: float = 4.0,
    provider: str | None = None,
    as_of: datetime | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """Scan gaps and fire alerts for large/massive ones."""
    from tradex.alerts.notifier import alert_gap

    if settings is None:
        settings = load_runtime_settings()

    try:
        gaps = scan_gaps(
            tickers,
            min_gap_pct=min_gap_pct,
            provider=provider,
            as_of=as_of,
            settings=settings,
        )
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
                settings=settings,
            )
    return gaps
