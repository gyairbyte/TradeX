"""Pure deterministic portfolio metrics, session-date block bootstrap, and validation gates."""
from __future__ import annotations

import math

import numpy as np

from .models import (
    BootstrapCI,
    ExitReason,
    GateEvaluationResult,
    SessionResult,
    StudyMetrics,
    ValidationDisposition,
)

DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20261007
DEFAULT_CONFIDENCE_LEVEL_PCT = 95.0

MIN_REGULAR_SESSIONS_WITH_CANDIDATES = 100
MIN_TRIGGERED_TRADES_TOTAL = 500
MIN_UNIQUE_SECURITIES_TRADED = 50


def compute_study_metrics(session_results: list[SessionResult]) -> StudyMetrics:
    """Compute aggregated portfolio and execution metrics across all valid included sessions.

    CRITICAL INVARIANTS:
    1. Daily return series includes EVERY valid included regular session.
       A valid session with 0 trades contributes exactly 0.0 to daily return and turnover.
    2. Non-computable / integrity-failed sessions never masquerade as zero-return observations.
    3. Excluded early-close sessions (EXCLUDED_EARLY_CLOSE) are excluded from the formal return series.
    4. Daily turnover measures traded notional turnover (sum of entry and exit notional / equity),
       not leverage. Max leverage is tracked separately as max_leverage_used.
    """
    valid_sessions = [s for s in session_results if s.is_valid]
    non_computable_sessions = [
        s for s in session_results if not s.is_valid and s.status != "EXCLUDED_EARLY_CLOSE"
    ]

    total_sessions = len(valid_sessions)
    if total_sessions == 0:
        return StudyMetrics(
            total_sessions_included=0,
            trading_sessions_count=0,
            zero_trade_sessions_count=0,
            qualified_candidates_count=0,
            selected_top_20_count=0,
            orders_placed_count=0,
            triggered_trades_count=0,
            capacity_rejected_count=0,
            long_trades_count=0,
            short_trades_count=0,
            wins_count=0,
            losses_count=0,
            win_rate=0.0,
            gross_pnl=0.0,
            net_pnl_a=0.0,
            net_pnl_b=0.0,
            net_pnl_c=0.0,
            mean_r_multiple=0.0,
            median_r_multiple=0.0,
            stop_out_rate=0.0,
            eod_exit_rate=0.0,
            same_bar_ambiguity_count=0,
            non_computable_count=len(non_computable_sessions),
            max_gross_exposure=0.0,
            max_leverage_used=0.0,
            mean_daily_return_a=0.0,
            mean_daily_return_b=0.0,
            mean_daily_return_c=0.0,
            cumulative_net_return_b=0.0,
            annualized_return_b=0.0,
            annualized_volatility_b=0.0,
            sharpe_ratio_b=0.0,
            max_drawdown_b=0.0,
            worst_day_return_b=0.0,
            daily_turnover=0.0,
        )

    all_trades = [t for s in valid_sessions for t in s.trades]
    trading_sessions = sum(1 for s in valid_sessions if s.trades_triggered_count > 0)
    zero_trade_sessions = total_sessions - trading_sessions

    qualified_cands = sum(s.qualified_candidate_count for s in valid_sessions)
    selected_top20 = sum(s.top_20_count for s in valid_sessions)
    orders_placed = sum(s.orders_placed_count for s in valid_sessions)
    trades_triggered = len(all_trades)
    capacity_rejected = sum(s.capacity_rejected_count for s in valid_sessions)

    long_trades = sum(1 for t in all_trades if t.direction.value == "LONG")
    short_trades = sum(1 for t in all_trades if t.direction.value == "SHORT")

    wins = sum(1 for t in all_trades if t.net_pnl_b > 0.0)
    losses = sum(1 for t in all_trades if t.net_pnl_b < 0.0)
    win_rate = float(wins / trades_triggered) if trades_triggered > 0 else 0.0

    gross_pnl = sum(t.gross_pnl for t in all_trades)
    net_pnl_a = sum(t.net_pnl_a for t in all_trades)
    net_pnl_b = sum(t.net_pnl_b for t in all_trades)
    net_pnl_c = sum(t.net_pnl_c for t in all_trades)

    r_multiples = [t.r_multiple for t in all_trades]
    mean_r = float(np.mean(r_multiples)) if r_multiples else 0.0
    median_r = float(np.median(r_multiples)) if r_multiples else 0.0

    stop_outs = sum(1 for t in all_trades if t.exit_reason == ExitReason.STOP_LOSS)
    eod_exits = sum(1 for t in all_trades if t.exit_reason == ExitReason.END_OF_DAY)
    stop_out_rate = float(stop_outs / trades_triggered) if trades_triggered > 0 else 0.0
    eod_exit_rate = float(eod_exits / trades_triggered) if trades_triggered > 0 else 0.0

    same_bar_ambiguity = sum(s.same_bar_ambiguity_count for s in valid_sessions)
    non_computable = len(non_computable_sessions)

    max_exposure = max((s.max_gross_exposure for s in valid_sessions), default=0.0)
    max_lev = max((s.max_leverage_used for s in valid_sessions), default=0.0)

    # Daily return series includes every valid included regular session!
    returns_a = [s.session_net_return_a for s in valid_sessions]
    returns_b = [s.session_net_return_b for s in valid_sessions]
    returns_c = [s.session_net_return_c for s in valid_sessions]

    mean_ret_a = float(np.mean(returns_a))
    mean_ret_b = float(np.mean(returns_b))
    mean_ret_c = float(np.mean(returns_c))

    # Compounded cumulative return under Scenario B
    cum_ret_b = float(np.prod([1.0 + r for r in returns_b]) - 1.0)
    ann_ret_b = mean_ret_b * 252.0
    std_ret_b = float(np.std(returns_b, ddof=1)) if len(returns_b) > 1 else 0.0
    ann_vol_b = std_ret_b * math.sqrt(252.0)
    sharpe_b = (ann_ret_b / ann_vol_b) if ann_vol_b > 0 else 0.0

    # Max drawdown on cumulative equity
    equity_curve = [1.0]
    for r in returns_b:
        equity_curve.append(equity_curve[-1] * (1.0 + r))
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        peak = max(peak, val)
        dd = (peak - val) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    worst_day_b = min(returns_b) if returns_b else 0.0

    # Two-sided traded notional turnover:
    # session_traded_notional = sum(abs(shares * raw_entry_price) + abs(shares * raw_exit_price) for trade in completed_trades)
    # session_turnover = session_traded_notional / session_start_equity
    # daily_turnover = mean(session_turnover across valid included full sessions)
    session_turnovers: list[float] = []
    for s in valid_sessions:
        if not s.trades or s.session_start_equity <= 0:
            session_turnovers.append(0.0)
        else:
            traded_notional = sum(
                abs(float(t.shares) * t.raw_entry_price) + abs(float(t.shares) * t.raw_exit_price)
                for t in s.trades
            )
            session_turnovers.append(float(traded_notional / s.session_start_equity))

    daily_turnover = float(np.mean(session_turnovers)) if session_turnovers else 0.0

    return StudyMetrics(
        total_sessions_included=total_sessions,
        trading_sessions_count=trading_sessions,
        zero_trade_sessions_count=zero_trade_sessions,
        qualified_candidates_count=qualified_cands,
        selected_top_20_count=selected_top20,
        orders_placed_count=orders_placed,
        triggered_trades_count=trades_triggered,
        capacity_rejected_count=capacity_rejected,
        long_trades_count=long_trades,
        short_trades_count=short_trades,
        wins_count=wins,
        losses_count=losses,
        win_rate=win_rate,
        gross_pnl=gross_pnl,
        net_pnl_a=net_pnl_a,
        net_pnl_b=net_pnl_b,
        net_pnl_c=net_pnl_c,
        mean_r_multiple=mean_r,
        median_r_multiple=median_r,
        stop_out_rate=stop_out_rate,
        eod_exit_rate=eod_exit_rate,
        same_bar_ambiguity_count=same_bar_ambiguity,
        non_computable_count=non_computable,
        max_gross_exposure=max_exposure,
        max_leverage_used=max_lev,
        mean_daily_return_a=mean_ret_a,
        mean_daily_return_b=mean_ret_b,
        mean_daily_return_c=mean_ret_c,
        cumulative_net_return_b=cum_ret_b,
        annualized_return_b=ann_ret_b,
        annualized_volatility_b=ann_vol_b,
        sharpe_ratio_b=sharpe_b,
        max_drawdown_b=max_dd,
        worst_day_return_b=worst_day_b,
        daily_turnover=daily_turnover,
    )


def run_session_date_bootstrap(
    session_results: list[SessionResult],
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    confidence_level_pct: float = DEFAULT_CONFIDENCE_LEVEL_PCT,
) -> BootstrapCI:
    """Execute deterministic cluster bootstrap by session date.

    Resamples entire session dates with replacement.
    Primary target quantity: mean daily portfolio net return under Scenario B.
    Fail closed: If any required full session is non-computable, bootstrap returns non_computable.
    """
    # Check for corrupted / non-computable sessions
    non_computable = [
        s for s in session_results if not s.is_valid and s.status != "EXCLUDED_EARLY_CLOSE"
    ]
    if non_computable:
        return BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason=f"corrupted_or_non_computable_sessions_present: {len(non_computable)} sessions failed",
        )

    valid_sessions = [s for s in session_results if s.is_valid]
    if not valid_sessions:
        return BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason="no_valid_sessions_available",
        )

    # Sort session dates for deterministic indexing
    sorted_sessions = sorted(valid_sessions, key=lambda s: s.session_date)
    daily_returns_b = np.array([s.session_net_return_b for s in sorted_sessions], dtype=np.float64)
    point_estimate = float(np.mean(daily_returns_b))

    n_sessions = len(daily_returns_b)
    rng = np.random.default_rng(seed)

    # Sample integer indices with replacement: shape (resamples, n_sessions)
    sampled_indices = rng.integers(0, n_sessions, size=(resamples, n_sessions))
    sampled_returns = daily_returns_b[sampled_indices]
    replicate_means = np.mean(sampled_returns, axis=1)

    alpha = (100.0 - confidence_level_pct) / 2.0
    lower_pct = alpha
    upper_pct = 100.0 - alpha

    ci_lower = float(np.percentile(replicate_means, lower_pct))
    ci_upper = float(np.percentile(replicate_means, upper_pct))

    return BootstrapCI(
        point_estimate=point_estimate,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        resamples=resamples,
        seed=seed,
        status="computable",
        error_reason=None,
    )


def evaluate_validation_disposition(
    session_results: list[SessionResult],
    bootstrap_ci: BootstrapCI,
    integrity_error: str | None = None,
) -> tuple[ValidationDisposition, str, str, dict[str, GateEvaluationResult]]:
    """Resolve validation disposition following the locked 5-step precedence hierarchy.

    Precedence:
    1. Material integrity failure -> INVALID
       (Triggered if explicit integrity_error or any required session is non-computable)
    2. Evidence sufficiency failure -> INCONCLUSIVE
       - >= 100 regular sessions with candidates
       - >= 500 triggered trades
       - >= 50 unique securities traded
    3. Primary net return <= 0 -> NOT_SUPPORTED
    4. Point estimate > 0 but 95% CI lower bound <= 0 -> PROMISING_NOT_CONFIRMED
    5. Point estimate > 0 and 95% CI lower bound > 0 -> SUPPORTED

    Returns:
        (disposition, disposition_step, disposition_reason, gates_dict)
    """
    gates: dict[str, GateEvaluationResult] = {}

    # Automatically derive integrity error if any full regular session is non-computable
    if integrity_error is None:
        non_computable = [
            s for s in session_results if not s.is_valid and s.status != "EXCLUDED_EARLY_CLOSE"
        ]
        if non_computable:
            integrity_error = (
                f"Integrity defect: {len(non_computable)} required session(s) non-computable. "
                f"First: {non_computable[0].session_date} ({non_computable[0].error_reason})"
            )

    # Step 1: Integrity Gate
    integrity_passed = integrity_error is None
    gates["integrity_gate"] = GateEvaluationResult(
        gate_name="integrity_gate",
        passed=integrity_passed,
        detail={"integrity_error": integrity_error},
    )

    if not integrity_passed:
        return (
            ValidationDisposition.INVALID,
            "step_1_integrity_gate",
            f"Integrity defect: {integrity_error}",
            gates,
        )

    # Step 2: Evidence Sufficiency Gate (counts ONLY valid included full sessions)
    valid_sessions = [s for s in session_results if s.is_valid]
    sessions_with_cands = sum(1 for s in valid_sessions if s.qualified_candidate_count > 0)
    all_trades = [t for s in valid_sessions for t in s.trades]
    total_trades = len(all_trades)
    unique_secs = len({t.symbol for t in all_trades})

    sessions_ok = sessions_with_cands >= MIN_REGULAR_SESSIONS_WITH_CANDIDATES
    trades_ok = total_trades >= MIN_TRIGGERED_TRADES_TOTAL
    secs_ok = unique_secs >= MIN_UNIQUE_SECURITIES_TRADED
    sufficiency_passed = sessions_ok and trades_ok and secs_ok

    gates["evidence_sufficiency_gate"] = GateEvaluationResult(
        gate_name="evidence_sufficiency_gate",
        passed=sufficiency_passed,
        detail={
            "sessions_with_candidates": sessions_with_cands,
            "min_sessions_required": MIN_REGULAR_SESSIONS_WITH_CANDIDATES,
            "total_trades": total_trades,
            "min_trades_required": MIN_TRIGGERED_TRADES_TOTAL,
            "unique_securities": unique_secs,
            "min_securities_required": MIN_UNIQUE_SECURITIES_TRADED,
        },
    )

    if not sufficiency_passed:
        failures: list[str] = []
        if not sessions_ok:
            failures.append(
                f"sessions_with_candidates ({sessions_with_cands} < {MIN_REGULAR_SESSIONS_WITH_CANDIDATES})"
            )
        if not trades_ok:
            failures.append(f"total_trades ({total_trades} < {MIN_TRIGGERED_TRADES_TOTAL})")
        if not secs_ok:
            failures.append(
                f"unique_securities ({unique_secs} < {MIN_UNIQUE_SECURITIES_TRADED})"
            )
        return (
            ValidationDisposition.INCONCLUSIVE,
            "step_2_evidence_sufficiency_gate",
            "; ".join(failures),
            gates,
        )

    # Step 3: Primary Economics Gate
    mean_ret = bootstrap_ci.point_estimate
    economics_passed = mean_ret is not None and mean_ret > 0.0

    gates["primary_economics_gate"] = GateEvaluationResult(
        gate_name="primary_economics_gate",
        passed=economics_passed,
        detail={
            "mean_daily_return_b": mean_ret,
            "condition": "gt_zero",
        },
    )

    if not economics_passed:
        return (
            ValidationDisposition.NOT_SUPPORTED,
            "step_3_primary_economics_gate",
            f"Mean daily Scenario-B net return <= 0.0 ({mean_ret})",
            gates,
        )

    # Step 4: Statistical Confidence Gate
    ci_passed = (
        bootstrap_ci.status == "computable"
        and bootstrap_ci.ci_lower is not None
        and bootstrap_ci.ci_lower > 0.0
    )

    gates["statistical_confidence_gate"] = GateEvaluationResult(
        gate_name="statistical_confidence_gate",
        passed=ci_passed,
        detail={
            "ci_lower": bootstrap_ci.ci_lower,
            "ci_upper": bootstrap_ci.ci_upper,
            "status": bootstrap_ci.status,
            "condition": "ci_lower_gt_zero",
        },
    )

    if not ci_passed:
        return (
            ValidationDisposition.PROMISING_NOT_CONFIRMED,
            "step_4_statistical_confidence_gate",
            f"Primary point estimate positive ({mean_ret:.6f}) but 95% CI lower bound <= 0 ({bootstrap_ci.ci_lower})",
            gates,
        )

    # Step 5: Support (All gates pass)
    return (
        ValidationDisposition.SUPPORTED,
        "step_5_support",
        "All locked validation gates passed: integrity, evidence sufficiency, positive point estimate, and 95% CI lower bound > 0.",
        gates,
    )
