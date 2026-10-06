"""Chronological expanding-window out-of-fold splitting and boundary purging for LONG-002E1."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradex.research.long_002c.calendar import (
    get_forward_sessions,
    get_trading_sessions,
)


@dataclass(frozen=True)
class FoldDefinition:
    """Specification of an expanding-window chronological fold."""

    fold_id: int
    train_years: list[int]
    eval_year: int
    eval_start_date: str
    eval_end_date: str
    purge_sessions_count: int
    purged_session_dates: list[str]
    last_retained_training_session: str | None


def build_fold_definitions(purge_sessions_count: int = 26) -> list[FoldDefinition]:
    """Construct the 4 expanding folds with 26-session pre-eval boundary purging."""
    fold_configs = [
        (1, [2016], 2017),
        (2, [2016, 2017], 2018),
        (3, [2016, 2017, 2018], 2019),
        (4, [2016, 2017, 2018, 2019], 2020),
    ]

    definitions: list[FoldDefinition] = []

    for fold_id, train_years, eval_yr in fold_configs:
        eval_sessions = get_trading_sessions(f"{eval_yr}-01-01", f"{eval_yr}-12-31")
        first_eval_session = eval_sessions[0]
        eval_start = f"{eval_yr}-01-01"
        eval_end = f"{eval_yr}-12-31"

        # Trading sessions in the training period
        first_train_year = train_years[0]
        last_train_year = train_years[-1]
        all_train_sessions = get_trading_sessions(
            f"{first_train_year}-01-01", f"{last_train_year}-12-31"
        )

        # The final 26 official sessions of the training period (immediately preceding the evaluation year)
        # These are removed to conservatively cover the 26-session Stage C forward-entry/outcome dependency window.
        if len(all_train_sessions) <= purge_sessions_count:
            # All available sessions in the training window fall within the purge window
            purged_sessions = all_train_sessions[:]
            last_retained: str | None = None
        else:
            purged_sessions = all_train_sessions[-purge_sessions_count:]
            last_retained = all_train_sessions[-purge_sessions_count - 1]

            # Invariant check: latest retained observation + 26 forward sessions must terminate < first_eval_session
            fwd = get_forward_sessions(last_retained, purge_sessions_count)
            final_fwd_session = fwd[-1]
            if final_fwd_session >= first_eval_session:
                raise ValueError(
                    f"PURGE BOUNDARY INVARIANT VIOLATION for Fold {fold_id}: "
                    f"Last retained session {last_retained} with 26 forward sessions reaches "
                    f"{final_fwd_session}, which is not strictly before first evaluation session {first_eval_session}"
                )

        definitions.append(
            FoldDefinition(
                fold_id=fold_id,
                train_years=train_years,
                eval_year=eval_yr,
                eval_start_date=eval_start,
                eval_end_date=eval_end,
                purge_sessions_count=purge_sessions_count,
                purged_session_dates=purged_sessions,
                last_retained_training_session=last_retained,
            )
        )

    return definitions


def split_fold_data(
    df: pd.DataFrame,
    fold: FoldDefinition,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into training and evaluation partitions for a fold.

    Removes purged boundary sessions from training partition.
    Never includes evaluation rows in training.
    """
    eval_year_str = str(fold.eval_year)

    # Filter evaluation data
    eval_mask = df["as_of_date"].str.startswith(eval_year_str)
    df_eval = df[eval_mask].copy()

    # Filter training data
    train_mask = (
        df["as_of_date"].str[:4].astype(int).isin(fold.train_years)
        & (~df["as_of_date"].isin(fold.purged_session_dates))
    )
    df_train = df[train_mask].copy()

    # Anti-leakage assertions
    train_dates = set(df_train["as_of_date"].unique())
    eval_dates = set(df_eval["as_of_date"].unique())
    overlap = train_dates.intersection(eval_dates)
    if overlap:
        raise ValueError(f"TRAIN/EVAL OVERLAP DETECTED in Fold {fold.fold_id}: {overlap}")

    if fold.last_retained_training_session and len(df_train) > 0:
        max_train_date = df_train["as_of_date"].max()
        if max_train_date > fold.last_retained_training_session:
            raise ValueError(
                f"TRAINING BOUNDARY LEAKAGE in Fold {fold.fold_id}: "
                f"Max train date {max_train_date} exceeds last retained session {fold.last_retained_training_session}"
            )

    return df_train, df_eval
