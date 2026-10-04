"""Dataset manifest contract, security bounds, and bounded Alpaca acquisition adapter."""
from __future__ import annotations

import calendar
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

from .calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from .models import (
    DataQualityReport,
    DaytradeSession,
    HoldoutAccessDeniedError,
    HoldoutAccessProof,
)
from .quality import audit_missing_ticker_session, audit_ticker_session
from .spec import DAYTRADE_002A_SPEC_SHA256, LOCKED_FROZEN_UNIVERSE, DaytradeSpec

LOCKED_PROVIDER = "alpaca"
LOCKED_FEED = "sip"
LOCKED_TIMEFRAME = "1Min"
LOCKED_ADJUSTMENT = "split"
LOCKED_CALENDAR = "XNYS"
LOCKED_TIMEZONE = "America/New_York"
MAX_RETRIES_PER_FAILED_PAGE = 1
MAX_PAGES_PER_CALENDAR_MONTH_CHUNK = 100

FORBIDDEN_KEY_PATTERNS = (
    "api_key",
    "secret_key",
    "apca-api",
    "authorization",
    "password",
    "bearer",
    "raw_body",
    "response_body",
    "error_body",
    "raw_response",
    "raw_error",
    "page_token",
    "next_page_token",
)

SAFE_KEY_ALLOWLIST = {
    "manifest_sha256",
    "spec_sha256",
    "preholdout_manifest_sha256",
    "validation_bundle_sha256",
    "evaluator_code_sha",
    "token_sequence_sha256",
    "source_files",
    "file_sha256",
    "token_hashes",
    "token_hash",
    "acquisition_provenance",
}


class DatasetSecurityError(ValueError):
    """Raised when dataset storage or manifest security constraints are breached."""


class DatasetPaginationLimitError(RuntimeError):
    """Raised when pagination exceeds the hard locked 100-page limit per month."""


def get_repo_root() -> Path:
    """Return the resolved TradeX repository root."""
    return Path(__file__).resolve().parents[3]


def validate_dataset_root(dataset_root: Path | str, repo_root: Path | None = None) -> Path:
    """Validate that dataset_root is outside the tracked repository/worktree.

    Fails closed if the path resolves inside the git worktree.
    """
    repo = (repo_root or get_repo_root()).resolve()
    target = Path(dataset_root).expanduser().resolve()

    is_inside = False
    try:
        target.relative_to(repo)
        is_inside = True
    except ValueError:
        is_inside = False

    if is_inside:
        raise DatasetSecurityError(
            f"Dataset root {target} is inside the tracked repository {repo}; "
            "raw/normalized OHLCV must reside outside the tracked repository."
        )

    return target


def sha256_of_file(path: Path) -> str:
    """Compute hex SHA-256 of file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_forbidden_key(k: str) -> None:
    k_lower = str(k).lower()
    if k in SAFE_KEY_ALLOWLIST or k_lower in SAFE_KEY_ALLOWLIST:
        return
    if "token" in k_lower and ("hash" in k_lower or "sequence" in k_lower):
        return
    for pattern in FORBIDDEN_KEY_PATTERNS:
        if pattern in k_lower:
            raise DatasetSecurityError(f"Prohibited key pattern '{pattern}' found in key '{k}'")


def _check_forbidden_val(v: Any) -> None:
    if isinstance(v, str):
        v_lower = v.strip().lower()
        if v_lower.startswith(("bearer ", "basic ")):
            raise DatasetSecurityError("Prohibited authorization token value found in manifest")
        if v_lower.startswith(("token ", "secret ")):
            raise DatasetSecurityError("Prohibited credential value found in manifest")


def sanitize_manifest_data(data: Any) -> Any:
    """Recursively validate that no API keys, secrets, tokens, or raw bodies exist.

    Fails closed: raises DatasetSecurityError if any forbidden pattern is detected.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            _check_forbidden_key(str(k))
            sanitize_manifest_data(v)
    elif isinstance(data, (list, tuple)):
        for item in data:
            sanitize_manifest_data(item)
    else:
        _check_forbidden_val(data)
    return data


def write_normalized_bars_csv(path: Path, df: pd.DataFrame) -> None:
    """Write normalized bars to CSV following the locked DAYTRADE schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["bar_start", "open", "high", "low", "close", "volume"]
    export_df = df.copy()

    # Handle DatetimeIndex or datetime/bar_start column
    if "bar_start" not in export_df.columns:
        if isinstance(export_df.index, pd.DatetimeIndex) or export_df.index.name in ("datetime", "bar_start"):
            export_df = export_df.reset_index()
            if "datetime" in export_df.columns:
                export_df = export_df.rename(columns={"datetime": "bar_start"})
            elif "index" in export_df.columns:
                export_df = export_df.rename(columns={"index": "bar_start"})
        elif "datetime" in export_df.columns:
            export_df["bar_start"] = export_df["datetime"]
        elif "timestamp" in export_df.columns:
            export_df["bar_start"] = export_df["timestamp"]
        else:
            raise DatasetSecurityError(
                f"Cannot extract 'bar_start' timestamp from DataFrame columns {list(export_df.columns)}"
            )

    def _to_iso_utc(ts: Any) -> str:
        if isinstance(ts, (datetime, pd.Timestamp)):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            else:
                ts = ts.astimezone(UTC)
            return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(ts, str):
            ts_dt = pd.to_datetime(ts, utc=True)
            return ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            ts_dt = pd.to_datetime(ts, utc=True)
            return ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if not export_df.empty:
        export_df["bar_start"] = export_df["bar_start"].apply(_to_iso_utc)
        export_df = export_df.sort_values(by="bar_start", ascending=True)
        for c in ["open", "high", "low", "close", "volume"]:
            if c not in export_df.columns:
                export_df[c] = pd.NA
        export_df = export_df[cols]
    else:
        export_df = pd.DataFrame(columns=cols)

    export_df[cols].to_csv(path, index=False, columns=cols, encoding="utf-8")


def read_normalized_bars_csv(path: Path) -> tuple[pd.DataFrame, int]:
    """Read normalized bars CSV and return (df, malformed_unassigned_rows_count).

    Safely parses timestamps. Any completely unparseable timestamp rows are dropped
    and returned in malformed_unassigned_rows_count without fabricating session attribution.
    """
    if not path.is_file():
        raise DatasetSecurityError(f"Bars file not found: {path}")
    df = pd.read_csv(path, encoding="utf-8")
    expected = ["bar_start", "open", "high", "low", "close", "volume"]
    if list(df.columns) != expected:
        raise DatasetSecurityError(
            f"CSV columns in {path} mismatch locked schema: expected {expected}, got {list(df.columns)}"
        )
    # Parse bar_start safely with errors='coerce'
    parsed_ts = pd.to_datetime(df["bar_start"], utc=True, errors="coerce")
    malformed_mask = parsed_ts.isna()
    malformed_count = int(malformed_mask.sum())
    if malformed_count > 0:
        df = df.loc[~malformed_mask].copy()
        parsed_ts = parsed_ts.loc[~malformed_mask]
    df["dt_parsed"] = parsed_ts
    return df, malformed_count


@dataclass
class DaytradeDatasetManifest:
    """Cryptographic manifest documenting acquired partition data and provenance."""

    task_id: str = "DAYTRADE-002A"
    spec_sha256: str = DAYTRADE_002A_SPEC_SHA256
    partition: str = "preholdout"  # 'preholdout' or 'holdout'
    provider: str = LOCKED_PROVIDER
    feed: str = LOCKED_FEED
    timeframe: str = LOCKED_TIMEFRAME
    adjustment: str = LOCKED_ADJUSTMENT
    calendar: str = LOCKED_CALENDAR
    timezone: str = LOCKED_TIMEZONE
    universe: tuple[str, ...] = LOCKED_FROZEN_UNIVERSE
    start_date: str = "2025-12-31"
    end_date: str = "2026-06-30"
    source_files: dict[str, str] = field(default_factory=dict)  # "bars/{ticker}.csv" -> sha256
    manifest_sha256: str = ""
    acquisition_provenance: dict[str, Any] = field(default_factory=dict)
    preholdout_manifest_sha256: str | None = None
    validation_bundle_sha256: str | None = None
    evaluator_code_sha: str | None = None

    def compute_sha256(self) -> str:
        """Compute deterministic manifest SHA-256 over all fields except manifest_sha256."""
        d = asdict(self)
        d["universe"] = list(self.universe)
        d.pop("manifest_sha256", None)
        sanitized = sanitize_manifest_data(d)
        serialized = json.dumps(sanitized, sort_keys=True, indent=2)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to sanitized dictionary and attach internal SHA-256."""
        d = asdict(self)
        d["universe"] = list(self.universe)
        d.pop("manifest_sha256", None)
        sanitized = sanitize_manifest_data(d)
        serialized = json.dumps(sanitized, sort_keys=True, indent=2)
        h = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        sanitized["manifest_sha256"] = h
        return sanitized

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaytradeDatasetManifest:
        """Construct manifest from dictionary, strictly validating its internal SHA-256."""
        sanitized = sanitize_manifest_data(dict(data))
        m_sha = sanitized.get("manifest_sha256", "")
        copy_d = dict(sanitized)
        copy_d.pop("manifest_sha256", None)
        computed = hashlib.sha256(json.dumps(copy_d, sort_keys=True, indent=2).encode("utf-8")).hexdigest()
        if m_sha and m_sha != computed:
            raise DatasetSecurityError(
                f"Manifest SHA-256 mismatch: recorded {m_sha}, computed {computed}"
            )
        copy_d["manifest_sha256"] = computed
        copy_d["universe"] = tuple(copy_d.get("universe", []))
        return cls(**copy_d)

    def validate_against_spec(self, spec: DaytradeSpec) -> None:
        """Strictly validate manifest properties against the locked DaytradeSpec."""
        if self.task_id not in ("DAYTRADE-002A", "DAYTRADE-002B"):
            raise DatasetSecurityError(
                f"Manifest task_id '{self.task_id}' invalid: must be 'DAYTRADE-002A' or 'DAYTRADE-002B'."
            )
        if self.spec_sha256 != spec.sha256:
            raise DatasetSecurityError(
                f"Manifest spec_sha256 mismatch: expected {spec.sha256}, got {self.spec_sha256}"
            )
        if self.provider != LOCKED_PROVIDER:
            raise DatasetSecurityError(
                f"Manifest provider '{self.provider}' mismatch: must be '{LOCKED_PROVIDER}'."
            )
        if self.feed != LOCKED_FEED:
            raise DatasetSecurityError(
                f"Manifest feed '{self.feed}' mismatch: must be '{LOCKED_FEED}'."
            )
        if self.timeframe != LOCKED_TIMEFRAME:
            raise DatasetSecurityError(
                f"Manifest timeframe '{self.timeframe}' mismatch: must be '{LOCKED_TIMEFRAME}'."
            )
        if self.adjustment != LOCKED_ADJUSTMENT:
            raise DatasetSecurityError(
                f"Manifest adjustment '{self.adjustment}' mismatch: must be '{LOCKED_ADJUSTMENT}'."
            )
        if self.calendar != LOCKED_CALENDAR:
            raise DatasetSecurityError(
                f"Manifest calendar '{self.calendar}' mismatch: must be '{LOCKED_CALENDAR}'."
            )
        if self.timezone != LOCKED_TIMEZONE:
            raise DatasetSecurityError(
                f"Manifest timezone '{self.timezone}' mismatch: must be '{LOCKED_TIMEZONE}'."
            )
        if tuple(self.universe) != spec.universe:
            raise DatasetSecurityError(
                f"Manifest universe mismatch: count {len(self.universe)} vs {len(spec.universe)}"
            )
        if not self.source_files:
            raise DatasetSecurityError("Manifest must contain at least one source file record.")

        # Strict source files validation: exactly "bars/{ticker}.csv"
        expected_files = {f"bars/{ticker}.csv" for ticker in spec.universe}
        for rel_path, digest in self.source_files.items():
            p_rel = Path(rel_path)
            if p_rel.is_absolute() or rel_path.startswith(("/", "\\")) or ":" in rel_path:
                raise DatasetSecurityError(f"Absolute or malformed path in manifest: '{rel_path}'")
            if ".." in p_rel.parts:
                raise DatasetSecurityError(f"Path traversal detected in manifest source file: '{rel_path}'")
            if len(digest) != 64 or not all(c in "0123456789abcdefABCDEF" for c in digest):
                raise DatasetSecurityError(f"Malformed SHA-256 digest in manifest for '{rel_path}': '{digest}'")

        manifest_files = set(self.source_files.keys())
        missing_files = expected_files - manifest_files
        if missing_files:
            raise DatasetSecurityError(f"Missing expected ticker source files in manifest: {sorted(missing_files)}")
        unexpected_files = manifest_files - expected_files
        if unexpected_files:
            raise DatasetSecurityError(f"Unexpected source files in manifest: {sorted(unexpected_files)}")

        # Check partition dates and lineage
        if self.partition == "preholdout":
            if self.start_date != spec.context_anchor_date or self.end_date != spec.validation.end:
                raise DatasetSecurityError(
                    f"Preholdout partition dates [{self.start_date}, {self.end_date}] "
                    f"must match [{spec.context_anchor_date}, {spec.validation.end}]."
                )
        elif self.partition == "holdout":
            if self.start_date != spec.holdout.start or self.end_date != spec.holdout.end:
                raise DatasetSecurityError(
                    f"Holdout partition dates [{self.start_date}, {self.end_date}] "
                    f"must match [{spec.holdout.start}, {spec.holdout.end}]."
                )
            if not self.preholdout_manifest_sha256:
                raise DatasetSecurityError("Holdout manifest must record preholdout_manifest_sha256 lineage.")
            if not self.validation_bundle_sha256:
                raise DatasetSecurityError("Holdout manifest must record validation_bundle_sha256 lineage.")
            if not self.evaluator_code_sha:
                raise DatasetSecurityError("Holdout manifest must record evaluator_code_sha lineage.")
        else:
            raise DatasetSecurityError(f"Unsupported manifest partition: {self.partition}")


def _verify_manifest_source_files(partition_dir: Path, manifest: DaytradeDatasetManifest) -> None:
    """Verify all source files exist on disk and hashes match manifest."""
    for rel_path, expected_sha in manifest.source_files.items():
        fp = partition_dir / rel_path
        if not fp.is_file():
            raise DatasetSecurityError(f"Missing source file recorded in manifest: {rel_path}")
        actual_sha = sha256_of_file(fp)
        if actual_sha != expected_sha:
            raise DatasetSecurityError(
                f"Source file hash mismatch for {rel_path}: {actual_sha} vs {expected_sha}"
            )


def _check_unmanifested_files(partition_dir: Path, manifest: DaytradeDatasetManifest) -> None:
    """Verify that no unmanifested CSV files exist on disk in partition/bars."""
    bars_dir = partition_dir / "bars"
    if bars_dir.is_dir():
        manifest_files = set(manifest.source_files.keys())
        for f in bars_dir.glob("*.csv"):
            rel = f"bars/{f.name}"
            if rel not in manifest_files:
                raise DatasetSecurityError(
                    f"Unmanifested OHLCV file found in partition {partition_dir}: {rel}"
                )


def verify_dataset_manifest(
    manifest: DaytradeDatasetManifest,
    spec: DaytradeSpec,
    partition_dir: Path,
) -> None:
    """Verify that dataset manifest adheres to locked contract and files match digests."""
    prov = manifest.acquisition_provenance or {}
    if prov.get("status") == "dry_run_no_provider_calls":
        raise DatasetSecurityError(
            "Manifest is a dry-run artifact (dry_run_no_provider_calls); "
            "dry-run cannot be verified as a formal acquired dataset."
        )
    if not manifest.source_files or len(manifest.source_files) != len(spec.universe):
        raise DatasetSecurityError(
            f"Manifest source_files incomplete: expected {len(spec.universe)} files, got {len(manifest.source_files)}"
        )
    manifest.validate_against_spec(spec)
    _verify_manifest_source_files(partition_dir, manifest)
    _check_unmanifested_files(partition_dir, manifest)


class DaytradeDatasetAcquisitionAdapter:
    """Safe bounded adapter for Alpaca market data acquisition."""

    def __init__(self, client: DatasetAlpacaClient) -> None:
        if client.max_retries > MAX_RETRIES_PER_FAILED_PAGE:
            raise DatasetSecurityError(
                f"Client max_retries {client.max_retries} exceeds locked limit of {MAX_RETRIES_PER_FAILED_PAGE}"
            )
        self.client = client

    def fetch_symbol_month_bars(
        self,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Fetch bars for a single symbol over a month with hard 100-page limit and safe metadata."""
        dfs, meta = self.client.get_bars(
            symbols=[symbol],
            start_utc=start_utc,
            end_utc=end_utc,
            feed=LOCKED_FEED,
            timeframe=LOCKED_TIMEFRAME,
            adjustment=LOCKED_ADJUSTMENT,
            max_pages=MAX_PAGES_PER_CALENDAR_MONTH_CHUNK,
        )

        safe_err = meta.get("safe_error_classification", "none")
        if safe_err == "max_pages_exceeded" or (
            meta.get("next_page_token_present") and not meta.get("pagination_complete")
        ):
            raise DatasetPaginationLimitError(
                f"Pagination hard limit of {MAX_PAGES_PER_CALENDAR_MONTH_CHUNK} pages exceeded for {symbol}"
            )

        if not meta.get("pagination_complete", False):
            raise DatasetSecurityError(f"Pagination failed for {symbol}: {safe_err}")

        if safe_err != "none":
            raise DatasetSecurityError(f"Provider returned error classification '{safe_err}' for {symbol}")

        # Response-symbol identity check: reject unexpected extra response symbols or missing symbol
        resp_syms = {s.upper() for s in meta.get("response_symbols", [])}
        if not resp_syms and dfs:
            resp_syms = {s.upper() for s in dfs}
        if symbol.upper() not in resp_syms:
            raise DatasetSecurityError(
                f"Requested symbol {symbol} missing from client response: {sorted(resp_syms)}"
            )
        unexpected = resp_syms - {symbol.upper()}
        if unexpected:
            raise DatasetSecurityError(
                f"Unexpected response symbols {sorted(unexpected)} returned for single-symbol request {symbol}"
            )

        logical_calls = meta.get("logical_calls", 1)
        http_attempts = meta.get("http_attempts", meta.get("attempts", 0))
        http_pages = meta.get("http_pages", meta.get("pages_retrieved", meta.get("page_count", 0)))
        retries = meta.get("retries", max(0, http_attempts - logical_calls))
        http_429s = meta.get("http_429s", meta.get("rate_limits_hit", 0))
        http_errors = meta.get("http_errors", meta.get("network_errors", 0))
        malformed_ts_count = meta.get("malformed_timestamp_counts", {}).get(symbol.upper(), 0) if isinstance(meta.get("malformed_timestamp_counts"), dict) else meta.get("malformed_timestamp_count", 0)

        safe_meta = {
            "symbol": symbol.upper(),
            "logical_calls": logical_calls,
            "http_pages": http_pages,
            "http_attempts": http_attempts,
            "retries": retries,
            "http_429s": http_429s,
            "http_errors": http_errors,
            "malformed_timestamp_counts": malformed_ts_count,
            "malformed_timestamp_count": malformed_ts_count,
            "pagination_complete": meta.get("pagination_complete", True),
            "safe_error_classification": safe_err,
            "page_count": http_pages,
        }

        df = dfs.get(symbol.upper(), pd.DataFrame())
        return df, safe_meta


def _month_intervals(start_d: date, end_d: date) -> list[tuple[datetime, datetime]]:
    """Generate (start_utc, end_utc) month intervals spanning start_d through end_d."""
    intervals: list[tuple[datetime, datetime]] = []
    curr_y, curr_m = start_d.year, start_d.month
    end_y, end_m = end_d.year, end_d.month

    while (curr_y, curr_m) <= (end_y, end_m):
        _, last_day = calendar.monthrange(curr_y, curr_m)
        chunk_start_d = max(start_d, date(curr_y, curr_m, 1))
        chunk_end_d = min(end_d, date(curr_y, curr_m, last_day))

        start_utc = datetime.combine(chunk_start_d, time.min, tzinfo=UTC)
        end_utc = datetime.combine(chunk_end_d, time.max, tzinfo=UTC)
        intervals.append((start_utc, end_utc))

        if curr_m == 12:
            curr_y += 1
            curr_m = 1
        else:
            curr_m += 1

    return intervals


def acquire_dataset_partition(
    dataset_root: Path | str,
    partition: str,
    spec: DaytradeSpec,
    *,
    client: Any = None,
    execute_provider: bool = False,
    repo_root: Path | None = None,
    validation_artifact_dir: Path | str | None = None,
    holdout_access_proof: HoldoutAccessProof | None = None,
) -> DaytradeDatasetManifest:
    """Future authorized dataset acquisition path with strict authorization guards.

    Canonical layout:
        <dataset_root>/<partition>/manifest.lock.json
        <dataset_root>/<partition>/bars/<ticker>.csv

    Locked guards:
    - Fails closed unless execute_provider is explicitly True;
    - Dataset root must reside outside the repository;
    - If holdout partition: requires verified HoldoutAccessProof (from validation_artifact_dir or trusted caller);
    - Reuses DatasetAlpacaClient.get_bars(...) with monthly chunking and bounded 100-page limit.
    """
    valid_root = validate_dataset_root(dataset_root, repo_root=repo_root)

    if partition not in ("preholdout", "holdout"):
        raise ValueError(f"Partition must be 'preholdout' or 'holdout', got: {partition}")

    partition_dir = valid_root / partition
    bars_dir = partition_dir / "bars"

    preholdout_manifest_sha: str | None = None
    validation_bundle_sha: str | None = None
    evaluator_code_sha: str | None = None

    if partition == "preholdout":
        start_date = spec.context_anchor_date  # 2025-12-31
        end_date = spec.validation.end          # 2026-06-30
    else:
        start_date = spec.holdout.start         # 2026-07-01
        end_date = spec.holdout.end             # 2026-08-31

        proof: HoldoutAccessProof | None = None
        if holdout_access_proof is not None:
            if not isinstance(holdout_access_proof, HoldoutAccessProof):
                raise HoldoutAccessDeniedError(
                    f"holdout_access_proof must be an instance of HoldoutAccessProof, got {type(holdout_access_proof).__name__}"
                )
            proof = holdout_access_proof
        elif validation_artifact_dir is not None:
            from .study import verify_holdout_access_prerequisites

            proof = verify_holdout_access_prerequisites(validation_artifact_dir, spec, repo_root=repo_root)
        else:
            raise HoldoutAccessDeniedError(
                "Holdout acquisition strictly requires verified HoldoutAccessProof or valid validation_artifact_dir."
            )

        preholdout_manifest_sha = proof.manifest_sha256
        validation_bundle_sha = proof.validation_bundle_sha256
        evaluator_code_sha = proof.evaluator_code_sha

    if not execute_provider:
        # Dry-run or planning mode: zero network requests and zero credential access
        manifest = DaytradeDatasetManifest(
            task_id="DAYTRADE-002A",
            spec_sha256=spec.sha256,
            partition=partition,
            provider=LOCKED_PROVIDER,
            feed=LOCKED_FEED,
            timeframe=LOCKED_TIMEFRAME,
            adjustment=LOCKED_ADJUSTMENT,
            calendar=LOCKED_CALENDAR,
            timezone=LOCKED_TIMEZONE,
            universe=spec.universe,
            start_date=start_date,
            end_date=end_date,
            source_files={},
            acquisition_provenance={
                "status": "dry_run_no_provider_calls",
                "execution_mode": "dry_run",
                "execute_provider": False,
                "logical_calls": 0,
                "http_pages": 0,
                "http_attempts": 0,
                "retries": 0,
                "http_429s": 0,
                "http_errors": 0,
                "malformed_timestamp_counts": {s: 0 for s in spec.universe},
                "total_malformed_timestamps": 0,
                "pagination_complete": True,
                "safe_error_classification": "none",
            },
            preholdout_manifest_sha256=preholdout_manifest_sha,
            validation_bundle_sha256=validation_bundle_sha,
            evaluator_code_sha=evaluator_code_sha,
        )
        manifest.manifest_sha256 = manifest.compute_sha256()
        partition_dir.mkdir(parents=True, exist_ok=True)
        dry_run_fp = partition_dir / "manifest.dry-run.json"
        dry_run_fp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return manifest

    # Authorized provider execution path (requires explicit client or credentials)
    if client is not None:
        alpaca_client = client
    else:
        api_key = os.environ.get("ALPACA_API_KEY")
        secret_key = os.environ.get("ALPACA_SECRET_KEY")
        if not api_key or not secret_key:
            raise DatasetSecurityError("ALPACA_API_KEY and ALPACA_SECRET_KEY required when execute_provider=True")
        alpaca_client = DatasetAlpacaClient(api_key=api_key, secret_key=secret_key, max_retries=1)

    adapter = DaytradeDatasetAcquisitionAdapter(alpaca_client)
    partition_dir.mkdir(parents=True, exist_ok=True)
    bars_dir.mkdir(parents=True, exist_ok=True)

    source_files: dict[str, str] = {}
    total_logical_calls = 0
    total_http_pages = 0
    total_http_attempts = 0
    total_retries = 0
    total_http_429s = 0
    total_http_errors = 0
    malformed_by_ticker: dict[str, int] = {s: 0 for s in spec.universe}

    start_d = date.fromisoformat(start_date)
    end_d = date.fromisoformat(end_date)
    intervals = _month_intervals(start_d, end_d)

    # Acquire each ETF's 1Min bars in monthly chunks
    for sym in spec.universe:
        all_month_dfs: list[pd.DataFrame] = []
        for start_utc, end_utc in intervals:
            month_df, safe_meta = adapter.fetch_symbol_month_bars(
                symbol=sym,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            total_logical_calls += safe_meta["logical_calls"]
            total_http_pages += safe_meta["http_pages"]
            total_http_attempts += safe_meta["http_attempts"]
            total_retries += safe_meta["retries"]
            total_http_429s += safe_meta["http_429s"]
            total_http_errors += safe_meta["http_errors"]
            malformed_by_ticker[sym] += safe_meta["malformed_timestamp_counts"]
            if not month_df.empty:
                all_month_dfs.append(month_df)

        if all_month_dfs:
            combined_df = pd.concat(all_month_dfs, axis=0)
        else:
            combined_df = pd.DataFrame(columns=["bar_start", "open", "high", "low", "close", "volume"])

        rel_fn = f"bars/{sym}.csv"
        out_fp = partition_dir / rel_fn
        write_normalized_bars_csv(out_fp, combined_df)
        source_files[rel_fn] = sha256_of_file(out_fp)

    provenance_stats = {
        "status": "authorized_provider_acquisition",
        "execution_mode": "provider_execution",
        "execute_provider": True,
        "logical_calls": total_logical_calls,
        "http_pages": total_http_pages,
        "http_attempts": total_http_attempts,
        "retries": total_retries,
        "http_429s": total_http_429s,
        "http_errors": total_http_errors,
        "malformed_timestamp_counts": malformed_by_ticker,
        "total_malformed_timestamps": sum(malformed_by_ticker.values()),
        "pagination_complete": True,
        "safe_error_classification": "none",
    }

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002A",
        spec_sha256=spec.sha256,
        partition=partition,
        provider=LOCKED_PROVIDER,
        feed=LOCKED_FEED,
        timeframe=LOCKED_TIMEFRAME,
        adjustment=LOCKED_ADJUSTMENT,
        calendar=LOCKED_CALENDAR,
        timezone=LOCKED_TIMEZONE,
        universe=spec.universe,
        start_date=start_date,
        end_date=end_date,
        source_files=source_files,
        acquisition_provenance=provenance_stats,
        preholdout_manifest_sha256=preholdout_manifest_sha,
        validation_bundle_sha256=validation_bundle_sha,
        evaluator_code_sha=evaluator_code_sha,
    )
    manifest.manifest_sha256 = manifest.compute_sha256()

    manifest_fp = partition_dir / "manifest.lock.json"
    manifest_fp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    return manifest


acquire_partition_data = acquire_dataset_partition


def load_private_dataset(
    dataset_root: Path | str,
    spec: DaytradeSpec,
    split_name: str,
    include_history: bool = True,
    repo_root: Path | None = None,
    validation_artifact_dir: Path | str | None = None,
) -> tuple[dict[str, list[DaytradeSession]], list[DataQualityReport]]:
    """Load and audit private dataset for a target evaluation split.

    Canonical layout:
        <dataset_root>/preholdout/manifest.lock.json
        <dataset_root>/preholdout/bars/<ticker>.csv
        <dataset_root>/holdout/manifest.lock.json
        <dataset_root>/holdout/bars/<ticker>.csv

    For development and validation:
        Loaded from <dataset_root>/preholdout.
    For holdout:
        History loaded from <dataset_root>/preholdout (entire preholdout context).
        Target observations loaded from <dataset_root>/holdout.

    Returns:
        (sessions_by_ticker, quality_reports)
    """
    valid_root = validate_dataset_root(dataset_root, repo_root=repo_root)
    name = split_name.lower().strip()

    split_dates = spec.get_split_dates(name)
    target_start = split_dates.start
    target_end = split_dates.end

    target_sessions = get_regular_trading_sessions(target_start, target_end, exclude_early_closes=True)
    target_sessions_set = set(target_sessions)

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    quality_reports: list[DataQualityReport] = []

    if name == "holdout":
        # Dual-partition holdout loader
        if not validation_artifact_dir:
            raise HoldoutAccessDeniedError("Holdout evaluation requires --validation-artifact-dir.")

        from .study import verify_holdout_access_prerequisites

        proof = verify_holdout_access_prerequisites(validation_artifact_dir, spec, repo_root=repo_root)
        val_bundle_sha = proof.validation_bundle_sha256
        val_evaluator_sha = proof.evaluator_code_sha
        val_manifest_sha = proof.manifest_sha256
        val_spec_sha = proof.spec_sha256

        # 1. Preholdout partition (history source)
        pre_dir = valid_root / "preholdout"
        pre_manifest_file = pre_dir / "manifest.lock.json"
        if not pre_manifest_file.is_file():
            raise DatasetSecurityError(f"Preholdout manifest not found in {pre_dir}")
        pre_data = json.loads(pre_manifest_file.read_text(encoding="utf-8"))
        pre_manifest = DaytradeDatasetManifest.from_dict(pre_data)
        verify_dataset_manifest(pre_manifest, spec, pre_dir)

        if pre_manifest.manifest_sha256 != val_manifest_sha:
            raise DatasetSecurityError(
                f"Preholdout manifest SHA '{pre_manifest.manifest_sha256}' mismatch with validation manifest '{val_manifest_sha}'"
            )

        # 2. Holdout partition (target source)
        holdout_dir = valid_root / "holdout"
        holdout_manifest_file = holdout_dir / "manifest.lock.json"
        if not holdout_manifest_file.is_file():
            raise DatasetSecurityError(f"Holdout manifest not found in {holdout_dir}")
        holdout_data = json.loads(holdout_manifest_file.read_text(encoding="utf-8"))
        holdout_manifest = DaytradeDatasetManifest.from_dict(holdout_data)
        verify_dataset_manifest(holdout_manifest, spec, holdout_dir)

        # 3. Lineage verification
        if holdout_manifest.preholdout_manifest_sha256 != pre_manifest.manifest_sha256:
            raise DatasetSecurityError(
                f"Holdout manifest preholdout_manifest_sha256 '{holdout_manifest.preholdout_manifest_sha256}' "
                f"mismatch with preholdout manifest SHA '{pre_manifest.manifest_sha256}'"
            )
        if holdout_manifest.validation_bundle_sha256 != val_bundle_sha:
            raise DatasetSecurityError(
                f"Holdout manifest validation_bundle_sha256 '{holdout_manifest.validation_bundle_sha256}' "
                f"mismatch with validation bundle SHA '{val_bundle_sha}'"
            )
        if holdout_manifest.evaluator_code_sha != val_evaluator_sha:
            raise DatasetSecurityError(
                f"Holdout manifest evaluator_code_sha '{holdout_manifest.evaluator_code_sha}' "
                f"mismatch with validation evaluator code SHA '{val_evaluator_sha}'"
            )
        if holdout_manifest.spec_sha256 != val_spec_sha:
            raise DatasetSecurityError(
                f"Holdout manifest spec_sha256 '{holdout_manifest.spec_sha256}' mismatch with spec '{val_spec_sha}'"
            )

        # 4. Load history from preholdout and target from holdout
        hist_dates = spec.get_history_dates("holdout")
        hist_start = hist_dates[0] if hist_dates else spec.context_anchor_date
        hist_end = hist_dates[1] if hist_dates else spec.validation.end

        history_sessions = get_regular_trading_sessions(hist_start, hist_end, exclude_early_closes=True)

        for sym in spec.universe:
            ticker_sessions: list[DaytradeSession] = []

            # History from preholdout
            hist_csv = pre_dir / "bars" / f"{sym}.csv"
            hist_df, _ = read_normalized_bars_csv(hist_csv)
            hist_by_session = {
                d: grp for d, grp in hist_df.groupby(hist_df["dt_parsed"].dt.tz_convert(LOCKED_TIMEZONE).dt.date)
            }
            for s_date in history_sessions:
                grid = build_regular_session_grid(s_date)
                sess_df = hist_by_session.get(s_date)
                if sess_df is None or len(sess_df) == 0:
                    sess, _ = audit_missing_ticker_session(sym, s_date)
                else:
                    sess, _ = audit_ticker_session(sym, s_date, sess_df, grid)
                ticker_sessions.append(sess)

            # Target from holdout
            tgt_csv = holdout_dir / "bars" / f"{sym}.csv"
            tgt_df, _ = read_normalized_bars_csv(tgt_csv)
            tgt_by_session = {
                d: grp for d, grp in tgt_df.groupby(tgt_df["dt_parsed"].dt.tz_convert(LOCKED_TIMEZONE).dt.date)
            }
            for s_date in target_sessions:
                grid = build_regular_session_grid(s_date)
                sess_df = tgt_by_session.get(s_date)
                if sess_df is None or len(sess_df) == 0:
                    sess, rep = audit_missing_ticker_session(sym, s_date)
                else:
                    sess, rep = audit_ticker_session(sym, s_date, sess_df, grid)
                ticker_sessions.append(sess)
                quality_reports.append(rep)

            sessions_by_ticker[sym] = ticker_sessions

    else:
        # Development and Validation partitions: loaded from preholdout
        part_dir = valid_root / "preholdout"
        manifest_file = part_dir / "manifest.lock.json"
        if not manifest_file.is_file():
            raise DatasetSecurityError(f"Preholdout manifest not found in {part_dir}")
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = DaytradeDatasetManifest.from_dict(manifest_data)
        verify_dataset_manifest(manifest, spec, part_dir)

        if include_history:
            hist_dates = spec.get_history_dates(name)
            load_start = hist_dates[0] if hist_dates else spec.context_anchor_date
        else:
            load_start = target_start

        expected_sessions = get_regular_trading_sessions(load_start, target_end, exclude_early_closes=True)

        for sym in spec.universe:
            csv_file = part_dir / "bars" / f"{sym}.csv"
            if not csv_file.is_file():
                ticker_sessions = []
                for s_date in expected_sessions:
                    sess, rep = audit_missing_ticker_session(sym, s_date)
                    ticker_sessions.append(sess)
                    if s_date in target_sessions_set:
                        quality_reports.append(rep)
                sessions_by_ticker[sym] = ticker_sessions
                continue

            df, _ = read_normalized_bars_csv(csv_file)
            by_session = {
                d: group
                for d, group in df.groupby(df["dt_parsed"].dt.tz_convert(LOCKED_TIMEZONE).dt.date)
            }

            ticker_sessions = []
            for s_date in expected_sessions:
                grid = build_regular_session_grid(s_date)
                sess_df = by_session.get(s_date)
                if sess_df is None or len(sess_df) == 0:
                    sess, rep = audit_missing_ticker_session(sym, s_date)
                else:
                    sess, rep = audit_ticker_session(sym, s_date, sess_df, grid)
                ticker_sessions.append(sess)
                if s_date in target_sessions_set:
                    quality_reports.append(rep)

            sessions_by_ticker[sym] = ticker_sessions

    return sessions_by_ticker, quality_reports
