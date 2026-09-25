"""Deterministic, credential-free specification tests for DAYTRADE-001B.

Validates the machine-readable specification and human-readable contract
without accessing live market data, providers, or historical records.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES
from tradex.watchlists.presets import DOW30

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-001B-v1.json"
MD_PATH = REPO_ROOT / "docs" / "research" / "DAYTRADE-001B.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def spec() -> dict:
    assert SPEC_PATH.exists(), f"Missing spec file: {SPEC_PATH}"
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def md_content() -> str:
    assert MD_PATH.exists(), f"Missing markdown document: {MD_PATH}"
    return MD_PATH.read_text(encoding="utf-8")


def test_spec_json_parses_cleanly_and_is_json_safe(spec: dict) -> None:
    """Requirement 1: Spec JSON parses and is JSON-safe (no NaN or Infinity)."""
    serialized = json.dumps(spec, allow_nan=False, indent=2)
    assert len(serialized) > 0
    reloaded = json.loads(serialized)
    assert reloaded == spec


def test_task_id_version_and_classification(spec: dict) -> None:
    """Requirement 2: Task ID, version, and classification are correct."""
    assert spec["task_id"] == "DAYTRADE-001B"
    assert spec["spec_version"] == 1
    assert spec["classification"] == "research_only_preregistration"
    assert spec["status"] == "preregistered_not_executed"
    assert spec["base_commit_sha"] == "089be61a8ad0c5b9e7b2909dd2f3e2f3e460b03b"
    assert spec["study_type"] == "event_study"
    assert spec["direction"] == "long_side_reversal_only"


def test_production_promotion_eligibility_is_false(spec: dict) -> None:
    """Requirement 3: Production promotion eligibility is strictly false."""
    assert spec["governance"]["production_promotion_eligible"] is False


def test_dow30_frozen_symbols_match_preset(spec: dict) -> None:
    """Requirement 4: DOW30 has exactly the frozen expected 30 symbols matching presets.DOW30."""
    spec_symbols = spec["universe"]["symbols"]
    assert len(spec_symbols) == 30
    assert tuple(spec_symbols) == DOW30
    assert spec["universe"]["symbol_count"] == 30
    assert spec["universe"]["reconstitution_policy"] == "frozen_static_snapshot_no_dynamic_refresh"


def test_provider_feed_and_timeframe_contract(spec: dict) -> None:
    """Requirement 5: Provider/feed/timeframe are exactly Alpaca / SIP / 1Min."""
    contract = spec["data_contract"]
    assert contract["provider"] == "alpaca"
    assert contract["feed"] == "sip"
    assert contract["timeframe"] == "1Min"
    assert contract["adjustment"] == "split"
    assert contract["session_calendar"] == "XNYS"
    assert contract["timezone"] == "America/New_York"


def test_no_provider_or_feed_fallback_permitted(spec: dict) -> None:
    """Requirement 6: No provider fallback is permitted."""
    contract = spec["data_contract"]
    assert contract["allow_provider_fallback"] is False
    assert contract["allow_feed_fallback"] is False
    assert "iex" in contract["disallowed_fallbacks"]
    assert "yahoo" in contract["disallowed_fallbacks"]
    assert "schwab" in contract["disallowed_fallbacks"]
    assert "ibkr" in contract["disallowed_fallbacks"]
    assert contract["provider_failure_action"] == "stop_and_report_provider_or_entitlement_blocker"


def test_split_ranges_do_not_overlap(spec: dict) -> None:
    """Requirement 7: Split ranges do not overlap and are contiguous."""
    splits = spec["dates_and_splits"]
    warmup = splits["warmup"]
    dev = splits["development"]
    val = splits["validation"]
    holdout = splits["holdout"]

    assert warmup["start"] == "2024-12-02"
    assert warmup["end"] == "2025-01-01"
    assert dev["start"] == "2025-01-02"
    assert dev["end"] == "2025-06-30"
    assert val["start"] == "2025-07-01"
    assert val["end"] == "2025-09-30"
    assert holdout["start"] == "2025-10-01"
    assert holdout["end"] == "2025-12-31"

    # Strictly non-overlapping chronological ordering
    assert warmup["start"] < warmup["end"] < dev["start"]
    assert dev["start"] < dev["end"] < val["start"]
    assert val["start"] < val["end"] < holdout["start"]
    assert holdout["start"] < holdout["end"]

    assert warmup["signal_origin_prohibited"] is True
    assert splits["split_boundary_enforcement"] == "forward_outcomes_must_not_cross_split_boundaries"


def test_holdout_follows_validation(spec: dict) -> None:
    """Requirement 8: Holdout follows validation chronologically."""
    val_end = spec["dates_and_splits"]["validation"]["end"]
    holdout_start = spec["dates_and_splits"]["holdout"]["start"]
    assert holdout_start > val_end


def test_holdout_conditional_on_validation_support(spec: dict) -> None:
    """Requirement 9: Holdout access is strictly conditional on validation support."""
    holdout_rule = spec["holdout_rule"]
    assert holdout_rule["evaluation_condition"] == "validation_must_earn_supported_disposition"
    assert holdout_rule["gates_identical_to_validation"] is True
    assert holdout_rule["parameter_or_method_changes_permitted"] is False
    assert holdout_rule["action_if_validation_not_supported"] == "leave_holdout_unread_and_report"


def test_event_percentile_and_quantile_scale_explicit(spec: dict) -> None:
    """Requirement 10: Event percentile is exactly 0.1st percentile (quantile 0.001).

    Explicitly verifies scale: bottom 1/10th of 1 percent, NOT 10th percentile.
    """
    event = spec["event_definition"]
    assert event["percentile_points"] == 0.1
    assert event["quantile"] == 0.001
    # Guard against confusing 0.1st percentile with 10% (0.10)
    assert event["quantile"] != 0.10
    assert event["percentile_points"] != 10.0
    assert "0.1" in event["percentile_clarification"]
    assert "0.001" in event["percentile_clarification"]
    assert event["parameter_search_prohibited"] is True


def test_trailing_session_count(spec: dict) -> None:
    """Requirement 11: Trailing session count is exactly 20 completed regular sessions."""
    assert spec["event_definition"]["trailing_window_sessions"] == 20


def test_entry_timing_is_next_bar_open(spec: dict) -> None:
    """Requirement 12: Entry is next-bar open; same-bar and close fills prohibited."""
    timing = spec["eligibility_and_timing"]
    assert "next executable 1-minute bar open" in timing["entry_timing"]
    assert timing["same_bar_execution_prohibited"] is True
    assert timing["entry_at_event_close_prohibited"] is True
    assert timing["opening_minute_eligible"] is False
    assert timing["earliest_event_bar_start"] == "09:31"


def test_primary_endpoint_is_one_minute(spec: dict) -> None:
    """Requirement 13: Primary endpoint is 1-minute forward return."""
    primary = spec["outcomes"]["primary_endpoint"]
    assert primary["name"] == "1_minute_forward_return"
    assert primary["horizon_minutes"] == 1
    assert "primary_endpoint" in primary["role"]


def test_only_three_horizons_exist(spec: dict) -> None:
    """Requirement 14: Only 1m, 2m, and 5m forward horizons exist."""
    primary = spec["outcomes"]["primary_endpoint"]
    secondary = spec["outcomes"]["secondary_endpoints"]

    horizons = [primary["horizon_minutes"]] + [s["horizon_minutes"] for s in secondary]
    assert sorted(horizons) == [1, 2, 5]
    assert len(secondary) == 2
    assert spec["outcomes"]["grid_search_prohibited"] is True


def test_execution_friction_parameters(spec: dict) -> None:
    """Requirement 15: Primary friction is 2 bps/side with 0 and 5 bps sensitivities."""
    friction = spec["execution_friction"]
    assert friction["primary_cost_bps_per_side"] == 2.0
    assert friction["primary_cost_round_trip_bps"] == 4.0
    assert friction["sensitivity_scenarios_bps_per_side"] == [0.0, 5.0]
    assert friction["commissions_beyond_friction"] == 0.0


def test_bootstrap_configuration(spec: dict) -> None:
    """Requirement 16: Bootstrap method, count (2000), and seed (20260925) are fixed."""
    boot = spec["statistical_inference"]
    assert boot["method"] == "cluster_bootstrap_by_ticker_session"
    assert boot["bootstrap_resamples"] == 2000
    assert boot["random_seed"] == 20260925
    assert boot["confidence_level_pct"] == 95.0
    assert boot["confidence_interval_type"] == "two_sided"


def test_required_validation_gates_encoded(spec: dict) -> None:
    """Requirement 17: Required validation gates are fully encoded."""
    gates = spec["validation_gates"]

    # Sample gate: >=300 events, >=15 tickers
    assert gates["sample_gate"]["min_eligible_events"] == 300
    assert gates["sample_gate"]["min_represented_tickers"] == 15

    # Concentration gate: <=15% max ticker
    assert gates["concentration_gate"]["max_single_ticker_event_pct"] == 15.0

    # Primary net effect gate: >0 and lower CI >0 at 2 bps/side
    assert gates["primary_net_effect_gate"]["cost_basis_bps_per_side"] == 2.0
    assert gates["primary_net_effect_gate"]["mean_net_return_gt_zero"] is True
    assert gates["primary_net_effect_gate"]["ci_95_lower_bound_gt_zero"] is True

    # Baseline uplift gate: >0 and lower CI >0
    assert gates["baseline_uplift_gate"]["mean_uplift_gt_zero"] is True
    assert gates["baseline_uplift_gate"]["ci_95_lower_bound_gt_zero"] is True

    # Breadth gate: >=60% represented tickers positive mean net
    assert gates["breadth_gate"]["min_pct_represented_tickers_positive_mean_net"] == 60.0


def test_maximum_evidence_confidence_is_limited_but_usable(spec: dict) -> None:
    """Requirement 18: Maximum evidence confidence is limited_but_usable_evidence."""
    assert spec["governance"]["maximum_evidence_confidence"] == "limited_but_usable_evidence"


def test_tick_resolution_acquisition_unauthorized(spec: dict) -> None:
    """Requirement 19: Tick-resolution acquisition is strictly unauthorized."""
    assert spec["governance"]["tick_resolution_acquisition_authorized"] is False
    assert spec["future_execution_budget"]["tick_data_authorized"] is False
    assert spec["future_execution_budget"]["network_calls_authorized_in_daytrade_001b"] == 0


def test_approved_production_strategies_empty() -> None:
    """Requirement 20: APPROVED_PRODUCTION_STRATEGIES == () is strictly preserved."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_spec_hash_matches_human_readable_contract(md_content: str) -> None:
    """Specification SHA-256 matches the hash recorded in DAYTRADE-001B.md."""
    actual_hash = _sha256(SPEC_PATH)
    match = re.search(r"JSON SHA-256:\*\* `([a-f0-9]{64})`", md_content)
    assert match is not None, "JSON SHA-256 hash not found in DAYTRADE-001B.md"
    assert match.group(1) == actual_hash, (
        f"Hash mismatch: spec has {actual_hash}, markdown records {match.group(1)}"
    )


def test_data_quality_gates(spec: dict) -> None:
    """Data quality gates enforce 390 bars/session, missing/duplicate limits, and exclusion limits."""
    dq = spec["data_quality_gates"]
    assert dq["expected_regular_session_minutes"] == 390
    assert dq["synthetic_filling_or_interpolation"] == "prohibited"
    assert dq["max_ticker_session_missing_bar_rate_pct"] == 5.0
    assert dq["max_ticker_session_duplicate_bar_rate_pct"] == 1.0
    assert dq["malformed_timestamps_action"] == "fail_closed_and_report"
    assert dq["max_excluded_ticker_sessions_pct_per_split"] == 5.0


def test_baseline_specification(spec: dict) -> None:
    """Baseline compares against same-ticker, same-minute non-events in same split."""
    baseline = spec["baseline"]
    assert baseline["type"] == "same_ticker_same_minute_of_day_in_same_split"
    assert baseline["event_observations_in_baseline"] is False
    assert baseline["production_scores_or_weights_in_baseline"] is False
