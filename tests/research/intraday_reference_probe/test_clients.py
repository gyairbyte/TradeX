"""Credential-free tests for Alpha Vantage and Massive clients."""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from tradex.research.intraday_reference_probe.alpha_vantage import (
    AlphaVantageReferenceClient,
    _EXPECTED_COLUMNS,
)
from tradex.research.intraday_reference_probe.massive import MassiveReferenceClient


class _FakeResponse:
    def __init__(self, body: bytes, code: int = 200) -> None:
        self._body = body
        self._code = code

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_alpha_vantage_client_requires_key() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        AlphaVantageReferenceClient("   ")


def test_alpha_vantage_fetch_listing_parses_csv() -> None:
    client = AlphaVantageReferenceClient("test-key")
    csv_body = (
        "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        "AAPL,Apple Inc,NASDAQ,Stock,1980-12-12,none,Active\n"
    ).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(csv_body, 200)):
        rows, obs = client.fetch_listing("2024-05-31", "active")
    assert obs.row_count == 1
    assert obs.provider == "alpha_vantage"
    assert rows[0]["symbol"] == "AAPL"
    assert "assetType" in rows[0]
    assert not obs.error


def test_alpha_vantage_handles_json_error() -> None:
    client = AlphaVantageReferenceClient("test-key")
    body = b'{"Information": "API rate limit exceeded"}'
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body, 200)):
        rows, obs = client.fetch_listing("2024-05-31", "active")
    assert obs.error
    assert obs.row_count == 0


def test_alpha_vantage_probe_provider_counts() -> None:
    client = AlphaVantageReferenceClient("test-key")
    csv = (
        "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        "AAPL,Apple Inc,NASDAQ,Stock,1980-12-12,none,Active\n"
        "MSFT,Microsoft Corp,NASDAQ,Stock,1986-03-13,none,Active\n"
    ).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(csv, 200)):
        with patch("time.sleep"):
            result = client.probe_provider(("2024-05-31",), states=("active",))
    assert result.provider == "alpha_vantage"
    assert result.security_type_counts.get("Stock") == 2


def test_massive_client_requires_key() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        MassiveReferenceClient("  ")


def test_massive_url_builds_api_key() -> None:
    client = MassiveReferenceClient("k")
    url = client._url("/v3/reference/tickers", {"market": "stocks"})
    assert "apiKey=k" in url
    assert "market=stocks" in url
