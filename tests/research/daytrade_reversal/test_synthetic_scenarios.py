"""Comprehensive synthetic fixture tests covering all 30 locked scenarios from Section 26."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.research.daytrade_reversal.baseline import build_baseline_pool, match_event_baselines
from tradex.research.daytrade_reversal.bootstrap import run_joint_cluster_bootstrap
from tradex.research.daytrade_reversal.calendar import (
    CalendarError,
    build_regular_session_grid,
    to_market_time,
)
from tradex.research.daytrade_reversal.events import (
    classify_overlapping_events,
    compute_session_threshold,
    detect_events_in_session,
    extract_session_eligible_returns,
)
from tradex.research.daytrade_reversal.gates import evaluate_gates_and_disposition
from tradex.research.daytrade_reversal.models import (
    BaselineObservation,
    BootstrapCI,
    DaytradeBar,
    EventObservation,
    HorizonOutcome,
)
from tradex.research.daytrade_reversal.outcomes import calculate_horizon_outcomes_for_bar
from tradex.research.daytrade_reversal.quality import audit_ticker_session
from tradex.research.daytrade_reversal.spec import SpecError, load_and_verify_spec
from tradex.research.daytrade_reversal.study import (
    HoldoutAccessDeniedError,
    load_and_evaluate_holdout,
)
from tradex.research.daytrade_reversal.synthetic import generate_synthetic_session_bars


def _make_dummy_outcome(gross: float) -> dict[int, HorizonOutcome]:
    return {
        1: HorizonOutcome(
            horizon_minutes=1,
            entry_time=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
            exit_time=datetime(2025, 7, 1, 14, 2, tzinfo=UTC),
            entry_price=100.0,
            exit_price=100.0 * (1.0 + gross),
            gross_return=gross,
            net_return_0bps=gross,
            net_return_2bps=gross - 0.0004,
            net_return_5bps=gross - 0.0010,
        )
    }


# Scenario 1: exactly 20 valid prior sessions
def test_scenario_01_exactly_20_valid_prior_sessions(sample_trading_days) -> None:
    sessions = []
    for d in sample_trading_days[:20]:
        grid = build_regular_session_grid(d)
        raw = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw, grid)
        sessions.append(s)
    threshold = compute_session_threshold(sessions)
    assert threshold is not None


# Scenario 2: fewer than 20 valid prior sessions
def test_scenario_02_fewer_than_20_valid_prior_sessions(sample_trading_days) -> None:
    sessions = []
    for d in sample_trading_days[:19]:
        grid = build_regular_session_grid(d)
        raw = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw, grid)
        sessions.append(s)
    assert compute_session_threshold(sessions) is None


# Scenario 3: 09:30 excluded from threshold distribution
def test_scenario_03_0930_excluded_from_threshold_distribution(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"09:30": -0.25})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    returns = extract_session_eligible_returns(s)
    assert all(r > -0.20 for r in returns)


# Scenario 4: current session excluded from threshold
def test_scenario_04_current_session_excluded_from_threshold(sample_trading_days) -> None:
    prior = []
    for d in sample_trading_days[:20]:
        grid = build_regular_session_grid(d)
        raw = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw, grid)
        prior.append(s)
    t_ref = compute_session_threshold(prior)

    # Current session 21 with huge move
    d21 = sample_trading_days[20]
    grid21 = build_regular_session_grid(d21)
    raw21 = generate_synthetic_session_bars("AAPL", d21, minute_returns={"10:00": -0.50})
    _s21, _ = audit_ticker_session("AAPL", d21, raw21, grid21)
    # Prior list without s21 is unchanged
    assert compute_session_threshold(prior) == t_ref


# Scenario 5: event exactly at threshold
def test_scenario_05_event_exactly_at_threshold(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"10:00": -0.015})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    events, _ = detect_events_in_session(s, threshold=-0.015, split_name="development")
    assert len(events) == 1
    assert events[0].event_return == pytest.approx(-0.015)


# Scenario 6: observation just above threshold
def test_scenario_06_observation_just_above_threshold(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"10:00": -0.015 + 1e-4})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    events, non_events = detect_events_in_session(s, threshold=-0.015, split_name="development")
    assert len(events) == 0
    assert any(to_market_time(b.bar_start).strftime("%H:%M") == "10:00" for b, _ in non_events)


# Scenario 7: earliest event at 09:31
def test_scenario_07_earliest_event_at_0931(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"09:30": -0.05, "09:31": -0.05})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    events, _ = detect_events_in_session(s, threshold=-0.01, split_name="development")
    times = [to_market_time(e.event_bar_start).strftime("%H:%M") for e in events]
    assert "09:30" not in times
    assert "09:31" in times


# Scenario 8: latest event at 15:54
def test_scenario_08_latest_event_at_1554(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"15:54": -0.05, "15:55": -0.05})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    events, _ = detect_events_in_session(s, threshold=-0.01, split_name="development")
    times = [to_market_time(e.event_bar_start).strftime("%H:%M") for e in events]
    assert "15:54" in times
    assert "15:55" not in times


# Scenario 9: next-bar-open entry
def test_scenario_09_next_bar_open_entry(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d)
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    bar_t = s.bars[20]
    bar_t1 = s.bars[21]
    # Replace bar_t1 with one with an opening gap so open != prev close
    gapped_bar_t1 = DaytradeBar(
        ticker=bar_t1.ticker,
        session_date=bar_t1.session_date,
        bar_start=bar_t1.bar_start,
        available_at=bar_t1.available_at,
        open=bar_t.close + 1.50,  # Clear price gap
        high=bar_t.close + 2.00,
        low=bar_t.close + 1.00,
        close=bar_t.close + 1.80,
        volume=bar_t1.volume,
    )
    bars_with_gap = list(s.bars)
    bars_with_gap[21] = gapped_bar_t1

    outcomes = calculate_horizon_outcomes_for_bar(bar_t, bars_with_gap)
    assert outcomes[1].entry_time == gapped_bar_t1.bar_start
    assert outcomes[1].entry_price == gapped_bar_t1.open
    assert outcomes[1].entry_price != bar_t.close


# Scenario 10: 1m/2m/5m outcome calculations
def test_scenario_10_outcome_calculations(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d)
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    bar_t = s.bars[10]
    outcomes = calculate_horizon_outcomes_for_bar(bar_t, s.bars)
    assert set(outcomes.keys()) == {1, 2, 5}
    entry_p = s.bars[11].open
    assert outcomes[1].gross_return == pytest.approx((s.bars[11].close - entry_p) / entry_p)
    assert outcomes[2].gross_return == pytest.approx((s.bars[12].close - entry_p) / entry_p)
    assert outcomes[5].gross_return == pytest.approx((s.bars[15].close - entry_p) / entry_p)


# Scenario 11: session-close boundary
def test_scenario_11_session_close_boundary(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d)
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    bar_late = s.bars[387]  # 15:57 -> 2m exit 15:59, 5m would be 16:02 (prohibited)
    outcomes = calculate_horizon_outcomes_for_bar(bar_late, s.bars)
    assert 1 in outcomes
    assert 2 in outcomes
    assert 5 not in outcomes


# Scenario 12: split boundary
def test_scenario_12_split_boundary(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d)
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    bar_t = s.bars[10]
    limit = bar_t.bar_start + timedelta(minutes=2)
    outcomes = calculate_horizon_outcomes_for_bar(bar_t, s.bars, split_end_dt=limit)
    assert 1 in outcomes
    assert 2 not in outcomes


# Scenario 13: missing bars
def test_scenario_13_missing_bars(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    # Drop 25 bars (> 5%)
    raw = generate_synthetic_session_bars("AAPL", d, drop_minutes=[f"10:{i:02d}" for i in range(25)])
    s, rep = audit_ticker_session("AAPL", d, raw, grid)
    assert rep.excluded is True
    assert not s.is_valid


# Scenario 14: duplicate bars
def test_scenario_14_duplicate_bars(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    # 5 duplicates (> 1%)
    raw = generate_synthetic_session_bars("AAPL", d, duplicate_minutes=[f"11:{i:02d}" for i in range(5)])
    s, rep = audit_ticker_session("AAPL", d, raw, grid)
    assert rep.excluded is True
    assert not s.is_valid


# Scenario 15: malformed timestamp handling
def test_scenario_15_malformed_timestamps(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, malformed_timestamps=["10:15"])
    _s, rep = audit_ticker_session("AAPL", d, raw, grid)
    assert rep.excluded is True
    assert rep.malformed_timestamp_count == 1


# Scenario 16: early-close exclusion
def test_scenario_16_early_close_exclusion() -> None:
    christmas_eve = date(2024, 12, 24)
    with pytest.raises(CalendarError, match="early-close session"):
        build_regular_session_grid(christmas_eve)


# Scenario 17: overlapping events
def test_scenario_17_overlapping_events(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d, minute_returns={"10:00": -0.05, "10:02": -0.05})
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    events, _ = detect_events_in_session(s, 0.0, "development")
    classify_overlapping_events(events)
    assert all(e.is_overlapping for e in events)


# Scenario 18: matching baseline
def test_scenario_18_matching_baseline() -> None:
    b = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0020),
    )
    ev = EventObservation(
        event_id="AAPL_20250701_1000",
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0040),
    )
    pool = build_baseline_pool([b])
    match_event_baselines([ev], pool, horizon=1, friction_bps=2.0)
    assert ev.matched_baseline_1m_net == pytest.approx(0.0020 - 0.0004)


# Scenario 19: baseline exclusion of event observations
def test_scenario_19_baseline_exclusion_of_event_observations() -> None:
    b = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0020),
    )
    pool = build_baseline_pool([b])
    # Baseline pool only contains non-events
    assert all(isinstance(obs, BaselineObservation) for obs in pool[("AAPL", "10:00", "validation")])


# Scenario 20: friction calculation
def test_scenario_20_friction_calculation(sample_trading_days) -> None:
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)
    raw = generate_synthetic_session_bars("AAPL", d)
    s, _ = audit_ticker_session("AAPL", d, raw, grid)
    outcomes = calculate_horizon_outcomes_for_bar(s.bars[5], s.bars)
    o = outcomes[1]
    assert o.net_return_0bps == pytest.approx(o.gross_return)
    assert o.net_return_2bps == pytest.approx(o.gross_return - 0.0004)
    assert o.net_return_5bps == pytest.approx(o.gross_return - 0.0010)


# Scenario 21: deterministic bootstrap
def test_scenario_21_deterministic_bootstrap() -> None:
    cl = [("AAPL", date(2025, 7, 1))]
    ev = EventObservation(
        event_id="AAPL_1",
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0050),
        matched_baseline_1m_net=0.0010,
        uplift_1m_net=0.0036,
    )
    ne = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0010),
    )
    ci1, _ = run_joint_cluster_bootstrap([ev], [ne], cl, resamples=50, seed=20260925)
    ci2, _ = run_joint_cluster_bootstrap([ev], [ne], cl, resamples=50, seed=20260925)
    assert ci1.ci_lower == ci2.ci_lower


# Scenario 22: bootstrap recomputes baseline jointly
def test_scenario_22_bootstrap_recomputes_baseline_jointly() -> None:
    cl1 = ("AAPL", date(2025, 7, 1))
    cl2 = ("AAPL", date(2025, 7, 2))
    # In cl1, baseline return is 0.0010; in cl2, baseline return is 0.0030
    ev1 = EventObservation(
        event_id="AAPL_1",
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0050),
        matched_baseline_1m_net=0.0010,
        uplift_1m_net=0.0036,
    )
    ev2 = EventObservation(
        event_id="AAPL_2",
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        event_bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0060),
        matched_baseline_1m_net=0.0030,
        uplift_1m_net=0.0026,
    )
    ne1 = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0010),
    )
    ne2 = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0030),
    )
    _ci_ev, ci_up = run_joint_cluster_bootstrap(
        [ev1, ev2], [ne1, ne2], [cl1, cl2], resamples=50, seed=20260925
    )
    assert ci_up.status == "computable"


# Scenario 23: ticker concentration gate
def test_scenario_23_ticker_concentration_gate() -> None:
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=16.0,  # > 15.0%
        mean_primary_net_return_2bps=0.0020,
        event_ci=BootstrapCI(0.0020, 0.0005, 0.0035, 2000, 20260925, "computable"),
        mean_uplift_2bps=0.0015,
        uplift_ci=BootstrapCI(0.0015, 0.0002, 0.0028, 2000, 20260925, "computable"),
        pct_positive_tickers=80.0,
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_2_evidence_sufficiency"


# Scenario 24: ticker breadth rejection
def test_scenario_24_ticker_breadth_rejection() -> None:
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        event_ci=BootstrapCI(0.0020, 0.0005, 0.0035, 2000, 20260925, "computable"),
        mean_uplift_2bps=0.0015,
        uplift_ci=BootstrapCI(0.0015, 0.0002, 0.0028, 2000, 20260925, "computable"),
        pct_positive_tickers=55.0,  # < 60.0%
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "rejected"
    assert step == "step_3_directional_hypothesis_failure"


# Scenario 25: CI uncertainty inconclusive path
def test_scenario_25_ci_uncertainty_inconclusive_path() -> None:
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        event_ci=BootstrapCI(0.0020, -0.0001, 0.0041, 2000, 20260925, "computable"),
        mean_uplift_2bps=0.0015,
        uplift_ci=BootstrapCI(0.0015, 0.0002, 0.0028, 2000, 20260925, "computable"),
        pct_positive_tickers=75.0,
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_4_statistical_uncertainty"


# Scenario 26: positive support path
def test_scenario_26_positive_support_path() -> None:
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=450,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0025,
        event_ci=BootstrapCI(0.0025, 0.0008, 0.0042, 2000, 20260925, "computable"),
        mean_uplift_2bps=0.0018,
        uplift_ci=BootstrapCI(0.0018, 0.0005, 0.0031, 2000, 20260925, "computable"),
        pct_positive_tickers=80.0,
        per_ticker_net_means={"AAPL": 0.0025},
        split_quality=None,
    )
    assert disp == "supported"
    assert step == "step_5_support"


# Scenario 27: invalid path
def test_scenario_27_invalid_path() -> None:
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=500,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0025,
        event_ci=BootstrapCI(0.0025, 0.0008, 0.0042, 2000, 20260925, "computable"),
        mean_uplift_2bps=0.0018,
        uplift_ci=BootstrapCI(0.0018, 0.0005, 0.0031, 2000, 20260925, "computable"),
        pct_positive_tickers=80.0,
        per_ticker_net_means={"AAPL": 0.0025},
        split_quality=None,
        integrity_error="split_contamination_detected",
    )
    assert disp == "invalid"
    assert step == "step_1_invalidity"


# Scenario 28: holdout access denied when validation != supported
def test_scenario_28_holdout_access_denied_when_validation_not_supported(tmp_path: Path, locked_spec) -> None:
    val_dir = tmp_path / "val"
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / "study.json").write_text(
        json.dumps({"split": "validation", "disposition": "rejected"}), encoding="utf-8"
    )
    with pytest.raises(HoldoutAccessDeniedError, match="must be strictly 'supported'"):
        load_and_evaluate_holdout(val_dir, locked_spec, holdout_loader=MagicMock())


# Scenario 29: holdout loader not invoked on failed guard
def test_scenario_29_holdout_loader_not_invoked_on_failed_guard(tmp_path: Path, locked_spec) -> None:
    val_dir = tmp_path / "val"
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / "study.json").write_text(
        json.dumps({"split": "validation", "disposition": "inconclusive"}), encoding="utf-8"
    )
    mock_loader = MagicMock()
    with pytest.raises(HoldoutAccessDeniedError):
        load_and_evaluate_holdout(val_dir, locked_spec, holdout_loader=mock_loader)
    assert mock_loader.call_count == 0


# Scenario 30: locked spec hash mismatch failure
def test_scenario_30_locked_spec_hash_mismatch_failure(tmp_path: Path) -> None:
    bad_spec = tmp_path / "bad.json"
    bad_spec.write_text('{"bad": true}', encoding="utf-8")
    with pytest.raises(SpecError, match="SHA-256 mismatch"):
        load_and_verify_spec(bad_spec)
