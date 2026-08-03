"""Offline daily-OHLCV snapshot creation and manifest locking."""
from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from tradex.data.history import fetch_daily_history

from .models import (
    DatasetManifest,
    ManifestEntry,
    Split,
    ValidationError,
)

_CANONICAL_COLUMNS = ["open", "high", "low", "close", "volume"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_ticker_input(ticker: str) -> str:
    """Normalize and validate a single ticker symbol before use in paths."""
    t = ticker.strip().upper()
    if not t:
        raise ValidationError("ticker must not be empty")
    if not t.isalnum():
        raise ValidationError(f"ticker must be alphanumeric; got {t!r}")
    if any(sep in t for sep in ("/", "\\", ".", "..", "~")):
        raise ValidationError(f"ticker contains path-like characters; got {t!r}")
    return t


def _validate_ticker_inputs(tickers: list[str]) -> None:
    """Reject empty, duplicate, malformed, or path-like ticker input."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        t = _validate_ticker_input(raw)
        if t in seen:
            raise ValidationError(f"duplicate ticker: {t}")
        seen.add(t)
        normalized.append(t)


def _validate_ticker_df(df: pd.DataFrame, start: date, end: date) -> tuple[pd.DataFrame, list[str], dict[str, int]]:
    """Validate and clean one ticker's OHLCV DataFrame.

    Returns (cleaned_df, warnings, counts).
    """
    warnings: list[str] = []
    counts: dict[str, int] = {
        "duplicate_timestamps": 0,
        "missing_required_values": 0,
        "invalid_ohlc_rows": 0,
        "bars_outside_range": 0,
    }

    if df.empty:
        return df, ["empty DataFrame"], counts

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "datetime"

    # Ensure canonical columns.
    for col in _CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_CANONICAL_COLUMNS]
    df = df.apply(pd.to_numeric, errors="coerce")

    # Drop duplicate timestamps, keep last, then sort deterministically.
    before = len(df)
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    counts["duplicate_timestamps"] = before - len(df)

    # Restrict to requested date range.
    start_dt = pd.Timestamp(start, tz="UTC")
    end_dt = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    in_range = (df.index >= start_dt) & (df.index <= end_dt)
    counts["bars_outside_range"] = int((~in_range).sum())
    df = df[in_range]

    if df.empty:
        return df, ["no bars within requested date range"], counts

    # Validate each row and drop rows that violate OHLCV invariants.
    valid = (
        pd.notna(df["open"]) & pd.notna(df["high"]) & pd.notna(df["low"]) & pd.notna(df["close"]) & pd.notna(df["volume"])
        & (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)
        & (df["volume"] >= 0)
        & (df["high"] >= df["low"])
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & df["open"].apply(lambda x: math.isfinite(x))
        & df["high"].apply(lambda x: math.isfinite(x))
        & df["low"].apply(lambda x: math.isfinite(x))
        & df["close"].apply(lambda x: math.isfinite(x))
        & df["volume"].apply(lambda x: math.isfinite(x))
    )
    invalid = (~valid).sum()
    counts["missing_required_values"] = int(df[_CANONICAL_COLUMNS].isna().sum().sum())
    counts["invalid_ohlc_rows"] = int(invalid)
    df = df[valid]

    for name, value in counts.items():
        if value:
            warnings.append(f"{name}: {value}")

    return df, warnings, counts


def _count_complete_bars(df: pd.DataFrame, lookback: int, holding: int) -> tuple[int, int]:
    """Count rows with enough preceding lookback and following forward bars."""
    complete_lookbacks = 0
    complete_forward_bars = 0
    n = len(df)
    for i in range(n):
        if i >= lookback - 1:
            complete_lookbacks += 1
        if i + holding < n:
            complete_forward_bars += 1
    return complete_lookbacks, complete_forward_bars


def _count_split_events(df: pd.DataFrame, splits: dict[str, Split], lookback: int, holding: int, move_days: int, runup_pct: float = 15.0, decline_pct: float = 12.0) -> dict[str, int]:
    """Count mined events per split for data-quality reporting (no future leakage)."""
    from .fingerprints import _find_events  # local import to avoid circularity

    counts: dict[str, int] = {}
    for name, split in splits.items():
        mask = (df.index >= pd.Timestamp(split.start, tz="UTC")) & (df.index <= pd.Timestamp(split.end, tz="UTC"))
        split_df = df[mask]
        if len(split_df) < lookback + move_days + holding + 5:
            counts[name] = 0
            continue
        runups = _find_events(split_df, runup_pct=runup_pct, decline_pct=decline_pct, move_days=move_days, lookback=lookback, event_type="runup")
        declines = _find_events(split_df, runup_pct=runup_pct, decline_pct=decline_pct, move_days=move_days, lookback=lookback, event_type="decline")
        counts[name] = len(runups) + len(declines)
    return counts


def create_snapshot(
    tickers: list[str],
    start: date,
    end: date,
    output_dir: str | Path,
    splits: dict[str, Split],
    provider: str | None = None,
    overwrite: bool = False,
    dataset_name: str = "pattern-similarity-validation",
    source_description: str = "offline OHLCV snapshots",
    adjustment_policy: str = "provider_default",
    fetch_fn: Callable[[str, date, date, str | None], pd.DataFrame] | None = None,
    created_at: datetime | None = None,
) -> Path:
    """Fetch or receive per-ticker OHLCV data and write an atomic snapshot with manifest.

    ``fetch_fn`` is injected for credential-free tests; it defaults to
    ``tradex.data.history.fetch_daily_history``.

    ``created_at`` is normally the current UTC wall-clock time. It can be
    injected for reproducible snapshot manifests in tests or for a deliberate
    dataset version label.
    """
    output_dir = Path(output_dir)
    if output_dir.exists() and not overwrite:
        raise ValidationError(f"output directory already exists: {output_dir}. Use --overwrite.")

    stage_dir = Path(tempfile.mkdtemp(prefix="pattern_validation_snapshot_"))
    try:
        fetcher = fetch_fn or fetch_daily_history
        _validate_ticker_inputs(tickers)
        requested_tickers = tuple(str(t).strip().upper() for t in tickers)
        entries: list[ManifestEntry] = []
        successful: list[str] = []
        failed: list[str] = []
        failure_categories: list[str] = []

        for ticker in requested_tickers:
            try:
                df = fetcher(ticker, start, end, provider)
                if df is None or df.empty:
                    raise ValueError("no data returned")
            except Exception as exc:  # noqa: BLE001
                category = type(exc).__name__
                failed.append(ticker)
                if category not in failure_categories:
                    failure_categories.append(category)
                entries.append(ManifestEntry(
                    ticker=ticker,
                    path="",
                    sha256="",
                    rows=0,
                    start=None,
                    end=None,
                    data_source=provider or "unknown",
                    adjustment_policy=adjustment_policy,
                    failure=category,
                    quality={},
                    warnings=[category],
                ))
                continue

            df, warnings, counts = _validate_ticker_df(df, start, end)
            if df.empty:
                failed.append(ticker)
                if "no_valid_bars" not in failure_categories:
                    failure_categories.append("no_valid_bars")
                entries.append(ManifestEntry(
                    ticker=ticker,
                    path="",
                    sha256="",
                    rows=0,
                    start=None,
                    end=None,
                    data_source=provider or "unknown",
                    adjustment_policy=adjustment_policy,
                    failure="no_valid_bars",
                    quality=counts,
                    warnings=warnings,
                ))
                continue

            file_path = stage_dir / f"{ticker}.csv"
            df.to_csv(file_path, index=True)
            file_sha = _sha256_file(file_path)
            successful.append(ticker)

            entry = ManifestEntry(
                ticker=ticker,
                path=str(file_path.relative_to(stage_dir)),
                sha256=file_sha,
                rows=len(df),
                start=df.index.min().to_pydatetime(),
                end=df.index.max().to_pydatetime(),
                data_source=provider or "unknown",
                adjustment_policy=adjustment_policy,
                failure=None,
                quality=counts,
                warnings=warnings,
            )
            entries.append(entry)

            # Quality and warnings are stored on the entry for downstream reporting.

        # Build manifest.
        manifest = DatasetManifest(
            schema_version=1,
            dataset_name=dataset_name,
            created_at=created_at or datetime.now(UTC),
            source_description=source_description,
            provider=provider or "unknown",
            adjustment_policy=adjustment_policy,
            request_start=start,
            request_end=end,
            entries=tuple(entries),
            splits=splits,
            requested_tickers=requested_tickers,
            successful_tickers=tuple(successful),
            failed_tickers=tuple(failed),
            failure_categories=tuple(failure_categories),
        )

        manifest_path = stage_dir / "manifest.lock.json"
        with manifest_path.open("w", encoding="utf-8") as f:
            f.write(manifest.to_json(indent=2))

        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.move(str(stage_dir), str(output_dir))

        return output_dir / "manifest.lock.json"
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def _load_ticker_csv(manifest_dir: Path, entry: ManifestEntry) -> pd.DataFrame:
    """Load one ticker snapshot CSV into a canonical UTC-indexed DataFrame."""
    path = manifest_dir / entry.path
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    for col in _CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_CANONICAL_COLUMNS].apply(pd.to_numeric, errors="coerce")
    return df


def load_snapshot(manifest_path: str | Path) -> tuple[DatasetManifest, dict[str, pd.DataFrame]]:
    """Load a manifest and all associated ticker CSVs, verifying per-file SHA-256."""
    manifest_path = Path(manifest_path)
    manifest_dir = manifest_path.parent
    from .models import ValidationError, load_manifest

    manifest = load_manifest(manifest_path)
    if not manifest.verify_integrity():
        raise ValidationError("manifest metadata integrity check failed")

    bars: dict[str, pd.DataFrame] = {}
    for entry in manifest.entries:
        if entry.failure or not entry.path:
            continue
        path = manifest_dir / entry.path
        if not path.exists():
            raise ValidationError(f"manifest entry missing on disk: {path}")
        actual = _sha256_file(path)
        if actual != entry.sha256:
            raise ValidationError(f"checksum mismatch for {entry.ticker}: expected {entry.sha256}, got {actual}")
        bars[entry.ticker] = _load_ticker_csv(manifest_dir, entry)
    return manifest, bars
