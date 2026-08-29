"""Deterministic calculation and reproducibility tests for Journal outcomes."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime

from tradex.journal.models import (
    ExecutionProvenance,
    ExecutionProvenanceType,
    OutcomeConfidence,
)
from tradex.journal.outcomes import (
    JOURNAL_OUTCOME_COMPUTATION_VERSION,
    compute_journal_outcome,
    map_outcome_confidence,
)


def test_entry_slippage_calculation() -> None:
    now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )

    # Positive slippage (paid more than planned)
    out_pos = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=101.5,
        quantity=100.0,
        exit_price=110.0,
        fill_provenance=prov,
        exit_provenance=prov,
    )
    assert math.isclose(out_pos.entry_slippage, 1.5)

    # Negative slippage (filled better than planned)
    out_neg = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=99.2,
        quantity=100.0,
        exit_price=110.0,
        fill_provenance=prov,
        exit_provenance=prov,
    )
    assert math.isclose(out_neg.entry_slippage, -0.8)


def test_gross_and_net_return_calculations() -> None:
    now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )

    # Standard gain with costs: fill=100, exit=110, qty=100, costs=10.0 ($0.10/share)
    # gross = (110 - 100) / 100 * 100 = 10.0%
    # net = (110 - 100 - 10/100) / 100 * 100 = (10 - 0.10) / 100 * 100 = 9.90%
    out1 = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=100.0,
        quantity=100.0,
        exit_price=110.0,
        fill_provenance=prov,
        exit_provenance=prov,
        costs=10.0,
    )
    assert math.isclose(out1.gross_return_pct, 10.0)
    assert out1.net_return_pct is not None
    assert math.isclose(out1.net_return_pct, 9.9)

    # Unknown costs (None) -> net_return_pct is None (NEVER silently 0)
    out_no_costs = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=100.0,
        quantity=100.0,
        exit_price=110.0,
        fill_provenance=prov,
        exit_provenance=prov,
        costs=None,
    )
    assert math.isclose(out_no_costs.gross_return_pct, 10.0)
    assert out_no_costs.net_return_pct is None

    # Zero costs (0.0) -> net_return_pct == gross_return_pct
    out_zero_costs = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=100.0,
        quantity=100.0,
        exit_price=110.0,
        fill_provenance=prov,
        exit_provenance=prov,
        costs=0.0,
    )
    assert math.isclose(out_zero_costs.gross_return_pct, 10.0)
    assert out_zero_costs.net_return_pct is not None
    assert math.isclose(out_zero_costs.net_return_pct, 10.0)

    # Loss with costs: fill=100, exit=90, qty=50, costs=5.0 ($0.10/share)
    # gross = (90 - 100) / 100 * 100 = -10.0%
    # net = (90 - 100 - 0.10) / 100 * 100 = -10.10%
    out_loss = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=100.0,
        quantity=50.0,
        exit_price=90.0,
        fill_provenance=prov,
        exit_provenance=prov,
        costs=5.0,
    )
    assert math.isclose(out_loss.gross_return_pct, -10.0)
    assert out_loss.net_return_pct is not None
    assert math.isclose(out_loss.net_return_pct, -10.1)


def test_strategy_drawdown_always_none() -> None:
    now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )
    out = compute_journal_outcome(
        journal_id="j-1",
        planned_entry=100.0,
        fill_price=100.0,
        quantity=100.0,
        exit_price=105.0,
        fill_provenance=prov,
        exit_provenance=prov,
    )
    assert out.strategy_drawdown is None


def test_outcome_confidence_mapping() -> None:
    now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)

    p_manual = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )
    p_sim = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.SIMULATED,
        provider="schwab",
        observed_at=now,
        observer="system",
        simulation_rule="next_open",
    )
    p_broker = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.BROKER_CONFIRMED,
        provider="schwab",
        observed_at=now,
        observer="broker_feed",
    )
    p_unknown_provider = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="unknown",
        observed_at=now,
        observer="gary",
    )

    # 1. Missing provenance -> UNKNOWN
    assert map_outcome_confidence(None, p_manual) == OutcomeConfidence.UNKNOWN
    assert map_outcome_confidence(p_manual, None) == OutcomeConfidence.UNKNOWN
    assert map_outcome_confidence(p_unknown_provider, p_manual) == OutcomeConfidence.UNKNOWN
    assert map_outcome_confidence(p_manual, p_unknown_provider) == OutcomeConfidence.UNKNOWN

    # 2. Both broker_confirmed -> CONFIRMED
    assert map_outcome_confidence(p_broker, p_broker) == OutcomeConfidence.CONFIRMED

    # 3. Manual / Simulated / Mixed with broker_confirmed -> PROVISIONAL
    assert map_outcome_confidence(p_manual, p_manual) == OutcomeConfidence.PROVISIONAL
    assert map_outcome_confidence(p_sim, p_sim) == OutcomeConfidence.PROVISIONAL
    assert map_outcome_confidence(p_manual, p_sim) == OutcomeConfidence.PROVISIONAL
    assert map_outcome_confidence(p_broker, p_manual) == OutcomeConfidence.PROVISIONAL
    assert map_outcome_confidence(p_sim, p_broker) == OutcomeConfidence.PROVISIONAL


def test_canonical_inputs_json_and_sha256_reproducibility() -> None:
    now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )

    out = compute_journal_outcome(
        journal_id="j-100",
        planned_entry=150.0,
        fill_price=150.5,
        quantity=200.0,
        exit_price=165.0,
        fill_provenance=prov,
        exit_provenance=prov,
        costs=15.0,
        source_event_seq=4,
    )

    # Verify canonical inputs JSON formatting and hash
    inputs = out.inputs
    canonical_json = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    assert out.inputs_hash == expected_hash
    assert out.computation_version == JOURNAL_OUTCOME_COMPUTATION_VERSION
    assert out.source_event_seq == 4
