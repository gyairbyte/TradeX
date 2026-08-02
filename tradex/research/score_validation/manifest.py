"""Manifest loading, validation, and construction."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.backtest.models import _clean  # noqa: PLC2701
from tradex.backtest.validation import canonicalize_bars

from .models import DatasetManifest, ManifestEntry, Split, ValidationError


SCHEMA_VERSION = 1


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load and validate a manifest file, returning a typed DatasetManifest."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValidationError(f"Manifest file not found: {path}")
    data = json.loads(path.read_text())
    base_dir = path.parent
    manifest = _parse_manifest(data, base_dir)
    object.__setattr__(manifest, "_base_dir", base_dir.resolve())
    return manifest


def _parse_manifest(data: dict, base_dir: Path) -> DatasetManifest:
    """Validate and convert raw manifest JSON to a DatasetManifest."""
    if not isinstance(data, dict):
        raise ValidationError("Manifest must be a JSON object")

    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValidationError(
            f"Unsupported manifest schema version: {schema_version!r}; expected {SCHEMA_VERSION}"
        )

    dataset_name = data.get("dataset_name")
    if not dataset_name or not isinstance(dataset_name, str):
        raise ValidationError("Manifest must have a nonempty 'dataset_name'")

    created_at = _parse_datetime(data.get("created_at"), "created_at")
    source_description = data.get("source_description", "")
    if not isinstance(source_description, str):
        raise ValidationError("'source_description' must be a string")

    entries_data = data.get("entries")
    if not isinstance(entries_data, list) or not entries_data:
        raise ValidationError("Manifest must contain a nonempty 'entries' list")

    splits_data = data.get("splits")
    if not isinstance(splits_data, dict) or not splits_data:
        raise ValidationError("Manifest must contain a 'splits' object")

    entries = []
    seen_tickers: set[str] = set()
    for idx, raw in enumerate(entries_data):
        entry = _parse_entry(raw, base_dir, idx)
        if entry.ticker in seen_tickers:
            raise ValidationError(f"Duplicate ticker in manifest: {entry.ticker}")
        seen_tickers.add(entry.ticker)
        entries.append(entry)

    splits = _parse_splits(splits_data)

    return DatasetManifest(
        schema_version=schema_version,
        dataset_name=dataset_name,
        created_at=created_at,
        source_description=source_description,
        entries=tuple(entries),
        splits=splits,
    )


def _parse_entry(raw: dict, base_dir: Path, idx: int) -> ManifestEntry:
    """Parse and validate one manifest entry."""
    if not isinstance(raw, dict):
        raise ValidationError(f"Entry {idx} must be an object")

    ticker = raw.get("ticker")
    if not isinstance(ticker, str) or not ticker:
        raise ValidationError(f"Entry {idx} has an invalid ticker")
    if ticker != ticker.upper():
        raise ValidationError(f"Entry {idx} ticker must be uppercase; got {ticker!r}")

    rel_path = raw.get("path")
    if not isinstance(rel_path, str) or not rel_path:
        raise ValidationError(f"Entry {ticker}: 'path' must be a nonempty string")
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise ValidationError(f"Entry {ticker}: 'path' must be relative; got {rel_path!r}")
    if ".." in Path(rel_path).parts:
        raise ValidationError(f"Entry {ticker}: 'path' must not contain '..';")

    csv_path = (base_dir / rel_path).resolve()
    try:
        csv_path.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ValidationError(
            f"Entry {ticker}: resolved path {csv_path} must remain under {base_dir}"
        ) from exc
    if not csv_path.is_file():
        raise ValidationError(f"Entry {ticker}: CSV not found at {rel_path}")

    expected_sha = raw.get("sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValidationError(f"Entry {ticker}: 'sha256' must be 64 lowercase hex characters")
    try:
        int(expected_sha, 16)
    except ValueError as exc:
        raise ValidationError(f"Entry {ticker}: 'sha256' is not valid hex") from exc
    if expected_sha != expected_sha.lower():
        raise ValidationError(f"Entry {ticker}: 'sha256' must be lowercase hex")

    actual_sha = _sha256_file(csv_path)
    if actual_sha != expected_sha:
        raise ValidationError(
            f"Entry {ticker}: SHA-256 mismatch for {rel_path}: "
            f"expected {expected_sha}, got {actual_sha}"
        )

    rows = raw.get("rows")
    if not isinstance(rows, int) or rows < 0:
        raise ValidationError(f"Entry {ticker}: 'rows' must be a nonnegative integer")

    start = _parse_datetime(raw.get("start"), f"Entry {ticker} start")
    end = _parse_datetime(raw.get("end"), f"Entry {ticker} end")
    if end < start:
        raise ValidationError(f"Entry {ticker}: end must be >= start")

    data_source = raw.get("data_source")
    if not isinstance(data_source, str) or not data_source:
        raise ValidationError(f"Entry {ticker}: 'data_source' must be a nonempty string")

    adjustment_policy = raw.get("adjustment_policy")
    if not isinstance(adjustment_policy, str):
        raise ValidationError(f"Entry {ticker}: 'adjustment_policy' must be a string")

    # Validate canonical bars and compare row count/date range.
    df = _load_and_canonicalize(csv_path)
    if len(df) != rows:
        raise ValidationError(
            f"Entry {ticker}: row count mismatch: manifest says {rows}, file has {len(df)}"
        )
    if df.index.empty:
        raise ValidationError(f"Entry {ticker}: CSV contains no rows")
    file_start = df.index[0].to_pydatetime()
    file_end = df.index[-1].to_pydatetime()
    if file_start != start:
        raise ValidationError(
            f"Entry {ticker}: start mismatch: manifest {_iso(start)}, file {_iso(file_start)}"
        )
    if file_end != end:
        raise ValidationError(
            f"Entry {ticker}: end mismatch: manifest {_iso(end)}, file {_iso(file_end)}"
        )

    return ManifestEntry(
        ticker=ticker,
        path=rel_path,
        sha256=expected_sha,
        rows=rows,
        start=start,
        end=end,
        data_source=data_source,
        adjustment_policy=adjustment_policy,
    )


def _parse_splits(data: dict) -> dict[str, Split]:
    """Validate temporal splits."""
    required = ["development", "validation", "holdout"]
    missing = [r for r in required if r not in data]
    if missing:
        raise ValidationError(f"Manifest missing required splits: {missing}")

    splits: dict[str, Split] = {}
    prev_end: date | None = None
    for name in required:
        raw = data.get(name)
        if not isinstance(raw, dict):
            raise ValidationError(f"Split {name} must be an object")
        start = _parse_date(raw.get("start"), f"Split {name} start")
        end = _parse_date(raw.get("end"), f"Split {name} end")
        if end < start:
            raise ValidationError(f"Split {name}: end must be >= start")
        if prev_end is not None and start < prev_end:
            raise ValidationError(
                f"Split {name}: start {start} is before previous split end {prev_end}"
            )
        if prev_end is not None and start == prev_end:
            # Non-overlapping but contiguous is allowed.
            pass
        prev_end = end
        splits[name] = Split(start=start, end=end)
    return splits


def _load_and_canonicalize(csv_path: Path) -> pd.DataFrame:
    """Load a CSV and canonicalize it through the existing backtest validator."""
    df = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
    return canonicalize_bars(df)


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_datetime(value: Any, label: str) -> datetime:
    """Parse an ISO datetime string into a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationError(f"{label} datetime is naive")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty ISO datetime string")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label} is not a valid ISO datetime: {value}") from exc
    if dt.tzinfo is None:
        raise ValidationError(f"{label} datetime is naive: {value}")
    return dt.astimezone(timezone.utc)


def _parse_date(value: Any, label: str) -> date:
    """Parse an ISO date string into a date."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label} is not a valid ISO date: {value}") from exc


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


# Sentinel for optional args used by snapshot builder.
def build_manifest(
    dataset_name: str,
    source_description: str,
    entries: list[ManifestEntry],
    splits: dict[str, Split],
    created_at: datetime | None = None,
) -> DatasetManifest:
    """Build a validated DatasetManifest from already-validated entries."""
    if not entries:
        raise ValidationError("Cannot build manifest with no entries")
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    return DatasetManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        created_at=created_at,
        source_description=source_description,
        entries=tuple(entries),
        splits=splits,
    )


def write_manifest(manifest: DatasetManifest, path: str | Path) -> None:
    """Write a manifest to JSON deterministically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": manifest.schema_version,
        "dataset_name": manifest.dataset_name,
        "created_at": manifest.created_at.isoformat(),
        "source_description": manifest.source_description,
        "entries": [
            {
                "ticker": e.ticker,
                "path": e.path,
                "sha256": e.sha256,
                "rows": e.rows,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "data_source": e.data_source,
                "adjustment_policy": e.adjustment_policy,
            }
            for e in sorted(manifest.entries, key=lambda e: e.ticker)
        ],
        "splits": {
            name: {"start": s.start.isoformat(), "end": s.end.isoformat()}
            for name, s in sorted(manifest.splits.items())
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
