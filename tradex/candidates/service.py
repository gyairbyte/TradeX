"""Candidate aggregation and shadow evaluation orchestration service (MVP-ARCH-001-R5B).

Coordinates extracting scorable observations from completed scan sessions, evaluating
descriptive shadow dimensions, assembling immutable CandidateDossier objects, and
persisting them atomically with per-candidate failure isolation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

from tradex.candidates.aggregator import (
    build_candidate_snapshot,
    extract_screener_evidence,
    is_scorable_observation,
)
from tradex.candidates.evaluator import ShadowObservationEvaluator
from tradex.candidates.models import CandidateDossier
from tradex.candidates.store import get_candidate, record_candidate_dossier
from tradex.config import TradeXSettings

if TYPE_CHECKING:
    from tradex.screener.engine import ScanReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateBatchResult:
    """Structured result of aggregating and persisting candidate dossiers for a scan session."""

    session_id: str
    scorable_count: int
    dossiers_persisted: int
    dossiers_replayed: int
    failed_symbols: tuple[str, ...] = ()
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def total_processed(self) -> int:
        return self.dossiers_persisted + self.dossiers_replayed


class CandidateService:
    """Orchestrates candidate snapshot aggregation, shadow evaluation, and persistence."""

    def __init__(self, evaluator: ShadowObservationEvaluator | None = None) -> None:
        self.evaluator = evaluator or ShadowObservationEvaluator()

    def process_scorable_observation(
        self,
        observation: pd.Series | dict[str, Any],
        session_id: str,
        timeframe: str,
        scan_time: datetime,
        *,
        requested_provider: str | None = None,
        actual_provider: str | None = None,
        fallback_used: bool = False,
        settings: TradeXSettings | None = None,
    ) -> tuple[CandidateDossier, bool]:
        """Aggregate, evaluate, and persist a single candidate dossier.

        Returns (dossier, is_replay).
        """
        obs_dict = observation.to_dict() if isinstance(observation, pd.Series) else dict(observation)
        symbol = str(obs_dict.get("ticker", "")).strip().upper()
        if not symbol:
            raise ValueError("Observation missing ticker symbol")

        decision_ts = scan_time.astimezone(UTC)
        resolved_actual = actual_provider or str(obs_dict.get("provider") or "unknown")

        # 1. Build immutable candidate snapshot header
        snapshot = build_candidate_snapshot(
            symbol=symbol,
            session_id=session_id,
            decision_timestamp=decision_ts,
        )

        # 2. Extract screener evidence and missing data
        evidence, missing_data = extract_screener_evidence(
            candidate_id=snapshot.candidate_id,
            observation=obs_dict,
            session_id=session_id,
            timeframe=timeframe,
            observed_at=decision_ts,
            actual_provider=resolved_actual,
        )

        # 3. Evaluate descriptive exploratory shadow dimensions and reasons
        evaluation, reasons = self.evaluator.evaluate(
            snapshot=snapshot,
            evidence=[evidence],
            missing_data=missing_data,
            requested_provider=requested_provider,
            actual_provider=resolved_actual,
            fallback_used=fallback_used,
        )

        # 4. Assemble complete CandidateDossier container
        dossier = CandidateDossier(
            snapshot=snapshot,
            evaluations=(evaluation,),
            evidence=(evidence,),
            reasons=tuple(reasons),
            missing_data=tuple(missing_data),
        )

        # 5. Check if candidate already exists before persistence
        existing = get_candidate(snapshot.candidate_id, settings=settings)
        is_replay = existing is not None

        # 6. Record dossier atomically (replay-safe & idempotent)
        persisted_dossier = record_candidate_dossier(dossier, settings=settings)
        return persisted_dossier, is_replay

    def record_session_candidates(
        self,
        report: ScanReport,
        session_id: str,
        timeframe: str,
        *,
        scan_time: datetime | None = None,
        settings: TradeXSettings | None = None,
    ) -> CandidateBatchResult:
        """Aggregate and record candidate dossiers for all scorable observations in a ScanReport.

        Only scorable observations ('signal' and 'below_threshold') produce dossiers.
        Non-scored observations ('fetch_failure', 'insufficient_data', etc.) remain
        in scan_observations and do not create dossiers.

        Per-candidate failures are isolated and do not prevent other candidates
        from being persisted.
        """
        if not session_id or not str(session_id).strip():
            raise ValueError("session_id must be a non-empty string")

        effective_scan_time = scan_time or datetime.now(UTC)
        if effective_scan_time.tzinfo is None:
            raise ValueError("scan_time must be timezone-aware; naive datetimes are rejected")

        obs_df = getattr(report, "observations", pd.DataFrame())
        if obs_df is None or obs_df.empty or "status" not in obs_df.columns:
            return CandidateBatchResult(
                session_id=session_id,
                scorable_count=0,
                dossiers_persisted=0,
                dossiers_replayed=0,
            )

        requested_provider = getattr(report, "requested_provider", "unknown")
        actual_provider = getattr(report, "actual_provider", None) or requested_provider
        fallback_used = bool(getattr(report, "fallback_used", False))

        scorable_rows = obs_df[obs_df["status"].apply(is_scorable_observation)]
        scorable_count = len(scorable_rows)

        dossiers_persisted = 0
        dossiers_replayed = 0
        failed_symbols: list[str] = []
        failures: dict[str, str] = {}

        for _, row in scorable_rows.iterrows():
            sym = str(row.get("ticker", "UNKNOWN")).strip().upper()
            try:
                _, is_replay = self.process_scorable_observation(
                    observation=row,
                    session_id=session_id,
                    timeframe=timeframe,
                    scan_time=effective_scan_time,
                    requested_provider=requested_provider,
                    actual_provider=actual_provider,
                    fallback_used=fallback_used,
                    settings=settings,
                )
                if is_replay:
                    dossiers_replayed += 1
                else:
                    dossiers_persisted += 1
            except Exception as exc:
                logger.exception(
                    "Candidate persistence failed for symbol '%s' in session '%s'",
                    sym,
                    session_id,
                )
                failed_symbols.append(sym)
                failures[sym] = str(exc)

        return CandidateBatchResult(
            session_id=session_id,
            scorable_count=scorable_count,
            dossiers_persisted=dossiers_persisted,
            dossiers_replayed=dossiers_replayed,
            failed_symbols=tuple(failed_symbols),
            failures=failures,
        )


def record_session_candidates(
    report: ScanReport,
    session_id: str,
    timeframe: str,
    *,
    scan_time: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> CandidateBatchResult:
    """Convenience function to record candidate dossiers for a scan session."""
    service = CandidateService()
    return service.record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe=timeframe,
        scan_time=scan_time,
        settings=settings,
    )
