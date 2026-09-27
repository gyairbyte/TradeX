"""Master Opportunity Episode clustering for LONG-002C.

Implements the locked non-recursive 21-session windowing anchored by earliest unassigned +10%/21 moves.
Assigns constituent observation tags (pre_target, target_session, post_target) and generates deterministic IDs.
"""
from __future__ import annotations

from typing import Any

from tradex.research.long_002c.calendar import get_forward_sessions
from tradex.research.long_002c.models import (
    EpisodeMembership,
    MasterOpportunityEpisode,
    OutcomeLabelRecord,
)


def cluster_master_episodes(
    observations_by_security: dict[str, list[dict[str, Any]]],
    outcomes_by_obs_key: dict[tuple[str, str, str], dict[tuple[float, int], OutcomeLabelRecord]],
    anchor_cutoff_time: str | None = "20:30",
) -> tuple[list[MasterOpportunityEpisode], list[EpisodeMembership]]:
    """Cluster decision observations into independent master opportunity episodes.

    observations_by_security: dict mapping immutable_security_id -> list of observation dicts.
    outcomes_by_obs_key: dict mapping (immutable_security_id, as_of_date, cutoff_time) -> {(target_pct, horizon): OutcomeLabelRecord}.
    anchor_cutoff_time: If set (default '20:30'), only observations at this cutoff time can anchor
    master episodes, preventing 09:00 pre-market reevaluation rows from preempting primary 20:30 episodes.
    """
    episodes: list[MasterOpportunityEpisode] = []
    memberships: list[EpisodeMembership] = []

    # Process securities in deterministic alphabetical order
    sorted_sec_ids = sorted(observations_by_security.keys())

    for sec_id in sorted_sec_ids:
        obs_list = observations_by_security[sec_id]
        # Sort observations deterministically: as_of_date ASC, with anchor_cutoff_time prioritized
        sorted_obs = sorted(
            obs_list,
            key=lambda x: (
                x["as_of_date"],
                0 if x.get("cutoff_time") == (anchor_cutoff_time or "20:30") else 1,
            ),
        )

        active_episode_end_date: str | None = None

        for obs in sorted_obs:
            as_of_date = obs["as_of_date"]
            cutoff_time = obs.get("cutoff_time", "20:30")
            ticker = obs.get("ticker_at_decision", "")

            # If inside an active episode window, this observation cannot anchor a new episode
            if active_episode_end_date is not None and as_of_date <= active_episode_end_date:
                continue

            # Only primary cutoff time observations can anchor if anchor_cutoff_time is specified
            if anchor_cutoff_time and cutoff_time != anchor_cutoff_time:
                continue

            # Must be eligible and not boundary-purged
            if not obs.get("raw_outcome_eligible", False) or obs.get("split_boundary_purged", False):
                continue

            obs_key = (sec_id, as_of_date, cutoff_time)
            cell_outcomes = outcomes_by_obs_key.get(obs_key, {})
            outcome_10_21 = cell_outcomes.get((10.0, 21))

            if outcome_10_21 is None:
                continue

            # Check if this observation reached at least +10% within 21 sessions
            if outcome_10_21.mfe_pct >= 0.10 or outcome_10_21.target_progress_ratio >= 1.0:
                # This anchors a new master opportunity episode!
                # Forward 21 trading sessions
                window_sessions = get_forward_sessions(as_of_date, 21)
                window_start_date = window_sessions[0]
                window_end_date = window_sessions[-1]
                active_episode_end_date = window_end_date

                # Deterministic episode ID: EP-{immutable_security_id}-{YYYYMMDD}-{cutoff}
                date_clean = as_of_date.replace("-", "")
                cutoff_clean = cutoff_time.replace(":", "")
                episode_id = f"EP-{sec_id}-{date_clean}-{cutoff_clean}"

                outcome_20_21 = cell_outcomes.get((20.0, 21))
                outcome_30_21 = cell_outcomes.get((30.0, 21))

                max_mfe = outcome_10_21.mfe_pct
                if max_mfe >= 0.30:
                    max_tier = "30"
                elif max_mfe >= 0.20:
                    max_tier = "20"
                else:
                    max_tier = "10"

                target_session_idx = outcome_10_21.time_to_target or 1

                # Identify all constituent daily observations falling into this 21-session window
                constituent_obs = [
                    o
                    for o in sorted_obs
                    if window_start_date <= o["as_of_date"] <= window_end_date
                ]

                # Map constituent memberships
                for c_obs in constituent_obs:
                    c_date = c_obs["as_of_date"]
                    c_cutoff = c_obs.get("cutoff_time", "20:30")
                    c_ticker = c_obs.get("ticker_at_decision", ticker)

                    # Find session index (1..21) in the window
                    if c_date in window_sessions:
                        session_idx = window_sessions.index(c_date) + 1
                    else:
                        session_idx = 1

                    if session_idx < target_session_idx:
                        tag = "pre_target"
                    elif session_idx == target_session_idx:
                        tag = "target_session"
                    else:
                        tag = "post_target"

                    memberships.append(
                        EpisodeMembership(
                            immutable_security_id=sec_id,
                            as_of_date=c_date,
                            cutoff_time=c_cutoff,
                            ticker_at_decision=c_ticker,
                            episode_id=episode_id,
                            session_index_in_episode=session_idx,
                            constituent_tag=tag,
                        )
                    )

                episodes.append(
                    MasterOpportunityEpisode(
                        episode_id=episode_id,
                        anchor_security_id=sec_id,
                        anchor_ticker=ticker,
                        anchor_as_of_date=as_of_date,
                        anchor_cutoff_time=cutoff_time,
                        anchor_entry_price=outcome_10_21.reference_entry_price,
                        window_start_date=window_start_date,
                        window_end_date=window_end_date,
                        window_session_count=21,
                        max_return_pct_21=round(max_mfe, 6),
                        max_target_tier_reached=max_tier,
                        clean_target_reached_10_21=outcome_10_21.clean_target_reached,
                        clean_target_reached_20_21=bool(
                            outcome_20_21 and outcome_20_21.clean_target_reached
                        ),
                        clean_target_reached_30_21=bool(
                            outcome_30_21 and outcome_30_21.clean_target_reached
                        ),
                        first_target_session_index=outcome_10_21.time_to_target,
                        constituent_observation_count=len(constituent_obs),
                    )
                )

    # Sort episodes deterministically: anchor_as_of_date ASC, anchor_security_id ASC
    episodes.sort(key=lambda ep: (ep.anchor_as_of_date, ep.anchor_security_id))
    return episodes, memberships
