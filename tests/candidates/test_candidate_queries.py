"""Unit and integration tests for read-only candidate queries (MVP-ARCH-001-R5C).

Validates deterministic latest-per-symbol selection, tie-breaking on identical timestamps,
chronological history queries, provider/fallback extraction, missing-data counts,
zero provider calls, zero database writes, and distinct error surfacing.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

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
    get_available_trading_dates,
    get_candidate_history_for_symbol,
    get_latest_candidates_for_date,
    get_today_summary_facts,
    record_candidate_dossier,
)
from tradex.tracker import store
from tradex.tracker.store import StoreError


@pytest.fixture
def query_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create and initialize an isolated test SQLite database."""
    db_path = str(tmp_path / "test_candidate_queries.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init(db_path)
    return db_path


def _build_dossier(
    candidate_id: str,
    symbol: str,
    decision_dt: datetime,
    *,
    status: str = "signal",
    score: int = 75,
    last_close: float = 150.0,
    volume_ratio: float = 2.1,
    rsi: float = 60.5,
    days_until_earnings: int | None = 10,
    timeframe: str = "intraday",
    actual_provider: str = "schwab",
    requested_provider: str = "schwab",
    fallback_used: bool = False,
    missing_inputs: tuple[str, ...] = (),
    session_id: str = "session-001",
) -> CandidateDossier:
    """Helper to construct a complete CandidateDossier with realistic metadata."""
    snap = CandidateSnapshot(
        candidate_id=candidate_id,
        symbol=symbol,
        decision_timestamp=decision_dt,
        contract_version=1,
        trading_date=decision_dt.strftime("%Y-%m-%d"),
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )

    ev_meta = {
        "observation_status": status,
        "legacy_heuristic_score": score,
        "last_close": last_close,
        "volume_ratio": volume_ratio,
        "rsi": rsi,
        "days_until_earnings": days_until_earnings,
        "reasons": "Volume surge > 2x | RSI in sweet spot",
        "timeframe": timeframe,
    }

    evid = CandidateEvidence(
        evidence_id=f"evid-{candidate_id}",
        candidate_id=candidate_id,
        evidence_type="screener_observation",
        source_ref_type="scan_session",
        source_ref_id=session_id,
        provider=actual_provider,
        observed_at=decision_dt,
        metadata=ev_meta,
    )

    context_dim = {
        "evidence_types": ["screener_observation"],
        "observation_status": status,
        "timeframe": timeframe,
        "days_until_earnings": days_until_earnings,
    }
    data_conf_dim = {
        "actual_provider": actual_provider,
        "requested_provider": requested_provider,
        "fallback_used": fallback_used,
        "missing_inputs_count": len(missing_inputs),
        "missing_inputs": list(missing_inputs),
    }

    eval_env = CandidateEvaluation(
        evaluation_id=f"eval-{candidate_id}",
        candidate_id=candidate_id,
        evaluator_id="shadow_observation_evaluator",
        evaluator_version="1.0.0",
        evidence_state="exploratory",
        dimensions={
            CandidateDimension.CONTEXT.value: context_dim,
            CandidateDimension.DATA_CONFIDENCE.value: data_conf_dim,
        },
    )

    reasons = [
        CandidateReason(
            reason_id=f"reas-{candidate_id}-1",
            candidate_id=candidate_id,
            evaluation_id=f"eval-{candidate_id}",
            dimension=CandidateDimension.CONTEXT,
            reason_code="PRIMARY_OBSERVATION_CAPTURED",
            human_text="Primary screener observation recorded.",
            polarity=ReasonPolarity.NEUTRAL,
            severity=ReasonSeverity.INFO,
            source_evidence_id=f"evid-{candidate_id}",
        )
    ]

    missing_data = [
        CandidateMissingData(
            record_id=f"miss-{candidate_id}-{inp}",
            candidate_id=candidate_id,
            evaluation_id=f"eval-{candidate_id}",
            input_name=inp,
            data_family="market_data",
            status=MissingDataStatus.UNKNOWN,
            detail=f"{inp} was unavailable",
            provider=actual_provider,
            observed_at=decision_dt,
        )
        for inp in missing_inputs
    ]

    return CandidateDossier(
        snapshot=snap,
        evaluations=(eval_env,),
        evidence=(evid,),
        reasons=tuple(reasons),
        missing_data=tuple(missing_data),
    )


# ── Test 1: One latest row per symbol for selected trading date ───────────────
def test_one_latest_row_per_symbol(query_db: str) -> None:
    dt1 = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    dt2 = datetime(2026, 8, 21, 15, 30, tzinfo=UTC)

    # AAPL has 2 snapshots; MSFT has 1 snapshot
    d1 = _build_dossier("cand-aapl-1", "AAPL", dt1, last_close=150.0)
    d2 = _build_dossier("cand-aapl-2", "AAPL", dt2, last_close=155.0)
    d3 = _build_dossier("cand-msft-1", "MSFT", dt1, last_close=320.0)

    record_candidate_dossier(d1, query_db)
    record_candidate_dossier(d2, query_db)
    record_candidate_dossier(d3, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    assert len(rows) == 2

    symbols = [r.symbol for r in rows]
    assert symbols == ["AAPL", "MSFT"]

    aapl_row = next(r for r in rows if r.symbol == "AAPL")
    assert aapl_row.candidate_id == "cand-aapl-2"
    assert aapl_row.observed_close == 155.0
    assert aapl_row.snapshot_count == 2


# ── Test 2: Multiple snapshots for same symbol on same day ───────────────────
def test_multiple_snapshots_same_symbol_same_day(query_db: str) -> None:
    base_dt = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)

    # 4 snapshots throughout the day
    for i in range(4):
        dt = base_dt + timedelta(hours=i)
        d = _build_dossier(f"cand-nvda-{i}", "NVDA", dt, last_close=100.0 + i * 5)
        record_candidate_dossier(d, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    assert len(rows) == 1
    nvda = rows[0]
    assert nvda.symbol == "NVDA"
    assert nvda.candidate_id == "cand-nvda-3"
    assert nvda.observed_close == 115.0
    assert nvda.snapshot_count == 4


# ── Test 3: Same symbol on different trading dates ───────────────────────────
def test_same_symbol_on_different_trading_dates(query_db: str) -> None:
    dt_day1 = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    dt_day2 = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    d1 = _build_dossier("cand-tsla-day1", "TSLA", dt_day1, last_close=200.0)
    d2 = _build_dossier("cand-tsla-day2", "TSLA", dt_day2, last_close=210.0)

    record_candidate_dossier(d1, query_db)
    record_candidate_dossier(d2, query_db)

    # Query day 1
    rows_d1 = get_latest_candidates_for_date("2026-08-20", query_db)
    assert len(rows_d1) == 1
    assert rows_d1[0].candidate_id == "cand-tsla-day1"
    assert rows_d1[0].observed_close == 200.0
    assert rows_d1[0].snapshot_count == 1

    # Query day 2
    rows_d2 = get_latest_candidates_for_date("2026-08-21", query_db)
    assert len(rows_d2) == 1
    assert rows_d2[0].candidate_id == "cand-tsla-day2"
    assert rows_d2[0].observed_close == 210.0
    assert rows_d2[0].snapshot_count == 1


# ── Test 4: Deterministic tie-break when decision_timestamp equal ────────────
def test_deterministic_tie_break_equal_timestamps(query_db: str) -> None:
    """Two candidate rows with identical decision_timestamp must deterministically select candidate_id DESC."""
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    d1 = _build_dossier("cand-amd-aaa", "AMD", dt, last_close=140.0)
    d2 = _build_dossier("cand-amd-zzz", "AMD", dt, last_close=142.0)

    record_candidate_dossier(d1, query_db)
    record_candidate_dossier(d2, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    assert len(rows) == 1
    # "cand-amd-zzz" > "cand-amd-aaa", so candidate_id DESC picks cand-amd-zzz
    assert rows[0].candidate_id == "cand-amd-zzz"
    assert rows[0].observed_close == 142.0
    assert rows[0].snapshot_count == 2


# ── Test 5: Today output ordering (decision_timestamp DESC, symbol ASC) ──────
def test_today_output_ordering(query_db: str) -> None:
    dt_early = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)
    dt_late = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    # AAPL (late), META (late), MSFT (early), GOOGL (early)
    d_aapl = _build_dossier("cand-aapl", "AAPL", dt_late)
    d_meta = _build_dossier("cand-meta", "META", dt_late)
    d_msft = _build_dossier("cand-msft", "MSFT", dt_early)
    d_googl = _build_dossier("cand-googl", "GOOGL", dt_early)

    for d in [d_msft, d_meta, d_googl, d_aapl]:
        record_candidate_dossier(d, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    symbols = [r.symbol for r in rows]

    # Late group (AAPL, META) sorted symbol ASC -> AAPL, META
    # Early group (GOOGL, MSFT) sorted symbol ASC -> GOOGL, MSFT
    assert symbols == ["AAPL", "META", "GOOGL", "MSFT"]


# ── Test 6: Available trading dates newest first ──────────────────────────────
def test_available_trading_dates_ordering(query_db: str) -> None:
    dt1 = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    dt2 = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
    dt3 = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    record_candidate_dossier(_build_dossier("c1", "AAPL", dt1), query_db)
    record_candidate_dossier(_build_dossier("c2", "AAPL", dt2), query_db)
    record_candidate_dossier(_build_dossier("c3", "AAPL", dt3), query_db)

    dates = get_available_trading_dates(query_db)
    assert dates == ["2026-08-21", "2026-08-20", "2026-08-19"]


# ── Test 7: Latest persisted trading date selection and summary facts ────────
def test_today_summary_facts(query_db: str) -> None:
    # Empty DB
    empty_facts = get_today_summary_facts("2026-08-21", query_db)
    assert empty_facts.total_candidates == 0
    assert empty_facts.total_snapshots == 0
    assert empty_facts.last_snapshot_time is None

    # Populate data
    dt1 = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    dt2 = datetime(2026, 8, 21, 15, 55, tzinfo=UTC)
    record_candidate_dossier(_build_dossier("c1", "AAPL", dt1), query_db)
    record_candidate_dossier(_build_dossier("c2", "AAPL", dt2), query_db)
    record_candidate_dossier(_build_dossier("c3", "MSFT", dt1), query_db)

    facts = get_today_summary_facts("2026-08-21", query_db)
    assert facts.latest_trading_date == "2026-08-21"
    assert facts.total_candidates == 2
    assert facts.total_snapshots == 3
    assert facts.last_snapshot_time == dt2
    assert "ET" in facts.formatted_last_snapshot_time


# ── Test 8: History query same symbol and date only ──────────────────────────
def test_candidate_history_symbol_and_date_isolation(query_db: str) -> None:
    dt1 = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)
    dt2 = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    dt_other_day = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)

    # AAPL today
    record_candidate_dossier(_build_dossier("cand-aapl-1", "AAPL", dt1), query_db)
    record_candidate_dossier(_build_dossier("cand-aapl-2", "AAPL", dt2), query_db)
    # AAPL yesterday
    record_candidate_dossier(_build_dossier("cand-aapl-yest", "AAPL", dt_other_day), query_db)
    # MSFT today
    record_candidate_dossier(_build_dossier("cand-msft-today", "MSFT", dt1), query_db)

    hist = get_candidate_history_for_symbol("AAPL", "2026-08-21", query_db)
    assert len(hist) == 2
    assert [h.candidate_id for h in hist] == ["cand-aapl-1", "cand-aapl-2"]


# ── Test 9: History deterministic chronological ordering ─────────────────────
def test_candidate_history_chronological_ordering(query_db: str) -> None:
    dt1 = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)
    dt2 = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    dt3 = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    # Insert out of order
    record_candidate_dossier(_build_dossier("c3", "PLTR", dt3, score=85), query_db)
    record_candidate_dossier(_build_dossier("c1", "PLTR", dt1, score=65), query_db)
    record_candidate_dossier(_build_dossier("c2", "PLTR", dt2, score=75), query_db)

    hist = get_candidate_history_for_symbol("PLTR", "2026-08-21", query_db)
    assert len(hist) == 3
    assert [h.candidate_id for h in hist] == ["c1", "c2", "c3"]
    assert [h.legacy_score for h in hist] == [65, 75, 85]


# ── Test 10: Provider & Fallback formatting ──────────────────────────────────
def test_provider_and_fallback_extraction(query_db: str) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    # Primary provider without fallback
    d1 = _build_dossier("c-schwab", "AAPL", dt, actual_provider="schwab", fallback_used=False)
    # Fallback provider with fallback_used=True
    d2 = _build_dossier(
        "c-yahoo-fb",
        "NVDA",
        dt,
        actual_provider="yahoo",
        requested_provider="schwab",
        fallback_used=True,
    )

    record_candidate_dossier(d1, query_db)
    record_candidate_dossier(d2, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    aapl = next(r for r in rows if r.symbol == "AAPL")
    nvda = next(r for r in rows if r.symbol == "NVDA")

    assert aapl.provider == "schwab"
    assert aapl.fallback_used is False
    assert aapl.provider_display == "schwab"

    assert nvda.provider == "yahoo"
    assert nvda.fallback_used is True
    assert nvda.provider_display == "yahoo · Fallback"


# ── Test 11: Missing data count and completeness formatting ──────────────────
def test_missing_data_extraction(query_db: str) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    d_complete = _build_dossier("c-comp", "AAPL", dt, missing_inputs=())
    d_one = _build_dossier("c-one", "MSFT", dt, missing_inputs=("rsi",))
    d_two = _build_dossier("c-two", "TSLA", dt, missing_inputs=("rsi", "volume_ratio"))

    record_candidate_dossier(d_complete, query_db)
    record_candidate_dossier(d_one, query_db)
    record_candidate_dossier(d_two, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    aapl = next(r for r in rows if r.symbol == "AAPL")
    msft = next(r for r in rows if r.symbol == "MSFT")
    tsla = next(r for r in rows if r.symbol == "TSLA")

    assert aapl.missing_count == 0
    assert aapl.data_completeness == "Complete"

    assert msft.missing_count == 1
    assert msft.data_completeness == "1 missing"
    assert msft.missing_inputs == ("rsi",)

    assert tsla.missing_count == 2
    assert tsla.data_completeness == "2 missing"
    assert tsla.missing_inputs == ("rsi", "volume_ratio")


# ── Test 12: Observation labels mapping ──────────────────────────────────────
def test_observation_labels_mapping(query_db: str) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    d_sig = _build_dossier("c-sig", "AAPL", dt, status="signal")
    d_below = _build_dossier("c-below", "MSFT", dt, status="below_threshold")

    record_candidate_dossier(d_sig, query_db)
    record_candidate_dossier(d_below, query_db)

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    aapl = next(r for r in rows if r.symbol == "AAPL")
    msft = next(r for r in rows if r.symbol == "MSFT")

    assert aapl.legacy_observation_label == "Signal (Legacy Heuristic)"
    assert msft.legacy_observation_label == "Below Threshold (Legacy)"


# ── Test 13: Zero provider/network calls ─────────────────────────────────────
def test_queries_make_zero_provider_calls(query_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
    record_candidate_dossier(_build_dossier("c-aapl", "AAPL", dt), query_db)

    # Mock all provider functions to raise if invoked
    faulty_provider = MagicMock(side_effect=RuntimeError("Provider network call attempted!"))
    monkeypatch.setattr("tradex.data.fetcher.fetch", faulty_provider)
    monkeypatch.setattr("tradex.screener.engine.run_with_report", faulty_provider)

    dates = get_available_trading_dates(query_db)
    assert dates == ["2026-08-21"]

    rows = get_latest_candidates_for_date("2026-08-21", query_db)
    assert len(rows) == 1

    hist = get_candidate_history_for_symbol("AAPL", "2026-08-21", query_db)
    assert len(hist) == 1

    faulty_provider.assert_not_called()


# ── Test 14: Zero database writes during query execution ─────────────────────
def test_queries_perform_zero_writes(query_db: str) -> None:
    dt = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
    record_candidate_dossier(_build_dossier("c-aapl", "AAPL", dt), query_db)

    # Inspect snapshot count before queries
    with store._conn(db_path=Path(query_db)) as con:
        count_before = con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    _ = get_available_trading_dates(query_db)
    _ = get_latest_candidates_for_date("2026-08-21", query_db)
    _ = get_candidate_history_for_symbol("AAPL", "2026-08-21", query_db)
    _ = get_today_summary_facts("2026-08-21", query_db)

    with store._conn(db_path=Path(query_db)) as con:
        count_after = con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    assert count_before == count_after == 1


# ── Test 15: DB/query error surfaces distinctly from empty result ────────────
def test_db_read_failure_surfaces_store_error(tmp_path: Path) -> None:
    # Point to a directory (not a valid SQLite file) to force an operational sqlite3.Error
    bad_db_path = str(tmp_path / "nonexistent_dir" / "bad.db")

    with pytest.raises(StoreError, match="Database error"):
        get_available_trading_dates(bad_db_path)

    with pytest.raises(StoreError, match="Database error"):
        get_latest_candidates_for_date("2026-08-21", bad_db_path)

    with pytest.raises(StoreError, match="Database error"):
        get_candidate_history_for_symbol("AAPL", "2026-08-21", bad_db_path)

    with pytest.raises(StoreError, match="Database error"):
        get_today_summary_facts("2026-08-21", bad_db_path)
