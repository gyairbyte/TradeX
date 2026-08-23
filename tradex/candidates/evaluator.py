"""Descriptive shadow evaluator for prospective candidate dossiers (MVP-ARCH-001-R5B).

Evaluates point-in-time candidate observations in a purely descriptive, non-actionable
envelope. Does NOT calculate trading actionability, probabilities, master scores,
weights, or alert eligibility. All explainability reasons are strictly neutral.
"""
from __future__ import annotations

import hashlib
from typing import Any

from tradex.candidates.models import (
    CandidateDimension,
    CandidateEvaluation,
    CandidateEvidence,
    CandidateMissingData,
    CandidateReason,
    CandidateSnapshot,
    ReasonPolarity,
    ReasonSeverity,
)

EVALUATOR_ID: str = "shadow_observation_evaluator"
EVALUATOR_VERSION: str = "1.0.0"
EVIDENCE_STATE: str = "exploratory"


def generate_evaluation_id(candidate_id: str, evaluator_id: str, evaluator_version: str) -> str:
    """Generate a deterministic evaluation ID for a candidate snapshot and evaluator."""
    key = f"{candidate_id.strip()}\x1f{evaluator_id.strip()}\x1f{evaluator_version.strip()}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return f"eval_{digest}"


def generate_reason_id(evaluation_id: str, reason_code: str) -> str:
    """Generate a deterministic reason ID for an evaluation and reason code."""
    key = f"{evaluation_id.strip()}\x1f{reason_code.strip()}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return f"reas_{digest}"


class ShadowObservationEvaluator:
    """Non-actionable, descriptive evaluator for prospective market observations.

    Populates only the 'context' and 'data_confidence' architectural dimensions.
    All explainability reasons have ReasonPolarity.NEUTRAL.
    """

    def __init__(
        self,
        evaluator_id: str = EVALUATOR_ID,
        evaluator_version: str = EVALUATOR_VERSION,
        evidence_state: str = EVIDENCE_STATE,
    ) -> None:
        self.evaluator_id = evaluator_id
        self.evaluator_version = evaluator_version
        self.evidence_state = evidence_state

    def evaluate(
        self,
        snapshot: CandidateSnapshot,
        evidence: list[CandidateEvidence] | tuple[CandidateEvidence, ...],
        missing_data: list[CandidateMissingData] | tuple[CandidateMissingData, ...],
        *,
        requested_provider: str | None = None,
        actual_provider: str | None = None,
        fallback_used: bool = False,
    ) -> tuple[CandidateEvaluation, list[CandidateReason]]:
        """Perform descriptive shadow evaluation and return evaluation envelope + neutral reasons."""
        cand_id = snapshot.candidate_id
        eval_id = generate_evaluation_id(cand_id, self.evaluator_id, self.evaluator_version)

        # Locate the primary screener observation evidence if present
        screener_ev = next((ev for ev in evidence if ev.evidence_type == "screener_observation"), None)
        screener_meta = screener_ev.metadata if screener_ev else {}

        # 1. Build 'context' dimension (factual, non-directional observations)
        context_dim: dict[str, Any] = {
            "evidence_types": [ev.evidence_type for ev in evidence],
            "observation_status": screener_meta.get("observation_status"),
            "timeframe": screener_meta.get("timeframe"),
            "days_until_earnings": screener_meta.get("days_until_earnings"),
        }

        # 2. Build 'data_confidence' dimension (operational data completeness facts)
        resolved_actual = actual_provider or (screener_ev.provider if screener_ev else "unknown")
        resolved_req = requested_provider or resolved_actual
        data_confidence_dim: dict[str, Any] = {
            "actual_provider": resolved_actual,
            "requested_provider": resolved_req,
            "fallback_used": bool(fallback_used),
            "missing_inputs_count": len(missing_data),
            "missing_inputs": [m.input_name for m in missing_data],
        }

        # The R5B evaluator populates ONLY context and data_confidence
        dimensions: dict[str, Any] = {
            CandidateDimension.CONTEXT.value: context_dim,
            CandidateDimension.DATA_CONFIDENCE.value: data_confidence_dim,
        }

        evaluation = CandidateEvaluation(
            evaluation_id=eval_id,
            candidate_id=cand_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            evidence_state=self.evidence_state,
            dimensions=dimensions,
            created_at=snapshot.created_at,
        )

        reasons: list[CandidateReason] = []
        source_ev_id = screener_ev.evidence_id if screener_ev else None

        # Reason 1: Primary observation captured (neutral)
        if screener_ev is not None:
            reasons.append(
                CandidateReason(
                    reason_id=generate_reason_id(eval_id, "PRIMARY_OBSERVATION_CAPTURED"),
                    candidate_id=cand_id,
                    evaluation_id=eval_id,
                    dimension=CandidateDimension.CONTEXT,
                    reason_code="PRIMARY_OBSERVATION_CAPTURED",
                    human_text=(
                        f"Primary screener observation recorded on {screener_meta.get('timeframe', 'intraday')} "
                        f"timeframe with status '{screener_meta.get('observation_status')}'."
                    ),
                    polarity=ReasonPolarity.NEUTRAL,
                    severity=ReasonSeverity.INFO,
                    source_evidence_id=source_ev_id,
                    created_at=snapshot.created_at,
                )
            )

        # Reason 2: Provider provenance captured (neutral)
        reasons.append(
            CandidateReason(
                reason_id=generate_reason_id(eval_id, "PROVIDER_PROVENANCE_CAPTURED"),
                candidate_id=cand_id,
                evaluation_id=eval_id,
                dimension=CandidateDimension.DATA_CONFIDENCE,
                reason_code="PROVIDER_PROVENANCE_CAPTURED",
                human_text=(
                    f"Market data observed via provider '{resolved_actual}' "
                    f"(fallback: {'active' if fallback_used else 'none'})."
                ),
                polarity=ReasonPolarity.NEUTRAL,
                severity=ReasonSeverity.INFO,
                source_evidence_id=source_ev_id,
                created_at=snapshot.created_at,
            )
        )

        # Reason 3: Earnings distance fact if available (neutral)
        er_days = screener_meta.get("days_until_earnings")
        if er_days is not None:
            reasons.append(
                CandidateReason(
                    reason_id=generate_reason_id(eval_id, "EARNINGS_CONTEXT_AVAILABLE"),
                    candidate_id=cand_id,
                    evaluation_id=eval_id,
                    dimension=CandidateDimension.CONTEXT,
                    reason_code="EARNINGS_CONTEXT_AVAILABLE",
                    human_text=f"Upcoming earnings event recorded {er_days} days from observation.",
                    polarity=ReasonPolarity.NEUTRAL,
                    severity=ReasonSeverity.INFO,
                    source_evidence_id=source_ev_id,
                    created_at=snapshot.created_at,
                )
            )

        # Reason 4: Fallback provider warning if active (neutral)
        if fallback_used:
            reasons.append(
                CandidateReason(
                    reason_id=generate_reason_id(eval_id, "PROVIDER_FALLBACK_ACTIVE"),
                    candidate_id=cand_id,
                    evaluation_id=eval_id,
                    dimension=CandidateDimension.DATA_CONFIDENCE,
                    reason_code="PROVIDER_FALLBACK_ACTIVE",
                    human_text=(
                        f"Fallback provider '{resolved_actual}' was used instead of "
                        f"requested '{resolved_req}'."
                    ),
                    polarity=ReasonPolarity.NEUTRAL,
                    severity=ReasonSeverity.WARNING,
                    source_evidence_id=source_ev_id,
                    created_at=snapshot.created_at,
                )
            )

        # Reason 5: Missing expected fields notice (neutral)
        if missing_data:
            missing_names = ", ".join(m.input_name for m in missing_data)
            reasons.append(
                CandidateReason(
                    reason_id=generate_reason_id(eval_id, "PRIMARY_INPUTS_INCOMPLETE"),
                    candidate_id=cand_id,
                    evaluation_id=eval_id,
                    dimension=CandidateDimension.DATA_CONFIDENCE,
                    reason_code="PRIMARY_INPUTS_INCOMPLETE",
                    human_text=f"Expected observation inputs unavailable: {missing_names}.",
                    polarity=ReasonPolarity.NEUTRAL,
                    severity=ReasonSeverity.WARNING,
                    source_evidence_id=source_ev_id,
                    created_at=snapshot.created_at,
                )
            )

        return evaluation, reasons
