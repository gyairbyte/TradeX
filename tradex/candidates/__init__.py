"""Candidate snapshot domain contract and schema v4 persistence primitives (MVP-ARCH-001-R5A/R5B)."""
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
    "CandidateMissingData",
    "CandidateReason",
    "CandidateService",
    "CandidateSnapshot",
    "MissingDataStatus",
    "ReasonPolarity",
    "ReasonSeverity",
    "SecurityIdentityStatus",
    "ShadowObservationEvaluator",
    "build_candidate_snapshot",
    "derive_trading_date",
    "extract_screener_evidence",
    "generate_candidate_id",
    "get_candidate",
    "get_candidate_dossier",
    "is_scorable_observation",
    "list_candidates",
    "record_candidate_dossier",
    "record_session_candidates",
]
