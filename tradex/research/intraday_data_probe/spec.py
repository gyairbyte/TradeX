"""Locked probe-spec loading and validation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BoundedWindowProbe:
    id: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class OverlapProbe:
    symbol: str
    left_start_date: str
    left_end_date: str
    right_start_date: str
    right_end_date: str


@dataclass(frozen=True)
class IntradayProbeSpec:
    """Machine-readable INTRA-001B probe specification."""

    schema_version: int
    task_id: str
    provider: str
    bar_interval: str
    timezone: str
    exchange_calendar: str
    need_extended_hours_data: bool
    repeat_count: int
    request_delay_seconds: float
    symbols: tuple[str, ...]
    methods: tuple[str, ...]
    full_range_probe: dict[str, Any]
    bounded_window_probes: tuple[BoundedWindowProbe, ...]
    overlap_probe: OverlapProbe
    exclude_early_close_sessions_from_primary_coverage: bool
    minimum_regular_session_coverage_pct: float
    maximum_duplicate_bar_rate_pct: float
    maximum_zero_volume_bar_rate_pct: float
    maximum_persistent_retry_count: int
    decision_requires_repeat_hash_match: bool
    decision_requires_method_overlap_match: bool
    decision_requires_chunk_overlap_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "provider": self.provider,
            "bar_interval": self.bar_interval,
            "timezone": self.timezone,
            "exchange_calendar": self.exchange_calendar,
            "need_extended_hours_data": self.need_extended_hours_data,
            "repeat_count": self.repeat_count,
            "request_delay_seconds": self.request_delay_seconds,
            "symbols": list(self.symbols),
            "methods": list(self.methods),
            "full_range_probe": self.full_range_probe,
            "bounded_window_probes": [
                {"id": w.id, "start_date": w.start_date, "end_date": w.end_date}
                for w in self.bounded_window_probes
            ],
            "overlap_probe": {
                "symbol": self.overlap_probe.symbol,
                "left_start_date": self.overlap_probe.left_start_date,
                "left_end_date": self.overlap_probe.left_end_date,
                "right_start_date": self.overlap_probe.right_start_date,
                "right_end_date": self.overlap_probe.right_end_date,
            },
            "exclude_early_close_sessions_from_primary_coverage": self.exclude_early_close_sessions_from_primary_coverage,
            "minimum_regular_session_coverage_pct": self.minimum_regular_session_coverage_pct,
            "maximum_duplicate_bar_rate_pct": self.maximum_duplicate_bar_rate_pct,
            "maximum_zero_volume_bar_rate_pct": self.maximum_zero_volume_bar_rate_pct,
            "maximum_persistent_retry_count": self.maximum_persistent_retry_count,
            "decision_requires_repeat_hash_match": self.decision_requires_repeat_hash_match,
            "decision_requires_method_overlap_match": self.decision_requires_method_overlap_match,
            "decision_requires_chunk_overlap_match": self.decision_requires_chunk_overlap_match,
        }


class SpecValidationError(ValueError):
    """Raised when a probe spec violates the locked contract."""


_ALLOWED_TOP_LEVEL = {f.name for f in IntradayProbeSpec.__dataclass_fields__.values()}


def _require_known_fields(data: dict[str, Any], allowed: set[str], path: str = "") -> None:
    for key in data:
        if key not in allowed:
            raise SpecValidationError(f"Unknown field {path}.{key}")


def _as_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    raise SpecValidationError(f"{name} must be a list of strings")


def load_probe_spec(path: str | Path) -> tuple[IntradayProbeSpec, bytes]:
    """Load and validate a probe specification, returning the object and raw bytes."""
    p = Path(path).expanduser().resolve()
    raw = p.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SpecValidationError("Probe spec must be a JSON object")

    _require_known_fields(data, _ALLOWED_TOP_LEVEL)

    windows = []
    for entry in data.get("bounded_window_probes", []):
        if not isinstance(entry, dict):
            raise SpecValidationError("bounded_window_probes entries must be objects")
        _require_known_fields(entry, {"id", "start_date", "end_date"}, "bounded_window_probes")
        windows.append(BoundedWindowProbe(
            id=str(entry["id"]),
            start_date=str(entry["start_date"]),
            end_date=str(entry["end_date"]),
        ))

    overlap = data.get("overlap_probe", {})
    if not isinstance(overlap, dict):
        raise SpecValidationError("overlap_probe must be an object")
    _require_known_fields(overlap, {"symbol", "left_start_date", "left_end_date", "right_start_date", "right_end_date"}, "overlap_probe")

    full = data.get("full_range_probe", {})
    if not isinstance(full, dict):
        raise SpecValidationError("full_range_probe must be an object")
    _require_known_fields(full, {"symbols", "start_date", "end_date"}, "full_range_probe")

    spec = IntradayProbeSpec(
        schema_version=int(data["schema_version"]),
        task_id=str(data["task_id"]),
        provider=str(data["provider"]),
        bar_interval=str(data["bar_interval"]),
        timezone=str(data["timezone"]),
        exchange_calendar=str(data["exchange_calendar"]),
        need_extended_hours_data=bool(data["need_extended_hours_data"]),
        repeat_count=int(data["repeat_count"]),
        request_delay_seconds=float(data["request_delay_seconds"]),
        symbols=_as_tuple(data["symbols"], "symbols"),
        methods=_as_tuple(data["methods"], "methods"),
        full_range_probe=dict(full),
        bounded_window_probes=tuple(windows),
        overlap_probe=OverlapProbe(
            symbol=str(overlap["symbol"]),
            left_start_date=str(overlap["left_start_date"]),
            left_end_date=str(overlap["left_end_date"]),
            right_start_date=str(overlap["right_start_date"]),
            right_end_date=str(overlap["right_end_date"]),
        ),
        exclude_early_close_sessions_from_primary_coverage=bool(data["exclude_early_close_sessions_from_primary_coverage"]),
        minimum_regular_session_coverage_pct=float(data["minimum_regular_session_coverage_pct"]),
        maximum_duplicate_bar_rate_pct=float(data["maximum_duplicate_bar_rate_pct"]),
        maximum_zero_volume_bar_rate_pct=float(data["maximum_zero_volume_bar_rate_pct"]),
        maximum_persistent_retry_count=int(data["maximum_persistent_retry_count"]),
        decision_requires_repeat_hash_match=bool(data["decision_requires_repeat_hash_match"]),
        decision_requires_method_overlap_match=bool(data["decision_requires_method_overlap_match"]),
        decision_requires_chunk_overlap_match=bool(data["decision_requires_chunk_overlap_match"]),
    )
    return spec, raw


def sha256_of_spec(path: str | Path) -> str:
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()
