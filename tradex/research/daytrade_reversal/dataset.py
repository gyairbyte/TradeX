"""Dataset manifest contract, security bounds, and future Alpaca acquisition adapter."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient
from tradex.watchlists.presets import DOW30

LOCKED_PROVIDER = "alpaca"
LOCKED_FEED = "sip"
LOCKED_TIMEFRAME = "1Min"
LOCKED_ADJUSTMENT = "split"
LOCKED_CALENDAR = "XNYS"
LOCKED_TIMEZONE = "America/New_York"
MAX_RETRIES_PER_FAILED_PAGE = 1
MAX_PAGES_PER_CALENDAR_MONTH_CHUNK = 100

FORBIDDEN_SECRET_KEYS = (
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "APCA-API-KEY-ID",
    "APCA-API-SECRET-KEY",
    "Bearer",
    "secret",
    "token",
)


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


def sanitize_manifest_data(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure no API keys, secrets, auth headers, or raw bodies exist in manifest data."""
    text = json.dumps(data)
    for forbidden in ("APCA-API-KEY-ID", "APCA-API-SECRET-KEY"):
        if forbidden in text:
            raise DatasetSecurityError(f"Prohibited header/key found in manifest: {forbidden}")

    # Inspect environment variable values if set
    for env_var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        val = os.environ.get(env_var)
        if val and len(val) >= 8 and val in text:
            raise DatasetSecurityError(f"Prohibited credential value from {env_var} found in manifest payload")

    return data


@dataclass
class DaytradeDatasetManifest:
    """Normative private-dataset manifest contract for DAYTRADE-001."""

    study_id: str
    spec_sha256: str
    provider: str = LOCKED_PROVIDER
    feed: str = LOCKED_FEED
    timeframe: str = LOCKED_TIMEFRAME
    adjustment: str = LOCKED_ADJUSTMENT
    session_calendar: str = LOCKED_CALENDAR
    timezone: str = LOCKED_TIMEZONE
    universe: list[str] = field(default_factory=lambda: list(DOW30))
    start_date: str = "2024-12-02"
    end_date: str = "2025-12-31"
    request_count: int = 0
    http_page_count: int = 0
    retry_count: int = 0
    safe_error_classifications: dict[str, int] = field(default_factory=dict)
    symbol_date_coverage: dict[str, list[str]] = field(default_factory=dict)
    malformed_timestamp_counts: dict[str, int] = field(default_factory=dict)
    missing_bar_counts: dict[str, int] = field(default_factory=dict)
    duplicate_bar_counts: dict[str, int] = field(default_factory=dict)
    excluded_ticker_sessions: list[dict[str, Any]] = field(default_factory=list)
    source_files: dict[str, str] = field(default_factory=dict)
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


class DaytradeDatasetAcquisitionAdapter:
    """Future data acquisition adapter reusing DatasetAlpacaClient with hard locked bounds.

    Note: DAYTRADE-001C1 makes 0 real network calls. This adapter enforces the contract
    and hard safety limits for future C2 execution.
    """

    def __init__(
        self,
        alpaca_client: DatasetAlpacaClient,
        dataset_root: Path,
    ) -> None:
        self.client = alpaca_client
        self.dataset_root = validate_dataset_root(dataset_root)

    def fetch_month_chunk(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch multi-symbol bars for one calendar-month chunk with locked 100-page limit.

        Fails closed if pagination exceeds 100 pages.
        """
        # Reuses existing DatasetAlpacaClient
        dfs, meta = self.client.get_bars(
            symbols=symbols,
            start_utc=start_utc,
            end_utc=end_utc,
            feed=LOCKED_FEED,
            timeframe=LOCKED_TIMEFRAME,
            adjustment=LOCKED_ADJUSTMENT,
        )

        page_count = meta.get("page_count", 0)
        if page_count > MAX_PAGES_PER_CALENDAR_MONTH_CHUNK:
            raise DatasetPaginationLimitError(
                f"Page count {page_count} exceeded locked hard limit of "
                f"{MAX_PAGES_PER_CALENDAR_MONTH_CHUNK} pages per month chunk."
            )

        return dfs, meta
