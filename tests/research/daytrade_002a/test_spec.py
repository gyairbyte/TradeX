"""Deterministic, credential-free specification tests for DAYTRADE-002A.

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
from tradex.watchlists.presets import SECTOR_ETFS

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-002A-v1.json"
MD_PATH = REPO_ROOT / "docs" / "research" / "DAYTRADE-002A.md"

FROZEN_LITERAL_SECTOR_ETFS: tuple[str, ...] = (
    "XLK", "XLV", "XLF", "XLY", "XLP",
    "XLE", "XLI", "XLB", "XLU", "XLRE",
    "XLC", "SPY", "QQQ", "IWM", "DIA",
)


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
    """Requirement: Spec JSON parses and is JSON-safe (no NaN or Infinity)."""
    serialized = json.dumps(spec, allow_nan=False, indent=2)
    assert len(serialized) > 0
    reloaded = json.loads(serialized)
    assert reloaded == spec


def test_task_id_version_and_classification(spec: dict) -> None:
    """Requirement: Task ID, version, and classification are correct."""
    assert spec["task_id"] == "DAYTRADE-002A"
    assert spec["spec_version"] == 1
    assert spec["classification"] == "research_only_preregistration"
    assert spec["status"] == "preregistered_not_executed"
    assert spec["base_commit_sha"] == "0a0805fd918bb7a45bb46d29d8c3470ce0c6bf27"
    assert spec["study_type"] == "event_study"
    assert spec["direction"] == "symmetric_directional"


def test_hypothesis_generation_disclosure(spec: dict) -> None:
    """Requirement: Explicit disclosure of hypothesis generation after DAYTRADE-001."""
    disclosure = spec["hypothesis_generation_disclosure"]
    assert disclosure["conceived_after_daytrade_001"] is True
    assert disclosure["distinct_hypothesis"] is True
    assert "rejected" in disclosure["daytrade_001_reversal_status"]
    assert "inconclusive" in disclosure["daytrade_001_reversal_status"]
    assert "unread_not_acquired" in disclosure["daytrade_001_reversal_status"]

    diffs = disclosure["differences_from_daytrade_001"]
    assert len(diffs) >= 5
    assert any("Signal horizon" in d for d in diffs)
    assert any("Execution horizon" in d for d in diffs)
    assert any("Universe" in d for d in diffs)
    assert any("Timing" in d for d in diffs)
    assert any("Mechanism" in d for d in diffs)
    assert any("Holding period" in d for d in diffs)
    assert any("Dataset period" in d for d in diffs)

    assert "No 2025 observations from DAYTRADE-001" in disclosure["no_reused_evidence_rule"]
    assert disclosure["fresh_confirmatory_period"] == "2026-01-02 through 2026-08-31"


def test_frozen_universe_literal_symbols_and_count(spec: dict) -> None:
    """Clarification 2: Universe test asserts exact literal snapshot; does not depend on mutable future presets.

    The JSON symbol list is the research source of truth. The preset source provides provenance.
    """
    spec_symbols = spec["universe"]["symbols"]
    assert len(spec_symbols) == 15
    assert tuple(spec_symbols) == FROZEN_LITERAL_SECTOR_ETFS
    assert spec["universe"]["symbol_count"] == 15
    assert spec["universe"]["reconstitution_policy"] == "frozen_static_snapshot_no_dynamic_refresh"
    assert spec["universe"]["preset_source"] == "tradex.watchlists.presets.SECTOR_ETFS"
    assert spec["universe"]["snapshot_vintage"] == "2026-05"

    # Confirms that at the approved base commit, SECTOR_ETFS matches this snapshot
    assert tuple(spec_symbols) == SECTOR_ETFS

    # Confirms research source-of-truth rule is documented in spec
    assert "source of truth" in spec["universe"]["source_of_truth_rule"].lower()


def test_provider_feed_and_timeframe_contract(spec: dict) -> None:
    """Requirement: Provider/feed/timeframe are Alpaca / SIP / 1Min / split / XNYS."""
    contract = spec["data_contract"]
    assert contract["provider"] == "alpaca"
    assert contract["feed"] == "sip"
    assert contract["timeframe"] == "1Min"
    assert contract["adjustment"] == "split"
    assert contract["session_calendar"] == "XNYS"
    assert contract["timezone"] == "America/New_York"
    assert contract["regular_sessions_only"] is True
    assert contract["exclude_early_close_sessions"] is True
    assert contract["allow_provider_fallback"] is False
    assert contract["allow_feed_fallback"] is False
    assert "iex" in contract["disallowed_fallbacks"]
    assert "yahoo" in contract["disallowed_fallbacks"]
    assert "schwab" in contract["disallowed_fallbacks"]
    assert "ibkr" in contract["disallowed_fallbacks"]
    assert contract["provider_failure_action"] == "stop_and_report_provider_or_entitlement_blocker"


def test_dates_splits_and_exchange_session_adjacency(spec: dict) -> None:
    """Clarification 3: Split adjacency is exchange-session aware under XNYS, not civil-calendar contiguous.

    Examines exact locked dates, strictly non-overlapping chronological ordering, and session adjacency.
    """
    splits = spec["dates_and_splits"]
    anchor = splits["context_anchor"]
    warmup = splits["warmup"]
    dev = splits["development"]
    val = splits["validation"]
    holdout = splits["holdout"]

    assert anchor["date"] == "2025-12-31"
    assert anchor["signal_origin_prohibited"] is True
    assert anchor["event_origin_prohibited"] is True
    assert anchor["outcome_origin_prohibited"] is True

    assert warmup["start"] == "2026-01-02"
    assert warmup["end"] == "2026-01-30"
    assert warmup["signal_origin_prohibited"] is True
    assert warmup["event_origin_prohibited"] is True
    assert warmup["outcome_origin_prohibited"] is True

    assert dev["start"] == "2026-02-02"
    assert dev["end"] == "2026-04-30"

    assert val["start"] == "2026-05-01"
    assert val["end"] == "2026-06-30"

    assert holdout["start"] == "2026-07-01"
    assert holdout["end"] == "2026-08-31"

    # Strictly non-overlapping chronological ordering
    assert anchor["date"] < warmup["start"] <= warmup["end"]
    assert warmup["end"] < dev["start"] <= dev["end"]
    assert dev["end"] < val["start"] <= val["end"]
    assert val["end"] < holdout["start"] <= holdout["end"]

    # Exchange-session awareness:
    # 2026-01-01 is an exchange holiday (New Year's Day); warmup starts on next trading session 2026-01-02.
    assert warmup["start"] != "2026-01-01"
    # 2026-01-31 (Sat) and 2026-02-01 (Sun) are weekend days; dev starts on Monday 2026-02-02.
    assert dev["start"] != "2026-01-31"

    # Split boundaries must not leak
    assert splits["split_boundary_enforcement"] == "all_events_and_outcomes_must_remain_inside_target_split"
    assert "exchange-session aware" in splits["split_adjacency_notes"].lower()


def test_holdout_access_rule_conditional_on_supported(spec: dict) -> None:
    """Requirement: Holdout access is strictly conditional on validation earning supported."""
    holdout = spec["dates_and_splits"]["holdout"]
    assert holdout["access_conditional"] is True
    assert holdout["access_condition"] == "validation_must_earn_supported_disposition"
    assert "unread, unparsed, unacquired, and uninspected" in spec["dates_and_splits"]["holdout_access_rule"]


def test_signal_return_definition_and_availability(spec: dict) -> None:
    """Requirement: First-half-hour return incorporates overnight/open to 09:59 bar; available at 10:00 ET."""
    signal = spec["signal_definition"]
    assert "close(i, D, 09:59 bar)" in signal["formula"]
    assert "close(i, previous_regular_session, 15:59 bar)" in signal["formula"]
    assert signal["signal_bar_timestamp"] == "09:59"
    assert signal["signal_available_at"] == "10:00 ET"

    prohibited = signal["prohibited_information"]
    assert any("10:00 ET or later" in p for p in prohibited)
    assert any("current-day future volume" in p for p in prohibited)
    assert any("final-half-hour data" in p for p in prohibited)


def test_threshold_quantile_and_lookback(spec: dict) -> None:
    """Requirement: Threshold is 80th percentile (q=0.80) over previous 20 valid regular sessions."""
    thresh = spec["signal_definition"]["threshold_definition"]
    assert thresh["percentile"] == 80.0
    assert thresh["quantile"] == 0.80
    assert thresh["method"] == "linear"
    assert thresh["implementation"] == "numpy.quantile(history, q=0.80, method='linear')"
    assert "20 valid completed regular sessions" in thresh["history_scope"]
    assert thresh["parameter_search_prohibited"] is True

    rules = thresh["history_rules"]
    assert any("previous 20 valid completed sessions" in r for r in rules)
    assert any("current session excluded" in r for r in rules)
    assert any("no future sessions" in r for r in rules)
    assert any("calendar days cannot substitute" in r for r in rules)


def test_event_definition_and_symmetric_direction(spec: dict) -> None:
    """Requirement: Event requires abs(return) >= threshold and != 0; symmetric LONG and SHORT."""
    event = spec["event_definition"]
    assert "abs(first_half_hour_return) >= abs_threshold" in event["condition"]
    assert "first_half_hour_return != 0" in event["condition"]

    dirs = event["direction_assignment"]
    assert dirs["LONG"] == "first_half_hour_return > 0"
    assert dirs["SHORT"] == "first_half_hour_return < 0"

    assert "simultaneous" in event["simultaneous_events"].lower()


def test_execution_timing_and_locked_assumptions(spec: dict) -> None:
    """Clarification 5: Explicitly locks remaining execution assumptions and 5.5-hour information gap."""
    timing = spec["execution_and_outcomes"]["timing"]
    assert timing["signal_available_at"] == "10:00 ET"
    assert timing["entry"] == "15:30 open"
    assert timing["entry_bar_start"] == "15:30"
    assert timing["exit"] == "15:59 close"
    assert timing["exit_bar_start"] == "15:59"
    assert timing["exit_bar_end"] == "16:00 ET"
    assert "5.5 hours" in timing["information_gap"]

    # Prohibited intervening information
    assert "no information from 10:00 et through the 15:30 entry" in timing[
        "prohibited_intervening_information_use"
    ].lower()

    # Clarification 5 locked execution assumptions
    locked = spec["execution_and_outcomes"]["locked_execution_assumptions"]
    assert locked["stop_loss"] == "none"
    assert locked["take_profit"] == "none"
    assert locked["intraday_position_only"] is True
    assert locked["same_bar_entry_allowed"] is False
    assert locked["entry_after_signal"] is True
    assert locked["position_crosses_session_boundary"] is False


def test_primary_outcome_and_algebraic_equivalence(spec: dict) -> None:
    """Requirement: Primary outcome is 15:30 open -> 15:59 close signed return with algebraic equivalence."""
    endpoint = spec["execution_and_outcomes"]["outcomes"]["primary_endpoint"]
    assert endpoint["name"] == "final_half_hour_return_30m"
    assert endpoint["interval"] == "15:30 open -> 15:59 close"
    assert endpoint["long_gross_return_formula"] == "exit / entry - 1"
    assert endpoint["short_gross_return_formula"] == "1 - exit / entry"

    # Algebraic equivalence verification:
    # For entry = 100, exit = 98 (SHORT):
    # Formula 1: 1 - 98/100 = 0.02 (+2%)
    # Formula 2: sign * (exit / entry - 1) = -1 * (98/100 - 1) = -1 * (-0.02) = +0.02 (+2%)
    entry, exit_val = 100.0, 98.0
    f1 = 1.0 - (exit_val / entry)
    f2 = -1.0 * ((exit_val / entry) - 1.0)
    assert abs(f1 - f2) < 1e-12

    assert "16:00" in endpoint["session_boundary_rule"]


def test_execution_friction_parameters(spec: dict) -> None:
    """Requirement: Primary friction is 2 bps/side (4 bps round-trip) with 0 and 5 bps sensitivities."""
    friction = spec["execution_friction"]
    assert friction["primary_cost_bps_per_side"] == 2.0
    assert friction["primary_cost_round_trip_bps"] == 4.0
    assert friction["sensitivity_scenarios_bps_per_side"] == [0.0, 5.0]
    assert friction["round_trip_sensitivities_bps"] == [0.0, 10.0]
    assert friction["commissions_beyond_friction"] == 0.0


def test_matched_baseline_specification(spec: dict) -> None:
    """Requirement: Matched non-event baseline matches ticker, split, direction, and execution window."""
    baseline = spec["matched_baseline"]
    assert baseline["type"] == "same_ticker_same_split_same_direction_non_event"

    reqs = baseline["eligibility_requirements"]
    assert reqs["same_ticker"] is True
    assert reqs["same_dataset_split"] is True
    assert reqs["same_first_half_hour_sign"] is True
    assert reqs["is_non_event"] is True
    assert "abs(first_half_hour_return) < abs_threshold" in reqs["non_event_rule"]
    assert reqs["valid_regular_session"] is True
    assert reqs["complete_required_timestamps"] is True
    assert reqs["same_execution_interval"] == "15:30 open -> 15:59 close"
    assert reqs["same_friction_treatment"] is True

    assert "arithmetic mean" in baseline["reference_return_formula"].lower()
    assert "never substitute zero" in baseline["empty_baseline_rule"].lower()


def test_data_quality_gates(spec: dict) -> None:
    """Requirement: Data quality enforces 390 bars, missing/duplicate limits, required timestamps, and 5% gate."""
    dq = spec["data_quality"]
    assert dq["expected_bars_per_session"] == 390
    assert dq["max_missing_bar_rate_pct"] == 5.0
    assert dq["max_duplicate_bar_rate_pct"] == 1.0
    assert dq["synthetic_filling_or_interpolation"] == "prohibited"

    req_ts = dq["required_timestamps"]
    assert "previous_session_15:59_close" in req_ts
    assert "current_session_09:59_close" in req_ts
    assert "current_session_15:30_open" in req_ts
    assert "current_session_15:59_close" in req_ts
    assert dq["missing_required_timestamp_action"] == "ticker_session_ineligible"

    split_gate = dq["split_data_quality_gate"]
    assert split_gate["max_excluded_ticker_sessions_pct"] == 5.0
    assert split_gate["consequence_of_excess_excluded_sessions"] == "split_cannot_earn_supported"


def test_bootstrap_configuration_and_session_date_clustering(spec: dict) -> None:
    """Requirement: Bootstrap clusters by session_date (not ticker_session) with 2,000 resamples and seed 20260926."""
    boot = spec["statistical_inference"]
    assert boot["method"] == "cluster_bootstrap_by_session_date"
    assert boot["cluster_variable"] == "session_date"
    # Guard against ticker-session clustering used in single-stock studies
    assert boot["cluster_variable"] != "ticker_session"
    assert boot["bootstrap_resamples"] == 2000
    assert boot["random_seed"] == 20260926
    assert boot["confidence_level_pct"] == 95.0
    assert "two_sided" in boot["confidence_interval_type"]

    # Joint recomputation of baseline alongside events
    assert "not held fixed" in boot["joint_recomputation_rule"].lower()
    assert "non_computable" in boot["non_computable_rule"].lower()


def test_required_metrics_list(spec: dict) -> None:
    """Requirement: All required sample, return, baseline, diagnostic, and audit metrics are preregistered."""
    metrics = spec["required_metrics"]
    assert isinstance(metrics, list)
    assert len(metrics) >= 28

    # Clarification 4 metric
    assert "event_session_count" in metrics
    assert "eligible_ticker_session_count" in metrics
    assert "event_count" in metrics
    assert "represented_etf_count" in metrics
    assert "maximum_single_etf_event_concentration" in metrics
    assert "multi_signal_session_count" in metrics
    assert "multi_signal_session_rate" in metrics

    assert "mean_gross_signed_return_30m" in metrics
    assert "mean_net_signed_return_2bps" in metrics
    assert "matched_non_event_baseline_mean" in metrics
    assert "event_minus_baseline_mean" in metrics
    assert "per_etf_primary_results" in metrics
    assert "per_month_primary_results" in metrics
    assert "long_side_primary_results" in metrics
    assert "short_side_primary_results" in metrics
    assert "data_quality_summary" in metrics
    assert "provider_provenance_summary" in metrics


def test_validation_gates_encoded_including_session_support(spec: dict) -> None:
    """Clarification 4: Validation sample gate requires >= 75 events, >= 10 ETFs, AND >= 20 session dates."""
    gates = spec["validation_gates"]

    # Clarification 4: Sample gate requires all three dimensions
    sample = gates["sample_gate"]
    assert sample["min_eligible_events"] == 75
    assert sample["min_represented_etfs"] == 10
    assert sample["min_event_session_count"] == 20

    # Concentration gate
    assert gates["concentration_gate"]["max_single_etf_event_pct"] == 15.0

    # Data quality gate
    assert gates["data_quality_gate"]["max_excluded_ticker_sessions_pct"] == 5.0

    # Primary net effect gate
    net_gate = gates["primary_net_effect_gate"]
    assert net_gate["cost_basis_bps_per_side"] == 2.0
    assert net_gate["mean_net_return_gt_zero"] is True
    assert net_gate["ci_95_lower_bound_gt_zero"] is True

    # Uplift gate
    uplift_gate = gates["baseline_uplift_gate"]
    assert uplift_gate["mean_uplift_gt_zero"] is True
    assert uplift_gate["ci_95_lower_bound_gt_zero"] is True

    # Breadth gate
    assert gates["breadth_gate"]["min_pct_represented_etfs_positive_mean_net"] == 60.0


def test_deterministic_disposition_precedence_sequence(spec: dict) -> None:
    """Clarification 4: Deterministic 5-step disposition sequence includes session date sufficiency in Step 2."""
    prec = spec["disposition_precedence"]

    # Step 1: Invalidity
    assert prec["step_1_invalidity"]["disposition"] == "invalid"

    # Step 2: Evidence Sufficiency (incorporates Clarification 4)
    assert prec["step_2_evidence_sufficiency"]["disposition"] == "inconclusive"
    cond_2 = prec["step_2_evidence_sufficiency"]["condition"].lower()
    assert "75 eligible events" in cond_2
    assert "10 represented etfs" in cond_2
    assert "20 distinct event session dates" in cond_2
    assert "15.0%" in cond_2
    assert "5.0%" in cond_2

    # Step 3: Directional Hypothesis Failure
    assert prec["step_3_directional_hypothesis_failure"]["disposition"] == "rejected"
    cond_3 = prec["step_3_directional_hypothesis_failure"]["condition"].lower()
    assert "breadth gate failure" in cond_3

    # Step 4: Statistical Uncertainty
    assert prec["step_4_statistical_uncertainty"]["disposition"] == "inconclusive"

    # Step 5: Support
    assert prec["step_5_support"]["disposition"] == "supported"

    # Holdout application
    assert "holdout" in prec["holdout_application"].lower()


def test_governance_and_production_boundary(spec: dict) -> None:
    """Requirement: Evidence confidence cap is limited_but_usable_evidence; production registry is empty."""
    gov = spec["governance"]
    assert gov["maximum_evidence_confidence"] == "limited_but_usable_evidence"
    assert gov["production_promotion_eligible"] is False
    assert gov["approved_production_strategies_empty"] is True

    # Literature references are motivation only
    refs = gov["literature_references"]
    assert len(refs) == 3
    assert all(r["role"] == "motivation_only_not_proof" for r in refs)

    # Runtime registry invariant strictly preserved
    assert APPROVED_PRODUCTION_STRATEGIES == ()

    # Explicit out-of-scope list
    out_of_scope = gov["explicit_out_of_scope"]
    assert "evaluator implementation" in out_of_scope
    assert "backtest execution" in out_of_scope
    assert "production changes" in out_of_scope


def test_spec_hash_matches_human_readable_contract(md_content: str) -> None:
    """Requirement: Specification SHA-256 matches the hash recorded in DAYTRADE-002A.md."""
    actual_hash = _sha256(SPEC_PATH)
    match = re.search(r"JSON SHA-256:\*\*\s*`([a-f0-9]{64})`", md_content)
    assert match is not None, "JSON SHA-256 hash not found in DAYTRADE-002A.md"
    assert match.group(1) == actual_hash, (
        f"Hash mismatch: spec has {actual_hash}, markdown records {match.group(1)}"
    )
