"""Manifest and integrity verification for the locked INTRA-001B-DATASET-V1 snapshot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .split import split_for_effective_month


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


@dataclass(frozen=True)
class VerifiedDataset:
    """A verified, locked dataset bundle."""

    symbol_months: list[SymbolMonth]
    by_split: dict[str, list[SymbolMonth]]
    manifest_sha256: str
    ohlcv_manifest: pd.DataFrame
    data_quality: pd.DataFrame
    universe_manifest: pd.DataFrame


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


def _safe_relative_path(root: Path, rel: str, ohlcv_subdir: str) -> Path:
    """Return a contained file path and reject traversal or absolute paths."""
    if not rel or rel.startswith(("/", "\\")):
        raise ManifestError(f"absolute or empty relative_path: {rel!r}")
    parts = Path(rel).parts
    if any(part == ".." for part in parts):
        raise ManifestError(f"relative_path contains '..': {rel!r}")
    target = (root / ohlcv_subdir / rel).resolve()
    base = (root / ohlcv_subdir).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ManifestError(f"relative_path escapes ohlcv root: {rel!r}") from e
    return target


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
        try:
            file_path = _safe_relative_path(root, rel, ohlcv_subdir)
        except ManifestError as e:
            errors.append(str(e))
            continue
        if not file_path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        actual_sha = sha256_of_file(file_path)
        if actual_sha != expected_sha:
            errors.append(
                f"sha256 mismatch for {rel}: expected {expected_sha}, got {actual_sha}"
            )
            continue
        split = split_for_effective_month(effective_month) if effective_month else ""
        verified.append(
            SymbolMonth(
                manifest_id=manifest_id,
                symbol=symbol or manifest_id.split("/")[-1],
                effective_month=effective_month or manifest_id.split("/")[1],
                relative_path=rel,
                sha256=expected_sha,
                file_size_bytes=int(rec.get("file_size_bytes", 0) or 0),
                split=split,
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


def verify_dataset_plan_file(path: Path, expected_sha256: str | None = None) -> str:
    """Verify the dataset plan file hash and return it."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"dataset_plan.lock.json not found: {p}")
    actual = sha256_of_file(p)
    if expected_sha256 is not None and actual != expected_sha256:
        raise ManifestError(
            f"dataset_plan.lock.json SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return actual


def verify_dataset_plan_linkage(plan_path: Path, committed_plan_path: Path) -> str:
    """Verify the dataset plan lock links to the committed locked plan.

    The build may store a variant of the committed plan, so we verify the locked
    references and dataset structure are identical rather than requiring a byte-
    for-byte match.  Returns the SHA-256 of the on-disk dataset plan lock.
    """
    p = Path(plan_path).expanduser().resolve()
    if not p.is_file():
        raise ManifestError(f"dataset_plan.lock.json not found: {p}")
    committed = _read_json(committed_plan_path)
    plan = _read_json(p)

    def _ref(obj: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(key)
        return obj

    for section, expected, actual in [
        (
            "original_strategy_spec.sha256",
            _ref(committed, "original_strategy_spec", "sha256"),
            _ref(plan, "original_strategy_spec", "sha256"),
        ),
        (
            "data_sufficiency_amendment.sha256",
            _ref(committed, "data_sufficiency_amendment", "sha256"),
            _ref(plan, "data_sufficiency_amendment", "sha256"),
        ),
        ("dataset.dataset_id", _ref(committed, "dataset_id"), _ref(plan, "dataset_id")),
    ]:
        if expected is None or actual is None:
            raise ManifestError(f"dataset_plan.lock.json missing {section}")
        if expected != actual:
            raise ManifestError(
                f"dataset_plan.lock.json {section} mismatch: expected {expected}, got {actual}"
            )

    # Verify the split date ranges match the committed plan.
    committed_dataset = committed.get("dataset", {})
    plan_dataset = plan.get("dataset", {})
    for split in ("development", "validation", "holdout"):
        for bound in ("start", "end"):
            key = f"dataset.{split}.{bound}"
            expected = _ref(committed_dataset, split, bound)
            actual = _ref(plan_dataset, split, bound)
            if expected != actual:
                raise ManifestError(
                    f"dataset_plan.lock.json {key} mismatch: expected {expected}, got {actual}"
                )

    return sha256_of_file(p)


def _key(symbol: str, effective_month: str) -> tuple[str, str]:
    return (symbol, effective_month)


def _as_bool_or_none(value: Any) -> bool | None:
    if pd.isna(value) or value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _as_str(value: Any) -> str:
    return "" if pd.isna(value) or value is None else str(value)


def verify_dataset_bundle(
    dataset_root: Path,
    *,
    expected_count: int | None = 756,
    ohlcv_subdir: str = "ohlcv",
    universe_subdir: str = "universe",
) -> VerifiedDataset:
    """Cross-check manifest.lock.json, ohlcv_manifest.csv, data_quality.csv, and universe_manifest.csv.

    Raises ManifestError on any identity, hash, path, split, or set-equality mismatch.
    """
    root = Path(dataset_root).expanduser().resolve()

    manifest_path = root / "manifest.lock.json"
    ohlcv_manifest_path = root / ohlcv_subdir / "ohlcv_manifest.csv"
    data_quality_path = root / ohlcv_subdir / "data_quality.csv"
    universe_path = root / universe_subdir / "universe_manifest.csv"

    for p in [ohlcv_manifest_path, data_quality_path, universe_path]:
        if not p.is_file():
            raise ManifestError(f"required dataset file not found: {p}")

    if manifest_path.is_file():
        manifest_lock = _read_json(manifest_path)
        manifest_records = manifest_lock.get("files", [])
        if not isinstance(manifest_records, list):
            raise ManifestError("manifest.lock.json 'files' must be a list")
    else:
        # The canonical ohlcv_manifest.csv serves as the lock file when no separate
        # manifest.lock.json is present in the dataset snapshot.
        manifest_path = ohlcv_manifest_path
        manifest_df = load_ohlcv_manifest(manifest_path)
        manifest_records = manifest_df.to_dict("records")

    ohlcv_df = load_ohlcv_manifest(ohlcv_manifest_path)
    dq_df = load_data_quality(data_quality_path)
    universe_df = load_universe_manifest(universe_path)

    def _keys(df: pd.DataFrame, symbol_col: str = "symbol", month_col: str = "effective_month") -> set[tuple[str, str]]:
        return {(_as_str(r[symbol_col]), _as_str(r[month_col])) for _, r in df.iterrows()}

    def _assert_no_duplicate_keys(df: pd.DataFrame, name: str, symbol_col: str, month_col: str) -> None:
        keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for _, r in df.iterrows():
            key = (_as_str(r[symbol_col]), _as_str(r[month_col]))
            if key in seen:
                raise ManifestError(f"duplicate {name} row for {key}")
            seen.add(key)
            keys.append(key)

    _assert_no_duplicate_keys(ohlcv_df, "ohlcv_manifest", "symbol", "effective_month")
    _assert_no_duplicate_keys(dq_df, "data_quality", "symbol", "effective_month")
    _assert_no_duplicate_keys(universe_df, "universe_manifest", "ticker", "effective_month")

    lock_keys = set()
    lock_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    lock_ids: list[tuple[str, str]] = []
    for rec in manifest_records:
        symbol = _as_str(rec.get("symbol"))
        month = _as_str(rec.get("effective_month"))
        key = _key(symbol, month)
        if key in lock_keys:
            raise ManifestError(f"duplicate manifest.lock.json record for {symbol}/{month}")
        lock_keys.add(key)
        lock_by_key[key] = rec
        lock_ids.append(key)

    ohlcv_keys = _keys(ohlcv_df)
    dq_keys = _keys(dq_df)
    universe_keys = _keys(universe_df, symbol_col="ticker")

    if not (lock_keys == ohlcv_keys == dq_keys == universe_keys):
        missing_lock = (ohlcv_keys | dq_keys | universe_keys) - lock_keys
        missing_ohlcv = lock_keys - ohlcv_keys
        missing_dq = lock_keys - dq_keys
        missing_universe = lock_keys - universe_keys
        raise ManifestError(
            f"symbol-month identity set mismatch: lock={len(lock_keys)} ohlcv={len(ohlcv_keys)} "
            f"dq={len(dq_keys)} universe={len(universe_keys)}; "
            f"missing_lock={sorted(missing_lock)} missing_ohlcv={sorted(missing_ohlcv)} "
            f"missing_dq={sorted(missing_dq)} missing_universe={sorted(missing_universe)}"
        )

    if expected_count is not None and len(lock_keys) != expected_count:
        raise ManifestError(
            f"expected {expected_count} symbol-months, found {len(lock_keys)}"
        )

    # Row-level consistency and path safety.
    errors: list[str] = []
    ohlcv_by_key = {
        _key(_as_str(r["symbol"]), _as_str(r["effective_month"])): r
        for _, r in ohlcv_df.iterrows()
    }
    dq_by_key = {
        _key(_as_str(r["symbol"]), _as_str(r["effective_month"])): r
        for _, r in dq_df.iterrows()
    }
    universe_by_key = {
        _key(_as_str(r["ticker"]), _as_str(r["effective_month"])): r
        for _, r in universe_df.iterrows()
    }

    symbol_months: list[SymbolMonth] = []
    for key in lock_ids:
        symbol, month = key
        lock_rec = lock_by_key[key]
        ohlcv_row = ohlcv_by_key[key]
        dq_row = dq_by_key[key]
        universe_row = universe_by_key[key]

        lock_rel = _as_str(lock_rec.get("relative_path"))
        ohlcv_rel = _as_str(ohlcv_row.get("relative_path"))
        dq_rel = _as_str(dq_row.get("relative_path"))
        if not (lock_rel == ohlcv_rel == dq_rel):
            errors.append(
                f"{symbol}/{month}: relative_path mismatch lock={lock_rel} ohlcv={ohlcv_rel} dq={dq_rel}"
            )
            continue

        lock_sha = _as_str(lock_rec.get("sha256"))
        ohlcv_sha = _as_str(ohlcv_row.get("sha256"))
        dq_sha = _as_str(dq_row.get("file_sha256"))
        if not (lock_sha and lock_sha == ohlcv_sha == dq_sha):
            errors.append(
                f"{symbol}/{month}: sha256 mismatch lock={lock_sha} ohlcv={ohlcv_sha} dq={dq_sha}"
            )
            continue

        requested = _as_str(dq_row.get("requested_symbol"))
        returned = _as_str(dq_row.get("returned_symbol"))
        if requested != symbol or returned != symbol:
            errors.append(
                f"{symbol}/{month}: symbol identity mismatch requested={requested} returned={returned}"
            )
            continue

        if _as_bool_or_none(dq_row.get("symbol_mismatch")) is True:
            errors.append(f"{symbol}/{month}: symbol_mismatch=True")
            continue

        if _as_bool_or_none(dq_row.get("pagination_complete")) is False:
            errors.append(f"{symbol}/{month}: pagination_complete=False")
            continue

        if _as_bool_or_none(dq_row.get("file_sha256_match")) is False:
            errors.append(f"{symbol}/{month}: file_sha256_match=False")
            continue

        try:
            _safe_relative_path(root, lock_rel, ohlcv_subdir)
        except ManifestError as e:
            errors.append(f"{symbol}/{month}: {e}")
            continue

        dq_split = _as_str(dq_row.get("split"))
        expected_split = split_for_effective_month(month)
        if dq_split != expected_split:
            errors.append(
                f"{symbol}/{month}: split mismatch dq={dq_split!r} expected={expected_split!r}"
            )
            continue

        included = _as_bool_or_none(universe_row.get("included"))
        if included is not True:
            errors.append(f"{symbol}/{month}: universe included={included}")
            continue

        symbol_months.append(
            SymbolMonth(
                manifest_id=_as_str(lock_rec.get("manifest_id") or f"{month}/{symbol}"),
                symbol=symbol,
                effective_month=month,
                split=dq_split,
                relative_path=lock_rel,
                sha256=lock_sha,
                file_size_bytes=int(lock_rec.get("file_size_bytes", 0) or 0),
            )
        )

    if errors:
        raise ManifestError("dataset bundle verification failed: " + "; ".join(errors))

    by_split: dict[str, list[SymbolMonth]] = {}
    for sm in symbol_months:
        by_split.setdefault(sm.split, []).append(sm)

    return VerifiedDataset(
        symbol_months=symbol_months,
        by_split=by_split,
        manifest_sha256=sha256_of_file(manifest_path),
        ohlcv_manifest=ohlcv_df,
        data_quality=dq_df,
        universe_manifest=universe_df,
    )


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
