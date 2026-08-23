import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tradex.candidates import (
    CandidateDimension,
    CandidateDossier,
    CandidateEvaluation,
    CandidateEvidence,
    CandidateMissingData,
    CandidateReason,
    CandidateSnapshot,
    MissingDataStatus,
    ReasonPolarity,
    ReasonSeverity,
    SecurityIdentityStatus,
)


def test_candidate_snapshot_valid() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(
        candidate_id="cand-001",
        symbol="aapl",
        decision_timestamp=dt,
    )
    assert snap.candidate_id == "cand-001"
    assert snap.symbol == "AAPL"
    assert snap.decision_timestamp == dt
    assert snap.contract_version == 1
    assert snap.trading_date == "2026-08-21"
    assert snap.security_identity_version is None
    assert snap.security_identity_status == SecurityIdentityStatus.UNKNOWN
    assert snap.created_at.tzinfo == UTC


def test_candidate_snapshot_rejects_naive_timestamp() -> None:
    naive_dt = datetime(2026, 8, 21, 14, 30)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        CandidateSnapshot(
            candidate_id="cand-001",
            symbol="AAPL",
            decision_timestamp=naive_dt,
        )


def test_candidate_snapshot_normalizes_non_utc_aware_timestamp() -> None:
    eastern = ZoneInfo("America/New_York")
    et_dt = datetime(2026, 8, 21, 9, 30, tzinfo=eastern)
    snap = CandidateSnapshot(
        candidate_id="cand-001",
        symbol="AAPL",
        decision_timestamp=et_dt,
    )
    assert snap.decision_timestamp.tzinfo == UTC
    assert snap.decision_timestamp == datetime(2026, 8, 21, 13, 30, tzinfo=UTC)
    assert snap.trading_date == "2026-08-21"


def test_candidate_snapshot_dst_boundary_timestamps() -> None:
    eastern = ZoneInfo("America/New_York")
    # Standard time (EST = UTC-5)
    dt_est = datetime(2026, 1, 15, 9, 30, tzinfo=eastern)
    snap_est = CandidateSnapshot(
        candidate_id="cand-est",
        symbol="AAPL",
        decision_timestamp=dt_est,
    )
    assert snap_est.decision_timestamp == datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
    assert snap_est.trading_date == "2026-01-15"

    # Daylight saving time (EDT = UTC-4)
    dt_edt = datetime(2026, 6, 15, 9, 30, tzinfo=eastern)
    snap_edt = CandidateSnapshot(
        candidate_id="cand-edt",
        symbol="AAPL",
        decision_timestamp=dt_edt,
    )
    assert snap_edt.decision_timestamp == datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    assert snap_edt.trading_date == "2026-06-15"


def test_candidate_snapshot_rejects_blank_symbol_and_id() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="Symbol must be a non-empty string"):
        CandidateSnapshot(candidate_id="cand-001", symbol="  ", decision_timestamp=dt)

    with pytest.raises(ValueError, match="candidate_id must be a non-empty string"):
        CandidateSnapshot(candidate_id="  ", symbol="AAPL", decision_timestamp=dt)


def test_candidate_snapshot_trading_date_mismatch_rejected() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="does not match derived market trading date"):
        CandidateSnapshot(
            candidate_id="cand-001",
            symbol="AAPL",
            decision_timestamp=dt,
            trading_date="2026-08-20",
        )


def test_candidate_snapshot_security_identity_consistency() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    # Valid known
    snap_known = CandidateSnapshot(
        candidate_id="cand-001",
        symbol="AAPL",
        decision_timestamp=dt,
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )
    assert snap_known.security_identity_status == SecurityIdentityStatus.KNOWN
    assert snap_known.security_identity_version == "sec-v1"

    # Status auto-promotes to KNOWN if version provided
    snap_auto = CandidateSnapshot(
        candidate_id="cand-001",
        symbol="AAPL",
        decision_timestamp=dt,
        security_identity_version="sec-v1",
    )
    assert snap_auto.security_identity_status == SecurityIdentityStatus.KNOWN

    # Inconsistent: status KNOWN but version None
    with pytest.raises(ValueError, match="cannot be 'known' when security_identity_version is None"):
        CandidateSnapshot(
            candidate_id="cand-001",
            symbol="AAPL",
            decision_timestamp=dt,
            security_identity_version=None,
            security_identity_status=SecurityIdentityStatus.KNOWN,
        )

    # Blank version rejected
    with pytest.raises(ValueError, match="security_identity_version cannot be empty"):
        CandidateSnapshot(
            candidate_id="cand-001",
            symbol="AAPL",
            decision_timestamp=dt,
            security_identity_version="  ",
        )


def test_candidate_evaluation_valid_and_rejects_non_finite_json() -> None:
    # Valid evaluation
    eval_rec = CandidateEvaluation(
        evaluation_id="eval-001",
        candidate_id="cand-001",
        evaluator_id="research_evaluator",
        evaluator_version="0.1.0",
        evidence_state="research_only",
        dimensions={CandidateDimension.SETUP_QUALITY: {"raw": 75, "normalized": 0.75}},
    )
    assert eval_rec.evaluator_id == "research_evaluator"
    assert eval_rec.dimensions == {"setup_quality": {"raw": 75, "normalized": 0.75}}

    # Reject NaN
    with pytest.raises(ValueError, match="without NaN/Infinity"):
        CandidateEvaluation(
            evaluation_id="eval-002",
            candidate_id="cand-001",
            evaluator_id="research_evaluator",
            evaluator_version="0.1.0",
            evidence_state="research_only",
            dimensions={"score": float("nan")},
        )

    # Reject Infinity
    with pytest.raises(ValueError, match="without NaN/Infinity"):
        CandidateEvaluation(
            evaluation_id="eval-003",
            candidate_id="cand-001",
            evaluator_id="research_evaluator",
            evaluator_version="0.1.0",
            evidence_state="research_only",
            dimensions={"score": math.inf},
        )


def test_candidate_evidence_valid() -> None:
    obs_dt = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    ev = CandidateEvidence(
        evidence_id="evid-001",
        candidate_id="cand-001",
        evidence_type="ohlcv",
        source_ref_type="scan_session",
        source_ref_id="session-123",
        provider="schwab",
        observed_at=obs_dt,
        metadata={"bar_count": 60, "timeframe": "intraday"},
    )
    assert ev.data_family == "ohlcv"
    assert ev.provider == "schwab"
    assert ev.observed_at == obs_dt

    # Reject naive observed_at
    with pytest.raises(ValueError, match="timezone-aware"):
        CandidateEvidence(
            evidence_id="evid-002",
            candidate_id="cand-001",
            evidence_type="ohlcv",
            observed_at=datetime(2026, 8, 21, 14, 0),  # noqa: DTZ001
        )


def test_candidate_reason_valid() -> None:
    reason = CandidateReason(
        reason_id="reas-001",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        dimension=CandidateDimension.CONTEXT,
        reason_code="SECTOR_ALIGNMENT",
        human_text="Sector ETF showed relative strength (+1.8%).",
        polarity=ReasonPolarity.SUPPORTING,
        severity=ReasonSeverity.INFO,
    )
    assert reason.polarity == ReasonPolarity.SUPPORTING
    assert reason.severity == ReasonSeverity.INFO
    assert reason.dimension == CandidateDimension.CONTEXT
    assert reason.human_text == "Sector ETF showed relative strength (+1.8%)."


def test_candidate_reason_dimension_normalization_and_rejection() -> None:
    # All enum members round-trip directly
    for dim in CandidateDimension:
        r = CandidateReason(
            reason_id=f"reas-{dim.value}",
            candidate_id="cand-001",
            evaluation_id="eval-001",
            dimension=dim,
            reason_code="R1",
            human_text="text",
        )
        assert r.dimension == dim

    # String normalization to enum
    r_str = CandidateReason(
        reason_id="reas-str",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        dimension=" SETUP_QUALITY ",
        reason_code="R1",
        human_text="text",
    )
    assert r_str.dimension == CandidateDimension.SETUP_QUALITY

    # None and empty string rejected
    with pytest.raises(TypeError, match="dimension must be a CandidateDimension instance or str"):
        CandidateReason(
            reason_id="reas-none",
            candidate_id="cand-001",
            evaluation_id="eval-001",
            dimension=None,  # type: ignore[arg-type]
            reason_code="R1",
            human_text="text",
        )

    with pytest.raises(ValueError, match="dimension cannot be empty"):
        CandidateReason(
            reason_id="reas-empty",
            candidate_id="cand-001",
            evaluation_id="eval-001",
            dimension="   ",
            reason_code="R1",
            human_text="text",
        )

    # Unknown string rejected
    with pytest.raises(ValueError, match="Unknown CandidateDimension"):
        CandidateReason(
            reason_id="reas-bad",
            candidate_id="cand-001",
            evaluation_id="eval-001",
            dimension="unsupported_dimension",
            reason_code="R1",
            human_text="text",
        )

    # Invalid type rejected
    with pytest.raises(TypeError, match="dimension must be a CandidateDimension instance or str"):
        CandidateReason(
            reason_id="reas-bad-type",
            candidate_id="cand-001",
            evaluation_id="eval-001",
            dimension=123,  # type: ignore[arg-type]
            reason_code="R1",
            human_text="text",
        )


def test_candidate_reason_requires_evaluation_id_and_dimension() -> None:
    # Missing evaluation_id / blank evaluation_id rejected
    with pytest.raises(ValueError, match="evaluation_id must be a non-empty string"):
        CandidateReason(
            reason_id="reas-bad-eval",
            candidate_id="cand-001",
            evaluation_id="",
            dimension=CandidateDimension.CONTEXT,
            reason_code="R1",
            human_text="text",
        )

    with pytest.raises(ValueError, match="evaluation_id must be a non-empty string"):
        CandidateReason(
            reason_id="reas-bad-eval",
            candidate_id="cand-001",
            evaluation_id="   ",
            dimension=CandidateDimension.CONTEXT,
            reason_code="R1",
            human_text="text",
        )

    # evaluation_id as None rejected
    with pytest.raises(ValueError, match="evaluation_id must be a non-empty string"):
        CandidateReason(
            reason_id="reas-bad-eval",
            candidate_id="cand-001",
            evaluation_id=None,  # type: ignore[arg-type]
            dimension=CandidateDimension.CONTEXT,
            reason_code="R1",
            human_text="text",
        )


def test_candidate_snapshot_contract_version_validation() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    # Valid
    snap = CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=1)
    assert snap.contract_version == 1

    # Rejected: non-positive int
    with pytest.raises(ValueError, match="contract_version must be a positive integer"):
        CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=0)

    with pytest.raises(ValueError, match="contract_version must be a positive integer"):
        CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=-1)

    # Rejected: unsupported version > 1
    with pytest.raises(ValueError, match="Unsupported candidate contract_version: 2"):
        CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=2)

    # Rejected: bool or float or str
    with pytest.raises(TypeError, match="contract_version must be an int"):
        CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=True)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="contract_version must be an int"):
        CandidateSnapshot(candidate_id="cand-1", symbol="AAPL", decision_timestamp=dt, contract_version=1.0)  # type: ignore[arg-type]


def test_candidate_snapshot_trading_date_non_trading_day_and_format_validation() -> None:
    # Saturday (non-trading day)
    sat_dt = datetime(2026, 8, 22, 14, 30, tzinfo=UTC)
    # Without trading_date, defaults to None
    snap_sat = CandidateSnapshot(candidate_id="cand-sat", symbol="AAPL", decision_timestamp=sat_dt)
    assert snap_sat.trading_date is None

    # Providing a trading_date on a non-trading day is rejected
    with pytest.raises(ValueError, match="falls on a non-trading day and cannot be assigned trading_date"):
        CandidateSnapshot(
            candidate_id="cand-sat",
            symbol="AAPL",
            decision_timestamp=sat_dt,
            trading_date="2026-08-22",
        )

    # Invalid trading_date format rejected
    trade_dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="Invalid trading_date format"):
        CandidateSnapshot(
            candidate_id="cand-fmt",
            symbol="AAPL",
            decision_timestamp=trade_dt,
            trading_date="2026/08/21",
        )

    with pytest.raises(TypeError, match="trading_date must be a string"):
        CandidateSnapshot(
            candidate_id="cand-fmt",
            symbol="AAPL",
            decision_timestamp=trade_dt,
            trading_date=20260821,  # type: ignore[arg-type]
        )


def test_candidate_missing_data_valid() -> None:
    obs_dt = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    m = CandidateMissingData(
        record_id="miss-001",
        candidate_id="cand-001",
        input_name="options_flow",
        data_family="options",
        status=MissingDataStatus.PROVIDER_UNSUPPORTED,
        detail="No true-flow provider configured in environment",
        provider="tradier",
        observed_at=obs_dt,
    )
    assert m.status == MissingDataStatus.PROVIDER_UNSUPPORTED
    assert m.detail == "No true-flow provider configured in environment"


def test_candidate_dossier_validation() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)
    eval1 = CandidateEvaluation(
        evaluation_id="eval-001",
        candidate_id="cand-001",
        evaluator_id="eval_1",
        evaluator_version="1.0",
        evidence_state="exploratory",
    )
    evid1 = CandidateEvidence(
        evidence_id="evid-001",
        candidate_id="cand-001",
        evidence_type="earnings",
    )
    reas1 = CandidateReason(
        reason_id="reas-001",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        dimension=CandidateDimension.CONTEXT,
        reason_code="R1",
        human_text="Sample explanation",
        source_evidence_id="evid-001",
    )
    miss1 = CandidateMissingData(
        record_id="miss-001",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        input_name="market_cap",
        data_family="fundamentals",
        status=MissingDataStatus.UNKNOWN,
    )

    dossier = CandidateDossier(
        snapshot=snap,
        evaluations=(eval1,),
        evidence=(evid1,),
        reasons=(reas1,),
        missing_data=(miss1,),
    )
    assert len(dossier.evaluations) == 1
    assert len(dossier.evidence) == 1
    assert len(dossier.reasons) == 1
    assert len(dossier.missing_data) == 1

    # Mismatched candidate_id in child evaluation
    eval_bad = CandidateEvaluation(
        evaluation_id="eval-002",
        candidate_id="cand-999",
        evaluator_id="eval_1",
        evaluator_version="1.0",
        evidence_state="exploratory",
    )
    with pytest.raises(ValueError, match="does not match snapshot"):
        CandidateDossier(snapshot=snap, evaluations=(eval_bad,))

    # Reason referencing non-existent evaluation in dossier (with non-empty evaluations)
    reas_bad = CandidateReason(
        reason_id="reas-002",
        candidate_id="cand-001",
        evaluation_id="eval-nonexistent",
        dimension=CandidateDimension.CONTEXT,
        reason_code="R2",
        human_text="Bad eval link",
    )
    with pytest.raises(ValueError, match="does not match any evaluation in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), reasons=(reas_bad,))

    # Reason referencing non-existent evidence in dossier (with non-empty evidence)
    reas_bad_ev = CandidateReason(
        reason_id="reas-003",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        dimension=CandidateDimension.CONTEXT,
        reason_code="R3",
        human_text="Bad evid link",
        source_evidence_id="evid-nonexistent",
    )
    with pytest.raises(ValueError, match="does not match any evidence in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), evidence=(evid1,), reasons=(reas_bad_ev,))


def test_candidate_dossier_unconditional_referential_integrity_empty_collections() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)
    eval1 = CandidateEvaluation(
        evaluation_id="eval-001",
        candidate_id="cand-001",
        evaluator_id="ev1",
        evaluator_version="1",
        evidence_state="e",
    )

    # Reason with evaluation_id when evaluations is EMPTY must fail unconditionally
    reas_dangling_eval = CandidateReason(
        reason_id="reas-001",
        candidate_id="cand-001",
        evaluation_id="eval-missing",
        dimension=CandidateDimension.CONTEXT,
        reason_code="R1",
        human_text="Dangling eval reference",
    )
    with pytest.raises(ValueError, match="Reason evaluation_id 'eval-missing' does not match any evaluation in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(), reasons=(reas_dangling_eval,))

    # MissingData with evaluation_id when evaluations is EMPTY must fail unconditionally
    miss_dangling_eval = CandidateMissingData(
        record_id="miss-001",
        candidate_id="cand-001",
        evaluation_id="eval-missing",
        input_name="price",
        data_family="ohlcv",
        status=MissingDataStatus.UNKNOWN,
    )
    with pytest.raises(ValueError, match="MissingData evaluation_id 'eval-missing' does not match any evaluation in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(), missing_data=(miss_dangling_eval,))

    # Reason with source_evidence_id when evidence is EMPTY must fail unconditionally
    reas_dangling_evid = CandidateReason(
        reason_id="reas-002",
        candidate_id="cand-001",
        evaluation_id="eval-001",
        dimension=CandidateDimension.CONTEXT,
        reason_code="R2",
        human_text="Dangling evid reference",
        source_evidence_id="evid-missing",
    )
    with pytest.raises(ValueError, match="Reason source_evidence_id 'evid-missing' does not match any evidence in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), evidence=(), reasons=(reas_dangling_evid,))


def test_candidate_dossier_duplicate_child_ids_rejected() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)
    eval1 = CandidateEvaluation(
        evaluation_id="eval-1",
        candidate_id="cand-001",
        evaluator_id="ev1",
        evaluator_version="1",
        evidence_state="e",
    )

    # Duplicate evaluation_id
    e1 = CandidateEvaluation(evaluation_id="eval-1", candidate_id="cand-001", evaluator_id="ev1", evaluator_version="1", evidence_state="e")
    e2 = CandidateEvaluation(evaluation_id="eval-1", candidate_id="cand-001", evaluator_id="ev2", evaluator_version="1", evidence_state="e")
    with pytest.raises(ValueError, match="Duplicate evaluation_id 'eval-1' in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(e1, e2))

    # Duplicate evidence_id
    ev1 = CandidateEvidence(evidence_id="evid-1", candidate_id="cand-001", evidence_type="ohlcv")
    ev2 = CandidateEvidence(evidence_id="evid-1", candidate_id="cand-001", evidence_type="earnings")
    with pytest.raises(ValueError, match="Duplicate evidence_id 'evid-1' in dossier"):
        CandidateDossier(snapshot=snap, evidence=(ev1, ev2))

    # Duplicate reason_id
    r1 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", evaluation_id="eval-1", dimension=CandidateDimension.CONTEXT, reason_code="R1", human_text="text1")
    r2 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", evaluation_id="eval-1", dimension=CandidateDimension.CONTEXT, reason_code="R2", human_text="text2")
    with pytest.raises(ValueError, match="Duplicate reason_id 'reas-1' in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), reasons=(r1, r2))

    # Duplicate record_id
    m1 = CandidateMissingData(record_id="miss-1", candidate_id="cand-001", input_name="i1", data_family="f1", status=MissingDataStatus.UNKNOWN)
    m2 = CandidateMissingData(record_id="miss-1", candidate_id="cand-001", input_name="i2", data_family="f2", status=MissingDataStatus.UNKNOWN)
    with pytest.raises(ValueError, match="Duplicate record_id 'miss-1' in dossier"):
        CandidateDossier(snapshot=snap, missing_data=(m1, m2))


def test_candidate_dossier_canonical_child_ordering() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)

    e_b = CandidateEvaluation(evaluation_id="eval-b", candidate_id="cand-001", evaluator_id="ev", evaluator_version="1", evidence_state="e")
    e_a = CandidateEvaluation(evaluation_id="eval-a", candidate_id="cand-001", evaluator_id="ev", evaluator_version="1", evidence_state="e")

    ev_z = CandidateEvidence(evidence_id="evid-z", candidate_id="cand-001", evidence_type="t")
    ev_a = CandidateEvidence(evidence_id="evid-a", candidate_id="cand-001", evidence_type="t")

    r_2 = CandidateReason(reason_id="reas-2", candidate_id="cand-001", evaluation_id="eval-a", dimension=CandidateDimension.CONTEXT, reason_code="R2", human_text="t")
    r_1 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", evaluation_id="eval-a", dimension=CandidateDimension.CONTEXT, reason_code="R1", human_text="t")

    m_y = CandidateMissingData(record_id="miss-y", candidate_id="cand-001", input_name="n", data_family="d", status=MissingDataStatus.UNKNOWN)
    m_x = CandidateMissingData(record_id="miss-x", candidate_id="cand-001", input_name="n", data_family="d", status=MissingDataStatus.UNKNOWN)

    # Pass in non-sorted order
    dossier = CandidateDossier(
        snapshot=snap,
        evaluations=(e_b, e_a),
        evidence=(ev_z, ev_a),
        reasons=(r_2, r_1),
        missing_data=(m_y, m_x),
    )

    assert [e.evaluation_id for e in dossier.evaluations] == ["eval-a", "eval-b"]
    assert [ev.evidence_id for ev in dossier.evidence] == ["evid-a", "evid-z"]
    assert [r.reason_id for r in dossier.reasons] == ["reas-1", "reas-2"]
    assert [m.record_id for m in dossier.missing_data] == ["miss-x", "miss-y"]


def test_no_actionable_candidate_state_in_models() -> None:
    """Invariance check: Candidate domain must not export actionable trading states."""
    import tradex.candidates.models as mod

    assert not hasattr(mod, "CandidateState")
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and issubclass(obj, (str, bytes)):
            # Check string enum members
            for member in getattr(obj, "__members__", {}).values():
                val = str(member.value).lower()
                assert val not in {
                    "enter_now",
                    "armed",
                    "waitlist",
                    "watchlist_candidate",
                    "quarantined_earnings",
                    "invalidated",
                    "expired",
                }


# ============================================================================
# BLOCKER 1: Point-In-Time (PIT) Temporal Integrity Tests
# ============================================================================


def test_pit_temporal_integrity_evidence_and_missing_data() -> None:
    decision_ts = datetime(2026, 8, 21, 14, 30, 0, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-pit-1", symbol="AAPL", decision_timestamp=decision_ts)

    # 1. Evidence observed strictly before decision -> accepted
    ev_before = CandidateEvidence(
        evidence_id="evid-before",
        candidate_id="cand-pit-1",
        evidence_type="ohlcv",
        observed_at=decision_ts - timedelta(minutes=5),
    )
    d1 = CandidateDossier(snapshot=snap, evidence=(ev_before,))
    assert len(d1.evidence) == 1

    # 2. Evidence observed exactly at decision timestamp -> accepted (<=)
    ev_exact = CandidateEvidence(
        evidence_id="evid-exact",
        candidate_id="cand-pit-1",
        evidence_type="ohlcv",
        observed_at=decision_ts,
    )
    d2 = CandidateDossier(snapshot=snap, evidence=(ev_exact,))
    assert len(d2.evidence) == 1

    # 3. Evidence observed after decision timestamp -> rejected with ValueError
    ev_future = CandidateEvidence(
        evidence_id="evid-future",
        candidate_id="cand-pit-1",
        evidence_type="ohlcv",
        observed_at=decision_ts + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="is after candidate decision_timestamp.*future observations are rejected"):
        CandidateDossier(snapshot=snap, evidence=(ev_future,))

    # 4. MissingData observed strictly before decision -> accepted
    miss_before = CandidateMissingData(
        record_id="miss-before",
        candidate_id="cand-pit-1",
        input_name="options",
        data_family="options",
        status=MissingDataStatus.UNKNOWN,
        observed_at=decision_ts - timedelta(minutes=1),
    )
    d3 = CandidateDossier(snapshot=snap, missing_data=(miss_before,))
    assert len(d3.missing_data) == 1

    # 5. MissingData observed exactly at decision timestamp -> accepted (<=)
    miss_exact = CandidateMissingData(
        record_id="miss-exact",
        candidate_id="cand-pit-1",
        input_name="options",
        data_family="options",
        status=MissingDataStatus.UNKNOWN,
        observed_at=decision_ts,
    )
    d4 = CandidateDossier(snapshot=snap, missing_data=(miss_exact,))
    assert len(d4.missing_data) == 1

    # 6. MissingData observed after decision timestamp -> rejected with ValueError
    miss_future = CandidateMissingData(
        record_id="miss-future",
        candidate_id="cand-pit-1",
        input_name="options",
        data_family="options",
        status=MissingDataStatus.UNKNOWN,
        observed_at=decision_ts + timedelta(seconds=5),
    )
    with pytest.raises(ValueError, match="is after candidate decision_timestamp.*future observations are rejected"):
        CandidateDossier(snapshot=snap, missing_data=(miss_future,))

    # 7. observed_at = None is accepted (unspecified observation time)
    ev_none = CandidateEvidence(
        evidence_id="evid-none",
        candidate_id="cand-pit-1",
        evidence_type="filings",
        observed_at=None,
    )
    miss_none = CandidateMissingData(
        record_id="miss-none",
        candidate_id="cand-pit-1",
        input_name="shares",
        data_family="fundamentals",
        status=MissingDataStatus.NOT_REQUESTED,
        observed_at=None,
    )
    d5 = CandidateDossier(snapshot=snap, evidence=(ev_none,), missing_data=(miss_none,))
    assert len(d5.evidence) == 1
    assert len(d5.missing_data) == 1


def test_pit_temporal_integrity_timezone_normalization() -> None:
    eastern = ZoneInfo("America/New_York")
    tokyo = ZoneInfo("Asia/Tokyo")

    # Decision at 9:30 AM EDT on 2026-08-21 (which is 13:30:00 UTC)
    decision_dt = datetime(2026, 8, 21, 9, 30, 0, tzinfo=eastern)
    snap = CandidateSnapshot(candidate_id="cand-tz-1", symbol="AAPL", decision_timestamp=decision_dt)

    # Observation in Tokyo timezone at 22:29:00 (13:29:00 UTC) -> accepted (before)
    obs_tokyo_before = datetime(2026, 8, 21, 22, 29, 0, tzinfo=tokyo)
    ev_tokyo = CandidateEvidence(
        evidence_id="evid-tokyo",
        candidate_id="cand-tz-1",
        evidence_type="ohlcv",
        observed_at=obs_tokyo_before,
    )
    d = CandidateDossier(snapshot=snap, evidence=(ev_tokyo,))
    assert len(d.evidence) == 1

    # Observation in Tokyo timezone at 22:31:00 (13:31:00 UTC) -> rejected (after)
    obs_tokyo_future = datetime(2026, 8, 21, 22, 31, 0, tzinfo=tokyo)
    ev_future = CandidateEvidence(
        evidence_id="evid-tokyo-fut",
        candidate_id="cand-tz-1",
        evidence_type="ohlcv",
        observed_at=obs_tokyo_future,
    )
    with pytest.raises(ValueError, match="is after candidate decision_timestamp"):
        CandidateDossier(snapshot=snap, evidence=(ev_future,))


def test_pit_created_at_later_allowed() -> None:
    decision_ts = datetime(2026, 8, 21, 14, 30, 0, tzinfo=UTC)
    # created_at is persistence audit timestamp and may be created after decision_timestamp
    created_ts = decision_ts + timedelta(hours=2)

    snap = CandidateSnapshot(
        candidate_id="cand-audit-1",
        symbol="AAPL",
        decision_timestamp=decision_ts,
        created_at=created_ts,
    )
    ev = CandidateEvidence(
        evidence_id="evid-audit-1",
        candidate_id="cand-audit-1",
        evidence_type="ohlcv",
        observed_at=decision_ts,
        created_at=created_ts,
    )
    dossier = CandidateDossier(snapshot=snap, evidence=(ev,))
    assert dossier.snapshot.created_at == created_ts
    assert dossier.evidence[0].created_at == created_ts


# ============================================================================
# BLOCKER 2: Model Round-Trip & Deterministic Normalization Tests
# ============================================================================


def test_enum_normalization_exhaustive() -> None:
    # 1. SecurityIdentityStatus on CandidateSnapshot
    snap1 = CandidateSnapshot(
        candidate_id="c1",
        symbol="AAPL",
        decision_timestamp=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
        security_identity_status="unknown",
    )
    assert snap1.security_identity_status == SecurityIdentityStatus.UNKNOWN
    assert isinstance(snap1.security_identity_status, SecurityIdentityStatus)

    snap2 = CandidateSnapshot(
        candidate_id="c2",
        symbol="AAPL",
        decision_timestamp=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
        security_identity_version="v1",
        security_identity_status=" KNOWN ",
    )
    assert snap2.security_identity_status == SecurityIdentityStatus.KNOWN
    assert isinstance(snap2.security_identity_status, SecurityIdentityStatus)

    with pytest.raises(TypeError, match="security_identity_status must be a SecurityIdentityStatus instance or str"):
        CandidateSnapshot(
            candidate_id="c3",
            symbol="AAPL",
            decision_timestamp=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
            security_identity_status=True,  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="security_identity_status must be a SecurityIdentityStatus instance or str"):
        CandidateSnapshot(
            candidate_id="c4",
            symbol="AAPL",
            decision_timestamp=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
            security_identity_status=1,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="Unknown SecurityIdentityStatus"):
        CandidateSnapshot(
            candidate_id="c5",
            symbol="AAPL",
            decision_timestamp=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
            security_identity_status="not_a_status",
        )

    # 2. ReasonPolarity on CandidateReason
    r_pol = CandidateReason(
        reason_id="r1",
        candidate_id="c1",
        evaluation_id="e1",
        dimension=CandidateDimension.SETUP_QUALITY,
        reason_code="R1",
        human_text="t",
        polarity=" SUPPORTING ",
    )
    assert r_pol.polarity == ReasonPolarity.SUPPORTING
    assert isinstance(r_pol.polarity, ReasonPolarity)

    with pytest.raises(TypeError, match="polarity must be a ReasonPolarity instance or str"):
        CandidateReason(
            reason_id="r2",
            candidate_id="c1",
            evaluation_id="e1",
            dimension=CandidateDimension.SETUP_QUALITY,
            reason_code="R1",
            human_text="t",
            polarity=123,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="Unknown ReasonPolarity"):
        CandidateReason(
            reason_id="r3",
            candidate_id="c1",
            evaluation_id="e1",
            dimension=CandidateDimension.SETUP_QUALITY,
            reason_code="R1",
            human_text="t",
            polarity="invalid_polarity",
        )

    # 3. ReasonSeverity on CandidateReason
    r_sev = CandidateReason(
        reason_id="r4",
        candidate_id="c1",
        evaluation_id="e1",
        dimension=CandidateDimension.SETUP_QUALITY,
        reason_code="R1",
        human_text="t",
        severity=" CRITICAL ",
    )
    assert r_sev.severity == ReasonSeverity.CRITICAL
    assert isinstance(r_sev.severity, ReasonSeverity)

    with pytest.raises(TypeError, match="severity must be a ReasonSeverity instance or str"):
        CandidateReason(
            reason_id="r5",
            candidate_id="c1",
            evaluation_id="e1",
            dimension=CandidateDimension.SETUP_QUALITY,
            reason_code="R1",
            human_text="t",
            severity=False,  # type: ignore[arg-type]
        )

    # 4. MissingDataStatus on CandidateMissingData
    for status in MissingDataStatus:
        m = CandidateMissingData(
            record_id=f"m-{status.value}",
            candidate_id="c1",
            input_name="inp",
            data_family="fam",
            status=status.value.upper(),
        )
        assert m.status == status
        assert isinstance(m.status, MissingDataStatus)

    with pytest.raises(TypeError, match="status must be a MissingDataStatus instance or str"):
        CandidateMissingData(
            record_id="m-bad-type",
            candidate_id="c1",
            input_name="inp",
            data_family="fam",
            status=3.14,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="Unknown MissingDataStatus"):
        CandidateMissingData(
            record_id="m-bad-val",
            candidate_id="c1",
            input_name="inp",
            data_family="fam",
            status="not_a_valid_missing_status",
        )


def test_json_canonicalization_and_type_rejection() -> None:
    # 1. CandidateDimension keys converted to canonical string keys
    e1 = CandidateEvaluation(
        evaluation_id="e1",
        candidate_id="c1",
        evaluator_id="ev",
        evaluator_version="1",
        evidence_state="e",
        dimensions={
            CandidateDimension.SETUP_QUALITY: {"score": 85},
            CandidateDimension.DATA_CONFIDENCE: {"conf": 0.9},
        },
    )
    assert e1.dimensions == {
        "setup_quality": {"score": 85},
        "data_confidence": {"conf": 0.9},
    }

    # 2. Nested tuples normalized to lists
    ev1 = CandidateEvidence(
        evidence_id="ev1",
        candidate_id="c1",
        evidence_type="ohlcv",
        metadata={"bars": (10, 20, 30), "nested": {"coords": (1.1, 2.2)}},
    )
    assert ev1.metadata == {"bars": [10, 20, 30], "nested": {"coords": [1.1, 2.2]}}

    # 3. Non-string / non-CandidateDimension keys rejected with TypeError
    with pytest.raises(TypeError, match="dictionary keys must be str or CandidateDimension"):
        CandidateEvaluation(
            evaluation_id="e2",
            candidate_id="c1",
            evaluator_id="ev",
            evaluator_version="1",
            evidence_state="e",
            dimensions={123: "bad key"},  # type: ignore[dict-item]
        )

    with pytest.raises(TypeError, match="dictionary keys must be str or CandidateDimension"):
        CandidateEvidence(
            evidence_id="ev2",
            candidate_id="c1",
            evidence_type="ohlcv",
            metadata={"nested": {(1, 2): "tuple key"}},  # type: ignore[dict-item]
        )

    with pytest.raises(TypeError, match="dictionary keys must be str or CandidateDimension"):
        CandidateEvaluation(
            evaluation_id="e3",
            candidate_id="c1",
            evaluator_id="ev",
            evaluator_version="1",
            evidence_state="e",
            dimensions={True: "bool key"},  # type: ignore[dict-item]
        )

    # 4. Non-serializable objects rejected
    class CustomObject:
        pass

    with pytest.raises(ValueError, match="without NaN/Infinity"):
        CandidateEvidence(
            evidence_id="ev3",
            candidate_id="c1",
            evidence_type="ohlcv",
            metadata={"obj": CustomObject()},
        )


def test_dimensions_and_metadata_must_be_dict() -> None:
    with pytest.raises(TypeError, match="dimensions must be a dict"):
        CandidateEvaluation(
            evaluation_id="e1",
            candidate_id="c1",
            evaluator_id="ev",
            evaluator_version="1",
            evidence_state="e",
            dimensions=["not", "a", "dict"],  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="metadata must be a dict"):
        CandidateEvidence(
            evidence_id="ev1",
            candidate_id="c1",
            evidence_type="ohlcv",
            metadata="not a dict",  # type: ignore[arg-type]
        )
