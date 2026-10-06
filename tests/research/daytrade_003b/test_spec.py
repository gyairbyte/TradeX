"""Deterministic, credential-free specification tests for DAYTRADE-003B.

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

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-003B-ORB-v1.json"
MD_PATH = REPO_ROOT / "docs" / "research" / "DAYTRADE-003B-ORB.md"


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


def test_task_id_strategy_id_and_classification(spec: dict) -> None:
    """Requirement: Task ID, strategy ID, version, and classification are correct."""
    assert spec["task_id"] == "DAYTRADE-003B-ORB-PREREG-001"
    assert spec["strategy_id"] == "DAYTRADE-003B-ORB-SIP5M"
    assert spec["spec_version"] == 1
    assert spec["classification"] == "research_only_preregistration"
    assert spec["status"] == "preregistered_not_executed"
    assert spec["base_commit_sha"] == "b15015cb46adf5ceca707589455fc12fbca64c63"


def test_governance_invariants(spec: dict) -> None:
    """Requirement: All governance authorization flags are strictly False and registry is empty."""
    gov = spec["governance"]
    assert gov["implementation_authorized"] is False
    assert gov["dataset_construction_authorized"] is False
    assert gov["provider_calls_authorized"] is False
    assert gov["empirical_execution_authorized"] is False
    assert gov["holdout_access_authorized"] is False
    assert gov["production_promotion_authorized"] is False
    assert gov["approved_production_strategies_empty"] is True
    assert gov["external_evidence_not_confirmatory"] is True
    assert gov["tick_infrastructure_required"] is False


def test_approved_production_strategies_empty() -> None:
    """Requirement: APPROVED_PRODUCTION_STRATEGIES == () is strictly preserved."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_source_citation_and_prior_evidence_period(spec: dict) -> None:
    """Requirement: Primary source is Zarattini et al. (2024) and prior period ends 2023-12-31."""
    citation = spec["source_citation"]
    paper = citation["primary_paper"]
    assert "Carlo Zarattini" in paper["authors"]
    assert "Andrea Barbon" in paper["authors"]
    assert "Andrew Aziz" in paper["authors"]
    assert paper["ssrn_id"] == "4729284"
    assert paper["publication_year"] == 2024
    assert paper["series"] == "Swiss Finance Institute Research Paper No. 24-98"

    assert len(citation["secondary_corroboration"]) >= 2
    assert any("QuantConnect" in s["source"] for s in citation["secondary_corroboration"])

    evidence_period = spec["source_evidence_period"]
    assert evidence_period["start_date"] == "2016-01-01"
    assert evidence_period["end_date"] == "2023-12-31"


def test_opening_range_duration_and_availability(spec: dict) -> None:
    """Requirement: 5-minute opening range available only at 09:35:00 ET."""
    mech = spec["strategy_mechanics"]
    op_range = mech["opening_range"]
    assert op_range["duration_minutes"] == 5
    assert op_range["minute_bars"] == ["09:30", "09:31", "09:32", "09:33", "09:34"]
    assert "09:35:00" in op_range["availability_timestamp"]
    assert op_range["pre_completion_decision_prohibited"] is True


def test_direction_qualification_and_doji_rule(spec: dict) -> None:
    """Requirement: Direction follows opening candle; doji results in NO ORDER."""
    dir_rules = spec["strategy_mechanics"]["direction_qualification"]
    assert "OR_close > OR_open" in dir_rules["bullish_condition"]
    assert dir_rules["bullish_direction"] == "LONG"
    assert dir_rules["bullish_entry_stop_level"] == "OR_high"

    assert "OR_close < OR_open" in dir_rules["bearish_condition"]
    assert dir_rules["bearish_direction"] == "SHORT"
    assert dir_rules["bearish_entry_stop_level"] == "OR_low"

    assert "OR_close == OR_open" in dir_rules["doji_condition"]
    assert dir_rules["doji_action"] == "NO_ORDER"
    assert dir_rules["bidirectional_same_symbol_session_prohibited"] is True


def test_basic_eligibility_filters(spec: dict) -> None:
    """Requirement: Price > $5, 14-session ADV >= 1,000,000 shares, ATR14 > $0.50."""
    filters = spec["eligibility_filters"]
    price_f = filters["price_filter"]
    assert price_f["metric"] == "opening_price"
    assert price_f["operator"] == "gt"
    assert price_f["threshold"] == 5.0

    vol_f = filters["average_daily_volume_filter"]
    assert vol_f["metric"] == "average_daily_volume"
    assert vol_f["lookback_trading_sessions"] == 14
    assert vol_f["operator"] == "gte"
    assert vol_f["threshold"] == 1000000
    assert vol_f["current_session_excluded"] is True

    atr_f = filters["atr_filter"]
    assert atr_f["metric"] == "average_true_range"
    assert atr_f["lookback_trading_sessions"] == 14
    assert atr_f["operator"] == "gt"
    assert atr_f["threshold"] == 0.50
    assert atr_f["current_session_excluded"] is True


def test_relative_volume_formula_lookback_and_ranking(spec: dict) -> None:
    """Requirement: RV uses first 5m volume, 14 prior sessions, RV >= 1.0, Top 20 ranking."""
    rv = spec["relative_volume_ranking"]
    assert rv["lookback_sessions"] == 14
    assert "opening_range_volume" in rv["numerator"]
    assert "mean" in rv["denominator"]
    assert rv["current_session_in_trailing_reference"] is False
    assert rv["threshold_operator"] == "gte"
    assert rv["threshold_value"] == 1.0
    assert rv["top_n_selection"] == 20
    assert rv["selection_order"] == "descending_by_relative_volume"
    assert "higher_relative_volume" in rv["deterministic_tie_breaker"]
    assert "ticker_ascending" in rv["deterministic_tie_breaker"]


def test_stop_loss_and_exit_rules(spec: dict) -> None:
    """Requirement: Stop distance = 0.10 * ATR14, EOD exit, no overnight hold, no profit target."""
    stop_rules = spec["strategy_mechanics"]["stop_loss"]
    assert "0.10 * ATR14" in stop_rules["long_stop_formula"]
    assert "0.10 * ATR14" in stop_rules["short_stop_formula"]
    assert stop_rules["trailing_stop_authorized"] is False
    assert stop_rules["breakeven_adjustment_authorized"] is False
    assert stop_rules["profit_target_authorized"] is False
    assert stop_rules["alternative_stops_authorized"] is False

    exit_rules = spec["strategy_mechanics"]["exit_rules"]
    assert "stop" in exit_rules["stop_hit_exit"].lower()
    assert "regular trading session" in exit_rules["session_close_exit"].lower()
    assert exit_rules["overnight_holds_permitted"] is False
    assert "15:59-16:00" in exit_rules["one_minute_eod_convention"]


def test_dates_and_splits(spec: dict) -> None:
    """Requirement: Warmup = 2023-12, Dev = 2024, Val = 2025, Holdout = 2026-01-02..2026-09-30."""
    splits = spec["dates_and_splits"]
    warmup = splits["warmup"]
    assert warmup["start"] == "2023-12-01"
    assert warmup["end"] == "2023-12-29"
    assert warmup["signal_origin_prohibited"] is True
    assert warmup["trade_origin_prohibited"] is True

    dev = splits["development"]
    assert dev["start"] == "2024-01-02"
    assert dev["end"] == "2024-12-31"
    assert dev["parameter_tuning_prohibited"] is True

    val = splits["validation"]
    assert val["start"] == "2025-01-02"
    assert val["end"] == "2025-12-31"

    holdout = splits["holdout"]
    assert holdout["start"] == "2026-01-02"
    assert holdout["end"] == "2026-09-30"
    assert "October 2026 excluded" in holdout["exclusion_note"]
    assert "SUPPORTED" in holdout["quarantine_rule"]


def test_holdout_access_rule(spec: dict) -> None:
    """Requirement: Holdout only accessible if validation is SUPPORTED."""
    rule = spec["holdout_access_rule"]
    assert rule["permitted_validation_disposition"] == "SUPPORTED"
    assert "PROMISING_NOT_CONFIRMED" in rule["prohibited_validation_dispositions"]
    assert "NOT_SUPPORTED" in rule["prohibited_validation_dispositions"]
    assert "INCONCLUSIVE" in rule["prohibited_validation_dispositions"]
    assert "INVALID" in rule["prohibited_validation_dispositions"]


def test_disposition_taxonomy_and_promising_not_confirmed(spec: dict) -> None:
    """Requirement: Disposition taxonomy includes PROMISING_NOT_CONFIRMED distinct from SUPPORTED."""
    tax = spec["disposition_taxonomy"]
    assert "INVALID" in tax
    assert "INCONCLUSIVE" in tax
    assert "NOT_SUPPORTED" in tax
    assert "PROMISING_NOT_CONFIRMED" in tax
    assert "SUPPORTED" in tax
    assert tax["PROMISING_NOT_CONFIRMED"] != tax["SUPPORTED"]


def test_validation_decision_gates(spec: dict) -> None:
    """Requirement: Validation decision gates encode integrity, sufficiency, economics, and bootstrap CI."""
    gates = spec["validation_gates"]
    assert gates["integrity_gate"]["failure_disposition"] == "INVALID"

    suff = gates["evidence_sufficiency_gate"]
    assert suff["min_regular_sessions_with_candidates"] == 100
    assert suff["min_triggered_trades_total"] == 500
    assert suff["min_unique_securities_traded"] == 50
    assert suff["failure_disposition"] == "INCONCLUSIVE"

    econ = gates["primary_economics_gate"]
    assert econ["condition"] == "gt_zero"
    assert econ["failure_disposition"] == "NOT_SUPPORTED"

    stat = gates["statistical_confidence_gate"]
    assert stat["condition"] == "ci_95_lower_bound_gt_zero"
    assert stat["failure_disposition_when_point_estimate_positive"] == "PROMISING_NOT_CONFIRMED"


def test_execution_model_rules(spec: dict) -> None:
    """Requirement: Execution model encodes gap-through, same-bar worst case, and immediate stop activation."""
    model = spec["execution_model"]
    assert "open" in model["stop_entry_gap_through"]["rule"].lower()
    assert "worse" in model["stop_loss_gap_through"]["rule"].lower()
    assert model["same_bar_entry_and_stop"]["favorable_ordering_permitted"] is False
    assert model["same_bar_entry_and_stop"]["diagnostic_metric"] == "same_bar_ambiguity_count"
    assert "immediately" in model["stop_activation_timing"]["rule"].lower()


def test_friction_and_cost_scenarios(spec: dict) -> None:
    """Requirement: Three distinct cost scenarios (Source A, TradeX B, Stress C)."""
    scenarios = spec["friction_and_cost_scenarios"]
    scen_a = scenarios["scenario_a_source_comparison"]
    assert scen_a["commission_per_share_usd"] == 0.0035
    assert scen_a["adverse_slippage_bps_per_side"] == 0.0

    scen_b = scenarios["scenario_b_tradex_primary"]
    assert scen_b["commission_per_share_usd"] == 0.0035
    assert scen_b["adverse_slippage_bps_per_side"] == 2.0

    scen_c = scenarios["scenario_c_stress"]
    assert scen_c["commission_per_share_usd"] == 0.0035
    assert scen_c["adverse_slippage_bps_per_side"] == 5.0


def test_parameter_fishing_prohibitions_explicit(spec: dict) -> None:
    """Requirement: Strict prohibition of parameter searches, grids, or alternative indicator additions."""
    prohibitions = spec["parameter_fishing_prohibitions"]
    assert len(prohibitions) >= 10
    assert any("opening range duration" in p.lower() for p in prohibitions)
    assert any("top 20" in p.lower() for p in prohibitions)
    assert any("relative volume" in p.lower() for p in prohibitions)
    assert any("atr" in p.lower() for p in prohibitions)
    assert any("vwap" in p.lower() for p in prohibitions)
    assert any("profit target" in p.lower() for p in prohibitions)
    assert any("trailing stop" in p.lower() for p in prohibitions)


def test_unresolved_source_ambiguities_registered(spec: dict) -> None:
    """Requirement: Unresolved source ambiguities are explicitly cataloged with AMB identifiers."""
    ambiguities = spec["unresolved_source_ambiguities"]
    assert len(ambiguities) >= 10
    topics = [a["topic"].lower() for a in ambiguities]
    assert any("universe" in t for t in topics)
    assert any("atr smoothing" in t for t in topics)
    assert any("sizing" in t for t in topics)
    assert any("lifetime" in t or "cancellation" in t for t in topics)
    assert any("resolution" in t for t in topics)
    assert any("gap-through" in t for t in topics)
    assert any("same-bar" in t for t in topics)
    assert any("liquidation" in t or "eod" in t for t in topics)
    assert any("commission" in t for t in topics)
    assert any("corporate action" in t for t in topics)


def test_no_tick_data_dependency(spec: dict) -> None:
    """Requirement: Tick-resolution data is explicitly prohibited and unneeded."""
    assert spec["governance"]["tick_infrastructure_required"] is False
    prohibited = spec["data_contract"]["unnecessary_and_prohibited_data_classes"]
    assert "raw_trade_ticks" in prohibited
    assert "50_tick_bars" in prohibited
    assert "133_tick_bars" in prohibited


def test_spec_hash_matches_human_readable_contract(md_content: str) -> None:
    """Specification SHA-256 matches the hash recorded in DAYTRADE-003B-ORB.md."""
    actual_hash = _sha256(SPEC_PATH)
    match = re.search(r"Spec JSON SHA-256:\*\* `([a-f0-9]{64})`", md_content)
    assert match is not None, "Spec JSON SHA-256 hash not found in DAYTRADE-003B-ORB.md"
    assert match.group(1) == actual_hash, (
        f"Hash mismatch: spec has {actual_hash}, markdown records {match.group(1)}"
    )
