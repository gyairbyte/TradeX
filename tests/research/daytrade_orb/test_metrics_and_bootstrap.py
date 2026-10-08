"""Portfolio metrics, block bootstrap, validation disposition, and holdout guard tests."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb import (
    BootstrapCI,
    Direction,
    ExitReason,
    HoldoutAccessDeniedError,
    SessionResult,
    Trade,
    ValidationDisposition,
    compute_study_metrics,
    evaluate_validation_disposition,
    run_session_date_bootstrap,
    verify_holdout_access_guard,
)

NY_TZ = ZoneInfo("America/New_York")


def _make_dummy_trade(
    sym: str,
    d: date,
    net_pnl: float,
    shares: int = 100,
    direction: Direction = Direction.LONG,
) -> Trade:
    dt = datetime(d.year, d.month, d.day, 9, 36, tzinfo=NY_TZ)
    return Trade(
        symbol=sym,
        direction=direction,
        session_date=d,
        entry_timestamp=dt,
        raw_entry_price=100.0,
        exit_timestamp=dt,
        raw_exit_price=101.0,
        shares=shares,
        protective_stop_price=99.80,
        exit_reason=ExitReason.END_OF_DAY,
        same_bar_ambiguity=False,
        gross_pnl=net_pnl + 5.0,
        entry_commission=2.0,
        exit_commission=2.0,
        total_commission=4.0,
        entry_slippage_cost_a=0.0,
        exit_slippage_cost_a=0.0,
        net_pnl_a=net_pnl + 1.0,
        entry_slippage_cost_b=0.5,
        exit_slippage_cost_b=0.5,
        net_pnl_b=net_pnl,
        entry_slippage_cost_c=1.5,
        exit_slippage_cost_c=1.5,
        net_pnl_c=net_pnl - 2.0,
        r_multiple=1.5,
    )


def _make_dummy_session(
    d: date,
    trades: list[Trade],
    start_equity: float = 25000.0,
) -> SessionResult:
    net_a = sum(t.net_pnl_a for t in trades)
    net_b = sum(t.net_pnl_b for t in trades)
    net_c = sum(t.net_pnl_c for t in trades)
    return SessionResult(
        session_date=d,
        is_valid=True,
        status="completed",
        error_reason=None,
        candidate_count=len(trades),
        qualified_candidate_count=len(trades),
        top_20_count=len(trades),
        orders_placed_count=len(trades),
        trades_triggered_count=len(trades),
        capacity_rejected_count=0,
        trades=tuple(trades),
        session_start_equity=start_equity,
        session_end_equity_a=start_equity + net_a,
        session_end_equity_b=start_equity + net_b,
        session_end_equity_c=start_equity + net_c,
        session_net_pnl_a=net_a,
        session_net_pnl_b=net_b,
        session_net_pnl_c=net_c,
        session_net_return_a=net_a / start_equity,
        session_net_return_b=net_b / start_equity,
        session_net_return_c=net_c / start_equity,
        max_gross_exposure=sum(t.shares * t.raw_entry_price for t in trades),
        max_leverage_used=sum(t.shares * t.raw_entry_price for t in trades) / start_equity,
        same_bar_ambiguity_count=0,
    )


def test_zero_trade_days_included_as_zero_return() -> None:
    """Requirement: Zero-trade sessions must contribute 0.0 to daily return series and not be omitted."""
    d1 = date(2025, 1, 2)
    d2 = date(2025, 1, 3)
    d3 = date(2025, 1, 6)

    # d1 has 1 trade with +$500 net PnL (return = +0.02)
    s1 = _make_dummy_session(d1, [_make_dummy_trade("AAPL", d1, 500.0)])
    # d2 has 0 trades (return = 0.0)
    s2 = _make_dummy_session(d2, [])
    # d3 has 1 trade with +$250 net PnL (return = +0.01)
    s3 = _make_dummy_session(d3, [_make_dummy_trade("AAPL", d3, 250.0)])

    metrics = compute_study_metrics([s1, s2, s3])

    assert metrics.total_sessions_included == 3
    assert metrics.trading_sessions_count == 2
    assert metrics.zero_trade_sessions_count == 1
    # Mean daily return must average over ALL 3 sessions: (0.02 + 0.0 + 0.01) / 3 = 0.01
    assert metrics.mean_daily_return_b == pytest.approx(0.01)


def test_bootstrap_determinism_and_percentiles() -> None:
    """Requirement: Block bootstrap is deterministic for seed 20261007 and computes 95% CI."""
    sessions: list[SessionResult] = []
    base_date = date(2025, 1, 2)
    for i in range(120):
        d = date.fromordinal(base_date.toordinal() + i)
        # Alternate positive and modest negative returns
        pnl = 250.0 if i % 2 == 0 else -100.0
        sessions.append(_make_dummy_session(d, [_make_dummy_trade("AAPL", d, pnl)]))

    ci_run1 = run_session_date_bootstrap(sessions, resamples=500, seed=20261007)
    ci_run2 = run_session_date_bootstrap(sessions, resamples=500, seed=20261007)

    assert ci_run1.status == "computable"
    assert ci_run1.point_estimate == ci_run2.point_estimate
    assert ci_run1.ci_lower == ci_run2.ci_lower
    assert ci_run1.ci_upper == ci_run2.ci_upper
    assert ci_run1.ci_lower is not None and ci_run1.ci_upper is not None
    assert ci_run1.ci_lower <= ci_run1.point_estimate <= ci_run1.ci_upper


def test_validation_disposition_precedence() -> None:
    """Requirement: 5-step hierarchy: INVALID -> INCONCLUSIVE -> NOT_SUPPORTED -> PROMISING_NOT_CONFIRMED -> SUPPORTED."""
    # 1. Integrity failure -> INVALID
    disp_inv, step_inv, _, _ = evaluate_validation_disposition([], BootstrapCI(None, None, None, 2000, 20261007, "non_computable"), integrity_error="Fatal schema mismatch")
    assert disp_inv == ValidationDisposition.INVALID
    assert "step_1" in step_inv

    # 2. Insufficient evidence (< 100 sessions, < 500 trades, < 50 securities) -> INCONCLUSIVE
    dummy_sessions = [_make_dummy_session(date(2025, 1, 2), [_make_dummy_trade("AAPL", date(2025, 1, 2), 100.0)])]
    disp_inc, step_inc, _, _ = evaluate_validation_disposition(dummy_sessions, BootstrapCI(0.01, 0.005, 0.015, 2000, 20261007, "computable"))
    assert disp_inc == ValidationDisposition.INCONCLUSIVE
    assert "step_2" in step_inc

    # Build compliant sample: 110 sessions, 550 trades, 55 unique securities
    compliant_sessions: list[SessionResult] = []
    for s_idx in range(110):
        d = date.fromordinal(date(2025, 1, 2).toordinal() + s_idx)
        trades: list[Trade] = []
        for t_idx in range(5):
            sym = f"SYM{((s_idx * 5 + t_idx) % 55):02d}"
            trades.append(_make_dummy_trade(sym, d, 50.0))
        compliant_sessions.append(_make_dummy_session(d, trades))

    # 3. Negative point estimate -> NOT_SUPPORTED
    ci_neg = BootstrapCI(-0.001, -0.005, 0.003, 2000, 20261007, "computable")
    disp_ns, step_ns, _, _ = evaluate_validation_disposition(compliant_sessions, ci_neg)
    assert disp_ns == ValidationDisposition.NOT_SUPPORTED
    assert "step_3" in step_ns

    # 4. Positive point estimate, but CI lower <= 0 -> PROMISING_NOT_CONFIRMED
    ci_pnc = BootstrapCI(0.002, -0.001, 0.005, 2000, 20261007, "computable")
    disp_pnc, step_pnc, _, _ = evaluate_validation_disposition(compliant_sessions, ci_pnc)
    assert disp_pnc == ValidationDisposition.PROMISING_NOT_CONFIRMED
    assert "step_4" in step_pnc

    # 5. Positive point estimate AND CI lower > 0 -> SUPPORTED
    ci_sup = BootstrapCI(0.004, 0.001, 0.007, 2000, 20261007, "computable")
    disp_sup, step_sup, _, _ = evaluate_validation_disposition(compliant_sessions, ci_sup)
    assert disp_sup == ValidationDisposition.SUPPORTED
    assert "step_5" in step_sup


def test_holdout_access_guard() -> None:
    """Requirement: Holdout access is strictly prohibited unless disposition == SUPPORTED."""
    # Permitted only for SUPPORTED
    proof = verify_holdout_access_guard(ValidationDisposition.SUPPORTED)
    assert proof.authorized is True
    assert proof.validation_disposition == "SUPPORTED"

    # All others raise HoldoutAccessDeniedError
    for invalid_disp in [
        ValidationDisposition.INVALID,
        ValidationDisposition.INCONCLUSIVE,
        ValidationDisposition.NOT_SUPPORTED,
        ValidationDisposition.PROMISING_NOT_CONFIRMED,
        "INVALID",
        "INCONCLUSIVE",
        "NOT_SUPPORTED",
        "PROMISING_NOT_CONFIRMED",
        "UNKNOWN",
    ]:
        with pytest.raises(HoldoutAccessDeniedError, match="Holdout access strictly prohibited"):
            verify_holdout_access_guard(invalid_disp)


def test_turnover_hand_calculation_and_separate_from_leverage() -> None:
    """Requirement: Turnover is two-sided traded notional / equity; max leverage is separate."""
    d1 = date(2025, 1, 2)
    d2 = date(2025, 1, 3)

    # Session 1: 1 trade, 100 shares @ $100 entry ($10,000) and $105 exit ($10,500)
    # Traded notional = $20,500 on $25,000 equity -> session turnover = 20,500 / 25,000 = 0.82
    # Max gross exposure = $10,000 -> max leverage = 10,000 / 25,000 = 0.40
    t1 = Trade(
        symbol="SYM1",
        direction=Direction.LONG,
        session_date=d1,
        entry_timestamp=datetime(2025, 1, 2, 9, 36, tzinfo=NY_TZ),
        raw_entry_price=100.0,
        exit_timestamp=datetime(2025, 1, 2, 10, 0, tzinfo=NY_TZ),
        raw_exit_price=105.0,
        shares=100,
        protective_stop_price=98.0,
        exit_reason=ExitReason.END_OF_DAY,
        same_bar_ambiguity=False,
        gross_pnl=500.0,
        entry_commission=0.35,
        exit_commission=0.35,
        total_commission=0.70,
        entry_slippage_cost_a=0.0,
        exit_slippage_cost_a=0.0,
        net_pnl_a=499.30,
        entry_slippage_cost_b=2.0,
        exit_slippage_cost_b=2.10,
        net_pnl_b=495.20,
        entry_slippage_cost_c=5.0,
        exit_slippage_cost_c=5.25,
        net_pnl_c=489.05,
        r_multiple=2.5,
    )
    s1 = SessionResult(
        session_date=d1,
        is_valid=True,
        status="completed",
        error_reason=None,
        candidate_count=1,
        qualified_candidate_count=1,
        top_20_count=1,
        orders_placed_count=1,
        trades_triggered_count=1,
        capacity_rejected_count=0,
        trades=(t1,),
        session_start_equity=25000.0,
        session_end_equity_a=25499.30,
        session_end_equity_b=25495.20,
        session_end_equity_c=25489.05,
        session_net_pnl_a=499.30,
        session_net_pnl_b=495.20,
        session_net_pnl_c=489.05,
        session_net_return_a=499.30 / 25000.0,
        session_net_return_b=495.20 / 25000.0,
        session_net_return_c=489.05 / 25000.0,
        max_gross_exposure=10000.0,
        max_leverage_used=0.40,
        same_bar_ambiguity_count=0,
    )

    # Session 2: valid full session with 0 trades -> turnover = 0.0, leverage = 0.0
    s2 = _make_dummy_session(d2, [])

    metrics = compute_study_metrics([s1, s2])

    # Hand calculation:
    # Session 1 turnover = 0.82
    # Session 2 turnover = 0.0
    # Mean daily turnover = (0.82 + 0.0) / 2 = 0.41
    assert metrics.daily_turnover == pytest.approx(0.41)
    # Max leverage used across sessions is 0.40 (tracked separately from turnover)
    assert metrics.max_leverage_used == pytest.approx(0.40)


def test_non_computable_session_handling_and_study_disposition() -> None:
    """Requirement: Non-computable session does NOT masquerade as 0.0, causes INVALID disposition."""
    d1 = date(2025, 1, 2)
    d2 = date(2025, 1, 3)

    s1 = _make_dummy_session(d1, [_make_dummy_trade("AAPL", d1, 500.0)])
    s_bad = SessionResult(
        session_date=d2,
        is_valid=False,
        status="non_computable",
        error_reason="Missing trade path bar at 10:00",
        candidate_count=0,
        qualified_candidate_count=0,
        top_20_count=0,
        orders_placed_count=0,
        trades_triggered_count=0,
        capacity_rejected_count=0,
        trades=(),
        session_start_equity=25000.0,
        session_end_equity_a=25000.0,
        session_end_equity_b=25000.0,
        session_end_equity_c=25000.0,
        session_net_pnl_a=0.0,
        session_net_pnl_b=0.0,
        session_net_pnl_c=0.0,
        session_net_return_a=0.0,
        session_net_return_b=0.0,
        session_net_return_c=0.0,
        max_gross_exposure=0.0,
        max_leverage_used=0.0,
        same_bar_ambiguity_count=0,
    )

    metrics = compute_study_metrics([s1, s_bad])
    # Corrupted session is NOT included in valid returns!
    assert metrics.total_sessions_included == 1
    assert metrics.non_computable_count == 1
    assert metrics.mean_daily_return_b == pytest.approx(500.0 / 25000.0)

    # Bootstrap fails closed when corrupted session is present
    bs_ci = run_session_date_bootstrap([s1, s_bad])
    assert bs_ci.status == "non_computable"

    # Disposition automatically evaluates to INVALID due to non-computable session
    disp, step, reason, _ = evaluate_validation_disposition([s1, s_bad], bs_ci)
    assert disp == ValidationDisposition.INVALID
    assert "step_1" in step
    assert "Missing trade path bar" in reason


def test_early_close_session_excluded_from_study_metrics() -> None:
    """Requirement: EXCLUDED_EARLY_CLOSE is omitted from formal return series and metrics."""
    d1 = date(2025, 1, 2)
    d_early = date(2025, 11, 28)

    s1 = _make_dummy_session(d1, [_make_dummy_trade("AAPL", d1, 500.0)])
    s_early = SessionResult(
        session_date=d_early,
        is_valid=False,
        status="EXCLUDED_EARLY_CLOSE",
        error_reason="Exchange early-close session excluded",
        candidate_count=0,
        qualified_candidate_count=0,
        top_20_count=0,
        orders_placed_count=0,
        trades_triggered_count=0,
        capacity_rejected_count=0,
        trades=(),
        session_start_equity=25000.0,
        session_end_equity_a=25000.0,
        session_end_equity_b=25000.0,
        session_end_equity_c=25000.0,
        session_net_pnl_a=0.0,
        session_net_pnl_b=0.0,
        session_net_pnl_c=0.0,
        session_net_return_a=0.0,
        session_net_return_b=0.0,
        session_net_return_c=0.0,
        max_gross_exposure=0.0,
        max_leverage_used=0.0,
        same_bar_ambiguity_count=0,
    )

    metrics = compute_study_metrics([s1, s_early])
    assert metrics.total_sessions_included == 1
    assert metrics.non_computable_count == 0  # Early close is not an integrity error
    assert metrics.mean_daily_return_b == pytest.approx(500.0 / 25000.0)

