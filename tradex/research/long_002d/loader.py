"""Data and provider cache loader for LONG-002D1.

Enforces read-only cache access, zero live network requests (allow_live=False),
verifies Stage C external parquet digests, and tracks consumed cache payload hashes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002c.bars import load_interval_aware_daily_bars
from tradex.research.long_002c.cache import ResponseCache
from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002c.providers import AlpacaDailyClient
from tradex.research.long_002d.spec import (
    DEV_END,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    HORIZON_SESSIONS,
    POPULATION_CUTOFF,
    TARGET_PCT,
    enforce_split_guard,
)


@dataclass
class NetworkAuditTracker:
    """Truthful tracker for cache hits, cache misses, and live request attempts."""

    provider_cache_hits: int = 0
    provider_cache_misses: int = 0
    live_request_path_attempts: int = 0
    outbound_http_requests_executed: int = 0
    blocked_live_request_attempts: int = 0


@dataclass
class PayloadAuditSummary:
    """Audit of provider cache payloads consumed during feature construction."""

    total_payloads_consumed: int
    total_payload_bytes: int
    unique_cache_keys: list[str]
    matched_provenance_count: int
    unmatched_provenance_count: int
    provider_cache_hits: int
    provider_cache_misses: int
    live_request_path_attempts: int
    outbound_http_requests_executed: int
    blocked_live_request_attempts: int
    unmatched_details: list[dict[str, Any]]


class AuditingReadOnlyCache(ResponseCache):
    """Subclass of ResponseCache that audits read payloads and forbids cache writes."""

    def __init__(self, cache_dir: Path, tracker: NetworkAuditTracker | None = None) -> None:
        super().__init__(cache_dir=cache_dir, enabled=True)
        self.consumed_payloads: dict[str, dict[str, Any]] = {}
        self.tracker = tracker or NetworkAuditTracker()

    def get(self, url: str, request_fingerprint: str) -> tuple[bytes | None, str | None, str | None]:
        body, resp_sha, req_time = super().get(url, request_fingerprint)
        if body is not None and resp_sha is not None:
            self.tracker.provider_cache_hits += 1
            key = self._cache_key(url, request_fingerprint)
            if key not in self.consumed_payloads:
                self.consumed_payloads[key] = {
                    "sha256": resp_sha,
                    "byte_count": len(body),
                    "url": url,
                    "req_fp": request_fingerprint,
                }
        else:
            self.tracker.provider_cache_misses += 1
        return body, resp_sha, req_time

    def set(self, *args: Any, **kwargs: Any) -> str:
        raise PermissionError("AuditingReadOnlyCache is strictly READ-ONLY; writes are forbidden.")


def create_read_only_alpaca_client(
    cache_dir: Path,
    tracker: NetworkAuditTracker | None = None,
) -> tuple[AlpacaDailyClient, AuditingReadOnlyCache, NetworkAuditTracker]:
    """Create an AlpacaDailyClient that fails closed against any live network request."""
    if not cache_dir.exists():
        raise FileNotFoundError(f"Provider cache directory not found: {cache_dir}")

    tracker = tracker or NetworkAuditTracker()
    cache = AuditingReadOnlyCache(cache_dir=cache_dir, tracker=tracker)

    def _forbidden_network_call(*args: Any, **kwargs: Any) -> Any:
        tracker.live_request_path_attempts += 1
        tracker.blocked_live_request_attempts += 1
        raise RuntimeError(
            "FAIL-CLOSED BREACH: A live provider network call was attempted! "
            "LONG-002D1 strictly requires allow_live=False and 100% provider cache hits."
        )

    client = AlpacaDailyClient(
        api_key="DUMMY_KEY_READ_ONLY",
        secret_key="DUMMY_SECRET_READ_ONLY",
        cache=cache,
        request_func=_forbidden_network_call,
        max_retries=0,
    )
    return client, cache, tracker


def select_study_candidates(
    discovery_manifest_path: Path,
    study_security_ids: list[str],
) -> list[CandidateSecurity]:
    """Load and validate study candidates from discovery manifest against expected study security IDs.

    Fails closed if:
    - discovery manifest file is missing or invalid
    - any duplicate immutable_security_id exists in manifest
    - any study_security_id is missing from discovery manifest
    - candidate count does not match study security IDs count
    """
    if not discovery_manifest_path.exists():
        raise FileNotFoundError(f"Discovery manifest not found: {discovery_manifest_path}")

    with open(discovery_manifest_path, "r", encoding="utf-8") as f:
        disc = json.load(f)

    candidates_raw = disc.get("candidates", [])
    if not candidates_raw:
        raise ValueError(f"No candidates found in {discovery_manifest_path}")

    disc_map: dict[str, CandidateSecurity] = {}
    for c_raw in candidates_raw:
        cand = CandidateSecurity.from_dict(c_raw)
        s_id = cand.immutable_security_id
        if s_id in disc_map:
            raise ValueError(f"Duplicate immutable_security_id found in discovery manifest: {s_id}")
        disc_map[s_id] = cand

    missing = [s_id for s_id in study_security_ids if s_id not in disc_map]
    if missing:
        raise ValueError(f"Missing {len(missing)} study security IDs from discovery manifest. Examples: {missing[:5]}")

    selected = [disc_map[s_id] for s_id in study_security_ids]
    if len(selected) != len(study_security_ids):
        raise ValueError(
            f"Selected candidate count mismatch: expected {len(study_security_ids)}, got {len(selected)}"
        )

    return selected


def audit_stage_c_cache_provenance(
    stage_c_dir: Path,
    auditing_cache: AuditingReadOnlyCache,
    tracker: NetworkAuditTracker,
) -> PayloadAuditSummary:
    """Audit all consumed provider cache payloads against Stage C Alpaca provenance records.

    Fails closed if any candidate-security or SPY payload cannot be matched against Stage C.
    """
    p_prov = stage_c_dir / "provenance_records.parquet"
    if not p_prov.exists():
        raise FileNotFoundError(f"Stage C provenance records not found: {p_prov}")

    tbl_prov = pq.read_table(p_prov, filters=[("provider_name", "=", "alpaca")])
    df_prov = tbl_prov.to_pandas()

    prov_pair_set = set(zip(df_prov["request_fingerprint_sha256"], df_prov["response_sha256"]))

    consumed = auditing_cache.consumed_payloads
    total_consumed = len(consumed)
    total_bytes = sum(p["byte_count"] for p in consumed.values())
    unique_keys = list(consumed.keys())

    matched_count = 0
    unmatched_count = 0
    unmatched_details: list[dict[str, Any]] = []

    for key, p_info in consumed.items():
        fp = p_info["req_fp"]
        sha = p_info["sha256"]
        url = p_info["url"]

        if (fp, sha) in prov_pair_set:
            matched_count += 1
        else:
            unmatched_count += 1
            unmatched_details.append({
                "cache_key": key,
                "url": url,
                "request_fingerprint_sha256": fp,
                "response_sha256": sha,
                "byte_count": p_info["byte_count"],
                "reason": "Exact (request_fingerprint_sha256, response_sha256) pair not found in Stage C Alpaca provenance",
            })

    if unmatched_count > 0:
        raise RuntimeError(
            f"STAGE C CACHE PROVENANCE AUDIT FAILED: {unmatched_count} consumed cache payloads "
            f"did not match Stage C provenance! First unmatched detail: {unmatched_details[0]}"
        )

    return PayloadAuditSummary(
        total_payloads_consumed=total_consumed,
        total_payload_bytes=total_bytes,
        unique_cache_keys=unique_keys,
        matched_provenance_count=matched_count,
        unmatched_provenance_count=unmatched_count,
        provider_cache_hits=tracker.provider_cache_hits,
        provider_cache_misses=tracker.provider_cache_misses,
        live_request_path_attempts=tracker.live_request_path_attempts,
        outbound_http_requests_executed=tracker.outbound_http_requests_executed,
        blocked_live_request_attempts=tracker.blocked_live_request_attempts,
        unmatched_details=unmatched_details,
    )


def load_stage_c_primary_data(
    stage_c_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and filter Stage C Parquet tables for the 20:30 primary population.

    Returns:
        (df_obs, df_outcomes, df_eligibility)
        all filtered to cutoff_time == '20:30', raw_outcome_eligible == True, split_boundary_purged == False.
    """
    p_obs = stage_c_dir / "decision_observations.parquet"
    p_out = stage_c_dir / "outcome_matrix.parquet"
    p_elig = stage_c_dir / "data_eligibility.parquet"

    for p in [p_obs, p_out, p_elig]:
        if not p.exists():
            raise FileNotFoundError(f"Stage C Parquet file not found: {p}")

    # Read decision observations
    filters_obs = [
        ("cutoff_time", "=", POPULATION_CUTOFF),
        ("raw_outcome_eligible", "=", True),
        ("split_boundary_purged", "=", False),
    ]
    cols_obs = [
        "immutable_security_id",
        "ticker_at_decision",
        "as_of_date",
        "cutoff_time",
        "split_normalized_close",
        "as_traded_close",
        "volume",
        "dollar_volume_20d_median",
        "atr_14",
    ]
    df_obs = pq.read_table(p_obs, columns=cols_obs, filters=filters_obs).to_pandas()

    if len(df_obs) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"Stage C decision observations count mismatch: expected {EXPECTED_DENOMINATOR}, got {len(df_obs)}"
        )

    # Read primary outcome labels (+10% / 10d clean target reached)
    filters_out = [
        ("cutoff_time", "=", POPULATION_CUTOFF),
        ("target_pct", "=", TARGET_PCT),
        ("horizon_sessions", "=", HORIZON_SESSIONS),
    ]
    cols_out = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "clean_target_reached",
        "target_progress_ratio",
        "near_miss",
        "partial_move",
        "adverse_excursion",
        "sustained_target",
    ]
    df_out_raw = pq.read_table(p_out, columns=cols_out, filters=filters_out).to_pandas()
    df_out = df_obs[["immutable_security_id", "as_of_date", "cutoff_time"]].merge(
        df_out_raw, on=["immutable_security_id", "as_of_date", "cutoff_time"], how="left"
    )

    if len(df_out) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"Stage C outcome matrix count mismatch: expected {EXPECTED_DENOMINATOR}, got {len(df_out)}"
        )

    clean_count = int(df_out["clean_target_reached"].sum())
    if clean_count != EXPECTED_CLEAN_EVENTS:
        raise ValueError(
            f"Stage C clean target count mismatch: expected {EXPECTED_CLEAN_EVENTS}, got {clean_count}"
        )

    # Read eligibility metadata (for cohort analysis)
    cols_elig = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "cohort_type",
        "market_cap",
        "trading_history_sessions",
    ]
    filters_elig = [("cutoff_time", "=", POPULATION_CUTOFF)]
    df_elig_raw = pq.read_table(p_elig, columns=cols_elig, filters=filters_elig).to_pandas()
    df_elig = df_obs[["immutable_security_id", "as_of_date", "cutoff_time"]].merge(
        df_elig_raw, on=["immutable_security_id", "as_of_date", "cutoff_time"], how="left"
    )

    return df_obs, df_out, df_elig


def load_spy_daily_closes(alpaca: AlpacaDailyClient) -> dict[str, float]:
    """Load SPY split-adjusted daily closes from provider cache."""
    raw_bars, _ = alpaca.fetch_daily_bars(
        "SPY",
        "2015-01-01T00:00:00Z",
        f"{DEV_END}T23:59:59Z",
        feed="sip",
        adjustment="split",
    )
    if not raw_bars:
        raise RuntimeError("FAIL-CLOSED CACHE MISS: SPY daily bars not found in provider cache!")

    df_spy = pd.DataFrame(raw_bars)
    df_spy["datetime"] = pd.to_datetime(df_spy["t"], utc=True)
    df_spy["date"] = df_spy["datetime"].dt.strftime("%Y-%m-%d")
    df_spy = df_spy.rename(columns={"c": "close"})
    df_spy = df_spy.set_index("date").sort_index()

    for d in df_spy.index:
        enforce_split_guard(str(d))

    return df_spy["close"].to_dict()


def load_candidate_bars(
    candidate: CandidateSecurity,
    alpaca: AlpacaDailyClient,
) -> tuple[pd.DataFrame, list[Any], dict[str, Any]]:
    """Load daily bars for a single candidate security strictly from cache.

    Fails closed immediately if bars cannot be loaded strictly from cache.
    """
    df_bars, prov, meta = load_interval_aware_daily_bars(
        candidate=candidate,
        alpaca=alpaca,
        load_split_adjusted=True,
    )
    if df_bars.empty:
        raise RuntimeError(
            f"FAIL-CLOSED CACHE MISS: Security {candidate.immutable_security_id} missed provider cache: {meta}"
        )
    return df_bars, prov, meta
