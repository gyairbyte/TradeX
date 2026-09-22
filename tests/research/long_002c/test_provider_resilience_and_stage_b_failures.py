"""Regression tests for LONG-002C provider resilience, auditable retries, and Stage B failure isolation.

Proves:
1. Successful HTTP 200 + bars=None => genuine empty bars, not crash
2. Successful HTTP 200 + bars=[] => genuine empty bars
3. Request exception after retries => provider failure, not no_trading_bars
4. HTTP 429 after retry exhaustion => provider_rate_limited_unresolved, not no_trading_bars
5. HTTP 500 after retry exhaustion => provider_request_failed
6. Page 1 success + page 2 failure => incomplete fetch, not partial valid history
7. Complete successful pagination => normal Stage B evaluation
8. Cached successful empty response remains legitimate empty data
9. Provider failures cannot enter the frozen eligible/rejected census as ordinary eligibility results
10. Alpaca audit metrics tracking (requests, cache hits, retries, 429s, transport failures, exhausted retries, pagination incomplete)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from tradex.research.long_002c.bars import load_interval_aware_daily_bars
from tradex.research.long_002c.cache import ResponseCache
from tradex.research.long_002c.exceptions import (
    MalformedProviderResponse,
    ProviderDataUnavailable,
    ProviderPaginationIncomplete,
    ProviderRateLimitedUnresolved,
    ProviderRequestFailed,
)
from tradex.research.long_002c.frozen_manifest import build_frozen_pre_run_manifest_data
from tradex.research.long_002c.manifest import CandidateSecurity, TickerInterval
from tradex.research.long_002c.providers import AlpacaDailyClient, EdgarClient
from tradex.research.long_002c.screening import (
    screen_candidate_security,
    screen_candidates_manifest,
)


def _make_candidate(sym: str = "TEST") -> CandidateSecurity:
    return CandidateSecurity(
        immutable_security_id=f"FIGI_{sym}",
        primary_symbol=sym,
        cik="0001090872",
        company_name=f"{sym} Inc.",
        primary_exchange="XNYS",
        security_type="supported_common_stock",
        first_seen_date="2016-01-04",
        last_seen_date="2020-12-31",
        ticker_intervals=[
            TickerInterval(symbol=sym, start_date="2016-01-04", end_date="2020-12-31", confidence="single_symbol_known")
        ],
    )


def test_alpaca_successful_http_200_null_bars_genuine_empty() -> None:
    """HTTP 200 with bars: null returns empty list without error, classified as true_no_trading_bars."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"bars": null, "symbol": "TEST", "next_page_token": null}'
    mock_resp.json.return_value = {"bars": None, "symbol": "TEST", "next_page_token": None}

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=lambda *args, **kwargs: mock_resp,
        request_delay_seconds=0.0,
    )
    bars, prov = client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
    assert bars == []
    assert len(prov) == 1

    cand = _make_candidate("TEST")
    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=client,
        edgar=MagicMock(),
        trading_sessions=["2016-01-04"],
    )
    assert is_elig is False
    assert "true_no_trading_bars" in reasons
    assert details["is_provider_failure"] is False


def test_alpaca_successful_http_200_empty_list_genuine_empty() -> None:
    """HTTP 200 with bars: [] returns empty list without error, classified as true_no_trading_bars."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"bars": [], "symbol": "TEST", "next_page_token": null}'
    mock_resp.json.return_value = {"bars": [], "symbol": "TEST", "next_page_token": None}

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=lambda *args, **kwargs: mock_resp,
        request_delay_seconds=0.0,
    )
    bars, prov = client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
    assert bars == []
    assert len(prov) == 1

    cand = _make_candidate("TEST")
    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=client,
        edgar=MagicMock(),
        trading_sessions=["2016-01-04"],
    )
    assert is_elig is False
    assert "true_no_trading_bars" in reasons
    assert details["is_provider_failure"] is False


def test_alpaca_request_exception_after_retries_raises_provider_request_failed() -> None:
    """Transport exception after retries raises ProviderRequestFailed and classifies as provider failure."""
    def _fail(*args: Any, **kwargs: Any) -> requests.Response:
        raise requests.exceptions.ConnectionError("Connection dropped by peer")

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=_fail,
        request_delay_seconds=0.0,
        max_retries=2,
    )

    with pytest.raises(ProviderRequestFailed) as exc_info:
        client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
    assert exc_info.value.failure_type == "provider_request_failed"

    # Verify audit metrics
    metrics = client.get_audit_metrics()
    assert metrics["transport_failure_count"] >= 1
    assert metrics["exhausted_retry_count"] == 1

    # In Stage B screening, this must be classified as provider failure (NOT no_trading_bars)
    cand = _make_candidate("TEST")
    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=client,
        edgar=MagicMock(),
        trading_sessions=["2016-01-04"],
    )
    assert is_elig is False
    assert details["is_provider_failure"] is True
    assert "provider_request_failed" in reasons
    assert "true_no_trading_bars" not in reasons
    assert "no_trading_bars" not in reasons


def test_alpaca_http_429_after_retry_exhaustion_raises_provider_rate_limited() -> None:
    """HTTP 429 after retries raises ProviderRateLimitedUnresolved and is not treated as no_trading_bars."""
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.content = b'{"message": "rate limit exceeded"}'
    mock_429.headers = {"Retry-After": "0", "X-Ratelimit-Reset": "0"}

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=lambda *args, **kwargs: mock_429,
        request_delay_seconds=0.0,
        max_retries=2,
    )

    with pytest.raises(ProviderRateLimitedUnresolved) as exc_info:
        client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
    assert exc_info.value.failure_type == "provider_rate_limited_unresolved"

    metrics = client.get_audit_metrics()
    assert metrics["rate_limit_429_count"] >= 1
    assert metrics["exhausted_retry_count"] == 1

    cand = _make_candidate("TEST")
    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=client,
        edgar=MagicMock(),
        trading_sessions=["2016-01-04"],
    )
    assert is_elig is False
    assert details["is_provider_failure"] is True
    assert "provider_rate_limited_unresolved" in reasons
    assert "true_no_trading_bars" not in reasons


def test_alpaca_http_500_after_retry_exhaustion_raises_provider_request_failed() -> None:
    """HTTP 500 after retries raises ProviderRequestFailed."""
    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.content = b'{"message": "internal server error"}'
    mock_500.headers = {}

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=lambda *args, **kwargs: mock_500,
        request_delay_seconds=0.0,
        max_retries=1,
    )

    with pytest.raises(ProviderRequestFailed):
        client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")


def test_alpaca_page_1_success_page_2_failure_fails_closed() -> None:
    """Page 1 success followed by Page 2 failure raises ProviderPaginationIncomplete and does not return partial bars."""
    page_counter = 0

    def _page_responder(*args: Any, **kwargs: Any) -> requests.Response:
        nonlocal page_counter
        page_counter += 1
        resp = MagicMock()
        if page_counter == 1:
            resp.status_code = 200
            resp.content = b'{"bars": [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}], "next_page_token": "page2_token"}'
            resp.json.return_value = {
                "bars": [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}],
                "next_page_token": "page2_token",
            }
            return resp
        else:
            resp.status_code = 500
            resp.content = b'{"message": "server error on page 2"}'
            return resp

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=_page_responder,
        request_delay_seconds=0.0,
        max_retries=1,
    )

    with pytest.raises(ProviderPaginationIncomplete) as exc_info:
        client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")

    assert isinstance(exc_info.value, ProviderDataUnavailable)
    assert exc_info.value.page == 2
    assert exc_info.value.failure_type == "provider_pagination_incomplete"
    assert client.incomplete_pagination_count == 1

    # When called through load_interval_aware_daily_bars, partial bars must NOT be returned
    page_counter = 0
    cand = _make_candidate("TEST")
    df_bars, _prov, meta = load_interval_aware_daily_bars(
        candidate=cand,
        alpaca=client,
        warmup_start="2016-01-04",
        dev_end="2020-12-31",
    )
    assert df_bars.empty  # Incomplete bars discarded
    assert meta["provider_failure"]["failure_type"] == "provider_pagination_incomplete"

    # In screening, must fail closed as provider failure
    page_counter = 0
    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=client,
        edgar=MagicMock(),
        trading_sessions=["2016-01-04"],
    )
    assert is_elig is False
    assert details["is_provider_failure"] is True
    assert "provider_pagination_incomplete" in reasons


def test_alpaca_malformed_response_raises_malformed_provider_response() -> None:
    """Non-JSON response raises MalformedProviderResponse."""
    mock_bad = MagicMock()
    mock_bad.status_code = 200
    mock_bad.content = b"not json"
    mock_bad.json.side_effect = ValueError("Invalid JSON")

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=lambda *args, **kwargs: mock_bad,
        request_delay_seconds=0.0,
        max_retries=1,
    )

    with pytest.raises(MalformedProviderResponse) as exc_info:
        client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")

    assert isinstance(exc_info.value, ProviderDataUnavailable)
    assert exc_info.value.failure_type == "malformed_provider_response"


def test_alpaca_complete_successful_pagination_returns_all_bars() -> None:
    """Normal multi-page pagination completes to exhaustion and returns all bars."""
    page_counter = 0

    def _page_responder(*args: Any, **kwargs: Any) -> requests.Response:
        nonlocal page_counter
        page_counter += 1
        resp = MagicMock()
        resp.status_code = 200
        if page_counter == 1:
            resp.content = b'{"bars": [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}], "next_page_token": "page2_token"}'
            resp.json.return_value = {
                "bars": [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}],
                "next_page_token": "page2_token",
            }
        else:
            resp.content = b'{"bars": [{"t": "2016-01-05T05:00:00Z", "o": 51.0, "h": 53.0, "l": 50.0, "c": 52.0, "v": 1100000}], "next_page_token": null}'
            resp.json.return_value = {
                "bars": [{"t": "2016-01-05T05:00:00Z", "o": 51.0, "h": 53.0, "l": 50.0, "c": 52.0, "v": 1100000}],
                "next_page_token": None,
            }
        return resp

    client = AlpacaDailyClient(
        api_key="TEST_K",
        secret_key="TEST_S",
        request_func=_page_responder,
        request_delay_seconds=0.0,
    )
    bars, _prov = client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
    assert len(bars) == 2
    assert client.network_requests_count == 2
    assert client.incomplete_pagination_count == 0


def test_cached_successful_empty_response_remains_legitimate_empty_data() -> None:
    """Cached response with genuine empty bars increments cache_hits and returns empty data."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"bars": null, "symbol": "TEST", "next_page_token": null}'
    mock_resp.json.return_value = {"bars": None, "symbol": "TEST", "next_page_token": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ResponseCache(cache_dir=Path(tmpdir))
        client = AlpacaDailyClient(
            api_key="TEST_K",
            secret_key="TEST_S",
            request_func=lambda *args, **kwargs: mock_resp,
            request_delay_seconds=0.0,
            cache=cache,
        )
        # First call populates cache
        b1, _ = client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
        assert b1 == []
        assert client.network_requests_count == 1

        # Second call reads from cache
        b2, _ = client.fetch_daily_bars("TEST", "2016-01-04T00:00:00Z", "2020-12-31T23:59:59Z")
        assert b2 == []
        assert client.cache_hits_count == 1


def test_provider_failures_cannot_enter_frozen_manifest(tmp_path: Path) -> None:
    """A manifest containing any unresolved provider failures is rejected from freezing."""
    dummy_disc = tmp_path / "discovery_manifest.json"
    dummy_disc.write_text('{"candidates": []}', encoding="utf-8")

    summary_with_failure = {
        "total_evaluated": 10,
        "eligible_count": 5,
        "rejected_count": 4,
        "provider_failures_count": 1,
        "unresolved_provider_failures_count": 1,
        "genuine_no_bars_count": 2,
        "eligible_security_ids": ["SEC_1", "SEC_2", "SEC_3", "SEC_4", "SEC_5"],
        "rejected_security_ids": ["SEC_6", "SEC_7", "SEC_8", "SEC_9"],
        "provider_failed_security_ids": ["SEC_10"],
        "provider_failure_reason_counts": {"provider_request_failed": 1},
        "rejection_reason_counts": {"price_below_5": 2, "true_no_trading_bars": 2},
    }

    with pytest.raises(ValueError) as exc_info:
        build_frozen_pre_run_manifest_data(
            discovery_manifest_path=dummy_disc,
            stage_b_eligible_ids=["SEC_1", "SEC_2", "SEC_3", "SEC_4", "SEC_5"],
            stage_b_summary=summary_with_failure,
        )
    assert "unresolved provider failures remain" in str(exc_info.value)


def test_screen_candidates_manifest_isolates_provider_failures() -> None:
    """screen_candidates_manifest keeps provider failures out of eligible and rejected lists."""
    cands = [_make_candidate("OK_SYM"), _make_candidate("FAIL_SYM")]

    mock_alpaca = MagicMock()
    def _mock_fetch(sym: str, *args: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], list[Any]]:
        if sym == "FAIL_SYM":
            raise ProviderRequestFailed("HTTP 500 internal server error", symbol=sym, status_code=500)
        return (
            [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}],
            [],
        )
    mock_alpaca.fetch_daily_bars.side_effect = _mock_fetch
    mock_alpaca.get_audit_metrics.return_value = {"network_requests_count": 2}

    mock_edgar = MagicMock(spec=EdgarClient)
    mock_edgar.fetch_company_facts.return_value = (None, [])
    mock_edgar.fetch_submissions.return_value = (None, [])

    elig, rej, summary = screen_candidates_manifest(
        candidates=cands,
        alpaca=mock_alpaca,
        edgar=mock_edgar,
    )

    assert "FIGI_FAIL_SYM" not in elig
    assert "FIGI_FAIL_SYM" not in rej
    assert "FIGI_FAIL_SYM" in summary["provider_failed_security_ids"]
    assert summary["provider_failures_count"] == 1
    assert summary["unresolved_provider_failures_count"] == 1
    assert "provider_request_failed" in summary["provider_failure_reason_counts"]
