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


# ── Timezone Provenance Regressions ───────────────────────────────────────────


def test_timezone_provenance_z() -> None:
    fake_body = {
        "results": [{"ticker": "AAPL", "last_updated_utc": "2026-08-30T14:30:00Z"}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_last_updated_at == datetime(2026, 8, 30, 14, 30, 0, tzinfo=UTC)
    assert "last_updated_utc" not in res.missing_fields


def test_timezone_provenance_explicit_offset() -> None:
    fake_body = {
        "results": [{"ticker": "AAPL", "last_updated_utc": "2026-08-30T10:30:00-04:00"}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_last_updated_at == datetime(2026, 8, 30, 14, 30, 0, tzinfo=UTC)
    assert "last_updated_utc" not in res.missing_fields


def test_timezone_provenance_naive_iso_rejected_as_utc() -> None:
    fake_body = {
        "results": [{"ticker": "AAPL", "name": "Apple Inc", "last_updated_utc": "2026-08-30T14:30:00"}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    # Must NOT fabricate UTC from naive timestamp
    assert res.provider_last_updated_at is None
    parsed_fact = json.loads(res.fact_json)
    assert parsed_fact["last_updated_utc"] is None
    assert "last_updated_utc" in res.missing_fields


def test_timezone_provenance_malformed_string() -> None:
    fake_body = {
        "results": [{"ticker": "AAPL", "name": "Apple Inc", "last_updated_utc": "not-a-date"}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_last_updated_at is None
    assert "last_updated_utc" in res.missing_fields


def test_timezone_provenance_absent_field() -> None:
    fake_body = {
        "results": [{"ticker": "AAPL", "name": "Apple Inc", "last_updated_utc": None}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_last_updated_at is None
    assert "last_updated_utc" in res.missing_fields


# ── Boolean Coercion Regressions ──────────────────────────────────────────────


def test_active_field_string_or_int_fails_closed_as_error() -> None:
    for bad_active in ("false", "true", 0, 1, "0", "1"):
        fake_body = {
            "results": [{"ticker": "AAPL", "name": "Apple Inc", "active": bad_active}],
        }
        client = MassiveReferenceClient(
            api_key="KEY",
            request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
            min_interval_seconds=0.0,
        )
        res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
        assert res.observation_status == ReferenceObservationStatus.ERROR
        assert res.error_category == "MassiveResponseError"
        assert "active" in (res.error_message or "")


def test_active_field_valid_bool_and_none() -> None:
    for valid_active, expected in ((True, True), (False, False), (None, None)):
        fake_body = {
            "results": [{"ticker": "AAPL", "active": valid_active}],
        }
        client = MassiveReferenceClient(
            api_key="KEY",
            request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
            min_interval_seconds=0.0,
        )
        res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
        assert res.observation_status == ReferenceObservationStatus.KNOWN
        assert res.provider_active is expected


# ── Exact Ticker Matching Regressions ─────────────────────────────────────────


def test_exact_ticker_lowercase_matches_normalized() -> None:
    fake_body = {
        "results": [{"ticker": "aapl", "name": "Apple Inc", "active": True}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.symbol == "AAPL"
    assert res.provider_ticker == "aapl"


def test_exact_ticker_whitespace_matches_normalized() -> None:
    fake_body = {
        "results": [{"ticker": "  AAPL  ", "name": "Apple Inc", "active": True}],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_ticker == "AAPL"


def test_near_match_ticker_is_not_matched() -> None:
    calls: list[str] = []

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        calls.append(url)
        # Provider returns AAPLX when AAPL was queried
        return json.dumps({"results": [{"ticker": "AAPLX", "active": True}]}).encode("utf-8"), 200, {}

    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=mock_request,
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert len(calls) == 2  # active and inactive queries tried
    assert res.observation_status == ReferenceObservationStatus.UNAVAILABLE


def test_multiple_exact_matches_yields_ambiguous() -> None:
    fake_body = {
        "request_id": "req-ambig-1",
        "results": [
            {"ticker": "AAPL", "name": "Apple Inc", "primary_exchange": "XNAS"},
            {"ticker": "aapl", "name": "Apple Alt", "primary_exchange": "BATS"},
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.AMBIGUOUS
    parsed_fact = json.loads(res.fact_json)
    assert len(parsed_fact["candidates"]) == 2


# ── Malformed Response Shapes Regressions ─────────────────────────────────────


def test_malformed_response_missing_results_yields_error() -> None:
    # A. Missing results key in HTTP 200 response
    fake_body = {"status": "OK", "request_id": "req-no-results"}
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"
    assert "req-no-results" in res.request_ids


def test_malformed_response_results_none_yields_error() -> None:
    # B. results is None
    fake_body = {"results": None, "request_id": "req-none-results"}
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"


def test_malformed_response_results_not_a_list_yields_error() -> None:
    # C. results is string or dict
    for bad_results in ("not-a-list", {"some": "dict"}):
        fake_body = {"results": bad_results, "request_id": "req-bad-results"}
        client = MassiveReferenceClient(
            api_key="KEY",
            request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
            min_interval_seconds=0.0,
        )
        res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
        assert res.observation_status == ReferenceObservationStatus.ERROR
        assert res.error_category == "MassiveResponseError"


def test_malformed_contract_field_type_in_record_yields_error() -> None:
    # D. Malformed contract field type inside an exact ticker record
    for field_name, bad_value in (
        ("ticker", 12345),
        ("name", {"nested": "dict"}),
        ("market", ["list", "of", "markets"]),
        ("type", 999),
        ("last_updated_utc", {"year": 2026}),
    ):
        record = {"ticker": "AAPL", "name": "Apple Inc", field_name: bad_value}
        fake_body = {"results": [record], "request_id": "req-bad-field"}
        client = MassiveReferenceClient(
            api_key="KEY",
            request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
            min_interval_seconds=0.0,
        )
        res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
        assert res.observation_status == ReferenceObservationStatus.ERROR
        assert res.error_category == "MassiveResponseError"


# ── Error Request IDs Provenance Regressions ──────────────────────────────────


def test_http_401_preserves_request_id() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Unauthorized","request_id":"body-req-401"}', 401, {"X-Request-Id": "hdr-req-401"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert "hdr-req-401" in res.request_ids
    assert "body-req-401" in res.request_ids


def test_http_403_preserves_request_id() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Forbidden"}', 403, {"X-Request-Id": "hdr-req-403"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert "hdr-req-403" in res.request_ids


def test_http_429_preserves_request_id() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Rate Limited","request_id":"body-req-429"}', 429, {"X-Request-Id": "hdr-req-429", "Retry-After": "60"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert "hdr-req-429" in res.request_ids
    assert "body-req-429" in res.request_ids


def test_http_500_preserves_request_id() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Server Error"}', 500, {"X-Request-Id": "hdr-req-500"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert "hdr-req-500" in res.request_ids


def test_malformed_json_preserves_request_id() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b"<html>Server crash</html>", 200, {"X-Request-Id": "hdr-req-malformed"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert "hdr-req-malformed" in res.request_ids


# ── Ambiguous Fact JSON Field Restriction Regression ──────────────────────────


def test_ambiguous_fact_json_excludes_unexpected_fields() -> None:
    fake_body = {
        "results": [
            {
                "ticker": "AMBIG",
                "name": "Alpha Corp",
                "primary_exchange": "XNAS",
                "unexpected_blob": {"foo": "bar"},
                "some_future_field": "value",
            },
            {
                "ticker": "AMBIG",
                "name": "Beta Corp",
                "primary_exchange": "XNYS",
                "unexpected_list": [1, 2, 3],
            },
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h: (json.dumps(fake_body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AMBIG", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.AMBIGUOUS

    parsed_fact = json.loads(res.fact_json)
    assert len(parsed_fact["candidates"]) == 2
    for cand in parsed_fact["candidates"]:
        assert "unexpected_blob" not in cand
        assert "some_future_field" not in cand
        assert "unexpected_list" not in cand
        # Only canonical keys exist
        assert set(cand.keys()) <= {
            "active", "cik", "composite_figi", "delisted_utc", "last_updated_utc",
            "locale", "market", "name", "primary_exchange", "share_class_figi",
            "ticker", "type_code",
        }


# ── Other General Provider Tests ──────────────────────────────────────────────


def test_active_zero_fallback_to_inactive_known() -> None:
    calls: list[str] = []

    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        calls.append(url)
        if "active=true" in url:
            return json.dumps({"request_id": "req-1", "results": []}).encode("utf-8"), 200, {}
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


# ── Merge-Gate Corrections: Request ID Preservation on Fallback Failure ────────


def test_fallback_failure_preserves_active_and_fallback_request_ids_401() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        if "active=true" in url:
            return json.dumps({"request_id": "req-act-1", "results": []}).encode("utf-8"), 200, {"X-Request-Id": "hdr-act-1"}
        # Fallback query returns 401
        return b'{"error":"Unauthorized"}', 401, {"X-Request-Id": "hdr-fallback-401"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveAuthError"
    assert "hdr-act-1" in res.request_ids or "req-act-1" in res.request_ids
    assert "hdr-fallback-401" in res.request_ids
    # Prove ordered union
    assert res.request_ids == ("hdr-act-1", "req-act-1", "hdr-fallback-401")


def test_fallback_failure_preserves_active_and_fallback_request_ids_429() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        if "active=true" in url:
            return json.dumps({"results": []}).encode("utf-8"), 200, {"X-Request-Id": "hdr-act-1"}
        return b'{"error":"Rate Limited","request_id":"body-fallback-429"}', 429, {"X-Request-Id": "hdr-fallback-429"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveRateLimitError"
    assert res.request_ids == ("hdr-act-1", "hdr-fallback-429", "body-fallback-429")


def test_fallback_failure_preserves_active_and_fallback_request_ids_500() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        if "active=true" in url:
            return json.dumps({"request_id": "req-act-1", "results": []}).encode("utf-8"), 200, {}
        return b'{"error":"Server Error"}', 500, {"X-Request-Id": "hdr-fallback-500"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveTransientError"
    assert res.request_ids == ("req-act-1", "hdr-fallback-500")


def test_fallback_failure_preserves_active_and_fallback_request_ids_malformed_json() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        if "active=true" in url:
            return json.dumps({"results": []}).encode("utf-8"), 200, {"X-Request-Id": "hdr-act-1"}
        return b"<html>Server crashed</html>", 200, {"X-Request-Id": "hdr-fallback-malformed"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"
    assert res.request_ids == ("hdr-act-1", "hdr-fallback-malformed")


# ── Merge-Gate Corrections: Malformed Ambiguous Candidates Normalized to ERROR ─


def test_ambiguous_malformed_active_field_yields_massive_response_error() -> None:
    fake_body = {
        "results": [
            {"ticker": "AAPL", "name": "Apple 1", "active": True},
            {"ticker": "AAPL", "name": "Apple 2", "active": "false"},  # malformed bool
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {"X-Request-Id": "req-ambig-bad-bool"}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"
    assert res.error_category != "TypeError"
    assert "req-ambig-bad-bool" in res.request_ids


def test_ambiguous_malformed_market_field_yields_massive_response_error() -> None:
    fake_body = {
        "results": [
            {"ticker": "AAPL", "name": "Apple 1", "market": "stocks"},
            {"ticker": "AAPL", "name": "Apple 2", "market": {"bad": "shape"}},  # malformed dict
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {"X-Request-Id": "req-ambig-bad-dict"}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.error_category == "MassiveResponseError"
    assert res.error_category != "TypeError"
    assert "req-ambig-bad-dict" in res.request_ids


# ── Merge-Gate Corrections: Fail Closed on HTTP 404 ───────────────────────────


def test_http_404_fails_closed_as_error_never_unavailable() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        return b'{"error":"Not Found"}', 404, {"X-Request-Id": "hdr-404"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.observation_status != ReferenceObservationStatus.UNAVAILABLE
    assert res.error_category == "MassiveResponseError"
    assert "hdr-404" in res.request_ids


def test_http_404_on_fallback_fails_closed_as_error() -> None:
    def mock_request(url: str, headers: dict[str, str]) -> tuple[bytes, int, dict[str, str]]:
        if "active=true" in url:
            return json.dumps({"results": []}).encode("utf-8"), 200, {"X-Request-Id": "hdr-act-1"}
        return b'{"error":"Not Found"}', 404, {"X-Request-Id": "hdr-fallback-404"}

    client = MassiveReferenceClient(api_key="KEY", request_func=mock_request, min_interval_seconds=0.0)
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.ERROR
    assert res.observation_status != ReferenceObservationStatus.UNAVAILABLE
    assert res.error_category == "MassiveResponseError"
    assert res.request_ids == ("hdr-act-1", "hdr-fallback-404")


# ── Merge-Gate Corrections: Do Not Accept Raw type_code as Alias for type ─────


def test_known_record_with_raw_type_code_only_has_none_type_and_missing_type() -> None:
    fake_body = {
        "results": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "active": True,
                "type_code": "CS",  # provider sent type_code instead of approved type
            }
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.KNOWN
    assert res.provider_type_code is None
    assert "type" in res.missing_fields
    parsed_fact = json.loads(res.fact_json)
    assert parsed_fact["type_code"] is None


def test_ambiguous_record_with_raw_type_code_only_excludes_type_code() -> None:
    fake_body = {
        "results": [
            {"ticker": "AAPL", "name": "Apple 1", "type": "CS"},
            {"ticker": "AAPL", "name": "Apple 2", "type_code": "CS"},  # provider sent type_code instead of type
        ],
    }
    client = MassiveReferenceClient(
        api_key="KEY",
        request_func=lambda url, h, body=fake_body: (json.dumps(body).encode("utf-8"), 200, {}),
        min_interval_seconds=0.0,
    )
    res = client.fetch_ticker_reference("AAPL", date(2026, 8, 30))
    assert res.observation_status == ReferenceObservationStatus.AMBIGUOUS
    parsed_fact = json.loads(res.fact_json)
    c1, c2 = parsed_fact["candidates"]
    assert "type_code" not in c2 or c2["type_code"] is None
    for cand in (c1, c2):
        assert "type" not in cand  # only normalized keys exist
        assert set(cand.keys()) <= {
            "active", "cik", "composite_figi", "delisted_utc", "last_updated_utc",
            "locale", "market", "name", "primary_exchange", "share_class_figi",
            "ticker", "type_code",
        }
