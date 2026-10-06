"""Configuration registry and definition models for LONG-002E1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradex.research.long_002e1.spec import (
    DETERMINISTIC_SEED,
)

FEATURE_SUBSETS: dict[str, list[str]] = {
    "S1": ["return_5", "atr_pct_14", "return_20", "return_60"],
    "S2": [
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
    ],
    "S3": [
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
        "relative_volume_20",
    ],
    "S4": [
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
        "sma20_slope_5",
        "relative_volume_20",
    ],
}


def compute_rank_weights(subset_id: str, template_id: str) -> dict[str, float]:
    """Compute exact deterministic weights for a given feature subset and weight template.

    Templates:
    T1 = EQUAL: All features receive identical weight (1 / N).
    T2 = ATR_TILT: atr_pct_14 = 0.40, remaining N-1 features split 0.60 equally (0.60 / (N - 1)).
    T3 = CORE_TILT: return_5 = 0.30, atr_pct_14 = 0.30, remaining N-2 features split 0.40 equally (0.40 / (N - 2)).
    """
    feats = FEATURE_SUBSETS[subset_id]
    n = len(feats)

    if template_id == "T1":
        w = 1.0 / n
        weights = {f: w for f in feats}
    elif template_id == "T2":
        if "atr_pct_14" not in feats:
            raise ValueError(f"atr_pct_14 missing from subset {subset_id}")
        rem_feats = [f for f in feats if f != "atr_pct_14"]
        rem_w = 0.60 / len(rem_feats)
        weights = {"atr_pct_14": 0.40}
        for f in rem_feats:
            weights[f] = rem_w
    elif template_id == "T3":
        if "return_5" not in feats or "atr_pct_14" not in feats:
            raise ValueError(f"Core features missing from subset {subset_id}")
        rem_feats = [f for f in feats if f not in ("return_5", "atr_pct_14")]
        rem_w = 0.40 / len(rem_feats) if len(rem_feats) > 0 else 0.0
        weights = {"return_5": 0.30, "atr_pct_14": 0.30}
        for f in rem_feats:
            weights[f] = rem_w
    else:
        raise ValueError(f"Unknown weight template: {template_id}")

    # Precision check: sum must equal 1.0
    total_w = sum(weights.values())
    if abs(total_w - 1.0) > 1e-9:
        raise ValueError(f"Weights do not sum to 1.0: sum={total_w}")

    # No negative weights check
    for f, val in weights.items():
        if val < 0.0:
            raise ValueError(f"Negative weight for {f}: {val}")

    return weights


GBDT_PROFILES: dict[str, dict[str, Any]] = {
    "G1": {
        "learning_rate": 0.03,
        "max_iter": 100,
        "max_depth": 2,
        "max_leaf_nodes": 4,
        "min_samples_leaf": 200,
        "l2_regularization": 5.0,
        "early_stopping": False,
        "random_state": DETERMINISTIC_SEED,
    },
    "G2": {
        "learning_rate": 0.03,
        "max_iter": 150,
        "max_depth": 3,
        "max_leaf_nodes": 8,
        "min_samples_leaf": 200,
        "l2_regularization": 10.0,
        "early_stopping": False,
        "random_state": DETERMINISTIC_SEED,
    },
    "G3": {
        "learning_rate": 0.05,
        "max_iter": 100,
        "max_depth": 3,
        "max_leaf_nodes": 8,
        "min_samples_leaf": 100,
        "l2_regularization": 20.0,
        "early_stopping": False,
        "random_state": DETERMINISTIC_SEED,
    },
}

LOGIT_C_VALUES: dict[str, float] = {
    "C003": 0.03,
    "C030": 0.30,
    "C300": 3.00,
}


@dataclass(frozen=True)
class ConfigurationSpec:
    """Full specification of a Round-1 material candidate configuration."""

    config_id: str
    family: str
    feature_subset_id: str
    features: list[str]
    parameters: dict[str, Any]
    budget_slot: int


def build_round1_registry() -> list[ConfigurationSpec]:
    """Construct exactly 36 material Round-1 configurations across the 3 approved families."""
    configs: list[ConfigurationSpec] = []
    slot = 1

    # Family 1: Transparent Rank/Score (12 configurations)
    for subset_id in ["S1", "S2", "S3", "S4"]:
        for tmpl_id in ["T1", "T2", "T3"]:
            c_id = f"RANK_{subset_id}_{tmpl_id}"
            w = compute_rank_weights(subset_id, tmpl_id)
            configs.append(
                ConfigurationSpec(
                    config_id=c_id,
                    family="cross_sectional_rank_score",
                    feature_subset_id=subset_id,
                    features=FEATURE_SUBSETS[subset_id],
                    parameters={"weights": w, "template": tmpl_id},
                    budget_slot=slot,
                )
            )
            slot += 1

    # Family 2: Regularized Probabilistic (12 configurations)
    for subset_id in ["S1", "S2", "S3", "S4"]:
        for c_code, c_val in LOGIT_C_VALUES.items():
            c_id = f"LOGIT_{subset_id}_{c_code}"
            params = {
                "penalty": "l2",
                "C": c_val,
                "solver": "lbfgs",
                "max_iter": 1000,
                "tol": 1e-6,
                "class_weight": None,
                "random_state": DETERMINISTIC_SEED,
            }
            configs.append(
                ConfigurationSpec(
                    config_id=c_id,
                    family="regularized_probabilistic",
                    feature_subset_id=subset_id,
                    features=FEATURE_SUBSETS[subset_id],
                    parameters=params,
                    budget_slot=slot,
                )
            )
            slot += 1

    # Family 3: Shallow Strongly Regularized GBDT (12 configurations)
    for subset_id in ["S1", "S2", "S3", "S4"]:
        for prof_code in ["G1", "G2", "G3"]:
            c_id = f"GBDT_{subset_id}_{prof_code}"
            params = dict(GBDT_PROFILES[prof_code])
            configs.append(
                ConfigurationSpec(
                    config_id=c_id,
                    family="shallow_strongly_regularized_gbdt",
                    feature_subset_id=subset_id,
                    features=FEATURE_SUBSETS[subset_id],
                    parameters=params,
                    budget_slot=slot,
                )
            )
            slot += 1

    if len(configs) != 36:
        raise ValueError(f"Expected 36 configurations, built {len(configs)}")

    return configs
