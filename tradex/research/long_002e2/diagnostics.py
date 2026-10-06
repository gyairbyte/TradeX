"""Comprehensive diagnostic runner orchestrating all LONG-002E2 analyses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.long_002e2.bootstrap import run_annual_paired_bootstrap
from tradex.research.long_002e2.concentration import evaluate_selection_concentration
from tradex.research.long_002e2.feature_profiles import (
    compute_cross_sectional_feature_percentiles,
    evaluate_feature_profile_drift,
)
from tradex.research.long_002e2.loader import load_e2_datasets
from tradex.research.long_002e2.localization import compute_localization_metrics
from tradex.research.long_002e2.probabilities import evaluate_probability_stability
from tradex.research.long_002e2.quarters import evaluate_quarterly_decomposition
from tradex.research.long_002e2.regimes import (
    compute_spy_date_regimes,
    evaluate_spy_regime_diagnostics,
)
from tradex.research.long_002e2.reproduction import (
    analyze_family_annual_context,
    verify_e1_reproduction,
)
from tradex.research.long_002e2.selection import build_date_selections
from tradex.research.long_002e2.selection_sets import (
    evaluate_selection_set_decomposition,
    partition_date_selections,
)
from tradex.research.long_002e2.spec import (
    D1_FEATURE_TABLE_PATH,
    E1_PREDICTION_PATH,
    STAGE_C_BASELINE_PATH,
)


def run_all_e2_diagnostics(
    e1_pred_path: Path = E1_PREDICTION_PATH,
    d1_feature_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
) -> dict[str, Any]:
    """Execute all 7 preregistered diagnostics for LONG-002E2."""
    # 1. Load and verify input integrity
    df_pred, df_vam5, df_features, digests = load_e2_datasets(
        e1_pred_path=e1_pred_path,
        d1_feature_path=d1_feature_path,
        baseline_path=baseline_path,
    )

    # 2. Extract deterministic date selections
    # Merge prediction metrics with VAM5 baseline ranks
    df_joined = df_pred.merge(
        df_vam5[
            [
                "immutable_security_id",
                "as_of_date",
                "cutoff_time",
                "cross_sectional_rank",
                "raw_score_or_return",
            ]
        ],
        on=["immutable_security_id", "as_of_date", "cutoff_time"],
        how="inner",
        validate="one_to_one",
    )

    cand_10_by_date, cand_25_by_date, vam5_10_by_date, vam5_25_by_date, date_records = (
        build_date_selections(df_joined)
    )

    df_cand_10 = pd.concat(list(cand_10_by_date.values()), ignore_index=True)
    df_cand_25 = pd.concat(list(cand_25_by_date.values()), ignore_index=True)
    df_vam5_10 = pd.concat(list(vam5_10_by_date.values()), ignore_index=True)
    df_vam5_25 = pd.concat(list(vam5_25_by_date.values()), ignore_index=True)

    # 3. Reproduction check & family context
    reproduction_check = verify_e1_reproduction(df_cand_10, df_cand_25, df_vam5_10, df_vam5_25)
    family_context = analyze_family_annual_context()

    # 4. Diagnostic 1: Annual Paired Uncertainty (21-session block bootstrap)
    annual_bootstrap = run_annual_paired_bootstrap(date_records)

    # 5. Diagnostic 2: Fixed Calendar-Quarter Decomposition
    quarterly_diagnostics = evaluate_quarterly_decomposition(
        df_cand_10, df_cand_25, df_vam5_10, df_vam5_25
    )

    # 6. Diagnostic 3: Market-Context Regimes
    date_regime_map, q30, q70, regime_date_counts = compute_spy_date_regimes(df_features)
    spy_regime_diagnostics = evaluate_spy_regime_diagnostics(
        df_cand_10,
        df_cand_25,
        df_vam5_10,
        df_vam5_25,
        date_regime_map,
        q30,
        q70,
        regime_date_counts,
    )

    # 7. Diagnostic 4: Selection-Set Decomposition
    df_overlap, df_logit_only, df_vam5_only = partition_date_selections(
        cand_10_by_date, vam5_10_by_date
    )
    selection_set_decomposition = evaluate_selection_set_decomposition(
        df_overlap, df_logit_only, df_vam5_only
    )

    # 8. Diagnostic 5: Feature-Profile Drift
    df_percentiles = compute_cross_sectional_feature_percentiles(df_features)
    feature_profile_drift = evaluate_feature_profile_drift(
        df_percentiles, df_logit_only, df_vam5_only
    )

    # 9. Diagnostic 6: Selection Concentration
    selection_concentration = evaluate_selection_concentration(df_cand_10, df_vam5_10)

    # 10. Diagnostic 7: Raw Probability Stability
    probability_stability = evaluate_probability_stability(df_pred)

    # 11. Localization Metrics and Decision Rule
    localization_metrics, diagnostic_decision = compute_localization_metrics(
        quarterly_diagnostics["quarters"],
        spy_regime_diagnostics["year_x_regime"],
        reproduction_check["annual_metrics"],
    )

    input_integrity = {
        "status": "verified",
        "observation_count": len(df_pred),
        "evaluation_sessions_count": len(date_records),
        "digests": digests,
    }

    return {
        "input_integrity": input_integrity,
        "reproduction_check": reproduction_check,
        "family_context": family_context,
        "annual_bootstrap": annual_bootstrap,
        "quarterly_diagnostics": quarterly_diagnostics,
        "spy_regime_diagnostics": spy_regime_diagnostics,
        "selection_set_decomposition": selection_set_decomposition,
        "feature_profile_drift": feature_profile_drift,
        "selection_concentration": selection_concentration,
        "probability_stability": probability_stability,
        "localization_metrics": localization_metrics,
        "diagnostic_decision": diagnostic_decision,
    }
