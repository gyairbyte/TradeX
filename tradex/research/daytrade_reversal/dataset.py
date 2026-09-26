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
    "evaluator_code_sha",
    "token_sequence_sha256",
    "source_files",
    "file_sha256",
    "token_hashes",
    "token_hash",
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


def write_normalized_bars_csv(path: Path, df: pd.DataFrame) -> None:
    """Write normalized bars to CSV following the locked DAYTRADE schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["bar_start", "open", "high", "low", "close", "volume"]
    export_df = df.copy()
    if "bar_start" not in export_df.columns and "datetime" in export_df.columns:
        export_df["bar_start"] = export_df["datetime"]

    # Format bar_start as ISO UTC
    export_df["bar_start"] = export_df["bar_start"].apply(
        lambda ts: ts.isoformat().replace("+00:00", "Z") if isinstance(ts, (datetime, pd.Timestamp)) else str(ts)
    )

    export_df = export_df.sort_values(by="bar_start", ascending=True)
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
    validation_artifact_dir: str | None = None
    evaluator_code_sha: str | None = None
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


def load_private_dataset(
    dataset_root: Path | str,
    split_name: str,
    spec: DaytradeSpec,
) -> tuple[list[DaytradeSession], list[DataQualityReport]]:
    """Load and audit a private dataset partition for the specified split."""
    root = validate_dataset_root(dataset_root)
    name = split_name.lower().strip()
    target_dates = spec.get_split_dates(name)
    history_dates = spec.get_history_dates(name)

    partition_name = "holdout" if name == "holdout" else "preholdout"
    partition_dir = root / partition_name

    manifest_file = partition_dir / "manifest.lock.json"
    if not manifest_file.is_file():
        raise DatasetSecurityError(f"Manifest not found in partition {partition_dir}")

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest = DaytradeDatasetManifest.from_dict(manifest_data)
    manifest.validate_against_spec(spec)

    # Verify all source files exist and hashes match
    for rel_path, expected_sha in manifest.source_files.items():
        fp = partition_dir / rel_path
        if not fp.is_file():
            raise DatasetSecurityError(f"Missing source file recorded in manifest: {rel_path}")
        actual_sha = sha256_of_file(fp)
        if actual_sha != expected_sha:
            raise DatasetSecurityError(f"Source file hash mismatch for {rel_path}: {actual_sha} vs {expected_sha}")

    # Determine date range to load: from history start (if any) to target split end
    eff_start = history_dates[0] if history_dates else target_dates.start
    eff_end = target_dates.end

    all_sessions: list[DaytradeSession] = []
    target_quality_reports: list[DataQualityReport] = []

    for ticker in spec.universe:
        bars_file = partition_dir / "bars" / f"{ticker}.csv"
        bars_df = read_normalized_bars_csv(bars_file) if bars_file.is_file() else pd.DataFrame()

        # Parse and group bars by date
        df_by_date: dict[date, list[dict[str, Any]]] = {}
        if not bars_df.empty:
            for _, row in bars_df.iterrows():
                try:
                    ts = datetime.fromisoformat(str(row["bar_start"]))
                    d = ts.astimezone(UTC).date()
                    if d not in df_by_date:
                        df_by_date[d] = []
                    df_by_date[d].append(dict(row))
                except (ValueError, KeyError, TypeError):
                    continue

        # Audit all expected regular trading sessions in [eff_start, eff_end]
        start_d = date.fromisoformat(eff_start)
        end_d = date.fromisoformat(eff_end)
        for curr_d in get_regular_trading_sessions(start_d, end_d, exclude_early_close=True):
            rows = df_by_date.get(curr_d, [])
            if rows:
                session_df = pd.DataFrame(rows)
                grid = build_regular_session_grid(curr_d)
                s, r = audit_ticker_session(ticker, curr_d, session_df, grid)
            else:
                s, r = audit_missing_ticker_session(ticker, curr_d)

            all_sessions.append(s)

            # Collect quality report only for target split dates
            if target_dates.start <= curr_d.isoformat() <= target_dates.end:
                target_quality_reports.append(r)

    return all_sessions, target_quality_reports
