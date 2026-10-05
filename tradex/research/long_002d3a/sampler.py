"""Deterministic pilot case sampling algorithm for LONG-002D3A."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002d3a.models import PilotCandidate
from tradex.research.long_002d3a.spec import (
    PILOT_QUOTA_PER_STRATUM,
    PILOT_SEED,
    PILOT_SIZE,
    POPULATION_CUTOFF,
    STRATA_PRECEDENCE,
    TARGET_PCT,
    enforce_split_guard,
)


def load_and_verify_stage_c_tables(
    stage_c_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load Stage C tables required for pilot stratification and verify integrity.

    Returns:
        (df_obs, df_outcomes, df_episodes, df_memberships)
    """
    for fname in [
        "decision_observations.parquet",
        "outcome_matrix.parquet",
        "master_episodes.parquet",
        "constituent_memberships.parquet",
    ]:
        p = stage_c_dir / fname
        if not p.exists():
            raise FileNotFoundError(f"Missing required Stage C table: {p}")

    # Load 20:30 development observations
    cols_obs = [
        "immutable_security_id",
        "ticker_at_decision",
        "as_of_date",
        "cutoff_time",
        "raw_outcome_eligible",
        "split_boundary_purged",
    ]
    filters_obs = [
        ("cutoff_time", "=", POPULATION_CUTOFF),
        ("raw_outcome_eligible", "=", True),
        ("split_boundary_purged", "=", False),
    ]
    df_obs = pq.read_table(stage_c_dir / "decision_observations.parquet", columns=cols_obs, filters=filters_obs).to_pandas()

    # Load primary outcome cell (+10% / 10d)
    cols_out = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "clean_target_reached",
        "target_progress_ratio",
        "near_miss",
        "adverse_excursion",
        "mfe_pct",
        "mae_pct",
        "time_to_target",
    ]
    filters_out = [
        ("cutoff_time", "=", POPULATION_CUTOFF),
        ("target_pct", "=", TARGET_PCT),
        ("horizon_sessions", "=", 10),
    ]
    df_out = pq.read_table(stage_c_dir / "outcome_matrix.parquet", columns=cols_out, filters=filters_out).to_pandas()

    # Load master episodes at 20:30
    cols_episodes = [
        "episode_id",
        "anchor_security_id",
        "anchor_ticker",
        "anchor_as_of_date",
        "anchor_cutoff_time",
        "clean_target_reached_10_21",
        "max_return_pct_21",
        "first_target_session_index",
    ]
    filters_episodes = [("anchor_cutoff_time", "=", POPULATION_CUTOFF)]
    df_episodes = pq.read_table(stage_c_dir / "master_episodes.parquet", columns=cols_episodes, filters=filters_episodes).to_pandas()

    # Load constituent memberships at 20:30
    cols_members = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "episode_id",
        "constituent_tag",
    ]
    filters_members = [("cutoff_time", "=", POPULATION_CUTOFF)]
    df_members = pq.read_table(stage_c_dir / "constituent_memberships.parquet", columns=cols_members, filters=filters_members).to_pandas()

    return df_obs, df_out, df_episodes, df_members


def sample_pilot_cases(
    stage_c_dir: Path,
    seed: int = PILOT_SEED,
) -> list[PilotCandidate]:
    """Execute deterministic, class-balanced pilot sampling.

    Enforces:
    - Exactly 24 pilot cases (6 per stratum).
    - Four strata: positive_master_episode, near_miss, adverse_trap, ordinary_non_mover.
    - Class precedence prevents overlap.
    - Control cases strictly outside active master episodes.
    - Global ticker diversity: exactly 24 unique tickers.
    - Annual diversity: representation across 2016-2020.
    - Deterministic final shuffle with frozen seed.
    - Opaque case IDs D3A-PILOT-001 through D3A-PILOT-024.
    """
    df_obs, df_out, df_episodes, df_members = load_and_verify_stage_c_tables(stage_c_dir)

    # Validate split guard on date ranges
    min_date = df_obs["as_of_date"].min()
    max_date = df_obs["as_of_date"].max()
    enforce_split_guard(min_date)
    enforce_split_guard(max_date)

    # Join observations and outcomes
    df_all = df_obs.merge(df_out, on=["immutable_security_id", "as_of_date", "cutoff_time"], how="inner")
    df_all["year"] = df_all["as_of_date"].str.slice(0, 4)

    # Identify all active episode observations (anchors + constituent members in window)
    anchor_set = set(zip(df_episodes["anchor_security_id"], df_episodes["anchor_as_of_date"], df_episodes["anchor_cutoff_time"]))
    member_set = set(zip(df_members["immutable_security_id"], df_members["as_of_date"], df_members["cutoff_time"]))
    active_episode_obs_set = anchor_set | member_set

    # Stratum 1: Positive Master Episodes (Anchor observations)
    pos_anchors = df_episodes.rename(
        columns={
            "anchor_security_id": "immutable_security_id",
            "anchor_ticker": "ticker_at_decision",
            "anchor_as_of_date": "as_of_date",
            "anchor_cutoff_time": "cutoff_time",
        }
    ).copy()
    pos_anchors["year"] = pos_anchors["as_of_date"].str.slice(0, 4)
    pos_anchors["sample_stratum"] = "positive_master_episode"

    # Merge primary outcome details into pos_anchors
    pos_anchors = pos_anchors.merge(
        df_out,
        on=["immutable_security_id", "as_of_date", "cutoff_time"],
        how="left",
    )

    # Non-episode observations for controls
    df_non_episode = df_all[
        ~df_all.apply(
            lambda r: (r["immutable_security_id"], r["as_of_date"], r["cutoff_time"]) in active_episode_obs_set,
            axis=1,
        )
    ].copy()
    df_non_episode["episode_id"] = None

    # Stratum 2: Near Miss (outside active episode, clean=False, near_miss=True)
    near_miss = df_non_episode[
        (df_non_episode["clean_target_reached"] == False) & (df_non_episode["near_miss"] == True)
    ].copy()
    near_miss["sample_stratum"] = "near_miss"

    # Stratum 3: Adverse Trap (outside active episode, clean=False, near_miss=False, adverse=True)
    adverse = df_non_episode[
        (df_non_episode["clean_target_reached"] == False)
        & (df_non_episode["near_miss"] == False)
        & (df_non_episode["adverse_excursion"] == True)
    ].copy()
    adverse["sample_stratum"] = "adverse_trap"

    # Stratum 4: Ordinary Non-Mover (outside active episode, clean=False, near_miss=False, adverse=False, progress < 0.5)
    non_mover = df_non_episode[
        (df_non_episode["clean_target_reached"] == False)
        & (df_non_episode["near_miss"] == False)
        & (df_non_episode["adverse_excursion"] == False)
        & (df_non_episode["target_progress_ratio"] < 0.50)
    ].copy()
    non_mover["sample_stratum"] = "ordinary_non_mover"

    strata_map = {
        "positive_master_episode": pos_anchors,
        "near_miss": near_miss,
        "adverse_trap": adverse,
        "ordinary_non_mover": non_mover,
    }

    # Deterministic sampling with seed
    rng = random.Random(seed)
    selected_rows: list[dict[str, Any]] = []
    selected_tickers: set[str] = set()

    development_years = ["2016", "2017", "2018", "2019", "2020"]

    for stratum_name in STRATA_PRECEDENCE:
        df_stratum = strata_map[stratum_name]
        stratum_selected = []

        # Step 1: Draw 1 case from each development year 2016-2020
        for yr in development_years:
            df_yr = df_stratum[df_stratum["year"] == yr].sort_values(["as_of_date", "immutable_security_id"])
            indices = list(df_yr.index)
            rng.shuffle(indices)

            chosen = None
            for idx in indices:
                row = df_yr.loc[idx]
                tk = str(row["ticker_at_decision"])
                if tk not in selected_tickers:
                    chosen = row.to_dict()
                    selected_tickers.add(tk)
                    break

            if chosen is None:
                raise RuntimeError(f"Could not find candidate with unique ticker for {stratum_name} in year {yr}")
            stratum_selected.append(chosen)

        # Step 2: Draw 1 6th case from remaining candidates in stratum pool
        df_rem = df_stratum.sort_values(["as_of_date", "immutable_security_id"])
        rem_indices = list(df_rem.index)
        rng.shuffle(rem_indices)

        chosen_6th = None
        for idx in rem_indices:
            row = df_rem.loc[idx]
            tk = str(row["ticker_at_decision"])
            if tk not in selected_tickers:
                chosen_6th = row.to_dict()
                selected_tickers.add(tk)
                break

        if chosen_6th is None:
            raise RuntimeError(f"Could not find 6th candidate with unique ticker for {stratum_name}")
        stratum_selected.append(chosen_6th)

        assert len(stratum_selected) == PILOT_QUOTA_PER_STRATUM == 6
        selected_rows.extend(stratum_selected)

    assert len(selected_rows) == PILOT_SIZE == 24
    assert len(selected_tickers) == PILOT_SIZE == 24

    # Final deterministic seeded shuffle across all 24 cases
    rng_shuffle = random.Random(seed)
    shuffled_rows = list(selected_rows)
    rng_shuffle.shuffle(shuffled_rows)

    # Assign opaque case IDs D3A-PILOT-001 through D3A-PILOT-024
    candidates: list[PilotCandidate] = []
    for i, r in enumerate(shuffled_rows, start=1):
        case_id = f"D3A-PILOT-{i:03d}"
        cand = PilotCandidate(
            case_id=case_id,
            sample_stratum=str(r["sample_stratum"]),
            immutable_security_id=str(r["immutable_security_id"]),
            as_of_date=str(r["as_of_date"]),
            cutoff_time=str(r["cutoff_time"]),
            ticker_at_decision=str(r["ticker_at_decision"]),
            year=str(r["year"]),
            episode_id=r.get("episode_id") if pd.notna(r.get("episode_id")) else None,
            clean_target_reached=bool(r.get("clean_target_reached", False)),
            target_progress_ratio=float(r.get("target_progress_ratio", 0.0)) if pd.notna(r.get("target_progress_ratio")) else 0.0,
            near_miss=bool(r.get("near_miss", False)),
            adverse_excursion=bool(r.get("adverse_excursion", False)),
            mfe_pct=float(r["mfe_pct"]) if pd.notna(r.get("mfe_pct")) else None,
            mae_pct=float(r["mae_pct"]) if pd.notna(r.get("mae_pct")) else None,
            time_to_target=int(r["time_to_target"]) if pd.notna(r.get("time_to_target")) else None,
        )
        candidates.append(cand)

    return candidates
