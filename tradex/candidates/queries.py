"""Read-only candidate query and view-model layer for Today and Candidate Detail surfaces (MVP-ARCH-001-R5C).

Provides deterministic, immutable read-models and SQLite queries over persisted
CandidateSnapshot, CandidateEvidence, CandidateEvaluation, and CandidateMissingData
records. Makes zero network or provider calls and performs zero database writes.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tradex.market.hours import MARKET_TIMEZONE, normalize_market_datetime
from tradex.tracker.store import StoreError, _conn, _resolve_db_path

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


def _parse_iso_dt(value: str | None) -> datetime | None:
    """Parse an ISO8601 string to a timezone-aware UTC datetime."""
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_market_time(dt: datetime | None, *, include_date: bool = False) -> str:
    """Format a UTC datetime in America/New_York (ET)."""
    if dt is None:
        return "—"
    try:
        ny_dt = normalize_market_datetime(dt)
        if include_date:
            return ny_dt.strftime("%b %d, %Y %I:%M %p ET")
        return ny_dt.strftime("%I:%M %p ET")
    except (ValueError, TypeError):
        # Fallback to direct astimezone if normalize fails
        ny_dt = dt.astimezone(MARKET_TIMEZONE)
        if include_date:
            return ny_dt.strftime("%b %d, %Y %I:%M %p ET")
        return ny_dt.strftime("%I:%M %p ET")


def _format_observation_status(status_raw: str | None) -> str:
    """Map raw observation status to authoritative user-facing label."""
    if not status_raw:
        return "Unknown"
    clean = str(status_raw).strip().lower()
    if clean == "signal":
        return "Signal (Legacy Heuristic)"
    if clean == "below_threshold":
        return "Below Threshold (Legacy)"
    return clean.replace("_", " ").title()


def _format_provider_display(provider: str | None, fallback_used: bool = False) -> str:
    """Format provider name with explicit persisted fallback status."""
    prov = (provider or "unknown").strip()
    if fallback_used:
        return f"{prov} · Fallback"
    return prov


def _format_data_completeness(missing_count: int) -> str:
    """Format data completeness badge label."""
    if missing_count <= 0:
        return "Complete"
    if missing_count == 1:
        return "1 missing"
    return f"{missing_count} missing"


@dataclass(frozen=True)
class TodayCandidateRow:
    """Immutable view-model representing one latest candidate snapshot for Today overview."""

    candidate_id: str
    symbol: str
    decision_timestamp: datetime
    trading_date: str
    observation_status_raw: str
    legacy_observation_label: str
    observed_close: float | None
    provider: str
    fallback_used: bool
    provider_display: str
    missing_count: int
    missing_inputs: tuple[str, ...]
    data_completeness: str
    snapshot_count: int
    observed_time_et: str
    timeframe: str | None = None

    @property
    def formatted_close(self) -> str:
        if self.observed_close is not None:
            return f"${self.observed_close:.2f}"
        return "—"


@dataclass(frozen=True)
class CandidateHistoryRow:
    """Immutable view-model representing a historical snapshot for the same symbol/day."""

    candidate_id: str
    symbol: str
    decision_timestamp: datetime
    trading_date: str
    observation_status_raw: str
    legacy_observation_label: str
    observed_close: float | None
    legacy_score: int | None
    volume_ratio: float | None
    rsi: float | None
    days_until_earnings: int | None
    timeframe: str | None
    provider: str
    fallback_used: bool
    provider_display: str
    missing_count: int
    data_completeness: str
    observed_time_et: str

    @property
    def formatted_close(self) -> str:
        if self.observed_close is not None:
            return f"${self.observed_close:.2f}"
        return "—"

    @property
    def formatted_volume_ratio(self) -> str:
        if self.volume_ratio is not None:
            return f"{self.volume_ratio:.2f}x"
        return "—"

    @property
    def formatted_rsi(self) -> str:
        if self.rsi is not None:
            return f"{self.rsi:.1f}"
        return "—"

    @property
    def formatted_score(self) -> str:
        if self.legacy_score is not None:
            return str(self.legacy_score)
        return "—"


@dataclass(frozen=True)
class TodaySummaryFacts:
    """Immutable summary facts for the Today landing header."""

    latest_trading_date: str | None
    last_snapshot_time: datetime | None
    total_candidates: int
    total_snapshots: int

    @property
    def formatted_last_snapshot_time(self) -> str:
        return _format_market_time(self.last_snapshot_time)


def get_available_trading_dates(
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> list[str]:
    """Return distinct non-null trading dates present in candidate persistence.

    Ordered chronologically newest-first (trading_date DESC).
    Returns an empty list if no candidate snapshots exist.
    """
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    try:
        with _conn(db_path=path) as con:
            rows = con.execute(
                """
                SELECT DISTINCT trading_date
                FROM candidates
                WHERE trading_date IS NOT NULL
                ORDER BY trading_date DESC
                """
            ).fetchall()
            return [row["trading_date"] for row in rows if row["trading_date"]]
    except sqlite3.Error as exc:
        raise StoreError(f"Database error reading available trading dates: {exc}") from exc


def get_latest_candidates_for_date(
    trading_date: str,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> list[TodayCandidateRow]:
    """Retrieve the latest CandidateSnapshot per symbol for a given trading date.

    Deterministic tie-breaking selection:
    1. decision_timestamp DESC
    2. candidate_id DESC

    Final presentation ordering:
    1. decision_timestamp DESC
    2. symbol ASC

    Returns an empty list if no snapshots exist for the given trading date.
    """
    if not trading_date or not str(trading_date).strip():
        return []

    clean_date = str(trading_date).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    # Use SQLite window functions (supported in SQLite 3.25+) for deterministic ranking & snapshot counts
    sql = """
        WITH ranked_candidates AS (
            SELECT
                c.candidate_id,
                c.symbol,
                c.decision_timestamp,
                c.trading_date,
                ROW_NUMBER() OVER (
                    PARTITION BY c.symbol
                    ORDER BY c.decision_timestamp DESC, c.candidate_id DESC
                ) AS rn,
                COUNT(*) OVER (
                    PARTITION BY c.symbol
                ) AS symbol_snapshot_count
            FROM candidates c
            WHERE c.trading_date = ?
        )
        SELECT
            r.candidate_id,
            r.symbol,
            r.decision_timestamp,
            r.trading_date,
            r.symbol_snapshot_count,
            ev.metadata_json AS screener_meta_json,
            ev.provider AS evid_provider,
            eval.dimensions_json AS eval_dimensions_json
        FROM ranked_candidates r
        LEFT JOIN candidate_evidence ev
            ON ev.candidate_id = r.candidate_id AND ev.evidence_type = 'screener_observation'
        LEFT JOIN candidate_evaluations eval
            ON eval.candidate_id = r.candidate_id AND eval.evaluator_id = 'shadow_observation_evaluator'
        WHERE r.rn = 1
        ORDER BY r.decision_timestamp DESC, r.symbol ASC
    """

    try:
        with _conn(db_path=path) as con:
            rows = con.execute(sql, (clean_date,)).fetchall()
            results: list[TodayCandidateRow] = []

            for row in rows:
                meta: dict[str, Any] = {}
                if row["screener_meta_json"]:
                    try:
                        meta = json.loads(row["screener_meta_json"])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        meta = {}

                dims: dict[str, Any] = {}
                if row["eval_dimensions_json"]:
                    try:
                        dims = json.loads(row["eval_dimensions_json"])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        dims = {}

                data_conf = dims.get("data_confidence", {}) if isinstance(dims, dict) else {}
                fallback_used = bool(data_conf.get("fallback_used", False))
                actual_provider = str(data_conf.get("actual_provider") or row["evid_provider"] or "unknown")
                missing_inputs = tuple(data_conf.get("missing_inputs", []))
                missing_count = int(data_conf.get("missing_inputs_count", len(missing_inputs)))

                status_raw = meta.get("observation_status") or "unknown"
                label = _format_observation_status(status_raw)
                close_val = meta.get("last_close")
                timeframe = meta.get("timeframe")

                dt = _parse_iso_dt(row["decision_timestamp"])
                assert dt is not None  # decision_timestamp is non-null in candidates table

                results.append(
                    TodayCandidateRow(
                        candidate_id=row["candidate_id"],
                        symbol=row["symbol"],
                        decision_timestamp=dt,
                        trading_date=row["trading_date"],
                        observation_status_raw=status_raw,
                        legacy_observation_label=label,
                        observed_close=float(close_val) if close_val is not None else None,
                        provider=actual_provider,
                        fallback_used=fallback_used,
                        provider_display=_format_provider_display(actual_provider, fallback_used),
                        missing_count=missing_count,
                        missing_inputs=missing_inputs,
                        data_completeness=_format_data_completeness(missing_count),
                        snapshot_count=int(row["symbol_snapshot_count"]),
                        observed_time_et=_format_market_time(dt),
                        timeframe=timeframe,
                    )
                )

            return results
    except sqlite3.Error as exc:
        raise StoreError(f"Database error querying latest candidates for date '{clean_date}': {exc}") from exc


def get_candidate_history_for_symbol(
    symbol: str,
    trading_date: str,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> list[CandidateHistoryRow]:
    """Retrieve all immutable snapshots for the same symbol and trading date.

    Deterministic chronological presentation ordering:
    1. decision_timestamp ASC
    2. candidate_id ASC
    """
    if not symbol or not str(symbol).strip():
        return []
    if not trading_date or not str(trading_date).strip():
        return []

    clean_symbol = str(symbol).strip().upper()
    clean_date = str(trading_date).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    sql = """
        SELECT
            c.candidate_id,
            c.symbol,
            c.decision_timestamp,
            c.trading_date,
            ev.metadata_json AS screener_meta_json,
            ev.provider AS evid_provider,
            eval.dimensions_json AS eval_dimensions_json
        FROM candidates c
        LEFT JOIN candidate_evidence ev
            ON ev.candidate_id = c.candidate_id AND ev.evidence_type = 'screener_observation'
        LEFT JOIN candidate_evaluations eval
            ON eval.candidate_id = c.candidate_id AND eval.evaluator_id = 'shadow_observation_evaluator'
        WHERE c.symbol = ? AND c.trading_date = ?
        ORDER BY c.decision_timestamp ASC, c.candidate_id ASC
    """

    try:
        with _conn(db_path=path) as con:
            rows = con.execute(sql, (clean_symbol, clean_date)).fetchall()
            results: list[CandidateHistoryRow] = []

            for row in rows:
                meta: dict[str, Any] = {}
                if row["screener_meta_json"]:
                    try:
                        meta = json.loads(row["screener_meta_json"])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        meta = {}

                dims: dict[str, Any] = {}
                if row["eval_dimensions_json"]:
                    try:
                        dims = json.loads(row["eval_dimensions_json"])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        dims = {}

                data_conf = dims.get("data_confidence", {}) if isinstance(dims, dict) else {}
                fallback_used = bool(data_conf.get("fallback_used", False))
                actual_provider = str(data_conf.get("actual_provider") or row["evid_provider"] or "unknown")
                missing_inputs = tuple(data_conf.get("missing_inputs", []))
                missing_count = int(data_conf.get("missing_inputs_count", len(missing_inputs)))

                status_raw = meta.get("observation_status") or "unknown"
                label = _format_observation_status(status_raw)
                close_val = meta.get("last_close")
                score_val = meta.get("legacy_heuristic_score")
                vol_val = meta.get("volume_ratio")
                rsi_val = meta.get("rsi")
                er_val = meta.get("days_until_earnings")
                timeframe = meta.get("timeframe")

                dt = _parse_iso_dt(row["decision_timestamp"])
                assert dt is not None

                results.append(
                    CandidateHistoryRow(
                        candidate_id=row["candidate_id"],
                        symbol=row["symbol"],
                        decision_timestamp=dt,
                        trading_date=row["trading_date"],
                        observation_status_raw=status_raw,
                        legacy_observation_label=label,
                        observed_close=float(close_val) if close_val is not None else None,
                        legacy_score=int(score_val) if score_val is not None else None,
                        volume_ratio=float(vol_val) if vol_val is not None else None,
                        rsi=float(rsi_val) if rsi_val is not None else None,
                        days_until_earnings=int(er_val) if er_val is not None else None,
                        timeframe=timeframe,
                        provider=actual_provider,
                        fallback_used=fallback_used,
                        provider_display=_format_provider_display(actual_provider, fallback_used),
                        missing_count=missing_count,
                        data_completeness=_format_data_completeness(missing_count),
                        observed_time_et=_format_market_time(dt),
                    )
                )

            return results
    except sqlite3.Error as exc:
        raise StoreError(
            f"Database error querying candidate history for symbol '{clean_symbol}' on date '{clean_date}': {exc}"
        ) from exc


def get_today_summary_facts(
    trading_date: str,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> TodaySummaryFacts:
    """Retrieve high-level summary facts for the selected trading date."""
    if not trading_date or not str(trading_date).strip():
        return TodaySummaryFacts(
            latest_trading_date=None,
            last_snapshot_time=None,
            total_candidates=0,
            total_snapshots=0,
        )

    clean_date = str(trading_date).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    sql = """
        SELECT
            MAX(decision_timestamp) AS last_snapshot_time,
            COUNT(DISTINCT symbol) AS total_candidates,
            COUNT(*) AS total_snapshots
        FROM candidates
        WHERE trading_date = ?
    """

    try:
        with _conn(db_path=path) as con:
            row = con.execute(sql, (clean_date,)).fetchone()
            if row is None or row["total_snapshots"] == 0:
                return TodaySummaryFacts(
                    latest_trading_date=clean_date,
                    last_snapshot_time=None,
                    total_candidates=0,
                    total_snapshots=0,
                )

            last_dt = _parse_iso_dt(row["last_snapshot_time"])
            return TodaySummaryFacts(
                latest_trading_date=clean_date,
                last_snapshot_time=last_dt,
                total_candidates=int(row["total_candidates"] or 0),
                total_snapshots=int(row["total_snapshots"] or 0),
            )
    except sqlite3.Error as exc:
        raise StoreError(f"Database error reading summary facts for date '{clean_date}': {exc}") from exc
