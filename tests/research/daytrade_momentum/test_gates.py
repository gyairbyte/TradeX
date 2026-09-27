"""Tests for validation gates evaluation and 5-step disposition precedence hierarchy."""
from __future__ import annotations

from tradex.research.daytrade_momentum.gates import (
    evaluate_gates_and_disposition,
)
from tradex.research.daytrade_momentum.models import BootstrapCI, SplitDataQualitySummary


def make_ci(point: float | None, lower: float | None, upper: float | None, status: str = "computable") -> BootstrapCI:
    return BootstrapCI(
        point_estimate=point,
        ci_lower=lower,
        ci_upper=upper,
        resamples=2000,
        seed=20260926,
        status=status,
    )


def test_all_six_gates_pass_supported() -> None:
    """Verify that when all 6 gates pass, disposition is supported at step 5."""
    split_q = SplitDataQualitySummary("val", 100, 3, 3.0, False, {})
    disp, step, _reason, gates = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=12,
        event_session_count=25,
        max_etf_concentration_pct=12.5,
        mean_primary_net_return_2bps=0.0025,
        primary_ci=make_ci(0.0025, 0.0005, 0.0045),
        mean_uplift_2bps=0.0015,
        uplift_ci=make_ci(0.0015, 0.0002, 0.0028),
        pct_positive_etfs=75.0,
        per_etf_net_means={"SPY": 0.002, "QQQ": 0.003},
        split_quality=split_q,
    )

    assert disp == "supported"
    assert step == "step_5_support"
    assert all(g.passed for g in gates.values())


def test_step_1_invalidity_takes_precedence() -> None:
    """Verify integrity defects trigger 'invalid' at step 1 regardless of gate results."""
    disp, step, reason, _ = evaluate_gates_and_disposition(
        event_count=100,
        represented_etfs=15,
        event_session_count=30,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0030,
        primary_ci=make_ci(0.0030, 0.0010, 0.0050),
        mean_uplift_2bps=0.0020,
        uplift_ci=make_ci(0.0020, 0.0005, 0.0035),
        pct_positive_etfs=80.0,
        per_etf_net_means={"SPY": 0.003},
        split_quality=None,
        integrity_error="Checksum mismatch detected in dataset",
    )
    assert disp == "invalid"
    assert step == "step_1_invalidity"
    assert "Checksum mismatch" in reason


def test_step_2_evidence_sufficiency_failure() -> None:
    """Verify that sample, concentration, or DQ failure triggers 'inconclusive' at step 2."""
    # Sub-case A: event count below 75 (e.g. 74)
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=74,  # fails (< 75)
        represented_etfs=12,
        event_session_count=25,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0030,
        primary_ci=make_ci(0.0030, 0.0010, 0.0050),
        mean_uplift_2bps=0.0020,
        uplift_ci=make_ci(0.0020, 0.0005, 0.0035),
        pct_positive_etfs=80.0,
        per_etf_net_means={"SPY": 0.003},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_2_evidence_sufficiency"

    # Sub-case B: concentration > 15.0%
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=12,
        event_session_count=25,
        max_etf_concentration_pct=15.1,  # fails (> 15.0%)
        mean_primary_net_return_2bps=0.0030,
        primary_ci=make_ci(0.0030, 0.0010, 0.0050),
        mean_uplift_2bps=0.0020,
        uplift_ci=make_ci(0.0020, 0.0005, 0.0035),
        pct_positive_etfs=80.0,
        per_etf_net_means={"SPY": 0.003},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_2_evidence_sufficiency"


def test_step_3_directional_hypothesis_failure() -> None:
    """Verify that negative mean net return or negative uplift triggers 'rejected' at step 3."""
    # When sample, conc, dq pass, but mean net return <= 0
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=12,
        event_session_count=25,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=-0.0010,  # <= 0
        primary_ci=make_ci(-0.0010, -0.0030, 0.0010),
        mean_uplift_2bps=0.0010,
        uplift_ci=make_ci(0.0010, 0.0001, 0.0020),
        pct_positive_etfs=50.0,
        per_etf_net_means={"SPY": -0.001},
        split_quality=None,
    )
    assert disp == "rejected"
    assert step == "step_3_directional_hypothesis_failure"


def test_step_4_statistical_significance_failure() -> None:
    """Verify that positive mean but non-significant CI lower <= 0 triggers 'inconclusive' at step 4."""
    # Sample/conc/dq pass, mean > 0, uplift mean > 0, breadth >= 60%, but CI lower <= 0 (e.g. -0.0005)
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=12,
        event_session_count=25,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0015,   # > 0
        primary_ci=make_ci(0.0015, -0.0005, 0.0035),  # CI spans zero!
        mean_uplift_2bps=0.0010,
        uplift_ci=make_ci(0.0010, 0.0001, 0.0020),
        pct_positive_etfs=70.0,
        per_etf_net_means={"SPY": 0.0015},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_4_statistical_uncertainty"


def test_breadth_gate_boundary() -> None:
    """Verify breadth gate exact boundary: 59.9% fails (step 3 rejected), 60.0% passes (supported)."""
    # 59.9% fails breadth gate -> step 3 directional hypothesis failure (rejected)
    disp, step, _, gates = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=10,
        event_session_count=25,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        primary_ci=make_ci(0.0020, 0.0005, 0.0035),
        mean_uplift_2bps=0.0015,
        uplift_ci=make_ci(0.0015, 0.0002, 0.0028),
        pct_positive_etfs=59.9,
        per_etf_net_means={},
        split_quality=None,
    )
    assert gates["breadth_gate"].passed is False
    assert disp == "rejected"
    assert step == "step_3_directional_hypothesis_failure"

    # 60.0% passes breadth gate -> supported
    disp, step, _, gates = evaluate_gates_and_disposition(
        event_count=80,
        represented_etfs=10,
        event_session_count=25,
        max_etf_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        primary_ci=make_ci(0.0020, 0.0005, 0.0035),
        mean_uplift_2bps=0.0015,
        uplift_ci=make_ci(0.0015, 0.0002, 0.0028),
        pct_positive_etfs=60.0,
        per_etf_net_means={},
        split_quality=None,
    )
    assert gates["breadth_gate"].passed is True
    assert disp == "supported"
    assert step == "step_5_support"
