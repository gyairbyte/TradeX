"""Deterministic outcome calculations and reproducibility helpers (MVP-ARCH-001-R6).

Implements entry slippage, gross return %, net return %, deterministic outcome confidence
mapping, canonical inputs serialization, and SHA-256 inputs hashing.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from tradex.journal.models import (
    ExecutionProvenance,
    ExecutionProvenanceType,
    JournalOutcome,
    OutcomeConfidence,
)

JOURNAL_OUTCOME_COMPUTATION_VERSION: str = "journal-outcome-v1"


def map_outcome_confidence(
    fill_provenance: ExecutionProvenance | None,
    exit_provenance: ExecutionProvenance | None,
) -> OutcomeConfidence:
    """Map fill and exit provenance to deterministic OutcomeConfidence.

    Precedence rules:
    1. If either provenance record is missing, has missing/empty execution_provenance,
       or has provider == 'unknown' -> UNKNOWN.
    2. Else if both fill and exit have execution_provenance == 'broker_confirmed' -> CONFIRMED.
    3. Otherwise (complete manual/simulated combinations) -> PROVISIONAL.
    """
    if fill_provenance is None or exit_provenance is None:
        return OutcomeConfidence.UNKNOWN

    fill_prov_type = (
        fill_provenance.execution_provenance.value
        if isinstance(fill_provenance.execution_provenance, ExecutionProvenanceType)
        else str(fill_provenance.execution_provenance).strip().lower()
    )
    exit_prov_type = (
        exit_provenance.execution_provenance.value
        if isinstance(exit_provenance.execution_provenance, ExecutionProvenanceType)
        else str(exit_provenance.execution_provenance).strip().lower()
    )

    if not fill_prov_type or not exit_prov_type:
        return OutcomeConfidence.UNKNOWN

    fill_provider = str(fill_provenance.provider or "").strip().lower()
    exit_provider = str(exit_provenance.provider or "").strip().lower()

    if fill_provider == "unknown" or exit_provider == "unknown" or not fill_provider or not exit_provider:
        return OutcomeConfidence.UNKNOWN

    if (
        fill_prov_type == ExecutionProvenanceType.BROKER_CONFIRMED.value
        and exit_prov_type == ExecutionProvenanceType.BROKER_CONFIRMED.value
    ):
        return OutcomeConfidence.CONFIRMED

    return OutcomeConfidence.PROVISIONAL


def canonicalize_provenance_payload(prov: ExecutionProvenance | None) -> dict[str, Any] | None:
    """Convert ExecutionProvenance to a deterministic dictionary for inputs_json."""
    if prov is None:
        return None
    res: dict[str, Any] = {
        "execution_provenance": (
            prov.execution_provenance.value
            if isinstance(prov.execution_provenance, ExecutionProvenanceType)
            else str(prov.execution_provenance)
        ),
        "observed_at": prov.observed_at.isoformat(),
        "observer": prov.observer,
        "provider": prov.provider,
        "simulation_rule": prov.simulation_rule,
    }
    return res


def serialize_canonical_inputs_json(inputs: dict[str, Any]) -> str:
    """Serialize computation inputs to the single canonical JSON string used for persistence and hashing."""
    return json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)


def compute_journal_outcome(
    *,
    journal_id: str,
    planned_entry: float,
    fill_price: float,
    quantity: float,
    exit_price: float,
    fill_provenance: ExecutionProvenance | None,
    exit_provenance: ExecutionProvenance | None,
    costs: float | None = None,
    source_event_seq: int = 1,
    computation_version: str = JOURNAL_OUTCOME_COMPUTATION_VERSION,
    outcome_id: str | None = None,
    computed_at: datetime | None = None,
) -> JournalOutcome:
    """Deterministically compute outcome metrics and construct a JournalOutcome record."""
    if outcome_id is None:
        outcome_id = uuid.uuid4().hex
    if computed_at is None:
        computed_at = datetime.now(tz=UTC)
    else:
        if computed_at.tzinfo is None:
            raise ValueError("computed_at must be timezone-aware")
        computed_at = computed_at.astimezone(UTC)

    entry_slippage = fill_price - planned_entry
    gross_return_pct = ((exit_price - fill_price) / fill_price) * 100.0

    if costs is not None:
        net_return_pct = ((exit_price - fill_price - (costs / quantity)) / fill_price) * 100.0
    else:
        net_return_pct = None

    confidence = map_outcome_confidence(fill_provenance, exit_provenance)

    inputs_dict: dict[str, Any] = {
        "costs": costs,
        "exit_price": exit_price,
        "exit_provenance": canonicalize_provenance_payload(exit_provenance),
        "fill_price": fill_price,
        "fill_provenance": canonicalize_provenance_payload(fill_provenance),
        "planned_entry": planned_entry,
        "quantity": quantity,
    }

    canonical_json = serialize_canonical_inputs_json(inputs_dict)
    inputs_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return JournalOutcome(
        outcome_id=outcome_id,
        journal_id=journal_id,
        computation_version=computation_version,
        computed_at=computed_at,
        source_event_seq=source_event_seq,
        inputs_hash=inputs_hash,
        entry_slippage=entry_slippage,
        costs=costs,
        gross_return_pct=gross_return_pct,
        net_return_pct=net_return_pct,
        outcome_confidence=confidence,
        inputs=inputs_dict,
        strategy_drawdown=None,
    )
