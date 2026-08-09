"""Typed dataclasses for the INTRA-001B-DATASET-V1 one-year snapshot build."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def hash_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Return lowercase hex SHA-256 of normalized text."""
    return hash_bytes(text.encode("utf-8"))


def json_hash(obj: Any) -> str:
    """Deterministic SHA-256 hash of a JSON-serializable object."""
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hash_bytes(encoded)


def now_utc_iso() -> str:
    """Current UTC time as ISO string with microseconds."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class PaginationPage:
    """One page of a paginated PIT snapshot."""

    provider: str
    pit_date: str
    state: str
    page_number: int
    row_count: int
    page_sha256: str
    next_url_present: bool
    next_cursor_sha256: str | None
    http_status: int | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pit_date": self.pit_date,
            "state": self.state,
            "page_number": self.page_number,
            "row_count": self.row_count,
            "page_sha256": self.page_sha256,
            "next_url_present": self.next_url_present,
            "next_cursor_sha256": self.next_cursor_sha256,
            "http_status": self.http_status,
            "error": self.error,
        }


@dataclass(frozen=True)
class PITObservation:
    """One point-in-time listing fetch for a single date and state."""

    provider: str
    pit_date: str
    state: str
    requested_at: str
    elapsed_seconds: float
    row_count: int
    raw_sha256: str
    http_status: int | None = None
    error: str | None = None
    page_count: int = 0
    first_page_count: int = 0
    last_page_count: int = 0
    provider_reported_count: int | None = None
    pagination_complete: bool = False
    max_pages_reached: bool = False
    repeated_cursor_detected: bool = False
    cycle_detected: bool = False
    unexpected_next_url: bool = False
    full_snapshot_sha256: str | None = None
    canonical_ticker_count: int = 0
    blank_ticker_count: int = 0
    duplicate_ticker_count: int = 0
    unresolved_duplicate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pit_date": self.pit_date,
            "state": self.state,
            "requested_at": self.requested_at,
            "elapsed_seconds": self.elapsed_seconds,
            "row_count": self.row_count,
            "raw_sha256": self.raw_sha256,
            "http_status": self.http_status,
            "error": self.error,
            "page_count": self.page_count,
            "first_page_count": self.first_page_count,
            "last_page_count": self.last_page_count,
            "provider_reported_count": self.provider_reported_count,
            "pagination_complete": self.pagination_complete,
            "max_pages_reached": self.max_pages_reached,
            "repeated_cursor_detected": self.repeated_cursor_detected,
            "cycle_detected": self.cycle_detected,
            "unexpected_next_url": self.unexpected_next_url,
            "full_snapshot_sha256": self.full_snapshot_sha256,
            "canonical_ticker_count": self.canonical_ticker_count,
            "blank_ticker_count": self.blank_ticker_count,
            "duplicate_ticker_count": self.duplicate_ticker_count,
            "unresolved_duplicate_count": self.unresolved_duplicate_count,
        }


@dataclass(frozen=True)
class ReferenceSnapshot:
    """A completely paginated Massive PIT snapshot plus metadata."""

    pit_date: str
    state: str
    rows: list[dict[str, Any]]
    observations: list[PITObservation]
    pages: list[PaginationPage]
    raw_sha256: str
    canonical_sha256: str
    duplicate_details: list[dict[str, Any]]


@dataclass(frozen=True)
class ExclusionReason:
    """A single ticker exclusion reason."""

    pit_date: str
    effective_month: str
    ticker: str
    reason: str
    provider_type: str
    provider_exchange: str


@dataclass(frozen=True)
class UniverseMember:
    """A single row in the universe manifest."""

    effective_month: str
    pit_date: str
    ticker: str
    stratum: str
    reference_provider: str
    security_type_category: str
    primary_exchange: str
    duplicate_status: str
    prior_close: float | None
    valid_prior_session_count: int
    median_prior_20_dollar_volume: float | None
    liquidity_rank: int | None
    included: bool
    exclusion_reason: str
    source_snapshot_sha256: str
    ohlcv_manifest_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_month": self.effective_month,
            "pit_date": self.pit_date,
            "ticker": self.ticker,
            "stratum": self.stratum,
            "reference_provider": self.reference_provider,
            "security_type_category": self.security_type_category,
            "primary_exchange": self.primary_exchange,
            "duplicate_status": self.duplicate_status,
            "prior_close": self.prior_close,
            "valid_prior_session_count": self.valid_prior_session_count,
            "median_prior_20_dollar_volume": self.median_prior_20_dollar_volume,
            "liquidity_rank": self.liquidity_rank,
            "included": self.included,
            "exclusion_reason": self.exclusion_reason,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "ohlcv_manifest_id": self.ohlcv_manifest_id,
        }


@dataclass(frozen=True)
class OhlcvFile:
    """A normalized OHLCV file stored outside the repository.

    Pre-normalization duplicate and malformed counts are optional because they
    cannot be recovered from already-deduplicated parquet files. When they are
    unavailable they are represented as ``None`` rather than zero.
    """

    manifest_id: str
    symbol: str
    effective_month: str
    feed: str
    timeframe: str
    adjustment: str
    start_utc: str
    end_utc: str
    regular_session_bars: int
    regular_session_sessions: int
    missing_bars: int
    missing_bar_rate_pct: float
    zero_volume_bars: int
    zero_volume_bar_rate_pct: float
    invalid_ohlc_rows: int
    off_grid_bars: int
    premarket_removed: int
    after_hours_removed: int
    early_close_removed: int
    file_size_bytes: int
    sha256: str
    relative_path: str
    requested_symbol: str
    returned_symbol: str
    pagination_complete: bool
    page_count: int
    # Optional pre-normalization observability
    pre_normalization_metrics_available: bool = False
    pre_dedup_duplicate_bars: int | None = None
    duplicate_bars: int | None = None
    duplicate_bar_rate_pct: float | None = None
    malformed_rows: int | None = None
    malformed_row_rate_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "symbol": self.symbol,
            "effective_month": self.effective_month,
            "feed": self.feed,
            "timeframe": self.timeframe,
            "adjustment": self.adjustment,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "regular_session_bars": self.regular_session_bars,
            "regular_session_sessions": self.regular_session_sessions,
            "missing_bars": self.missing_bars,
            "missing_bar_rate_pct": self.missing_bar_rate_pct,
            "zero_volume_bars": self.zero_volume_bars,
            "zero_volume_bar_rate_pct": self.zero_volume_bar_rate_pct,
            "invalid_ohlc_rows": self.invalid_ohlc_rows,
            "off_grid_bars": self.off_grid_bars,
            "premarket_removed": self.premarket_removed,
            "after_hours_removed": self.after_hours_removed,
            "early_close_removed": self.early_close_removed,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "relative_path": self.relative_path,
            "requested_symbol": self.requested_symbol,
            "returned_symbol": self.returned_symbol,
            "pagination_complete": self.pagination_complete,
            "page_count": self.page_count,
            "pre_normalization_metrics_available": self.pre_normalization_metrics_available,
            "pre_dedup_duplicate_bars": self.pre_dedup_duplicate_bars,
            "duplicate_bars": self.duplicate_bars,
            "duplicate_bar_rate_pct": self.duplicate_bar_rate_pct,
            "malformed_rows": self.malformed_rows,
            "malformed_row_rate_pct": self.malformed_row_rate_pct,
        }


@dataclass(frozen=True)
class DataQuality:
    """Data-quality summary for one symbol/month.

    Pre-normalization duplicate and malformed counts are optional because they
    cannot be recovered from already-deduplicated parquet files. When they are
    unavailable they are represented as ``None`` rather than zero.
    """

    symbol: str
    effective_month: str
    split: str
    expected_sessions: int
    actual_sessions: int
    expected_bars: int
    actual_bars: int
    missing_bars: int
    missing_bar_rate_pct: float
    zero_volume_bars: int
    zero_volume_bar_rate_pct: float
    invalid_ohlc_rows: int
    off_grid_bars: int
    premarket_removed: int
    after_hours_removed: int
    early_close_removed: int
    ohlc_consistency_violations: int
    provider_feed: str
    timeframe: str
    adjustment: str
    file_sha256: str
    relative_path: str
    requested_symbol: str
    returned_symbol: str
    symbol_mismatch: bool
    pagination_complete: bool
    rejected: bool
    rejection_reason: str
    # Optional pre-normalization observability
    pre_normalization_metrics_available: bool = False
    pre_dedup_duplicate_bars: int | None = None
    duplicate_bars: int | None = None
    duplicate_bar_rate_pct: float | None = None
    malformed_rows: int | None = None
    malformed_row_rate_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "effective_month": self.effective_month,
            "split": self.split,
            "expected_sessions": self.expected_sessions,
            "actual_sessions": self.actual_sessions,
            "expected_bars": self.expected_bars,
            "actual_bars": self.actual_bars,
            "missing_bars": self.missing_bars,
            "missing_bar_rate_pct": self.missing_bar_rate_pct,
            "zero_volume_bars": self.zero_volume_bars,
            "zero_volume_bar_rate_pct": self.zero_volume_bar_rate_pct,
            "invalid_ohlc_rows": self.invalid_ohlc_rows,
            "off_grid_bars": self.off_grid_bars,
            "premarket_removed": self.premarket_removed,
            "after_hours_removed": self.after_hours_removed,
            "early_close_removed": self.early_close_removed,
            "ohlc_consistency_violations": self.ohlc_consistency_violations,
            "provider_feed": self.provider_feed,
            "timeframe": self.timeframe,
            "adjustment": self.adjustment,
            "file_sha256": self.file_sha256,
            "relative_path": self.relative_path,
            "requested_symbol": self.requested_symbol,
            "returned_symbol": self.returned_symbol,
            "symbol_mismatch": self.symbol_mismatch,
            "pagination_complete": self.pagination_complete,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
            "pre_normalization_metrics_available": self.pre_normalization_metrics_available,
            "pre_dedup_duplicate_bars": self.pre_dedup_duplicate_bars,
            "duplicate_bars": self.duplicate_bars,
            "duplicate_bar_rate_pct": self.duplicate_bar_rate_pct,
            "malformed_rows": self.malformed_rows,
            "malformed_row_rate_pct": self.malformed_row_rate_pct,
        }


@dataclass(frozen=True)
class DatasetDecision:
    """Final dataset disposition."""

    task_id: str
    dataset_id: str
    disposition: str
    reason: str
    starting_main_sha: str
    branch: str
    live_run_head: str
    pre_registration_commit: str
    original_strategy_spec_sha256: str
    amendment_v3_sha256: str
    v4_decision_doc_sha256: str
    alpaca_v2_probe_spec_sha256: str
    monthly_stock_counts: dict[str, int]
    etf_count: int
    unique_selected_stock_count: int
    total_selected_symbol_month_count: int
    dataset_coverage_start: str
    dataset_coverage_end: str
    massive_http_requests: int
    local_storage_bytes: int
    ranking_timeframe: str
    ranking_feed: str
    ranking_timeframe_parity_passed: bool
    ranking_parity_message: str
    parity_fallback_used: bool
    data_quality_disposition: str
    missing_bar_rate_max_pct: float
    zero_volume_rate_max_pct: float
    symbols_rejected_pct: float
    next_assignment: str
    # Optional nullable data-quality maxima (None when pre-normalization metrics are unavailable).
    duplicate_rate_max_pct: float | None = None
    malformed_row_rate_max_pct: float | None = None
    # Optional / derived counters (must follow required fields)
    massive_incomplete_snapshots: int = 0
    alpaca_http_requests: int | None = None
    # Per-phase Alpaca counters are None when the state was produced without
    # detailed request accounting (legacy or recomputed bundles).
    alpaca_ranking_logical_calls: int | None = None
    alpaca_ranking_http_pages: int | None = None
    alpaca_ranking_http_attempts: int | None = None
    alpaca_ranking_http_429s: int | None = None
    alpaca_ranking_http_errors: int | None = None
    alpaca_ohlcv_logical_calls: int | None = None
    alpaca_ohlcv_http_pages: int | None = None
    alpaca_ohlcv_http_attempts: int | None = None
    alpaca_ohlcv_http_429s: int | None = None
    alpaca_ohlcv_http_errors: int | None = None
    http_errors: int = 0
    http_429s: int = 0
    pagination_cycles: int = 0
    incomplete_requests: int = 0
    runtime_seconds: float | None = None
    runtime_note: str = ""
    per_phase_request_counters_available: bool = False
    pre_normalization_metrics_available: bool = False
    production_behavior_changed: bool = False
    no_v5_or_provider_search: bool = True
    ran_at: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "dataset_id": self.dataset_id,
            "disposition": self.disposition,
            "reason": self.reason,
            "starting_main_sha": self.starting_main_sha,
            "branch": self.branch,
            "live_run_head": self.live_run_head,
            "pre_registration_commit": self.pre_registration_commit,
            "original_strategy_spec_sha256": self.original_strategy_spec_sha256,
            "amendment_v3_sha256": self.amendment_v3_sha256,
            "v4_decision_doc_sha256": self.v4_decision_doc_sha256,
            "alpaca_v2_probe_spec_sha256": self.alpaca_v2_probe_spec_sha256,
            "monthly_stock_counts": self.monthly_stock_counts,
            "etf_count": self.etf_count,
            "unique_selected_stock_count": self.unique_selected_stock_count,
            "total_selected_symbol_month_count": self.total_selected_symbol_month_count,
            "dataset_coverage_start": self.dataset_coverage_start,
            "dataset_coverage_end": self.dataset_coverage_end,
            "massive_http_requests": self.massive_http_requests,
            "massive_incomplete_snapshots": self.massive_incomplete_snapshots,
            "alpaca_http_requests": self.alpaca_http_requests,
            "alpaca_ranking_logical_calls": self.alpaca_ranking_logical_calls,
            "alpaca_ranking_http_pages": self.alpaca_ranking_http_pages,
            "alpaca_ranking_http_attempts": self.alpaca_ranking_http_attempts,
            "alpaca_ranking_http_429s": self.alpaca_ranking_http_429s,
            "alpaca_ranking_http_errors": self.alpaca_ranking_http_errors,
            "alpaca_ohlcv_logical_calls": self.alpaca_ohlcv_logical_calls,
            "alpaca_ohlcv_http_pages": self.alpaca_ohlcv_http_pages,
            "alpaca_ohlcv_http_attempts": self.alpaca_ohlcv_http_attempts,
            "alpaca_ohlcv_http_429s": self.alpaca_ohlcv_http_429s,
            "alpaca_ohlcv_http_errors": self.alpaca_ohlcv_http_errors,
            "http_errors": self.http_errors,
            "http_429s": self.http_429s,
            "pagination_cycles": self.pagination_cycles,
            "incomplete_requests": self.incomplete_requests,
            "runtime_seconds": self.runtime_seconds,
            "runtime_note": self.runtime_note,
            "local_storage_bytes": self.local_storage_bytes,
            "ranking_timeframe": self.ranking_timeframe,
            "ranking_feed": self.ranking_feed,
            "ranking_timeframe_parity_passed": self.ranking_timeframe_parity_passed,
            "ranking_parity_message": self.ranking_parity_message,
            "parity_fallback_used": self.parity_fallback_used,
            "data_quality_disposition": self.data_quality_disposition,
            "missing_bar_rate_max_pct": self.missing_bar_rate_max_pct,
            "zero_volume_rate_max_pct": self.zero_volume_rate_max_pct,
            "symbols_rejected_pct": self.symbols_rejected_pct,
            "next_assignment": self.next_assignment,
            "duplicate_rate_max_pct": self.duplicate_rate_max_pct,
            "malformed_row_rate_max_pct": self.malformed_row_rate_max_pct,
            "per_phase_request_counters_available": self.per_phase_request_counters_available,
            "pre_normalization_metrics_available": self.pre_normalization_metrics_available,
            "production_behavior_changed": self.production_behavior_changed,
            "no_v5_or_provider_search": self.no_v5_or_provider_search,
            "ran_at": self.ran_at,
        }


@dataclass
class DatasetState:
    """Mutable pipeline state persisted to checkpoint JSON."""

    phase: str = "init"
    pit_dates_completed: list[str] = field(default_factory=list)
    universe_built_for_months: list[str] = field(default_factory=list)
    ohlcv_fetched_for_months: list[str] = field(default_factory=list)
    validated: bool = False
    finalized: bool = False
    errors: list[str] = field(default_factory=list)
    # Legacy aggregate counters (kept for backward compatibility)
    massive_request_count: int = 0
    alpaca_request_count: int = 0
    http_error_count: int = 0
    http_429_count: int = 0
    pagination_cycles: int = 0
    incomplete_requests: int = 0
    # Detailed Alpaca request accounting
    alpaca_ranking_logical_calls: int = 0
    alpaca_ranking_http_pages: int = 0
    alpaca_ranking_http_attempts: int = 0
    alpaca_ranking_http_429s: int = 0
    alpaca_ranking_http_errors: int = 0
    alpaca_ohlcv_logical_calls: int = 0
    alpaca_ohlcv_http_pages: int = 0
    alpaca_ohlcv_http_attempts: int = 0
    alpaca_ohlcv_http_429s: int = 0
    alpaca_ohlcv_http_errors: int = 0
    # Runtime and per-request logs
    phase_start_times: dict[str, str] = field(default_factory=dict)
    phase_end_times: dict[str, str] = field(default_factory=dict)
    runtime_seconds: float | None = None
    request_audit_rows: list[dict[str, Any]] = field(default_factory=list)
    # Availability flags for legacy/recomputed states
    per_phase_request_counters_available: bool = False
    pre_normalization_metrics_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "pit_dates_completed": self.pit_dates_completed,
            "universe_built_for_months": self.universe_built_for_months,
            "ohlcv_fetched_for_months": self.ohlcv_fetched_for_months,
            "validated": self.validated,
            "finalized": self.finalized,
            "errors": self.errors,
            "massive_request_count": self.massive_request_count,
            "alpaca_request_count": self.alpaca_request_count,
            "http_error_count": self.http_error_count,
            "http_429_count": self.http_429_count,
            "pagination_cycles": self.pagination_cycles,
            "incomplete_requests": self.incomplete_requests,
            "alpaca_ranking_logical_calls": self.alpaca_ranking_logical_calls,
            "alpaca_ranking_http_pages": self.alpaca_ranking_http_pages,
            "alpaca_ranking_http_attempts": self.alpaca_ranking_http_attempts,
            "alpaca_ranking_http_429s": self.alpaca_ranking_http_429s,
            "alpaca_ranking_http_errors": self.alpaca_ranking_http_errors,
            "alpaca_ohlcv_logical_calls": self.alpaca_ohlcv_logical_calls,
            "alpaca_ohlcv_http_pages": self.alpaca_ohlcv_http_pages,
            "alpaca_ohlcv_http_attempts": self.alpaca_ohlcv_http_attempts,
            "alpaca_ohlcv_http_429s": self.alpaca_ohlcv_http_429s,
            "alpaca_ohlcv_http_errors": self.alpaca_ohlcv_http_errors,
            "phase_start_times": self.phase_start_times,
            "phase_end_times": self.phase_end_times,
            "runtime_seconds": self.runtime_seconds,
            "request_audit_rows": self.request_audit_rows,
            "per_phase_request_counters_available": self.per_phase_request_counters_available,
            "pre_normalization_metrics_available": self.pre_normalization_metrics_available,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetState:
        return cls(
            phase=data.get("phase", "init"),
            pit_dates_completed=list(data.get("pit_dates_completed", [])),
            universe_built_for_months=list(data.get("universe_built_for_months", [])),
            ohlcv_fetched_for_months=list(data.get("ohlcv_fetched_for_months", [])),
            validated=bool(data.get("validated", False)),
            finalized=bool(data.get("finalized", False)),
            errors=list(data.get("errors", [])),
            massive_request_count=int(data.get("massive_request_count", 0)),
            alpaca_request_count=int(data.get("alpaca_request_count", 0)),
            http_error_count=int(data.get("http_error_count", 0)),
            http_429_count=int(data.get("http_429_count", 0)),
            pagination_cycles=int(data.get("pagination_cycles", 0)),
            incomplete_requests=int(data.get("incomplete_requests", 0)),
            alpaca_ranking_logical_calls=int(data.get("alpaca_ranking_logical_calls", 0)),
            alpaca_ranking_http_pages=int(data.get("alpaca_ranking_http_pages", 0)),
            alpaca_ranking_http_attempts=int(data.get("alpaca_ranking_http_attempts", 0)),
            alpaca_ranking_http_429s=int(data.get("alpaca_ranking_http_429s", 0)),
            alpaca_ranking_http_errors=int(data.get("alpaca_ranking_http_errors", 0)),
            alpaca_ohlcv_logical_calls=int(data.get("alpaca_ohlcv_logical_calls", 0)),
            alpaca_ohlcv_http_pages=int(data.get("alpaca_ohlcv_http_pages", 0)),
            alpaca_ohlcv_http_attempts=int(data.get("alpaca_ohlcv_http_attempts", 0)),
            alpaca_ohlcv_http_429s=int(data.get("alpaca_ohlcv_http_429s", 0)),
            alpaca_ohlcv_http_errors=int(data.get("alpaca_ohlcv_http_errors", 0)),
            phase_start_times=dict(data.get("phase_start_times", {})),
            phase_end_times=dict(data.get("phase_end_times", {})),
            runtime_seconds=data.get("runtime_seconds"),
            request_audit_rows=list(data.get("request_audit_rows", [])),
            per_phase_request_counters_available=bool(data.get("per_phase_request_counters_available", False)),
            pre_normalization_metrics_available=bool(data.get("pre_normalization_metrics_available", False)),
        )
