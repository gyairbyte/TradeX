"""Tests for production strategy isolation, network fail-closed, and cache immutability."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.long_002d.loader import AuditingReadOnlyCache, create_read_only_alpaca_client
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


def test_approved_production_strategies_is_empty():
    """Verify that APPROVED_PRODUCTION_STRATEGIES remains empty (no strategies promoted)."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_network_provider_live_access_fails_closed(tmp_path: Path):
    """Verify that any live network request attempted by the client fails closed with an error."""
    client, _cache, tracker = create_read_only_alpaca_client(tmp_path)
    with pytest.raises(RuntimeError, match="FAIL-CLOSED BREACH"):
        client._request_func("https://data.alpaca.markets/v2/stocks/AAPL/bars")
    assert tracker.live_request_path_attempts == 1
    assert tracker.blocked_live_request_attempts == 1
    assert tracker.outbound_http_requests_executed == 0


def test_cache_is_strictly_read_only(tmp_path: Path):
    """Verify that the auditing cache prevents any write operations."""
    cache = AuditingReadOnlyCache(tmp_path)
    with pytest.raises(PermissionError, match="strictly READ-ONLY"):
        cache.set("http://test", "dummy_fp", b"data")
