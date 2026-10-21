"""Typed models and deterministic parser for ORB candidate preview snapshots."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import (
    DailyBar,
    DataIntegrityError,
    MinuteBar,
    OpeningRangeVolumeObservation,
)

MARKET_TIMEZONE = ZoneInfo("America/New_York")
MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024  # 5 MB MVP limit


class SnapshotValidationError(ValueError):
    """Raised when an ORB snapshot payload violates structural or bounds invariants."""


@dataclass(frozen=True)
class SnapshotSymbolPayload:
    """Per-symbol raw input payload contained in an ORB snapshot."""

    symbol: str
    daily_bars: list[DailyBar] = field(default_factory=list)
    opening_range_bars: list[MinuteBar] = field(default_factory=list)
    prior_opening_range_volumes: list[OpeningRangeVolumeObservation] = field(default_factory=list)
    primary_exchange: str | None = None
    integrity_error: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise SnapshotValidationError("Symbol must be a non-empty string")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())


@dataclass(frozen=True)
class ORBSnapshot:
    """Immutable, point-in-time ORB candidate preview input snapshot for session D."""

    session_date: date
    as_of_time: datetime
    source_type: str  # "synthetic_demo" | "user_provided_unverified"
    source_label: str
    completeness_status: str  # "watchlist_only" | "unknown" | "declared_complete"
    symbols: dict[str, SnapshotSymbolPayload] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.as_of_time.tzinfo is None:
            raise SnapshotValidationError("as_of_time must be timezone-aware")
        ny_time = self.as_of_time.astimezone(MARKET_TIMEZONE)
        if ny_time.date() != self.session_date:
            raise SnapshotValidationError(
                f"as_of_time New York date {ny_time.date()} does not match session_date {self.session_date}"
            )


def parse_snapshot_dict(raw: dict[str, Any]) -> ORBSnapshot:
    """Parse a dictionary payload into an ORBSnapshot with strict validation.

    Root-level schema or bounds errors raise SnapshotValidationError (global integrity failure).
    Per-symbol corruption (e.g. malformed bar, high < low, invalid timestamp) is captured
    on the symbol payload as an integrity_error so that valid symbols remain inspectable.
    """
    if not isinstance(raw, dict):
        raise SnapshotValidationError("Snapshot root must be a JSON object")

    # Required top-level fields
    for field_name in ("session_date", "as_of_time", "source_type", "source_label", "symbols"):
        if field_name not in raw:
            raise SnapshotValidationError(f"Missing required snapshot field: '{field_name}'")

    raw_session = raw["session_date"]
    if isinstance(raw_session, str):
        try:
            session_date = date.fromisoformat(raw_session)
        except ValueError as err:
            raise SnapshotValidationError(f"Invalid session_date ISO format: {raw_session}") from err
    elif isinstance(raw_session, date):
        session_date = raw_session
    else:
        raise SnapshotValidationError(f"session_date must be an ISO date string, got: {type(raw_session)}")

    raw_as_of = raw["as_of_time"]
    if isinstance(raw_as_of, str):
        try:
            as_of_time = datetime.fromisoformat(raw_as_of)
        except ValueError as err:
            raise SnapshotValidationError(f"Invalid as_of_time ISO format: {raw_as_of}") from err
    elif isinstance(raw_as_of, datetime):
        as_of_time = raw_as_of
    else:
        raise SnapshotValidationError(f"as_of_time must be an ISO datetime string, got: {type(raw_as_of)}")

    if as_of_time.tzinfo is None:
        raise SnapshotValidationError("as_of_time must be timezone-aware")

    source_type = str(raw["source_type"]).strip()
    if source_type not in ("synthetic_demo", "user_provided_unverified"):
        raise SnapshotValidationError(
            f"Invalid source_type '{source_type}'. Must be 'synthetic_demo' or 'user_provided_unverified'."
        )

    source_label = str(raw["source_label"]).strip()
    completeness_status = str(raw.get("completeness_status", "unknown")).strip()
    notes = str(raw.get("notes", "")).strip()

    raw_symbols = raw["symbols"]
    if not isinstance(raw_symbols, dict):
        raise SnapshotValidationError("symbols must be a JSON object mapping ticker symbols to payloads")

    parsed_symbols: dict[str, SnapshotSymbolPayload] = {}
    seen_symbols_normalized: set[str] = set()

    for raw_sym, sym_data in raw_symbols.items():
        if not isinstance(raw_sym, str) or not raw_sym.strip():
            raise SnapshotValidationError("Symbol key must be a non-empty string")
        sym_norm = raw_sym.strip().upper()
        if sym_norm in seen_symbols_normalized:
            raise SnapshotValidationError(f"Duplicate symbol key in snapshot: '{raw_sym}'")
        seen_symbols_normalized.add(sym_norm)

        if not isinstance(sym_data, dict):
            parsed_symbols[sym_norm] = SnapshotSymbolPayload(
                symbol=sym_norm,
                integrity_error=f"Symbol data for '{sym_norm}' must be a JSON object",
            )
            continue

        payload_sym = str(sym_data.get("symbol", sym_norm)).strip().upper()
        if payload_sym != sym_norm:
            parsed_symbols[sym_norm] = SnapshotSymbolPayload(
                symbol=sym_norm,
                integrity_error=(
                    f"Contradictory symbol identity: key '{sym_norm}' does not match payload symbol '{payload_sym}'"
                ),
            )
            continue

        primary_exchange = sym_data.get("primary_exchange")
        if primary_exchange is not None:
            primary_exchange = str(primary_exchange).strip().upper()

        symbol_error: str | None = None
        parsed_daily: list[DailyBar] = []
        parsed_or: list[MinuteBar] = []
        parsed_prior: list[OpeningRangeVolumeObservation] = []

        # Parse daily bars
        raw_daily = sym_data.get("daily_bars", [])
        if not isinstance(raw_daily, list):
            symbol_error = f"daily_bars for '{sym_norm}' must be a list"
        else:
            for i, b in enumerate(raw_daily):
                if not isinstance(b, dict):
                    symbol_error = f"daily_bar [{i}] for '{sym_norm}' must be a JSON object"
                    break
                try:
                    b_date = (
                        b["session_date"]
                        if isinstance(b["session_date"], date)
                        else date.fromisoformat(str(b["session_date"]))
                    )
                    bar = DailyBar(
                        symbol=sym_norm,
                        session_date=b_date,
                        open=float(b["open"]),
                        high=float(b["high"]),
                        low=float(b["low"]),
                        close=float(b["close"]),
                        volume=float(b["volume"]),
                    )
                    parsed_daily.append(bar)
                except (KeyError, ValueError, TypeError, DataIntegrityError) as err:
                    symbol_error = f"Corrupt daily_bar [{i}] for symbol '{sym_norm}': {err}"
                    break

        # Parse opening range minute bars
        if symbol_error is None:
            raw_or = sym_data.get("opening_range_bars", [])
            if not isinstance(raw_or, list):
                symbol_error = f"opening_range_bars for '{sym_norm}' must be a list"
            else:
                for i, b in enumerate(raw_or):
                    if not isinstance(b, dict):
                        symbol_error = f"opening_range_bar [{i}] for '{sym_norm}' must be a JSON object"
                        break
                    try:
                        b_ts = (
                            b["timestamp"]
                            if isinstance(b["timestamp"], datetime)
                            else datetime.fromisoformat(str(b["timestamp"]))
                        )
                        bar = MinuteBar(
                            symbol=sym_norm,
                            timestamp=b_ts,
                            session_date=session_date,
                            open=float(b["open"]),
                            high=float(b["high"]),
                            low=float(b["low"]),
                            close=float(b["close"]),
                            volume=float(b["volume"]),
                        )
                        parsed_or.append(bar)
                    except (KeyError, ValueError, TypeError, DataIntegrityError) as err:
                        symbol_error = f"Corrupt opening_range_bar [{i}] for symbol '{sym_norm}': {err}"
                        break

        # Parse prior OR volume observations
        if symbol_error is None:
            raw_prior = sym_data.get("prior_opening_range_volumes", [])
            if not isinstance(raw_prior, list):
                symbol_error = f"prior_opening_range_volumes for '{sym_norm}' must be a list"
            else:
                for i, b in enumerate(raw_prior):
                    if not isinstance(b, dict):
                        symbol_error = f"prior_opening_range_volume [{i}] for '{sym_norm}' must be a JSON object"
                        break
                    try:
                        b_date = (
                            b["session_date"]
                            if isinstance(b["session_date"], date)
                            else date.fromisoformat(str(b["session_date"]))
                        )
                        obs = OpeningRangeVolumeObservation(
                            symbol=sym_norm,
                            session_date=b_date,
                            volume=float(b["volume"]),
                        )
                        parsed_prior.append(obs)
                    except (KeyError, ValueError, TypeError, DataIntegrityError) as err:
                        symbol_error = f"Corrupt prior_opening_range_volume [{i}] for symbol '{sym_norm}': {err}"
                        break

        parsed_symbols[sym_norm] = SnapshotSymbolPayload(
            symbol=sym_norm,
            daily_bars=parsed_daily,
            opening_range_bars=parsed_or,
            prior_opening_range_volumes=parsed_prior,
            primary_exchange=primary_exchange,
            integrity_error=symbol_error,
        )

    return ORBSnapshot(
        session_date=session_date,
        as_of_time=as_of_time,
        source_type=source_type,
        source_label=source_label,
        completeness_status=completeness_status,
        symbols=parsed_symbols,
        notes=notes,
    )


def parse_snapshot_json(
    content: str | bytes,
    max_bytes: int = MAX_SNAPSHOT_BYTES,
) -> ORBSnapshot:
    """Parse JSON string or bytes into an ORBSnapshot with strict size limits."""
    if isinstance(content, str):
        encoded = content.encode("utf-8")
    elif isinstance(content, (bytes, bytearray)):
        encoded = bytes(content)
    else:
        raise SnapshotValidationError(f"Expected str or bytes content, got {type(content)}")

    if len(encoded) > max_bytes:
        raise SnapshotValidationError(
            f"Snapshot file size ({len(encoded)} bytes) exceeds the maximum allowed limit of {max_bytes} bytes (5 MB)."
        )

    try:
        raw_data = json.loads(encoded.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise SnapshotValidationError(f"Malformed JSON: {err}") from err

    return parse_snapshot_dict(raw_data)


def load_demo_snapshot() -> ORBSnapshot:
    """Load the built-in synthetic demo snapshot for testing and UI demonstration."""
    from .demo_fixture import create_demo_snapshot

    return create_demo_snapshot()

