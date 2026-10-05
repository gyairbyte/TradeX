"""Data models for LONG-002D3A Blinded Review Pilot."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PilotCandidate:
    """Internal candidate representation before blinding."""

    case_id: str
    sample_stratum: str
    immutable_security_id: str
    as_of_date: str
    cutoff_time: str
    ticker_at_decision: str
    year: str
    episode_id: str | None = None
    clean_target_reached: bool = False
    target_progress_ratio: float = 0.0
    near_miss: bool = False
    adverse_excursion: bool = False
    mfe_pct: float | None = None
    mae_pct: float | None = None
    time_to_target: int | None = None

    def to_observation_key(self) -> tuple[str, str, str]:
        return (self.immutable_security_id, self.as_of_date, self.cutoff_time)


@dataclass
class BlindedBar:
    """Anonymized single price bar in relative time."""

    relative_index: int
    relative_label: str
    normalized_open: float
    normalized_high: float
    normalized_low: float
    normalized_close: float
    relative_volume: float | None
    normalized_sma20: float | None
    normalized_sma50: float | None
    atr_pct_14: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageAPacket:
    """Reviewer-visible Stage A packet (technical only)."""

    case_id: str
    relative_bars: list[dict[str, Any]]
    technical_metrics: dict[str, Any]
    spy_context: dict[str, Any]
    data_quality_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageBPacket:
    """Reviewer-visible Stage B packet (technical + PIT context)."""

    case_id: str
    stage_a: dict[str, Any]
    pit_context: dict[str, Any]
    data_confidence_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerKeyRecord:
    """External, uncommitted answer key record."""

    case_id: str
    sample_stratum: str
    immutable_security_id: str
    ticker: str
    decision_date: str
    cutoff_time: str
    episode_id: str | None
    clean_target_reached: bool
    target_progress_ratio: float
    near_miss: bool
    adverse_excursion: bool
    mfe_pct: float | None
    mae_pct: float | None
    time_to_target: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewerLabel:
    """Reviewer label conforming to the locked D3A schema."""

    case_id: str
    stage: str
    surface_decision: str
    visible_state_if_surfaced: str | None
    expected_target_pct: int | None
    expected_horizon_sessions: int | None
    qualitative_confidence: int
    setup_archetype: str
    entry_plan: str
    trigger_or_zone: str
    max_validity_sessions: int | None
    gap_handling: str
    invalidation: str
    positive_reasons: list[str]
    material_risks_counterarguments: str
    submitted_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
