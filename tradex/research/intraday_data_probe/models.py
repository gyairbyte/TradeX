"""Dataclasses and value objects for the INTRA-001B probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProbeRequestRecord:
    """One executed request/repetition row."""

    probe_id: str
    symbol: str
    method: str
    repetition: int
    requested_eastern_start: str
    requested_eastern_end: str
    requested_utc_start: str
    requested_utc_end: str
    http_status: int
    safe_error_classification: str
    raw_candle_count: int
    normalized_candle_count: int
    raw_earliest_timestamp: str | None
    raw_latest_timestamp: str | None
    requested_range_earliest: str | None
    requested_range_latest: str | None
    out_of_range_candles: int
    unique_regular_sessions: int
    expected_eligible_sessions: int
    expected_regular_session_bars: int
    returned_regular_session_bars: int
    primary_session_bars: int
    early_close_session_bars: int
    extended_hours_bars: int
    regular_session_coverage_pct: float
    missing_regular_session_bars: int
    duplicate_timestamps: int
    duplicate_bar_rate_pct: float
    zero_volume_bars: int
    zero_volume_rate_pct: float
    invalid_ohlc_rows: int
    non_five_minute_intervals: int
    candle_payload_sha256: str
    requested_range_normalized_sha256: str
    date_bound_classification: str
    timestamp_semantics_classification: str
    threshold_result: str
    retry_after_seconds: float | None = None
    notes: str = ""
    # Pagination and retry diagnostics (added for Alpaca probe)
    page_count: int = 1
    next_page_token_present: bool = False
    pagination_complete: bool = False
    repeated_page_token: bool = False
    pagination_cycle_detected: bool = False
    page_bar_counts: tuple[int, ...] = ()
    token_sequence_sha256: str = ""
    # v2: quality metrics restricted to the eligible regular-session expected grid
    regular_session_zero_volume_bars: int = 0
    regular_session_zero_volume_rate_pct: float = 0.0
    regular_session_invalid_ohlc_rows: int = 0
    regular_session_duplicate_timestamps: int = 0
    regular_session_duplicate_bar_rate_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "symbol": self.symbol,
            "method": self.method,
            "repetition": self.repetition,
            "requested_eastern_start": self.requested_eastern_start,
            "requested_eastern_end": self.requested_eastern_end,
            "requested_utc_start": self.requested_utc_start,
            "requested_utc_end": self.requested_utc_end,
            "http_status": self.http_status,
            "safe_error_classification": self.safe_error_classification,
            "raw_candle_count": self.raw_candle_count,
            "normalized_candle_count": self.normalized_candle_count,
            "raw_earliest_timestamp": self.raw_earliest_timestamp,
            "raw_latest_timestamp": self.raw_latest_timestamp,
            "requested_range_earliest": self.requested_range_earliest,
            "requested_range_latest": self.requested_range_latest,
            "out_of_range_candles": self.out_of_range_candles,
            "unique_regular_sessions": self.unique_regular_sessions,
            "expected_eligible_sessions": self.expected_eligible_sessions,
            "expected_regular_session_bars": self.expected_regular_session_bars,
            "returned_regular_session_bars": self.returned_regular_session_bars,
            "primary_session_bars": self.primary_session_bars,
            "early_close_session_bars": self.early_close_session_bars,
            "extended_hours_bars": self.extended_hours_bars,
            "regular_session_coverage_pct": self.regular_session_coverage_pct,
            "missing_regular_session_bars": self.missing_regular_session_bars,
            "duplicate_timestamps": self.duplicate_timestamps,
            "duplicate_bar_rate_pct": self.duplicate_bar_rate_pct,
            "zero_volume_bars": self.zero_volume_bars,
            "zero_volume_rate_pct": self.zero_volume_rate_pct,
            "invalid_ohlc_rows": self.invalid_ohlc_rows,
            "non_five_minute_intervals": self.non_five_minute_intervals,
            "candle_payload_sha256": self.candle_payload_sha256,
            "requested_range_normalized_sha256": self.requested_range_normalized_sha256,
            "date_bound_classification": self.date_bound_classification,
            "timestamp_semantics_classification": self.timestamp_semantics_classification,
            "threshold_result": self.threshold_result,
            "retry_after_seconds": self.retry_after_seconds,
            "notes": self.notes,
            "page_count": self.page_count,
            "next_page_token_present": self.next_page_token_present,
            "pagination_complete": self.pagination_complete,
            "repeated_page_token": self.repeated_page_token,
            "pagination_cycle_detected": self.pagination_cycle_detected,
            "page_bar_counts": list(self.page_bar_counts),
            "token_sequence_sha256": self.token_sequence_sha256,
            "regular_session_zero_volume_bars": self.regular_session_zero_volume_bars,
            "regular_session_zero_volume_rate_pct": self.regular_session_zero_volume_rate_pct,
            "regular_session_invalid_ohlc_rows": self.regular_session_invalid_ohlc_rows,
            "regular_session_duplicate_timestamps": self.regular_session_duplicate_timestamps,
            "regular_session_duplicate_bar_rate_pct": self.regular_session_duplicate_bar_rate_pct,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeRequestRecord:
        filtered = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "page_bar_counts" in filtered and isinstance(filtered["page_bar_counts"], list):
            filtered["page_bar_counts"] = tuple(filtered["page_bar_counts"])
        return cls(**filtered)


@dataclass
class ProbeDecision:
    """Machine-readable provider decision."""

    task_id: str
    outcome: str
    provider: str
    schwab_py_version: str
    strategy_spec_sha256: str
    probe_spec_sha256: str
    pre_registration_commit: str
    direct_full_range_supported: bool
    chunked_historical_windows_supported: bool
    selected_request_method: str
    selected_windowing_policy: str
    approved_for_intra_001_five_minute_ohlcv: bool
    approved_as_complete_intra_001_data_source: bool
    date_filtering_required: bool
    timestamp_semantics: str
    timestamp_normalization_required: bool
    repeatability_passed: bool
    chunk_overlap_passed: bool
    coverage_threshold_passed: bool
    method_parity_applicable: bool = True
    method_parity_passed: bool | None = None
    remaining_universe_source_required: bool = True
    remaining_security_master_required: bool = True
    remaining_delisted_symbol_support_required: bool = True
    remaining_volume_provenance_disclosure_required: bool = True
    blockers: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    recommended_next_assignment: str = ""
    production_behavior_changed: bool = False
    # v2 provenance and schema fields
    probe_version: int = 2
    target_entitlement: str = ""
    v1_pre_registration_commit: str = ""
    v2_pre_registration_commit: str = ""
    client_version: str = ""
    # Alpaca-specific decision fields
    alpaca_client_or_rest_version: str = ""
    candidate_feed: str = ""
    comparison_feed: str = ""
    selected_feed: str = ""
    consolidated_volume_supported: bool = False
    iex_historical_available: bool = False
    point_in_time_universe_supported: bool = False
    historical_security_type_supported: bool = False
    stock_etf_classification_supported: bool = False
    inactive_asset_listing_supported: bool = False
    delisted_symbol_handling_supported: bool = False
    corporate_action_endpoint_supported: bool = False
    symbol_mapping_asof_supported: bool = False
    no_provider_mixing_contract_satisfied: bool | None = None
    excluded_security_types_supported: bool = False
    # v2 audit/contract fields
    candidate_timestamp_semantics: str = ""
    timestamp_semantics_passed: bool = False
    pagination_verified: bool = False
    pagination_repeatability_passed: bool = False
    candidate_zero_volume_threshold_passed: bool = False
    candidate_invalid_ohlc_threshold_passed: bool = False
    candidate_duplicate_threshold_passed: bool = False
    volume_provenance_disclosure_complete: bool = False
    monthly_pit_membership_reproducible: bool = False
    corporate_action_historical_completeness_supported: bool = False
    current_inactive_asset_master_supported: bool = False
    probe_did_not_mix_providers: bool = True
    single_provider_contract_satisfied: bool = False
    methodology_decision_required: bool = False
    methodology_decision_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "task_id": self.task_id,
            "outcome": self.outcome,
            "provider": self.provider,
            "schwab_py_version": self.schwab_py_version,
            "strategy_spec_sha256": self.strategy_spec_sha256,
            "probe_spec_sha256": self.probe_spec_sha256,
            "pre_registration_commit": self.pre_registration_commit,
            "direct_full_range_supported": self.direct_full_range_supported,
            "chunked_historical_windows_supported": self.chunked_historical_windows_supported,
            "selected_request_method": self.selected_request_method,
            "selected_windowing_policy": self.selected_windowing_policy,
            "approved_for_intra_001_five_minute_ohlcv": self.approved_for_intra_001_five_minute_ohlcv,
            "approved_as_complete_intra_001_data_source": self.approved_as_complete_intra_001_data_source,
            "date_filtering_required": self.date_filtering_required,
            "timestamp_semantics": self.timestamp_semantics,
            "timestamp_normalization_required": self.timestamp_normalization_required,
            "repeatability_passed": self.repeatability_passed,
            "method_parity_applicable": self.method_parity_applicable,
            "method_parity_passed": self.method_parity_passed,
            "chunk_overlap_passed": self.chunk_overlap_passed,
            "coverage_threshold_passed": self.coverage_threshold_passed,
            "remaining_universe_source_required": self.remaining_universe_source_required,
            "remaining_security_master_required": self.remaining_security_master_required,
            "remaining_delisted_symbol_support_required": self.remaining_delisted_symbol_support_required,
            "remaining_volume_provenance_disclosure_required": self.remaining_volume_provenance_disclosure_required,
            "blockers": self.blockers,
            "limitations": self.limitations,
            "recommended_next_assignment": self.recommended_next_assignment,
            "production_behavior_changed": self.production_behavior_changed,
            "alpaca_client_or_rest_version": self.alpaca_client_or_rest_version,
            "candidate_feed": self.candidate_feed,
            "comparison_feed": self.comparison_feed,
            "selected_feed": self.selected_feed,
            "pagination_verified": self.pagination_verified,
            "consolidated_volume_supported": self.consolidated_volume_supported,
            "iex_historical_available": self.iex_historical_available,
            "point_in_time_universe_supported": self.point_in_time_universe_supported,
            "historical_security_type_supported": self.historical_security_type_supported,
            "stock_etf_classification_supported": self.stock_etf_classification_supported,
            "inactive_asset_listing_supported": self.inactive_asset_listing_supported,
            "delisted_symbol_handling_supported": self.delisted_symbol_handling_supported,
            "corporate_action_endpoint_supported": self.corporate_action_endpoint_supported,
            "symbol_mapping_asof_supported": self.symbol_mapping_asof_supported,
            "no_provider_mixing_contract_satisfied": self.no_provider_mixing_contract_satisfied,
            "excluded_security_types_supported": self.excluded_security_types_supported,
            "probe_version": self.probe_version,
            "target_entitlement": self.target_entitlement,
            "v1_pre_registration_commit": self.v1_pre_registration_commit,
            "v2_pre_registration_commit": self.v2_pre_registration_commit,
            "client_version": self.client_version,
            "candidate_timestamp_semantics": self.candidate_timestamp_semantics,
            "timestamp_semantics_passed": self.timestamp_semantics_passed,
            "pagination_repeatability_passed": self.pagination_repeatability_passed,
            "candidate_zero_volume_threshold_passed": self.candidate_zero_volume_threshold_passed,
            "candidate_invalid_ohlc_threshold_passed": self.candidate_invalid_ohlc_threshold_passed,
            "candidate_duplicate_threshold_passed": self.candidate_duplicate_threshold_passed,
            "volume_provenance_disclosure_complete": self.volume_provenance_disclosure_complete,
            "monthly_pit_membership_reproducible": self.monthly_pit_membership_reproducible,
            "corporate_action_historical_completeness_supported": self.corporate_action_historical_completeness_supported,
            "current_inactive_asset_master_supported": self.current_inactive_asset_master_supported,
            "probe_did_not_mix_providers": self.probe_did_not_mix_providers,
            "single_provider_contract_satisfied": self.single_provider_contract_satisfied,
            "methodology_decision_required": self.methodology_decision_required,
            "methodology_decision_reason": self.methodology_decision_reason,
        }
        # For v2 the legacy field is intentionally deprecated in favor of
        # ``probe_did_not_mix_providers`` and ``single_provider_contract_satisfied``.
        if self.probe_version == 2:
            data.pop("no_provider_mixing_contract_satisfied", None)
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeDecision:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProbeReport:
    """Aggregate container for all probe results."""

    records: list[ProbeRequestRecord]
    decision: ProbeDecision
    method_parity_rows: list[dict[str, Any]]
    repeatability_rows: list[dict[str, Any]]
    chunk_overlap_rows: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]
    feed_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    provider_contract_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "decision": self.decision.to_dict(),
            "method_parity": self.method_parity_rows,
            "repeatability": self.repeatability_rows,
            "chunk_overlap": self.chunk_overlap_rows,
            "summary": self.summary_rows,
            "feed_comparison": self.feed_comparison_rows,
            "provider_contract": self.provider_contract_rows,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeReport:
        return cls(
            records=[ProbeRequestRecord.from_dict(r) for r in d["records"]],
            decision=ProbeDecision.from_dict(d["decision"]),
            method_parity_rows=d.get("method_parity", []),
            repeatability_rows=d.get("repeatability", []),
            chunk_overlap_rows=d.get("chunk_overlap", []),
            summary_rows=d.get("summary", []),
            feed_comparison_rows=d.get("feed_comparison", []),
            provider_contract_rows=d.get("provider_contract", []),
        )
