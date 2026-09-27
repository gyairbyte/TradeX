"""Data models for LONG-002C relational entities.

Implements all 11 locked entities defined in docs/research/specs/LONG-002C-design-v1.json.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DecisionObservation:
    """Point-in-time snapshot evaluation for each (security, date, cutoff)."""

    immutable_security_id: str
    ticker_at_decision: str
    as_of_date: str
    cutoff_time: str
    decision_timestamp_utc: str
    as_traded_close: float
    split_normalized_close: float
    volume: int
    immutable_issuer_id: str | None = None
    dollar_volume_20d_median: float | None = None
    atr_14: float | None = None
    raw_outcome_eligible: bool = False
    universe_eligible: bool = False
    data_complete: bool = False
    earnings_schedule_status: str = "unknown"  # "known" | "unknown"
    actionability_status: str = "unavailable_earnings_unknown"  # "eligible" | "unavailable_earnings_unknown" | "unavailable_data_incomplete" | "excluded"
    split_boundary_purged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataEligibility:
    """Evaluation of universal filtering gates at decision time."""

    immutable_security_id: str
    ticker_at_decision: str
    as_of_date: str
    cutoff_time: str
    price_gte_5: bool
    dollar_volume_20d_gte_20m: bool
    trading_history_sessions: int
    cohort_type: str  # "established" | "recent_ipo" | "insufficient_history" | "unverified_history_truncated"
    eligibility_passed: bool
    rejection_reason_codes: list[str] = field(default_factory=list)
    dollar_volume_60d_gte_10m: bool | None = None
    market_cap: float | None = None
    market_cap_gte_3b: bool | None = None
    index_membership_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SecurityClassificationStatus:
    """Point-in-time security classification and exclusion evaluation."""

    immutable_security_id: str
    as_of_date: str
    ticker_at_decision: str
    inferred_classification: str  # "common_stock" | "etf" | "etn" | "closed_end_fund" | "preferred" | "warrant" | "right" | "unit" | "pre_merger_spac" | "shell" | "otc" | "unknown"
    classification_status: str  # "supported_common_stock" | "excluded_security_type" | "unknown_fail_closed"
    is_eligible_common_stock: bool
    provenance_source: str
    provider_type_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EarningsScheduleStatus:
    """Point-in-time next earnings announcement schedule state."""

    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    ticker_at_decision: str
    schedule_status: str  # "known_point_in_time" | "unknown"
    provenance_source: str
    next_earnings_date: str | None = None
    announcement_timing: str | None = None  # "before_market_open" | "after_market_close" | "during_trading_hours" | "unspecified"
    sessions_to_earnings: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OutcomeLabelRecord:
    """Calculated outcome metrics across all nine target/horizon cells."""

    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    target_pct: float
    horizon_sessions: int
    ticker_at_decision: str
    reference_entry_price: float
    entry_friction_bps: float
    target_price: float
    adverse_barrier_pct: float
    adverse_barrier_price: float
    clean_risk_cap_pct: float
    clean_risk_cap_amount: float
    mfe_pct: float
    target_progress_ratio: float
    near_miss: bool
    partial_move: bool
    mae_pct: float
    mae_atr: float
    adverse_excursion: bool
    clean_target_reached: bool
    path_sequence_ambiguous: bool
    end_of_horizon_return: float
    retention_ratio: float
    sustained_target: bool
    analysis_entry_price: float = 0.0
    special_distribution_unresolved: bool = False
    time_to_target: int | None = None
    time_to_mae: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MasterOpportunityEpisode:
    """Independent master opportunity episode anchored by first qualifying +10%/21 move."""

    episode_id: str
    anchor_security_id: str
    anchor_ticker: str
    anchor_as_of_date: str
    anchor_cutoff_time: str
    anchor_entry_price: float
    window_start_date: str
    window_end_date: str
    window_session_count: int
    max_return_pct_21: float
    max_target_tier_reached: str  # "10" | "20" | "30" | "none"
    clean_target_reached_10_21: bool
    clean_target_reached_20_21: bool
    clean_target_reached_30_21: bool
    first_target_session_index: int | None
    constituent_observation_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeMembership:
    """Mapping linking daily decision observations to their parent master episode."""

    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    ticker_at_decision: str
    episode_id: str
    session_index_in_episode: int  # 1..21
    constituent_tag: str  # "pre_target" | "target_session" | "post_target"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineComparatorOutput:
    """Evaluation of locked baseline models on common observations."""

    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    comparator_id: str
    ticker_at_decision: str
    comparator_family: str
    raw_score_or_return: float
    cross_sectional_rank: int
    cross_sectional_percentile: float
    top_10_flag: bool
    top_25_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataQualityCoverage:
    """Per-security data completeness and integrity audit metrics."""

    immutable_security_id: str
    split_name: str
    expected_sessions: int
    observed_sessions: int
    completeness_pct: float
    unexplained_missing_sessions: int
    max_consecutive_missing_sessions: int
    duplicate_bar_count: int
    malformed_bar_count: int
    halt_sessions_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceProviderRecord:
    """Audit trail for market and reference data inputs."""

    record_id: str
    data_family: str
    provider_name: str
    provider_role: str
    endpoint_url_pattern: str
    retrieval_timestamp_utc: str
    request_fingerprint_sha256: str
    response_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExclusionReasonRecord:
    """Enumeration and accounting of all rejected or unavailable observations."""

    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    reason_code: str
    ticker_at_decision: str
    reason_category: str  # "security_type" | "liquidity" | "price" | "trading_history" | "lookback_unavailable" | "earnings_unknown" | "split_boundary" | "unknown_security_identity"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
