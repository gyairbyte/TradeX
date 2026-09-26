"""Dataset manifest contract, security bounds, and bounded Alpaca acquisition adapter."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

from .calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from .models import DataQualityReport, DaytradeSession
from .quality import audit_missing_ticker_session, audit_ticker_session
from .spec import DaytradeSpec

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
    k_lower = k.lower()
    if k in SAFE_KEY_ALLOWLIST or k_lower in SAFE_KEY_ALLOWLIST:
        return
    if "token" in k_lower and ("hash" in k_lower or "sequence" in k_lower):
        return
    for pattern in FORBIDDEN_KEY_PATTERNS:
        if pattern in k_lower:
            raise DatasetSecurityError(f"Prohibited key pattern '{pattern}' found in key '{k}'")


def _check_forbidden_val(v: Any) -> None:
    if isinstance(v, str):
        v_lower = v.lower()
        if v_lower.startswith(("bearer ", "basic ")):
            raise DatasetSecurityError("Prohibited authorization token value found in manifest")
        for env_var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
            secret_val = os.environ.get(env_var)
            if secret_val and len(secret_val) >= 8 and secret_val in v:
                raise DatasetSecurityError(f"Prohibited credential value from {env_var} found in manifest payload")


def sanitize_manifest_data(data: Any) -> Any:
    """Recursively validate that no API keys, secrets, tokens, or raw bodies exist."""
    if isinstance(data, dict):
        for k, v in data.items():
            _check_forbidden_key(str(k))
            sanitize_manifest_data(v)
    elif isinstance(data, list):
        for item in data:
            sanitize_manifest_data(item)
    else:
        _check_forbidden_val(data)
    return data


def compute_validation_bundle_sha256(validation_artifact_dir: Path | str) -> str:
    """Compute the deterministic SHA-256 identity of the validation artifact bundle."""
    vdir = Path(validation_artifact_dir).expanduser().resolve()
    chk_file = vdir / "checksums.sha256"
    if not chk_file.is_file():
        raise DatasetSecurityError(f"Missing checksums.sha256 in validation artifact dir: {vdir}")
    return sha256_of_file(chk_file)


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


def read_normalized_bars_csv(path: Path) -> pd.DataFrame:
    """Read normalized bars CSV and return typed DataFrame."""
    if not path.is_file():
        raise DatasetSecurityError(f"Bars file not found: {path}")
    df = pd.read_csv(path, encoding="utf-8")
    expected = ["bar_start", "open", "high", "low", "close", "volume"]
    if list(df.columns) != expected:
        raise DatasetSecurityError(
            f"CSV columns in {path} mismatch locked schema: expected {expected}, got {list(df.columns)}"
        )
    return df


@dataclass
class DaytradeDatasetManifest:
    """Normative private-dataset manifest contract for DAYTRADE-001."""

    study_id: str = "DAYTRADE-001B"
    spec_sha256: str = ""
    partition: str = "preholdout"  # "preholdout" or "holdout"
    provider: str = LOCKED_PROVIDER
    feed: str = LOCKED_FEED
    timeframe: str = LOCKED_TIMEFRAME
    adjustment: str = LOCKED_ADJUSTMENT
    session_calendar: str = LOCKED_CALENDAR
    timezone: str = LOCKED_TIMEZONE
    universe: list[str] = field(default_factory=list)
    start_date: str = "2024-12-02"
    end_date: str = "2025-09-30"
    source_files: dict[str, str] = field(default_factory=dict)
    preholdout_manifest_sha256: str | None = None
    validation_bundle_sha256: str | None = None
    validation_artifact_dir: str | None = None
    evaluator_code_sha: str | None = None
    acquisition_provenance: dict[str, Any] = field(default_factory=dict)
    manifest_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dict and compute its deterministic manifest_sha256."""
        d = asdict(self)
        d.pop("manifest_sha256", None)
        sanitized = sanitize_manifest_data(d)
        serialized = json.dumps(sanitized, sort_keys=True, indent=2)
        h = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        sanitized["manifest_sha256"] = h
        return sanitized

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaytradeDatasetManifest:
        """Parse and verify a manifest dictionary."""
        sanitized = sanitize_manifest_data(dict(data))
        m_sha = sanitized.get("manifest_sha256", "")
        copy_d = dict(sanitized)
        copy_d.pop("manifest_sha256", None)
        computed = hashlib.sha256(json.dumps(copy_d, sort_keys=True, indent=2).encode("utf-8")).hexdigest()
        if m_sha and m_sha != computed:
            raise DatasetSecurityError(
                f"Manifest SHA-256 mismatch: recorded {m_sha}, computed {computed}"
            )
        return cls(**sanitized)

    def validate_against_spec(self, spec: DaytradeSpec) -> None:
        """Strictly validate manifest properties against the locked DaytradeSpec."""
        if self.study_id != "DAYTRADE-001B":
            raise DatasetSecurityError(
                f"Manifest study_id '{self.study_id}' invalid: must be strictly 'DAYTRADE-001B'."
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
        if self.session_calendar != LOCKED_CALENDAR:
            raise DatasetSecurityError(
                f"Manifest calendar '{self.session_calendar}' mismatch: must be '{LOCKED_CALENDAR}'."
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

        # Strict source files validation
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

        # Check partition dates
        if self.partition == "preholdout":
            if self.start_date != spec.warmup.start or self.end_date != spec.validation.end:
                raise DatasetSecurityError(
                    f"Pre-holdout partition dates [{self.start_date}, {self.end_date}] "
                    f"must match [{spec.warmup.start}, {spec.validation.end}]."
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
    ) -> pd.DataFrame:
        """Fetch bars for a single symbol over a month with hard 100-page limit."""
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
        if safe_err == "max_pages_exceeded" or (meta.get("next_page_token_present") and not meta.get("pagination_complete")):
            raise DatasetPaginationLimitError(
                f"Pagination hard limit of {MAX_PAGES_PER_CALENDAR_MONTH_CHUNK} pages exceeded for {symbol}"
            )

        if not meta.get("pagination_complete", False):
            raise DatasetSecurityError(f"Pagination failed for {symbol}: {safe_err}")

        return dfs.get(symbol.upper(), pd.DataFrame())


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


def _verify_manifest_source_files(partition_dir: Path, manifest: DaytradeDatasetManifest) -> None:
    """Verify all source files exist and hashes match manifest."""
    for rel_path, expected_sha in manifest.source_files.items():
        fp = partition_dir / rel_path
        if not fp.is_file():
            raise DatasetSecurityError(f"Missing source file recorded in manifest: {rel_path}")
        actual_sha = sha256_of_file(fp)
        if actual_sha != expected_sha:
            raise DatasetSecurityError(
                f"Source file hash mismatch for {rel_path}: {actual_sha} vs {expected_sha}"
            )


def load_private_dataset(
    dataset_root: Path | str,
    split_name: str,
    spec: DaytradeSpec,
    validation_artifact_dir: Path | str | None = None,
) -> tuple[list[DaytradeSession], list[DataQualityReport]]:
    """Load and audit a private dataset partition for the specified split."""
    root = validate_dataset_root(dataset_root)
    name = split_name.lower().strip()
    target_dates = spec.get_split_dates(name)
    history_dates = spec.get_history_dates(name)

    all_sessions: list[DaytradeSession] = []
    target_quality_reports: list[DataQualityReport] = []

    if name == "holdout":
        # 1. Preholdout partition (history source)
        pre_dir = root / "preholdout"
        pre_manifest_file = pre_dir / "manifest.lock.json"
        if not pre_manifest_file.is_file():
            raise DatasetSecurityError(f"Preholdout manifest not found in {pre_dir}")
        pre_data = json.loads(pre_manifest_file.read_text(encoding="utf-8"))
        pre_manifest = DaytradeDatasetManifest.from_dict(pre_data)
        pre_manifest.validate_against_spec(spec)
        _check_unmanifested_files(pre_dir, pre_manifest)
        _verify_manifest_source_files(pre_dir, pre_manifest)

        # 2. Holdout partition (target observations)
        holdout_dir = root / "holdout"
        holdout_manifest_file = holdout_dir / "manifest.lock.json"
        if not holdout_manifest_file.is_file():
            raise DatasetSecurityError(f"Holdout manifest not found in {holdout_dir}")
        holdout_data = json.loads(holdout_manifest_file.read_text(encoding="utf-8"))
        holdout_manifest = DaytradeDatasetManifest.from_dict(holdout_data)
        holdout_manifest.validate_against_spec(spec)
        _check_unmanifested_files(holdout_dir, holdout_manifest)
        _verify_manifest_source_files(holdout_dir, holdout_manifest)

        # 3. Lineage verification
        if holdout_manifest.preholdout_manifest_sha256 != pre_manifest.manifest_sha256:
            raise DatasetSecurityError(
                f"Holdout manifest preholdout_manifest_sha256 '{holdout_manifest.preholdout_manifest_sha256}' "
                f"mismatch with preholdout manifest '{pre_manifest.manifest_sha256}'"
            )
        if holdout_manifest.spec_sha256 != spec.sha256:
            raise DatasetSecurityError("Holdout manifest spec_sha256 mismatch with locked spec")

        if validation_artifact_dir:
            val_bundle_sha = compute_validation_bundle_sha256(validation_artifact_dir)
            if holdout_manifest.validation_bundle_sha256 != val_bundle_sha:
                raise DatasetSecurityError(
                    f"Holdout manifest validation_bundle_sha256 '{holdout_manifest.validation_bundle_sha256}' "
                    f"mismatch with validation bundle '{val_bundle_sha}'"
                )

        # 4. Load history from preholdout and target from holdout
        hist_start_d = date.fromisoformat(history_dates[0]) if history_dates else date.fromisoformat(target_dates.start)
        hist_end_d = date.fromisoformat(history_dates[1]) if history_dates else date.fromisoformat(target_dates.start)
        tgt_start_d = date.fromisoformat(target_dates.start)
        tgt_end_d = date.fromisoformat(target_dates.end)

        for ticker in spec.universe:
            # History bars from preholdout
            hist_file = pre_dir / "bars" / f"{ticker}.csv"
            hist_df = read_normalized_bars_csv(hist_file) if hist_file.is_file() else pd.DataFrame()
            hist_by_date: dict[date, pd.DataFrame] = {}
            if not hist_df.empty and "bar_start" in hist_df.columns:
                bar_dates = pd.to_datetime(hist_df["bar_start"], utc=True).dt.date
                for d, sub in hist_df.groupby(bar_dates):
                    hist_by_date[d] = sub

            for curr_d in get_regular_trading_sessions(hist_start_d, hist_end_d, exclude_early_close=True):
                session_df = hist_by_date.get(curr_d)
                if session_df is not None and not session_df.empty:
                    grid = build_regular_session_grid(curr_d)
                    s, _ = audit_ticker_session(ticker, curr_d, session_df, grid)
                else:
                    s, _ = audit_missing_ticker_session(ticker, curr_d)
                all_sessions.append(s)

            # Target bars from holdout
            tgt_file = holdout_dir / "bars" / f"{ticker}.csv"
            tgt_df = read_normalized_bars_csv(tgt_file) if tgt_file.is_file() else pd.DataFrame()
            tgt_by_date: dict[date, pd.DataFrame] = {}
            if not tgt_df.empty and "bar_start" in tgt_df.columns:
                bar_dates = pd.to_datetime(tgt_df["bar_start"], utc=True).dt.date
                for d, sub in tgt_df.groupby(bar_dates):
                    tgt_by_date[d] = sub

            for curr_d in get_regular_trading_sessions(tgt_start_d, tgt_end_d, exclude_early_close=True):
                session_df = tgt_by_date.get(curr_d)
                if session_df is not None and not session_df.empty:
                    grid = build_regular_session_grid(curr_d)
                    s, r = audit_ticker_session(ticker, curr_d, session_df, grid)
                else:
                    s, r = audit_missing_ticker_session(ticker, curr_d)
                all_sessions.append(s)
                target_quality_reports.append(r)

    else:
        # Preholdout partition for warmup, development, validation
        partition_dir = root / "preholdout"
        manifest_file = partition_dir / "manifest.lock.json"
        if not manifest_file.is_file():
            raise DatasetSecurityError(f"Manifest not found in partition {partition_dir}")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = DaytradeDatasetManifest.from_dict(manifest_data)
        manifest.validate_against_spec(spec)
        _check_unmanifested_files(partition_dir, manifest)
        _verify_manifest_source_files(partition_dir, manifest)

        eff_start = history_dates[0] if history_dates else target_dates.start
        eff_end = target_dates.end

        start_d = date.fromisoformat(eff_start)
        end_d = date.fromisoformat(eff_end)

        for ticker in spec.universe:
            bars_file = partition_dir / "bars" / f"{ticker}.csv"
            bars_df = read_normalized_bars_csv(bars_file) if bars_file.is_file() else pd.DataFrame()

            df_by_date: dict[date, pd.DataFrame] = {}
            if not bars_df.empty and "bar_start" in bars_df.columns:
                bar_dates = pd.to_datetime(bars_df["bar_start"], utc=True).dt.date
                for d, sub in bars_df.groupby(bar_dates):
                    df_by_date[d] = sub

            for curr_d in get_regular_trading_sessions(start_d, end_d, exclude_early_close=True):
                session_df = df_by_date.get(curr_d)
                if session_df is not None and not session_df.empty:
                    grid = build_regular_session_grid(curr_d)
                    s, r = audit_ticker_session(ticker, curr_d, session_df, grid)
                else:
                    s, r = audit_missing_ticker_session(ticker, curr_d)

                all_sessions.append(s)
                if target_dates.start <= curr_d.isoformat() <= target_dates.end:
                    target_quality_reports.append(r)

    return all_sessions, target_quality_reports


def _get_monthly_chunks(start_date: str, end_date: str) -> list[tuple[str, datetime, datetime]]:
    """Return list of (month_label, start_utc, end_utc) for calendar months."""
    import calendar as py_cal
    s_d = date.fromisoformat(start_date)
    e_d = date.fromisoformat(end_date)

    chunks: list[tuple[str, datetime, datetime]] = []
    curr_y = s_d.year
    curr_m = s_d.month

    while True:
        if curr_y == s_d.year and curr_m == s_d.month:
            m_start_d = s_d
        else:
            m_start_d = date(curr_y, curr_m, 1)

        _, last_day = py_cal.monthrange(curr_y, curr_m)
        m_end_cand = date(curr_y, curr_m, last_day)
        m_end_d = min(e_d, m_end_cand)

        label = f"{curr_y:04d}-{curr_m:02d}"
        start_utc = datetime(m_start_d.year, m_start_d.month, m_start_d.day, 0, 0, 0, tzinfo=UTC)
        end_utc = datetime(m_end_d.year, m_end_d.month, m_end_d.day, 23, 59, 59, tzinfo=UTC)
        chunks.append((label, start_utc, end_utc))

        if m_end_d >= e_d:
            break

        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1

    return chunks


def acquire_dataset_partition(
    spec: DaytradeSpec,
    dataset_root: Path | str,
    partition: str,
    client: DatasetAlpacaClient,
    validation_bundle_dir: Path | str | None = None,
    evaluator_code_sha: str | None = None,
) -> tuple[DaytradeDatasetManifest, dict[str, Any]]:
    """Acquire private dataset partition using locked Alpaca client parameters."""
    if partition not in ("preholdout", "holdout"):
        raise DatasetSecurityError(
            f"Unsupported acquisition partition: '{partition}'. Must be 'preholdout' or 'holdout'."
        )

    root = validate_dataset_root(dataset_root)
    partition_dir = root / partition
    bars_dir = partition_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    if client.max_retries > MAX_RETRIES_PER_FAILED_PAGE:
        raise DatasetSecurityError(
            f"Client max_retries {client.max_retries} exceeds locked limit of {MAX_RETRIES_PER_FAILED_PAGE}"
        )

    if partition == "preholdout":
        start_date = spec.warmup.start
        end_date = spec.validation.end
        preholdout_manifest_sha = None
        validation_bundle_sha = None
    else:  # holdout
        start_date = spec.holdout.start
        end_date = spec.holdout.end
        pre_file = root / "preholdout" / "manifest.lock.json"
        if not pre_file.is_file():
            raise DatasetSecurityError(
                f"Preholdout manifest not found at {pre_file}; holdout acquisition requires preholdout lineage."
            )
        pre_data = json.loads(pre_file.read_text(encoding="utf-8"))
        preholdout_manifest = DaytradeDatasetManifest.from_dict(pre_data)
        preholdout_manifest_sha = preholdout_manifest.manifest_sha256

        if not validation_bundle_dir:
            raise DatasetSecurityError("Holdout acquisition requires validation_bundle_dir.")
        validation_bundle_sha = compute_validation_bundle_sha256(validation_bundle_dir)

    chunks = _get_monthly_chunks(start_date, end_date)
    source_files: dict[str, str] = {}

    total_requests = 0
    total_pages = 0
    total_retries = 0
    total_errors = 0
    total_malformed_timestamps = 0
    per_symbol_provenance: dict[str, Any] = {}

    for symbol in spec.universe:
        sym_chunks_data: list[dict[str, Any]] = []
        sym_dfs: list[pd.DataFrame] = []
        sym_malformed_ts = 0

        for month_label, s_utc, e_utc in chunks:
            dfs, meta = client.get_bars(
                symbols=[symbol],
                start_utc=s_utc,
                end_utc=e_utc,
                feed=LOCKED_FEED,
                timeframe=LOCKED_TIMEFRAME,
                adjustment=LOCKED_ADJUSTMENT,
                max_pages=MAX_PAGES_PER_CALENDAR_MONTH_CHUNK,
            )
            total_requests += meta.get("logical_calls", 1)
            total_pages += meta.get("http_pages", 0)
            total_retries += meta.get("http_attempts", 1) - meta.get("http_pages", 0)
            http_errors = meta.get("http_errors", 0)
            total_errors += http_errors
            malformed_count = meta.get("malformed_timestamp_counts", {}).get(symbol.upper(), 0)
            sym_malformed_ts += malformed_count
            total_malformed_timestamps += malformed_count

            safe_err = meta.get("safe_error_classification", "none")
            if safe_err == "max_pages_exceeded":
                raise DatasetPaginationLimitError(
                    f"Pagination limit of {MAX_PAGES_PER_CALENDAR_MONTH_CHUNK} pages exceeded for {symbol} in {month_label}"
                )
            if not meta.get("pagination_complete", False) or safe_err != "none":
                raise DatasetSecurityError(
                    f"Provider acquisition failed for {symbol} in {month_label}: error={safe_err}, status={meta.get('http_status')}"
                )

            m_df = dfs.get(symbol.upper(), pd.DataFrame())
            sym_dfs.append(m_df)
            sym_chunks_data.append({
                "month": month_label,
                "start_utc": s_utc.isoformat(),
                "end_utc": e_utc.isoformat(),
                "pages": meta.get("http_pages", 0),
                "attempts": meta.get("http_attempts", 0),
                "safe_error": safe_err,
                "pagination_complete": meta.get("pagination_complete", False),
                "malformed_timestamps": malformed_count,
                "bar_count": len(m_df),
            })

        sym_combined = pd.concat(sym_dfs) if sym_dfs else pd.DataFrame()
        out_csv = bars_dir / f"{symbol}.csv"
        write_normalized_bars_csv(out_csv, sym_combined)
        file_sha = sha256_of_file(out_csv)
        rel_path = f"bars/{symbol}.csv"
        source_files[rel_path] = file_sha

        per_symbol_provenance[symbol] = {
            "source_file": rel_path,
            "file_sha256": file_sha,
            "total_bars": len(sym_combined),
            "malformed_timestamps": sym_malformed_ts,
            "month_chunks": sym_chunks_data,
        }

    acquisition_provenance = {
        "provider": LOCKED_PROVIDER,
        "feed": LOCKED_FEED,
        "timeframe": LOCKED_TIMEFRAME,
        "adjustment": LOCKED_ADJUSTMENT,
        "session_calendar": LOCKED_CALENDAR,
        "timezone": LOCKED_TIMEZONE,
        "start_date": start_date,
        "end_date": end_date,
        "total_symbols": len(spec.universe),
        "total_requests": total_requests,
        "total_pages": total_pages,
        "total_retries": total_retries,
        "total_errors": total_errors,
        "total_malformed_timestamps": total_malformed_timestamps,
        "pagination_complete": True,
        "symbols": per_symbol_provenance,
    }

    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition=partition,
        provider=LOCKED_PROVIDER,
        feed=LOCKED_FEED,
        timeframe=LOCKED_TIMEFRAME,
        adjustment=LOCKED_ADJUSTMENT,
        session_calendar=LOCKED_CALENDAR,
        timezone=LOCKED_TIMEZONE,
        universe=list(spec.universe),
        start_date=start_date,
        end_date=end_date,
        source_files=source_files,
        preholdout_manifest_sha256=preholdout_manifest_sha,
        validation_bundle_sha256=validation_bundle_sha,
        validation_artifact_dir=str(validation_bundle_dir) if validation_bundle_dir else None,
        evaluator_code_sha=evaluator_code_sha,
        acquisition_provenance=acquisition_provenance,
    )

    manifest_dict = manifest.to_dict()
    man_file = partition_dir / "manifest.lock.json"
    man_file.write_text(json.dumps(manifest_dict, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "partition": partition,
        "start_date": start_date,
        "end_date": end_date,
        "total_symbols": len(spec.universe),
        "total_requests": total_requests,
        "total_pages": total_pages,
        "total_retries": total_retries,
        "total_errors": total_errors,
        "manifest_sha256": manifest_dict["manifest_sha256"],
        "manifest_path": str(man_file),
    }

    return manifest, summary
