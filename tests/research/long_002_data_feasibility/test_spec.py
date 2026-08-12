"""Credential-free tests for the LONG-002B probe and data-contract specs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LONG_002_SPEC = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002-v1.json"
PROBE_SPEC = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002B-probe-v1.json"
DATA_CONTRACT = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002B-data-contract-v1.json"

LOCKED_LONG_002_SHA256 = "f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_long_002_spec_is_unchanged() -> None:
    assert LONG_002_SPEC.exists()
    assert _sha256(LONG_002_SPEC) == LOCKED_LONG_002_SHA256


def test_probe_spec_is_json_safe_and_locked_to_long_002() -> None:
    spec = _load_json(PROBE_SPEC)
    json.dumps(spec, allow_nan=False)
    assert spec["task_id"] == "LONG-002B"
    assert spec["classification"] == "research-only"
    assert spec["production_promotion_eligible"] is False
    assert spec["locked_long_002_spec_sha256"] == LOCKED_LONG_002_SHA256
    assert Path(spec["locked_long_002_spec_path"]).exists()


def test_probe_spec_enumerates_four_data_families() -> None:
    spec = _load_json(PROBE_SPEC)
    families = spec["data_families"]
    assert set(families.keys()) == {
        "daily_market_data",
        "security_master_and_corporate_actions",
        "issuer_fundamentals_and_shares",
        "earnings_event_timing",
    }
    for family in families.values():
        assert "preferred_provider" in family
        assert "fallback_order" in family
        assert len(family["fallback_order"]) <= 2
        assert "minimum_usable_contract" in family
        assert "stop_condition" in family


def test_probe_spec_budgets_are_locked() -> None:
    budget = _load_json(PROBE_SPEC)["hard_network_budget"]
    assert budget["max_probe_securities"] == 12
    assert budget["max_as_of_dates_per_security"] == 4
    assert budget["max_total_http_requests"] == 120
    assert budget["max_retries_for_transient_failure"] == 1
    assert budget["stop_on_minimum_usable"] is True
    assert budget["no_extra_provider_hunting_without_gary_approval"] is True
    assert "authentication" in budget["no_retry_for"]


def test_probe_spec_panel_covers_required_categories() -> None:
    panel = _load_json(PROBE_SPEC)["probe_panel"]["locked_panel"]
    assert len(panel) <= 12
    categories = {item["category"].lower() for item in panel}
    combined = " ".join(categories)
    assert "active mega-cap" in combined
    assert "active mid-cap" in combined or "mid-cap" in combined
    assert "multiple share classes" in combined
    assert "recent ipo" in combined
    assert "ticker/name change" in combined or "renamed" in combined
    assert "split" in combined
    assert "spin-off" in combined or "special distribution" in combined
    assert "merger" in combined or "delisting" in combined
    assert "excluded" in combined


def test_probe_spec_prohibitions_include_validation_holdout_outcomes() -> None:
    spec = _load_json(PROBE_SPEC)
    pro = "\n".join(spec["explicit_prohibitions"])
    assert "No validation/holdout" in pro or "validation" in pro.lower() and "holdout" in pro.lower()
    assert "No full historical dataset construction" in pro
    assert "No model fitting" in pro or "No model fitting or configuration search" in pro


def test_data_contract_is_json_safe_and_references_long_002() -> None:
    contract = _load_json(DATA_CONTRACT)
    json.dumps(contract, allow_nan=False)
    assert contract["task_id"] == "LONG-002"
    assert contract["locked_specs"]["long_002_v1_sha256"] == LOCKED_LONG_002_SHA256


def test_data_contract_schema_covers_required_fields() -> None:
    schema = _load_json(DATA_CONTRACT)["dataset_manifest_schema"]
    assert "per_field_family" in schema
    for family in (
        "daily_market_data",
        "security_master_and_corporate_actions",
        "issuer_fundamentals_and_shares",
        "earnings_event_timing",
    ):
        assert family in schema["per_field_family"]
    assert "universe_and_identity" in schema
    assert "quality_and_integrity" in schema
    assert "splits_and_adjustments" in schema
    contract = _load_json(DATA_CONTRACT)
    assert contract["point_in_time_rules"]["no_current_membership_backfill"] is True
    assert contract["point_in_time_rules"]["missing_values_remain_null"] is True
    assert schema["holdout_access_safeguard"]["holdout_parsed"] == "boolean"


def test_probe_spec_dispositions_are_valid() -> None:
    spec = _load_json(PROBE_SPEC)
    assert set(spec["disposition_labels"]["per_family"]) == {
        "supported",
        "supported_with_documented_limitations",
        "not_supported",
        "invalid_evidence",
    }
    assert set(spec["evidence_confidence_labels"]) == {
        "strong_evidence",
        "moderate_evidence",
        "limited_but_usable_evidence",
        "invalid_evidence",
    }
