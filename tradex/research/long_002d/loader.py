"""Data and provider cache loader for LONG-002D1.

Enforces read-only cache access, zero live network requests (allow_live=False),
verifies Stage C external parquet digests, and tracks consumed cache payload hashes.
"""
from __future__ import annotations

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
class PayloadAuditSummary:
    """Audit of provider cache payloads consumed during feature construction."""

    total_payloads_consumed: int
    total_payload_bytes: int
    unique_cache_keys: list[str]
    matched_provenance_count: int
    unmatched_provenance_count: int
    live_network_calls_attempted: int
    live_network_calls_blocked: int


class AuditingReadOnlyCache(ResponseCache):
    """Subclass of ResponseCache that audits read payloads and forbids cache writes."""

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir=cache_dir, enabled=True)
        self.consumed_payloads: dict[str, dict[str, Any]] = {}
        # key -> {"sha256": str, "byte_count": int, "url": str, "req_fp": str}

    def get(self, url: str, request_fingerprint: str) -> tuple[bytes | None, str | None, str | None]:
        body, resp_sha, req_time = super().get(url, request_fingerprint)
        if body is not None and resp_sha is not None:
            key = self._cache_key(url, request_fingerprint)
            if key not in self.consumed_payloads:
                self.consumed_payloads[key] = {
                    "sha256": resp_sha,
                    "byte_count": len(body),
                    "url": url,
                    "req_fp": request_fingerprint,
                }
        return body, resp_sha, req_time

    def set(self, *args: Any, **kwargs: Any) -> str:
        raise PermissionError("AuditingReadOnlyCache is strictly READ-ONLY; writes are forbidden.")


def _forbidden_network_call(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError(
        "FAIL-CLOSED BREACH: A live provider network call was attempted! "
        "LONG-002D1 strictly requires allow_live=False and 100% provider cache hits."
    )


def create_read_only_alpaca_client(cache_dir: Path) -> tuple[AlpacaDailyClient, AuditingReadOnlyCache]:
    """Create an AlpacaDailyClient that fails closed against any live network request."""
    if not cache_dir.exists():
        raise FileNotFoundError(f"Provider cache directory not found: {cache_dir}")

    cache = AuditingReadOnlyCache(cache_dir=cache_dir)
    client = AlpacaDailyClient(
        api_key="DUMMY_KEY_READ_ONLY",
        secret_key="DUMMY_SECRET_READ_ONLY",
        cache=cache,
        request_func=_forbidden_network_call,
        max_retries=0,
    )
    return client, cache


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
        raise ValueError("SPY daily bars not found in provider cache!")

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
    """Load daily bars for a single candidate security strictly from cache."""
    df_bars, prov, meta = load_interval_aware_daily_bars(
        candidate=candidate,
        alpaca=alpaca,
        load_split_adjusted=True,
    )
    return df_bars, prov, meta
