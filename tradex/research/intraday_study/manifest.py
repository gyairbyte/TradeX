"""Manifest and integrity verification for the locked INTRA-001B-DATASET-V1 snapshot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


class ManifestError(Exception):
    """Raised when a manifest or file integrity check fails."""


@dataclass(frozen=True)
class SymbolMonth:
    """A single symbol/effective-month pair in the dataset."""

    manifest_id: str
    symbol: str
    effective_month: str
    split: str
    relative_path: str
    sha256: str
    file_size_bytes: int


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_of_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file on disk."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest_lock(path: Path) -> list[dict[str, Any]]:
    """Load the locked manifest.lock.json file and return the file records."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"manifest.lock.json not found: {p}")
    data = _read_json(p)
    files = data.get("files", [])
    if not isinstance(files, list):
        raise ManifestError("manifest.lock.json 'files' must be a list")
    return files


def verify_dataset_integrity(
    dataset_root: Path,
    manifest_records: list[dict[str, Any]],
    ohlcv_subdir: str = "ohlcv",
) -> list[SymbolMonth]:
    """Verify every manifest record exists and matches its SHA-256.

    Returns a list of ``SymbolMonth`` objects for the verified records.
    """
    root = Path(dataset_root).expanduser().resolve()
    verified: list[SymbolMonth] = []
    errors: list[str] = []
    for rec in manifest_records:
        rel = rec.get("relative_path")
        manifest_id = rec.get("manifest_id") or rel
        expected_sha = rec.get("sha256")
        symbol = rec.get("symbol")
        effective_month = rec.get("effective_month")
        if not rel or not expected_sha:
            errors.append(f"manifest record missing required fields: {rec}")
            continue
        file_path = root / ohlcv_subdir / rel
        if not file_path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        actual_sha = sha256_of_file(file_path)
        if actual_sha != expected_sha:
            errors.append(
                f"sha256 mismatch for {rel}: expected {expected_sha}, got {actual_sha}"
            )
            continue
        verified.append(
            SymbolMonth(
                manifest_id=manifest_id,
                symbol=symbol or manifest_id.split("/")[-1],
                effective_month=effective_month or manifest_id.split("/")[1],
                relative_path=rel,
                sha256=expected_sha,
                file_size_bytes=int(rec.get("file_size_bytes", 0) or 0),
                split="",
            )
        )
    if errors:
        raise ManifestError("dataset integrity verification failed: " + "; ".join(errors))
    return verified


def load_ohlcv_manifest(path: Path) -> pd.DataFrame:
    """Load the ohlcv_manifest.csv as a DataFrame."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"ohlcv_manifest.csv not found: {p}")
    return pd.read_csv(p, dtype=str)


def load_data_quality(path: Path) -> pd.DataFrame:
    """Load the data_quality.csv as a DataFrame."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"data_quality.csv not found: {p}")
    df = pd.read_csv(p, dtype=str)
    # Convert numeric columns back to numeric where possible.
    for col in [
        "expected_bars",
        "actual_bars",
        "missing_bars",
        "missing_bar_rate_pct",
        "zero_volume_bars",
        "zero_volume_bar_rate_pct",
        "invalid_ohlc_rows",
        "off_grid_bars",
        "premarket_removed",
        "after_hours_removed",
        "early_close_removed",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "pre_normalization_metrics_available" in df.columns:
        df["pre_normalization_metrics_available"] = df[
            "pre_normalization_metrics_available"
        ].map({"True": True, "False": False, "true": True, "false": False})
    return df


def load_universe_manifest(path: Path) -> pd.DataFrame:
    """Load the universe_manifest.csv as a DataFrame."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"universe_manifest.csv not found: {p}")
    df = pd.read_csv(p, dtype=str)
    for col in ["prior_close", "median_prior_20_dollar_volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "included" in df.columns:
        df["included"] = df["included"].map({"True": True, "False": False})
    return df


def load_dataset_plan(path: Path) -> dict[str, Any]:
    """Load the locked dataset_plan.lock.json file."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"dataset_plan.lock.json not found: {p}")
    data = _read_json(p)
    return data


def verify_dataset_plan_sha(dataset_plan: dict[str, Any], expected_sha: str | None = None) -> None:
    """Verify the dataset plan contains the expected spec and amendment references."""
    spec_ref = dataset_plan.get("strategy_spec", {})
    if spec_ref.get("sha256") != expected_sha:
        raise ManifestError(
            f"dataset_plan strategy_spec SHA mismatch: expected {expected_sha}, got {spec_ref.get('sha256')}"
        )


def month_split(effective_month: str) -> str:
    """Map an effective month to development/validation/holdout split."""
    split_map = {
        "2025-01": "development",
        "2025-02": "development",
        "2025-03": "development",
        "2025-04": "development",
        "2025-05": "development",
        "2025-06": "development",
        "2025-07": "validation",
        "2025-08": "validation",
        "2025-09": "validation",
        "2025-10": "holdout",
        "2025-11": "holdout",
        "2025-12": "holdout",
    }
    return split_map.get(effective_month, "unknown")


def get_symbol_months_for_split(
    data_quality_df: pd.DataFrame,
    split: str,
) -> list[SymbolMonth]:
    """Return ``SymbolMonth`` objects for the requested split using locked month mapping."""
    rows = data_quality_df[data_quality_df["split"] == split]
    return [
        SymbolMonth(
            manifest_id=row.get("manifest_id") or f"{row['effective_month']}/{row['symbol']}",
            symbol=row["symbol"],
            effective_month=row["effective_month"],
            split=split,
            relative_path=row.get("relative_path", f"{row['effective_month']}/{row['symbol']}.parquet"),
            sha256=row.get("file_sha256", ""),
            file_size_bytes=0,
        )
        for _, row in rows.iterrows()
    ]


def get_effective_month_dates(start_month: str) -> tuple[date, date]:
    """Return (start_date, end_date) for an effective month ISO string YYYY-MM."""
    import calendar

    year, month = int(start_month[:4]), int(start_month[5:7])
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last
