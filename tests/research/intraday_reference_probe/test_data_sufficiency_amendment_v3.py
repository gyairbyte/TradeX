"""Credential-free regression tests for the INTRA-001 data-sufficiency amendment v3."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tradex.research.intraday_reference_probe.spec import sha256_of_file

AMENDMENT_V3 = Path("docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json")
ORIGINAL_SPEC = Path("docs/research/specs/INTRA-001-v1.json")
AMENDMENT_V2 = Path("docs/research/specs/INTRA-001-data-contract-amendment-v2.json")
V4_DECISION_DOC = Path("docs/research/INTRA-001B-REFERENCE-V4.md")


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def test_amendment_v3_is_valid_json_and_required_fields() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    assert data["schema_version"] == "1.0"
    assert data["task_id"] == "INTRA-001"
    assert data["amendment_id"] == "INTRA-001-data-sufficiency-amendment-v3"
    assert data["amendment_version"] == 3
    assert data["amendment_type"] == "data_sufficiency_methodology"
    assert data["status"] == "approved_best_available_data_ready_for_snapshot_implementation"
    assert data["evidence_label"] == "limited_but_usable_evidence"


def test_amendment_v3_references_correct_original_spec_and_sha() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    assert data["original_strategy_spec"] == "docs/research/specs/INTRA-001-v1.json"
    assert data["original_strategy_spec_sha256"] == sha256_of_file(ORIGINAL_SPEC)
    assert data["original_strategy_spec_sha256"] == (
        "09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464"
    )


def test_amendment_v3_preserves_v2_record() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    assert data["supersedes"]["amendment_id"] == "INTRA-001-data-contract-amendment-v2"
    assert data["supersedes"]["amendment_path"] == str(AMENDMENT_V2)
    assert data["supersedes"]["amendment_sha256"] == sha256_of_file(AMENDMENT_V2)
    assert "prospective" in data["supersedes"]["superseded_for"].lower()


def test_amendment_v3_preserves_v4_evidence() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    v4 = data["preserved_reference_probe_evidence"]
    assert v4["v4_strict_contract_disposition"] == "unsupported"
    assert v4["v4_decision_document"] == str(V4_DECISION_DOC)
    assert v4["v4_decision_document_sha256"] == sha256_of_file(V4_DECISION_DOC)
    assert v4["v4_failed_mandatory_gates"] == ["otc_exclusion", "duplicate_symbol_behavior_and_resolution"]


def test_amendment_v3_date_ranges_chronological_and_in_dataset() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    dataset = data["dataset"]
    ds_start = _parse_date(dataset["start"])
    ds_end = _parse_date(dataset["end"])
    splits = dataset["splits"]

    dev_start = _parse_date(splits["development"]["start"])
    dev_end = _parse_date(splits["development"]["end"])
    val_start = _parse_date(splits["validation"]["start"])
    val_end = _parse_date(splits["validation"]["end"])
    ho_start = _parse_date(splits["holdout"]["start"])
    ho_end = _parse_date(splits["holdout"]["end"])

    assert ds_start <= dev_start < dev_end < val_start <= val_end < ho_start <= ho_end
    assert ds_start == dev_start
    assert ho_end == ds_end
    assert dataset["splits_are_chronological_and_non_overlapping"] is True


def test_amendment_v3_pit_dates_are_month_end_and_precede_effective_months() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    pit_dates = data["conservative_universe_controls"]["monthly_pit_dates"]
    assert len(pit_dates) == 12

    effective_year, effective_month = 2025, 1
    for pit_str in pit_dates:
        pit = _parse_date(pit_str)
        assert pit.year == effective_year or (pit.year == 2024 and effective_year == 2025 and effective_month == 1)
        # PIT must be the last calendar day of the preceding month.
        next_month_first = (
            date(effective_year, effective_month, 1)
            if effective_month > 1
            else date(effective_year, 1, 1)
        )
        assert pit < next_month_first
        assert (next_month_first - pit).days <= 31

        if effective_month == 12:
            effective_year += 1
            effective_month = 1
        else:
            effective_month += 1

    assert data["conservative_universe_controls"]["pit_date_precedes_effective_month"] is True


def test_amendment_v3_alpaca_remains_sole_ohlcv_provider() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    roles = data["provider_roles"]
    assert roles["authoritative_ohlcv_provider"] == "alpaca"
    assert roles.get("authoritative_ohlcv_feed") == "sip"
    assert roles["secondary_provider_cannot_supply_ohlcv"] is True
    assert roles["no_ohlcv_provider_mixing"] is True


def test_amendment_v3_massive_accepted_with_limitations_not_strict_supported() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    roles = data["provider_roles"]
    assert roles["reference_provider"] == "massive"
    assert roles["reference_provider_status"] == "accepted_with_documented_limitations"
    assert roles["no_composite_reference_stack"] is True
    assert data["preserved_reference_probe_evidence"]["v4_strict_contract_disposition"] == "unsupported"
    assert isinstance(data["accepted_limitations"], list)
    assert any("duplicate" in item.lower() for item in data["accepted_limitations"])
    assert any("otc" in item.lower() for item in data["accepted_limitations"])


def test_amendment_v3_conservative_universe_controls_exclude_bad_records() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    controls = data["conservative_universe_controls"]
    assert controls["stock_security_type_allowlist"] == ["common_stock"]
    assert "unmapped" in controls["security_type_exclusions"]
    assert controls["exclude_unknown_or_unmapped_exchanges"] is True
    assert "exclude" in controls["duplicate_symbol_policy"].lower()
    assert controls["missing_security_type_policy"] == "Exclude"
    assert controls["unmapped_security_type_policy"] == "Exclude"
    assert controls["no_manual_ticker_exceptions"] is True
    assert controls["record_exclusion_reasons"] is True
    assert controls["record_monthly_exclusion_counts"] is True
    assert controls["do_not_construct_from_todays_listings"] is True
    assert controls["do_not_silently_substitute_providers_or_fields"] is True


def test_amendment_v3_exchange_allowlist_matches_v4_evidence() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    assert data["conservative_universe_controls"]["exchange_allowlist"] == [
        "XNYS", "XNAS", "ARCX", "BATS", "XASE", "XBOS"
    ]


def test_amendment_v3_no_v5_authorized() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    assert data["no_v5_or_additional_provider_search"] is True


def test_amendment_v3_sample_minimums_not_reduced_for_shorter_history() -> None:
    data = json.loads(AMENDMENT_V3.read_bytes())
    policy = data["sample_minimums_policy"]
    assert policy["shorter_history_does_not_reduce_sample_minimums"] is True
    assert policy["any_change_to_sample_minimums_or_gates_must_be_preregistered"] is True
