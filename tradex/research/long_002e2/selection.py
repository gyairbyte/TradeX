"""Deterministic date-level selection and Top-K extraction for LONG-002E2."""

from __future__ import annotations

from typing import Any

import pandas as pd


def select_top_k_for_date(
    df_date: pd.DataFrame,
    score_column: str,
    k: int,
    ascending: bool = False,
) -> pd.DataFrame:
    """Deterministically select top K observations for a single date.

    Tie-break: immutable_security_id ASC.
    If date has fewer than K observations, returns all observations without backfill.
    """
    n = len(df_date)
    k_actual = min(k, n)
    if k_actual == 0:
        return df_date.head(0)

    # Sort by score_column, tie-break immutable_security_id ASC
    sorted_df = df_date.sort_values(
        by=[score_column, "immutable_security_id"],
        ascending=[ascending, True],
    )
    return sorted_df.head(k_actual)


def build_date_selections(
    df_joined: pd.DataFrame,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
]:
    """Extract candidate and matched VAM5 Top-10 and Top-25 selections for each date.

    df_joined must contain:
    - immutable_security_id
    - as_of_date
    - candidate_probability
    - cross_sectional_rank
    - clean_target_reached
    - realized_clean_tier
    - adverse_excursion
    - time_to_target
    """
    unique_dates = sorted(df_joined["as_of_date"].unique().tolist())

    cand_10_by_date: dict[str, pd.DataFrame] = {}
    cand_25_by_date: dict[str, pd.DataFrame] = {}
    vam5_10_by_date: dict[str, pd.DataFrame] = {}
    vam5_25_by_date: dict[str, pd.DataFrame] = {}
    date_records: list[dict[str, Any]] = []

    for d in unique_dates:
        df_d = df_joined[df_joined["as_of_date"] == d]

        # Candidate selections (DESC by candidate_probability, tie-break ID ASC)
        c10 = select_top_k_for_date(df_d, "candidate_probability", 10, ascending=False)
        c25 = select_top_k_for_date(df_d, "candidate_probability", 25, ascending=False)

        # VAM5 baseline selections (ASC by cross_sectional_rank, tie-break ID ASC)
        v10 = select_top_k_for_date(df_d, "cross_sectional_rank", 10, ascending=True)
        v25 = select_top_k_for_date(df_d, "cross_sectional_rank", 25, ascending=True)

        if len(c10) != len(v10):
            raise ValueError(
                f"SELECTION COUNT MISMATCH ON DATE {d}: candidate selected {len(c10)} != VAM5 {len(v10)}"
            )
        if len(c25) != len(v25):
            raise ValueError(
                f"SELECTION COUNT MISMATCH ON DATE {d} (K=25): candidate {len(c25)} != VAM5 {len(v25)}"
            )

        cand_10_by_date[d] = c10
        cand_25_by_date[d] = c25
        vam5_10_by_date[d] = v10
        vam5_25_by_date[d] = v25

        c10_clean = int(c10["clean_target_reached"].sum())
        v10_clean = int(v10["clean_target_reached"].sum())
        c25_clean = int(c25["clean_target_reached"].sum())
        v25_clean = int(v25["clean_target_reached"].sum())

        overlap_10 = len(
            set(c10["immutable_security_id"]).intersection(set(v10["immutable_security_id"]))
        )
        overlap_25 = len(
            set(c25["immutable_security_id"]).intersection(set(v25["immutable_security_id"]))
        )

        date_records.append(
            {
                "as_of_date": d,
                "n_eval": len(df_d),
                "k10_selected": len(c10),
                "c10_clean": c10_clean,
                "v10_clean": v10_clean,
                "hit_delta_10": c10_clean - v10_clean,
                "overlap_10": overlap_10,
                "k25_selected": len(c25),
                "c25_clean": c25_clean,
                "v25_clean": v25_clean,
                "hit_delta_25": c25_clean - v25_clean,
                "overlap_25": overlap_25,
            }
        )

    return cand_10_by_date, cand_25_by_date, vam5_10_by_date, vam5_25_by_date, date_records
