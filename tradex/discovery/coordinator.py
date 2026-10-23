"""Discovery coordinator for bounded, resumable market opportunity scans (LONG-MVP-003).

Coordinates market-wide scans by:
  1. Resolving the selected universe.
  2. Establishing the applicable completed daily-bar session.
  3. Checking the persistent discovery cache for valid same-session results.
  4. Processing missing tickers in deterministic, bounded batches (default 100, max 200).
  5. Applying bounded concurrency (default max 4 workers) and provider pacing.
  6. Handling provider rate limiting by safely pausing and checkpointing.
  7. Persisting truthful batch telemetry through store.record_scan().
  8. Aggregating results using deterministic Long MVP ranking and 7/12/12 focus list caps.
  9. Preserving full uncapped qualifying results and complete failure provenance.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import resolve_provider
from tradex.discovery.cache import DiscoveryCache, compute_discovery_cache_key
from tradex.discovery.models import (
    DiscoveryCheckpoint,
    DiscoveryResult,
    ScanStatus,
    Scope,
)
from tradex.discovery.session import get_applicable_completed_session
from tradex.discovery.universe import resolve_universe
from tradex.screener.engine import (
    OBSERVATION_COLUMNS,
    SUCCESSFUL_STATUSES,
    build_long_focus_list,
    run_with_report,
)
from tradex.signals import long_term
from tradex.tracker import store

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 200
DEFAULT_DISCOVERY_WORKERS = 4
MAX_DISCOVERY_WORKERS = 4
DEFAULT_PACING_DELAY_SECONDS = 0.5


def _is_rate_limit_error(err: Any) -> bool:
    """Detect HTTP 429, Too Many Requests, or rate-limiting provider errors."""
    if err is None:
        return False
    msg = str(err).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg or "throttl" in msg


class DiscoveryCoordinator:
    """Orchestrates bounded, resumable discovery scans for Long MVP opportunities."""

    def __init__(
        self,
        *,
        settings: TradeXSettings | None = None,
        cache: DiscoveryCache | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings or load_runtime_settings()
        self.cache = cache or DiscoveryCache(settings=self.settings)
        self.sleeper = sleeper or time.sleep

    def run(
        self,
        scope: Scope | str,
        *,
        watchlist: list[str] | None = None,
        provider: str | None = None,
        earnings_source: str | None = None,
        earnings_buffer: int = 0,
        min_score: int = 40,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_workers: int = DEFAULT_DISCOVERY_WORKERS,
        pacing_delay_seconds: float = DEFAULT_PACING_DELAY_SECONDS,
        max_batches_per_run: int | None = None,
        as_of: datetime | None = None,
        retry_failed: bool = False,
        force_reset: bool = False,
        allow_stale_universe: bool = False,
        http_fetcher: Callable[[str], str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        min_listings_per_source: int | None = None,
    ) -> DiscoveryResult:
        """Run or resume a discovery scan for the specified scope."""
        # Operational bounds enforcement
        effective_batch_size = min(max(batch_size, 1), MAX_BATCH_SIZE)
        effective_workers = min(max(max_workers, 1), MAX_DISCOVERY_WORKERS)

        req_provider = resolve_provider(provider, settings=self.settings)
        req_er_source = (earnings_source or self.settings.earnings_data_source).lower().strip()

        # Step 1: Resolve Universe
        resolve_kwargs: dict[str, Any] = {
            "watchlist": watchlist,
            "settings": self.settings,
            "http_fetcher": http_fetcher,
            "allow_stale": allow_stale_universe,
        }
        if min_listings_per_source is not None:
            resolve_kwargs["min_listings_per_source"] = min_listings_per_source
        tickers, prov = resolve_universe(scope, **resolve_kwargs)
        total_universe_tickers = len(tickers)

        # Step 2: Establish applicable completed session
        market_session = get_applicable_completed_session(as_of)
        session_date = market_session.session_date

        # Step 3: Cache and Checkpoint resolution
        cache_key = compute_discovery_cache_key(
            strategy_id=long_term.STRATEGY_ID,
            strategy_version=long_term.STRATEGY_VERSION,
            universe_id=prov.universe_id,
            universe_hash=prov.snapshot_hash,
            session_date=session_date,
            requested_provider=req_provider,
            earnings_source=req_er_source,
            earnings_buffer=earnings_buffer,
            min_score=min_score,
            fallback_order=tuple(self.settings.data.ohlcv_fallback_order),
            max_retries=self.settings.data.ohlcv_max_retries,
        )

        if force_reset:
            self.cache.clear(cache_key)
            checkpoint = None
        else:
            checkpoint = self.cache.load(cache_key)

        if checkpoint is None:
            checkpoint = DiscoveryCheckpoint(
                version=1,
                cache_key=cache_key,
                universe_id=prov.universe_id,
                universe_hash=prov.snapshot_hash,
                session_date=session_date.isoformat(),
                provider=req_provider,
                earnings_source=req_er_source,
                earnings_buffer=earnings_buffer,
                min_score=min_score,
                strategy_id=long_term.STRATEGY_ID,
                strategy_version=long_term.STRATEGY_VERSION,
                attempted_tickers=[],
                completed_tickers=[],
                failed_tickers={},
                observations=[],
                results=[],
                status=ScanStatus.NOT_STARTED.value,
                updated_at=datetime.now(UTC).isoformat(),
                actual_providers=[],
                fallback_used=False,
            )

        completed_set = set(checkpoint.completed_tickers)
        failed_dict = dict(checkpoint.failed_tickers)
        actual_providers_set: set[str] = set(checkpoint.actual_providers)
        any_fallback_used: bool = checkpoint.fallback_used

        # Count tickers reused from pre-existing checkpoint BEFORE processing new batches
        initial_cached_count = len(completed_set) if (checkpoint and not force_reset) else 0

        if retry_failed:
            failed_set = set(failed_dict.keys())
            failed_dict.clear()
            # Prioritize retrying the failed tickers first, followed by unattempted tickers
            previously_failed = [t for t in tickers if t in failed_set]
            unattempted = [t for t in tickers if t not in completed_set and t not in failed_set]
            remaining_tickers = previously_failed + unattempted
        else:
            remaining_tickers = [t for t in tickers if t not in completed_set and t not in failed_dict]

        scan_status = ScanStatus.IN_PROGRESS
        status_message: str | None = None
        batches_processed = 0

        # Observations and results lookup tables
        obs_by_ticker: dict[str, dict[str, Any]] = {o["ticker"]: o for o in checkpoint.observations}
        results_by_ticker: dict[str, dict[str, Any]] = {r["ticker"]: r for r in checkpoint.results}

        # Step 5: Process bounded batches
        if not remaining_tickers:
            if failed_dict:
                scan_status = ScanStatus.COMPLETE_WITH_FAILURES
                status_message = f"Scan complete with {len(failed_dict)} failed ticker(s)."
            else:
                scan_status = ScanStatus.COMPLETE
                status_message = "Scan complete across the full universe."
        else:
            batches = [
                remaining_tickers[i : i + effective_batch_size]
                for i in range(0, len(remaining_tickers), effective_batch_size)
            ]

            for batch in batches:
                if max_batches_per_run is not None and batches_processed >= max_batches_per_run:
                    scan_status = ScanStatus.PAUSED
                    status_message = f"Paused after reaching max batch limit ({batches_processed} batch(es))."
                    break

                batch_num = batches_processed + 1
                total_batches = len(batches)
                if progress_callback:
                    progress_callback(
                        len(completed_set) + len(failed_dict),
                        total_universe_tickers,
                        f"Scanning batch {batch_num}/{total_batches} ({len(batch)} tickers)…",
                    )

                # Authoritative strategy scoring path
                batch_report = run_with_report(
                    batch,
                    timeframe="long",
                    min_score=min_score,
                    exclude_earnings_within=earnings_buffer if earnings_buffer > 0 else None,
                    max_workers=effective_workers,
                    provider=req_provider,
                    earnings_source=req_er_source,
                    completed_session=session_date,
                    settings=self.settings,
                )

                # Persist batch observations truthfully to the canonical store
                store.record_scan(
                    batch_report,
                    timeframe="long",
                    min_score=min_score,
                    tickers_scanned=batch,
                    settings=self.settings,
                )

                # Record batch outcomes
                if batch_report.actual_provider:
                    actual_providers_set.add(batch_report.actual_provider)
                if batch_report.fallback_used:
                    any_fallback_used = True

                rate_limited = False
                for _, obs_row in batch_report.observations.iterrows():
                    t = str(obs_row["ticker"]).upper()
                    st = obs_row["status"]
                    row_dict = obs_row.to_dict()
                    if not row_dict.get("provider"):
                        row_dict["provider"] = batch_report.actual_provider or req_provider

                    obs_by_ticker[t] = row_dict

                    if st in SUCCESSFUL_STATUSES:
                        completed_set.add(t)
                        failed_dict.pop(t, None)
                    else:
                        err_cat = row_dict.get("error_category") or "UnknownError"
                        err_msg = row_dict.get("error_message") or ""
                        failed_dict[t] = {
                            "error_category": err_cat,
                            "error_message": err_msg,
                        }
                        if _is_rate_limit_error(err_msg):
                            rate_limited = True

                # Record qualifying signal results
                if not batch_report.results.empty:
                    for _, res_row in batch_report.results.iterrows():
                        t = str(res_row["ticker"]).upper()
                        row_dict = res_row.to_dict()
                        if not row_dict.get("provider"):
                            row_dict["provider"] = batch_report.actual_provider or req_provider
                        results_by_ticker[t] = row_dict

                checkpoint.completed_tickers = sorted(completed_set)
                checkpoint.failed_tickers = failed_dict
                checkpoint.attempted_tickers = sorted(completed_set | set(failed_dict.keys()))
                checkpoint.observations = list(obs_by_ticker.values())
                checkpoint.results = list(results_by_ticker.values())
                checkpoint.actual_providers = sorted(actual_providers_set)
                checkpoint.fallback_used = any_fallback_used
                checkpoint.status = ScanStatus.IN_PROGRESS.value

                self.cache.save(checkpoint)
                batches_processed += 1

                if rate_limited:
                    scan_status = ScanStatus.PAUSED
                    status_message = "Data provider rate limit encountered. Scan paused to avoid throttling."
                    break

                if pacing_delay_seconds > 0:
                    self.sleeper(pacing_delay_seconds)

            # Check completion after loop
            if scan_status == ScanStatus.IN_PROGRESS:
                total_attempted = len(completed_set) + len(failed_dict)
                if total_attempted >= total_universe_tickers:
                    if failed_dict:
                        scan_status = ScanStatus.COMPLETE_WITH_FAILURES
                        status_message = f"Scan complete with {len(failed_dict)} failed ticker(s)."
                    else:
                        scan_status = ScanStatus.COMPLETE
                        status_message = "Scan complete across the full universe."
                else:
                    scan_status = ScanStatus.PAUSED
                    status_message = (
                        f"Partial scan: {total_attempted}/{total_universe_tickers} tickers processed."
                    )

        checkpoint.status = scan_status.value
        self.cache.save(checkpoint)

        # Step 6: Deterministic Long MVP ranking and display focus list
        if results_by_ticker:
            df_all = pd.DataFrame(list(results_by_ticker.values()))
            STATE_RANK = {"ENTER NOW": 0, "ARMED": 1, "QUALIFIED WAITLIST": 2}
            df_all["_state_rank"] = df_all["state"].map(lambda s: STATE_RANK.get(s, 99))
            all_qualifying = (
                df_all.sort_values(
                    by=["_state_rank", "score", "ticker"],
                    ascending=[True, False, True],
                )
                .drop(columns=["_state_rank"])
                .reset_index(drop=True)
            )
            focus_list = build_long_focus_list(all_qualifying)
        else:
            base_cols = [
                "ticker",
                "state",
                "primary_setup",
                "score",
                "last_close",
                "trigger",
                "invalidation",
                "atr_pct",
                "volume_ratio",
                "return_5",
                "return_20",
                "return_60",
                "days_until_earnings",
                "reasons",
                "provider",
            ]
            all_qualifying = pd.DataFrame(columns=base_cols)
            focus_list = pd.DataFrame(columns=base_cols)

        if obs_by_ticker:
            all_observations = pd.DataFrame(list(obs_by_ticker.values()), columns=OBSERVATION_COLUMNS)
        else:
            all_observations = pd.DataFrame(columns=OBSERVATION_COLUMNS)

        completed_count = len(completed_set)
        failed_count = len(failed_dict)
        attempted_count = completed_count + failed_count
        remaining_count = max(0, total_universe_tickers - attempted_count)

        insufficient_data_count = sum(
            1 for o in obs_by_ticker.values() if o.get("status") == "insufficient_data"
        )
        scored_count = sum(
            1 for o in obs_by_ticker.values() if o.get("status") in ("signal", "below_threshold")
        )
        qualifying_count = len(all_qualifying)
        cached_count = initial_cached_count

        failures_summary = {
            t: f"{info.get('error_category', 'Error')}: {info.get('error_message', '')}"
            for t, info in failed_dict.items()
        }

        is_partial = attempted_count < total_universe_tickers

        sorted_actual = sorted(actual_providers_set)
        if not sorted_actual:
            result_actual_provider = req_provider
        elif len(sorted_actual) == 1:
            result_actual_provider = sorted_actual[0]
        else:
            result_actual_provider = ", ".join(sorted_actual)

        return DiscoveryResult(
            scope=prov.scope,
            universe_provenance=prov,
            session_date=session_date,
            provider=req_provider,
            actual_provider=result_actual_provider,
            actual_providers=tuple(sorted_actual),
            fallback_used=any_fallback_used,
            total_tickers=total_universe_tickers,
            completed_count=completed_count,
            remaining_count=remaining_count,
            scored_count=scored_count,
            qualifying_count=qualifying_count,
            insufficient_data_count=insufficient_data_count,
            failed_count=failed_count,
            cached_count=cached_count,
            status=scan_status,
            focus_list=focus_list,
            all_qualifying=all_qualifying,
            all_observations=all_observations,
            failures=failures_summary,
            is_partial=is_partial,
            is_stale_universe=prov.is_stale,
            status_message=status_message,
        )
