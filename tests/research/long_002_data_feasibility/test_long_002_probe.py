"""Credential-free tests for the LONG-002B probe orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tradex.research.long_002_data_feasibility.models import DataFamilyResult
from tradex.research.long_002_data_feasibility.probe import (
    _overall_disposition,
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
    assert _overall_disposition([f1, f2]) == "supported_with_documented_limitations"


def test_overall_disposition_all_not_supported() -> None:
    f1 = DataFamilyResult("a", "not_supported", "invalid_evidence")
    f2 = DataFamilyResult("b", "not_supported", "invalid_evidence")
    assert _overall_disposition([f1, f2]) == "not_supported"


def test_recommended_next_action_for_not_supported() -> None:
    report = type("R", (), {"overall_disposition": "not_supported"})()
    assert "Perform no further" in _recommended_next_action(report)
