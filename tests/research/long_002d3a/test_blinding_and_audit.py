"""Blinding, price normalization, and leakage audit tests for LONG-002D3A."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from tradex.research.long_002d3a.audit import audit_single_case
from tradex.research.long_002d3a.blinder import (
    get_market_cap_cohort,
)
from tradex.research.long_002d3a.models import AnswerKeyRecord


@pytest.fixture
def clean_test_case() -> tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]:
    """Create a minimal valid blinded Stage A packet, Stage B packet, and AnswerKeyRecord."""
    bars = []
    for i in range(-60, 1):
        label = "T0" if i == 0 else f"T{i}"
        bars.append({
            "relative_index": i,
            "relative_label": label,
            "normalized_open": 100.0 + i * 0.1,
            "normalized_high": 101.0 + i * 0.1,
            "normalized_low": 99.0 + i * 0.1,
            "normalized_close": 100.5 + i * 0.1,
            "relative_volume": 1.1,
            "normalized_sma20": 100.0,
            "normalized_sma50": 98.0,
            "atr_pct_14": 2.5,
        })

    stage_a = {
        "case_id": "D3A-PILOT-001",
        "relative_bars": bars,
        "technical_metrics": {
            "pre_decision_normalized_close_t0": 100.5,
            "return_5_bars_pct": 1.2,
            "return_20_bars_pct": 3.4,
            "relative_volume_t0": 1.1,
            "atr_pct_14_t0": 2.5,
        },
        "spy_context": {
            "spy_return_20_bars_pct": 2.0,
            "stock_minus_spy_20_bars_pct": 1.4,
            "benchmark": "SPY",
        },
        "data_quality_warnings": [],
    }

    stage_b = {
        "case_id": "D3A-PILOT-001",
        "stage_a": copy.deepcopy(stage_a),
        "pit_context": {
            "security_type": "U.S. Common Stock (Operating Company)",
            "market_cap_cohort": "$5B - $20B (Mid-to-Large Cap)",
            "trading_history_cohort": "established (252+ sessions history)",
            "pit_earnings_schedule_status": "unknown",
            "pit_earnings_announcement_timing": None,
            "pit_sessions_to_next_earnings": None,
            "reported_financial_facts": "unavailable_in_local_artifacts (fail-closed null)",
            "analyst_revisions": "unavailable_in_local_artifacts (fail-closed null)",
            "catalyst_news_feed": "unavailable_in_local_artifacts (fail-closed null)",
        },
        "data_confidence_status": "verified_local_pit_artifacts_only",
    }

    answer_key = AnswerKeyRecord(
        case_id="D3A-PILOT-001",
        sample_stratum="positive_master_episode",
        immutable_security_id="FIGI_TEST0001",
        ticker="XYZ",
        decision_date="2018-05-15",
        cutoff_time="20:30",
        episode_id="EP_12345",
        clean_target_reached=True,
        target_progress_ratio=1.0,
        near_miss=False,
        adverse_excursion=False,
        mfe_pct=14.5,
        mae_pct=2.1,
        time_to_target=6,
    )

    return stage_a, stage_b, answer_key


def test_clean_packet_passes_audit(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    res = audit_single_case(stage_a, stage_b, answer_key)
    assert res["case_id"] == "D3A-PILOT-001"
    assert res["ticker_leakage_clean"] is True
    assert res["security_id_leakage_clean"] is True
    assert res["calendar_date_leakage_clean"] is True
    assert res["class_leakage_clean"] is True
    assert res["outcome_leakage_clean"] is True
    assert res["future_bar_leakage_clean"] is True
    assert res["cutoff_bar_label"] == "T0"


def test_audit_detects_ticker_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_a["technical_metrics"]["commentary"] = "Stock XYZ is breaking out"
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_security_id_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_b["pit_context"]["internal_ref"] = "FIGI_TEST0001"
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_calendar_date_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_a["relative_bars"][0]["as_of"] = "2018-05-15"
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_stratum_name_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_a["technical_metrics"]["stratum"] = "positive_master_episode"
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_future_outcome_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_b["pit_context"]["clean_target_reached"] = True
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_future_bar_leakage(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    # Append a future bar T+1
    stage_a["relative_bars"].append({
        "relative_index": 1,
        "relative_label": "T1",
        "normalized_open": 101.0,
        "normalized_high": 102.0,
        "normalized_low": 100.0,
        "normalized_close": 101.5,
    })
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_audit_detects_stage_b_fields_leaking_into_stage_a(
    clean_test_case: tuple[dict[str, Any], dict[str, Any], AnswerKeyRecord]
) -> None:
    stage_a, stage_b, answer_key = clean_test_case
    stage_a["market_cap_cohort"] = "$5B - $20B (Mid-to-Large Cap)"
    with pytest.raises(ValueError, match="LEAKAGE AUDIT FAILED"):
        audit_single_case(stage_a, stage_b, answer_key)


def test_market_cap_cohort_mapping() -> None:
    assert get_market_cap_cohort(None) == "unknown"
    assert get_market_cap_cohort(float("nan")) == "unknown"
    assert get_market_cap_cohort(2_000_000_000) == "< $3B (index exception)"
    assert get_market_cap_cohort(4_000_000_000) == "$3B - $5B (Mid-Cap)"
    assert get_market_cap_cohort(15_000_000_000) == "$5B - $20B (Mid-to-Large Cap)"
    assert get_market_cap_cohort(50_000_000_000) == "$20B - $200B (Large Cap)"
    assert get_market_cap_cohort(300_000_000_000) == "$200B+ (Mega Cap)"
