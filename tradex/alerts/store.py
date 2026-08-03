"""Persistent, isolated SQLite alert cooldown state store."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.alerts.models import AlertDecision, AlertKey, AlertPolicyError, ensure_aware_utc

_SCHEMA_VERSION = 1

_CREATE_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS _schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
);
INSERT OR IGNORE INTO _schema_version (id, version) VALUES (1, {_SCHEMA_VERSION});

CREATE TABLE IF NOT EXISTS alert_state (
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    last_attempt_at TEXT,
    last_success_at TEXT,
    cooldown_until TEXT,

    claim_token TEXT,
    claim_expires_at TEXT,

    last_decision TEXT,
    last_reason TEXT,
    last_subject TEXT,
    last_payload_hash TEXT,
    last_channel_results_json TEXT,

    sent_count INTEGER NOT NULL DEFAULT 0,
    suppressed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    PRIMARY KEY (ticker, alert_type, timeframe)
);
"""


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


@dataclass(frozen=True)
class AlertState:
    """Read-only view of one alert-state row."""

    key: AlertKey
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    cooldown_until: datetime | None
    claim_token: str | None
    claim_expires_at: datetime | None
    last_decision: str | None
    last_reason: str | None
    last_subject: str | None
    last_payload_hash: str | None
    last_channel_results_json: str | None
    sent_count: int
    suppressed_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime


class AlertStateError(AlertPolicyError):
    """Raised when the alert state store is unavailable or corrupt."""


class AlertStore:
    """Isolated SQLite store for alert cooldown, claim, and audit state.

    The database is created only when the store is first used, not on import or
    construction. Use a temporary path for tests and a dedicated path in
    production (default ``~/.tradex/alerts.db``).
    """

    def __init__(self, state_path: Path | str) -> None:
        self._state_path = Path(state_path)

    @property
    def resolved_path(self) -> Path:
        return Path(os.path.expanduser(str(self._state_path)))

    def _ensure_db(self) -> None:
        """Create the database, schema, and version record on first use."""
        path = self.resolved_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AlertStateError(f"cannot create alert state directory: {exc}") from exc

        try:
            conn = sqlite3.connect(str(path), timeout=5.0)
        except sqlite3.Error as exc:
            raise AlertStateError(f"cannot open alert state database: {exc}") from exc

        try:
            # WAL mode supports reasonable concurrent readers/writers in one file.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_CREATE_SCHEMA_SQL)

            row = conn.execute("SELECT version FROM _schema_version WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    f"INSERT INTO _schema_version (id, version) VALUES (1, {_SCHEMA_VERSION})"
                )
                conn.commit()
            elif row[0] != _SCHEMA_VERSION:
                raise AlertStateError(
                    f"unsupported alert state schema version {row[0]}; expected {_SCHEMA_VERSION}"
                )
        except sqlite3.Error as exc:
            raise AlertStateError(f"alert state schema error: {exc}") from exc
        finally:
            conn.close()

    def _connection(self) -> sqlite3.Connection:
        self._ensure_db()
        try:
            return sqlite3.connect(str(self.resolved_path), timeout=5.0, isolation_level=None)
        except sqlite3.Error as exc:
            raise AlertStateError(f"cannot connect to alert state database: {exc}") from exc

    def claim(
        self,
        key: AlertKey,
        observed_at: datetime,
        *,
        lease_seconds: int = 120,
    ) -> dict[str, Any]:
        """Attempt to atomically claim the right to send this alert.

        Returns a dict describing the outcome:
          allowed: bool
          token: str | None
          decision: AlertDecision | None
          reason: str
          last_success_at: datetime | None
          next_eligible_at: datetime | None

        ``next_eligible_at`` is ``cooldown_until`` when the cooldown is still
        active. A stale (expired) claim is silently overwritten.
        """
        observed_at = ensure_aware_utc(observed_at)
        token = uuid.uuid4().hex
        lease_expires = observed_at + timedelta(seconds=lease_seconds)

        conn = self._connection()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                row = cur.execute(
                    """
                    SELECT last_success_at, cooldown_until, claim_token, claim_expires_at
                    FROM alert_state
                    WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                    """,
                    (key.ticker, key.alert_type, key.timeframe),
                ).fetchone()

                if row is not None:
                    last_success_at, cooldown_until, claim_token, claim_expires_at = row
                    last_success_dt = _from_iso(last_success_at)
                    cooldown_dt = _from_iso(cooldown_until)
                    claim_expires_dt = _from_iso(claim_expires_at)

                    if cooldown_dt is not None and observed_at < cooldown_dt:
                        cur.execute(
                            """
                            UPDATE alert_state
                            SET suppressed_count = suppressed_count + 1,
                                last_attempt_at = ?,
                                last_decision = ?,
                                updated_at = ?
                            WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                            """,
                            (
                                _to_iso(observed_at),
                                AlertDecision.SUPPRESSED_COOLDOWN.value,
                                _to_iso(observed_at),
                                key.ticker,
                                key.alert_type,
                                key.timeframe,
                            ),
                        )
                        conn.commit()
                        return {
                            "allowed": False,
                            "token": None,
                            "decision": AlertDecision.SUPPRESSED_COOLDOWN,
                            "reason": f"Cooldown active until {cooldown_dt.isoformat()}",
                            "last_success_at": last_success_dt,
                            "next_eligible_at": cooldown_dt,
                        }

                    if (
                        claim_token is not None
                        and claim_expires_dt is not None
                        and observed_at < claim_expires_dt
                    ):
                        cur.execute(
                            """
                            UPDATE alert_state
                            SET suppressed_count = suppressed_count + 1,
                                last_attempt_at = ?,
                                last_decision = ?,
                                updated_at = ?
                            WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                            """,
                            (
                                _to_iso(observed_at),
                                AlertDecision.SUPPRESSED_IN_FLIGHT.value,
                                _to_iso(observed_at),
                                key.ticker,
                                key.alert_type,
                                key.timeframe,
                            ),
                        )
                        conn.commit()
                        return {
                            "allowed": False,
                            "token": None,
                            "decision": AlertDecision.SUPPRESSED_IN_FLIGHT,
                            "reason": "Another delivery claim is in flight",
                            "last_success_at": last_success_dt,
                            "next_eligible_at": cooldown_dt,
                        }

                    # Stale or no claim: overwrite with new claim.
                    cur.execute(
                        """
                        UPDATE alert_state
                        SET claim_token = ?,
                            claim_expires_at = ?,
                            last_attempt_at = ?,
                            updated_at = ?
                        WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                        """,
                        (
                            token,
                            _to_iso(lease_expires),
                            _to_iso(observed_at),
                            _to_iso(observed_at),
                            key.ticker,
                            key.alert_type,
                            key.timeframe,
                        ),
                    )
                    conn.commit()
                    return {
                        "allowed": True,
                        "token": token,
                        "decision": None,
                        "reason": "Claim acquired",
                        "last_success_at": last_success_dt,
                        "next_eligible_at": None,
                    }

                # No row exists; insert with the claim.
                cur.execute(
                    """
                    INSERT INTO alert_state (
                        ticker, alert_type, timeframe,
                        claim_token, claim_expires_at, last_attempt_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key.ticker,
                        key.alert_type,
                        key.timeframe,
                        token,
                        _to_iso(lease_expires),
                        _to_iso(observed_at),
                        _to_iso(observed_at),
                        _to_iso(observed_at),
                    ),
                )
                conn.commit()
                return {
                    "allowed": True,
                    "token": token,
                    "decision": None,
                    "reason": "Claim acquired",
                    "last_success_at": None,
                    "next_eligible_at": None,
                }
            except Exception:
                conn.rollback()
                raise
        except sqlite3.Error as exc:
            raise AlertStateError(f"alert state claim failed: {exc}") from exc
        finally:
            conn.close()

    def finalize(
        self,
        key: AlertKey,
        token: str,
        observed_at: datetime,
        decision: AlertDecision,
        cooldown_minutes: int | None,
        subject: str,
        payload_hash: str,
        channel_results: dict[str, bool],
        reason: str,
    ) -> bool:
        """Finalize a previously acquired claim.

        Returns ``True`` if the token matched and the row was updated. Wrong or
        expired tokens return ``False``. Cooldown is only started for ``SENT``
        decisions.
        """
        observed_at = ensure_aware_utc(observed_at)
        cooldown_until = (
            observed_at + timedelta(minutes=cooldown_minutes)
            if decision == AlertDecision.SENT and cooldown_minutes is not None
            else None
        )

        channel_json = json.dumps(channel_results, allow_nan=False, sort_keys=True, ensure_ascii=True)

        conn = self._connection()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                row = cur.execute(
                    """
                    SELECT claim_token, last_attempt_at, last_decision, last_subject, last_payload_hash
                    FROM alert_state
                    WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                    """,
                    (key.ticker, key.alert_type, key.timeframe),
                ).fetchone()

                if row is None:
                    conn.rollback()
                    return False

                stored_token, last_attempt_at, last_decision, last_subject, last_payload_hash = row

                # Idempotent duplicate finalize: same token already cleared and the
                # same outcome was recorded for this exact attempt.
                if (
                    stored_token is None
                    and last_attempt_at == _to_iso(observed_at)
                    and last_decision == decision.value
                    and last_subject == subject
                    and last_payload_hash == payload_hash
                ):
                    conn.commit()
                    return True

                if stored_token != token:
                    conn.rollback()
                    return False

                if decision == AlertDecision.SENT:
                    cur.execute(
                        """
                        UPDATE alert_state
                        SET sent_count = sent_count + 1,
                            last_success_at = ?,
                            cooldown_until = ?,
                            claim_token = NULL,
                            claim_expires_at = NULL,
                            last_decision = ?,
                            last_reason = ?,
                            last_subject = ?,
                            last_payload_hash = ?,
                            last_channel_results_json = ?,
                            updated_at = ?
                        WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                        """,
                        (
                            _to_iso(observed_at),
                            _to_iso(cooldown_until) if cooldown_until else None,
                            decision.value,
                            reason,
                            subject,
                            payload_hash,
                            channel_json,
                            _to_iso(observed_at),
                            key.ticker,
                            key.alert_type,
                            key.timeframe,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE alert_state
                        SET failed_count = failed_count + 1,
                            claim_token = NULL,
                            claim_expires_at = NULL,
                            last_decision = ?,
                            last_reason = ?,
                            last_subject = ?,
                            last_payload_hash = ?,
                            last_channel_results_json = ?,
                            updated_at = ?
                        WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                        """,
                        (
                            decision.value,
                            reason,
                            subject,
                            payload_hash,
                            channel_json,
                            _to_iso(observed_at),
                            key.ticker,
                            key.alert_type,
                            key.timeframe,
                        ),
                    )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        except sqlite3.Error as exc:
            raise AlertStateError(f"alert state finalize failed: {exc}") from exc
        finally:
            conn.close()

    def get_state(self, key: AlertKey) -> AlertState | None:
        """Read one alert-state row, or ``None`` if it does not exist."""
        conn = self._connection()
        try:
            cur = conn.cursor()
            row = cur.execute(
                """
                SELECT
                    last_attempt_at, last_success_at, cooldown_until,
                    claim_token, claim_expires_at,
                    last_decision, last_reason, last_subject, last_payload_hash,
                    last_channel_results_json,
                    sent_count, suppressed_count, failed_count,
                    created_at, updated_at
                FROM alert_state
                WHERE ticker = ? AND alert_type = ? AND timeframe = ?
                """,
                (key.ticker, key.alert_type, key.timeframe),
            ).fetchone()
        except sqlite3.Error as exc:
            raise AlertStateError(f"alert state read failed: {exc}") from exc
        finally:
            conn.close()

        if row is None:
            return None

        return AlertState(
            key=key,
            last_attempt_at=_from_iso(row[0]),
            last_success_at=_from_iso(row[1]),
            cooldown_until=_from_iso(row[2]),
            claim_token=row[3],
            claim_expires_at=_from_iso(row[4]),
            last_decision=row[5],
            last_reason=row[6],
            last_subject=row[7],
            last_payload_hash=row[8],
            last_channel_results_json=row[9],
            sent_count=row[10],
            suppressed_count=row[11],
            failed_count=row[12],
            created_at=_from_iso(row[13]),
            updated_at=_from_iso(row[14]),
        )

    def list_alert_states(
        self,
        *,
        ticker: str | None = None,
        alert_type: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Return a stable, deterministic DataFrame of alert-state rows.

        Columns include the key, audit timestamps, counters, and claim state.
        Never exposes message bodies or secrets.
        """
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        if limit <= 0 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")

        filters: list[str] = []
        params: list[Any] = []
        if ticker is not None:
            filters.append("ticker = ?")
            params.append(str(ticker).strip().upper())
        if alert_type is not None:
            filters.append("alert_type = ?")
            params.append(str(alert_type).strip().lower())

        where = ""
        if filters:
            where = "WHERE " + " AND ".join(filters)

        conn = self._connection()
        try:
            cur = conn.cursor()
            rows = cur.execute(
                f"""
                SELECT
                    ticker, alert_type, timeframe,
                    last_attempt_at, last_success_at, cooldown_until,
                    claim_token, claim_expires_at,
                    last_decision, last_reason, last_subject,
                    sent_count, suppressed_count, failed_count,
                    created_at, updated_at
                FROM alert_state
                {where}
                ORDER BY ticker, alert_type, timeframe
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise AlertStateError(f"alert state list failed: {exc}") from exc
        finally:
            conn.close()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "ticker",
                    "alert_type",
                    "timeframe",
                    "last_decision",
                    "last_success_at",
                    "cooldown_until",
                    "claim_token",
                    "claim_expires_at",
                    "sent_count",
                    "suppressed_count",
                    "failed_count",
                    "last_attempt_at",
                    "created_at",
                    "updated_at",
                ]
            )

        data = []
        for row in rows:
            data.append(
                {
                    "ticker": row[0],
                    "alert_type": row[1],
                    "timeframe": row[2],
                    "last_decision": row[8],
                    "last_success_at": _from_iso(row[4]),
                    "cooldown_until": _from_iso(row[5]),
                    "claim_token": row[6],
                    "claim_expires_at": _from_iso(row[7]),
                    "sent_count": row[11],
                    "suppressed_count": row[12],
                    "failed_count": row[13],
                    "last_attempt_at": _from_iso(row[3]),
                    "created_at": _from_iso(row[14]),
                    "updated_at": _from_iso(row[15]),
                }
            )

        return pd.DataFrame(data)


# alias for backward-compatible spelling
AlertCooldownState = AlertStore
