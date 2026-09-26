"""Validation gates evaluation and locked 5-step disposition precedence."""
from __future__ import annotations

from .models import BootstrapCI, GateEvaluationResult, SplitDataQualitySummary

MIN_EVENTS = 300
MIN_TICKERS = 15
MAX_CONCENTRATION_PCT = 15.0
MIN_BREADTH_PCT = 60.0
MAX_SPLIT_EXCLUDED_SESSIONS_PCT = 5.0


class GateError(Exception):
    """Raised when gate evaluation inputs are malformed."""


def evaluate_gates_and_disposition(
    *,
    event_count: int,
    represented_tickers: int,
    max_ticker_concentration_pct: float,
    mean_primary_net_return_2bps: float | None,
    event_ci: BootstrapCI,
    mean_uplift_2bps: float | None,
    uplift_ci: BootstrapCI,
    pct_positive_tickers: float,
    per_ticker_net_means: dict[str, float],
    split_quality: SplitDataQualitySummary | None,
    integrity_error: str | None = None,
) -> tuple[str, str, str, dict[str, GateEvaluationResult]]:
    """Evaluate the 5 locked gates and resolve disposition via the 5-step precedence hierarchy.

    Returns:
        (disposition, disposition_step, disposition_reason, gates_dict)
    """
    gates: dict[str, GateEvaluationResult] = {}

    # Gate 1: Sample Gate
    sample_passed = (event_count >= MIN_EVENTS) and (represented_tickers >= MIN_TICKERS)
    gates["sample_gate"] = GateEvaluationResult(
        gate_name="sample_gate",
        passed=sample_passed,
        detail={
            "event_count": event_count,
            "min_events": MIN_EVENTS,
            "represented_tickers": represented_tickers,
            "min_tickers": MIN_TICKERS,
        },
    )

    # Gate 2: Concentration Gate
    conc_passed = max_ticker_concentration_pct <= MAX_CONCENTRATION_PCT
    gates["concentration_gate"] = GateEvaluationResult(
        gate_name="concentration_gate",
        passed=conc_passed,
        detail={
            "max_single_ticker_pct": max_ticker_concentration_pct,
            "max_allowed_pct": MAX_CONCENTRATION_PCT,
        },
    )

    # Gate 3: Primary Net-Effect Gate (mean > 0 and 95% CI lower > 0)
    event_mean_gt_zero = (
        mean_primary_net_return_2bps is not None and mean_primary_net_return_2bps > 0
    )
    event_ci_gt_zero = (
        event_ci.status == "computable"
        and event_ci.ci_lower is not None
        and event_ci.ci_lower > 0
    )
    primary_net_passed = event_mean_gt_zero and event_ci_gt_zero
    gates["primary_net_effect_gate"] = GateEvaluationResult(
        gate_name="primary_net_effect_gate",
        passed=primary_net_passed,
        detail={
            "mean_net_return_2bps": mean_primary_net_return_2bps,
            "ci_lower": event_ci.ci_lower,
            "ci_status": event_ci.status,
            "cost_basis_bps_per_side": 2.0,
        },
    )

    # Gate 4: Baseline Uplift Gate (mean > 0 and 95% CI lower > 0)
    uplift_mean_gt_zero = mean_uplift_2bps is not None and mean_uplift_2bps > 0
    uplift_ci_gt_zero = (
        uplift_ci.status == "computable"
        and uplift_ci.ci_lower is not None
        and uplift_ci.ci_lower > 0
    )
    baseline_uplift_passed = uplift_mean_gt_zero and uplift_ci_gt_zero
    gates["baseline_uplift_gate"] = GateEvaluationResult(
        gate_name="baseline_uplift_gate",
        passed=baseline_uplift_passed,
        detail={
            "mean_uplift_2bps": mean_uplift_2bps,
            "ci_lower": uplift_ci.ci_lower,
            "ci_status": uplift_ci.status,
        },
    )

    # Gate 5: Ticker Breadth Gate (>= 60.0% positive)
    breadth_passed = pct_positive_tickers >= MIN_BREADTH_PCT
    gates["breadth_gate"] = GateEvaluationResult(
        gate_name="breadth_gate",
        passed=breadth_passed,
        detail={
            "pct_positive_tickers": pct_positive_tickers,
            "min_required_pct": MIN_BREADTH_PCT,
            "per_ticker_net_means": per_ticker_net_means,
        },
    )

    # Data quality split check
    dq_excluded_pct = split_quality.excluded_rate_pct if split_quality else 0.0
    dq_gate_passed = dq_excluded_pct <= MAX_SPLIT_EXCLUDED_SESSIONS_PCT

    # --- Locked 5-Step Precedence Resolution ---

    # Step 1: Invalidity (methodological, integrity, lookahead, or execution defect)
    if integrity_error:
        return (
            "invalid",
            "step_1_invalidity",
            f"Integrity defect: {integrity_error}",
            gates,
        )

    # Step 2: Evidence Sufficiency (sample, tickers, concentration, data-quality exclusions)
    if not sample_passed or not conc_passed or not dq_gate_passed:
        reasons: list[str] = []
        if event_count < MIN_EVENTS:
            reasons.append(f"events_{event_count}_below_{MIN_EVENTS}")
        if represented_tickers < MIN_TICKERS:
            reasons.append(f"tickers_{represented_tickers}_below_{MIN_TICKERS}")
        if max_ticker_concentration_pct > MAX_CONCENTRATION_PCT:
            reasons.append(
                f"concentration_{max_ticker_concentration_pct:.2f}%_above_{MAX_CONCENTRATION_PCT}%"
            )
        if not dq_gate_passed:
            reasons.append(
                f"split_excluded_sessions_{dq_excluded_pct:.2f}%_above_{MAX_SPLIT_EXCLUDED_SESSIONS_PCT}%"
            )

        return (
            "inconclusive",
            "step_2_evidence_sufficiency",
            f"Evidence sufficiency gate failure: {'; '.join(reasons)}",
            gates,
        )

    # Step 3: Directional Hypothesis Failure (mean net <= 0, mean uplift <= 0, or breadth < 60%)
    mean_net_val = mean_primary_net_return_2bps if mean_primary_net_return_2bps is not None else 0.0
    mean_uplift_val = mean_uplift_2bps if mean_uplift_2bps is not None else 0.0

    directional_failures: list[str] = []
    if mean_net_val <= 0:
        directional_failures.append(f"primary_mean_net_{mean_net_val:.6f}_le_0")
    if mean_uplift_val <= 0:
        directional_failures.append(f"mean_uplift_{mean_uplift_val:.6f}_le_0")
    if not breadth_passed:
        directional_failures.append(
            f"ticker_breadth_{pct_positive_tickers:.1f}%_below_{MIN_BREADTH_PCT}%"
        )

    if directional_failures:
        return (
            "rejected",
            "step_3_directional_hypothesis_failure",
            f"Directional hypothesis failure: {'; '.join(directional_failures)}",
            gates,
        )

    # Step 4: Statistical Uncertainty (means positive and breadth passed, but CI lower <= 0 or non-computable)
    ci_failures: list[str] = []
    if event_ci.status != "computable" or event_ci.ci_lower is None or event_ci.ci_lower <= 0:
        if event_ci.status != "computable":
            ci_failures.append(f"primary_net_ci_non_computable_{event_ci.error_reason}")
        else:
            ci_failures.append(f"primary_net_ci_lower_{event_ci.ci_lower:.6f}_le_0")

    if uplift_ci.status != "computable" or uplift_ci.ci_lower is None or uplift_ci.ci_lower <= 0:
        if uplift_ci.status != "computable":
            ci_failures.append(f"uplift_ci_non_computable_{uplift_ci.error_reason}")
        else:
            ci_failures.append(f"uplift_ci_lower_{uplift_ci.ci_lower:.6f}_le_0")

    if ci_failures:
        return (
            "inconclusive",
            "step_4_statistical_uncertainty",
            f"Statistical uncertainty: {'; '.join(ci_failures)}",
            gates,
        )

    # Step 5: Support (all gates pass simultaneously)
    return (
        "supported",
        "step_5_support",
        "All five locked validation gates passed simultaneously.",
        gates,
    )
