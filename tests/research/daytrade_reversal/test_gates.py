"""Validation gates and 5-step disposition precedence tests."""
from __future__ import annotations

from tradex.research.daytrade_reversal.gates import evaluate_gates_and_disposition
from tradex.research.daytrade_reversal.models import BootstrapCI


def _make_ci(lower: float | None, upper: float | None, status: str = "computable") -> BootstrapCI:
    return BootstrapCI(
        point_estimate=lower,
        ci_lower=lower,
        ci_upper=upper,
        resamples=2000,
        seed=20260925,
        status=status,
    )


def test_step_1_invalidity_precedence() -> None:
    """Step 1: Any integrity error yields 'invalid' regardless of gate results."""
    disp, step, reason, _ = evaluate_gates_and_disposition(
        event_count=500,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0050,
        event_ci=_make_ci(0.0020, 0.0080),
        mean_uplift_2bps=0.0030,
        uplift_ci=_make_ci(0.0010, 0.0050),
        pct_positive_tickers=80.0,
        per_ticker_net_means={"AAPL": 0.0050},
        split_quality=None,
        integrity_error="lookahead_bias_detected",
    )
    assert disp == "invalid"
    assert step == "step_1_invalidity"
    assert "lookahead" in reason


def test_step_2_evidence_sufficiency_failure_inconclusive() -> None:
    """Step 2: Insufficient events (< 300) yields 'inconclusive' even if mean is negative."""
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=200,  # < 300
        represented_tickers=16,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=-0.0050,  # negative, but Step 2 takes precedence
        event_ci=_make_ci(-0.0080, -0.0020),
        mean_uplift_2bps=-0.0030,
        uplift_ci=_make_ci(-0.0050, -0.0010),
        pct_positive_tickers=30.0,
        per_ticker_net_means={"AAPL": -0.0050},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_2_evidence_sufficiency"


def test_step_2_concentration_failure_inconclusive() -> None:
    """Step 2: Single-ticker concentration > 15.0% yields 'inconclusive'."""
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=18.0,  # > 15.0%
        mean_primary_net_return_2bps=0.0050,
        event_ci=_make_ci(0.0020, 0.0080),
        mean_uplift_2bps=0.0030,
        uplift_ci=_make_ci(0.0010, 0.0050),
        pct_positive_tickers=80.0,
        per_ticker_net_means={"AAPL": 0.0050},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_2_evidence_sufficiency"


def test_step_3_directional_failure_rejected() -> None:
    """Step 3: Sufficient sample, but primary net return <= 0 yields 'rejected'."""
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=-0.0010,  # <= 0
        event_ci=_make_ci(-0.0030, 0.0010),
        mean_uplift_2bps=0.0010,
        uplift_ci=_make_ci(-0.0010, 0.0030),
        pct_positive_tickers=70.0,
        per_ticker_net_means={"AAPL": 0.0010},
        split_quality=None,
    )
    assert disp == "rejected"
    assert step == "step_3_directional_hypothesis_failure"


def test_step_3_breadth_failure_rejected() -> None:
    """Step 3: Ticker breadth < 60% positive yields 'rejected'."""
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        event_ci=_make_ci(0.0005, 0.0035),
        mean_uplift_2bps=0.0015,
        uplift_ci=_make_ci(0.0002, 0.0028),
        pct_positive_tickers=50.0,  # < 60.0%
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "rejected"
    assert step == "step_3_directional_hypothesis_failure"


def test_step_4_statistical_uncertainty_inconclusive() -> None:
    """Step 4: Positive means & passing breadth, but CI lower bound <= 0 yields 'inconclusive'."""
    disp, step, _, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,  # > 0
        event_ci=_make_ci(-0.0005, 0.0045),  # CI lower <= 0
        mean_uplift_2bps=0.0015,  # > 0
        uplift_ci=_make_ci(0.0002, 0.0028),  # CI lower > 0
        pct_positive_tickers=75.0,  # >= 60%
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_4_statistical_uncertainty"


def test_step_4_non_computable_bootstrap_inconclusive() -> None:
    """Step 4: Non-computable bootstrap CI yields 'inconclusive'."""
    disp, step, reason, _ = evaluate_gates_and_disposition(
        event_count=400,
        represented_tickers=20,
        max_ticker_concentration_pct=10.0,
        mean_primary_net_return_2bps=0.0020,
        event_ci=_make_ci(None, None, status="non_computable"),
        mean_uplift_2bps=0.0015,
        uplift_ci=_make_ci(0.0002, 0.0028),
        pct_positive_tickers=75.0,
        per_ticker_net_means={"AAPL": 0.0020},
        split_quality=None,
    )
    assert disp == "inconclusive"
    assert step == "step_4_statistical_uncertainty"
    assert "non_computable" in reason


def test_step_5_all_gates_pass_supported() -> None:
    """Step 5: All five locked gates pass simultaneously yields 'supported'."""
    disp, step, _, gates = evaluate_gates_and_disposition(
        event_count=450,
        represented_tickers=22,
        max_ticker_concentration_pct=9.5,
        mean_primary_net_return_2bps=0.0025,
        event_ci=_make_ci(0.0008, 0.0042),
        mean_uplift_2bps=0.0018,
        uplift_ci=_make_ci(0.0004, 0.0032),
        pct_positive_tickers=72.7,
        per_ticker_net_means={"AAPL": 0.0025},
        split_quality=None,
    )
    assert disp == "supported"
    assert step == "step_5_support"
    assert all(g.passed for g in gates.values())
