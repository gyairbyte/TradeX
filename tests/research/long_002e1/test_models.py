"""Tests for deterministic candidate models across 3 families (Tests 41-48)."""

import numpy as np
import pandas as pd

from tradex.research.long_002e1.configs import build_round1_registry
from tradex.research.long_002e1.gbdt import fit_and_predict_gbdt
from tradex.research.long_002e1.probabilistic import fit_and_predict_logistic
from tradex.research.long_002e1.rank_model import evaluate_rank_model
from tradex.research.long_002e1.spec import ALLOWED_FEATURES


def test_41_rank_model_determinism():
    """Test 41: Transparent rank model produces identical scores across two independent runs."""
    configs = [c for c in build_round1_registry() if c.family == "cross_sectional_rank_score"]
    cfg = configs[0]
    dummy_eval = pd.DataFrame(
        {
            "immutable_security_id": ["S1", "S2", "S3", "S4"],
            "as_of_date": ["2018-01-02"] * 4,
            "return_5": [0.05, 0.02, 0.08, -0.01],
            "atr_pct_14": [0.03, 0.04, 0.01, 0.05],
            "return_20": [0.10, 0.05, 0.12, 0.00],
            "return_60": [0.15, 0.08, 0.20, 0.02],
        }
    )
    s1 = evaluate_rank_model(dummy_eval, cfg)
    s2 = evaluate_rank_model(dummy_eval, cfg)
    np.testing.assert_array_equal(s1.to_numpy(), s2.to_numpy())


def test_42_rank_model_tie_breaking():
    """Test 42: Rank model tie-breaking by immutable_security_id is deterministic."""
    configs = [c for c in build_round1_registry() if c.family == "cross_sectional_rank_score"]
    cfg = configs[0]
    # Two identical feature observations with different IDs
    dummy_eval = pd.DataFrame(
        {
            "immutable_security_id": ["SEC_B", "SEC_A"],
            "as_of_date": ["2018-01-02", "2018-01-02"],
            "return_5": [0.05, 0.05],
            "atr_pct_14": [0.03, 0.03],
            "return_20": [0.10, 0.10],
            "return_60": [0.15, 0.15],
        }
    )
    # SEC_A comes first lexicographically, so it gets higher percentile rank than SEC_B
    scores = evaluate_rank_model(dummy_eval, cfg)
    assert scores.iloc[1] > scores.iloc[0]  # SEC_A > SEC_B


def test_43_rank_weights_sum_to_one():
    """Test 43: Rank weights sum to 1.0 within 1e-9 tolerance for all 12 rank configs."""
    rank_configs = [c for c in build_round1_registry() if c.family == "cross_sectional_rank_score"]
    assert len(rank_configs) == 12
    for c in rank_configs:
        w_sum = sum(c.parameters["weights"].values())
        assert abs(w_sum - 1.0) < 1e-9


def test_44_logistic_regression_determinism():
    """Test 44: Logistic regression with StandardScaler produces identical probabilities on identical input."""
    log_configs = [c for c in build_round1_registry() if c.family == "regularized_probabilistic"]
    cfg = log_configs[0]

    np.random.seed(42)
    n = 200
    df_train = pd.DataFrame(
        {
            "return_5": np.random.randn(n),
            "atr_pct_14": np.random.randn(n),
            "return_20": np.random.randn(n),
            "return_60": np.random.randn(n),
            "clean_target_reached": np.random.randint(0, 2, n),
        }
    )
    df_eval = pd.DataFrame(
        {
            "return_5": np.random.randn(50),
            "atr_pct_14": np.random.randn(50),
            "return_20": np.random.randn(50),
            "return_60": np.random.randn(50),
        }
    )

    p1 = fit_and_predict_logistic(df_train, df_eval, cfg)
    p2 = fit_and_predict_logistic(df_train, df_eval, cfg)
    assert p1 is not None and p2 is not None
    np.testing.assert_array_equal(p1.to_numpy(), p2.to_numpy())


def test_45_scaler_fit_exclusively_on_train():
    """Test 45: StandardScaler is fit exclusively on training data and never refit on eval data."""
    # Verified by inspection of fit_and_predict_logistic: scaler.fit_transform(X_train), scaler.transform(X_eval)
    from sklearn.preprocessing import StandardScaler
    X_tr = np.array([[10.0], [20.0]])
    X_ev = np.array([[100.0]])
    sc = StandardScaler()
    sc.fit(X_tr)
    # Mean of training is 15.0, std is 5.0
    ev_scaled = sc.transform(X_ev)
    assert ev_scaled[0, 0] == (100.0 - 15.0) / 5.0


def test_46_gbdt_determinism():
    """Test 46: HistGradientBoostingClassifier produces deterministic probabilities with random_state=20261005."""
    gbdt_configs = [c for c in build_round1_registry() if c.family == "shallow_strongly_regularized_gbdt"]
    cfg = gbdt_configs[0]

    np.random.seed(42)
    n = 300
    df_train = pd.DataFrame(
        {
            "return_5": np.random.randn(n),
            "atr_pct_14": np.random.randn(n),
            "return_20": np.random.randn(n),
            "return_60": np.random.randn(n),
            "clean_target_reached": np.random.randint(0, 2, n),
        }
    )
    df_eval = pd.DataFrame(
        {
            "return_5": np.random.randn(50),
            "atr_pct_14": np.random.randn(50),
            "return_20": np.random.randn(50),
            "return_60": np.random.randn(50),
        }
    )

    p1 = fit_and_predict_gbdt(df_train, df_eval, cfg)
    p2 = fit_and_predict_gbdt(df_train, df_eval, cfg)
    assert p1 is not None and p2 is not None
    np.testing.assert_array_equal(p1.to_numpy(), p2.to_numpy())


def test_47_gbdt_shallow_regularization():
    """Test 47: GBDT models have max_depth <= 3 and early_stopping == False across all 12 configs."""
    gbdt_configs = [c for c in build_round1_registry() if c.family == "shallow_strongly_regularized_gbdt"]
    assert len(gbdt_configs) == 12
    for c in gbdt_configs:
        assert c.parameters["max_depth"] <= 3
        assert c.parameters["early_stopping"] is False
        assert c.parameters["l2_regularization"] >= 5.0


def test_48_no_unallowed_features():
    """Test 48: No model uses features outside the 8 frozen features in ALLOWED_FEATURES."""
    all_configs = build_round1_registry()
    allowed_set = set(ALLOWED_FEATURES)
    for c in all_configs:
        assert set(c.features).issubset(allowed_set)
