"""Validation gates evaluation and locked 5-step disposition precedence."""
from __future__ import annotations

from .models import BootstrapCI, GateEvaluationResult, SplitDataQualitySummary

MIN_EVENTS = 75
MIN_REPRESENTED_ETFS = 10
MIN_EVENT_SESSION_COUNT = 20
MAX_CONCENTRATION_PCT = 15.0
MAX_SPLIT_EXCLUDED_RATE_PCT = 5.0
MIN_BREADTH_PCT = 60.0


class GateError(Exception):
    """Raised when gate evaluation inputs are malformed."""


def evaluate_gates_and_disposition(
    *,
    event_count: int,
    represented_etfs: int,
    event_session_count: int,
    max_etf_concentration_pct: float,
    mean_primary_net_return_2bps: float | None,
    primary_ci: BootstrapCI,
    mean_uplift_2bps: float | None,
    uplift_ci: BootstrapCI,
    pct_positive_etfs: float,
    per_etf_net_means: dict[str, float],
    split_quality: SplitDataQualitySummary | None,
    integrity_error: str | None = None,
) -> tuple[str, str, str, dict[str, GateEvaluationResult]]:
    """Evaluate the 6 locked validation gates and resolve disposition via the 5-step precedence hierarchy.

    Returns:
        (disposition, disposition_step, disposition_reason, gates_dict)
    """
    gates: dict[str, GateEvaluationResult] = {}

    # Gate 1: Sample Gate (>= 75 events, >= 10 ETFs, >= 20 event session dates)
    sample_passed = (
        (event_count >= MIN_EVENTS)
        and (represented_etfs >= MIN_REPRESENTED_ETFS)
        and (event_session_count >= MIN_EVENT_SESSION_COUNT)
    )
    gates["sample_gate"] = GateEvaluationResult(
        gate_name="sample_gate",
        passed=sample_passed,
        detail={
            "event_count": event_count,
            "min_events": MIN_EVENTS,
            "represented_etfs": represented_etfs,
            "min_represented_etfs": MIN_REPRESENTED_ETFS,
            "event_session_count": event_session_count,
            "min_event_session_count": MIN_EVENT_SESSION_COUNT,
        },
    )

    # Gate 2: Concentration Gate (<= 15.0%)
    conc_passed = max_etf_concentration_pct <= MAX_CONCENTRATION_PCT
    gates["concentration_gate"] = GateEvaluationResult(
        gate_name="concentration_gate",
        passed=conc_passed,
        detail={
            "max_single_etf_pct": max_etf_concentration_pct,
            "max_allowed_pct": MAX_CONCENTRATION_PCT,
        },
    )

    # Gate 3: Data Quality Gate (<= 5.0% excluded ticker-sessions)
    if split_quality is not None:
        dq_excluded_pct = split_quality.excluded_rate_pct
        dq_passed = dq_excluded_pct <= MAX_SPLIT_EXCLUDED_RATE_PCT
    else:
        dq_excluded_pct = 0.0
        dq_passed = True

    gates["data_quality_gate"] = GateEvaluationResult(
        gate_name="data_quality_gate",
        passed=dq_passed,
        detail={
            "excluded_rate_pct": dq_excluded_pct,
            "max_allowed_pct": MAX_SPLIT_EXCLUDED_RATE_PCT,
            "excluded_ticker_sessions": split_quality.excluded_ticker_sessions if split_quality else 0,
            "total_ticker_sessions": split_quality.total_ticker_sessions if split_quality else 0,
        },
    )

    # Gate 4: Primary Net Effect Gate (mean > 0 and 95% CI lower > 0)
    event_mean_gt_zero = (
        mean_primary_net_return_2bps is not None and mean_primary_net_return_2bps > 0.0
    )
    event_ci_gt_zero = (
        primary_ci.status == "computable"
        and primary_ci.ci_lower is not None
        and primary_ci.ci_lower > 0.0
    )
    primary_net_passed = event_mean_gt_zero and event_ci_gt_zero
    gates["primary_net_effect_gate"] = GateEvaluationResult(
        gate_name="primary_net_effect_gate",
        passed=primary_net_passed,
        detail={
            "mean_net_return_2bps": mean_primary_net_return_2bps,
            "ci_lower": primary_ci.ci_lower,
            "ci_status": primary_ci.status,
            "cost_basis_bps_per_side": 2.0,
        },
    )

    # Gate 5: Baseline Uplift Gate (mean > 0 and 95% CI lower > 0)
    uplift_mean_gt_zero = mean_uplift_2bps is not None and mean_uplift_2bps > 0.0
    uplift_ci_gt_zero = (
        uplift_ci.status == "computable"
        and uplift_ci.ci_lower is not None
        and uplift_ci.ci_lower > 0.0
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

    # Gate 6: Breadth Gate (>= 60.0% of represented ETFs with mean primary net > 0)
    breadth_passed = pct_positive_etfs >= MIN_BREADTH_PCT
    gates["breadth_gate"] = GateEvaluationResult(
        gate_name="breadth_gate",
        passed=breadth_passed,
        detail={
            "pct_positive_etfs": pct_positive_etfs,
            "min_required_pct": MIN_BREADTH_PCT,
            "per_etf_net_means": per_etf_net_means,
        },
    )

    # Exact 5-Step Disposition Precedence
    # Step 1: Invalidity
    if integrity_error:
        return (
            "invalid",
            "step_1_invalidity",
            f"Integrity defect: {integrity_error}",
            gates,
        )

    # Step 2: Evidence Sufficiency
    if not sample_passed or not conc_passed or not dq_passed:
        reasons: list[str] = []
        if not sample_passed:
            reasons.append(
                f"sample_gate_failed (events={event_count}, etfs={represented_etfs}, dates={event_session_count})"
            )
        if not conc_passed:
            reasons.append(f"concentration_gate_failed ({max_etf_concentration_pct:.2f}%)")
        if not dq_passed:
            reasons.append(f"data_quality_gate_failed ({dq_excluded_pct:.2f}%)")
        return (
            "inconclusive",
            "step_2_evidence_sufficiency",
            "; ".join(reasons),
            gates,
        )

    # Step 3: Directional Hypothesis Failure
    directional_failure = False
    dir_reasons: list[str] = []
    if mean_primary_net_return_2bps is None or mean_primary_net_return_2bps <= 0.0:
        directional_failure = True
        dir_reasons.append(f"mean_net_return_le_zero ({mean_primary_net_return_2bps})")
    if mean_uplift_2bps is None or mean_uplift_2bps <= 0.0:
        directional_failure = True
        dir_reasons.append(f"mean_uplift_le_zero ({mean_uplift_2bps})")
    if not breadth_passed:
        directional_failure = True
        dir_reasons.append(f"breadth_gate_failed ({pct_positive_etfs:.2f}% < {MIN_BREADTH_PCT}%)")

    if directional_failure:
        return (
            "rejected",
            "step_3_directional_hypothesis_failure",
            "; ".join(dir_reasons),
            gates,
        )

    # Step 4: Statistical Uncertainty
    uncertainty_reasons: list[str] = []
    if not event_ci_gt_zero:
        if primary_ci.status != "computable":
            uncertainty_reasons.append(f"primary_ci_non_computable ({primary_ci.error_reason})")
        else:
            uncertainty_reasons.append(f"primary_ci_lower_le_zero ({primary_ci.ci_lower})")
    if not uplift_ci_gt_zero:
        if uplift_ci.status != "computable":
            uncertainty_reasons.append(f"uplift_ci_non_computable ({uplift_ci.error_reason})")
        else:
            uncertainty_reasons.append(f"uplift_ci_lower_le_zero ({uplift_ci.ci_lower})")

    if uncertainty_reasons:
        return (
            "inconclusive",
            "step_4_statistical_uncertainty",
            "; ".join(uncertainty_reasons),
            gates,
        )

    # Step 5: Support (All 6 gates pass)
    return (
        "supported",
        "step_5_support",
        "All six locked validation gates passed simultaneously.",
        gates,
    )
