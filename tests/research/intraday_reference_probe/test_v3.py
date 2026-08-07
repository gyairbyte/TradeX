"""Credential-free v3 reference probe tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tradex.config import settings_from_mapping
from tradex.research.intraday_reference_probe import report
from tradex.research.intraday_reference_probe.cli import main as cli_main
from tradex.research.intraday_reference_probe.massive import MassiveReferenceClient
from tradex.research.intraday_reference_probe.models import (
    PITObservation,
    ProviderCandidateResult,
    ReferenceProbeDecision,
)
from tradex.research.intraday_reference_probe.probe import (
    _capability_matrix_v3,
    _is_structural_failure,
    run_reference_probe,
)
from tradex.research.intraday_reference_probe.report import write_reference_probe_artifacts
from tradex.research.intraday_reference_probe.spec import load_probe_spec

V3_SPEC = "docs/research/specs/INTRA-001B-reference-probe-v3.json"


@pytest.fixture(autouse=True)
def _patch_time_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)


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


def _ticker_page(
    tickers: list[str],
    next_url: str | None = None,
    count: int | None = None,
) -> bytes:
    results = []
    for t in tickers:
        results.append({
            "ticker": t,
            "name": f"{t} Inc",
            "type": "CS",
            "primary_exchange": "XNYS",
            "active": True,
            "cik": f"000{t}",
        })
    payload = {"results": results}
    if count is not None:
        payload["count"] = count
    if next_url is not None:
        payload["next_url"] = next_url
    return json.dumps(payload).encode("utf-8")


def _types_page() -> bytes:
    return json.dumps({
        "results": [
            {"code": "CS", "description": "Common Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "ETF", "description": "ETF", "asset_class": "stocks", "locale": "us"},
            {"code": "WARRANT", "description": "Warrant", "asset_class": "stocks", "locale": "us"},
            {"code": "RIGHT", "description": "Right", "asset_class": "stocks", "locale": "us"},
            {"code": "UNIT", "description": "Unit", "asset_class": "stocks", "locale": "us"},
            {"code": "PFD", "description": "Preferred Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "OTC", "description": "OTC Common Stock", "asset_class": "stocks", "locale": "us"},
        ]
    }).encode("utf-8")


def test_v3_spec_loads() -> None:
    spec, raw = load_probe_spec(V3_SPEC)
    assert spec.task_id == "INTRA-001B-REFERENCE-V3"
    assert spec.probe_version == 3
    assert "alpha_vantage" in spec.candidate_selection_order
    assert "massive" in spec.candidate_selection_order
    assert len(spec.mandatory_gates) == 22
    assert raw == Path(V3_SPEC).read_bytes()


def test_massive_pagination_one_page_terminal() -> None:
    client = MassiveReferenceClient("k", base_url="https://api.massive.com")
    body = _ticker_page(["AAPL", "MSFT"])
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body, 200)):
        _rows, pages, obs = client.fetch_tickers("2024-05-31", True)
    assert obs.pagination_complete
    assert obs.page_count == 1
    assert obs.row_count == 2
    assert pages[0].next_url_present is False


def test_massive_pagination_two_pages() -> None:
    client = MassiveReferenceClient("k", base_url="https://api.massive.com")
    page1 = _ticker_page(["AAPL"], next_url="https://api.massive.com/v3/reference/tickers?date=2024-05-31&active=true&market=stocks&locale=us&cursor=c1")
    page2 = _ticker_page(["MSFT"])

    def _urlopen(req, *args, **kwargs):
        url = req.get_full_url()
        if "cursor=c1" in url:
            return _FakeResponse(page2, 200)
        return _FakeResponse(page1, 200)

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        rows, _pages, obs = client.fetch_tickers("2024-05-31", True)
    assert obs.pagination_complete
    assert obs.page_count == 2
    assert len(rows) == 2


def test_massive_pagination_first_page_only_fails() -> None:
    client = MassiveReferenceClient("k", base_url="https://api.massive.com")
    body = _ticker_page(["AAPL"] * 1000, next_url="https://api.massive.com/v3/reference/tickers?date=2024-05-31&active=true&market=stocks&locale=us&cursor=c1")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body, 200)):
        _rows, _pages, obs = client.fetch_tickers("2024-05-31", True, safety_max_pages=1)
    assert obs.max_pages_reached
    assert not obs.pagination_complete


def test_massive_pagination_repeated_next_url_fails() -> None:
    client = MassiveReferenceClient("k", base_url="https://api.massive.com")
    url = "https://api.massive.com/v3/reference/tickers?date=2024-05-31&active=true&market=stocks&locale=us&cursor=c1"
    body = _ticker_page(["AAPL"], next_url=url)

    def _urlopen(req, *args, **kwargs):
        return _FakeResponse(body, 200)

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        _rows, _pages, obs = client.fetch_tickers("2024-05-31", True)
    assert obs.repeated_next_url_detected


def test_massive_pagination_unexpected_host_fails() -> None:
    client = MassiveReferenceClient("k", base_url="https://api.massive.com")
    body = _ticker_page(["AAPL"], next_url="https://evil.com/v3/reference/tickers?date=2024-05-31&active=true&market=stocks&locale=us&cursor=c1")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body, 200)):
        _rows, _pages, obs = client.fetch_tickers("2024-05-31", True)
    assert obs.unexpected_next_url


def test_massive_ticker_types_builds_mapping() -> None:
    client = MassiveReferenceClient("k")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(_types_page(), 200)):
        types, error = client.fetch_ticker_types()
    assert error is None
    mapping, allowlist, _ = client.build_taxonomy_mapping(types)
    assert mapping["CS"] == "common_stock"
    assert mapping["ETF"] == "etf"
    assert mapping["WARRANT"] == "warrant"
    assert "CS" in allowlist


def test_massive_probe_provider_runs_with_mocks() -> None:
    client = MassiveReferenceClient("k")
    page1 = _ticker_page(["AAPL"], next_url="https://api.massive.com/v3/reference/tickers?date=2024-05-31&active=true&market=stocks&locale=us&cursor=c1")
    page2 = _ticker_page(["MSFT"])
    call_count = {"n": 0}

    def _urlopen(req, *args, **kwargs):
        call_count["n"] += 1
        url = req.get_full_url()
        if "tickers/types" in url:
            return _FakeResponse(_types_page(), 200)
        if "cursor=c1" in url:
            return _FakeResponse(page2, 200)
        return _FakeResponse(page1, 200)

    with patch("urllib.request.urlopen", side_effect=_urlopen), patch("time.sleep"):
        result = client.probe_provider(("2024-05-31",), (True, False))
    assert result.provider == "massive"
    assert result.taxonomy_endpoint_verified
    assert any(obs.pagination_complete for obs in result.observations)


def test_gate_evaluation_with_complete_massive_result() -> None:
    spec, _ = load_probe_spec(V3_SPEC)
    obs = PITObservation(
        provider="massive",
        pit_date="2024-05-31",
        state="active",
        requested_at="2024-05-31T00:00:00+00:00",
        elapsed_seconds=1.0,
        row_count=2,
        column_headers=("ticker", "name", "type", "primary_exchange"),
        raw_sha256="a" * 64,
        repeat_sha256="a" * 64,
        repeat_match=True,
        http_status=200,
        page_count=1,
        first_page_count=2,
        last_page_count=2,
        pagination_complete=True,
        full_snapshot_sha256="a" * 64,
        canonical_ticker_count=2,
        blank_ticker_count=0,
        duplicate_ticker_count=0,
        unresolved_duplicate_count=0,
    )
    result = ProviderCandidateResult(
        provider="massive",
        target_entitlement="current Gary entitlement",
        probe_version=3,
        observations=(obs,),
        capability_rows=(),
        pagination_pages=(),
        security_type_counts={"CS": 2},
        exchange_counts={"XNYS": 2},
        primary_exchange_field="primary_exchange",
        security_type_field="type",
        delisting_date_field="delisted_utc",
        ticker_types=(
            {"code": "CS", "description": "Common Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "ETF", "description": "ETF", "asset_class": "stocks", "locale": "us"},
            {"code": "WARRANT", "description": "Warrant", "asset_class": "stocks", "locale": "us"},
            {"code": "RIGHT", "description": "Right", "asset_class": "stocks", "locale": "us"},
            {"code": "UNIT", "description": "Unit", "asset_class": "stocks", "locale": "us"},
            {"code": "PFD", "description": "Preferred Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "OTC", "description": "OTC", "asset_class": "stocks", "locale": "us"},
        ),
        taxonomy_mapping={
            "CS": "common_stock",
            "ETF": "etf",
            "WARRANT": "warrant",
            "RIGHT": "right",
            "UNIT": "unit",
            "PFD": "preferred_stock",
            "OTC": "otc",
        },
        taxonomy_endpoint_verified=True,
        max_pages_active=1,
        max_pages_inactive=1,
        estimated_http_calls_48_months=96,
        estimated_collection_time_48_months_seconds=96 * 12.1,
        lifecycle_fields_present=("delisted_utc",),
    )
    matrix = _capability_matrix_v3(result, spec)
    by_name = {row.capability: row for row in matrix}
    assert by_name["common_stock_classification"].supported
    assert by_name["warrant_exclusion"].supported
    assert by_name["otc_exclusion"].supported


def test_safe_artifact_contract() -> None:
    spec, raw = load_probe_spec(V3_SPEC)
    obs = PITObservation(
        provider="massive",
        pit_date="2024-05-31",
        state="active",
        requested_at="2024-05-31T00:00:00+00:00",
        elapsed_seconds=1.0,
        row_count=2,
        column_headers=("ticker", "name", "type", "primary_exchange"),
        raw_sha256="a" * 64,
        repeat_match=True,
        http_status=200,
        page_count=1,
        pagination_complete=True,
        full_snapshot_sha256="a" * 64,
        canonical_ticker_count=2,
    )
    result = ProviderCandidateResult(
        provider="massive",
        target_entitlement="test",
        probe_version=3,
        observations=(obs,),
        capability_rows=(),
        security_type_counts={"CS": 2},
        exchange_counts={"XNYS": 2},
        primary_exchange_field="primary_exchange",
        security_type_field="type",
        ticker_types=({"code": "CS", "description": "Common Stock", "asset_class": "stocks", "locale": "us"},),
        taxonomy_mapping={"CS": "common_stock"},
        taxonomy_endpoint_verified=True,
        estimated_http_calls_48_months=96,
        estimated_collection_time_48_months_seconds=96 * 12.1,
    )
    decision = ReferenceProbeDecision(
        probe_version=3,
        task_id="INTRA-001B-REFERENCE-V3",
        provider="massive",
        outcome="supported",
        approved_as_reference_provider=True,
        reason="all gates passed",
        candidate_order=("alpha_vantage", "massive"),
        pit_dates=("2024-05-31",),
        v1_pre_registration_commit="a" * 40,
        v2_pre_registration_commit="b" * 40,
        v3_pre_registration_commit="c" * 40,
        probe_spec_sha256="d" * 64,
    )
    out = Path("/tmp/test_v3_artifacts")
    if out.exists():
        shutil.rmtree(out)
    bundle = write_reference_probe_artifacts(spec, decision, result, out, probe_spec_raw=raw)
    manifest = json.loads((bundle / "artifact_manifest.json").read_text())
    expected = set(report.EXPECTED_SAFE_ARTIFACTS)
    actual_files = {p.name for p in bundle.iterdir() if p.is_file()}
    assert actual_files == expected
    assert set(manifest["files"].keys()) <= expected
    assert "probe_spec.lock.json" in manifest["files"]
    assert "decision.json" in manifest["files"]


def test_cli_help_runs() -> None:
    with patch("sys.argv", ["probe", "--help"]), pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 0


def test_run_reference_probe_missing_credentials(monkeypatch) -> None:
    spec, _ = load_probe_spec(V3_SPEC)
    settings = settings_from_mapping({})
    from tradex.research.intraday_reference_probe import probe as probe_module
    monkeypatch.setattr(probe_module, "validate_pre_registration_commit", lambda *args, **kwargs: None)
    result, decision = run_reference_probe(
        spec,
        settings,
        v1_pre_registration_commit="a" * 40,
        v2_pre_registration_commit="b" * 40,
        v3_pre_registration_commit="c" * 40,
        probe_spec_sha256="d" * 64,
        starting_main_sha="e" * 40,
        branch="devin/intra-001b-reference-v3",
        final_head="e" * 40,
    )
    assert result is None
    assert decision.outcome == "no_currently_free_complete_reference_source"
    assert decision.alpha_vantage_credentials_available is False
    assert decision.massive_credentials_available is False


def test_is_structural_failure_detects_pagination_cycle() -> None:
    decision = ReferenceProbeDecision(
        probe_version=3,
        task_id="INTRA-001B-REFERENCE-V3",
        provider=None,
        outcome="no_currently_free_complete_reference_source",
        approved_as_reference_provider=False,
        reason="test",
        candidate_order=("alpha_vantage", "massive"),
        no_pagination_cycles_or_repeated_cursors=False,
    )
    assert _is_structural_failure(decision)


