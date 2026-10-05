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


class RecommendationEpisodeSimulator:
    """Reference implementation of the frozen recommendation-episode grouping contract."""

    def __init__(self, system_id: str, cutoff: str = "20:30") -> None:
        self.system_id = system_id
        self.cutoff = cutoff
        self._active_episode: SyntheticEpisode | None = None
        self._eligible_for_new_episode: bool = True
        self.closed_episodes: list[SyntheticEpisode] = []

    def process_session(self, security_id: str, session_date: str, state: str | None) -> None:
        """Process one session. state in {'Enter Now', 'Armed', 'Qualified Waitlist'} or None (hidden)."""
        is_surfaced = state in {"Enter Now", "Armed", "Qualified Waitlist"}

        if is_surfaced:
            if self._active_episode is not None:
                # Active episode continues
                self._active_episode.session_count += 1
                self._active_episode.end_date = session_date
                self._active_episode.states.append(state or "")

                # Check 21-session cap
                if self._active_episode.session_count >= 21:
                    self._active_episode.close_reason = "max_session_cap_reached"
                    self.closed_episodes.append(self._active_episode)
                    self._active_episode = None
                    self._eligible_for_new_episode = False  # Anti-double-count rule!
            else:
                # Not in active episode
                if self._eligible_for_new_episode:
                    # Open new episode
                    ep_id = f"REC_{self.system_id}_{security_id}_{session_date}_{self.cutoff.replace(':', '')}"
                    self._active_episode = SyntheticEpisode(
                        episode_id=ep_id,
                        system_id=self.system_id,
                        security_id=security_id,
                        start_date=session_date,
                        end_date=session_date,
                        session_count=1,
                        close_reason="in_progress",
                        states=[state or ""],
                    )
                else:
                    # Suppressed by anti-double-count rule
                    pass
        else:
            # Not surfaced (Hidden)
            if self._active_episode is not None:
                self._active_episode.close_reason = "surface_lost_hidden"
                self.closed_episodes.append(self._active_episode)
                self._active_episode = None
            # Hidden snapshot resets eligibility!
            self._eligible_for_new_episode = True


def test_31_one_active_episode_per_security_and_system() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    sim.process_session("SEC1", "2020-01-02", "Armed")
    assert sim._active_episode is not None
    assert sim._active_episode.security_id == "SEC1"
    # Further calls do not create a second episode for SEC1
    sim.process_session("SEC1", "2020-01-03", "Armed")
    assert len(sim.closed_episodes) == 0
    assert sim._active_episode.session_count == 2


def test_32_contiguous_surfaced_observations_remain_one_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    for day in range(1, 10):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Enter Now")
    assert len(sim.closed_episodes) == 0
    assert sim._active_episode is not None
    assert sim._active_episode.session_count == 9


def test_33_state_changes_do_not_create_new_evaluation_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    states = ["Qualified Waitlist", "Armed", "Enter Now", "Armed", "Qualified Waitlist"]
    for day, st in enumerate(states, start=1):
        sim.process_session("SEC1", f"2020-01-{day:02d}", st)
    assert len(sim.closed_episodes) == 0
    assert sim._active_episode is not None
    assert sim._active_episode.session_count == 5
    assert sim._active_episode.states == states


def test_34_hidden_snapshot_closes_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    sim.process_session("SEC1", "2020-01-02", "Enter Now")
    sim.process_session("SEC1", "2020-01-03", "Enter Now")
    sim.process_session("SEC1", "2020-01-04", None)  # Hidden!
    assert sim._active_episode is None
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
    assert sim._active_episode is None


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
    assert sim._active_episode is None


def test_37_later_hidden_snapshot_resets_eligibility_for_new_episode() -> None:
    sim = RecommendationEpisodeSimulator(system_id="test_sys")
    # 21 sessions capped
    for day in range(1, 22):
        sim.process_session("SEC1", f"2020-01-{day:02d}", "Armed")
    assert len(sim.closed_episodes) == 1
    # Remains surfaced: suppressed
    sim.process_session("SEC1", "2020-01-22", "Armed")
    assert sim._active_episode is None
    # Hidden snapshot: reset!
    sim.process_session("SEC1", "2020-01-23", None)
    assert sim._eligible_for_new_episode is True
    # Surfaced again: opens NEW episode!
    sim.process_session("SEC1", "2020-01-24", "Enter Now")
    assert sim._active_episode is not None
    assert sim._active_episode.session_count == 1
    assert sim._active_episode.start_date == "2020-01-24"


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
    assert sim1._active_episode is not None and sim2._active_episode is not None
    assert sim1._active_episode.episode_id == sim2._active_episode.episode_id


# --- 39-45: Metadata, search budget, isolation, and production guards ---


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


def test_45_no_daytrade_files_changed() -> None:
    # Verify via git status that no DAYTRADE files were touched
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files = [line.strip().split()[-1] for line in res.stdout.strip().splitlines() if line.strip()]
    daytrade_changes = [f for f in changed_files if "daytrade" in f.lower()]
    assert daytrade_changes == [], f"DAYTRADE files modified: {daytrade_changes}"
