"""Tests for observation aggregation and candidate ID generation (MVP-ARCH-001-R5B)."""
from datetime import UTC, datetime

import pandas as pd
import pytest

from tradex.candidates.aggregator import (
    build_candidate_snapshot,
    extract_screener_evidence,
    generate_candidate_id,
    is_scorable_observation,
)
from tradex.candidates.models import (
    MissingDataStatus,
    SecurityIdentityStatus,
)


def test_generate_candidate_id_deterministic():
    session_id = "session-12345"
    id1 = generate_candidate_id(session_id, "AAPL")
    id2 = generate_candidate_id(session_id, "aapl")
    id3 = generate_candidate_id(session_id, "  AAPL  ")
    assert id1 == id2 == id3
    assert id1.startswith("cand_")
    assert len(id1) == 29  # "cand_" (5) + 24 hex chars = 29

    # Different symbol -> different ID
    id_msft = generate_candidate_id(session_id, "MSFT")
    assert id_msft != id1

    # Different session -> different ID
    id_diff_session = generate_candidate_id("session-67890", "AAPL")
    assert id_diff_session != id1


def test_generate_candidate_id_validation():
    with pytest.raises(ValueError, match="session_id"):
        generate_candidate_id("", "AAPL")
    with pytest.raises(ValueError, match="symbol"):
        generate_candidate_id("sess-1", "   ")


def test_is_scorable_observation():
    assert is_scorable_observation("signal") is True
    assert is_scorable_observation("SIGNAL") is True
    assert is_scorable_observation("below_threshold") is True
    assert is_scorable_observation("BELOW_THRESHOLD") is True

    assert is_scorable_observation("fetch_failure") is False
    assert is_scorable_observation("insufficient_data") is False
    assert is_scorable_observation("earnings_excluded") is False
    assert is_scorable_observation("earnings_failure") is False
    assert is_scorable_observation("scoring_failure") is False
    assert is_scorable_observation(None) is False
    assert is_scorable_observation("") is False


def test_build_candidate_snapshot():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)  # Friday trading session
    snap = build_candidate_snapshot("aapl", "sess-abc", dt)
    assert snap.symbol == "AAPL"
    assert snap.candidate_id == generate_candidate_id("sess-abc", "AAPL")
    assert snap.decision_timestamp == dt
    assert snap.trading_date == "2026-08-21"
    assert snap.security_identity_status == SecurityIdentityStatus.UNKNOWN
    assert snap.security_identity_version is None
    assert snap.contract_version == 1


def test_extract_screener_evidence_complete():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    obs = pd.Series({
        "ticker": "AAPL",
        "status": "signal",
        "score": 65,
        "last_close": 150.25,
        "volume_ratio": 1.45,
        "rsi": 58.2,
        "days_until_earnings": 22,
        "reasons": "RSI in momentum zone | Volume confirming",
        "provider": "schwab",
    })
    cand_id = generate_candidate_id("sess-1", "AAPL")
    evidence, missing = extract_screener_evidence(
        candidate_id=cand_id,
        observation=obs,
        session_id="sess-1",
        timeframe="intraday",
        observed_at=dt,
        actual_provider="schwab",
    )
    assert evidence.candidate_id == cand_id
    assert evidence.evidence_type == "screener_observation"
    assert evidence.source_ref_type == "scan_session"
    assert evidence.source_ref_id == "sess-1"
    assert evidence.provider == "schwab"
    assert evidence.observed_at == dt
    assert evidence.metadata["legacy_heuristic_score"] == 65
    assert evidence.metadata["last_close"] == 150.25
    assert evidence.metadata["volume_ratio"] == 1.45
    assert evidence.metadata["rsi"] == 58.2
    assert evidence.metadata["days_until_earnings"] == 22
    assert evidence.metadata["observation_status"] == "signal"
    assert evidence.metadata["timeframe"] == "intraday"
    assert missing == []


def test_extract_screener_evidence_missing_fields():
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    obs = {
        "ticker": "MSFT",
        "status": "below_threshold",
        "score": 25,
        "last_close": None,
        "volume_ratio": None,
        "rsi": None,
        "days_until_earnings": None,
        "reasons": None,
        "provider": "alpaca",
    }
    cand_id = generate_candidate_id("sess-2", "MSFT")
    evidence, missing = extract_screener_evidence(
        candidate_id=cand_id,
        observation=obs,
        session_id="sess-2",
        timeframe="short",
        observed_at=dt,
        actual_provider="alpaca",
    )
    assert evidence.metadata["legacy_heuristic_score"] == 25
    assert evidence.metadata["last_close"] is None
    assert len(missing) == 3
    input_names = {m.input_name for m in missing}
    assert input_names == {"last_close", "volume_ratio", "rsi"}
    for m in missing:
        assert m.candidate_id == cand_id
        assert m.status == MissingDataStatus.UNKNOWN
        assert m.observed_at == dt
