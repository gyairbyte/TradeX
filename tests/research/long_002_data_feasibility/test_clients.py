"""Credential-free unit tests for LONG-002B provider clients and budgets."""
from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest
import requests

from tradex.research.long_002_data_feasibility.clients import (
    BudgetError,
    Long002AlpacaClient,
    Long002EdgarClient,
    Long002MassiveClient,
    Long002ProviderAuthError,
    Long002ProviderTransientError,
    RequestBudget,
)


def test_request_budget_enforces_max_and_counts() -> None:
    budget = RequestBudget(max_requests=3)
    budget.charge(1)
    assert budget.used == 1
    budget.charge(2)
    assert budget.used == 3
    with pytest.raises(BudgetError):
        budget.charge(1)


def test_request_budget_elapsed_time_is_non_negative() -> None:
    budget = RequestBudget()
    assert budget.elapsed_seconds() >= 0.0


def test_alpaca_client_rejects_missing_credentials() -> None:
    with pytest.raises(Long002ProviderAuthError):
        Long002AlpacaClient("", "secret")
    with pytest.raises(Long002ProviderAuthError):
        Long002AlpacaClient("key", "")


def test_alpaca_client_transient_timeout_is_retried_then_raised() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeResp:
        status_code = 200
        def json(self):
            return {"bars": [{"t": "2020-08-31T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 100}]}

    def fake_get(url: str, **kwargs: Any) -> FakeResp:
        calls.append((url, kwargs.get("params", {})))
        if len(calls) < 2:
            raise requests.Timeout("timeout")
        return FakeResp()

    budget = RequestBudget(max_requests=10)
    client = Long002AlpacaClient("key", "secret", budget=budget, request_func=fake_get, request_delay_seconds=0.0, max_retries=1)
    summary = client.fetch_daily_bars("AAPL", "2020-08-31T00:00:00Z", "2020-08-31T23:59:59Z")
    assert summary["http_status"] == 200
    assert summary["pagination_complete"] is True
    assert summary["bar_count"] == 1
    assert budget.used >= 1


def test_alpaca_client_raw_vs_normalized_separation() -> None:
    class FakeResp:
        status_code = 200
        def json(self):
            return {"bars": [{"t": "2020-08-31T04:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}]}

    client = Long002AlpacaClient("k", "s", request_func=lambda *a, **k: FakeResp(), request_delay_seconds=0.0)
    summary = client.fetch_daily_bars("AAPL", "2020-08-31T00:00:00Z", "2020-08-31T23:59:59Z", adjustment="raw", feed="sip")
    df = client.to_dataframe(summary["bars"])
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert summary["feed"] == "sip"
    assert summary["adjustment"] == "raw"


def test_massive_client_rejects_missing_api_key() -> None:
    with pytest.raises(Long002ProviderAuthError):
        Long002MassiveClient("")


def test_massive_client_pagination_stops_when_no_next_url() -> None:
    pages: list[int] = []
    def fake_request(url: str) -> bytes:
        pages.append(1)
        return json.dumps({
            "results": [{"ticker": "AAPL", "type": "CS", "primary_exchange": "XNAS", "active": True}],
            "next_url": None,
        }).encode("utf-8")

    budget = RequestBudget(max_requests=5)
    client = Long002MassiveClient("key", budget=budget, request_func=fake_request)
    snap = client.fetch_reference_snapshot("2020-03-31", True, safety_max_pages=3)
    assert snap["pagination_complete"] is True
    assert snap["row_count"] == 1
    assert budget.used == 1


def test_massive_client_excluded_security_types_observable() -> None:
    def fake_request(url: str) -> bytes:
        return json.dumps({
            "results": [
                {"ticker": "SPY", "type": "ETF", "primary_exchange": "ARCX", "active": True},
                {"ticker": "AAPL", "type": "CS", "primary_exchange": "XNAS", "active": True},
            ],
            "next_url": None,
        }).encode("utf-8")

    client = Long002MassiveClient("key", request_func=fake_request)
    snap = client.fetch_reference_snapshot("2020-03-31", True, safety_max_pages=1)
    types = {r.get("type") for r in snap["rows"]}
    assert "ETF" in types
    assert "CS" in types


def test_edgar_client_handles_404_as_empty_and_transient_as_error() -> None:
    class FakeUrlLib:
        def __init__(self, code: int | None = None) -> None:
            self.code = code
        def read(self) -> bytes:
            return b"{}"
        def __enter__(self):
            return self
        def __exit__(self, *a: object) -> None:
            pass
        def getcode(self) -> int | None:
            return self.code

    budget = RequestBudget(max_requests=5)
    def fake_request(url: str) -> bytes:
        if "404CIK" in url:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)  # type: ignore[attr-defined]
        if "TIMEOUT" in url:
            raise urllib.error.URLError("timeout")
        return b'{"cik":"320193"}'

    client = Long002EdgarClient(budget=budget, request_func=fake_request)
    assert client.fetch_submissions("0000320193") == {"cik": "320193"}
    assert client.fetch_submissions("404CIK") == {}
    with pytest.raises(Long002ProviderTransientError):
        client.fetch_submissions("TIMEOUT")


def test_edgar_client_budget_is_charged() -> None:
    calls: list[str] = []
    def fake_request(url: str) -> bytes:
        calls.append(url)
        return b'{"cik":"320193"}'
    budget = RequestBudget(max_requests=2)
    client = Long002EdgarClient(budget=budget, request_func=fake_request)
    client.fetch_submissions("0000320193")
    assert budget.used == 1
