"""Deterministic credential-free tests for MassiveReferenceClient adapter."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

from tradex.pit.massive_reference import (
    MassiveReferenceClient,
    sanitize_text,
)
from tradex.pit.models import ReferenceObservationStatus


def test_missing_api_key_raises_auth_error() -> None:
    client = MassiveReferenceClient(api_key="")
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveAuthError"
    assert "API key is required" in res.error_message


def test_exact_active_known_record() -> None:
    fake_body = {
        "request_id": "req-act-001",
        "results": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "market": "stocks",
                "locale": "us",
                "active": True,
                "type": "CS",
                "primary_exchange": "XNAS",
                "cik": "0000320193",
                "composite_figi": "BBG000B9XRY4",
                "share_class_figi": "BBG001S5N8V8",
                "last_updated_utc": "2026-08-28T20:00:00Z",
                "delisted_utc": None,
            }
        ],
        "status": "OK",
    }

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        assert "active=true" in url
        assert "ticker=AAPL" in url
        return json.dumps(fake_body).encode("utf-8"), 200, {"X-Request-Id": "header-req-1"}

    client = MassiveReferenceClient(
        api_key="TESTKEY123",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))

    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.symbol == "AAPL"
    assert res.provider_ticker == "AAPL"
    assert res.provider_name == "Apple Inc."
    assert res.provider_market == "stocks"
    assert res.provider_locale == "us"
    assert res.provider_active is True
    assert res.provider_type_code == "CS"
    assert res.provider_primary_exchange == "XNAS"
    assert res.provider_cik == "0000320193"
    assert res.provider_composite_figi == "BBG000B9XRY4"
    assert res.provider_share_class_figi == "BBG001S5N8V8"
    assert res.provider_last_updated_at == datetime(2026, 8, 28, 20, 0, tzinfo=UTC)
    assert res.provider_delisted_at is None
    assert "header-req-1" in res.request_ids or "req-act-001" in res.request_ids
    assert "delisted_utc" in res.missing_fields
    assert "cik" not in res.missing_fields


def test_active_zero_fallback_to_inactive_known() -> None:
    calls: list[str] = []

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        calls.append(url)
        if "active=true" in url:
            return json.dumps({"request_id": "req-1", "results": []}).encode("utf-8"), 200, {}
        # inactive query
        body = {
            "request_id": "req-2",
            "results": [
                {
                    "ticker": "OLDTICK",
                    "name": "Old Ticker Corp",
                    "market": "stocks",
                    "locale": "us",
                    "active": False,
                    "type": "CS",
                    "primary_exchange": "XNAS",
                    "cik": "0000111222",
                    "delisted_utc": "2025-01-15",
                }
            ],
        }
        return json.dumps(body).encode("utf-8"), 200, {}

    client = MassiveReferenceClient(
        api_key="TESTKEY123",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("OLDTICK", date(2026, 8, 30))

    assert len(calls) == 2
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_active is False
    assert res.provider_delisted_at == "2025-01-15"
    assert "req-1" in res.request_ids
    assert "req-2" in res.request_ids


def test_active_and_inactive_zero_results_yields_unavailable() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return json.dumps({"request_id": "req-empty", "results": []}).encode("utf-8"), 200, {}

    client = MassiveReferenceClient(
        api_key="TESTKEY123",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("NONEXISTENT", date(2026, 8, 30))

    assert res.observation_status == ReferenceObservationStatus.UNAVAILABLE
    assert res.provider_ticker is None
    assert res.error_category == "MassiveDataUnavailableError"
    assert "NONEXISTENT" in res.error_message


def test_multiple_matching_rows_yields_ambiguous() -> None:
    fake_body = {
        "request_id": "req-ambig-1",
        "results": [
            {
                "ticker": "AMBIG",
                "name": "Ambig Alpha Inc",
                "primary_exchange": "XNYS",
                "cik": "0000100001",
            },
            {
                "ticker": "AMBIG",
                "name": "Ambig Beta Corp",
                "primary_exchange": "XNAS",
                "cik": "0000100002",
            },
        ],
    }

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return json.dumps(fake_body).encode("utf-8"), 200, {}

    client = MassiveReferenceClient(
        api_key="TESTKEY123",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AMBIG", date(2026, 8, 30))

    assert res.observation_status == ReferenceObservationStatus.AMBIGUOUS
    assert res.error_category == "MassiveAmbiguousIdentityError"
    parsed_fact = json.loads(res.fact_json)
    assert "candidates" in parsed_fact
    assert len(parsed_fact["candidates"]) == 2
    # Deterministically sorted candidates preserved
    assert parsed_fact["candidates"][0]["name"] == "Ambig Alpha Inc"
    assert parsed_fact["candidates"][1]["name"] == "Ambig Beta Corp"


def test_otc_market_record_preserved_truthfully() -> None:
    fake_body = {
        "request_id": "req-otc-1",
        "results": [
            {
                "ticker": "OTCK",
                "name": "OTC Pink Corp",
                "market": "otc",
                "locale": "us",
                "active": True,
                "type": "CS",
                "primary_exchange": "OTCM",
            }
        ],
    }

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return json.dumps(fake_body).encode("utf-8"), 200, {}

    client = MassiveReferenceClient(
        api_key="TESTKEY123",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("OTCK", date(2026, 8, 30))

    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_market == "otc"
    assert res.provider_primary_exchange == "OTCM"
    assert res.provider_type_code == "CS"


def test_http_401_auth_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Unauthorized"}', 401, {}

    client = MassiveReferenceClient(api_key="BADKEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveAuthError"


def test_http_403_entitlement_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Forbidden"}', 403, {}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveEntitlementError"


def test_http_429_rate_limit_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Too Many Requests"}', 429, {"Retry-After": "60"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveRateLimitError"
    assert "Retry-After: 60" in res.error_message


def test_http_500_transient_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Internal Server Error"}', 500, {}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveTransientError"


def test_malformed_json_response_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b"<html>Not JSON</html>", 200, {}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"


def test_secret_scrubbing_regression() -> None:
    raw_error = "Connection failed to https://api.massive.com/v3?ticker=AAPL&apiKey=SECRETKEY999 on C:\\Users\\Gary\\private\\keys.env"
    cleaned = sanitize_text(raw_error, "SECRETKEY999")
    assert "SECRETKEY999" not in cleaned
    assert "apiKey=[REDACTED]" in cleaned
    assert "C:\\Users\\Gary\\private" not in cleaned

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        raise RuntimeError(f"Failed calling {url} with C:\\Users\\Gary\\private\\token.txt")

    client = MassiveReferenceClient(api_key="SECRETKEY999", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert "SECRETKEY999" not in (res.error_message or "")
    assert "C:\\Users\\Gary\\private" not in (res.error_message or "")
