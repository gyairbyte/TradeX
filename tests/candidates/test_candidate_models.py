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
    assert reason.dimension == "context"
    assert reason.human_text == "Sector ETF showed relative strength (+1.8%)."


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

    # Reason referencing non-existent evaluation in dossier
    reas_bad = CandidateReason(
        reason_id="reas-002",
        candidate_id="cand-001",
        evaluation_id="eval-nonexistent",
        reason_code="R2",
        human_text="Bad eval link",
    )
    with pytest.raises(ValueError, match="does not match any evaluation in dossier"):
        CandidateDossier(snapshot=snap, evaluations=(eval1,), reasons=(reas_bad,))

    # Reason referencing non-existent evidence in dossier
    reas_bad_ev = CandidateReason(
        reason_id="reas-003",
        candidate_id="cand-001",
        reason_code="R3",
        human_text="Bad evid link",
        source_evidence_id="evid-nonexistent",
    )
    with pytest.raises(ValueError, match="does not match any evidence in dossier"):
        CandidateDossier(snapshot=snap, evidence=(evid1,), reasons=(reas_bad_ev,))


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
