"""Tests for discovery caching and checkpointing (LONG-MVP-003)."""

from __future__ import annotations

import json
from datetime import date

from tradex.discovery.cache import (
    CURRENT_CHECKPOINT_VERSION,
    DiscoveryCache,
    compute_discovery_cache_key,
)
from tradex.discovery.models import DiscoveryCheckpoint, ScanStatus


def test_compute_discovery_cache_key_deterministic():
    """Cache key is deterministic and sensitive to every material input."""
    k1 = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
    )
    k2 = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
    )
    assert k1 == k2

    # Session date change
    k_session = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 22),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
    )
    assert k1 != k_session

    # Min score change
    k_score = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=60,
    )
    assert k1 != k_score

    # Provider change
    k_provider = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="yahoo",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
    )
    assert k1 != k_provider

    # Universe hash change
    k_univ = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash999",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
    )
    assert k1 != k_univ

    # Fallback order change
    k_fallback = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
        fallback_order=("yahoo",),
    )
    assert k1 != k_fallback

    # Max retries change
    k_retries = compute_discovery_cache_key(
        strategy_id="long_mvp",
        strategy_version="v1",
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date=date(2026, 10, 21),
        requested_provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
        max_retries=2,
    )
    assert k1 != k_retries


def test_discovery_cache_save_and_load(tmp_path):
    """DiscoveryCache atomically saves checkpoint with checksum and reloads it."""
    cache = DiscoveryCache(cache_dir=tmp_path)
    k = "test_key_123"
    cp = DiscoveryCheckpoint(
        version=CURRENT_CHECKPOINT_VERSION,
        cache_key=k,
        universe_id="all_us_stocks",
        universe_hash="hash123",
        session_date="2026-10-21",
        provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
        strategy_id="long_mvp",
        strategy_version="v1",
        attempted_tickers=["AAPL", "MSFT"],
        completed_tickers=["AAPL"],
        failed_tickers={"MSFT": {"error_category": "ProviderDataUnavailableError", "error_message": "insufficient bars"}},
        observations=[
            {"ticker": "AAPL", "status": "signal", "score": 85},
            {"ticker": "MSFT", "status": "insufficient_data", "score": None},
        ],
        results=[{"ticker": "AAPL", "score": 85, "state": "ENTER NOW"}],
        status=ScanStatus.IN_PROGRESS.value,
        updated_at="2026-10-22T08:00:00Z",
    )

    cache.save(cp)
    loaded = cache.load(k)
    assert loaded is not None
    assert loaded.cache_key == k
    assert loaded.completed_tickers == ["AAPL"]
    assert "MSFT" in loaded.failed_tickers
    assert len(loaded.observations) == 2
    assert loaded.status == ScanStatus.IN_PROGRESS.value
    assert loaded.checksum != ""


def test_discovery_cache_detects_corruption(tmp_path):
    """Corrupted checkpoint payload or mismatched checksum is detected and safely rejected."""
    cache = DiscoveryCache(cache_dir=tmp_path)
    k = "corrupt_key"
    cp = DiscoveryCheckpoint(
        version=CURRENT_CHECKPOINT_VERSION,
        cache_key=k,
        universe_id="sp500",
        universe_hash="hash",
        session_date="2026-10-21",
        provider="schwab",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
        strategy_id="long_mvp",
        strategy_version="v1",
        attempted_tickers=["AAPL"],
        completed_tickers=["AAPL"],
        failed_tickers={},
        observations=[],
        results=[],
        status=ScanStatus.COMPLETE.value,
        updated_at="2026-10-22T08:00:00Z",
    )
    cache.save(cp)

    file_path = tmp_path / f"discovery_{k}.json"
    assert file_path.exists()

    # Tamper with file content
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["completed_tickers"] = ["AAPL", "TAMPERED"]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Checksum will no longer match
    loaded = cache.load(k)
    assert loaded is None


def test_discovery_cache_clear(tmp_path):
    """Cache clear removes file."""
    cache = DiscoveryCache(cache_dir=tmp_path)
    k = "to_delete"
    cp = DiscoveryCheckpoint(
        version=CURRENT_CHECKPOINT_VERSION,
        cache_key=k,
        universe_id="ndx",
        universe_hash="h",
        session_date="2026-10-21",
        provider="yahoo",
        earnings_source="yahoo",
        earnings_buffer=0,
        min_score=40,
        strategy_id="long_mvp",
        strategy_version="v1",
        attempted_tickers=[],
        completed_tickers=[],
        failed_tickers={},
        observations=[],
        results=[],
        status=ScanStatus.NOT_STARTED.value,
        updated_at="",
    )
    cache.save(cp)
    assert (tmp_path / f"discovery_{k}.json").exists()

    assert cache.clear(k) is True
    assert not (tmp_path / f"discovery_{k}.json").exists()
