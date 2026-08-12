"""Credential-free tests for the LONG-002B probe orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tradex.research.long_002_data_feasibility.clients import (
    Long002AlpacaClient,
    Long002MassiveClient,
    RequestBudget,
)
from tradex.research.long_002_data_feasibility.models import DataFamilyResult
from tradex.research.long_002_data_feasibility.probe import (
    _overall_disposition,
    _probe_daily_market_data,
    _recommended_next_action,
    run_probe,
)
from tradex.research.long_002_data_feasibility.report import write_safe_artifacts


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fake_alpaca_request(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    class Resp:
        status_code = 200
        def json(self):
            return {
                "bars": [
                    {"t": "2020-08-31T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 100},
                ],
                "next_page_token": None,
            }
    return Resp()


def _fake_massive_request(url: str) -> bytes:
    return json.dumps({
        "results": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "type": "CS",
                "primary_exchange": "XNAS",
                "active": True,
                "cik": "0000320193",
            }
        ],
        "next_url": None,
        "count": 1,
    }).encode("utf-8")


def _fake_edgar_request(url: str) -> bytes:
    if "submissions" in url:
        return json.dumps({"cik": "320193", "recent": {}}).encode("utf-8")
    return json.dumps({"cik": "320193", "facts": {}}).encode("utf-8")


def test_run_probe_with_mocks_produces_report_and_artifacts(repo_root: Path, tmp_path: Path) -> None:
    report = run_probe(
        repo_root,
        test_inject={
            "alpaca_request_func": _fake_alpaca_request,
            "massive_request_func": _fake_massive_request,
            "edgar_request_func": _fake_edgar_request,
            "symbol_to_cik": {"AAPL": "0000320193"},
        },
    )
    assert report.task_id == "LONG-002B"
    assert report.long_002_spec_sha256
    assert report.probe_spec_sha256
    assert report.total_http_requests <= 120
    assert all(f.request_count >= 0 for f in report.data_families)

    bundle = write_safe_artifacts(report, tmp_path, run_id="test-run", code_commit_sha="abc123")
    assert bundle.exists()
    assert (bundle / "feasibility_report.json").exists()
    assert (bundle / "provider_contract_matrix.csv").exists()
    assert (bundle / "coverage_summary.csv").exists()
    assert (bundle / "data_quality_summary.csv").exists()
    assert (bundle / "artifact_manifest.json").exists()
    assert (bundle / "checksums.sha256").exists()


def test_overall_disposition_supported() -> None:
    f1 = DataFamilyResult("a", "supported", "strong_evidence")
    f2 = DataFamilyResult("b", "supported", "strong_evidence")
    assert _overall_disposition([f1, f2]) == "supported"


def test_overall_disposition_mixed() -> None:
    f1 = DataFamilyResult("a", "supported", "strong_evidence")
    f2 = DataFamilyResult("b", "not_supported", "invalid_evidence")
    assert _overall_disposition([f1, f2]) == "not_supported"


def test_overall_disposition_all_not_supported() -> None:
    f1 = DataFamilyResult("a", "not_supported", "invalid_evidence")
    f2 = DataFamilyResult("b", "not_supported", "invalid_evidence")
    assert _overall_disposition([f1, f2]) == "not_supported"


def test_recommended_next_action_for_not_supported() -> None:
    report = type("R", (), {"overall_disposition": "not_supported"})()
    assert "Perform no further" in _recommended_next_action(report)


def _make_alpaca_bar() -> dict[str, Any]:
    return {
        "t": "2020-08-31T04:00:00Z",
        "o": 120.0,
        "h": 125.0,
        "l": 119.0,
        "c": 124.0,
        "v": 1000000.0,
    }


def test_daily_market_data_records_massive_failure_and_alpaca_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Massive 403 is a provider response, not a capability gap; Alpaca fallback is reported as such."""
    panel = [{"identifier": "AAPL", "as_of_dates": ["2020-12-31"]}]
    budget = RequestBudget(max_requests=120)
    creds = {"massive_api_key": "test", "alpaca_api_key": "test", "alpaca_secret_key": "test"}
    min_contract = {}

    def fake_massive_daily_bars(self: Any, ticker: str, start: str, end: str, *, adjusted: bool = False) -> dict[str, Any]:
        return {
            "provider": "massive/polygon",
            "ticker": ticker,
            "start": start,
            "end": end,
            "status": 403,
            "error": "Forbidden",
            "bars": [],
            "results_count": 0,
            "pagination_complete": False,
            "adjusted": adjusted,
        }

    def fake_alpaca_daily_bars(
        self: Any, symbol: str, start_utc: str, end_utc: str, *, feed: str = "sip", adjustment: str = "raw",
    ) -> dict[str, Any]:
        return {
            "provider": "alpaca",
            "symbol": symbol,
            "http_status": 200,
            "error_classification": "none",
            "bars": [_make_alpaca_bar()],
            "bar_count": 1,
            "page_count": 1,
            "pagination_complete": True,
            "feed": feed,
            "adjustment": adjustment,
        }

    monkeypatch.setattr(Long002MassiveClient, "fetch_daily_bars", fake_massive_daily_bars)
    monkeypatch.setattr(Long002AlpacaClient, "fetch_daily_bars", fake_alpaca_daily_bars)

    result, evidence, _any_attempted, _raw_bars = _probe_daily_market_data(
        ["massive/polygon", "alpaca"], panel, budget, creds, min_contract, test_inject=None,
    )

    massive_records = [r for r in result.records if r.provider == "massive/polygon"]
    alpaca_records = [r for r in result.records if r.provider == "alpaca"]
    assert massive_records, "expected a Massive/Polygon attempt record"
    assert alpaca_records, "expected an Alpaca fallback record"
    assert massive_records[0].error_classification == "entitlement"
    assert result.provider_selected == "alpaca"
    assert result.provider_role == "fallback"
    assert evidence.notes
    assert "stopping preferred-provider exercise" in evidence.notes[0].lower()


def test_daily_market_data_unexercised_preferred_provider_not_capability_failure() -> None:
    """If the preferred provider is never attempted, it is not a provider capability failure."""
    panel = [{"identifier": "AAPL", "as_of_dates": ["2020-12-31"]}]
    budget = RequestBudget(max_requests=120)
    creds: dict[str, Any] = {}
    min_contract = {}

    result, evidence, _any_attempted, _raw_bars = _probe_daily_market_data(
        ["massive/polygon", "alpaca"], panel, budget, creds, min_contract, test_inject=None,
    )
    # With no credentials, no provider is exercised.
    assert not any(r.provider == "massive/polygon" and r.http_status == 200 for r in result.records)
    assert not any(r.provider == "alpaca" and r.http_status == 200 for r in result.records)
    # The notes should record the missing attempt, not classify as unsupported capability.
    assert any("missing" in n.lower() or "not attempted" in n.lower() for n in evidence.notes)
    assert result.provider_selected is None
    assert result.provider_role is None
