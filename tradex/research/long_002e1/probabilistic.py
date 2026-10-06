"""Regularized probabilistic logistic regression modeling for LONG-002E1."""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from tradex.research.long_002e1.configs import ConfigurationSpec


def fit_and_predict_logistic(
    df_train: pd.DataFrame,
    df_eval: pd.DataFrame,
    config: ConfigurationSpec,
) -> pd.Series | None:
    """Fit regularized binary LogisticRegression on training fold and predict evaluation fold.

    Preprocessing:
    - StandardScaler fit ONLY on df_train.
    - df_eval is transformed using training scaler without refitting.

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

    # Scale using training fold only
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_eval_scaled = scaler.transform(X_eval)

    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        clf = LogisticRegression(
            penalty=params.get("penalty", "l2"),
            C=params.get("C", 1.0),
            solver=params.get("solver", "lbfgs"),
            max_iter=params.get("max_iter", 1000),
            tol=params.get("tol", 1e-6),
            class_weight=params.get("class_weight", None),
            random_state=params.get("random_state", 20261005),
        )
        clf.fit(X_train_scaled, y_train)

    probs = clf.predict_proba(X_eval_scaled)[:, 1]

    return pd.Series(probs, index=df_eval.index, name="candidate_probability")
