"""Pure deterministic market-wide ORB Opportunity Scanner service.

Implements DAYTRADE-003F:
- Automatically discovers eligible U.S. equities on NYSE and Nasdaq without requiring a user watchlist.
- Executes lean two-stage filtering: inexpensively screens daily history (Price > $5, ADV14 >= 1M, ATR14 > $0.50)
  before acquiring expensive intraday 1-minute opening-range bars.
- Enforces strict 09:35 ET time-gating: candidate ranking is blocked prior to 09:35 ET.
- Evaluates opening range (09:30-09:34 ET) and exact 14-session Relative Volume (RV14 >= 1.0).
- Ranks top 20 by RV descending, symbol ascending tie-breaker.
- Doji setups produce NO_ORDER and are NOT backfilled with rank #21.
- Theoretical protective stop offset (0.10 * ATR14) is displayed relative to future executed fill.
- Accurately audits and discloses universe coverage, feed type (SIP vs IEX), and provisional rankings.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import time as dt_time
from enum import Enum
from typing import Any

from tradex.market.hours import (
    MARKET_TIMEZONE,
    is_trading_day,
    previous_trading_session,
)

from .indicators import (
    compute_adv14,
    compute_atr14_wilder,
    compute_relative_volume,
    get_prior_xnys_sessions,
)
from .models import (
    Candidate,
    Direction,
    OpeningRange,
)
from .preview import (
    RESEARCH_PREVIEW_DISCLAIMER,
    CandidatePreviewRow,
    ExclusionCategory,
    SymbolExclusion,
)
from .provider import ORBMarketDataProvider, ORBProviderError
from .ranking import (
    evaluate_candidate,
    evaluate_opening_range,
    rank_and_select_top_20,
)

logger = logging.getLogger(__name__)

ORB_RANKING_EARLIEST_TIME = dt_time(9, 35)


class ScanStage(str, Enum):
    """Execution stages of the market-wide ORB opportunity scan."""

    INIT = "INIT"
    DISCOVERY = "DISCOVERY"
    DAILY_ELIGIBILITY = "DAILY_ELIGIBILITY"
    OPENING_RANGE = "OPENING_RANGE"
    RANKING = "RANKING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ScanProgress:
    """Progress snapshot emitted during scanner execution."""

    stage: ScanStage
    message: str
    discovered_count: int = 0
    evaluated_daily_count: int = 0
    daily_qualified_count: int = 0
    or_evaluated_count: int = 0
    eligible_candidates_count: int = 0
    stage_timings: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketScanResult:
    """Immutable result of a market-wide ORB opportunity scan."""

    session_date: date
    as_of_time: datetime
    provider: str
    feed: str
    is_feed_consolidated: bool
    feed_disclosure: str
    universe_size_discovered: int
    securities_evaluated: int
    daily_eligible_count: int
    eligible_candidates_count: int
    top_n_selected: int
    candidates: list[CandidatePreviewRow]
    unranked_eligible_candidates: list[Candidate]
    exclusions: list[SymbolExclusion]
    is_time_gated: bool
    time_gate_message: str | None
    coverage_completeness_pct: float
    coverage_status: str  # "full_market_sip" | "provisional_iex" | "provisional_incomplete" | "failed" | "time_gated" | "no_qualifying_candidates" | "empty"
    coverage_warning: str
    warnings: list[str]
    scan_requested_at: datetime | None = None
    scan_completed_at: datetime | None = None
    or_window_end_time: datetime | None = None
    data_freshness_time: datetime | None = None
    daily_history_complete_count: int = 0
    or_observations_valid_count: int = 0
    rv_baseline_complete_count: int = 0
    missing_data_count: int = 0
    stage_failures: dict[str, str] = field(default_factory=dict)
    disclaimer: str = RESEARCH_PREVIEW_DISCLAIMER

    @property
    def as_of_time_et(self) -> datetime:
        return self.as_of_time.astimezone(MARKET_TIMEZONE)

    @property
    def scan_requested_at_et(self) -> datetime | None:
        return self.scan_requested_at.astimezone(MARKET_TIMEZONE) if self.scan_requested_at else None

    @property
    def scan_completed_at_et(self) -> datetime | None:
        return self.scan_completed_at.astimezone(MARKET_TIMEZONE) if self.scan_completed_at else None

    @property
    def or_window_end_time_et(self) -> datetime | None:
        target = self.or_window_end_time or self.data_freshness_time
        return target.astimezone(MARKET_TIMEZONE) if target else None

    @property
    def data_freshness_time_et(self) -> datetime | None:
        return self.or_window_end_time_et


def _build_candidate_row(
    rank: int,
    cand: Candidate,
    op_range: OpeningRange,
    intent: Any,
) -> CandidatePreviewRow:
    """Build a user-facing CandidatePreviewRow with rich setup explanations."""
    if op_range.direction == Direction.LONG:
        trigger = intent.stop_level
        exp = (
            f"Rank {rank}: Bullish OR (${op_range.or_open:.2f} -> ${op_range.or_close:.2f}) qualifies LONG setup. "
            f"Breakout trigger at OR High ${trigger:.2f}. "
            f"RV14 {cand.relative_volume:.2f}x ({op_range.or_volume:,.0f} shares vs 14-day baseline {cand.mean_prior_or_volume:,.0f}). "
            f"ADV14 {cand.adv14:,.0f}, ATR14 ${cand.atr14:.2f}, theoretical stop offset ±${intent.protective_stop_offset:.2f}."
        )
    elif op_range.direction == Direction.SHORT:
        trigger = intent.stop_level
        exp = (
            f"Rank {rank}: Bearish OR (${op_range.or_open:.2f} -> ${op_range.or_close:.2f}) qualifies SHORT setup. "
            f"Breakout trigger at OR Low ${trigger:.2f}. "
            f"RV14 {cand.relative_volume:.2f}x ({op_range.or_volume:,.0f} shares vs 14-day baseline {cand.mean_prior_or_volume:,.0f}). "
            f"ADV14 {cand.adv14:,.0f}, ATR14 ${cand.atr14:.2f}, theoretical stop offset ±${intent.protective_stop_offset:.2f}."
        )
    else:
        trigger = None
        exp = (
            f"Rank {rank}: Doji OR (${op_range.or_open:.2f} == ${op_range.or_close:.2f}) qualifies by volume but produces NO ORDER. "
            f"Rank #21 is not backfilled pursuant to published strategy methodology. "
            f"RV14 {cand.relative_volume:.2f}x, ADV14 {cand.adv14:,.0f}, ATR14 ${cand.atr14:.2f}."
        )

    return CandidatePreviewRow(
        rank=rank,
        symbol=cand.symbol,
        direction=op_range.direction,
        or_open=op_range.or_open,
        or_high=op_range.or_high,
        or_low=op_range.or_low,
        or_close=op_range.or_close,
        or_volume=op_range.or_volume,
        adv14=cand.adv14,
        atr14=cand.atr14,
        rv14=cand.relative_volume,
        stop_entry_trigger=trigger,
        theoretical_stop_offset=intent.protective_stop_offset,
        order_intent_status=intent.status,
        explanation=exp,
    )


def run_market_scan(
    provider: ORBMarketDataProvider,
    session_date: date | None = None,
    as_of_time: datetime | None = None,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    top_n: int = 20,
) -> MarketScanResult:
    """Execute an end-to-end market-wide ORB opportunity scan.

    Stages:
    1. Validate calendar session and enforce 09:35 ET time-gating.
    2. Stage 1 — Discover active NYSE and Nasdaq universe.
    3. Stage 2 — Broad daily screening: fetch 15 completed XNYS daily bars (D-15..D-1)
       and filter Price > $5, ADV14 >= 1M, ATR14 > $0.50.
    4. Stage 3 — Opening-range evaluation: fetch 09:30-09:34 ET bars for session D
       and prior 14 completed XNYS sessions for daily-qualified candidates; filter RV14 >= 1.0.
    5. Stage 4 — Rank Top 20 by RV descending (ticker ascending tie-breaker).
    6. Stage 5 — Disclose coverage completeness, feed type (SIP vs IEX), and provisional warnings.
    """
    timings: dict[str, float] = {}
    stage_failures: dict[str, str] = {}
    warnings: list[str] = []

    # -------------------------------------------------------------------------
    # Timing and Session Resolution
    # -------------------------------------------------------------------------
    # If provider specifies a default historical demo session (e.g. Mock populated fixture), adopt it
    provider_default_as_of = getattr(provider, "default_as_of_time", None)
    if as_of_time is None and provider_default_as_of is not None:
        as_of_time = provider_default_as_of
    provider_default_session = getattr(provider, "default_session_date", None)
    if session_date is None and provider_default_session is not None:
        session_date = provider_default_session

    now_et = datetime.now(MARKET_TIMEZONE)
    if as_of_time is None:
        eval_as_of = now_et
    else:
        eval_as_of = as_of_time.astimezone(MARKET_TIMEZONE)

    if session_date is None:
        eval_date = eval_as_of.date()
        # If weekend or holiday, use previous trading session
        if not is_trading_day(eval_date):
            prev_sess = previous_trading_session(eval_date)
            eval_date = prev_sess.session_date
            warnings.append(
                f"Market is closed on {eval_as_of.date().isoformat()}; scanning last completed session {eval_date.isoformat()}."
            )
    else:
        eval_date = session_date

    scan_requested_at = datetime.now(MARKET_TIMEZONE)
    or_window_end_time = datetime.combine(eval_date, dt_time(9, 34, 59), tzinfo=MARKET_TIMEZONE)
    data_freshness_time = or_window_end_time

    def _notify(stage: ScanStage, msg: str, **kwargs: Any) -> None:
        if progress_callback:
            progress_callback(
                ScanProgress(
                    stage=stage,
                    message=msg,
                    stage_timings=timings,
                    **kwargs,
                )
            )

    _notify(ScanStage.INIT, f"Initializing market-wide scan for session {eval_date.isoformat()}...")

    # -------------------------------------------------------------------------
    # Time-Gating Check
    # -------------------------------------------------------------------------
    # If evaluating today's session and current time is before 09:35:00 ET, candidate ranking is strictly blocked
    is_today = (eval_date == eval_as_of.date())
    is_before_935 = is_today and (eval_as_of.time() < ORB_RANKING_EARLIEST_TIME)

    if is_before_935:
        gate_msg = (
            f"Candidate ranking is blocked: as-of time {eval_as_of.strftime('%H:%M:%S %Z')} "
            f"is prior to {ORB_RANKING_EARLIEST_TIME.strftime('%H:%M')} ET. "
            "The 5-minute Opening Range Breakout strategy requires complete 09:30–09:34 ET regular-session bars."
        )
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=scan_requested_at,
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=0,
            securities_evaluated=0,
            daily_eligible_count=0,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            is_time_gated=True,
            time_gate_message=gate_msg,
            coverage_completeness_pct=0.0,
            coverage_status="time_gated",
            coverage_warning="Scan is time-gated before 09:35 ET; no ranking performed.",
            warnings=[gate_msg],
        )

    # -------------------------------------------------------------------------
    # STAGE 1: Broad Universe Discovery
    # -------------------------------------------------------------------------
    t0 = time.time()
    _notify(ScanStage.DISCOVERY, "Stage 1: Discovering active NYSE and Nasdaq equities...")
    try:
        discovered_universe = provider.discover_universe()
        timings["discovery"] = round(time.time() - t0, 3)
    except ORBProviderError as err:
        err_msg = f"Universe discovery failed at Stage 1: {err}"
        stage_failures["DISCOVERY"] = str(err)
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=0,
            securities_evaluated=0,
            daily_eligible_count=0,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=0.0,
            coverage_status="failed",
            coverage_warning="Scan failed during universe discovery.",
            warnings=[err_msg],
            stage_failures=stage_failures,
        )

    universe_size = len(discovered_universe)
    _notify(
        ScanStage.DISCOVERY,
        f"Stage 1 Complete: Discovered {universe_size:,} active U.S. equities.",
        discovered_count=universe_size,
    )

    if universe_size == 0:
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=0,
            securities_evaluated=0,
            daily_eligible_count=0,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=0.0,
            coverage_status="empty",
            coverage_warning="Discovered universe was empty.",
            warnings=["Discovered universe was empty."],
        )

    # -------------------------------------------------------------------------
    # STAGE 2: Daily History & Liquidity Screening
    # -------------------------------------------------------------------------
    t1 = time.time()
    try:
        prior_15_daily_sessions = get_prior_xnys_sessions(eval_date, 15)
        d_start = prior_15_daily_sessions[0]
        d_end = prior_15_daily_sessions[-1]  # D-1
    except ValueError as err:
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=universe_size,
            securities_evaluated=0,
            daily_eligible_count=0,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=0.0,
            coverage_status="failed",
            coverage_warning=f"Failed to resolve XNYS trading calendar: {err}",
            warnings=[f"Failed to resolve prior trading sessions for {eval_date.isoformat()}: {err}"],
            stage_failures={"CALENDAR": str(err)},
        )

    _notify(
        ScanStage.DAILY_ELIGIBILITY,
        f"Stage 2: Evaluating daily history ({d_start.isoformat()} to {d_end.isoformat()}) across {universe_size:,} securities...",
        discovered_count=universe_size,
    )

    try:
        daily_bars_by_sym = provider.fetch_daily_bars(discovered_universe, d_start, d_end)
    except ORBProviderError as err:
        stage_failures["DAILY_ELIGIBILITY"] = str(err)
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=universe_size,
            securities_evaluated=0,
            daily_eligible_count=0,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=0.0,
            coverage_status="failed",
            coverage_warning="Daily data acquisition failed.",
            warnings=[f"Daily history fetch failed: {err}"],
            stage_failures=stage_failures,
        )

    exclusions: list[SymbolExclusion] = []
    daily_qualified_symbols: list[str] = []
    daily_metrics_by_sym: dict[str, tuple[float, float]] = {}  # sym -> (adv14, atr14)
    daily_history_complete_count = 0

    for sym in sorted(discovered_universe):
        bars = daily_bars_by_sym.get(sym, [])

        # Check for duplicate session dates
        seen_dates: set[date] = set()
        has_dup_date = False
        for b in bars:
            if b.session_date in seen_dates:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason=f"Conflicting duplicate daily bars detected for date {b.session_date.isoformat()}",
                    )
                )
                has_dup_date = True
                break
            seen_dates.add(b.session_date)
        if has_dup_date:
            continue

        # Check for daily bar availability and lookback requirements
        adv14 = compute_adv14(bars, eval_date, 14)
        if adv14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ADV14 non-computable: missing or non-contiguous prior 14 completed XNYS daily sessions",
                )
            )
            continue

        atr14 = compute_atr14_wilder(bars, eval_date, 14)
        if atr14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ATR14 non-computable: requires 15 contiguous completed XNYS daily sessions through D-1",
                )
            )
            continue

        daily_history_complete_count += 1

        # NOTE: Opening price > $5.00 applies to session D opening price at 09:30 ET,
        # NOT prior-session close (DAYTRADE-003B). Evaluated in Stage 3 on or_open.

        # Filter: ADV14 >= 1,000,000 shares
        if adv14 < 1_000_000.0:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"ADV14 {adv14:,.0f} shares < 1,000,000 minimum threshold",
                )
            )
            continue

        # Filter: ATR14 > $0.50
        if atr14 <= 0.50:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"ATR14 ${atr14:.2f} <= $0.50 minimum threshold",
                )
            )
            continue

        daily_qualified_symbols.append(sym)
        daily_metrics_by_sym[sym] = (adv14, atr14)

    timings["daily_screening"] = round(time.time() - t1, 3)
    daily_qual_count = len(daily_qualified_symbols)

    _notify(
        ScanStage.DAILY_ELIGIBILITY,
        f"Stage 2 Complete: {daily_qual_count:,} securities passed daily liquidity screening (ADV >= 1M, ATR > $0.50).",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
    )

    if daily_qual_count == 0:
        missing_count = sum(
            1 for e in exclusions if e.category in (ExclusionCategory.DATA_UNAVAILABLE, ExclusionCategory.INTEGRITY_BLOCKED)
        )
        evaluated_count = universe_size - missing_count
        comp_pct = round((evaluated_count / universe_size) * 100.0, 1) if universe_size > 0 else 0.0
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=universe_size,
            securities_evaluated=evaluated_count,
            daily_history_complete_count=daily_history_complete_count,
            daily_eligible_count=0,
            or_observations_valid_count=0,
            rv_baseline_complete_count=0,
            missing_data_count=missing_count,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=exclusions,
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=comp_pct,
            coverage_status="no_qualifying_candidates",
            coverage_warning="No securities passed the daily liquidity and volatility filters.",
            warnings=["No securities met the ADV >= 1M, ATR > $0.50 criteria."],
        )

    # -------------------------------------------------------------------------
    # STAGE 3: Opening Range & Relative Volume Evaluation
    # -------------------------------------------------------------------------
    t2 = time.time()
    prior_14_sessions = get_prior_xnys_sessions(eval_date, 14)

    _notify(
        ScanStage.OPENING_RANGE,
        f"Stage 3: Evaluating 5-minute opening range and 14-session baseline for {daily_qual_count:,} candidates...",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
    )

    try:
        current_or_bars_by_sym = provider.fetch_opening_range_bars(daily_qualified_symbols, eval_date)
        prior_or_vols_by_sym = provider.fetch_prior_opening_range_volumes(daily_qualified_symbols, prior_14_sessions)
    except ORBProviderError as err:
        stage_failures["OPENING_RANGE"] = str(err)
        missing_count = sum(
            1 for e in exclusions if e.category in (ExclusionCategory.DATA_UNAVAILABLE, ExclusionCategory.INTEGRITY_BLOCKED)
        )
        evaluated_count = universe_size - missing_count
        comp_pct = round((evaluated_count / universe_size) * 100.0, 1) if universe_size > 0 else 0.0
        return MarketScanResult(
            session_date=eval_date,
            as_of_time=eval_as_of,
            scan_requested_at=scan_requested_at,
            scan_completed_at=datetime.now(MARKET_TIMEZONE),
            or_window_end_time=or_window_end_time,
            data_freshness_time=data_freshness_time,
            provider=provider.provider_name,
            feed=provider.feed_name,
            is_feed_consolidated=provider.is_feed_consolidated,
            feed_disclosure=provider.feed_disclosure,
            universe_size_discovered=universe_size,
            securities_evaluated=evaluated_count,
            daily_history_complete_count=daily_history_complete_count,
            daily_eligible_count=daily_qual_count,
            or_observations_valid_count=0,
            rv_baseline_complete_count=0,
            missing_data_count=missing_count,
            eligible_candidates_count=0,
            top_n_selected=0,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=exclusions,
            is_time_gated=False,
            time_gate_message=None,
            coverage_completeness_pct=comp_pct,
            coverage_status="failed",
            coverage_warning="Opening range data retrieval failed.",
            warnings=[f"Opening range fetch failed: {err}"],
            stage_failures=stage_failures,
        )

    eligible_candidates: list[Candidate] = []
    opening_ranges: dict[str, OpeningRange] = {}
    or_observations_valid_count = 0
    rv_baseline_complete_count = 0

    for sym in daily_qualified_symbols:
        adv14, atr14 = daily_metrics_by_sym[sym]
        or_bars = current_or_bars_by_sym.get(sym, [])

        # Check for future-bar leakage in opening range minute bars
        has_future_bar = False
        for b in or_bars:
            bar_et = b.timestamp.astimezone(MARKET_TIMEZONE).time()
            if bar_et >= ORB_RANKING_EARLIEST_TIME:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason=f"Future-bar leakage: bar timestamp {bar_et.strftime('%H:%M:%S')} is at or after 09:35 ET",
                    )
                )
                has_future_bar = True
                break
        if has_future_bar:
            continue

        # Check for duplicate minute bar timestamps in opening range
        seen_ts: set[datetime] = set()
        has_dup_ts = False
        for b in or_bars:
            if b.timestamp in seen_ts:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason=f"Conflicting duplicate opening-range minute bars detected at {b.timestamp.isoformat()}",
                    )
                )
                has_dup_ts = True
                break
            seen_ts.add(b.timestamp)
        if has_dup_ts:
            continue

        # Evaluate opening range (09:30-09:34 ET)
        op_range = evaluate_opening_range(or_bars, require_five_bars=False)
        if op_range is None:
            if len(or_bars) == 0:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.DATA_UNAVAILABLE,
                        reason="No opening range prints in 09:30–09:34 ET regular session (NO_OPENING_PRINT_NO_SETUP)",
                    )
                )
            else:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason="Opening range bars failed validation or contained contradictory timestamps",
                    )
                )
            continue

        or_observations_valid_count += 1

        # Filter: Opening Price > $5.00 (DAYTRADE-003B: Session D regular-session opening print)
        if op_range.or_open <= 5.00:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"Opening price ${op_range.or_open:.2f} <= $5.00 minimum threshold",
                )
            )
            continue

        # Compute Relative Volume over prior 14 completed sessions
        prior_obs = prior_or_vols_by_sym.get(sym, [])
        rv14, mean_prior_or_vol = compute_relative_volume(
            prior_observations=prior_obs,
            current_or_volume=op_range.or_volume,
            target_session=eval_date,
            lookback=14,
        )

        if rv14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="RV14 non-computable: missing prior opening-range observations in the 14-session baseline",
                )
            )
            continue

        rv_baseline_complete_count += 1

        # Filter: Relative Volume >= 1.0
        if rv14 < 1.0:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"Relative volume {rv14:.2f}x < 1.00x threshold (prior OR mean {mean_prior_or_vol:,.0f} shares)",
                )
            )
            continue

        # Construct Candidate
        cand = evaluate_candidate(
            symbol=sym,
            session_date=eval_date,
            opening_range=op_range,
            adv14=adv14,
            atr14=atr14,
            mean_prior_or_volume=mean_prior_or_vol,
            rv=rv14,
        )
        if cand is not None:
            eligible_candidates.append(cand)
            opening_ranges[sym] = op_range

    timings["opening_range"] = round(time.time() - t2, 3)
    eligible_count = len(eligible_candidates)

    _notify(
        ScanStage.OPENING_RANGE,
        f"Stage 3 Complete: {eligible_count:,} candidates met all ORB eligibility requirements (Open > $5, RV14 >= 1.0).",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
        or_evaluated_count=or_observations_valid_count,
        eligible_candidates_count=eligible_count,
    )

    # -------------------------------------------------------------------------
    # STAGE 4: Ranking & Top-20 Selection
    # -------------------------------------------------------------------------
    t3 = time.time()
    _notify(
        ScanStage.RANKING,
        f"Stage 4: Ranking {eligible_count:,} candidates by Relative Volume descending...",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
        or_evaluated_count=or_observations_valid_count,
        eligible_candidates_count=eligible_count,
    )

    ranked_candidates = rank_and_select_top_20(
        candidates=eligible_candidates,
        opening_ranges=opening_ranges,
        top_n=top_n,
    )

    # Sort all eligible candidates to identify unranked outside top_n
    sorted_eligible = sorted(eligible_candidates, key=lambda c: (-c.relative_volume, c.symbol))
    unranked_candidates = sorted_eligible[top_n:]

    preview_rows: list[CandidatePreviewRow] = []
    for rc in ranked_candidates:
        cand = rc.candidate
        op_range = rc.opening_range
        intent = rc.order_intent
        row = _build_candidate_row(rank=rc.rank, cand=cand, op_range=op_range, intent=intent)
        preview_rows.append(row)

    # Record unranked eligible candidates in exclusions
    for unranked_cand in unranked_candidates:
        exclusions.append(
            SymbolExclusion(
                symbol=unranked_cand.symbol,
                category=ExclusionCategory.TECHNICAL_FILTER,
                reason=(
                    f"Passed all eligibility filters (RV14={unranked_cand.relative_volume:.2f}x) "
                    f"but ranked outside the Top {top_n}"
                ),
            )
        )

    timings["ranking"] = round(time.time() - t3, 3)
    timings["total"] = round(sum(timings.values()), 3)

    # -------------------------------------------------------------------------
    # STAGE 5: Truthful Coverage Disclosures & Reporting
    # -------------------------------------------------------------------------
    missing_data_count = sum(
        1 for e in exclusions if e.category in (ExclusionCategory.DATA_UNAVAILABLE, ExclusionCategory.INTEGRITY_BLOCKED)
    )
    securities_evaluated = universe_size - missing_data_count
    completeness_pct = round((securities_evaluated / universe_size) * 100.0, 1) if universe_size > 0 else 0.0

    is_synthetic = (
        provider.provider_name.strip().lower() in ("mock", "synthetic")
        or provider.feed_name.strip().lower() in ("mock", "synthetic")
    )

    if is_synthetic:
        coverage_status = "synthetic_demo"
        cov_warn = (
            f"HISTORICAL SYNTHETIC DEMO: Evaluated {securities_evaluated:,} of {universe_size:,} simulated securities "
            f"({completeness_pct:.1f}% fixture coverage) using synthetic research snapshot fixture. "
            "Rankings are deterministic simulated heuristics and do NOT represent live market data."
        )
        warnings.append(cov_warn)
    elif not provider.is_feed_consolidated:
        coverage_status = "provisional_iex"
        cov_warn = (
            f"PROVISIONAL RANKINGS (IEX FEED ONLY): Evaluated {securities_evaluated:,} of {universe_size:,} securities "
            f"({completeness_pct:.1f}% data completeness) using Alpaca free-tier IEX feed (~2% of market volume). "
            "Relative volume figures reflect IEX exchange activity only and may diverge from the consolidated tape. "
            "Rankings are provisional heuristics over the evaluated provider universe and do NOT represent an authoritative SIP Top 20."
        )
        warnings.append(cov_warn)
    elif missing_data_count > 0 or securities_evaluated < universe_size:
        coverage_status = "provisional_incomplete"
        cov_warn = (
            f"Top 20 of evaluated provider universe — provisional: Evaluated {securities_evaluated:,} of {universe_size:,} discovered "
            f"securities ({completeness_pct:.1f}% data completeness). {missing_data_count:,} securities were excluded due to missing "
            "or incomplete provider data. Rankings are provisional over the evaluated provider universe and do NOT represent an "
            "authoritative full-market Top 20."
        )
        warnings.append(cov_warn)
    else:
        coverage_status = "full_market_sip"
        cov_warn = (
            f"Authoritative full-market candidate discovery: Evaluated all {securities_evaluated:,} of {universe_size:,} discovered securities "
            f"(100.0% verified coverage) using consolidated SIP market data."
        )

    scan_completed_at = datetime.now(MARKET_TIMEZONE)

    _notify(
        ScanStage.COMPLETE,
        f"Scan complete in {timings['total']}s: Selected Top {len(preview_rows)} opportunities from {eligible_count} qualifying candidates.",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
        or_evaluated_count=or_observations_valid_count,
        eligible_candidates_count=eligible_count,
    )

    return MarketScanResult(
        session_date=eval_date,
        as_of_time=eval_as_of,
        scan_requested_at=scan_requested_at,
        scan_completed_at=scan_completed_at,
        or_window_end_time=or_window_end_time,
        data_freshness_time=data_freshness_time,
        provider=provider.provider_name,
        feed=provider.feed_name,
        is_feed_consolidated=provider.is_feed_consolidated,
        feed_disclosure=provider.feed_disclosure,
        universe_size_discovered=universe_size,
        securities_evaluated=securities_evaluated,
        daily_history_complete_count=daily_history_complete_count,
        daily_eligible_count=daily_qual_count,
        or_observations_valid_count=or_observations_valid_count,
        rv_baseline_complete_count=rv_baseline_complete_count,
        missing_data_count=missing_data_count,
        eligible_candidates_count=eligible_count,
        top_n_selected=len(preview_rows),
        candidates=preview_rows,
        unranked_eligible_candidates=unranked_candidates,
        exclusions=exclusions,
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=completeness_pct,
        coverage_status=coverage_status,
        coverage_warning=cov_warn,
        warnings=warnings,
        stage_failures=stage_failures,
    )
