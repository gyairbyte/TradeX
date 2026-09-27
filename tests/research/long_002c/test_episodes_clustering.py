"""Tests for non-recursive 21-session master opportunity episode clustering."""
from __future__ import annotations

from tradex.research.long_002c.episodes import cluster_master_episodes
from tradex.research.long_002c.models import OutcomeLabelRecord


def _dummy_outcome(
    sec_id: str,
    date: str,
    cutoff: str,
    mfe_pct: float,
    clean: bool = True,
    time_to_target: int = 5,
) -> OutcomeLabelRecord:
    return OutcomeLabelRecord(
        immutable_security_id=sec_id,
        as_of_date=date,
        cutoff_time=cutoff,
        target_pct=10.0,
        horizon_sessions=21,
        ticker_at_decision="TEST",
        reference_entry_price=100.0,
        entry_friction_bps=10.0,
        target_price=110.0,
        adverse_barrier_pct=0.05,
        adverse_barrier_price=95.0,
        clean_risk_cap_pct=0.05,
        clean_risk_cap_amount=5.0,
        mfe_pct=mfe_pct,
        target_progress_ratio=mfe_pct / 0.10,
        near_miss=False,
        partial_move=False,
        mae_pct=0.02,
        mae_atr=1.0,
        adverse_excursion=False,
        clean_target_reached=clean,
        path_sequence_ambiguous=False,
        end_of_horizon_return=mfe_pct * 0.8,
        retention_ratio=0.8,
        sustained_target=True,
        time_to_target=time_to_target,
        time_to_mae=2,
    )


def test_master_episode_anchoring_and_window() -> None:
    """Earliest qualifying +10%/21 observation anchors episode; next observation within 21 sessions cannot anchor."""
    sec_id = "TEST_SEC"
    # Create observations on consecutive sessions
    dates = [
        "2016-01-04",
        "2016-01-05",
        "2016-01-06",
        "2016-01-07",
        "2016-01-08",
        "2016-01-11",
    ]
    obs_list = [
        {
            "immutable_security_id": sec_id,
            "ticker_at_decision": "TEST",
            "as_of_date": d,
            "cutoff_time": "20:30",
            "as_traded_close": 100.0,
            "raw_outcome_eligible": True,
            "universe_eligible": True,
            "split_boundary_purged": False,
        }
        for d in dates
    ]
    obs_by_sec = {sec_id: obs_list}

    # Both Jan 04 and Jan 05 reached +10%/21
    outcomes_map = {
        (sec_id, "2016-01-04", "20:30"): {(10.0, 21): _dummy_outcome(sec_id, "2016-01-04", "20:30", 0.15)},
        (sec_id, "2016-01-05", "20:30"): {(10.0, 21): _dummy_outcome(sec_id, "2016-01-05", "20:30", 0.18)},
    }

    episodes, memberships = cluster_master_episodes(obs_by_sec, outcomes_map)

    # Strictly 1 master episode should be anchored (Jan 04 anchors; Jan 05 is inside the 21-session window)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.anchor_as_of_date == "2016-01-04"
    assert ep.episode_id == "EP-TEST_SEC-20160104-2030"
    assert ep.window_session_count == 21

    # Jan 05 is a constituent observation
    jan_05_memberships = [m for m in memberships if m.as_of_date == "2016-01-05"]
    assert len(jan_05_memberships) == 1
    assert jan_05_memberships[0].episode_id == ep.episode_id


def test_constituent_tags() -> None:
    """Constituent observations are tagged pre_target, target_session, post_target."""
    sec_id = "TEST_SEC"
    # Target reached on session 3 (Jan 06)
    dates = ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07"]
    obs_list = [
        {
            "immutable_security_id": sec_id,
            "ticker_at_decision": "TEST",
            "as_of_date": d,
            "cutoff_time": "20:30",
            "as_traded_close": 100.0,
            "raw_outcome_eligible": True,
            "universe_eligible": True,
            "split_boundary_purged": False,
        }
        for d in dates
    ]
    obs_by_sec = {sec_id: obs_list}

    # time_to_target = 2 in window (i.e. session index 2 in window = 2016-01-06)
    dummy_out = _dummy_outcome(sec_id, "2016-01-04", "20:30", 0.12, time_to_target=2)
    # Target hit on 2nd session of window (2016-01-06)
    outcomes_map = {
        (sec_id, "2016-01-04", "20:30"): {(10.0, 21): dummy_out},
    }

    episodes, memberships = cluster_master_episodes(obs_by_sec, outcomes_map)
    assert len(episodes) == 1

    tags_by_date = {m.as_of_date: m.constituent_tag for m in memberships}
    # Window starts next session: 2016-01-05 is session 1, 2016-01-06 is session 2 (time_to_target), 2016-01-07 is session 3
    assert tags_by_date.get("2016-01-05") == "pre_target"
    assert tags_by_date.get("2016-01-06") == "target_session"
    assert tags_by_date.get("2016-01-07") == "post_target"
