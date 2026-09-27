"""Dataset manifest contract, security bounds, and bounded Alpaca acquisition adapter."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

from .calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from .models import DataQualityReport, DaytradeSession, HoldoutAccessDeniedError
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


def sanitize_manifest_dict(d: Any) -> Any:
    """Recursively strip any keys or values containing forbidden credential tokens."""
    if isinstance(d, dict):
        sanitized: dict[str, Any] = {}
        for k, v in d.items():
            k_lower = str(k).lower()
            if any(p in k_lower for p in FORBIDDEN_KEY_PATTERNS) and k_lower not in SAFE_KEY_ALLOWLIST:
                continue
            sanitized[k] = sanitize_manifest_dict(v)
        return sanitized
    elif isinstance(d, (list, tuple)):
        return [sanitize_manifest_dict(x) for x in d]
    return d


@dataclass
class DaytradeDatasetManifest:
    """Cryptographic manifest documenting acquired partition data and provenance."""

    task_id: str
    spec_sha256: str
    partition: str  # 'preholdout' or 'holdout'
    provider: str
    feed: str
    timeframe: str
    adjustment: str
    calendar: str
    timezone: str
    universe: tuple[str, ...]
    start_date: str
    end_date: str
    source_files: dict[str, str]  # rel_path -> sha256
    manifest_sha256: str = ""
    acquisition_provenance: dict[str, Any] = field(default_factory=dict)
    preholdout_manifest_sha256: str | None = None
    validation_bundle_sha256: str | None = None
    evaluator_code_sha: str | None = None

    def compute_sha256(self) -> str:
        """Compute deterministic manifest SHA-256 over all fields except manifest_sha256."""
        payload = {
            "task_id": self.task_id,
            "spec_sha256": self.spec_sha256,
            "partition": self.partition,
            "provider": self.provider,
            "feed": self.feed,
            "timeframe": self.timeframe,
            "adjustment": self.adjustment,
            "calendar": self.calendar,
            "timezone": self.timezone,
            "universe": list(self.universe),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source_files": dict(sorted(self.source_files.items())),
            "acquisition_provenance": sanitize_manifest_dict(self.acquisition_provenance),
            "preholdout_manifest_sha256": self.preholdout_manifest_sha256,
            "validation_bundle_sha256": self.validation_bundle_sha256,
            "evaluator_code_sha": self.evaluator_code_sha,
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to sanitized dictionary."""
        d = asdict(self)
        d["manifest_sha256"] = self.manifest_sha256 or self.compute_sha256()
        return sanitize_manifest_dict(d)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaytradeDatasetManifest:
        """Construct manifest from dictionary."""
        d = dict(data)
        d["universe"] = tuple(d.get("universe", []))
        return cls(**d)


def verify_dataset_manifest(
    manifest: DaytradeDatasetManifest,
    spec: DaytradeSpec,
    dataset_root: Path,
) -> None:
    """Verify that dataset manifest adheres to locked contract and files match digests."""
    if manifest.task_id != "DAYTRADE-002B":
        raise DatasetSecurityError(f"Unexpected task_id in manifest: {manifest.task_id}")
    if manifest.spec_sha256 != DAYTRADE_002A_SPEC_SHA256:
        raise DatasetSecurityError(
            f"Manifest spec SHA mismatch: expected {DAYTRADE_002A_SPEC_SHA256}, got {manifest.spec_sha256}"
        )
    if manifest.provider != LOCKED_PROVIDER:
        raise DatasetSecurityError(f"Provider mismatch: expected {LOCKED_PROVIDER}, got {manifest.provider}")
    if manifest.feed != LOCKED_FEED:
        raise DatasetSecurityError(f"Feed mismatch: expected {LOCKED_FEED}, got {manifest.feed}")
    if manifest.timeframe != LOCKED_TIMEFRAME:
        raise DatasetSecurityError(f"Timeframe mismatch: expected {LOCKED_TIMEFRAME}, got {manifest.timeframe}")
    if manifest.adjustment != LOCKED_ADJUSTMENT:
        raise DatasetSecurityError(f"Adjustment mismatch: expected {LOCKED_ADJUSTMENT}, got {manifest.adjustment}")
    if manifest.calendar != LOCKED_CALENDAR:
        raise DatasetSecurityError(f"Calendar mismatch: expected {LOCKED_CALENDAR}, got {manifest.calendar}")
    if manifest.timezone != LOCKED_TIMEZONE:
        raise DatasetSecurityError(f"Timezone mismatch: expected {LOCKED_TIMEZONE}, got {manifest.timezone}")
    if manifest.universe != LOCKED_FROZEN_UNIVERSE:
        raise DatasetSecurityError(
            f"Manifest universe mismatch: expected {LOCKED_FROZEN_UNIVERSE}, got {manifest.universe}"
        )

    # Verify per-file SHA-256
    for rel_path, expected_hash in manifest.source_files.items():
        fp = dataset_root / rel_path
        if not fp.is_file():
            raise DatasetSecurityError(f"Manifest source file not found: {fp}")
        actual_hash = sha256_of_file(fp)
        if actual_hash != expected_hash:
            raise DatasetSecurityError(
                f"File SHA-256 mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
            )

    computed_sha = manifest.compute_sha256()
    if manifest.manifest_sha256 and manifest.manifest_sha256 != computed_sha:
        raise DatasetSecurityError(
            f"Manifest internal SHA mismatch: recorded {manifest.manifest_sha256} vs computed {computed_sha}"
        )


def acquire_dataset_partition(
    dataset_root: Path | str,
    partition: str,
    spec: DaytradeSpec,
    *,
    client: Any = None,
    execute_provider: bool = False,
    repo_root: Path | None = None,
    validation_bundle_sha: str | None = None,
    preholdout_manifest_sha: str | None = None,
    evaluator_code_sha: str | None = None,
    validation_artifact_dir: Path | str | None = None,
) -> DaytradeDatasetManifest:
    """Future authorized dataset acquisition path with strict authorization guards.

    Locked guards:
    - Fails closed unless execute_provider is explicitly True;
    - Dataset root must reside outside the repository;
    - If holdout partition: requires validation_bundle_sha, preholdout_manifest_sha, evaluator_code_sha (or valid validation_artifact_dir);
    - Reuses DatasetAlpacaClient with monthly chunking and bounded pagination.
    """
    valid_root = validate_dataset_root(dataset_root, repo_root=repo_root)

    if partition not in ("preholdout", "holdout"):
        raise ValueError(f"Partition must be 'preholdout' or 'holdout', got: {partition}")

    if partition == "preholdout":
        start_date = spec.context_anchor_date  # 2025-12-31
        end_date = spec.validation.end          # 2026-06-30
    else:
        start_date = spec.holdout.start         # 2026-07-01
        end_date = spec.holdout.end             # 2026-08-31
        if validation_artifact_dir is not None:
            from .study import verify_holdout_access_prerequisites
            verify_holdout_access_prerequisites(validation_artifact_dir, spec, repo_root=repo_root)
        elif not (validation_bundle_sha and preholdout_manifest_sha and evaluator_code_sha):
            raise HoldoutAccessDeniedError(
                "Holdout acquisition strictly requires verified validation_bundle_sha, preholdout_manifest_sha, and evaluator_code_sha (or valid validation_artifact_dir)."
            )

    if not execute_provider:
        # Dry-run or planning mode: zero network requests
        manifest = DaytradeDatasetManifest(
            task_id="DAYTRADE-002B",
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
                "pages_retrieved": 0,
                "rows_retrieved": 0,
            },
            preholdout_manifest_sha256=preholdout_manifest_sha,
            validation_bundle_sha256=validation_bundle_sha,
            evaluator_code_sha=evaluator_code_sha,
        )
        manifest.manifest_sha256 = manifest.compute_sha256()
        manifest_fp = valid_root / f"manifest_{partition}.json"
        manifest_fp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return manifest

    # Authorized provider execution path (requires explicit client or credentials)
    alpaca_client = client or DatasetAlpacaClient()
    partition_dir = valid_root / partition
    partition_dir.mkdir(parents=True, exist_ok=True)

    source_files: dict[str, str] = {}
    provenance_stats = {
        "requests": 0,
        "pages": 0,
        "retries": 0,
        "errors": 0,
        "status": "authorized_provider_acquisition",
    }

    # Acquire each ETF's 1Min bars
    for sym in spec.universe:
        rel_fn = f"{partition}/{sym}.csv"
        out_fp = valid_root / rel_fn

        # Bounded fetch using client
        df = alpaca_client.fetch_bars(
            symbol=sym,
            timeframe=LOCKED_TIMEFRAME,
            start=start_date,
            end=end_date,
            feed=LOCKED_FEED,
            adjustment=LOCKED_ADJUSTMENT,
        )
        provenance_stats["requests"] += 1
        provenance_stats["pages"] += getattr(alpaca_client, "last_page_count", 1)

        # Write CSV
        df.to_csv(out_fp, index=False)
        source_files[rel_fn] = sha256_of_file(out_fp)

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
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

    manifest_fp = valid_root / f"manifest_{partition}.json"
    manifest_fp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    return manifest


acquire_partition_data = acquire_dataset_partition


def load_private_dataset(
    dataset_root: Path | str,
    spec: DaytradeSpec,
    split_name: str,
    include_history: bool = True,
    repo_root: Path | None = None,
) -> tuple[dict[str, list[DaytradeSession]], list[DataQualityReport]]:
    """Load and audit private dataset for a target evaluation split.

    Returns:
        (sessions_by_ticker, quality_reports)
    """
    valid_root = validate_dataset_root(dataset_root, repo_root=repo_root)

    # Determine date span to load
    split_dates = spec.get_split_dates(split_name)
    target_start = split_dates.start
    target_end = split_dates.end

    if include_history:
        # Load preceding history sessions needed to build rolling thresholds
        hist_dates = spec.get_history_dates(split_name)
        if hist_dates:
            load_start = hist_dates[0]
        else:
            load_start = spec.context_anchor_date
    else:
        load_start = target_start

    # Determine which partition to look in
    partition = "holdout" if split_name == "holdout" else "preholdout"
    part_dir = valid_root / partition
    if not part_dir.is_dir():
        # Fall back to checking directly in valid_root if files are stored flat
        part_dir = valid_root

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    quality_reports: list[DataQualityReport] = []

    # Get expected trading sessions in load range
    expected_sessions = get_regular_trading_sessions(load_start, target_end, exclude_early_closes=True)

    for sym in spec.universe:
        csv_file = part_dir / f"{sym}.csv"
        if not csv_file.is_file():
            # Ticker missing entirely: record missing reports
            ticker_sessions: list[DaytradeSession] = []
            for s_date in expected_sessions:
                sess, rep = audit_missing_ticker_session(sym, s_date)
                ticker_sessions.append(sess)
                quality_reports.append(rep)
            sessions_by_ticker[sym] = ticker_sessions
            continue

        df = pd.read_csv(csv_file)
        # Parse datetime column
        ts_col = "datetime" if "datetime" in df.columns else ("timestamp" if "timestamp" in df.columns else "t")
        df["dt_parsed"] = pd.to_datetime(df[ts_col], utc=True)
        df["session_date"] = df["dt_parsed"].dt.tz_convert(LOCKED_TIMEZONE).dt.date

        # Group by session_date
        by_session = {d: group for d, group in df.groupby("session_date")}

        ticker_sessions = []
        for s_date in expected_sessions:
            grid = build_regular_session_grid(s_date)
            sess_df = by_session.get(s_date)
            if sess_df is None or len(sess_df) == 0:
                sess, rep = audit_missing_ticker_session(sym, s_date)
            else:
                sess, rep = audit_ticker_session(sym, s_date, sess_df, grid)
            ticker_sessions.append(sess)
            quality_reports.append(rep)

        sessions_by_ticker[sym] = ticker_sessions

    return sessions_by_ticker, quality_reports
