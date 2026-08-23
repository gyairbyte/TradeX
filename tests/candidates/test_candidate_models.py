import math
from datetime import UTC, datetime
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

    # Reject NaN
    with pytest.raises(ValueError, match="non-finite"):
        CandidateEvaluation(
            evaluation_id="eval-002",
            candidate_id="cand-001",
            evaluator_id="research_evaluator",
            evaluator_version="0.1.0",
            evidence_state="research_only",
            dimensions={"score": float("nan")},
        )

    # Reject Infinity
    with pytest.raises(ValueError, match="non-finite"):
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
        polarity=ReasonPolarity.SUPPORTING,
        severity=ReasonSeverity.INFO,
        human_text="Sector ETF showed relative strength (+1.8%).",
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
            reason_code="R1",
            human_text="text",
            dimension=dim,
        )
        assert r.dimension == dim

    # String normalization to enum
    r_str = CandidateReason(
        reason_id="reas-str",
        candidate_id="cand-001",
        reason_code="R1",
        human_text="text",
        dimension=" SETUP_QUALITY ",
    )
    assert r_str.dimension == CandidateDimension.SETUP_QUALITY

    # None and empty string
    r_none = CandidateReason(
        reason_id="reas-none",
        candidate_id="cand-001",
        reason_code="R1",
        human_text="text",
        dimension=None,
    )
    assert r_none.dimension is None

    r_empty = CandidateReason(
        reason_id="reas-empty",
        candidate_id="cand-001",
        reason_code="R1",
        human_text="text",
        dimension="   ",
    )
    assert r_empty.dimension is None

    # Unknown string rejected
    with pytest.raises(ValueError, match="Unknown CandidateDimension"):
        CandidateReason(
            reason_id="reas-bad",
            candidate_id="cand-001",
            reason_code="R1",
            human_text="text",
            dimension="unsupported_dimension",
        )

    # Invalid type rejected
    with pytest.raises(TypeError, match="dimension must be CandidateDimension or str"):
        CandidateReason(
            reason_id="reas-bad-type",
            candidate_id="cand-001",
            reason_code="R1",
            human_text="text",
            dimension=123,  # type: ignore[arg-type]
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
        reason_code="R2",
        human_text="Bad eval link",
    )
    with pytest.raises(ValueError, match="does not match any evaluation in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), reasons=(reas_bad,))

    # Reason referencing non-existent evidence in dossier (with non-empty evidence)
    reas_bad_ev = CandidateReason(
        reason_id="reas-003",
        candidate_id="cand-001",
        reason_code="R3",
        human_text="Bad evid link",
        source_evidence_id="evid-nonexistent",
    )
    with pytest.raises(ValueError, match="does not match any evidence in dossier"):
        CandidateDossier(snapshot=snap, evidence=(evid1,), reasons=(reas_bad_ev,))


def test_candidate_dossier_unconditional_referential_integrity_empty_collections() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)

    # Reason with evaluation_id when evaluations is EMPTY must fail unconditionally
    reas_dangling_eval = CandidateReason(
        reason_id="reas-001",
        candidate_id="cand-001",
        evaluation_id="eval-missing",
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
        reason_code="R2",
        human_text="Dangling evid reference",
        source_evidence_id="evid-missing",
    )
    with pytest.raises(ValueError, match="Reason source_evidence_id 'evid-missing' does not match any evidence in dossier"):
        CandidateDossier(snapshot=snap, evidence=(), reasons=(reas_dangling_evid,))


def test_candidate_dossier_duplicate_child_ids_rejected() -> None:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-001", symbol="AAPL", decision_timestamp=dt)

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
    r1 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", reason_code="R1", human_text="text1")
    r2 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", reason_code="R2", human_text="text2")
    with pytest.raises(ValueError, match="Duplicate reason_id 'reas-1' in dossier"):
        CandidateDossier(snapshot=snap, reasons=(r1, r2))

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

    r_2 = CandidateReason(reason_id="reas-2", candidate_id="cand-001", reason_code="R2", human_text="t")
    r_1 = CandidateReason(reason_id="reas-1", candidate_id="cand-001", reason_code="R1", human_text="t")

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
