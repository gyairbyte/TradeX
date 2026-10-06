"""2020 localization metrics and preregistered decision rules for LONG-002E2."""

from __future__ import annotations

from typing import Any

from tradex.research.long_002e2.spec import (
    ALLOWED_DISPOSITIONS,
    ALLOWED_RECOMMENDED_ACTIONS,
    LOCALIZATION_THRESHOLD,
    REPRESENTATIVE_CONFIGURATION_ID,
    REPRESENTATIVE_SELECTION_BASIS,
    TASK_ID,
)


def compute_localization_metrics(
    quarter_results: dict[str, dict[str, Any]],
    regime_results_by_year: dict[str, dict[str, dict[str, Any]]],
    annual_metrics: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute 2020 hit loss localization metrics across calendar quarters and SPY regimes.

    Returns:
        (localization_metrics, decision_result)
    """
    # 2020 annual hit delta
    annual_hit_delta_2020 = annual_metrics["2020"]["clean_hit_difference"]

    # --- 1. Calendar Quarters (2020) ---
    q_2020 = ["2020Q1", "2020Q2", "2020Q3", "2020Q4"]
    quarter_deltas = {q: quarter_results[q]["clean_hit_difference"] for q in q_2020}
    sum_q_deltas = sum(quarter_deltas.values())

    if sum_q_deltas != annual_hit_delta_2020:
        raise ValueError(
            f"2020 QUARTER HIT DELTAS SUM MISMATCH: {sum_q_deltas} != annual {annual_hit_delta_2020}"
        )

    quarter_neg_loss = {q: abs(delta) if delta < 0 else 0 for q, delta in quarter_deltas.items()}
    total_q_neg_loss = sum(quarter_neg_loss.values())

    if total_q_neg_loss > 0:
        dominant_q = max(quarter_neg_loss.keys(), key=lambda q: quarter_neg_loss[q])
        dominant_q_loss = quarter_neg_loss[dominant_q]
        dominant_q_share = dominant_q_loss / total_q_neg_loss
    else:
        dominant_q = "none"
        dominant_q_loss = 0
        dominant_q_share = 0.0

    dominant_q_hit_delta = quarter_deltas.get(dominant_q, 0)
    remaining_q_hit_delta = annual_hit_delta_2020 - dominant_q_hit_delta

    rule_a_passed = (dominant_q_share >= LOCALIZATION_THRESHOLD) and (remaining_q_hit_delta >= 0)

    # --- 2. Market-Context SPY Regimes (2020) ---
    regimes_2020 = regime_results_by_year["2020"]
    regime_deltas = {
        r: regimes_2020[r]["clean_hit_difference"] for r in ["LOWER", "MIDDLE", "UPPER"]
    }
    sum_r_deltas = sum(regime_deltas.values())

    if sum_r_deltas != annual_hit_delta_2020:
        raise ValueError(
            f"2020 REGIME HIT DELTAS SUM MISMATCH: {sum_r_deltas} != annual {annual_hit_delta_2020}"
        )

    regime_neg_loss = {r: abs(delta) if delta < 0 else 0 for r, delta in regime_deltas.items()}
    total_r_neg_loss = sum(regime_neg_loss.values())

    if total_r_neg_loss > 0:
        dominant_r = max(regime_neg_loss.keys(), key=lambda r: regime_neg_loss[r])
        dominant_r_loss = regime_neg_loss[dominant_r]
        dominant_r_share = dominant_r_loss / total_r_neg_loss
    else:
        dominant_r = "none"
        dominant_r_loss = 0
        dominant_r_share = 0.0

    dominant_r_hit_delta = regime_deltas.get(dominant_r, 0)
    remaining_r_hit_delta = annual_hit_delta_2020 - dominant_r_hit_delta

    rule_b_passed = (dominant_r_share >= LOCALIZATION_THRESHOLD) and (remaining_r_hit_delta >= 0)

    localization_metrics = {
        "year": "2020",
        "annual_hit_delta": annual_hit_delta_2020,
        "calendar_quarter_dimension": {
            "quarter_hit_deltas": quarter_deltas,
            "quarter_negative_losses": quarter_neg_loss,
            "total_negative_hit_loss": total_q_neg_loss,
            "dominant_negative_quarter": dominant_q,
            "dominant_negative_quarter_loss": dominant_q_loss,
            "dominant_negative_quarter_share": round(dominant_q_share, 4),
            "dominant_quarter_hit_delta": dominant_q_hit_delta,
            "remaining_three_quarters_hit_delta": remaining_q_hit_delta,
            "localization_threshold": LOCALIZATION_THRESHOLD,
            "rule_a_calendar_localization_passed": rule_a_passed,
        },
        "market_context_regime_dimension": {
            "regime_hit_deltas": regime_deltas,
            "regime_negative_losses": regime_neg_loss,
            "total_negative_hit_loss": total_r_neg_loss,
            "dominant_negative_regime": dominant_r,
            "dominant_negative_regime_loss": dominant_r_loss,
            "dominant_negative_regime_share": round(dominant_r_share, 4),
            "dominant_regime_hit_delta": dominant_r_hit_delta,
            "remaining_two_regimes_hit_delta": remaining_r_hit_delta,
            "localization_threshold": LOCALIZATION_THRESHOLD,
            "rule_b_market_context_localization_passed": rule_b_passed,
        },
    }

    # Decision disposition
    if rule_a_passed or rule_b_passed:
        disposition = "bounded_followup_hypothesis_warranted"
        rec_action = "preregister_one_bounded_followup_hypothesis"
    else:
        disposition = "no_bounded_regime_hypothesis_supported"
        rec_action = "close_initial_long_002e_search_preserve_unused_budget"

    assert disposition in ALLOWED_DISPOSITIONS
    assert rec_action in ALLOWED_RECOMMENDED_ACTIONS

    decision_result = {
        "task_id": TASK_ID,
        "representative_configuration_id": REPRESENTATIVE_CONFIGURATION_ID,
        "representative_selection_basis": REPRESENTATIVE_SELECTION_BASIS,
        "material_configurations_consumed_before": 36,
        "material_configurations_consumed_after": 36,
        "remaining_long_002e_budget": 12,
        "round2_authorized": False,
        "validation_opened": False,
        "holdout_opened": False,
        "shadow_opened": False,
        "production_change_authorized": False,
        "calendar_localization_passed": rule_a_passed,
        "market_context_localization_passed": rule_b_passed,
        "diagnostic_disposition": disposition,
        "recommended_next_action": rec_action,
        "limitations": [
            "Development-only post-hoc diagnostic covering 2018-2020; does not constitute out-of-sample evidence.",
            "Descriptive market-context regimes are derived from retrospective development SPY return distributions.",
            "Quarterly and regime decompositions are for hypothesis generation only and do not validate a trading rule or regime gate.",
            "Validation (2021-2022), holdout (2023-2025), and shadow (2026+) remain strictly quarantined.",
            "No model was refitted or modified; remaining 12 search budget slots remain unspent.",
        ],
    }

    return localization_metrics, decision_result
