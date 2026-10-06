"""Deterministic, credential-free contract tests for LONG-002D3B.

Validates the research amendment, frozen quantitative feature registry,
recommendation-episode evaluation grouping contract, and readiness decision.
Does not require row-level Parquet datasets or network access.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[2]

# Upstream locked specs
LONG_002_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002-v1.json"
LONG_002D1_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D1-v1.json"
LONG_002D2_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D2-v1.json"
LONG_002D3A_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D3A-v1.json"
LONG_002D3A_CORR_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D3A-CORR-001.json"

# Locked SHA-256 digests
LOCKED_HASHES = {
    "LONG-002-v1.json": "f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5",
    "LONG-002D1-v1.json": "cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381",
    "LONG-002D2-v1.json": "db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8",
    "LONG-002D3A-v1.json": "7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427",
    "LONG-002D3A-CORR-001.json": "f0c239ab934cb7435ed914a33e1224b490974218016b442cba4793a7a8f87cfe",
}

# D3B artifacts
AMENDMENT_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D-AMEND-001.json"
AMENDMENT_MD_PATH = REPO_ROOT / "docs/research/LONG-002D-AMEND-001.md"
D3B_SPEC_PATH = REPO_ROOT / "docs/research/specs/LONG-002D3B-v1.json"
D3B_REPORT_PATH = REPO_ROOT / "docs/research/LONG-002D3B-QUANTITATIVE-FREEZE.md"
FEATURE_REGISTRY_PATH = REPO_ROOT / "docs/research/artifacts/LONG-002D3B/feature_registry.json"
REC_EPISODE_CONTRACT_PATH = REPO_ROOT / "docs/research/artifacts/LONG-002D3B/recommendation_episode_contract.json"
READINESS_DECISION_PATH = REPO_ROOT / "docs/research/artifacts/LONG-002D3B/readiness_decision.json"
CHECKSUMS_PATH = REPO_ROOT / "docs/research/artifacts/LONG-002D3B/checksums.sha256"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def amendment_spec() -> dict[str, Any]:
    with AMENDMENT_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def feature_registry() -> dict[str, Any]:
    with FEATURE_REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def rec_episode_contract() -> dict[str, Any]:
    with REC_EPISODE_CONTRACT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def readiness_decision() -> dict[str, Any]:
    with READINESS_DECISION_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def long_002_spec() -> dict[str, Any]:
    with LONG_002_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def long_002d1_spec() -> dict[str, Any]:
    with LONG_002D1_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# --- 1-4: Upstream locked specifications immutability ---


def test_01_original_long_002_v1_spec_unchanged() -> None:
    assert _sha256(LONG_002_SPEC_PATH) == LOCKED_HASHES["LONG-002-v1.json"]


def test_02_long_002d1_spec_unchanged() -> None:
    assert _sha256(LONG_002D1_SPEC_PATH) == LOCKED_HASHES["LONG-002D1-v1.json"]


def test_03_long_002d2_spec_unchanged() -> None:
    assert _sha256(LONG_002D2_SPEC_PATH) == LOCKED_HASHES["LONG-002D2-v1.json"]


def test_04_long_002d3a_specs_unchanged() -> None:
    assert _sha256(LONG_002D3A_SPEC_PATH) == LOCKED_HASHES["LONG-002D3A-v1.json"]
    assert _sha256(LONG_002D3A_CORR_SPEC_PATH) == LOCKED_HASHES["LONG-002D3A-CORR-001.json"]


# --- 5-10: Amendment explicit terms and quarantine boundaries ---


def test_05_amendment_explicitly_records_human_review_waived_not_executed(
    amendment_spec: dict[str, Any],
) -> None:
    assert amendment_spec["human_blinded_review_status"] == "waived_by_gary_not_executed"
    assert amendment_spec["pilot_human_labels_collected"] is False
    assert amendment_spec["main_240_human_sample_generated"] is False
    assert amendment_spec["human_review_evidence_used_for_feature_selection"] is False
    assert amendment_spec["human_review_required_for_long_002e"] is False
    assert amendment_spec["d3a_tooling_disposition"]["tooling_status"] == "completed"
    assert amendment_spec["d3a_tooling_disposition"]["24_case_human_pilot"] == "waived_not_executed"
    assert amendment_spec["d3a_tooling_disposition"]["240_case_main_study"] == "waived_not_generated"
    assert amendment_spec["d3a_tooling_disposition"]["human_labels_collected"] == 0


def test_06_amendment_does_not_authorize_validation(amendment_spec: dict[str, Any]) -> None:
    assert amendment_spec["validation_access_authorized"] is False


def test_07_amendment_does_not_authorize_holdout(amendment_spec: dict[str, Any]) -> None:
    assert amendment_spec["holdout_access_authorized"] is False


def test_08_amendment_does_not_authorize_shadow(amendment_spec: dict[str, Any]) -> None:
    assert amendment_spec["shadow_access_authorized"] is False


def test_09_amendment_does_not_authorize_long_002e(amendment_spec: dict[str, Any]) -> None:
    assert amendment_spec["long_002e_authorized"] is False


def test_10_amendment_does_not_authorize_production_change(amendment_spec: dict[str, Any]) -> None:
    assert amendment_spec["production_change_authorized"] is False
    assert amendment_spec["production_promotion_eligible"] is False
    assert amendment_spec["approved_production_strategies"] == []


# --- 11-30: Feature registry classifications and constraints ---


def test_11_feature_registry_includes_every_d1_feature_exactly_once(
    feature_registry: dict[str, Any], long_002d1_spec: dict[str, Any]
) -> None:
    d1_feature_ids = [f["feature_id"] for f in long_002d1_spec["feature_registry"]]
    registry_features = feature_registry["features"]
    registry_feature_ids = [f["feature_id"] for f in registry_features]

    assert len(d1_feature_ids) == 15
    assert len(registry_feature_ids) == 15
    assert sorted(registry_feature_ids) == sorted(d1_feature_ids)
    assert len(set(registry_feature_ids)) == 15  # exactly once


def test_12_vam5_remains_frozen_comparator(feature_registry: dict[str, Any]) -> None:
    baseline = feature_registry["frozen_baseline_system"]
    assert baseline["system_id"] == "volatility_aware_momentum_5"
    assert baseline["final_disposition"] == "FROZEN BASELINE COMPARATOR"
    assert baseline["status"] == "frozen_comparator"
    reqs = " ".join(baseline["requirements"]).lower()
    assert "no retuning" in reqs
    assert "no weight changes" in reqs
    assert "no threshold changes" in reqs
    assert "no lookback changes" in reqs


def test_13_atr_pct_14_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "atr_pct_14")
    assert feat["final_disposition"] == "carry_core"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_14_return_5_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "return_5")
    assert feat["final_disposition"] == "baseline_component"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_15_return_20_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "return_20")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_16_return_60_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "return_60")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_17_close_vs_sma20_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "close_vs_sma20")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_18_close_vs_sma60_is_allowed(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "close_vs_sma60")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is True
    assert feat["allowed_direction"] == "HIGHER"


def test_19_sma20_slope_5_allowed_only_as_bounded_challenger_not_standalone(
    feature_registry: dict[str, Any],
) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "sma20_slope_5")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is False
    assert "multivariate" in feat["limitations"].lower()


def test_20_relative_volume_20_allowed_only_as_bounded_challenger_not_standalone(
    feature_registry: dict[str, Any],
) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "relative_volume_20")
    assert feat["final_disposition"] == "carry_bounded_challenger"
    assert feat["allowed_in_LONG_002E"] is True
    assert feat["allowed_as_standalone_ranker"] is False
    assert "not_supported" in feat["D2_evidence_summary_if_applicable"].lower()


def test_21_proximity_high20_excluded(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "proximity_high20")
    assert feat["final_disposition"] == "excluded"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_22_proximity_high60_excluded(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "proximity_high60")
    assert feat["final_disposition"] == "excluded"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_23_compression_excluded(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "true_range_compression_5_20")
    assert feat["final_disposition"] == "excluded"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_24_dollar_volume_trend_excluded(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "dollar_volume_trend_20_60")
    assert feat["final_disposition"] == "excluded"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_25_up_volume_share_excluded(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "up_volume_share_20")
    assert feat["final_disposition"] == "excluded"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_26_spy_return_20_is_context_only(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "spy_return_20")
    assert feat["final_disposition"] == "context_only"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_27_stock_minus_spy_20_is_reference_only(feature_registry: dict[str, Any]) -> None:
    feat = next(f for f in feature_registry["features"] if f["feature_id"] == "stock_minus_spy_20")
    assert feat["final_disposition"] == "reference_only"
    assert feat["allowed_in_LONG_002E"] is False
    assert feat["allowed_as_standalone_ranker"] is False


def test_28_post_hoc_pullback_is_not_in_e_registry(feature_registry: dict[str, Any]) -> None:
    allowed_features = [f["feature_id"] for f in feature_registry["features"] if f["allowed_in_LONG_002E"]]
    assert "pullback" not in " ".join(allowed_features).lower()
    assert "dip" not in " ".join(allowed_features).lower()

    post_hoc = feature_registry.get("post_hoc_findings", [])
    assert len(post_hoc) >= 1
    pb = next(p for p in post_hoc if "pullback" in p["observation_id"])
    assert pb["final_disposition"] == "separate_preregistration_required"
    assert pb["allowed_in_LONG_002E"] is False


def test_29_no_optional_fundamental_news_analyst_options_features(
    feature_registry: dict[str, Any],
) -> None:
    opt = feature_registry.get("optional_data_families", {})
    assert opt.get("allowed_in_LONG_002E") is False
    allowed_features = [f["feature_id"] for f in feature_registry["features"] if f["allowed_in_LONG_002E"]]
    prohibited_substrings = ["fundamental", "analyst", "news", "option", "short", "insider", "institutional"]
    for feat_id in allowed_features:
        for sub in prohibited_substrings:
            assert sub not in feat_id.lower()


def test_30_no_unregistered_feature_appears_as_allowed_in_long_002e(
    feature_registry: dict[str, Any],
) -> None:
    expected_allowed = {
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
        "sma20_slope_5",
        "relative_volume_20",
    }
    actual_allowed = {f["feature_id"] for f in feature_registry["features"] if f["allowed_in_LONG_002E"]}
    assert actual_allowed == expected_allowed


# --- 31-38: Recommendation-episode evaluation grouping rules ---


@dataclass
class SyntheticEpisode:
    episode_id: str
    system_id: str
    security_id: str
    start_date: str
    end_date: str
    session_count: int
    close_reason: str
    states: list[str]
    start_score_or_probability: float | None = None
    start_rank: int | None = None
    max_score_or_probability: float | None = None
    best_rank: int | None = None
    clean_target_reached_10_10: bool | None = None
    time_to_target_if_reached: int | None = None


class RecommendationEpisodeSimulator:
    """Reference implementation of the frozen recommendation-episode grouping contract.

    Tracks active episodes and anti-double-count suppression states independently
    keyed by immutable security_id.
    """

    def __init__(self, system_id: str, cutoff: str = "20:30") -> None:
        self.system_id = system_id
        self.cutoff = cutoff
        self._active_episodes: dict[str, SyntheticEpisode] = {}
        self._eligible_for_new_episode: dict[str, bool] = {}
        self.closed_episodes: list[SyntheticEpisode] = []

    def get_active_episode(self, security_id: str) -> SyntheticEpisode | None:
        return self._active_episodes.get(security_id)

    def is_eligible(self, security_id: str) -> bool:
        return self._eligible_for_new_episode.get(security_id, True)

    def process_session(
        self,
        security_id: str,
        session_date: str,
        state: str | None,
        score_or_prob: float | None = None,
        rank: int | None = None,
        clean_target_reached_10_10: bool | None = None,
        time_to_target_if_reached: int | None = None,
    ) -> None:
        """Process one session for an immutable security.
        state in {'Enter Now', 'Armed', 'Qualified Waitlist'} or None (hidden).
        """
        is_surfaced = state in {"Enter Now", "Armed", "Qualified Waitlist"}
        eligible = self._eligible_for_new_episode.get(security_id, True)

        if is_surfaced:
            if security_id in self._active_episodes:
                # Active episode continues
                ep = self._active_episodes[security_id]
                ep.session_count += 1
                ep.end_date = session_date
                ep.states.append(state or "")

                # Update trajectory descriptive diagnostics only (start predictions and outcomes remain locked)
                if score_or_prob is not None and (
                    ep.max_score_or_probability is None or score_or_prob > ep.max_score_or_probability
                ):
                    ep.max_score_or_probability = score_or_prob
                if rank is not None and (ep.best_rank is None or rank < ep.best_rank):
                    ep.best_rank = rank

                # Check 21-session cap
                if ep.session_count >= 21:
                    ep.close_reason = "max_session_cap_reached"
                    self.closed_episodes.append(ep)
                    del self._active_episodes[security_id]
                    self._eligible_for_new_episode[security_id] = False  # Anti-double-count rule!
            else:
                # Not currently in an active episode for this security
                if eligible:
                    # Open new episode: anchor primary prediction and outcome strictly to episode-start 20:30 observation
                    ep_id = f"REC_{self.system_id}_{security_id}_{session_date}_{self.cutoff.replace(':', '')}"
                    new_ep = SyntheticEpisode(
                        episode_id=ep_id,
                        system_id=self.system_id,
                        security_id=security_id,
                        start_date=session_date,
                        end_date=session_date,
                        session_count=1,
                        close_reason="in_progress",
                        states=[state or ""],
                        start_score_or_probability=score_or_prob,
                        start_rank=rank,
                        max_score_or_probability=score_or_prob,
                        best_rank=rank,
                        clean_target_reached_10_10=clean_target_reached_10_10,
                        time_to_target_if_reached=time_to_target_if_reached,
                    )
                    self._active_episodes[security_id] = new_ep
                else:
                    # Suppressed by anti-double-count rule for this security
                    pass
        else:
            # Not surfaced (Hidden)
            if security_id in self._active_episodes:
                ep = self._active_episodes[security_id]
                ep.close_reason = "surface_lost_hidden"
                self.closed_episodes.append(ep)
                del self._active_episodes[security_id]
            # Hidden snapshot resets eligibility for this security!
            self._eligible_for_new_episode[security_id] = True


def test_31_one_active_episode_per_security_and_system() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    # Day 1: Both SEC1 and SEC2 surface concurrently
    sim.process_session("SEC1", "2020-01-02", "Armed")
    sim.process_session("SEC2", "2020-01-02", "Enter Now")
    assert sim.get_active_episode("SEC1") is not None
    assert sim.get_active_episode("SEC2") is not None
    assert sim.get_active_episode("SEC1").security_id == "SEC1"
    assert sim.get_active_episode("SEC2").security_id == "SEC2"
    assert sim.get_active_episode("SEC1").episode_id != sim.get_active_episode("SEC2").episode_id

    # Day 2: SEC1 continues, SEC2 goes Hidden
    sim.process_session("SEC1", "2020-01-03", "Armed")
    sim.process_session("SEC2", "2020-01-03", None)

    # SEC1 remains active with session_count == 2, SEC2 closed independently
    assert sim.get_active_episode("SEC1") is not None
    assert sim.get_active_episode("SEC1").session_count == 2
    assert sim.get_active_episode("SEC2") is None
    assert len(sim.closed_episodes) == 1
    assert sim.closed_episodes[0].security_id == "SEC2"
    assert sim.closed_episodes[0].close_reason == "surface_lost_hidden"

    # Day 3: SEC2 resurfaces, SEC1 continues
    sim.process_session("SEC1", "2020-01-04", "Armed")
    sim.process_session("SEC2", "2020-01-04", "Enter Now")
    assert sim.get_active_episode("SEC1").session_count == 3
    assert sim.get_active_episode("SEC2") is not None
    assert sim.get_active_episode("SEC2").session_count == 1
    assert sim.get_active_episode("SEC2").start_date == "2020-01-04"


def test_32_contiguous_surfaced_observations_remain_one_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    for day in range(1, 10):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Enter Now")
    assert len(sim.closed_episodes) == 0
    ep = sim.get_active_episode("SEC1")
    assert ep is not None
    assert ep.session_count == 9


def test_33_state_changes_do_not_create_new_evaluation_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    states = ["Qualified Waitlist", "Armed", "Enter Now", "Armed", "Qualified Waitlist"]
    for day, st in enumerate(states, start=1):
        sim.process_session("SEC1", f"2020-01-{day:02d}", st)
    assert len(sim.closed_episodes) == 0
    ep = sim.get_active_episode("SEC1")
    assert ep is not None
    assert ep.session_count == 5
    assert ep.states == states


def test_34_hidden_snapshot_closes_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    sim.process_session("SEC1", "2020-01-02", "Enter Now")
    sim.process_session("SEC1", "2020-01-03", "Enter Now")
    sim.process_session("SEC1", "2020-01-04", None)  # Hidden!
    assert sim.get_active_episode("SEC1") is None
    assert len(sim.closed_episodes) == 1
    assert sim.closed_episodes[0].close_reason == "surface_lost_hidden"
    assert sim.closed_episodes[0].session_count == 2


def test_35_21_session_cap_applies() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    for day in range(1, 22):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Armed")
    assert len(sim.closed_episodes) == 1
    assert sim.closed_episodes[0].session_count == 21
    assert sim.closed_episodes[0].close_reason == "max_session_cap_reached"
    assert sim.get_active_episode("SEC1") is None


def test_36_persistent_surface_after_21_sessions_does_not_automatically_open_new_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    # 21 sessions surface
    for day in range(1, 22):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Armed")
    assert len(sim.closed_episodes) == 1
    # Day 22: still surfaced! Should NOT open new episode
    sim.process_session("SEC1", "2020-01-22", "Armed")
    sim.process_session("SEC1", "2020-01-23", "Armed")
    assert len(sim.closed_episodes) == 1
    assert sim.get_active_episode("SEC1") is None


def test_37_later_hidden_snapshot_resets_eligibility_for_new_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    # 21 sessions capped
    for day in range(1, 22):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Armed")
    assert len(sim.closed_episodes) == 1
    # Remains surfaced: suppressed
    sim.process_session("SEC1", "2020-01-22", "Armed")
    assert sim.get_active_episode("SEC1") is None
    # Hidden snapshot: reset!
    sim.process_session("SEC1", "2020-01-23", None)
    assert sim.is_eligible("SEC1") is True
    # Surfaced again: opens NEW episode!
    sim.process_session("SEC1", "2020-01-24", "Enter Now")
    assert sim.get_active_episode("SEC1") is not None
    assert sim.get_active_episode("SEC1").session_count == 1
    assert sim.get_active_episode("SEC1").start_date == "2020-01-24"


def test_38_episode_grouping_is_deterministic() -> None:
    sim1 = RecommendationEpisodeSimulator(system_id="model_v1")
    sim2 = RecommendationEpisodeSimulator(system_id="model_v1")

    history = [
        ("2020-01-02", "Armed"),
        ("2020-01-03", "Enter Now"),
        ("2020-01-04", None),
        ("2020-01-05", "Qualified Waitlist"),
        ("2020-01-06", "Armed"),
    ]
    for d, s in history:
        sim1.process_session("SEC1", d, s)
        sim2.process_session("SEC1", d, s)

    assert [ep.episode_id for ep in sim1.closed_episodes] == [ep.episode_id for ep in sim2.closed_episodes]
    ep1 = sim1.get_active_episode("SEC1")
    ep2 = sim2.get_active_episode("SEC1")
    assert ep1 is not None and ep2 is not None
    assert ep1.episode_id == ep2.episode_id


# --- 39-48: Metadata, search budget, isolation, and production guards ---


def test_39_primary_evaluation_cutoff_is_20_30(rec_episode_contract: dict[str, Any]) -> None:
    snap = rec_episode_contract["snapshot_specification"]
    assert snap["primary_cutoff_time"] == "20:30"
    assert snap["timezone"] == "America/New_York"
    assert snap["calendar"] == "XNYS"


def test_40_master_opportunity_episode_and_recommendation_episode_are_distinct(
    rec_episode_contract: dict[str, Any],
) -> None:
    diff = rec_episode_contract["conceptual_distinctions"]["stage_c_master_opportunity_episodes"].lower()
    assert "ex-post" in diff or "ground-truth" in diff
    assert "distinct" in rec_episode_contract["conceptual_distinctions"]["stage_c_master_opportunity_episodes"].lower() or "grouping" in diff


def test_41_e_search_budget_remains_lte_48(long_002_spec: dict[str, Any]) -> None:
    budget = long_002_spec["allowed_model_families"]["search_budget"]
    assert budget["initial_total_max"] == 48
    assert budget["round_1"]["max_total_material_configurations"] == 36
    assert budget["round_2"]["max_additional_material_configurations_across_all_families"] == 12


def test_42_allowed_model_families_remain_exactly_bounded(long_002_spec: dict[str, Any]) -> None:
    families = {f["id"] for f in long_002_spec["allowed_model_families"]["allowlist"]}
    assert families == {
        "cross_sectional_rank_score",
        "regularized_probabilistic_time_to_event",
        "shallow_strongly_regularized_gbdt",
    }


def test_43_no_row_level_empirical_input_required_for_this_task() -> None:
    # All D3B test assertions evaluate purely committed JSON/Markdown specifications
    assert FEATURE_REGISTRY_PATH.is_file()
    assert REC_EPISODE_CONTRACT_PATH.is_file()
    assert READINESS_DECISION_PATH.is_file()
    assert AMENDMENT_SPEC_PATH.is_file()


def test_44_approved_production_strategies_is_empty() -> None:
    assert APPROVED_PRODUCTION_STRATEGIES == ()


LONG_002D3B_APPROVED_BASE = "770a1a66382351dd63b9245c50bed0c1d92f3ca1"
LONG_002D3B_IMPLEMENTATION_HEAD = "c8fcef5afc490147c3dd4143616ae8d22c0b585f"


def _commit_exists(sha: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).returncode == 0


def _ensure_commit(sha: str) -> bool:
    if _commit_exists(sha):
        return True
    # In shallow CI environments, attempt bounded fetch of exact SHA
    subprocess.run(
        ["git", "fetch", "--depth=1", "origin", sha],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if _commit_exists(sha):
        return True
    # If still missing, attempt fetching bounded main history
    subprocess.run(
        ["git", "fetch", "--depth=100", "origin", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return _commit_exists(sha)


def test_45_no_daytrade_files_changed() -> None:
    """Historical audit invariant: verify PR #97 / LONG-002D3B itself changed zero DAYTRADE files.

    This test checks that the immutable historical commit range of LONG-002D3B
    (base 770a1a66382351dd63b9245c50bed0c1d92f3ca1 to implementation head
    c8fcef5afc490147c3dd4143616ae8d22c0b585f) did not touch any DAYTRADE files.

    It scopes the check strictly to that historical task commit range rather than
    comparing against current HEAD. This proves LONG-002D3B task isolation without
    falsely asserting that no DAYTRADE work may ever occur in subsequent tasks/PRs.
    """
    # Fail closed if required historical commits cannot be obtained
    assert _ensure_commit(LONG_002D3B_APPROVED_BASE), (
        f"Required historical base commit {LONG_002D3B_APPROVED_BASE} could not be resolved."
    )
    assert _ensure_commit(LONG_002D3B_IMPLEMENTATION_HEAD), (
        f"Required historical implementation head commit {LONG_002D3B_IMPLEMENTATION_HEAD} could not be resolved."
    )

    # Diff between the two immutable commits; fallback to direct tree diff if shallow clone lacks merge base
    res = subprocess.run(
        ["git", "diff", "--name-only", f"{LONG_002D3B_APPROVED_BASE}...{LONG_002D3B_IMPLEMENTATION_HEAD}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        res = subprocess.run(
            ["git", "diff", "--name-only", LONG_002D3B_APPROVED_BASE, LONG_002D3B_IMPLEMENTATION_HEAD],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    assert res.returncode == 0, (
        f"Failed to compute git diff between {LONG_002D3B_APPROVED_BASE} and {LONG_002D3B_IMPLEMENTATION_HEAD}: {res.stderr}"
    )

    changed_files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
    assert len(changed_files) > 0, "Expected non-empty set of files changed in LONG-002D3B task."

    daytrade_changes = [f for f in changed_files if "daytrade" in f.lower()]
    assert daytrade_changes == [], (
        f"DAYTRADE files were modified in historical LONG-002D3B task ({LONG_002D3B_APPROVED_BASE}..{LONG_002D3B_IMPLEMENTATION_HEAD}): {daytrade_changes}"
    )


def test_45_historical_scope_regression_proof() -> None:
    """Regression proof for TEST-004: test_45 is historical-scoped and active.

    Demonstrates that:
    1. The detection logic actively flags any path containing 'daytrade' (not a no-op).
    2. The historical LONG-002D3B task range contains zero DAYTRADE changes.
    3. The post-PR97 repository history (such as PR #98 on main) does contain legitimate
       DAYTRADE changes, proving that scoping to the historical commit range rather than
       current HEAD is strictly necessary and sufficient.
    """
    # 1. Verify detection logic actively catches daytrade files
    sample_files = [
        "docs/research/LONG-002D-AMEND-001.md",
        "tradex/research/daytrade_momentum/study.py",
        "docs/research/artifacts/DAYTRADE-002C-v1/development/metrics.json",
    ]
    detected = [f for f in sample_files if "daytrade" in f.lower()]
    assert len(detected) == 2
    assert "tradex/research/daytrade_momentum/study.py" in detected

    # 2. Verify historical range has zero daytrade files
    res = subprocess.run(
        ["git", "diff", "--name-only", LONG_002D3B_APPROVED_BASE, LONG_002D3B_IMPLEMENTATION_HEAD],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    hist_files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
    assert [f for f in hist_files if "daytrade" in f.lower()] == []

    # 3. Verify that changes between LONG base and current main indeed contain legitimate DAYTRADE files
    res_main = subprocess.run(
        ["git", "diff", "--name-only", LONG_002D3B_APPROVED_BASE, "origin/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if res_main.returncode == 0:
        main_files = [line.strip() for line in res_main.stdout.strip().splitlines() if line.strip()]
        main_daytrade = [f for f in main_files if "daytrade" in f.lower()]
        assert len(main_daytrade) > 0, (
            "Expected legitimate post-PR97 DAYTRADE changes to exist between approved base and origin/main."
        )


def test_46_primary_outcome_anchored_to_episode_start_no_post_start_pooling(
    rec_episode_contract: dict[str, Any],
) -> None:
    # Verify contract outcome specification
    outcome_sem = rec_episode_contract["outcome_semantics"]
    assert outcome_sem["primary_outcome_anchor"] == "episode_start_observation"
    assert "never" in outcome_sem["prohibition_of_post_start_pooling"].lower()
    assert "start" in outcome_sem["definition"].lower()

    # Simulator behavioral check: outcome must NOT be pooled/OR'd across constituent snapshots
    sim = RecommendationEpisodeSimulator(system_id="rank_model_1")
    # Day 1: Episode opens. Start observation has clean_target_reached = False, score = 0.75, rank = 5
    sim.process_session(
        "SEC1",
        "2020-01-02",
        "Armed",
        score_or_prob=0.75,
        rank=5,
        clean_target_reached_10_10=False,
        time_to_target_if_reached=None,
    )
    # Day 2: Continued observation has favorable outcome (True), higher score (0.95), best rank (1)
    sim.process_session(
        "SEC1",
        "2020-01-03",
        "Enter Now",
        score_or_prob=0.95,
        rank=1,
        clean_target_reached_10_10=True,
        time_to_target_if_reached=3,
    )
    # Day 3: Closes
    sim.process_session("SEC1", "2020-01-04", None)

    ep = sim.closed_episodes[0]
    # Primary outcome must remain strictly anchored to start observation (False, not pooled/OR'd)
    assert ep.clean_target_reached_10_10 is False
    assert ep.time_to_target_if_reached is None
    # Primary prediction fields remain anchored to start observation
    assert ep.start_score_or_probability == 0.75
    assert ep.start_rank == 5
    # Descriptive trajectory fields record the maximums
    assert ep.max_score_or_probability == 0.95
    assert ep.best_rank == 1


def test_47_primary_prediction_fields_specified_and_descriptive_fields_restricted(
    rec_episode_contract: dict[str, Any],
) -> None:
    pred_sem = rec_episode_contract["prediction_fields_semantics"]
    assert pred_sem["primary_prediction_fields"] == ["start_score_or_probability", "start_rank"]
    assert "start_score_or_probability" in pred_sem["primary_prediction_rule"]
    assert "start_rank" in pred_sem["primary_prediction_rule"]
    assert "max_score_or_probability" in pred_sem["descriptive_fields"]
    assert "best_rank" in pred_sem["descriptive_fields"]
    assert "prohibited" in pred_sem["descriptive_fields_restriction"].lower()

    tracked = rec_episode_contract["tracked_fields"]
    required_fields = [
        "recommendation_episode_id",
        "system_id",
        "immutable_security_id",
        "start_date",
        "end_date",
        "start_state",
        "terminal_state",
        "episode_session_count",
        "close_reason",
        "start_score_or_probability",
        "start_rank",
        "max_score_or_probability",
        "best_rank",
        "clean_target_reached_10_10",
        "time_to_target_if_reached",
    ]
    for rf in required_fields:
        assert rf in tracked


def test_48_auditability_of_freeze_and_decision_dates(
    feature_registry: dict[str, Any],
    rec_episode_contract: dict[str, Any],
    readiness_decision: dict[str, Any],
) -> None:
    # Verify date-only auditability fields
    assert feature_registry.get("frozen_on") == "2026-10-05"
    assert "frozen_at_utc" not in feature_registry

    assert rec_episode_contract.get("frozen_on") == "2026-10-05"
    assert "frozen_at_utc" not in rec_episode_contract

    assert readiness_decision.get("decision_date") == "2026-10-05"
    assert "decision_timestamp_utc" not in readiness_decision
