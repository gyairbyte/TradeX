"""Offline daily-OHLCV snapshot creation and manifest locking."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from tradex.data.history import fetch_daily_history

from .models import (
    DatasetManifest,
    DataQualityRow,
    ManifestEntry,
    Split,
    ValidationError,
    _clean,
)


_CANONICAL_COLUMNS = ["open", "high", "low", "close", "volume"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


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

    # Drop duplicate timestamps, keep last.
    before = len(df)
    df = df[~df.index.duplicated(keep="last")]
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


def _build_data_quality(
    ticker: str,
    entry: ManifestEntry,
    df: pd.DataFrame,
    counts: dict[str, int],
    split_event_counts: dict[str, int],
    warnings: list[str],
    complete_lookbacks: int,
    complete_forward_bars: int,
) -> DataQualityRow:
    return DataQualityRow(
        ticker=ticker,
        data_source=entry.data_source,
        sha256=entry.sha256,
        manifest_rows=entry.rows,
        validated_rows=len(df),
        data_start=df.index.min().to_pydatetime() if not df.empty else None,
        data_end=df.index.max().to_pydatetime() if not df.empty else None,
        duplicate_timestamps=counts["duplicate_timestamps"],
        missing_required_values=counts["missing_required_values"],
        invalid_ohlc_rows=counts["invalid_ohlc_rows"],
        bars_outside_range=counts["bars_outside_range"],
        complete_lookbacks=complete_lookbacks,
        complete_forward_bars=complete_forward_bars,
        split_event_counts=split_event_counts,
        warnings=warnings,
    )


def _count_split_events(df: pd.DataFrame, splits: dict[str, Split], lookback: int, holding: int, move_days: int) -> dict[str, int]:
    """Count mined events per split for data-quality reporting (no future leakage)."""
    from .fingerprints import _find_events  # local import to avoid circularity

    counts: dict[str, int] = {}
    for name, split in splits.items():
        mask = (df.index >= pd.Timestamp(split.start, tz="UTC")) & (df.index <= pd.Timestamp(split.end, tz="UTC"))
        split_df = df[mask]
        if len(split_df) < lookback + move_days + holding + 5:
            counts[name] = 0
            continue
        runups = _find_events(split_df, runup_pct=15.0, decline_pct=12.0, move_days=move_days, lookback=lookback, event_type="runup")
        declines = _find_events(split_df, runup_pct=15.0, decline_pct=12.0, move_days=move_days, lookback=lookback, event_type="decline")
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
) -> Path:
    """Fetch or receive per-ticker OHLCV data and write an atomic snapshot with manifest.

    ``fetch_fn`` is injected for credential-free tests; it defaults to
    ``tradex.data.history.fetch_daily_history``.
    """
    output_dir = Path(output_dir)
    if output_dir.exists() and not overwrite:
        raise ValidationError(f"output directory already exists: {output_dir}. Use --overwrite.")

    stage_dir = Path(tempfile.mkdtemp(prefix="pattern_validation_snapshot_"))
    try:
        fetcher = fetch_fn or fetch_daily_history
        requested_tickers = tuple(str(t).strip().upper() for t in tickers)
        entries: list[ManifestEntry] = []
        data_quality_rows: list[DataQualityRow] = []
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
            )
            entries.append(entry)

            # Data-quality counts use a default lookback/holding for reporting.
            split_event_counts = _count_split_events(df, splits, lookback=10, holding=5, move_days=5)
            complete_lookbacks = int((df.index.to_series().diff().dt.days <= 5).sum())  # placeholder; refined later
            complete_forward_bars = int((df.index.to_series().diff().dt.days <= 5).sum())  # placeholder
            data_quality_rows.append(_build_data_quality(
                ticker, entry, df, counts, split_event_counts, warnings,
                complete_lookbacks, complete_forward_bars,
            ))

        # Build manifest.
        manifest = DatasetManifest(
            schema_version=1,
            dataset_name=dataset_name,
            created_at=datetime.now(timezone.utc),
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
    """Load a manifest and all associated ticker CSVs."""
    manifest_path = Path(manifest_path)
    manifest_dir = manifest_path.parent
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    from .models import load_manifest
    manifest = load_manifest(manifest_path)
    bars: dict[str, pd.DataFrame] = {}
    for entry in manifest.entries:
        if entry.failure or not entry.path:
            continue
        bars[entry.ticker] = _load_ticker_csv(manifest_dir, entry)
    return manifest, bars
