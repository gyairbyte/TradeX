"""Candidate snapshot domain contract, persistence, and read queries (MVP-ARCH-001-R5A/R5B/R5C)."""
from __future__ import annotations

from tradex.candidates.aggregator import (
    SCORABLE_OBSERVATION_STATUSES,
    build_candidate_snapshot,
    extract_screener_evidence,
    generate_candidate_id,
    is_scorable_observation,
)
from tradex.candidates.evaluator import (
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    EVIDENCE_STATE,
    ShadowObservationEvaluator,
)
from tradex.candidates.models import (
    CandidateDimension,
    CandidateDossier,
    CandidateEvaluation,
    CandidateEvidence,
    CandidateMissingData,
    CandidateReason,
    CandidateSnapshot,
    MissingDataStatus,
    ReasonPolarity,
    ReasonSeverity,
    SecurityIdentityStatus,
    derive_trading_date,
)
from tradex.candidates.queries import (
    CandidateHistoryRow,
    TodayCandidateRow,
    TodaySummaryFacts,
    get_available_trading_dates,
    get_candidate_history_for_symbol,
    get_latest_candidates_for_date,
    get_today_summary_facts,
)
from tradex.candidates.service import (
    CandidateBatchResult,
    CandidateService,
    record_session_candidates,
)
from tradex.candidates.store import (
    get_candidate,
    get_candidate_dossier,
    list_candidates,
    record_candidate_dossier,
)

__all__ = [
    "EVALUATOR_ID",
    "EVALUATOR_VERSION",
    "EVIDENCE_STATE",
    "SCORABLE_OBSERVATION_STATUSES",
    "CandidateBatchResult",
    "CandidateDimension",
    "CandidateDossier",
    "CandidateEvaluation",
    "CandidateEvidence",
    "CandidateHistoryRow",
    "CandidateMissingData",
    "CandidateReason",
    "CandidateService",
    "CandidateSnapshot",
    "MissingDataStatus",
    "ReasonPolarity",
    "ReasonSeverity",
    "SecurityIdentityStatus",
    "ShadowObservationEvaluator",
    "TodayCandidateRow",
    "TodaySummaryFacts",
    "build_candidate_snapshot",
    "derive_trading_date",
    "extract_screener_evidence",
    "generate_candidate_id",
    "get_available_trading_dates",
    "get_candidate",
    "get_candidate_dossier",
    "get_candidate_history_for_symbol",
    "get_latest_candidates_for_date",
    "get_today_summary_facts",
    "is_scorable_observation",
    "list_candidates",
    "record_candidate_dossier",
    "record_session_candidates",
]
