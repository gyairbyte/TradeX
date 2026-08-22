"""Tests for the alert state store."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from tradex.alerts.models import AlertDecision, AlertKey
from tradex.alerts.store import AlertStateError, AlertStore


def test_store_does_not_create_db_on_construction(tmp_path):
    path = tmp_path / "alerts.db"
    AlertStore(path)
    assert not path.exists()


def test_store_creates_db_on_first_use(tmp_path):
    path = tmp_path / "alerts.db"
    store = AlertStore(path)
    store._ensure_db()
    assert path.exists()


def test_schema_version_rejected(tmp_path):
    path = tmp_path / "alerts.db"
    store = AlertStore(path)
    store._ensure_db()
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE _schema_version SET version = 999 WHERE id = 1")
    conn.commit()
    conn.close()
    with pytest.raises(AlertStateError, match="unsupported alert state schema version"):
        store._ensure_db()


def test_corrupt_database_handling(tmp_path):
    path = tmp_path / "alerts.db"
    path.write_text("not a database")
    store = AlertStore(path)
    with pytest.raises(AlertStateError):
        store.claim(AlertKey("AAPL", "coil", "intraday"), datetime.now(UTC))


def test_claim_first_alert(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    claim = tmp_alert_store.claim(key, now)
    assert claim["allowed"] is True
    assert claim["token"] is not None


def test_claim_suppresses_immediate_repeat(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    token = tmp_alert_store.claim(key, now)["token"]
    tmp_alert_store.finalize(
        key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent"
    )
    claim = tmp_alert_store.claim(key, now)
    assert claim["allowed"] is False
    assert claim["decision"] == AlertDecision.SUPPRESSED_COOLDOWN


def test_claim_one_microsecond_before_expiry(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    start = datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    token = tmp_alert_store.claim(key, start)["token"]
    tmp_alert_store.finalize(
        key, token, start, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent"
    )
    before = start + timedelta(minutes=60) - timedelta(microseconds=1)
    claim = tmp_alert_store.claim(key, before)
    assert claim["allowed"] is False


def test_claim_exact_expiry(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    start = datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    token = tmp_alert_store.claim(key, start)["token"]
    tmp_alert_store.finalize(
        key,
        token,
        start,
        AlertDecision.SENT,
        60,
        "subject",
        "hash",
        {"discord": True},
        "sent",
    )
    exact = start + timedelta(minutes=60)
    claim = tmp_alert_store.claim(key, exact)
    assert claim["allowed"] is True


def test_claim_one_microsecond_after_expiry(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    start = datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    token = tmp_alert_store.claim(key, start)["token"]
    tmp_alert_store.finalize(
        key,
        token,
        start,
        AlertDecision.SENT,
        60,
        "subject",
        "hash",
        {"discord": True},
        "sent",
    )
    after = start + timedelta(minutes=60) + timedelta(microseconds=1)
    claim = tmp_alert_store.claim(key, after)
    assert claim["allowed"] is True


def test_different_ticker_independent(tmp_alert_store):
    now = datetime.now(UTC)
    assert tmp_alert_store.claim(AlertKey("AAPL", "coil", "intraday"), now)["allowed"] is True
    assert tmp_alert_store.claim(AlertKey("MSFT", "coil", "intraday"), now)["allowed"] is True


def test_different_alert_type_independent(tmp_alert_store):
    now = datetime.now(UTC)
    assert tmp_alert_store.claim(AlertKey("AAPL", "coil", "intraday"), now)["allowed"] is True
    assert tmp_alert_store.claim(AlertKey("AAPL", "confluence", "multi"), now)["allowed"] is True


def test_different_timeframe_independent(tmp_alert_store):
    now = datetime.now(UTC)
    assert tmp_alert_store.claim(AlertKey("AAPL", "coil", "intraday"), now)["allowed"] is True
    assert tmp_alert_store.claim(AlertKey("AAPL", "coil", "short"), now)["allowed"] is True


def test_in_flight_claim_blocks_second_claimant(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    first = tmp_alert_store.claim(key, now, lease_seconds=120)
    assert first["allowed"] is True
    second = tmp_alert_store.claim(key, now, lease_seconds=120)
    assert second["allowed"] is False
    assert second["decision"] == AlertDecision.SUPPRESSED_IN_FLIGHT


def test_expired_lease_reclaimable(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    tmp_alert_store.claim(key, now, lease_seconds=1)
    later = now + timedelta(seconds=2)
    claim = tmp_alert_store.claim(key, later, lease_seconds=1)
    assert claim["allowed"] is True


def test_finalize_wrong_token(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    tmp_alert_store.claim(key, now)
    success = tmp_alert_store.finalize(
        key,
        "wrong-token",
        now,
        AlertDecision.SENT,
        60,
        "subject",
        "hash",
        {"discord": True},
        "sent",
    )
    assert success is False


def test_finalize_idempotent(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    token = tmp_alert_store.claim(key, now)["token"]
    args = (key, token, now, AlertDecision.SENT, 60, "subject", "hash", {"discord": True}, "sent")
    assert tmp_alert_store.finalize(*args) is True
    assert tmp_alert_store.finalize(*args) is True
    state = tmp_alert_store.get_state(key)
    assert state.sent_count == 1


def test_failed_finalize_clears_claim(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    token = tmp_alert_store.claim(key, now)["token"]
    tmp_alert_store.finalize(
        key,
        token,
        now,
        AlertDecision.DELIVERY_FAILED,
        None,
        "subject",
        "hash",
        {},
        "failed",
    )
    state = tmp_alert_store.get_state(key)
    assert state.claim_token is None
    assert state.failed_count == 1


def test_state_persistence_across_instances(tmp_path):
    path = tmp_path / "alerts.db"
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    store1 = AlertStore(path)
    token = store1.claim(key, now)["token"]
    store1.finalize(key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent")
    store2 = AlertStore(path)
    state = store2.get_state(key)
    assert state.sent_count == 1


def test_list_alert_states_empty_schema(tmp_alert_store):
    df = tmp_alert_store.list_alert_states()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "ticker",
        "alert_type",
        "timeframe",
        "last_decision",
        "last_success_at",
        "cooldown_until",
        "claim_expires_at",
        "sent_count",
        "suppressed_count",
        "failed_count",
        "last_attempt_at",
        "created_at",
        "updated_at",
    ]
    assert df.empty


def test_list_alert_states_sorting_and_filters(tmp_alert_store):
    now = datetime.now(UTC)
    keys = [
        AlertKey("AAPL", "gap:up", "premarket"),
        AlertKey("MSFT", "coil", "intraday"),
        AlertKey("AAPL", "coil", "intraday"),
    ]
    for key in keys:
        token = tmp_alert_store.claim(key, now)["token"]
        tmp_alert_store.finalize(
            key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent"
        )
    df = tmp_alert_store.list_alert_states(ticker="AAPL", limit=10)
    assert len(df) == 2
    assert list(df["ticker"]) == ["AAPL", "AAPL"]


def test_list_invalid_limit(tmp_alert_store):
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(limit=0)
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(limit=10001)


def test_list_invalid_ticker_filter(tmp_alert_store):
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(ticker="  ")
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(ticker="AAPL\x00")
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(ticker=123)


def test_list_invalid_alert_type_filter(tmp_alert_store):
    with pytest.raises(ValueError):
        tmp_alert_store.list_alert_states(alert_type="  ")
    with pytest.raises(ValueError, match="control"):
        tmp_alert_store.list_alert_states(alert_type="coil\x01")


def test_in_flight_next_eligible_is_claim_expires_at(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    tmp_alert_store.claim(key, now, lease_seconds=120)
    second = tmp_alert_store.claim(key, now, lease_seconds=120)
    assert second["allowed"] is False
    assert second["decision"] == AlertDecision.SUPPRESSED_IN_FLIGHT
    assert second["next_eligible_at"] == now + timedelta(seconds=120)


def test_corrupt_cooldown_until_raises_alert_state_error(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    token = tmp_alert_store.claim(key, now)["token"]
    tmp_alert_store.finalize(
        key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent"
    )
    conn = sqlite3.connect(str(tmp_alert_store.resolved_path))
    conn.execute("UPDATE alert_state SET cooldown_until = 'not-a-date' WHERE ticker = ?", (key.ticker,))
    conn.commit()
    conn.close()
    with pytest.raises(AlertStateError):
        tmp_alert_store.get_state(key)
    with pytest.raises(AlertStateError):
        tmp_alert_store.list_alert_states()


def test_no_secrets_stored(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime.now(UTC)
    token = tmp_alert_store.claim(key, now)["token"]
    body = "This is the full alert body that must not be persisted."
    tmp_alert_store.finalize(
        key,
        token,
        now,
        AlertDecision.SENT,
        60,
        "subject",
        "hash",
        {"discord": True},
        "sent",
    )
    conn = sqlite3.connect(str(tmp_alert_store.resolved_path))
    rows = conn.execute("SELECT * FROM alert_state").fetchall()
    raw = "\n".join(str(row) for row in rows)
    assert body not in raw
    # claim_token is an opaque lease handle, not a secret.
    assert "password" not in raw
    assert "secret" not in raw.lower()
    conn.close()


def test_record_suppression_first_event(tmp_alert_store):
    """record_suppression creates a state row with suppressed_count=1 and no cooldown/claim."""
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    tmp_alert_store.record_suppression(
        key,
        now,
        AlertDecision.SUPPRESSED_EVIDENCE_GATE,
        "gated fail-closed",
        subject="AAPL coil",
    )

    state = tmp_alert_store.get_state(key)
    assert state is not None
    assert state.key.ticker == "AAPL"
    assert state.key.alert_type == "coil"
    assert state.key.timeframe == "intraday"
    assert state.suppressed_count == 1
    assert state.sent_count == 0
    assert state.failed_count == 0
    assert state.cooldown_until is None
    assert state.claim_token is None
    assert state.last_decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE.value
    assert state.last_reason == "gated fail-closed"
    assert state.last_attempt_at == now


def test_record_suppression_increments_and_preserves(tmp_alert_store):
    """record_suppression increments suppressed_count and preserves existing sent_count/cooldown."""
    key = AlertKey("AAPL", "coil", "intraday")
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    # First simulate a sent alert
    token = tmp_alert_store.claim(key, now)["token"]
    tmp_alert_store.finalize(
        key,
        token,
        now,
        AlertDecision.SENT,
        60,
        "subj",
        "hash",
        {"discord": True},
        "sent",
    )
    initial_state = tmp_alert_store.get_state(key)
    assert initial_state.sent_count == 1
    assert initial_state.cooldown_until == now + timedelta(minutes=60)

    # Record suppression
    later = now + timedelta(minutes=10)
    tmp_alert_store.record_suppression(
        key,
        later,
        AlertDecision.SUPPRESSED_EVIDENCE_GATE,
        "evidence gate active",
    )

    updated_state = tmp_alert_store.get_state(key)
    assert updated_state.suppressed_count == 1
    assert updated_state.sent_count == 1
    assert updated_state.failed_count == 0
    assert updated_state.cooldown_until == now + timedelta(minutes=60)
    assert updated_state.last_decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE.value
    assert updated_state.last_reason == "evidence gate active"
    assert updated_state.last_attempt_at == later


def test_record_suppression_naive_datetime_rejected(tmp_alert_store):
    key = AlertKey("AAPL", "coil", "intraday")
    naive = datetime(2024, 1, 1, 12, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="naive"):
        tmp_alert_store.record_suppression(
            key,
            naive,
            AlertDecision.SUPPRESSED_EVIDENCE_GATE,
            "reason",
        )
