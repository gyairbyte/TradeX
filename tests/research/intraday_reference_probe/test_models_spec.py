"""Credential-free tests for reference probe models and spec loader."""
from __future__ import annotations

import json
from pathlib import Path

from tradex.research.intraday_reference_probe.models import (
    PITObservation,
    ProviderCandidateResult,
    ReferenceProbeDecision,
    hash_bytes,
    hash_text,
    json_hash,
    now_utc_iso,
)
from tradex.research.intraday_reference_probe.spec import (
    ReferenceProbeSpec,
    load_probe_spec,
)

PROBE_SPEC = Path("docs/research/specs/INTRA-001B-reference-probe-v1.json")
AMENDMENT = Path("docs/research/specs/INTRA-001-data-contract-amendment-v2.json")


def test_reference_probe_spec_loads() -> None:
    spec, raw = load_probe_spec(PROBE_SPEC)
    assert isinstance(spec, ReferenceProbeSpec)
    assert isinstance(raw, bytes)
    assert spec.task_id == "INTRA-001B-REFERENCE"
    assert spec.probe_version == 1
    assert "alpha_vantage" in spec.candidate_selection_order


def test_original_strategy_spec_sha_matches() -> None:
    spec, _ = load_probe_spec(PROBE_SPEC)
    from tradex.research.intraday_reference_probe.spec import sha256_of_file

    observed = sha256_of_file(Path("docs/research/specs/INTRA-001-v1.json"))
    assert observed == spec.expected_original_strategy_spec_sha256


def test_amendment_json_valid() -> None:
    data = json.loads(AMENDMENT.read_bytes())
    assert data["amendment_id"] == "INTRA-001-data-contract-amendment-v2"
    assert data["original_strategy_spec_sha256"]
    assert data["no_silent_fallback"] is True
    assert data["no_ohlcv_provider_mixing"] is True


def test_reference_probe_decision_defaults() -> None:
    decision = ReferenceProbeDecision(
        probe_version=1,
        task_id="INTRA-001B-REFERENCE",
        provider="alpha_vantage",
        outcome="supported",
        approved_as_reference_provider=True,
        reason="all gates passed",
        candidate_order=("alpha_vantage",),
    )
    d = decision.to_dict()
    assert d["provider"] == "alpha_vantage"
    assert d["approved_as_reference_provider"] is True


def test_provider_candidate_result_round_trip() -> None:
    obs = PITObservation(
        provider="alpha_vantage",
        pit_date="2024-05-31",
        state="active",
        requested_at=now_utc_iso(),
        elapsed_seconds=1.2,
        row_count=3,
        column_headers=("symbol", "name"),
        raw_sha256=hash_text("a,b\n1,2"),
        repeat_match=True,
    )
    result = ProviderCandidateResult(
        provider="alpha_vantage",
        target_entitlement="free LISTING_STATUS",
        probe_version=1,
        observations=(obs,),
        capability_rows=(),
        security_type_counts={"Stock": 3},
        exchange_counts={"NYSE": 3},
    )
    d = result.to_dict()
    assert d["observations"][0]["row_count"] == 3


def test_hash_functions() -> None:
    assert hash_bytes(b"foo") == hash_text("foo")
    assert len(hash_bytes(b"foo")) == 64
    assert json_hash({"a": 1, "b": [2, 3]}) == json_hash({"b": [2, 3], "a": 1})
