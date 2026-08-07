"""Deterministic malformed-row exclusion for research snapshot ingestion.

This module is research-only. It does not change production behavior, provider
contracts, or the strict ``canonicalize_bars`` validator. When an ingestion
policy is supplied, rows that violate the configured hard OHLCV invariants are
dropped and audited; the cleaned DataFrame is then passed to
``canonicalize_bars`` for final strict validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.score_validation.models import ValidationError

_CANONICAL_COLUMNS = ["open", "high", "low", "close", "volume"]

# Fixed reason-code order from the SHORT-001 v2 ingestion policy.
_REASON_CODES = [
    "missing_or_non_numeric_open",
    "missing_or_non_numeric_high",
    "missing_or_non_numeric_low",
    "missing_or_non_numeric_close",
    "missing_or_non_numeric_volume",
    "non_finite_open",
    "non_finite_high",
    "non_finite_low",
    "non_finite_close",
    "non_finite_volume",
    "nonpositive_open",
    "nonpositive_high",
    "nonpositive_low",
    "nonpositive_close",
    "negative_volume",
    "high_below_low",
    "high_below_open",
    "high_below_close",
    "low_above_open",
    "low_above_close",
]
_REASON_ORDER = {code: idx for idx, code in enumerate(_REASON_CODES)}


@dataclass(frozen=True)
class IngestionPolicy:
    """Immutable, validated SHORT-001 v2 ingestion policy."""

    schema_version: int
    policy_id: str
    action: str
    structural_failures_remain_fatal: bool
    repair_values: bool
    require_all_symbols: bool
    required_symbol_count: int
    max_total_invalid_rows: int
    max_total_invalid_rate_pct: float
    max_invalid_rows_per_ticker: int
    max_invalid_rate_pct_per_ticker: float
    max_consecutive_invalid_rows_per_ticker: int
    allow_first_or_last_row_removal: bool
    minimum_pre_development_warmup_bars: int
    hard_row_invariants: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValidationError(f"Unsupported ingestion policy schema_version: {self.schema_version}")
        if not self.policy_id:
            raise ValidationError("policy_id must be a nonempty string")
        if self.action != "drop":
            raise ValidationError(f"Unsupported ingestion action: {self.action!r}; expected 'drop'")
        if self.repair_values:
            raise ValidationError("repair_values must be false for this policy")
        if not self.structural_failures_remain_fatal:
            raise ValidationError("structural_failures_remain_fatal must be true for this policy")
        if self.required_symbol_count < 1:
            raise ValidationError(f"required_symbol_count must be positive; got {self.required_symbol_count}")
        if self.max_total_invalid_rows < 0:
            raise ValidationError(f"max_total_invalid_rows must be nonnegative; got {self.max_total_invalid_rows}")
        if self.max_total_invalid_rate_pct < 0:
            raise ValidationError(f"max_total_invalid_rate_pct must be nonnegative; got {self.max_total_invalid_rate_pct}")
        if self.max_invalid_rows_per_ticker < 0:
            raise ValidationError(f"max_invalid_rows_per_ticker must be nonnegative; got {self.max_invalid_rows_per_ticker}")
        if self.max_invalid_rate_pct_per_ticker < 0:
            raise ValidationError(f"max_invalid_rate_pct_per_ticker must be nonnegative; got {self.max_invalid_rate_pct_per_ticker}")
        if self.max_consecutive_invalid_rows_per_ticker < 1:
            raise ValidationError(f"max_consecutive_invalid_rows_per_ticker must be >= 1; got {self.max_consecutive_invalid_rows_per_ticker}")
        if self.minimum_pre_development_warmup_bars < 0:
            raise ValidationError(f"minimum_pre_development_warmup_bars must be nonnegative; got {self.minimum_pre_development_warmup_bars}")
        object.__setattr__(self, "hard_row_invariants", tuple(self.hard_row_invariants))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hard_row_invariants"] = list(self.hard_row_invariants)
        return d

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(frozen=True)
class TickerIngestionResult:
    """Per-ticker cleaning outcome."""

    ticker: str
    data_source: str
    raw_rows: int
    cleaned_rows: int
    invalid_rows_removed: int
    invalid_row_rate_pct: float
    raw_start: datetime | None
    raw_end: datetime | None
    cleaned_start: datetime | None
    cleaned_end: datetime | None
    max_consecutive_invalid_rows: int
    raw_normalized_sha256: str
    cleaned_csv_sha256: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SnapshotAudit:
    """Aggregated snapshot-level audit summary."""

    schema_version: int
    policy_id: str
    ingestion_spec_sha256: str
    context_spec_sha256: str | None
    provider: str
    requested_start: str
    requested_end: str
    required_symbol_count: int
    retrieved_symbol_count: int
    raw_total_rows: int
    cleaned_total_rows: int
    invalid_rows_removed: int
    total_invalid_row_rate_pct: float
    affected_symbols: int
    max_invalid_rows_per_symbol: int
    max_invalid_row_rate_pct_per_symbol: float
    max_consecutive_invalid_rows: int
    threshold_result: str
    price_repair: bool
    all_symbols_retained: bool
    removed_reason_summary: dict[str, int]
    manifest_sha256: str | None = None
    sidecar_sha256: dict[str, str] = field(default_factory=dict)


def load_ingestion_policy(path: str | Path) -> tuple[IngestionPolicy, bytes]:
    """Load and validate an ingestion-policy JSON file."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValidationError(f"Ingestion policy not found: {path}")
    raw_bytes = path.read_bytes()
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Ingestion policy is not valid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ValidationError("Ingestion policy must be a JSON object")
    policy = _build_policy(data)
    return policy, raw_bytes


def _build_policy(data: Mapping[str, Any]) -> IngestionPolicy:
    """Build a validated IngestionPolicy from a JSON object, rejecting unknown fields."""
    allowed = {
        "schema_version",
        "policy_id",
        "action",
        "structural_failures_remain_fatal",
        "repair_values",
        "require_all_symbols",
        "required_symbol_count",
        "max_total_invalid_rows",
        "max_total_invalid_rate_pct",
        "max_invalid_rows_per_ticker",
        "max_invalid_rate_pct_per_ticker",
        "max_consecutive_invalid_rows_per_ticker",
        "allow_first_or_last_row_removal",
        "minimum_pre_development_warmup_bars",
        "hard_row_invariants",
    }
    unknown = set(data.keys()) - allowed
    if unknown:
        raise ValidationError(f"Ingestion policy contains unknown keys: {sorted(unknown)}")

    hard_invariants = data.get("hard_row_invariants", [])
    if not isinstance(hard_invariants, list) or not all(isinstance(i, str) for i in hard_invariants):
        raise ValidationError("hard_row_invariants must be a list of strings")

    return IngestionPolicy(
        schema_version=_require_int(data.get("schema_version"), "schema_version", min_value=1),
        policy_id=_require_str(data.get("policy_id"), "policy_id"),
        action=_require_str(data.get("action"), "action"),
        structural_failures_remain_fatal=_require_bool(data.get("structural_failures_remain_fatal"), "structural_failures_remain_fatal"),
        repair_values=_require_bool(data.get("repair_values"), "repair_values"),
        require_all_symbols=_require_bool(data.get("require_all_symbols"), "require_all_symbols"),
        required_symbol_count=_require_int(data.get("required_symbol_count"), "required_symbol_count", min_value=1),
        max_total_invalid_rows=_require_int(data.get("max_total_invalid_rows"), "max_total_invalid_rows", min_value=0),
        max_total_invalid_rate_pct=_require_float(data.get("max_total_invalid_rate_pct"), "max_total_invalid_rate_pct", min_value=0),
        max_invalid_rows_per_ticker=_require_int(data.get("max_invalid_rows_per_ticker"), "max_invalid_rows_per_ticker", min_value=0),
        max_invalid_rate_pct_per_ticker=_require_float(data.get("max_invalid_rate_pct_per_ticker"), "max_invalid_rate_pct_per_ticker", min_value=0),
        max_consecutive_invalid_rows_per_ticker=_require_int(data.get("max_consecutive_invalid_rows_per_ticker"), "max_consecutive_invalid_rows_per_ticker", min_value=1),
        allow_first_or_last_row_removal=_require_bool(data.get("allow_first_or_last_row_removal"), "allow_first_or_last_row_removal"),
        minimum_pre_development_warmup_bars=_require_int(data.get("minimum_pre_development_warmup_bars"), "minimum_pre_development_warmup_bars", min_value=0),
        hard_row_invariants=tuple(hard_invariants),
    )


def _require_int(value: Any, name: str, min_value: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer; got {value!r}")
    if min_value is not None and value < min_value:
        raise ValidationError(f"{name} must be >= {min_value}; got {value}")
    return value


def _require_float(value: Any, name: str, min_value: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number; got {value!r}")
    f = float(value)
    if not math.isfinite(f):
        raise ValidationError(f"{name} must be finite; got {value}")
    if min_value is not None and f < min_value:
        raise ValidationError(f"{name} must be >= {min_value}; got {f}")
    return f


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{name} must be a nonempty string; got {value!r}")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{name} must be a boolean; got {value!r}")
    return value


def clean_ticker(
    df: pd.DataFrame,
    ticker: str,
    policy: IngestionPolicy,
    start: date,
    end: date,
    development_start: date,
    data_source: str,
) -> tuple[pd.DataFrame, pd.DataFrame, TickerIngestionResult]:
    """Return (cleaned_df, removed_rows_df, audit_result) for one ticker.

    Raises ``ValidationError`` when a structural invariant or policy threshold is
    violated (no rows are repaired or clamped).
    """
    if df.empty:
        raise ValidationError(f"{ticker}: fetched DataFrame is empty")

    # Keep the provider-returned values for the audit trail.
    missing_cols = [c for c in _CANONICAL_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValidationError(f"{ticker}: missing required columns {missing_cols}")
    raw_df = df[_CANONICAL_COLUMNS].copy()

    # Timestamp index must be parseable, timezone-aware, monotonic, and unique.
    if not isinstance(raw_df.index, pd.DatetimeIndex):
        try:
            raw_df.index = pd.to_datetime(raw_df.index)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(f"{ticker}: index cannot be parsed as datetime: {exc}") from None
    if raw_df.index.tz is None:
        raise ValidationError(f"{ticker}: DatetimeIndex is naive; timezone-aware UTC index required")
    raw_df.index = raw_df.index.tz_convert("UTC")
    raw_df.index.name = "datetime"

    if raw_df.index.isna().any():
        raise ValidationError(f"{ticker}: DatetimeIndex contains NaT timestamps")
    if not raw_df.index.is_unique:
        raise ValidationError(f"{ticker}: DatetimeIndex contains duplicate timestamps")
    if not raw_df.index.is_monotonic_increasing:
        raise ValidationError(f"{ticker}: DatetimeIndex is not monotonic increasing")

    # Restrict to requested date contract and fail if any provider row is outside it.
    start_dt = pd.Timestamp(start, tz="UTC")
    end_dt = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    in_range = (raw_df.index >= start_dt) & (raw_df.index <= end_dt)
    if not in_range.all():
        out_of_range = (~in_range).sum()
        raise ValidationError(f"{ticker}: {out_of_range} row(s) outside requested date range {start} to {end}")

    # Convert to numeric for validation, coercing provider anomalies to NaN.
    numeric_df = raw_df.copy()
    for col in _CANONICAL_COLUMNS:
        numeric_df[col] = pd.to_numeric(numeric_df[col], errors="coerce")

    # Compute the raw normalized hash before any row removal.
    raw_hash = _hash_dataframe(numeric_df)

    # Determine invalid rows and their deterministic reason codes.
    invalid_mask, reason_series = _row_invalidity(numeric_df)
    invalid_rows_removed = int(invalid_mask.sum())
    raw_rows = len(numeric_df)

    warnings: list[str] = []
    if invalid_rows_removed:
        warnings.append(f"{invalid_rows_removed} hard-invalid OHLCV rows will be dropped")

    # Consecutive invalid-row check.
    max_consecutive = _max_consecutive(invalid_mask)
    if max_consecutive > policy.max_consecutive_invalid_rows_per_ticker:
        raise ValidationError(
            f"{ticker}: max consecutive invalid rows is {max_consecutive}; "
            f"policy limit is {policy.max_consecutive_invalid_rows_per_ticker}"
        )

    # First/last row removal prohibition.
    if invalid_rows_removed and not policy.allow_first_or_last_row_removal and (invalid_mask.iloc[0] or invalid_mask.iloc[-1]):
        raise ValidationError(f"{ticker}: invalid first or last row cannot be removed under this policy")

    # Per-ticker count and rate thresholds.
    if invalid_rows_removed > policy.max_invalid_rows_per_ticker:
        raise ValidationError(
            f"{ticker}: {invalid_rows_removed} invalid rows exceeds per-ticker limit {policy.max_invalid_rows_per_ticker}"
        )
    invalid_rate_pct = (invalid_rows_removed / raw_rows * 100.0) if raw_rows else 0.0
    if invalid_rate_pct > policy.max_invalid_rate_pct_per_ticker:
        raise ValidationError(
            f"{ticker}: invalid row rate {invalid_rate_pct:.4f}% exceeds per-ticker limit {policy.max_invalid_rate_pct_per_ticker}%"
        )

    # Remove invalid rows from the numeric (calculation) frame; preserve original
    # provider values for the removed-row audit.
    cleaned_df = numeric_df[~invalid_mask].copy()
    removed_df = raw_df[invalid_mask].copy()
    removed_df["reason_codes"] = reason_series[invalid_mask]
    removed_df["ticker"] = ticker

    if cleaned_df.empty:
        raise ValidationError(f"{ticker}: no usable rows remain after invalid-row removal")

    # Pre-development warmup minimum.
    development_start_dt = pd.Timestamp(development_start, tz="UTC")
    pre_development_bars = int((cleaned_df.index < development_start_dt).sum())
    if pre_development_bars < policy.minimum_pre_development_warmup_bars:
        raise ValidationError(
            f"{ticker}: only {pre_development_bars} pre-development bars; "
            f"policy requires {policy.minimum_pre_development_warmup_bars}"
        )

    # Final cleaned CSV hash (must match the manifest entry written later).
    cleaned_hash = _hash_dataframe(cleaned_df)

    result = TickerIngestionResult(
        ticker=ticker,
        data_source=data_source,
        raw_rows=raw_rows,
        cleaned_rows=len(cleaned_df),
        invalid_rows_removed=invalid_rows_removed,
        invalid_row_rate_pct=round(invalid_rate_pct, 6),
        raw_start=raw_df.index[0].to_pydatetime(),
        raw_end=raw_df.index[-1].to_pydatetime(),
        cleaned_start=cleaned_df.index[0].to_pydatetime(),
        cleaned_end=cleaned_df.index[-1].to_pydatetime(),
        max_consecutive_invalid_rows=max_consecutive,
        raw_normalized_sha256=raw_hash,
        cleaned_csv_sha256=cleaned_hash,
        warnings=warnings,
    )
    return cleaned_df, removed_df, result


def _row_invalidity(numeric_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (boolean invalid mask, Series of comma-sorted reason-code strings)."""
    reasons: list[list[str]] = []
    for _, row in numeric_df.iterrows():
        codes: list[str] = []
        # Per-field checks.
        for col in _CANONICAL_COLUMNS:
            value = row[col]
            if pd.isna(value):
                codes.append(f"missing_or_non_numeric_{col}")
            elif not math.isfinite(float(value)):
                codes.append(f"non_finite_{col}")
            elif col != "volume" and value <= 0:
                codes.append(f"nonpositive_{col}")
            elif col == "volume" and value < 0:
                codes.append("negative_volume")
        # Cross-field checks (only when both sides are finite and non-missing).
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        if all(not pd.isna(x) and math.isfinite(float(x)) for x in (h, l)) and h < l:
            codes.append("high_below_low")
        if all(not pd.isna(x) and math.isfinite(float(x)) for x in (h, o)) and h < o:
            codes.append("high_below_open")
        if all(not pd.isna(x) and math.isfinite(float(x)) for x in (h, c)) and h < c:
            codes.append("high_below_close")
        if all(not pd.isna(x) and math.isfinite(float(x)) for x in (l, o)) and l > o:
            codes.append("low_above_open")
        if all(not pd.isna(x) and math.isfinite(float(x)) for x in (l, c)) and l > c:
            codes.append("low_above_close")
        # Deterministic ordering.
        codes = sorted(set(codes), key=lambda c: _REASON_ORDER[c])
        reasons.append(codes)

    invalid_mask = pd.Series([len(r) > 0 for r in reasons], index=numeric_df.index)
    reason_series = pd.Series([",".join(r) for r in reasons], index=numeric_df.index)
    return invalid_mask, reason_series


def _max_consecutive(mask: pd.Series) -> int:
    """Return the maximum run length of True values in ``mask``."""
    if not mask.any():
        return 0
    groups = (mask != mask.shift()).cumsum()
    return int(mask.groupby(groups).sum().max())


def _hash_dataframe(df: pd.DataFrame) -> str:
    """Return a deterministic SHA-256 of a DataFrame serialized as CSV."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        df.to_csv(tmp_path, index=True, date_format="%Y-%m-%dT%H:%M:%S%z")
        return _sha256_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_snapshot_audit(
    results: list[TickerIngestionResult],
    policy: IngestionPolicy,
    provider: str,
    start: date,
    end: date,
    ingestion_spec_sha256: str,
    context_spec_sha256: str | None,
    manifest_sha256: str | None = None,
    sidecar_sha256: dict[str, str] | None = None,
) -> SnapshotAudit:
    """Validate global policy thresholds and return an aggregated audit."""
    if len(results) != policy.required_symbol_count:
        raise ValidationError(
            f"Expected {policy.required_symbol_count} symbols; got {len(results)}"
        )

    raw_total = sum(r.raw_rows for r in results)
    cleaned_total = sum(r.cleaned_rows for r in results)
    invalid_total = sum(r.invalid_rows_removed for r in results)
    rate_pct = (invalid_total / raw_total * 100.0) if raw_total else 0.0

    if invalid_total > policy.max_total_invalid_rows:
        raise ValidationError(
            f"Total invalid rows {invalid_total} exceeds policy limit {policy.max_total_invalid_rows}"
        )
    if rate_pct > policy.max_total_invalid_rate_pct:
        raise ValidationError(
            f"Total invalid row rate {rate_pct:.4f}% exceeds policy limit {policy.max_total_invalid_rate_pct}%"
        )

    affected = sum(1 for r in results if r.invalid_rows_removed > 0)
    max_per_symbol = max(r.invalid_rows_removed for r in results)
    max_rate_per_symbol = max(r.invalid_row_rate_pct for r in results)
    max_consecutive = max(r.max_consecutive_invalid_rows for r in results)

    reason_summary: dict[str, int] = {}
    # Reason summaries are computed from the removed-row DataFrame when sidecars are written.
    # The audit stores the summary computed later; pass an empty dict here.

    threshold_result = "passed"
    if provider != "schwab":
        threshold_result = "failed: provider must be schwab"
        raise ValidationError(f"Provider provenance must be 'schwab'; got {provider!r}")

    return SnapshotAudit(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        ingestion_spec_sha256=ingestion_spec_sha256,
        context_spec_sha256=context_spec_sha256,
        provider=provider,
        requested_start=start.isoformat(),
        requested_end=end.isoformat(),
        required_symbol_count=policy.required_symbol_count,
        retrieved_symbol_count=len(results),
        raw_total_rows=raw_total,
        cleaned_total_rows=cleaned_total,
        invalid_rows_removed=invalid_total,
        total_invalid_row_rate_pct=round(rate_pct, 6),
        affected_symbols=affected,
        max_invalid_rows_per_symbol=max_per_symbol,
        max_invalid_row_rate_pct_per_symbol=round(max_rate_per_symbol, 6),
        max_consecutive_invalid_rows=max_consecutive,
        threshold_result=threshold_result,
        price_repair=False,
        all_symbols_retained=True,
        removed_reason_summary=reason_summary,
        manifest_sha256=manifest_sha256,
        sidecar_sha256=sidecar_sha256 or {},
    )


def update_audit_reason_summary(audit: SnapshotAudit, invalid_rows_df: pd.DataFrame) -> SnapshotAudit:
    """Return a new audit with the reason-code summary populated."""
    summary: dict[str, int] = {}
    if not invalid_rows_df.empty and "reason_codes" in invalid_rows_df.columns:
        for codes in invalid_rows_df["reason_codes"]:
            for code in str(codes).split(","):
                if code:
                    summary[code] = summary.get(code, 0) + 1
    return SnapshotAudit(**{**asdict(audit), "removed_reason_summary": summary})


def result_to_quality_row(result: TickerIngestionResult, threshold_status: str) -> dict[str, Any]:
    """Map a TickerIngestionResult to a snapshot_data_quality.csv row."""
    return {
        "ticker": result.ticker,
        "data_source": result.data_source,
        "raw_rows": result.raw_rows,
        "cleaned_rows": result.cleaned_rows,
        "invalid_rows_removed": result.invalid_rows_removed,
        "invalid_row_rate_pct": result.invalid_row_rate_pct,
        "raw_start": result.raw_start.isoformat() if result.raw_start else None,
        "raw_end": result.raw_end.isoformat() if result.raw_end else None,
        "cleaned_start": result.cleaned_start.isoformat() if result.cleaned_start else None,
        "cleaned_end": result.cleaned_end.isoformat() if result.cleaned_end else None,
        "max_consecutive_invalid_rows": result.max_consecutive_invalid_rows,
        "raw_normalized_sha256": result.raw_normalized_sha256,
        "cleaned_csv_sha256": result.cleaned_csv_sha256,
        "threshold_status": threshold_status,
        "warnings": "; ".join(result.warnings) if result.warnings else "",
    }


def write_snapshot_data_quality(results: list[TickerIngestionResult], path: str | Path) -> None:
    """Write the per-symbol snapshot data-quality CSV."""
    path = Path(path)
    rows = [result_to_quality_row(r, "passed") for r in sorted(results, key=lambda r: r.ticker)]
    df = pd.DataFrame(rows)
    expected_cols = [
        "ticker",
        "data_source",
        "raw_rows",
        "cleaned_rows",
        "invalid_rows_removed",
        "invalid_row_rate_pct",
        "raw_start",
        "raw_end",
        "cleaned_start",
        "cleaned_end",
        "max_consecutive_invalid_rows",
        "raw_normalized_sha256",
        "cleaned_csv_sha256",
        "threshold_status",
        "warnings",
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
    df = df[expected_cols]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_invalid_rows(invalid_rows_df: pd.DataFrame, path: str | Path) -> None:
    """Write the removed-row audit CSV, ordered by ticker and timestamp."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if invalid_rows_df.empty:
        invalid_rows_df = pd.DataFrame(
            columns=["ticker", "datetime", "open", "high", "low", "close", "volume", "reason_codes"]
        )
    else:
        # Preserve provider-returned values and order deterministically.
        invalid_rows_df = invalid_rows_df.reset_index()
        if "ticker" not in invalid_rows_df.columns:
            raise ValidationError("Invalid rows DataFrame must contain a 'ticker' column")
        invalid_rows_df = invalid_rows_df.sort_values(["ticker", "datetime"])
        cols = ["ticker", "datetime", "open", "high", "low", "close", "volume", "reason_codes"]
        for col in cols:
            if col not in invalid_rows_df.columns:
                invalid_rows_df[col] = None
        invalid_rows_df = invalid_rows_df[cols]
    invalid_rows_df.to_csv(path, index=False)


def write_snapshot_audit(audit: SnapshotAudit, path: str | Path) -> None:
    """Write the snapshot-level audit JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(audit)
    # datetime objects are already strings or None; ensure JSON-safe.
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def write_snapshot_checksums(snapshot_dir: str | Path, output_path: str | Path) -> None:
    """Write a checksums.sha256 file for the files in ``snapshot_dir``."""
    snapshot_dir = Path(snapshot_dir)
    output_path = Path(output_path)
    lines: list[str] = []
    for path in sorted(snapshot_dir.iterdir()):
        if path.is_file() and path.name != output_path.name:
            lines.append(f"{_sha256_file(path)}  {path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")


def verify_snapshot_sidecars(snapshot_dir: str | Path, expected_ingestion_sha256: str) -> dict[str, Any]:
    """Verify that a snapshot directory contains a locked, matching ingestion spec and checksums.

    Returns the parsed snapshot audit dictionary.
    """
    snapshot_dir = Path(snapshot_dir)
    ingestion_lock = snapshot_dir / "ingestion_spec.lock.json"
    if not ingestion_lock.is_file():
        raise ValidationError(f"Snapshot missing ingestion_spec.lock.json: {snapshot_dir}")
    actual_ingestion_sha = _sha256_file(ingestion_lock)
    if actual_ingestion_sha != expected_ingestion_sha256:
        raise ValidationError(
            f"Ingestion spec SHA-256 mismatch: expected {expected_ingestion_sha256}, got {actual_ingestion_sha}"
        )

    audit_path = snapshot_dir / "snapshot_audit.json"
    if not audit_path.is_file():
        raise ValidationError(f"Snapshot missing snapshot_audit.json: {snapshot_dir}")
    audit = json.loads(audit_path.read_text())

    checksums_path = snapshot_dir / "snapshot_checksums.sha256"
    if not checksums_path.is_file():
        raise ValidationError(f"Snapshot missing snapshot_checksums.sha256: {snapshot_dir}")

    # Verify listed checksums for all files except the checksums file itself.
    checksums = _parse_checksums_file(checksums_path)
    for filename, expected in checksums.items():
        file_path = snapshot_dir / filename
        if not file_path.is_file():
            raise ValidationError(f"Checksum entry missing on disk: {filename}")
        actual = _sha256_file(file_path)
        if actual != expected:
            raise ValidationError(f"Checksum mismatch for {filename}: expected {expected}, got {actual}")

    return audit


def _parse_checksums_file(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValidationError(f"Malformed checksum line: {line!r}")
        checksums[parts[1].strip()] = parts[0].strip()
    return checksums
