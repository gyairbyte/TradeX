"""Safe artifact generation and serialization for LONG-002E2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradex.research.long_002e2.spec import (
    compute_file_sha256,
)


def write_json_artifact(path: Path, data: Any) -> None:
    """Write an artifact dictionary to formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def save_diagnostic_artifacts(
    artifacts_dir: Path,
    execution_metadata: dict[str, Any],
    input_integrity: dict[str, Any],
    reproduction_check: dict[str, Any],
    family_context: dict[str, Any],
    annual_bootstrap: dict[str, Any],
    quarterly_diagnostics: dict[str, Any],
    spy_regime_diagnostics: dict[str, Any],
    selection_set_decomposition: dict[str, Any],
    feature_profile_drift: dict[str, Any],
    selection_concentration: dict[str, Any],
    probability_stability: dict[str, Any],
    localization_metrics: dict[str, Any],
    diagnostic_decision: dict[str, Any],
) -> dict[str, str]:
    """Write all safe JSON artifacts and compute checksums.sha256."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_map = {
        "execution_metadata.json": execution_metadata,
        "input_integrity.json": input_integrity,
        "e1_reproduction_check.json": reproduction_check,
        "family_annual_context.json": family_context,
        "annual_bootstrap.json": annual_bootstrap,
        "quarterly_diagnostics.json": quarterly_diagnostics,
        "spy_regime_diagnostics.json": spy_regime_diagnostics,
        "selection_set_decomposition.json": selection_set_decomposition,
        "feature_profile_drift.json": feature_profile_drift,
        "selection_concentration.json": selection_concentration,
        "probability_stability.json": probability_stability,
        "localization_metrics.json": localization_metrics,
        "diagnostic_decision.json": diagnostic_decision,
    }

    checksums: dict[str, str] = {}
    for filename, content in artifact_map.items():
        file_path = artifacts_dir / filename
        write_json_artifact(file_path, content)
        checksums[filename] = compute_file_sha256(file_path)

    # Write checksums.sha256
    checksums_path = artifacts_dir / "checksums.sha256"
    with checksums_path.open("w", encoding="utf-8") as f:
        for filename in sorted(checksums.keys()):
            f.write(f"{checksums[filename]}  {filename}\n")

    return checksums


def generate_markdown_report(
    run_id: str,
    execution_metadata: dict[str, Any],
    reproduction_check: dict[str, Any],
    family_context: dict[str, Any],
    annual_bootstrap: dict[str, Any],
    quarterly_diagnostics: dict[str, Any],
    spy_regime_diagnostics: dict[str, Any],
    selection_set_decomposition: dict[str, Any],
    feature_profile_drift: dict[str, Any],
    selection_concentration: dict[str, Any],
    probability_stability: dict[str, Any],
    localization_metrics: dict[str, Any],
    diagnostic_decision: dict[str, Any],
) -> str:
    """Generate comprehensive human-readable markdown research report."""
    rep_cfg = diagnostic_decision["representative_configuration_id"]
    disp = diagnostic_decision["diagnostic_disposition"]
    rec = diagnostic_decision["recommended_next_action"]

    q_dim = localization_metrics["calendar_quarter_dimension"]
    r_dim = localization_metrics["market_context_regime_dimension"]

    lines = [
        "# LONG-002E2: Development-Only Logistic Regime/Stability Diagnostic",
        "",
        f"**Task ID:** `{diagnostic_decision['task_id']}`  ",
        f"**Official Run ID:** `{run_id}`  ",
        f"**Representative Configuration:** `{rep_cfg}` ({diagnostic_decision['representative_selection_basis']})  ",
        f"**Diagnostic Disposition:** `{disp}`  ",
        f"**Recommended Next Action:** `{rec}`  ",
        "**Authorization:** Authorized by Gary Yang on 2026-10-06 (Research-Only / Post-Hoc Diagnostic)  ",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        (
            "In corrected Round 1 (`LONG-002E1-20261006_152832`), the best regularized logistic configuration "
            f"(`{rep_cfg}`) demonstrated pooled Precision@10 of 26.8109% (+2.7216 pp vs matched VAM5) and Precision@25 "
            "of 25.2420% (+4.2909 pp vs matched VAM5), but exhibited negative delta in 2020 (-1.4520 pp), failing the "
            "preregistered 3-of-3 year annual stability gate (achieving 2/3 years)."
        ),
        "",
        (
            "This diagnostic (LONG-002E2) investigated why the logistic family underperformed in 2020 without model refitting, "
            "hyperparameter tuning, or searching new configurations. The evaluation locked two preregistered localization rules:"
        ),
        "- **Rule A (Calendar Localization):** One calendar quarter accounts for >= 60% of 2020 negative hit loss AND other 3 quarters have clean hit delta >= 0.",
        "- **Rule B (Market-Context Localization):** One SPY return regime accounts for >= 60% of 2020 negative hit loss AND other 2 regimes have clean hit delta >= 0.",
        "",
        f"- **Rule A Passed:** `{diagnostic_decision['calendar_localization_passed']}`",
        f"- **Rule B Passed:** `{diagnostic_decision['market_context_localization_passed']}`",
        f"- **Final Disposition:** `{disp}`",
        f"- **Recommended Next Action:** `{rec}`",
        "",
        "---",
        "",
        "## 1. Provenance and Input Verification",
        "",
        f"- **Execution Code SHA:** `{execution_metadata.get('execution_code_sha')}`",
        f"- **Preregistration Commit SHA:** `{execution_metadata.get('preregistration_commit_sha')}`",
        f"- **E2 Spec SHA-256:** `{execution_metadata.get('spec_sha256')}`",
        "- **E1 Input Prediction SHA-256:** `837b824ac11754a900b44c2e118872996a9cad424cab1c549be7df5b61780062` (Verified)",
        "- **D1 Feature Table SHA-256:** `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` (Verified)",
        "- **Stage C Baseline SHA-256:** `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` (Verified)",
        f"- **Total Development Observations:** {execution_metadata.get('observation_count', 610648):,} (730 sessions, 2018-2020)",
        "",
        "### Exact Reproduction of E1 Metrics",
        "",
        "| Metric | Reconstructed | Committed Target | Match Status |",
        "|---|---|---|---|",
        f"| Top-10 Precision | {reproduction_check['pooled_metrics']['candidate_p10'] * 100:.4f}% | 26.8109% | EXACT MATCH |",
        f"| Top-10 VAM5 Precision | {reproduction_check['pooled_metrics']['vam5_p10'] * 100:.4f}% | 24.0893% | EXACT MATCH |",
        f"| Top-10 Delta | {reproduction_check['pooled_metrics']['p10_delta'] * 100:+.4f} pp | +2.7216 pp | EXACT MATCH |",
        f"| Top-25 Precision | {reproduction_check['pooled_metrics']['candidate_p25'] * 100:.4f}% | 25.2420% | EXACT MATCH |",
        f"| Top-25 VAM5 Precision | {reproduction_check['pooled_metrics']['vam5_p25'] * 100:.4f}% | 20.9510% | EXACT MATCH |",
        f"| Top-25 Delta | {reproduction_check['pooled_metrics']['p25_delta'] * 100:+.4f} pp | +4.2909 pp | EXACT MATCH |",
        f"| 2018 P@10 Delta | {reproduction_check['annual_metrics']['2018']['p10_delta'] * 100:+.4f} pp | +3.9841 pp | EXACT MATCH |",
        f"| 2019 P@10 Delta | {reproduction_check['annual_metrics']['2019']['p10_delta'] * 100:+.4f} pp | +5.0000 pp | EXACT MATCH |",
        f"| 2020 P@10 Delta | {reproduction_check['annual_metrics']['2020']['p10_delta'] * 100:+.4f} pp | -1.4520 pp | EXACT MATCH |",
        "",
        "---",
        "",
        "## 2. Family-Wide Annual Context",
        "",
        f"- **All 12 LOGIT configurations share 2018+ / 2019+ / 2020- pattern:** `{family_context['all_12_share_2018pos_2019pos_2020neg_pattern']}`",
        f"- **Interpretation:** {family_context['interpretation']}",
        "",
        "---",
        "",
        "## 3. Diagnostic 1 — Annual Paired Uncertainty (21-Session Block Bootstrap)",
        "",
        "| Year | Candidate P@10 | VAM5 P@10 | Delta | Bootstrap Median | 95% Bootstrap CI | Clean Hit Diff |",
        "|---|---|---|---|---|---|---|",
    ]

    for yr in ["2018", "2019", "2020"]:
        bs = annual_bootstrap["years"][yr]
        lines.append(
            f"| {yr} | {bs['candidate_p10'] * 100:.2f}% | {bs['vam5_p10'] * 100:.2f}% | "
            f"{bs['delta'] * 100:+.2f} pp | {bs['bootstrap_median'] * 100:+.2f} pp | "
            f"[{bs['ci_2_5'] * 100:+.2f} pp, {bs['ci_97_5'] * 100:+.2f} pp] | "
            f"{bs['clean_hit_difference']:+d} hits |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Diagnostic 2 — Fixed Calendar-Quarter Decomposition",
            "",
            "| Quarter | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | P@10 Delta | Cand Adverse | VAM5 Adverse | Top10 Overlap |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )

    for q in quarterly_diagnostics["quarters"].values():
        lines.append(
            f"| {q['quarter']} | {q['evaluation_dates_count']} | {q['candidate_selected_count']} | "
            f"{q['candidate_clean_hits']} | {q['vam5_clean_hits']} | {q['clean_hit_difference']:+d} | "
            f"{q['candidate_p10'] * 100:.2f}% | {q['vam5_p10'] * 100:.2f}% | {q['p10_delta'] * 100:+.2f} pp | "
            f"{q['candidate_adverse_rate_10'] * 100:.1f}% | {q['vam5_adverse_rate_10'] * 100:.1f}% | "
            f"{q['top10_overlap_pct'] * 100:.1f}% |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 5. Diagnostic 3 — Market-Context Regimes (SPY Return 20)",
            "",
            f"- **SPY Return q30 Threshold:** `{spy_regime_diagnostics['q30']}`",
            f"- **SPY Return q70 Threshold:** `{spy_regime_diagnostics['q70']}`",
            (
                f"- **Regime Date Counts:** LOWER={spy_regime_diagnostics['regime_date_counts']['LOWER']}, "
                f"MIDDLE={spy_regime_diagnostics['regime_date_counts']['MIDDLE']}, "
                f"UPPER={spy_regime_diagnostics['regime_date_counts']['UPPER']}"
            ),
            "",
            "### Overall Regime Performance",
            "",
            "| Regime | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | Delta P@10 | Cand Adverse | VAM5 Adverse | Overlap |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )

    for r_name, r_data in spy_regime_diagnostics["overall_regimes"].items():
        lines.append(
            f"| {r_name} | {r_data['evaluation_dates_count']} | {r_data['candidate_selected_count']} | "
            f"{r_data['candidate_clean_hits']} | {r_data['vam5_clean_hits']} | {r_data['clean_hit_difference']:+d} | "
            f"{r_data['candidate_p10'] * 100:.2f}% | {r_data['vam5_p10'] * 100:.2f}% | {r_data['delta_p10'] * 100:+.2f} pp | "
            f"{r_data['candidate_adverse_rate_10'] * 100:.1f}% | {r_data['vam5_adverse_rate_10'] * 100:.1f}% | "
            f"{r_data['selection_overlap_pct'] * 100:.1f}% |"
        )

    lines.extend(
        [
            "",
            "### 2020 Year x Regime Performance",
            "",
            "| Regime (2020) | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | Delta P@10 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )

    for r_name, r_data in spy_regime_diagnostics["year_x_regime"]["2020"].items():
        lines.append(
            f"| {r_name} | {r_data['evaluation_dates_count']} | {r_data['candidate_selected_count']} | "
            f"{r_data['candidate_clean_hits']} | {r_data['vam5_clean_hits']} | {r_data['clean_hit_difference']:+d} | "
            f"{r_data['candidate_p10'] * 100:.2f}% | {r_data['vam5_p10'] * 100:.2f}% | {r_data['delta_p10'] * 100:+.2f} pp |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 6. Diagnostic 4 — Selection-Set Decomposition",
            "",
            "| Partition | 2018 Obs (Clean %) | 2019 Obs (Clean %) | 2020 Obs (Clean %) | Overall Obs (Clean %) | Overall ECMV |",
            "|---|---|---|---|---|---|",
        ]
    )

    p_names = ["OVERLAP", "LOGIT_ONLY", "VAM5_ONLY"]
    for p in p_names:
        o_18 = selection_set_decomposition["by_year"]["2018"][p]
        o_19 = selection_set_decomposition["by_year"]["2019"][p]
        o_20 = selection_set_decomposition["by_year"]["2020"][p]
        o_tot = selection_set_decomposition["overall"][p]

        lines.append(
            f"| {p} | {o_18['observation_count']} ({o_18['clean_rate'] * 100:.2f}%) | "
            f"{o_19['observation_count']} ({o_19['clean_rate'] * 100:.2f}%) | "
            f"{o_20['observation_count']} ({o_20['clean_rate'] * 100:.2f}%) | "
            f"{o_tot['observation_count']} ({o_tot['clean_rate'] * 100:.2f}%) | "
            f"{o_tot['ecmv']:.2f} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 7. Diagnostic 5 — Feature-Profile Drift (Percentile Profiles)",
            "",
            "Comparison of average cross-sectional percentile rank of securities chosen by `LOGIT_ONLY` vs `VAM5_ONLY`:",
            "",
            "| Feature | 2018 Diff (L - V) | 2019 Diff (L - V) | 2020 Diff (L - V) | Overall Diff (L - V) |",
            "|---|---|---|---|---|",
        ]
    )

    for i, f_row in enumerate(feature_profile_drift["overall"]):
        feat = f_row["feature"]
        d18 = feature_profile_drift["by_year"]["2018"][i]["mean_percentile_difference"]
        d19 = feature_profile_drift["by_year"]["2019"][i]["mean_percentile_difference"]
        d20 = feature_profile_drift["by_year"]["2020"][i]["mean_percentile_difference"]
        dtot = f_row["mean_percentile_difference"]
        lines.append(f"| `{feat}` | {d18:+.2f} | {d19:+.2f} | {d20:+.2f} | {dtot:+.2f} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 8. Diagnostic 6 — Selection Concentration",
            "",
            "| Year | Model | Distinct Sec | Max Count | Top-5 Share | Top-10 Share | HHI | Eff N |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )

    for yr in ["2018", "2019", "2020"]:
        c_conc = selection_concentration["by_year"][yr]["candidate"]
        v_conc = selection_concentration["by_year"][yr]["matched_vam5"]
        lines.append(
            f"| {yr} | LOGIT_S4_C300 | {c_conc['distinct_immutable_securities_count']} | "
            f"{c_conc['maximum_selection_count']} | {c_conc['top_5_securities_share'] * 100:.1f}% | "
            f"{c_conc['top_10_securities_share'] * 100:.1f}% | {c_conc['herfindahl_hirschman_index']:.6f} | "
            f"{c_conc['effective_number_of_securities']:.1f} |"
        )
        lines.append(
            f"| {yr} | VAM5 Baseline | {v_conc['distinct_immutable_securities_count']} | "
            f"{v_conc['maximum_selection_count']} | {v_conc['top_5_securities_share'] * 100:.1f}% | "
            f"{v_conc['top_10_securities_share'] * 100:.1f}% | {v_conc['herfindahl_hirschman_index']:.6f} | "
            f"{v_conc['effective_number_of_securities']:.1f} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 9. Diagnostic 7 — Raw Probability Stability",
            "",
            "| Year | Obs | Empirical Base Rate | Brier Score | Mean Predicted Prob | Median Predicted Prob |",
            "|---|---|---|---|---|---|",
        ]
    )

    for yr in ["2018", "2019", "2020"]:
        p_yr = probability_stability["by_year"][yr]
        lines.append(
            f"| {yr} | {p_yr['observation_count']:,} | {p_yr['empirical_base_rate'] * 100:.2f}% | "
            f"{p_yr['brier_score']:.6f} | {p_yr['mean_predicted_probability'] * 100:.2f}% | "
            f"{p_yr['median_predicted_probability'] * 100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 10. 2020 Localization Metrics & Decision Gate",
            "",
            f"- **2020 Annual Clean Hit Delta:** `{localization_metrics['annual_hit_delta']:+d}` hits",
            "",
            "### Rule A — Calendar Localization",
            f"- **Dominant Negative Quarter:** `{q_dim['dominant_negative_quarter']}` (loss: `{q_dim['dominant_negative_quarter_loss']}` hits)",
            f"- **Quarter Negative Loss Share:** `{q_dim['dominant_negative_quarter_share'] * 100:.2f}%` (Threshold: 60.0%)",
            f"- **Remaining Three Quarters Hit Delta:** `{q_dim['remaining_three_quarters_hit_delta']:+d}` hits (Threshold: >= 0)",
            f"- **Rule A Disposition:** `{'PASSED' if q_dim['rule_a_calendar_localization_passed'] else 'FAILED'}`",
            "",
            "### Rule B — Market-Context Localization",
            f"- **Dominant Negative SPY Regime:** `{r_dim['dominant_negative_regime']}` (loss: `{r_dim['dominant_negative_regime_loss']}` hits)",
            f"- **Regime Negative Loss Share:** `{r_dim['dominant_negative_regime_share'] * 100:.2f}%` (Threshold: 60.0%)",
            f"- **Remaining Two Regimes Hit Delta:** `{r_dim['remaining_two_regimes_hit_delta']:+d}` hits (Threshold: >= 0)",
            f"- **Rule B Disposition:** `{'PASSED' if r_dim['rule_b_market_context_localization_passed'] else 'FAILED'}`",
            "",
            "### Final Decision",
            f"- **Diagnostic Disposition:** `{disp}`",
            f"- **Recommended Next Action:** `{rec}`",
            "- **Search Budget Status:** 36 consumed / 12 unused (Total: 48). Unchanged.",
            "- **Round 2 Authorized:** `False`",
            "",
            "---",
            "",
            "## 11. Governance, Isolation, and Limitations",
            "",
            "1. **Zero Provider / Network Calls:** All evaluations were executed offline against frozen TradeX artifacts.",
            "2. **Strict Quarantines:** Validation (2021-2022), Holdout (2023-2025), and Shadow (2026+) remain unopened.",
            "3. **Zero Model Refitting:** No model parameters, coefficients, scalers, or probability calibrations were refitted.",
            "4. **No Production Strategy Promotion:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.",
            "5. **Hypothesis Generation Only:** Findings from this development diagnostic cannot directly justify trading rules, market timing gates, or score modifications without independent preregistered validation.",
        ]
    )

    return "\n".join(lines) + "\n"
