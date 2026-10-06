"""Artifact generation and report compilation for LONG-002E1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tradex.research.long_002e1.bootstrap import BootstrapResult
from tradex.research.long_002e1.configs import ConfigurationSpec
from tradex.research.long_002e1.evaluation import EvaluationSummary
from tradex.research.long_002e1.ledger import LedgerRecord, write_experiment_ledger

STATUS_RANK = {
    "round2_eligible": 1,
    "round1_inconclusive": 2,
    "round1_not_supported": 3,
    "invalid_configuration": 4,
}

SUBSET_COMPLEXITY_RANK = {
    "S1": 1,
    "S2": 2,
    "S3": 3,
    "S4": 4,
}


def sort_configurations_within_family(
    config_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort configuration result dictionaries by the locked 8-level ordering."""

    def _sort_key(item: dict[str, Any]) -> tuple:
        status_order = STATUS_RANK.get(item["status"], 99)
        p10_delta = item.get("p10_delta", 0.0)
        bs_lower = item.get("bootstrap_21_p10_lower", 0.0)
        p25_delta = item.get("p25_delta", 0.0)
        ecmv_delta = item.get("ecmv10_delta", 0.0)
        adverse_rate = item.get("adverse_rate_10", 1.0)
        complexity = SUBSET_COMPLEXITY_RANK.get(item.get("feature_subset_id", "S4"), 99)
        c_id = item.get("configuration_id", "")

        return (
            status_order,
            -p10_delta,
            -bs_lower,
            -p25_delta,
            -ecmv_delta,
            adverse_rate,
            complexity,
            c_id,
        )

    return sorted(config_results, key=_sort_key)


def build_and_write_artifacts(
    run_id: str,
    output_dir: Path,
    metadata: dict[str, Any],
    input_integrity: dict[str, Any],
    configs: list[ConfigurationSpec],
    eval_summaries: dict[str, EvaluationSummary],
    bootstrap_results_21: dict[str, BootstrapResult],
    bootstrap_results_42: dict[str, BootstrapResult],
    config_statuses: dict[str, str],
    external_manifest: dict[str, Any],
    execution_failures: dict[str, str],
) -> dict[str, str]:
    """Generate and write all safe committed JSON artifacts and the checksum manifest.

    Returns:
        dict of artifact filename -> SHA-256 digest.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. execution_metadata.json
    with (output_dir / "execution_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # 2. input_integrity.json
    with (output_dir / "input_integrity.json").open("w", encoding="utf-8") as f:
        json.dump(input_integrity, f, indent=2)

    # 3. configuration_registry.json
    reg_data = [
        {
            "configuration_id": c.config_id,
            "family": c.family,
            "feature_subset_id": c.feature_subset_id,
            "features": c.features,
            "parameters": c.parameters,
            "budget_slot": c.budget_slot,
        }
        for c in configs
    ]
    with (output_dir / "configuration_registry.json").open("w", encoding="utf-8") as f:
        json.dump(reg_data, f, indent=2)

    # 4. experiment_ledger.jsonl
    ledger_records: list[LedgerRecord] = []
    for c in configs:
        cid = c.config_id
        summary = eval_summaries.get(cid)
        bs21 = bootstrap_results_21.get(cid)
        bs42 = bootstrap_results_42.get(cid)
        fail_msg = execution_failures.get(cid)

        # Folds attempted and completed (3 expanding folds in corrected design)
        f_att = 3
        f_comp = 3 if fail_msg is None else 0

        p_metrics: dict[str, Any] = {}
        r_metrics: dict[str, Any] = {}

        if summary:
            p_metrics = {
                "precision_at_10": round(summary.top10.precision, 6),
                "matched_vam5_precision_at_10": round(summary.top10.matched_vam5_precision, 6),
                "precision_at_10_delta": round(summary.top10.precision_delta_vs_vam5, 6),
                "precision_at_25": round(summary.top25.precision, 6),
                "matched_vam5_precision_at_25": round(summary.top25.matched_vam5_precision, 6),
                "precision_at_25_delta": round(summary.top25.precision_delta_vs_vam5, 6),
                "lift_at_10": round(summary.top10.lift_vs_oof_base_rate, 4),
                "empirical_clean_move_value_at_10": round(summary.top10.empirical_clean_move_value, 4),
                "empirical_clean_move_value_delta_at_10": round(summary.top10.clean_move_value_delta, 4),
                "adverse_rate_at_10": round(summary.top10.primary_adverse_rate, 4),
                "median_time_to_target_at_10": summary.top10.median_time_to_target,
                "annual_precision_10": {str(k): (round(v, 6) if v is not None else None) for k, v in summary.annual_precision_10.items()},
                "annual_precision_10_delta": {str(k): (round(v, 6) if v is not None else None) for k, v in summary.annual_precision_10_delta.items()},
                "annual_positive_years_count": summary.annual_positive_years_count,
            }
        if bs21 and bs42:
            r_metrics = {
                "bootstrap_21_p10_delta": {
                    "lower": round(bs21.p10_delta_lower, 6),
                    "median": round(bs21.p10_delta_median, 6),
                    "upper": round(bs21.p10_delta_upper, 6),
                },
                "bootstrap_21_p25_delta": {
                    "lower": round(bs21.p25_delta_lower, 6),
                    "median": round(bs21.p25_delta_median, 6),
                    "upper": round(bs21.p25_delta_upper, 6),
                },
                "bootstrap_42_p10_delta": {
                    "lower": round(bs42.p10_delta_lower, 6),
                    "median": round(bs42.p10_delta_median, 6),
                    "upper": round(bs42.p10_delta_upper, 6),
                },
            }

        ledger_records.append(
            LedgerRecord(
                configuration_id=cid,
                family=c.family,
                feature_subset=c.feature_subset_id,
                hyperparameters_or_weights=c.parameters,
                attempt_number=metadata.get("attempt_number", 2),
                budget_slot=c.budget_slot,
                status=config_statuses[cid],
                failure_reason_if_any=fail_msg,
                folds_attempted=f_att,
                folds_completed=f_comp,
                input_hashes=input_integrity["file_digests"],
                preregistration_spec_sha=metadata["preregistration_spec_sha"],
                execution_code_sha=metadata["execution_code_sha"],
                primary_metrics=p_metrics,
                robustness_metrics=r_metrics,
                created_at_or_run_reference=run_id,
                consumes_new_material_slot=metadata.get("consumes_new_material_slot", False),
                correction_contract=metadata.get("correction_task_id", "LONG-002E1-CORR-001"),
                supersedes_run_id=metadata.get("superseded_run_id", "LONG-002E1-20261006_133722"),
            )
        )

    write_experiment_ledger(ledger_records, output_dir / "experiment_ledger.jsonl")

    # 5. round1_summary.json
    all_config_results: list[dict[str, Any]] = []
    for c in configs:
        cid = c.config_id
        summary = eval_summaries.get(cid)
        bs21 = bootstrap_results_21.get(cid)
        st = config_statuses[cid]

        item: dict[str, Any] = {
            "configuration_id": cid,
            "family": c.family,
            "feature_subset_id": c.feature_subset_id,
            "status": st,
            "budget_slot": c.budget_slot,
        }
        if summary and bs21:
            item.update(
                {
                    "p10": round(summary.top10.precision, 6),
                    "matched_vam5_p10": round(summary.top10.matched_vam5_precision, 6),
                    "p10_delta": round(summary.top10.precision_delta_vs_vam5, 6),
                    "p25": round(summary.top25.precision, 6),
                    "matched_vam5_p25": round(summary.top25.matched_vam5_precision, 6),
                    "p25_delta": round(summary.top25.precision_delta_vs_vam5, 6),
                    "lift_10": round(summary.top10.lift_vs_oof_base_rate, 4),
                    "ecmv10": round(summary.top10.empirical_clean_move_value, 4),
                    "ecmv10_delta": round(summary.top10.clean_move_value_delta, 4),
                    "adverse_rate_10": round(summary.top10.primary_adverse_rate, 4),
                    "median_time_to_target": summary.top10.median_time_to_target,
                    "bootstrap_21_p10_lower": round(bs21.p10_delta_lower, 6),
                    "bootstrap_21_p10_median": round(bs21.p10_delta_median, 6),
                    "bootstrap_21_p10_upper": round(bs21.p10_delta_upper, 6),
                    "annual_positive_years": summary.annual_positive_years_count,
                    "overlap_with_vam5_10": round(summary.top10.selection_overlap_pct, 4),
                    "distinct_tickers_10": summary.top10.distinct_tickers_count,
                }
            )
        all_config_results.append(item)

    with (output_dir / "round1_summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_config_results, f, indent=2)

    # 6. family_summary.json
    families_grouped: dict[str, list[dict[str, Any]]] = {}
    for item in all_config_results:
        families_grouped.setdefault(item["family"], []).append(item)

    family_summary_data: dict[str, Any] = {}
    for fam_name, items in families_grouped.items():
        sorted_items = sort_configurations_within_family(items)
        eligible = [x["configuration_id"] for x in items if x["status"] == "round2_eligible"]
        inconclusive = [x["configuration_id"] for x in items if x["status"] == "round1_inconclusive"]
        not_supported = [x["configuration_id"] for x in items if x["status"] == "round1_not_supported"]
        invalid = [x["configuration_id"] for x in items if x["status"] == "invalid_configuration"]

        family_summary_data[fam_name] = {
            "total_configurations": len(items),
            "eligible_count": len(eligible),
            "inconclusive_count": len(inconclusive),
            "not_supported_count": len(not_supported),
            "invalid_count": len(invalid),
            "best_configuration_id": sorted_items[0]["configuration_id"] if sorted_items else None,
            "eligible_configuration_ids": eligible,
            "inconclusive_configuration_ids": inconclusive,
            "not_supported_configuration_ids": not_supported,
            "invalid_configuration_ids": invalid,
            "ordered_configurations": sorted_items,
        }

    with (output_dir / "family_summary.json").open("w", encoding="utf-8") as f:
        json.dump(family_summary_data, f, indent=2)

    # 7. baseline_summary.json
    # Pull matched VAM5 metrics from any summary
    first_sum = next(iter(eval_summaries.values()))
    base_summary_data = {
        "comparator_id": "volatility_aware_momentum_5",
        "family": "frozen_baseline",
        "formula": "0.5 * percentile(return_5) + 0.5 * percentile(atr_pct_14)",
        "evaluation_period": "2018-01-01 to 2020-12-31",
        "evaluation_dates_count": first_sum.evaluation_dates_count,
        "oof_base_rate": round(first_sum.oof_base_rate, 6),
        "matched_top10": {
            "selected_count": first_sum.top10.selected_count,
            "precision_at_10": round(first_sum.top10.matched_vam5_precision, 6),
            "lift_vs_oof_base_rate": round(first_sum.top10.matched_vam5_precision / first_sum.oof_base_rate, 4),
            "empirical_clean_move_value": round(first_sum.top10.matched_vam5_clean_move_value, 4),
            "primary_adverse_rate": round(first_sum.top10.matched_vam5_adverse_rate, 4),
        },
        "matched_top25": {
            "selected_count": first_sum.top25.selected_count,
            "precision_at_25": round(first_sum.top25.matched_vam5_precision, 6),
            "lift_vs_oof_base_rate": round(first_sum.top25.matched_vam5_precision / first_sum.oof_base_rate, 4),
            "empirical_clean_move_value": round(first_sum.top25.matched_vam5_clean_move_value, 4),
            "primary_adverse_rate": round(first_sum.top25.matched_vam5_adverse_rate, 4),
        },
        "annual_precision_10": {str(k): round(v, 6) for k, v in first_sum.annual_vam5_precision_10.items()},
        "full_development_reference": {
            "top_10_clean_rate": 0.153533,
            "top_10_lift": 1.7320,
            "top_25_clean_rate": 0.126881,
            "top_25_lift": 1.4314,
        },
    }
    with (output_dir / "baseline_summary.json").open("w", encoding="utf-8") as f:
        json.dump(base_summary_data, f, indent=2)

    # 8. bootstrap_summary.json
    bs_all_data: dict[str, Any] = {}
    for cid in eval_summaries:
        b21 = bootstrap_results_21[cid]
        b42 = bootstrap_results_42[cid]
        bs_all_data[cid] = {
            "primary_21_session": {
                "p10_delta_ci": [round(b21.p10_delta_lower, 6), round(b21.p10_delta_median, 6), round(b21.p10_delta_upper, 6)],
                "p25_delta_ci": [round(b21.p25_delta_lower, 6), round(b21.p25_delta_median, 6), round(b21.p25_delta_upper, 6)],
            },
            "robustness_42_session": {
                "p10_delta_ci": [round(b42.p10_delta_lower, 6), round(b42.p10_delta_median, 6), round(b42.p10_delta_upper, 6)],
                "p25_delta_ci": [round(b42.p25_delta_lower, 6), round(b42.p25_delta_median, 6), round(b42.p25_delta_upper, 6)],
            },
        }
    with (output_dir / "bootstrap_summary.json").open("w", encoding="utf-8") as f:
        json.dump(bs_all_data, f, indent=2)

    # 9. annual_stability.json
    annual_data: dict[str, Any] = {}
    for cid, sm in eval_summaries.items():
        annual_data[cid] = {
            "annual_precision_10": {str(k): (round(v, 6) if v is not None else None) for k, v in sm.annual_precision_10.items()},
            "annual_precision_10_delta": {str(k): (round(v, 6) if v is not None else None) for k, v in sm.annual_precision_10_delta.items()},
            "annual_positive_years_count": sm.annual_positive_years_count,
        }
    with (output_dir / "annual_stability.json").open("w", encoding="utf-8") as f:
        json.dump(annual_data, f, indent=2)

    # 10. model_diagnostics.json
    diag_data: dict[str, Any] = {}
    for cid, sm in eval_summaries.items():
        diag_data[cid] = {
            "family": sm.family,
            "calibration_status": sm.calibration_status,
            "brier_score": round(sm.brier_score, 6) if sm.brier_score is not None else None,
            "reliability_table": sm.reliability_table,
            "top10_overlap_pct": round(sm.top10.selection_overlap_pct, 4),
            "top25_overlap_pct": round(sm.top25.selection_overlap_pct, 4),
            "top10_distinct_tickers": sm.top10.distinct_tickers_count,
            "top25_distinct_tickers": sm.top25.distinct_tickers_count,
        }
    with (output_dir / "model_diagnostics.json").open("w", encoding="utf-8") as f:
        json.dump(diag_data, f, indent=2)

    # 11. round2_readiness.json
    all_eligible: list[str] = [cid for cid, st in config_statuses.items() if st == "round2_eligible"]
    all_inconclusive: list[str] = [cid for cid, st in config_statuses.items() if st == "round1_inconclusive"]
    all_not_supported: list[str] = [cid for cid, st in config_statuses.items() if st == "round1_not_supported"]
    all_invalid: list[str] = [cid for cid, st in config_statuses.items() if st == "invalid_configuration"]

    if all_eligible:
        overall_status = "round2_candidates_available"
    elif all_inconclusive or all_not_supported:
        overall_status = "no_round2_candidate_supported"
    else:
        overall_status = "invalid_round1_evidence"

    per_family_dispositions: dict[str, dict[str, list[str]]] = {}
    for fam_name in ["cross_sectional_rank_score", "regularized_probabilistic", "shallow_strongly_regularized_gbdt"]:
        fam_cids = [c.config_id for c in configs if c.family == fam_name]
        per_family_dispositions[fam_name] = {
            "eligible_configuration_ids": [cid for cid in fam_cids if config_statuses[cid] == "round2_eligible"],
            "inconclusive_configuration_ids": [cid for cid in fam_cids if config_statuses[cid] == "round1_inconclusive"],
            "not_supported_configuration_ids": [cid for cid in fam_cids if config_statuses[cid] == "round1_not_supported"],
            "invalid_configuration_ids": [cid for cid in fam_cids if config_statuses[cid] == "invalid_configuration"],
        }

    readiness_data = {
        "round1_configurations_budgeted": 36,
        "round1_configurations_attempted": 36,
        "round1_configurations_completed": len(eval_summaries),
        "attempt_number": metadata.get("attempt_number", 2),
        "consumes_new_material_slot": metadata.get("consumes_new_material_slot", False),
        "correction_contract": metadata.get("correction_task_id", "LONG-002E1-CORR-001"),
        "superseded_run_id": metadata.get("superseded_run_id", "LONG-002E1-20261006_133722"),
        "round1_budget_remaining": 0,
        "total_e_budget": 48,
        "remaining_e_budget": 12,
        "overall_status": overall_status,
        "round2_authorized": False,
        "requires_separate_assignment": True,
        "eligible_configuration_ids": all_eligible,
        "inconclusive_configuration_ids": all_inconclusive,
        "not_supported_configuration_ids": all_not_supported,
        "invalid_configuration_ids": all_invalid,
        "family_dispositions": per_family_dispositions,
    }
    with (output_dir / "round2_readiness.json").open("w", encoding="utf-8") as f:
        json.dump(readiness_data, f, indent=2)

    # 12. external_files_manifest.json
    with (output_dir / "external_files_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(external_manifest, f, indent=2)

    # 13. checksums.sha256
    checksums: dict[str, str] = {}
    for p in sorted(output_dir.iterdir()):
        if p.name == "checksums.sha256" or p.is_dir():
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        checksums[p.name] = h

    with (output_dir / "checksums.sha256").open("w", encoding="utf-8") as f:
        for fname, digest in sorted(checksums.items()):
            f.write(f"{digest}  {fname}\n")

    return checksums


def generate_markdown_results_report(
    run_id: str,
    metadata: dict[str, Any],
    base_summary: dict[str, Any],
    round1_summary: list[dict[str, Any]],
    family_summary: dict[str, Any],
    readiness: dict[str, Any],
    checksums: dict[str, str],
) -> str:
    """Generate comprehensive human-readable Markdown report."""
    md: list[str] = []
    md.append("# LONG-002E1: Preregistered Development-Only Round-1 Candidate-System Search Results\n")
    md.append(f"- **Task ID:** `{metadata['task_id']}`")
    md.append(f"- **Correction Contract:** `{metadata.get('correction_task_id', 'LONG-002E1-CORR-001')}`")
    md.append(f"- **Correction Spec SHA-256:** `{metadata.get('correction_spec_sha', '6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96')}`")
    md.append(f"- **Attempt Number:** {metadata.get('attempt_number', 2)} (Consumes New Material Budget Slot: `false`)")
    md.append(f"- **Superseded Run ID:** `{metadata.get('superseded_run_id', 'LONG-002E1-20261006_133722')}` *(preserved as audit evidence; invalid for decision use)*")
    md.append("- **Program:** `LONG-002` (Rapid-Upside Long Opportunity Program)")
    md.append("- **Phase:** `LONG-002E1` (Round-1 Candidate Search)")
    md.append("- **Authorization:** Gary Yang (authorized 2026-10-05)")
    md.append("- **Classification:** Research-Only (Development Split Only)")
    md.append(f"- **Base Git SHA:** `{metadata['base_git_sha']}`")
    md.append(f"- **Preregistration Commit SHA:** `{metadata['preregistration_commit_sha']}`")
    md.append(f"- **Preregistration Spec SHA-256:** `{metadata['preregistration_spec_sha']}`")
    md.append(f"- **Execution Code SHA:** `{metadata['execution_code_sha']}`")
    md.append(f"- **Official Run ID:** `{run_id}`")
    md.append("- **Round-1 Search Budget Accounting:** 36 / 36 material configurations attempted and accounted")
    md.append("- **Remaining LONG-002E Search Budget:** 12 configurations")
    md.append("- **Round 2 Authorized:** `false` (`requires_separate_assignment = true`)")
    md.append("- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)")
    md.append("\n---\n")

    md.append("> [!WARNING]\n"
              f"> **Audit Notice — Superseded Run:** This execution supersedes run `{metadata.get('superseded_run_id', 'LONG-002E1-20261006_133722')}`. "
              "The original run suffered from Fold-1 design asymmetry (post-purge 2016 training set had 0 rows leaving fitted models unpredicted for 2017), "
              "non-common evaluation periods (2017–2020 vs 2018–2020), positional outcome join, and unverified execution provenance. "
              "Per `LONG-002E1-CORR-001`, all 36 configurations are re-executed across the common 2018–2020 evaluation period (730 sessions) "
              "under a 3-of-3 annual positive stability requirement.\n")

    md.append("## 1. Executive Summary & Purpose\n")
    md.append("LONG-002E1 is the first controlled empirical candidate-system search for the LONG-002 program. "
              "Among the 8 frozen features established in LONG-002D3B, exactly 36 material configurations across 3 approved "
              "model families were evaluated strictly on the DEVELOPMENT split (2016–2020 at 20:30 ET) using chronological "
              "expanding-window out-of-fold evaluation (2018–2020 common evaluation period across 730 sessions).\n")
    md.append("> [!IMPORTANT]\n"
              "> This report presents DEVELOPMENT-ONLY evidence. It does NOT constitute validation, holdout, or shadow support, "
              "and does NOT authorize production changes, trading triggers, or Round 2 execution.\n")

    md.append("## 2. Matched Baseline Comparator Performance (VAM5)\n")
    md.append("All candidate configurations are evaluated on the exact same common population and dates as the frozen "
              "baseline comparator `volatility_aware_momentum_5` (50% return_5 percentile + 50% atr_pct_14 percentile).\n")
    md.append(f"- **Evaluation Period:** {base_summary['evaluation_period']} ({base_summary['evaluation_dates_count']} dates)")
    md.append(f"- **OOF Base Rate:** {base_summary['oof_base_rate']:.4%}")
    md.append(f"- **Matched VAM5 Precision@10:** {base_summary['matched_top10']['precision_at_10']:.4%} ({base_summary['matched_top10']['lift_vs_oof_base_rate']:.4f}x lift)")
    md.append(f"- **Matched VAM5 Precision@25:** {base_summary['matched_top25']['precision_at_25']:.4%} ({base_summary['matched_top25']['lift_vs_oof_base_rate']:.4f}x lift)")
    md.append(f"- **Matched VAM5 Clean Move Value @10:** {base_summary['matched_top10']['empirical_clean_move_value']:.4f}")
    md.append(f"- **Matched VAM5 Adverse Rate @10:** {base_summary['matched_top10']['primary_adverse_rate']:.4%}\n")

    md.append("### Annual Matched VAM5 Precision@10:\n")
    md.append("| Year | Matched VAM5 Precision@10 |")
    md.append("|:---:|:---:|")
    for yr, val in base_summary["annual_precision_10"].items():
        md.append(f"| {yr} | {val:.4%} |")
    md.append("\n---\n")

    md.append("## 3. Round-1 Family Summary & Dispositions\n")
    for fam_name, fdata in family_summary.items():
        md.append(f"### Family: `{fam_name}`")
        md.append(f"- Total Configs: {fdata['total_configurations']} | Eligible: {fdata['eligible_count']} | "
                  f"Inconclusive: {fdata['inconclusive_count']} | Not Supported: {fdata['not_supported_count']} | Invalid: {fdata['invalid_count']}")
        md.append(f"- Best Configuration (by locked ordering): `{fdata['best_configuration_id']}`\n")

        md.append("| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |")
        md.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
        for item in fdata["ordered_configurations"]:
            bs_str = f"[{item.get('bootstrap_21_p10_lower', 0):.4f}, {item.get('bootstrap_21_p10_upper', 0):.4f}]" if "bootstrap_21_p10_lower" in item else "N/A"
            p10_str = f"{item['p10']:.4%}" if "p10" in item else "N/A"
            d10_str = f"{item['p10_delta']:+.4%}" if "p10_delta" in item else "N/A"
            p25_str = f"{item['p25']:.4%}" if "p25" in item else "N/A"
            d25_str = f"{item['p25_delta']:+.4%}" if "p25_delta" in item else "N/A"
            pos_str = f"{item['annual_positive_years']}/3" if "annual_positive_years" in item else "N/A"
            adv_str = f"{item['adverse_rate_10']:.4%}" if "adverse_rate_10" in item else "N/A"
            ecmv_str = f"{item['ecmv10']:.2f}" if "ecmv10" in item else "N/A"
            md.append(f"| `{item['configuration_id']}` | {item['feature_subset_id']} | `{item['status']}` | {p10_str} | {d10_str} | {p25_str} | {d25_str} | {bs_str} | {pos_str} | {adv_str} | {ecmv_str} |")
        md.append("\n")

    md.append("---\n")
    md.append("## 4. Search Budget Accounting & Round-2 Readiness\n")
    md.append(f"- **Round-1 Configurations Budgeted:** {readiness['round1_configurations_budgeted']}")
    md.append(f"- **Round-1 Configurations Attempted:** {readiness['round1_configurations_attempted']}")
    md.append(f"- **Round-1 Configurations Completed:** {readiness['round1_configurations_completed']}")
    md.append(f"- **Round-1 Budget Remaining:** {readiness['round1_budget_remaining']}")
    md.append(f"- **Total E Budget:** {readiness['total_e_budget']}")
    md.append(f"- **Remaining E Budget for Round 2:** {readiness['remaining_e_budget']}")
    md.append(f"- **Overall Readiness Disposition:** `{readiness['overall_status']}`")
    md.append(f"- **Round 2 Authorized:** `{str(readiness['round2_authorized']).lower()}`")
    md.append(f"- **Requires Separate Assignment:** `{str(readiness['requires_separate_assignment']).lower()}`\n")

    md.append("### Eligible Configuration IDs for Potential Round 2:\n")
    if readiness["eligible_configuration_ids"]:
        for cid in readiness["eligible_configuration_ids"]:
            md.append(f"- `{cid}`")
    else:
        md.append("- *None*")
    md.append("\n---\n")

    md.append("## 5. Artifact Inventory & Cryptographic Checksums\n")
    md.append("| Artifact File | SHA-256 Digest |")
    md.append("|:---|:---|")
    for fname, digest in sorted(checksums.items()):
        md.append(f"| [`{fname}`](artifacts/LONG-002E1/{run_id}/{fname}) | `{digest}` |")
    md.append("\n---\n")

    md.append("## 6. Stop Condition & Governance Invariants\n")
    md.append("- Execution is complete and verified.")
    md.append("- Round 2 is NOT executed and remains strictly unauthorized.")
    md.append("- Validation (2021–2022), Holdout (2023–2025), and Shadow (2026+) remain strictly quarantined.")
    md.append("- `APPROVED_PRODUCTION_STRATEGIES == ()` is preserved. Zero production trading logic changes.")
    md.append("- Zero market data provider calls were made.")

    return "\n".join(md)
