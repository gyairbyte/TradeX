"""Tests for descriptive shadow candidate evaluation (MVP-ARCH-001-R5B)."""
from datetime import UTC, datetime

from tradex.candidates.aggregator import (
    build_candidate_snapshot,
    extract_screener_evidence,
)
from tradex.candidates.evaluator import (
    ShadowObservationEvaluator,
)
from tradex.candidates.models import (
    CandidateDimension,
    ReasonPolarity,
    ReasonSeverity,
)


def test_shadow_evaluator_properties():
    evaluator = ShadowObservationEvaluator()
    assert evaluator.evaluator_id == "shadow_observation_evaluator"
    assert evaluator.evaluator_version == "1.0.0"
    assert evaluator.evidence_state == "exploratory"


def test_shadow_evaluator_dimensions_narrow():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snapshot = build_candidate_snapshot("AAPL", "sess-1", dt)
    evidence, missing = extract_screener_evidence(
        candidate_id=snapshot.candidate_id,
        observation={
            "ticker": "AAPL",
            "status": "signal",
            "score": 70,
            "last_close": 220.50,
            "volume_ratio": 1.8,
            "rsi": 62.0,
            "days_until_earnings": 15,
            "reasons": "Bullish structure",
            "provider": "schwab",
        },
        session_id="sess-1",
        timeframe="intraday",
        observed_at=dt,
        actual_provider="schwab",
    )

    evaluator = ShadowObservationEvaluator()
    evaluation, _ = evaluator.evaluate(
        snapshot=snapshot,
        evidence=[evidence],
        missing_data=missing,
        requested_provider="schwab",
        actual_provider="schwab",
        fallback_used=False,
    )

    # Dimensional assertions: ONLY context and data_confidence
    assert set(evaluation.dimensions.keys()) == {
        CandidateDimension.CONTEXT.value,
        CandidateDimension.DATA_CONFIDENCE.value,
    }

    # Verify explicitly excluded dimensions are ABSENT
    for excluded in (
        CandidateDimension.ELIGIBILITY,
        CandidateDimension.SETUP_QUALITY,
        CandidateDimension.MOVE_POTENTIAL,
        CandidateDimension.ENTRY_READINESS,
        CandidateDimension.DOWNSIDE_RISK,
    ):
        assert excluded.value not in evaluation.dimensions

    # Check context contents
    ctx = evaluation.dimensions["context"]
    assert ctx["evidence_types"] == ["screener_observation"]
    assert ctx["observation_status"] == "signal"
    assert ctx["timeframe"] == "intraday"
    assert ctx["days_until_earnings"] == 15

    # Check data confidence contents
    dc = evaluation.dimensions["data_confidence"]
    assert dc["actual_provider"] == "schwab"
    assert dc["requested_provider"] == "schwab"
    assert dc["fallback_used"] is False
    assert dc["missing_inputs_count"] == 0


def test_shadow_evaluator_reasons_all_neutral():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snapshot = build_candidate_snapshot("NVDA", "sess-1", dt)
    evidence, missing = extract_screener_evidence(
        candidate_id=snapshot.candidate_id,
        observation={
            "ticker": "NVDA",
            "status": "below_threshold",
            "score": 30,
            "last_close": 120.0,
            "volume_ratio": 0.9,
            "rsi": 45.0,
            "days_until_earnings": None,
            "reasons": "Below minimum threshold",
            "provider": "alpaca",
        },
        session_id="sess-1",
        timeframe="short",
        observed_at=dt,
        actual_provider="alpaca",
    )

    evaluator = ShadowObservationEvaluator()
    evaluation, reasons = evaluator.evaluate(
        snapshot=snapshot,
        evidence=[evidence],
        missing_data=missing,
        requested_provider="schwab",
        actual_provider="alpaca",
        fallback_used=True,
    )

    # Invariant: ALL reason polarities must be strictly NEUTRAL
    assert len(reasons) > 0
    for r in reasons:
        assert r.polarity == ReasonPolarity.NEUTRAL
        assert r.candidate_id == snapshot.candidate_id
        assert r.evaluation_id == evaluation.evaluation_id
        # Referential integrity to evidence
        if r.source_evidence_id is not None:
            assert r.source_evidence_id == evidence.evidence_id

    # Fallback reason emitted as warning
    fallback_reason = next((r for r in reasons if r.reason_code == "PROVIDER_FALLBACK_ACTIVE"), None)
    assert fallback_reason is not None
    assert fallback_reason.severity == ReasonSeverity.WARNING
    assert fallback_reason.polarity == ReasonPolarity.NEUTRAL


def test_shadow_evaluator_missing_fields_reason():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snapshot = build_candidate_snapshot("AMD", "sess-1", dt)
    evidence, missing = extract_screener_evidence(
        candidate_id=snapshot.candidate_id,
        observation={
            "ticker": "AMD",
            "status": "signal",
            "score": 50,
            "last_close": 140.0,
            "volume_ratio": None,
            "rsi": None,
            "days_until_earnings": 10,
            "reasons": "",
            "provider": "schwab",
        },
        session_id="sess-1",
        timeframe="intraday",
        observed_at=dt,
        actual_provider="schwab",
    )

    evaluator = ShadowObservationEvaluator()
    _, reasons = evaluator.evaluate(
        snapshot=snapshot,
        evidence=[evidence],
        missing_data=missing,
        requested_provider="schwab",
        actual_provider="schwab",
        fallback_used=False,
    )

    incomplete_reason = next((r for r in reasons if r.reason_code == "PRIMARY_INPUTS_INCOMPLETE"), None)
    assert incomplete_reason is not None
    assert "volume_ratio" in incomplete_reason.human_text
    assert "rsi" in incomplete_reason.human_text
    assert incomplete_reason.polarity == ReasonPolarity.NEUTRAL
