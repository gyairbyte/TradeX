"""Dependence-aware uncertainty and endpoint feasibility engine for LONG-002C.

Implements 21-session primary and 42-session robustness block resampling,
derives proposed numerical evidence gates from development data only, and evaluates
the primary endpoint (+10/10) vs sole fallback (+10/21).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from tradex.research.long_002c.models import (
    MasterOpportunityEpisode,
    OutcomeLabelRecord,
)


def compute_hhi_and_effective_n(counts: dict[str, int]) -> tuple[float, float]:
    """Compute Herfindahl-Hirschman Index and effective N (1 / HHI) for a frequency distribution."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0, 0.0
    shares = [c / total for c in counts.values()]
    hhi = sum(s * s for s in shares)
    effective_n = 1.0 / hhi if hhi > 0 else 0.0
    return round(hhi, 6), round(effective_n, 2)


def run_block_resampling(
    observations: list[dict[str, Any]],
    outcomes_by_obs_key: dict[tuple[str, str, str], dict[tuple[float, int], OutcomeLabelRecord]],
    sessions_ordered: list[str],
    block_size_sessions: int = 21,
    num_bootstraps: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Perform dependence-aware time-block bootstrap resampling.

    Partitions trading sessions into sequential blocks of block_size_sessions,
    resamples blocks with replacement, and computes 95% confidence intervals
    for key prevalence metrics.
    """
    rng = np.random.default_rng(seed)

    # Group sessions into non-overlapping blocks
    blocks: list[list[str]] = []
    for i in range(0, len(sessions_ordered), block_size_sessions):
        blocks.append(sessions_ordered[i : i + block_size_sessions])

    if not blocks:
        return {}

    # Map session date to list of eligible observations
    obs_by_session: dict[str, list[dict[str, Any]]] = {}
    for obs in observations:
        if obs.get("raw_outcome_eligible", False) and not obs.get("split_boundary_purged", False):
            d = obs["as_of_date"]
            obs_by_session.setdefault(d, []).append(obs)

    num_blocks = len(blocks)

    # Bootstrap metrics tracking
    bs_clean_10_10_rates: list[float] = []
    bs_clean_10_21_rates: list[float] = []
    bs_gross_10_10_rates: list[float] = []
    bs_gross_10_21_rates: list[float] = []

    for _ in range(num_bootstraps):
        sampled_block_indices = rng.integers(0, num_blocks, size=num_blocks)
        tot_obs = 0
        clean_10_10 = 0
        clean_10_21 = 0
        gross_10_10 = 0
        gross_10_21 = 0

        for b_idx in sampled_block_indices:
            block_sessions = blocks[b_idx]
            for s in block_sessions:
                s_obs = obs_by_session.get(s, [])
                for o in s_obs:
                    key = (o["immutable_security_id"], o["as_of_date"], o.get("cutoff_time", "20:30"))
                    cell_outcomes = outcomes_by_obs_key.get(key, {})
                    rec_10_10 = cell_outcomes.get((10.0, 10))
                    rec_10_21 = cell_outcomes.get((10.0, 21))

                    tot_obs += 1
                    if rec_10_10:
                        if rec_10_10.clean_target_reached:
                            clean_10_10 += 1
                        if rec_10_10.target_progress_ratio >= 1.0:
                            gross_10_10 += 1
                    if rec_10_21:
                        if rec_10_21.clean_target_reached:
                            clean_10_21 += 1
                        if rec_10_21.target_progress_ratio >= 1.0:
                            gross_10_21 += 1

        if tot_obs > 0:
            bs_clean_10_10_rates.append(clean_10_10 / tot_obs)
            bs_clean_10_21_rates.append(clean_10_21 / tot_obs)
            bs_gross_10_10_rates.append(gross_10_10 / tot_obs)
            bs_gross_10_21_rates.append(gross_10_21 / tot_obs)
        else:
            bs_clean_10_10_rates.append(0.0)
            bs_clean_10_21_rates.append(0.0)
            bs_gross_10_10_rates.append(0.0)
            bs_gross_10_21_rates.append(0.0)

    def _summary_stats(arr: list[float]) -> dict[str, float]:
        np_arr = np.array(arr)
        return {
            "mean": float(np.mean(np_arr)),
            "std_err": float(np.std(np_arr)),
            "ci_2_5": float(np.percentile(np_arr, 2.5)),
            "median": float(np.percentile(np_arr, 50.0)),
            "ci_97_5": float(np.percentile(np_arr, 97.5)),
        }

    return {
        "block_size_sessions": block_size_sessions,
        "num_blocks": num_blocks,
        "num_bootstraps": num_bootstraps,
        "clean_target_10_10": _summary_stats(bs_clean_10_10_rates),
        "clean_target_10_21": _summary_stats(bs_clean_10_21_rates),
        "gross_target_10_10": _summary_stats(bs_gross_10_10_rates),
        "gross_target_10_21": _summary_stats(bs_gross_10_21_rates),
    }


def analyze_endpoint_feasibility(
    observations: list[dict[str, Any]],
    episodes: list[MasterOpportunityEpisode],
    outcomes: list[OutcomeLabelRecord],
    resampling_21: dict[str, Any],
    resampling_42: dict[str, Any],
) -> dict[str, Any]:
    """Derive development-only endpoint feasibility metrics and frozen future evidence gates."""
    total_obs = len(observations)
    eligible_obs = [
        o for o in observations if o.get("raw_outcome_eligible") and not o.get("split_boundary_purged")
    ]
    purged_obs = [o for o in observations if o.get("split_boundary_purged")]

    n_eligible = len(eligible_obs)
    n_episodes = len(episodes)

    # Clean target prevalence for primary (+10/10) and fallback (+10/21)
    outcomes_10_10 = [o for o in outcomes if o.target_pct == 10.0 and o.horizon_sessions == 10]
    outcomes_10_21 = [o for o in outcomes if o.target_pct == 10.0 and o.horizon_sessions == 21]

    clean_10_10_count = sum(1 for o in outcomes_10_10 if o.clean_target_reached)
    clean_21_count = sum(1 for o in outcomes_10_21 if o.clean_target_reached)

    clean_10_10_prev = (clean_10_10_count / len(outcomes_10_10)) if outcomes_10_10 else 0.0
    clean_21_prev = (clean_21_count / len(outcomes_10_21)) if outcomes_10_21 else 0.0

    # Effective securities in episodes
    ep_sec_counts: dict[str, int] = {}
    for ep in episodes:
        ep_sec_counts[ep.anchor_security_id] = ep_sec_counts.get(ep.anchor_security_id, 0) + 1
    hhi, eff_n = compute_hhi_and_effective_n(ep_sec_counts)

    # Primary endpoint feasibility determination rule:
    # Retain primary +10/10 if:
    # 1. Total master episodes >= 100
    # 2. Primary clean target occurrences >= 100
    # 3. 21-session block bootstrap 95% CI lower bound > 0.005 (0.5%)
    # 4. Effective number of securities in episodes N_eff >= 15.0
    ci_lower = resampling_21.get("clean_target_10_10", {}).get("ci_2_5", 0.0)

    has_sufficient_episodes = n_episodes >= 100
    has_sufficient_prevalence = clean_10_10_count >= 100 and ci_lower > 0.005
    has_sufficient_effective_n = eff_n >= 15.0

    if has_sufficient_episodes and has_sufficient_prevalence and has_sufficient_effective_n:
        preliminary_endpoint = "clean_+10%_10_sessions"
        preliminary_disposition = "primary_retained"
    else:
        preliminary_endpoint = "clean_+10%_21_sessions"
        preliminary_disposition = "fallback_invoked"

    endpoint_disposition = "pending_gary_chatgpt_review"
    selected_endpoint = "pending_gary_chatgpt_review"
    rationale = (
        f"Endpoint disposition is pending Gary/ChatGPT review of the completed development census. "
        f"Preliminary empirical evaluation: {preliminary_disposition} ({preliminary_endpoint}). "
        f"Development census observed {n_episodes} master episodes, {clean_10_10_count} primary clean target events "
        f"(prevalence {clean_10_10_prev:.4f}, 21-session block 95% CI lower bound {ci_lower:.4f}), "
        f"effective securities {eff_n:.1f}, and fallback +10%/21 clean events {clean_21_count} (prevalence {clean_21_prev:.4f})."
    )

    # Actionable observation accounting: if earnings schedule unknown, actionability is unavailable
    actionable_obs = [o for o in observations if o.get("actionability_status") == "eligible"]
    if actionable_obs:
        act_status = "available_point_in_time"
        min_act_val: int | None = max(50, int(0.30 * len(actionable_obs)))
    else:
        act_status = "unavailable_historical_earnings_unknown"
        min_act_val = None

    # Proposed numerical minimum evidence gates for future validation split (2021-2022)
    # Labeled proposed_for_review; NOT frozen until explicitly approved by Gary/ChatGPT review
    proposed_gates = {
        "status": "proposed_for_review",
        "notes": "Proposed numerical evidence gates derived from development data for Gary/ChatGPT review; not locked.",
        "minimum_master_episodes_validation": max(30, int(0.30 * n_episodes)),
        "minimum_clean_target_events_validation": max(15, int(0.30 * clean_10_10_count)),
        "minimum_effective_securities_validation": max(10.0, round(0.35 * eff_n, 1)),
        "actionable_observations_status": act_status,
        "minimum_actionable_observations_validation": min_act_val,
        "clustering_session_fraction_ceiling": 0.85,
    }

    return {
        "total_observations": total_obs,
        "eligible_observations": n_eligible,
        "split_boundary_purged_observations": len(purged_obs),
        "master_episodes_count": n_episodes,
        "distinct_immutable_securities_in_episodes": len(ep_sec_counts),
        "effective_number_of_securities_in_episodes": eff_n,
        "herfindahl_hirschman_index": hhi,
        "primary_clean_10_10_prevalence": round(clean_10_10_prev, 6),
        "primary_clean_10_10_events": clean_10_10_count,
        "fallback_clean_10_21_prevalence": round(clean_21_prev, 6),
        "fallback_clean_10_21_events": clean_21_count,
        "resampling_21_primary": resampling_21,
        "resampling_42_robustness": resampling_42,
        "selected_endpoint": selected_endpoint,
        "endpoint_disposition": endpoint_disposition,
        "preliminary_endpoint": preliminary_endpoint,
        "preliminary_disposition": preliminary_disposition,
        "rationale": rationale,
        "proposed_evidence_gates_for_review": proposed_gates,
        "proposed_frozen_evidence_gates": proposed_gates,
    }
