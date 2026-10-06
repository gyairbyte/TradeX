"""Shallow strongly regularized gradient-boosted trees modeling for LONG-002E1."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from tradex.research.long_002e1.configs import ConfigurationSpec


def fit_and_predict_gbdt(
    df_train: pd.DataFrame,
    df_eval: pd.DataFrame,
    config: ConfigurationSpec,
) -> pd.Series | None:
    """Fit HistGradientBoostingClassifier on training fold and predict evaluation fold.

    Uses locked profile hyperparameters. No early stopping.
    Deterministic random state = 20261005.

    Returns:
        pd.Series of predicted probabilities for evaluation fold, or None if training data is empty.
    """
    if len(df_train) == 0:
        return None

    features = config.features
    params = config.parameters

    X_train = df_train[features].to_numpy(dtype=float)
    y_train = df_train["clean_target_reached"].to_numpy(dtype=int)

    X_eval = df_eval[features].to_numpy(dtype=float)

    gbdt = HistGradientBoostingClassifier(
        learning_rate=params.get("learning_rate", 0.03),
        max_iter=params.get("max_iter", 100),
        max_depth=params.get("max_depth", 2),
        max_leaf_nodes=params.get("max_leaf_nodes", 4),
        min_samples_leaf=params.get("min_samples_leaf", 200),
        l2_regularization=params.get("l2_regularization", 5.0),
        early_stopping=params.get("early_stopping", False),
        random_state=params.get("random_state", 20261005),
    )

    gbdt.fit(X_train, y_train)
    probs = gbdt.predict_proba(X_eval)[:, 1]

    return pd.Series(probs, index=df_eval.index, name="candidate_probability")
