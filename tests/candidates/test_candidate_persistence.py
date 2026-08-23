"""Unit tests for candidate persistence primitives (signals.db schema v4)."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

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
    get_candidate,
    get_candidate_dossier,
    list_candidates,
    record_candidate_dossier,
)
from tradex.tracker import store


@pytest.fixture
def candidate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_signals.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init(db_path)
    return db_path


def _make_sample_dossier(candidate_id: str = "cand-001", symbol: str = "AAPL") -> CandidateDossier:
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(
        candidate_id=candidate_id,
        symbol=symbol,
        decision_timestamp=dt,
        contract_version=1,
        trading_date="2026-08-21",
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )
    eval1 = CandidateEvaluation(
        evaluation_id=f"eval-{candidate_id}-1",
        candidate_id=candidate_id,
        evaluator_id="research_scorer",
        evaluator_version="1.0.0",
        evidence_state="research_only",
        dimensions={
            CandidateDimension.SETUP_QUALITY: {"score": 82},
            CandidateDimension.DATA_CONFIDENCE: {"confidence": 0.95},
        },
    )
    evid1 = CandidateEvidence(
        evidence_id=f"evid-{candidate_id}-1",
        candidate_id=candidate_id,
        evidence_type="ohlcv",
        source_ref_type="scan_session",
        source_ref_id="session-xyz-123",
        provider="schwab",
        observed_at=dt - timedelta(minutes=5),
        metadata={"bars": 60, "timeframe": "intraday"},
    )
    reason1 = CandidateReason(
        reason_id=f"reas-{candidate_id}-1",
        candidate_id=candidate_id,
        evaluation_id=f"eval-{candidate_id}-1",
        dimension=CandidateDimension.SETUP_QUALITY,
        reason_code="VOL_SURGE",
        polarity=ReasonPolarity.SUPPORTING,
        severity=ReasonSeverity.INFO,
        human_text="Volume ratio > 2.0x 20-day average. ΔP > 1.5%",
        source_evidence_id=f"evid-{candidate_id}-1",
    )
    missing1 = CandidateMissingData(
        record_id=f"miss-{candidate_id}-1",
        candidate_id=candidate_id,
        evaluation_id=f"eval-{candidate_id}-1",
        input_name="options_flow",
        data_family="options",
        status=MissingDataStatus.NOT_REQUESTED,
        detail="Options data was not requested for this study",
    )
    return CandidateDossier(
        snapshot=snap,
        evaluations=(eval1,),
        evidence=(evid1,),
        reasons=(reason1,),
        missing_data=(missing1,),
    )


def test_record_and_get_candidate_dossier_round_trip(candidate_db) -> None:
    dossier = _make_sample_dossier("cand-100", "MSFT")
    saved = record_candidate_dossier(dossier, candidate_db)
    assert saved == dossier

    retrieved = get_candidate_dossier("cand-100", candidate_db)
    assert retrieved is not None
    assert retrieved.snapshot == dossier.snapshot
    assert retrieved.evaluations == dossier.evaluations
    assert retrieved.evidence == dossier.evidence
    assert retrieved.reasons == dossier.reasons
    assert retrieved.missing_data == dossier.missing_data


def test_get_candidate_header_only(candidate_db) -> None:
    dossier = _make_sample_dossier("cand-200", "NVDA")
    record_candidate_dossier(dossier, candidate_db)

    snap = get_candidate("cand-200", candidate_db)
    assert snap is not None
    assert snap == dossier.snapshot


def test_get_candidate_nonexistent(candidate_db) -> None:
    assert get_candidate("does-not-exist", candidate_db) is None
    assert get_candidate_dossier("does-not-exist", candidate_db) is None


def test_multiple_evaluators_and_unicode_reasons(candidate_db) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
    cand_id = "cand-300"
    snap = CandidateSnapshot(candidate_id=cand_id, symbol="TSLA", decision_timestamp=dt)

    eval1 = CandidateEvaluation(
        evaluation_id="eval-300-a",
        candidate_id=cand_id,
        evaluator_id="eval_a",
        evaluator_version="1.0",
        evidence_state="exploratory",
    )
    eval2 = CandidateEvaluation(
        evaluation_id="eval-300-b",
        candidate_id=cand_id,
        evaluator_id="eval_b",
        evaluator_version="2.0",
        evidence_state="shadow",
    )

    reason1 = CandidateReason(
        reason_id="reas-300-1",
        candidate_id=cand_id,
        evaluation_id="eval-300-a",
        dimension=CandidateDimension.CONTEXT,
        reason_code="UNICODE_TEST",
        human_text="Greek symbols α, β, γ and emojis 🚀 📈 with accents é, à, ü.",
    )

    dossier = CandidateDossier(
        snapshot=snap,
        evaluations=(eval1, eval2),
        reasons=(reason1,),
    )
    record_candidate_dossier(dossier, candidate_db)

    retrieved = get_candidate_dossier(cand_id, candidate_db)
    assert retrieved is not None
    assert len(retrieved.evaluations) == 2
    assert {e.evaluator_id for e in retrieved.evaluations} == {"eval_a", "eval_b"}
    assert retrieved.reasons[0].human_text == "Greek symbols α, β, γ and emojis 🚀 📈 with accents é, à, ü."


def test_missing_data_taxonomy_persistence(candidate_db) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
    cand_id = "cand-400"
    snap = CandidateSnapshot(candidate_id=cand_id, symbol="GOOGL", decision_timestamp=dt)

    missing_items = []
    for idx, status in enumerate(MissingDataStatus):
        missing_items.append(
            CandidateMissingData(
                record_id=f"miss-400-{idx}",
                candidate_id=cand_id,
                input_name=f"input_{status.value}",
                data_family="market_data",
                status=status,
                detail=f"Testing status {status.value}",
            )
        )

    dossier = CandidateDossier(snapshot=snap, missing_data=tuple(missing_items))
    record_candidate_dossier(dossier, candidate_db)

    retrieved = get_candidate_dossier(cand_id, candidate_db)
    assert retrieved is not None
    assert len(retrieved.missing_data) == len(MissingDataStatus)
    persisted_statuses = {m.status for m in retrieved.missing_data}
    assert persisted_statuses == set(MissingDataStatus)


def test_multi_provider_evidence_persistence(candidate_db) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
    cand_id = "cand-500"
    snap = CandidateSnapshot(candidate_id=cand_id, symbol="AMZN", decision_timestamp=dt)

    ev1 = CandidateEvidence(
        evidence_id="evid-500-1",
        candidate_id=cand_id,
        evidence_type="ohlcv",
        provider="schwab",
        metadata={"feed": "primary"},
    )
    ev2 = CandidateEvidence(
        evidence_id="evid-500-2",
        candidate_id=cand_id,
        evidence_type="premarket_bars",
        provider="yahoo",
        metadata={"gap_pct": 3.2},
    )
    ev3 = CandidateEvidence(
        evidence_id="evid-500-3",
        candidate_id=cand_id,
        evidence_type="earnings",
        provider="sec_edgar",
        metadata={"filing_form": "10-Q"},
    )

    dossier = CandidateDossier(snapshot=snap, evidence=(ev1, ev2, ev3))
    record_candidate_dossier(dossier, candidate_db)

    retrieved = get_candidate_dossier(cand_id, candidate_db)
    assert retrieved is not None
    assert len(retrieved.evidence) == 3
    providers = {ev.provider for ev in retrieved.evidence}
    assert providers == {"schwab", "yahoo", "sec_edgar"}


def test_exact_replay_is_idempotent(candidate_db) -> None:
    dossier = _make_sample_dossier("cand-600", "META")
    res1 = record_candidate_dossier(dossier, candidate_db)
    res2 = record_candidate_dossier(dossier, candidate_db)

    assert res1 == dossier
    assert res2 == dossier

    with sqlite3.connect(candidate_db) as con:
        count = con.execute("SELECT COUNT(*) FROM candidates WHERE candidate_id = 'cand-600'").fetchone()[0]
        assert count == 1


def test_conflicting_candidate_id_fails(candidate_db) -> None:
    dossier1 = _make_sample_dossier("cand-700", "META")
    record_candidate_dossier(dossier1, candidate_db)

    # Different symbol with same candidate_id
    dossier2 = _make_sample_dossier("cand-700", "AAPL")
    with pytest.raises(store.StoreError, match="already exists with divergent immutable content"):
        record_candidate_dossier(dossier2, candidate_db)


def test_child_insert_failure_rolls_back(candidate_db) -> None:
    dossier = _make_sample_dossier("cand-800", "NFLX")

    with sqlite3.connect(candidate_db) as con:
        con.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_child_fail "
            "BEFORE INSERT ON candidate_evaluations "
            "BEGIN SELECT RAISE(ABORT, 'injected evaluation insert failure'); END;"
        )

    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="injected evaluation insert failure"):
        record_candidate_dossier(dossier, candidate_db)

    # Invariants: No partial candidate header exists in DB
    snap = get_candidate("cand-800", candidate_db)
    assert snap is None

    with sqlite3.connect(candidate_db) as con:
        cand_count = con.execute("SELECT COUNT(*) FROM candidates WHERE candidate_id = 'cand-800'").fetchone()[0]
        eval_count = con.execute("SELECT COUNT(*) FROM candidate_evaluations WHERE candidate_id = 'cand-800'").fetchone()[0]
        assert cand_count == 0
        assert eval_count == 0


def test_list_candidates_filters_and_neutral_order(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)

    d1 = CandidateDossier(snapshot=CandidateSnapshot(candidate_id="cand-list-1", symbol="AAPL", decision_timestamp=t0))
    d2 = CandidateDossier(snapshot=CandidateSnapshot(candidate_id="cand-list-2", symbol="MSFT", decision_timestamp=t1))
    d3 = CandidateDossier(snapshot=CandidateSnapshot(candidate_id="cand-list-3", symbol="AAPL", decision_timestamp=t2))

    record_candidate_dossier(d1, candidate_db)
    record_candidate_dossier(d2, candidate_db)
    record_candidate_dossier(d3, candidate_db)

    # All candidates ordered by decision_timestamp DESC
    all_cands = list_candidates(db_path=candidate_db)
    assert [c.candidate_id for c in all_cands] == ["cand-list-3", "cand-list-2", "cand-list-1"]

    # Filter by symbol
    aapl_cands = list_candidates(symbol="AAPL", db_path=candidate_db)
    assert [c.candidate_id for c in aapl_cands] == ["cand-list-3", "cand-list-1"]

    # Filter by trading date
    date_cands = list_candidates(trading_date="2026-08-21", db_path=candidate_db)
    assert len(date_cands) == 3

    # Filter by time range
    mid_cands = list_candidates(start_time=t0 + timedelta(minutes=30), end_time=t1 + timedelta(minutes=30), db_path=candidate_db)
    assert [c.candidate_id for c in mid_cands] == ["cand-list-2"]

    # Limit
    limited = list_candidates(limit=2, db_path=candidate_db)
    assert len(limited) == 2
    assert [c.candidate_id for c in limited] == ["cand-list-3", "cand-list-2"]

    with pytest.raises(ValueError, match="positive integer"):
        list_candidates(limit=0, db_path=candidate_db)


def test_existing_legacy_tables_unaffected_by_candidate_writes(candidate_db) -> None:
    # Verify legacy tables exist and remain untouched
    with sqlite3.connect(candidate_db) as con:
        con.execute(
            """
            INSERT INTO signal_history (ticker, timeframe, scan_time, score)
            VALUES ('SPY', 'intraday', '2026-08-21T14:00:00Z', 70)
            """
        )
        con.commit()

    dossier = _make_sample_dossier("cand-900", "SPY")
    record_candidate_dossier(dossier, candidate_db)

    with sqlite3.connect(candidate_db) as con:
        sh_rows = con.execute("SELECT * FROM signal_history WHERE ticker = 'SPY'").fetchall()
        assert len(sh_rows) == 1
        assert sh_rows[0][4] == 70  # score


def test_reconstructed_retry_with_different_created_at_is_idempotent(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    t_created_1 = datetime(2026, 8, 21, 14, 30, 1, tzinfo=UTC)
    t_created_2 = datetime(2026, 8, 21, 14, 30, 5, tzinfo=UTC)

    snap1 = CandidateSnapshot(
        candidate_id="cand-retry-1",
        symbol="AAPL",
        decision_timestamp=t0,
        created_at=t_created_1,
    )
    eval1 = CandidateEvaluation(
        evaluation_id="eval-retry-1",
        candidate_id="cand-retry-1",
        evaluator_id="scorer",
        evaluator_version="1.0",
        evidence_state="exploratory",
        created_at=t_created_1,
    )
    dossier1 = CandidateDossier(snapshot=snap1, evaluations=(eval1,))
    saved1 = record_candidate_dossier(dossier1, candidate_db)

    # Reconstructed retry with different created_at
    snap2 = CandidateSnapshot(
        candidate_id="cand-retry-1",
        symbol="AAPL",
        decision_timestamp=t0,
        created_at=t_created_2,
    )
    eval2 = CandidateEvaluation(
        evaluation_id="eval-retry-1",
        candidate_id="cand-retry-1",
        evaluator_id="scorer",
        evaluator_version="1.0",
        evidence_state="exploratory",
        created_at=t_created_2,
    )
    dossier2 = CandidateDossier(snapshot=snap2, evaluations=(eval2,))
    saved2 = record_candidate_dossier(dossier2, candidate_db)

    assert saved1 == saved2
    assert saved2.snapshot.created_at == t_created_1
    assert saved2.evaluations[0].created_at == t_created_1


def test_replay_with_noncanonical_tuple_order_succeeds_idempotently(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-order-1", symbol="AAPL", decision_timestamp=t0)

    e1 = CandidateEvaluation(evaluation_id="eval-1", candidate_id="cand-order-1", evaluator_id="ev1", evaluator_version="1", evidence_state="e")
    e2 = CandidateEvaluation(evaluation_id="eval-2", candidate_id="cand-order-1", evaluator_id="ev2", evaluator_version="1", evidence_state="e")

    # First write with (e1, e2)
    dossier1 = CandidateDossier(snapshot=snap, evaluations=(e1, e2))
    saved1 = record_candidate_dossier(dossier1, candidate_db)

    # Replay with reversed order (e2, e1)
    dossier2 = CandidateDossier(snapshot=snap, evaluations=(e2, e1))
    saved2 = record_candidate_dossier(dossier2, candidate_db)

    assert saved1 == saved2
    assert [e.evaluation_id for e in saved2.evaluations] == ["eval-1", "eval-2"]


def test_material_divergence_raises_store_error_conflict(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    snap = CandidateSnapshot(candidate_id="cand-div-1", symbol="AAPL", decision_timestamp=t0)
    e1 = CandidateEvaluation(evaluation_id="eval-1", candidate_id="cand-div-1", evaluator_id="ev1", evaluator_version="1", evidence_state="e", dimensions={"score": 50})
    ev1 = CandidateEvidence(evidence_id="evid-1", candidate_id="cand-div-1", evidence_type="ohlcv", provider="schwab")
    r1 = CandidateReason(reason_id="reas-1", candidate_id="cand-div-1", evaluation_id="eval-1", dimension=CandidateDimension.SETUP_QUALITY, reason_code="R1", human_text="Text 1")
    m1 = CandidateMissingData(record_id="miss-1", candidate_id="cand-div-1", input_name="i1", data_family="f1", status=MissingDataStatus.UNKNOWN, detail="det1")

    dossier = CandidateDossier(snapshot=snap, evaluations=(e1,), evidence=(ev1,), reasons=(r1,), missing_data=(m1,))
    record_candidate_dossier(dossier, candidate_db)

    # Divergent evaluation dimension
    e_div = CandidateEvaluation(evaluation_id="eval-1", candidate_id="cand-div-1", evaluator_id="ev1", evaluator_version="1", evidence_state="e", dimensions={"score": 90})
    with pytest.raises(store.StoreError, match="already exists with divergent immutable content"):
        record_candidate_dossier(CandidateDossier(snapshot=snap, evaluations=(e_div,), evidence=(ev1,), reasons=(r1,), missing_data=(m1,)), candidate_db)

    # Divergent evidence provider
    ev_div = CandidateEvidence(evidence_id="evid-1", candidate_id="cand-div-1", evidence_type="ohlcv", provider="alpaca")
    with pytest.raises(store.StoreError, match="already exists with divergent immutable content"):
        record_candidate_dossier(CandidateDossier(snapshot=snap, evaluations=(e1,), evidence=(ev_div,), reasons=(r1,), missing_data=(m1,)), candidate_db)

    # Divergent reason human text
    r_div = CandidateReason(reason_id="reas-1", candidate_id="cand-div-1", evaluation_id="eval-1", dimension=CandidateDimension.SETUP_QUALITY, reason_code="R1", human_text="Different text")
    with pytest.raises(store.StoreError, match="already exists with divergent immutable content"):
        record_candidate_dossier(CandidateDossier(snapshot=snap, evaluations=(e1,), evidence=(ev1,), reasons=(r_div,), missing_data=(m1,)), candidate_db)

    # Divergent missing data status
    m_div = CandidateMissingData(record_id="miss-1", candidate_id="cand-div-1", input_name="i1", data_family="f1", status=MissingDataStatus.PROVIDER_FAILED, detail="det1")
    with pytest.raises(store.StoreError, match="already exists with divergent immutable content"):
        record_candidate_dossier(CandidateDossier(snapshot=snap, evaluations=(e1,), evidence=(ev1,), reasons=(r1,), missing_data=(m_div,)), candidate_db)


def test_sqlite_source_evidence_fk_enforcement(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC).isoformat()
    with sqlite3.connect(candidate_db) as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute(
            "INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, created_at) "
            "VALUES ('cand-fk-1', 1, 'AAPL', ?, ?)",
            (t0, t0),
        )
        con.execute(
            "INSERT INTO candidate_evaluations (evaluation_id, candidate_id, evaluator_id, evaluator_version, evidence_state, created_at) "
            "VALUES ('eval-fk-1', 'cand-fk-1', 'ev1', '1.0', 'exploratory', ?)",
            (t0,),
        )
        con.commit()

        # Insert reason with non-existent source_evidence_id under PRAGMA foreign_keys = ON
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            con.execute(
                "INSERT INTO candidate_reasons (reason_id, candidate_id, evaluation_id, dimension, reason_code, human_text, source_evidence_id, created_at) "
                "VALUES ('reas-fk-1', 'cand-fk-1', 'eval-fk-1', 'context', 'R1', 'test text', 'evid-nonexistent', ?)",
                (t0,),
            )


def test_sqlite_evaluation_fk_not_null_and_cascade(candidate_db) -> None:
    t0 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC).isoformat()
    with sqlite3.connect(candidate_db) as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute(
            "INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, created_at) "
            "VALUES ('cand-cas-1', 1, 'AAPL', ?, ?)",
            (t0, t0),
        )
        con.execute(
            "INSERT INTO candidate_evaluations (evaluation_id, candidate_id, evaluator_id, evaluator_version, evidence_state, created_at) "
            "VALUES ('eval-cas-1', 'cand-cas-1', 'ev1', '1.0', 'exploratory', ?)",
            (t0,),
        )
        con.execute(
            "INSERT INTO candidate_evidence (evidence_id, candidate_id, evidence_type, created_at) "
            "VALUES ('evid-cas-1', 'cand-cas-1', 'ohlcv', ?)",
            (t0,),
        )
        con.execute(
            "INSERT INTO candidate_reasons (reason_id, candidate_id, evaluation_id, dimension, reason_code, human_text, source_evidence_id, created_at) "
            "VALUES ('reas-cas-1', 'cand-cas-1', 'eval-cas-1', 'setup_quality', 'R1', 'test text', 'evid-cas-1', ?)",
            (t0,),
        )
        con.commit()

        # 1. Non-existent evaluation_id fails FK constraint
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            con.execute(
                "INSERT INTO candidate_reasons (reason_id, candidate_id, evaluation_id, dimension, reason_code, human_text, created_at) "
                "VALUES ('reas-bad-eval', 'cand-cas-1', 'eval-nonexistent', 'setup_quality', 'R2', 'text', ?)",
                (t0,),
            )

        # 2. NULL evaluation_id fails NOT NULL constraint
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            con.execute(
                "INSERT INTO candidate_reasons (reason_id, candidate_id, evaluation_id, dimension, reason_code, human_text, created_at) "
                "VALUES ('reas-null-eval', 'cand-cas-1', NULL, 'setup_quality', 'R3', 'text', ?)",
                (t0,),
            )

        # 3. NULL dimension fails NOT NULL constraint
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            con.execute(
                "INSERT INTO candidate_reasons (reason_id, candidate_id, evaluation_id, dimension, reason_code, human_text, created_at) "
                "VALUES ('reas-null-dim', 'cand-cas-1', 'eval-cas-1', NULL, 'R4', 'text', ?)",
                (t0,),
            )

        # 4. Deleting evidence sets source_evidence_id to NULL (ON DELETE SET NULL) without deleting the reason
        con.execute("DELETE FROM candidate_evidence WHERE evidence_id = 'evid-cas-1'")
        con.commit()
        reason_row = con.execute("SELECT source_evidence_id FROM candidate_reasons WHERE reason_id = 'reas-cas-1'").fetchone()
        assert reason_row is not None
        assert reason_row[0] is None

        # 5. Deleting evaluation cascades to delete the reason (ON DELETE CASCADE)
        con.execute("DELETE FROM candidate_evaluations WHERE evaluation_id = 'eval-cas-1'")
        con.commit()
        reason_count = con.execute("SELECT COUNT(*) FROM candidate_reasons WHERE reason_id = 'reas-cas-1'").fetchone()[0]
        assert reason_count == 0
