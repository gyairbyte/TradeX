"""Observation aggregation and candidate dossier input extraction for MVP-ARCH-001-R5B.

Assembles immutable CandidateSnapshot, CandidateEvidence, and CandidateMissingData
records from completed, persisted scan observations without making new provider calls.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from tradex.candidates.models import (
    CandidateEvidence,
    CandidateMissingData,
    CandidateSnapshot,
    MissingDataStatus,
    SecurityIdentityStatus,
    derive_trading_date,
)

SCORABLE_OBSERVATION_STATUSES = frozenset({"signal", "below_threshold"})


def generate_candidate_id(session_id: str, symbol: str) -> str:
    """Generate a deterministic, collision-resistant candidate snapshot ID.

    The ID is deterministically derived from the canonical scan session ID
    and the normalized uppercase symbol:
        cand_<sha256(session_id\\x1fSYMBOL)[:24]>
    """
    clean_session = str(session_id).strip()
    clean_symbol = str(symbol).strip().upper()
    if not clean_session:
        raise ValueError("session_id must be a non-empty string")
    if not clean_symbol:
        raise ValueError("symbol must be a non-empty string")

    key = f"{clean_session}\x1f{clean_symbol}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return f"cand_{digest}"


def generate_evidence_id(candidate_id: str, evidence_type: str) -> str:
    """Generate a deterministic evidence ID for a candidate and evidence type."""
    key = f"{candidate_id.strip()}\x1f{evidence_type.strip()}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return f"evid_{digest}"


def generate_missing_data_id(candidate_id: str, input_name: str) -> str:
    """Generate a deterministic missing data record ID."""
    key = f"{candidate_id.strip()}\x1f{input_name.strip()}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return f"miss_{digest}"


def is_scorable_observation(status: str | None) -> bool:
    """Return True if the observation status is scorable (SIGNAL or BELOW_THRESHOLD)."""
    if not status:
        return False
    return str(status).strip().lower() in SCORABLE_OBSERVATION_STATUSES


def build_candidate_snapshot(
    symbol: str,
    session_id: str,
    decision_timestamp: datetime,
    *,
    contract_version: int = 1,
) -> CandidateSnapshot:
    """Build an immutable CandidateSnapshot header anchored to the scan session."""
    norm_symbol = str(symbol).strip().upper()
    cand_id = generate_candidate_id(session_id, norm_symbol)
    norm_ts = decision_timestamp.astimezone(UTC)
    trading_date = derive_trading_date(norm_ts)

    return CandidateSnapshot(
        candidate_id=cand_id,
        symbol=norm_symbol,
        decision_timestamp=norm_ts,
        contract_version=contract_version,
        trading_date=trading_date,
        security_identity_version=None,
        security_identity_status=SecurityIdentityStatus.UNKNOWN,
    )


def extract_screener_evidence(
    candidate_id: str,
    observation: pd.Series | dict[str, Any],
    session_id: str,
    timeframe: str,
    observed_at: datetime,
    actual_provider: str,
) -> tuple[CandidateEvidence, list[CandidateMissingData]]:
    """Extract primary screener observation evidence and any missing field records."""
    obs_dict = observation.to_dict() if isinstance(observation, pd.Series) else dict(observation)
    norm_obs_at = observed_at.astimezone(UTC)

    raw_score = obs_dict.get("score")
    score_val = int(raw_score) if pd.notna(raw_score) and raw_score is not None else None

    raw_close = obs_dict.get("last_close")
    close_val = float(raw_close) if pd.notna(raw_close) and raw_close is not None else None

    raw_vol = obs_dict.get("volume_ratio")
    vol_val = float(raw_vol) if pd.notna(raw_vol) and raw_vol is not None else None

    raw_rsi = obs_dict.get("rsi")
    rsi_val = float(raw_rsi) if pd.notna(raw_rsi) and raw_rsi is not None else None

    raw_er = obs_dict.get("days_until_earnings")
    er_val = int(raw_er) if pd.notna(raw_er) and raw_er is not None else None

    reasons_val = obs_dict.get("reasons")
    reasons_clean = str(reasons_val) if pd.notna(reasons_val) and reasons_val is not None else None

    provider_val = obs_dict.get("provider") or actual_provider or "unknown"
    status_val = str(obs_dict.get("status") or "unknown").strip().lower()

    evidence_metadata: dict[str, Any] = {
        "observation_status": status_val,
        "legacy_heuristic_score": score_val,
        "last_close": close_val,
        "volume_ratio": vol_val,
        "rsi": rsi_val,
        "days_until_earnings": er_val,
        "reasons": reasons_clean,
        "timeframe": timeframe,
    }

    evidence = CandidateEvidence(
        evidence_id=generate_evidence_id(candidate_id, "screener_observation"),
        candidate_id=candidate_id,
        evidence_type="screener_observation",
        source_ref_type="scan_session",
        source_ref_id=session_id,
        provider=provider_val,
        observed_at=norm_obs_at,
        metadata=evidence_metadata,
    )

    missing_data: list[CandidateMissingData] = []

    # Check for unexpected missing primary inputs on a scorable observation
    if close_val is None:
        missing_data.append(
            CandidateMissingData(
                record_id=generate_missing_data_id(candidate_id, "last_close"),
                candidate_id=candidate_id,
                input_name="last_close",
                data_family="market_data",
                status=MissingDataStatus.UNKNOWN,
                detail="Price close missing from screener observation",
                provider=provider_val,
                observed_at=norm_obs_at,
            )
        )

    if vol_val is None:
        missing_data.append(
            CandidateMissingData(
                record_id=generate_missing_data_id(candidate_id, "volume_ratio"),
                candidate_id=candidate_id,
                input_name="volume_ratio",
                data_family="market_data",
                status=MissingDataStatus.UNKNOWN,
                detail="Volume ratio missing from screener observation",
                provider=provider_val,
                observed_at=norm_obs_at,
            )
        )

    if rsi_val is None:
        missing_data.append(
            CandidateMissingData(
                record_id=generate_missing_data_id(candidate_id, "rsi"),
                candidate_id=candidate_id,
                input_name="rsi",
                data_family="indicator",
                status=MissingDataStatus.UNKNOWN,
                detail="RSI missing from screener observation",
                provider=provider_val,
                observed_at=norm_obs_at,
            )
        )

    return evidence, missing_data
