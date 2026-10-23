"""Tests for discovery coordinator batching, resumption, and ranking (LONG-MVP-003)."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.config import settings_from_mapping
from tradex.data.fetcher import ProviderDataUnavailableError
from tradex.discovery.coordinator import DiscoveryCoordinator
from tradex.discovery.models import ScanStatus, Scope
from tradex.screener.engine import ScanReport


def _make_dummy_long_df(ticker: str, session_date: date) -> pd.DataFrame:
    """Generate 250 bars ending on session_date with realistic prices."""
    dates = pd.date_range(end=session_date.isoformat(), periods=250, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": [150.0] * 250,
            "high": [155.0] * 250,
            "low": [148.0] * 250,
            "close": [152.0] * 250,
            "volume": [2_000_000] * 250,
        },
        index=dates,
    )


def test_coordinator_batch_chunking_and_pacing(tmp_path):
    """Coordinator divides tickers into bounded batches and records truthful progress."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )

    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)

    # 5 tickers with batch_size=2 -> 3 batches (2, 2, 1)
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    calls = []

    def mock_run_with_report(batch, **kwargs):
        calls.append(list(batch))
        rows = [
            {
                "ticker": t,
                "score": 80,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Trend Quality: 30",
                "provider": "schwab",
                "state": "ENTER NOW",
                "primary_setup": "momentum_continuation",
                "matched_setups": "momentum_continuation",
                "qualified": True,
            }
            for t in batch
        ]
        obs = [
            {
                "ticker": t,
                "status": "signal",
                "score": 80,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Trend Quality: 30",
                "provider": "schwab",
                "strategy_id": "long_mvp",
                "strategy_version": "v1",
                "state": "ENTER NOW",
                "primary_setup": "momentum_continuation",
                "matched_setups": "momentum_continuation",
                "qualified": True,
                "error_category": None,
                "error_message": None,
                "component_scores": None,
                "trigger": None,
                "invalidation": None,
                "atr_pct": 0.03,
                "return_5": 0.01,
                "return_20": 0.05,
                "return_60": 0.15,
            }
            for t in batch
        ]
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures={},
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=len(batch),
            total_scored=len(batch),
            total_signals=len(batch),
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_with_report),
        patch("tradex.discovery.coordinator.store.record_scan") as mock_record,
    ):
        res = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_workers=2,
            as_of=fixed_as_of,
        )

    assert calls == [["AAPL", "MSFT"], ["GOOGL", "AMZN"], ["NVDA"]]
    assert mock_record.call_count == 3
    assert res.status == ScanStatus.COMPLETE
    assert res.completed_count == 5
    assert res.remaining_count == 0
    assert len(res.all_qualifying) == 5


def test_coordinator_resume_from_checkpoint(tmp_path):
    """Coordinator skips already-completed tickers when resuming an interrupted scan."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)

    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    def mock_run_batch(batch, **kwargs):
        rows = [
            {"ticker": t, "score": 85, "state": "ENTER NOW", "primary_setup": "momentum_continuation"}
            for t in batch
        ]
        obs = [
            {"ticker": t, "status": "signal", "score": 85, "state": "ENTER NOW", "provider": "schwab"}
            for t in batch
        ]
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures={},
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=len(batch),
            total_scored=len(batch),
            total_signals=len(batch),
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    # First run: process only 1 batch of 2 tickers (max_batches_per_run=1)
    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_batch),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        res_part = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            as_of=fixed_as_of,
        )

    assert res_part.status == ScanStatus.PAUSED
    assert res_part.is_partial is True
    assert res_part.completed_count == 2
    assert res_part.remaining_count == 2

    # Second run: resume scan -> should process ONLY the remaining 2 tickers
    resumed_calls = []

    def mock_run_resumed(batch, **kwargs):
        resumed_calls.append(list(batch))
        return mock_run_batch(batch, **kwargs)

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_resumed),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        res_full = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            as_of=fixed_as_of,
        )

    # Only remaining 2 tickers should have been fetched in the resumed pass
    assert resumed_calls == [["GOOGL", "AMZN"]]
    assert res_full.status == ScanStatus.COMPLETE
    assert res_full.completed_count == 4
    assert res_full.remaining_count == 0
    assert len(res_full.all_qualifying) == 4


def test_coordinator_rate_limit_interruption(tmp_path):
    """Coordinator safely pauses and checkpoints when provider returns 429 rate limit."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)

    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    def mock_run_rate_limited(batch, **kwargs):
        # Fail with 429 rate limit
        obs = [
            {
                "ticker": t,
                "status": "fetch_failure",
                "score": None,
                "provider": "schwab",
                "error_category": "ProviderTransientError",
                "error_message": "HTTP 429: Too Many Requests (Rate limit exceeded)",
            }
            for t in batch
        ]
        return ScanReport(
            results=pd.DataFrame(),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures={t: ProviderDataUnavailableError("HTTP 429 rate limit") for t in batch},
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=0,
            total_scored=0,
            total_signals=0,
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_rate_limited),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        res = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            as_of=fixed_as_of,
        )

    assert res.status == ScanStatus.PAUSED
    assert "rate limit" in (res.status_message or "").lower()
    assert res.failed_count == 2  # First batch failed with 429, second batch was not attempted
    assert res.remaining_count == 2


def test_coordinator_long_focus_caps_and_ranking(tmp_path):
    """Combined discovery results apply 7/12/12 caps while preserving full uncapped table."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)

    # Generate 50 tickers: 10 ENTER NOW, 15 ARMED, 15 QUALIFIED WAITLIST, 10 BELOW
    candidates = []
    for i in range(10):
        candidates.append({"ticker": f"EN_{i:02d}", "score": 90 - i, "state": "ENTER NOW"})
    for i in range(15):
        candidates.append({"ticker": f"AR_{i:02d}", "score": 79 - i, "state": "ARMED"})
    for i in range(15):
        candidates.append({"ticker": f"QW_{i:02d}", "score": 69 - i, "state": "QUALIFIED WAITLIST"})

    tickers = [c["ticker"] for c in candidates]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    def mock_run_all(batch, **kwargs):
        cand_map = {c["ticker"]: c for c in candidates}
        rows = [
            {
                "ticker": t,
                "score": cand_map[t]["score"],
                "state": cand_map[t]["state"],
                "primary_setup": "momentum_continuation",
                "last_close": 100.0,
                "trigger": "Trigger",
                "invalidation": "Inv",
                "atr_pct": 0.03,
                "volume_ratio": 2.0,
                "return_5": 0.02,
                "return_20": 0.08,
                "return_60": 0.20,
                "days_until_earnings": 15,
                "reasons": "Reasons",
                "provider": "schwab",
            }
            for t in batch
            if t in cand_map
        ]
        obs = [
            {
                "ticker": t,
                "status": "signal",
                "score": cand_map[t]["score"],
                "state": cand_map[t]["state"],
                "provider": "schwab",
            }
            for t in batch
        ]
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures={},
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=len(batch),
            total_scored=len(batch),
            total_signals=len(rows),
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_all),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        res = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=50,
            as_of=fixed_as_of,
        )

    # Caps: 7 ENTER NOW + 12 ARMED + 12 QUALIFIED WAITLIST = 31 max focus list
    assert len(res.focus_list) == 31
    focus_states = res.focus_list["state"].value_counts().to_dict()
    assert focus_states["ENTER NOW"] == 7
    assert focus_states["ARMED"] == 12
    assert focus_states["QUALIFIED WAITLIST"] == 12

    # Full uncapped table contains all 40 qualifying candidates
    assert len(res.all_qualifying) == 40
    # Deterministic ranking: ENTER NOW first, then score descending
    assert res.focus_list.iloc[0]["state"] == "ENTER NOW"
    assert res.focus_list.iloc[0]["score"] == 90


def test_coordinator_tracks_mixed_providers_and_fallback(tmp_path):
    """Coordinator truthfully aggregates actual providers and fallback status across batches."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)

    tickers = ["AAPL", "MSFT"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    batch_idx = 0

    def mock_run_mixed(batch, **kwargs):
        nonlocal batch_idx
        batch_idx += 1
        prov = "alpaca" if batch_idx == 1 else "yahoo"
        fb = batch_idx == 2
        t = batch[0]
        rows = [
            {
                "ticker": t,
                "score": 85,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Breakout",
                "provider": prov,
                "state": "ENTER NOW",
                "primary_setup": "breakout_expansion",
                "matched_setups": "breakout_expansion",
                "qualified": True,
            }
        ]
        obs = [
            {
                "ticker": t,
                "status": "signal",
                "score": 85,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Breakout",
                "provider": prov,
                "strategy_id": "long_mvp",
                "strategy_version": "v1",
                "state": "ENTER NOW",
                "primary_setup": "breakout_expansion",
                "matched_setups": "breakout_expansion",
                "qualified": True,
                "error_category": None,
                "error_message": None,
                "component_scores": None,
                "trigger": None,
                "invalidation": None,
                "atr_pct": 0.03,
                "return_5": 0.01,
                "return_20": 0.05,
                "return_60": 0.15,
            }
        ]
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="alpaca",
            actual_provider=prov,
            fallback_used=fb,
            providers_attempted=("alpaca",) if not fb else ("alpaca", "yahoo"),
            failures={},
            total_requested=1,
            total_fetch_eligible=1,
            total_fetch_attempted=1,
            total_retries=1 if fb else 0,
            total_fetched=1,
            total_scored=1,
            total_signals=1,
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_mixed),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        res = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=1,
            as_of=fixed_as_of,
        )

    assert res.actual_provider == "alpaca, yahoo"
    assert res.actual_providers == ("alpaca", "yahoo")
    assert res.fallback_used is True
    assert set(res.focus_list["provider"]) == {"alpaca", "yahoo"}


def test_coordinator_cached_count_fresh_vs_resumed(tmp_path):
    """cached_count counts reused checkpoint tickers before new batches, reporting 0 on fresh scan."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    def mock_run_simple(batch, **kwargs):
        rows = [
            {
                "ticker": t,
                "score": 80,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Trend",
                "provider": "schwab",
                "state": "ENTER NOW",
                "primary_setup": "momentum_continuation",
                "matched_setups": "momentum_continuation",
                "qualified": True,
            }
            for t in batch
        ]
        obs = [
            {
                "ticker": t,
                "status": "signal",
                "score": 80,
                "last_close": 150.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "days_until_earnings": 10,
                "reasons": "Trend",
                "provider": "schwab",
                "strategy_id": "long_mvp",
                "strategy_version": "v1",
                "state": "ENTER NOW",
                "primary_setup": "momentum_continuation",
                "matched_setups": "momentum_continuation",
                "qualified": True,
                "error_category": None,
                "error_message": None,
                "component_scores": None,
                "trigger": None,
                "invalidation": None,
                "atr_pct": 0.03,
                "return_5": 0.01,
                "return_20": 0.05,
                "return_60": 0.15,
            }
            for t in batch
        ]
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures={},
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=len(batch),
            total_scored=len(batch),
            total_signals=len(batch),
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_simple),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        # Run 1: Fresh scan, 1 batch of 2 tickers
        res1 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            as_of=fixed_as_of,
        )
        assert res1.cached_count == 0  # 0 reused from cache on fresh scan
        assert res1.completed_count == 2
        assert res1.remaining_count == 2
        assert res1.is_partial is True

        # Run 2: Resume scan, next batch of 2 tickers
        res2 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            as_of=fixed_as_of,
        )
        assert res2.cached_count == 2  # 2 reused from checkpoint prior to batch 2
        assert res2.completed_count == 4
        assert res2.remaining_count == 0
        assert res2.is_partial is False

        # Run 3: View checkpoint without fetching (max_batches_per_run=0)
        res3 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=0,
            as_of=fixed_as_of,
        )
        assert res3.cached_count == 4  # All 4 reused from checkpoint
        assert res3.completed_count == 4


def test_coordinator_partial_scan_retry_failed_and_continue(tmp_path):
    """Failed tickers in a partial scan can be retried immediately without waiting for full completion."""
    cache_dir = tmp_path / "cache"
    settings = settings_from_mapping(
        {
            "TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir),
            "TRADEX_DB_PATH": str(tmp_path / "signals.db"),
        }
    )
    coordinator = DiscoveryCoordinator(settings=settings, sleeper=lambda _: None)
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    fixed_as_of = datetime(2026, 10, 21, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    # Batch 1: AAPL succeeds, MSFT fails
    attempt_count = 0

    def mock_run_flaky(batch, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        rows = []
        obs = []
        failures = {}
        for t in batch:
            if t == "MSFT" and attempt_count == 1:
                # MSFT fails on first attempt
                failures[t] = ProviderDataUnavailableError("Rate limit exceeded")
                obs.append(
                    {
                        "ticker": t,
                        "status": "fetch_failed",
                        "score": None,
                        "last_close": None,
                        "volume_ratio": None,
                        "rsi": None,
                        "days_until_earnings": None,
                        "reasons": None,
                        "provider": "schwab",
                        "strategy_id": "long_mvp",
                        "strategy_version": "v1",
                        "state": None,
                        "primary_setup": None,
                        "matched_setups": None,
                        "qualified": False,
                        "error_category": "ProviderDataUnavailableError",
                        "error_message": "Rate limit exceeded",
                        "component_scores": None,
                        "trigger": None,
                        "invalidation": None,
                        "atr_pct": None,
                        "return_5": None,
                        "return_20": None,
                        "return_60": None,
                    }
                )
            else:
                # Normal success
                rows.append(
                    {
                        "ticker": t,
                        "score": 80,
                        "last_close": 150.0,
                        "volume_ratio": 2.0,
                        "rsi": 60.0,
                        "days_until_earnings": 10,
                        "reasons": "Trend",
                        "provider": "schwab",
                        "state": "ENTER NOW",
                        "primary_setup": "momentum_continuation",
                        "matched_setups": "momentum_continuation",
                        "qualified": True,
                    }
                )
                obs.append(
                    {
                        "ticker": t,
                        "status": "signal",
                        "score": 80,
                        "last_close": 150.0,
                        "volume_ratio": 2.0,
                        "rsi": 60.0,
                        "days_until_earnings": 10,
                        "reasons": "Trend",
                        "provider": "schwab",
                        "strategy_id": "long_mvp",
                        "strategy_version": "v1",
                        "state": "ENTER NOW",
                        "primary_setup": "momentum_continuation",
                        "matched_setups": "momentum_continuation",
                        "qualified": True,
                        "error_category": None,
                        "error_message": None,
                        "component_scores": None,
                        "trigger": None,
                        "invalidation": None,
                        "atr_pct": 0.03,
                        "return_5": 0.01,
                        "return_20": 0.05,
                        "return_60": 0.15,
                    }
                )
        return ScanReport(
            results=pd.DataFrame(rows),
            requested_provider="schwab",
            actual_provider="schwab",
            fallback_used=False,
            providers_attempted=("schwab",),
            failures=failures,
            total_requested=len(batch),
            total_fetch_eligible=len(batch),
            total_fetch_attempted=len(batch),
            total_retries=0,
            total_fetched=len(rows),
            total_scored=len(rows),
            total_signals=len(rows),
            total_below_threshold=0,
            total_insufficient_data=0,
            total_earnings_excluded=0,
            observations=pd.DataFrame(obs),
            min_score=40,
            completed_session=date(2026, 10, 21),
        )

    with (
        patch("tradex.discovery.coordinator.run_with_report", side_effect=mock_run_flaky),
        patch("tradex.discovery.coordinator.store.record_scan"),
    ):
        # Step 1: Initial pass runs batch 1 (AAPL, MSFT). MSFT fails.
        res1 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            as_of=fixed_as_of,
        )
        assert res1.is_partial is True
        assert res1.completed_count == 1  # AAPL
        assert res1.failed_count == 1  # MSFT
        assert "MSFT" in res1.failures

        # Step 2: Retry failed tickers while still partial. MSFT is retried first in batch with GOOGL.
        res2 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            retry_failed=True,
            as_of=fixed_as_of,
        )
        # MSFT succeeded on retry, GOOGL succeeded. AAPL is preserved.
        assert res2.is_partial is True
        assert res2.completed_count == 3  # AAPL, MSFT, and GOOGL
        assert res2.failed_count == 0
        assert res2.remaining_count == 1  # AMZN remains

        # Step 3: Continue scan for remaining unattempted tickers
        res3 = coordinator.run(
            Scope.MY_WATCHLIST,
            watchlist=tickers,
            batch_size=2,
            max_batches_per_run=1,
            as_of=fixed_as_of,
        )
        assert res3.is_partial is False
        assert res3.completed_count == 4
        assert res3.failed_count == 0
        assert res3.remaining_count == 0


