"""Deterministic regression tests for LONG-002B-AMEND-001."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tradex.research.long_002_data_feasibility.amendment_001 import (
    _classify_security,
    run_amendment_probe,
)
from tradex.research.long_002_data_feasibility.report import write_safe_artifacts

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_ticker_detail(
    ticker: str,
    *,
    type_code: str = "CS",
    sic_code: str = "7370",
    active: bool = True,
    primary_exchange: str = "XNAS",
    cik: str = "0000000001",
    composite_figi: str = "BBG000000001",
    name: str = "Example Co Inc",
    list_date: str = "2010-01-01",
) -> dict[str, Any]:
    return {
        "request_id": "test-req",
        "status": "OK",
        "results": {
            "ticker": ticker,
            "name": name,
            "market": "stocks",
            "locale": "us",
            "primary_exchange": primary_exchange,
            "type": type_code,
            "active": active,
            "currency_name": "usd",
            "cik": cik,
            "composite_figi": composite_figi,
            "share_class_figi": f"{composite_figi}SC",
            "ticker_root": ticker,
            "list_date": list_date,
            "sic_code": sic_code,
            "sic_description": "TEST",
        },
    }


def _make_delisted_404(ticker: str) -> dict[str, Any]:
    return {"status": "NOT_FOUND", "message": "Ticker not found."}


def _make_types() -> dict[str, Any]:
    return {
        "status": "OK",
        "results": [
            {"code": "CS", "description": "Common Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "ETF", "description": "Exchange Traded Fund", "asset_class": "stocks", "locale": "us"},
            {"code": "FUND", "description": "Fund", "asset_class": "stocks", "locale": "us"},
            {"code": "PFD", "description": "Preferred Stock", "asset_class": "stocks", "locale": "us"},
            {"code": "WARRANT", "description": "Warrant", "asset_class": "stocks", "locale": "us"},
            {"code": "RIGHT", "description": "Rights", "asset_class": "stocks", "locale": "us"},
            {"code": "UNIT", "description": "Unit", "asset_class": "stocks", "locale": "us"},
            {"code": "ETN", "description": "Exchange Traded Note", "asset_class": "stocks", "locale": "us"},
            {"code": "INDEX", "description": "Index", "asset_class": "stocks", "locale": "us"},
        ],
    }


def _make_ticker_change_events(identifier: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "OK",
        "results": {
            "name": f"{identifier} Inc",
            "composite_figi": f"BBG{identifier}",
            "cik": "0000000001",
            "events": history,
        },
    }


def _make_empty_events() -> dict[str, Any]:
    return {"status": "NOT_FOUND", "message": "No events found"}


def _make_empty_events_200() -> dict[str, Any]:
    return {
        "status": "OK",
        "results": {
            "name": "Unknown",
            "composite_figi": "BBGUNKNOWN",
            "cik": "0000000000",
            "events": [],
        },
    }


def _make_splits(ticker: str) -> dict[str, Any]:
    return {
        "status": "OK",
        "results": [
            {"ticker": ticker, "execution_date": "2020-08-31", "split_from": 1, "split_to": 4},
        ],
    }


def _make_dividends(ticker: str) -> dict[str, Any]:
    return {
        "status": "OK",
        "results": [
            {"ticker": ticker, "ex_date": "2020-08-31", "amount": 0.22},
        ],
    }


def _make_financials(ticker: str) -> dict[str, Any]:
    return {
        "status": "OK",
        "results": [
            {
                "ticker": ticker,
                "filing_date": "2021-01-28",
                "period_of_report_date": "2020-12-31",
                "fiscal_period": "Q1",
                "fiscal_year": "2021",
            }
        ],
    }


def _massive_request_factory(
    details: dict[str, Any],
    events: dict[str, dict[str, Any]],
) -> Callable[[str], bytes]:
    """Return a Massive request function for testing.

    `details` is a mapping of (ticker, date_or_none) -> detail response dict.
    `events` is a mapping of identifier -> event response dict.
    """
    def request(url: str) -> bytes:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/v3/reference/tickers/types":
            return json.dumps(_make_types()).encode("utf-8")

        m = re.match(r"^/v3/reference/tickers/([^/]+)$", path)
        if m:
            ticker = m.group(1)
            date = qs.get("date", [None])[0]
            key = (ticker, date)
            if key in details:
                return json.dumps(details[key]).encode("utf-8")
            # Default to a present-day active CS record if not explicitly configured.
            return json.dumps(_make_ticker_detail(ticker)).encode("utf-8")

        m = re.match(r"^/vX/reference/tickers/([^/]+)/events$", path)
        if m:
            ident = m.group(1)
            return json.dumps(events.get(ident, _make_empty_events_200())).encode("utf-8")

        if path == "/v3/reference/splits":
            ticker = qs.get("ticker", [""])[0]
            return json.dumps(_make_splits(ticker)).encode("utf-8")

        if path == "/v3/reference/dividends":
            ticker = qs.get("ticker", [""])[0]
            return json.dumps(_make_dividends(ticker)).encode("utf-8")

        if path == "/vX/reference/financials":
            ticker = qs.get("ticker", [""])[0]
            return json.dumps(_make_financials(ticker)).encode("utf-8")

        raise RuntimeError(f"Unhandled Massive test URL: {url}")

    return request


def _panel() -> list[dict[str, Any]]:
    return [
        {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
        {"identifier": "SPY", "as_of_dates": ["2020-12-31"]},
        {"identifier": "PFF", "as_of_dates": ["2020-12-31"]},
        {"identifier": "IGR", "as_of_dates": ["2020-12-31"]},
        {"identifier": "IPOD", "as_of_dates": ["2020-12-31"]},
        {"identifier": "YHOO", "as_of_dates": ["2017-03-31"], "lifecycle_supplement_dates": ["2018-03-31"]},
        {"identifier": "FB", "as_of_dates": ["2020-12-31"]},
    ]


def test_security_family_supported_with_documented_limitations() -> None:
    """A complete PIT identity/classification/corporate-action pathway satisfies the security contract."""
    details: dict[tuple[str, str | None], dict[str, Any]] = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
        ("SPY", "2020-12-31"): _make_ticker_detail("SPY", type_code="ETF", name="SPDR S&P 500 ETF Trust"),
        ("PFF", "2020-12-31"): _make_ticker_detail("PFF", type_code="ETF", name="iShares Preferred and Income Securities ETF"),
        ("IGR", "2020-12-31"): _make_ticker_detail("IGR", type_code="FUND", name="CBRE Fund", primary_exchange="XNYS"),
        ("IPOD", "2020-12-31"): _make_ticker_detail("IPOD", sic_code="6770", name="Social Capital Hedosophia Holdings Corp. IV"),
        ("YHOO", "2017-03-31"): _make_ticker_detail("YHOO", name="Yahoo Inc"),
        ("YHOO", "2018-03-31"): _make_delisted_404("YHOO"),
        ("FB", "2020-12-31"): _make_ticker_detail("FB", name="Meta Platforms Inc"),
    }
    events = {
        "META": _make_ticker_change_events("META", [
            {"type": "ticker_change", "date": "2012-05-18", "ticker_change": {"ticker": "FB"}},
            {"type": "ticker_change", "date": "2022-06-09", "ticker_change": {"ticker": "META"}},
        ]),
        "YHOO": _make_empty_events(),
    }
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
                {"identifier": "SPY", "as_of_dates": ["2020-12-31"]},
                {"identifier": "PFF", "as_of_dates": ["2020-12-31"]},
                {"identifier": "IGR", "as_of_dates": ["2020-12-31"]},
                {"identifier": "IPOD", "as_of_dates": ["2020-12-31"]},
                {"identifier": "YHOO", "as_of_dates": ["2017-03-31"], "lifecycle_supplement_dates": ["2018-03-31"]},
                {"identifier": "FB", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    earn = next(f for f in report.data_families if f.family == "earnings_event_timing")
    assert sec.disposition == "supported_with_documented_limitations"
    assert earn.disposition == "not_supported"
    assert report.overall_disposition == "not_supported"
    assert "LONG-002C" in report.recommended_next_action


def test_per_date_classification_does_not_backfill_from_later_row() -> None:
    """Each (symbol, as_of_date) PIT row is classified independently from its own fields."""
    details = {
        ("IGR", "2016-03-31"): _make_ticker_detail("IGR", type_code="CS", name="CBRE Global Real Estate Income Fund", primary_exchange="XNYS"),
        ("IGR", "2020-12-31"): _make_ticker_detail("IGR", type_code="FUND", name="CBRE Global Real Estate Income Fund", primary_exchange="XNYS"),
    }
    events = {
        "IGR": _make_ticker_change_events("IGR", [
            {"type": "ticker_change", "date": "2004-02-25", "ticker_change": {"ticker": "IGR"}},
        ]),
    }
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "IGR", "as_of_dates": ["2016-03-31", "2020-12-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    assert sec.disposition == "supported_with_documented_limitations"
    # The 2016 `CS` row is classified from its PIT name as closed_end_fund,
    # not by backfilling the 2020 `FUND` type.
    assert any("2016-03-31" in n and "closed_end_fund" in n for n in sec.limitations)


def test_unresolved_historical_row_fails_closed() -> None:
    """A PIT row with a null/missing type and no corroborating name/SIC signal is `unknown`."""
    details = {
        ("AAPL", "2016-03-31"): _make_ticker_detail("AAPL", type_code=None, name="Apple Inc"),
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", type_code="CS", name="Apple Inc"),
    }
    events = {
        "AAPL": _make_ticker_change_events("AAPL", [{"type": "ticker_change", "date": "2003-09-10", "ticker_change": {"ticker": "AAPL"}}]),
    }
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2016-03-31", "2020-12-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    assert sec.disposition == "not_supported"
    assert any("defensible_exclusion_classification" in b for b in sec.blockers)


def test_generic_index_type_without_etf_name_cannot_satisfy_exclusion_contract() -> None:
    """A provider response with an untaxonomied generic 'INDEX' type and no ETF name does not satisfy defensible classification."""
    details = {
        ("SPY", "2020-12-31"): _make_ticker_detail("SPY", type_code="INDEX", name="S&P 500 Index"),
    }
    events = {}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "SPY", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    assert sec.disposition == "not_supported"
    assert any("defensible_exclusion_classification" in b for b in sec.blockers)


def test_pff_preferred_etf_classified_as_etf_not_preferred_stock() -> None:
    """A preferred-stock ETF must be classified as ETF (with preferred-stock strategy), not as preferred stock."""
    row = _make_ticker_detail("PFF", type_code="ETF", name="iShares Preferred and Income Securities ETF")["results"]
    type_map = {t["code"]: t for t in _make_types()["results"]}
    assert _classify_security(row, type_map) == "ETF"


def test_cs_with_fund_name_is_not_common_stock() -> None:
    """A generic `CS` row with a closed-end-fund name is classified as closed_end_fund or unknown, never common stock."""
    row = _make_ticker_detail("IGR", type_code="CS", name="CBRE Global Real Estate Income Fund", primary_exchange="XNYS")["results"]
    type_map = {t["code"]: t for t in _make_types()["results"]}
    classification = _classify_security(row, type_map)
    assert classification in ("closed_end_fund", "unknown"), classification
    assert classification != "common_stock"


def test_lifecycle_evidence_requires_positive_evidence_404_is_not_evidence() -> None:
    """A missing ticker/event response (HTTP 404) alone cannot satisfy the lifecycle gate."""
    details = {
        ("YHOO", "2017-03-31"): _make_ticker_detail("YHOO", name="Yahoo Inc"),
        ("YHOO", "2018-03-31"): _make_delisted_404("YHOO"),
    }
    events = {"YHOO": _make_empty_events()}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "YHOO", "as_of_dates": ["2017-03-31"], "lifecycle_supplement_dates": ["2018-03-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    # The 404 on the supplement date and the 404 event lookup are not positive
    # lifecycle evidence. The family fails closed.
    assert sec.disposition == "not_supported"
    assert any("active_inactive_lifecycle_evidence" in b for b in sec.blockers)
    # Confirm no note claims 404 provided lifecycle evidence.
    assert not any("404" in n and "lifecycle" in n.lower() for n in sec.limitations)


def test_lifecycle_evidence_requires_effective_dated_or_inactive_delisted_evidence() -> None:
    """Active-only rows without ticker-change or later delisting evidence do not prove lifecycle coverage."""
    details = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
    }
    events = {"AAPL": _make_empty_events_200()}  # Active, no ticker_change events
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    sec = next(f for f in report.data_families if f.family == "security_identity_lifecycle_and_exclusion_classification")
    assert sec.disposition == "not_supported"
    assert any("active_inactive_lifecycle_evidence" in b for b in sec.blockers)


def test_earnings_fallbacks_are_unverified_and_recorded() -> None:
    """Fallback providers that are not exercised are recorded as unverified, not as unsupported capability failures."""
    details = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
    }
    events = {"AAPL": _make_ticker_change_events("AAPL", [{"type": "ticker_change", "date": "2003-09-10", "ticker_change": {"ticker": "AAPL"}}])}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    earn = next(f for f in report.data_families if f.family == "earnings_event_timing")
    assert earn.disposition == "not_supported"
    fallback_records = [r for r in earn.records if r.provider in ("sec_edgar", "yahoo_earnings_calendar")]
    assert len(fallback_records) == 2
    for r in fallback_records:
        assert r.error_classification == "unverified"
    # The report should explicitly note that provider search was not exhausted.
    assert any("not exhausted" in n.lower() for n in earn.limitations)
    assert any("fallback" in n.lower() and "not evaluated" in n.lower() for n in earn.limitations)


def test_earnings_disclosure_timestamps_are_not_schedules() -> None:
    """A successful Massive financials response with filing/period dates does not satisfy the earnings schedule contract."""
    details = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
    }
    events = {"AAPL": _make_ticker_change_events("AAPL", [{"type": "ticker_change", "date": "2003-09-10", "ticker_change": {"ticker": "AAPL"}}])}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    earn = next(f for f in report.data_families if f.family == "earnings_event_timing")
    assert earn.disposition == "not_supported"
    assert any("historical_known_at_time_schedule" in b for b in earn.blockers)
    massive_records = [r for r in earn.records if r.provider == "massive"]
    assert any(r.http_status == 200 and "/vX/reference/financials" in r.endpoint_pattern for r in massive_records)


def test_amendment_does_not_authorize_long_002c_automatically() -> None:
    """Even when security identity is supported, an unsupported earnings family keeps overall not_supported and does not authorize LONG-002C."""
    details = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
    }
    events = {"AAPL": _make_ticker_change_events("AAPL", [{"type": "ticker_change", "date": "2003-09-10", "ticker_change": {"ticker": "AAPL"}}])}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    assert report.overall_disposition == "not_supported"
    assert "dataset construction" not in report.recommended_next_action.lower() or "does not" in report.recommended_next_action.lower()
    assert "LONG-002C" in report.recommended_next_action


def test_spac_classification_uses_sic_and_name_not_generic_cs() -> None:
    """A blank-check SPAC with type 'CS' is classified via SIC/name, not treated as common stock."""
    row = _make_ticker_detail("IPOD", sic_code="6770", name="Social Capital Hedosophia Holdings Corp. IV")["results"]
    type_map = {t["code"]: t for t in _make_types()["results"]}
    assert _classify_security(row, type_map) == "pre_merger_spac"

    # Without the SIC/name signals, the same type would be treated as common stock.
    row2 = _make_ticker_detail("AAPL", type_code="CS", name="Apple Inc")["results"]
    assert _classify_security(row2, type_map) == "common_stock"


def test_write_safe_artifacts_uses_task_id_for_bundle_path(tmp_path: Path) -> None:
    """The artifact bundle is written under a LONG-002B-AMEND-001 directory keyed by task_id."""
    details = {
        ("AAPL", "2020-12-31"): _make_ticker_detail("AAPL", name="Apple Inc"),
    }
    events = {"AAPL": _make_ticker_change_events("AAPL", [{"type": "ticker_change", "date": "2003-09-10", "ticker_change": {"ticker": "AAPL"}}])}
    report = run_amendment_probe(
        REPO_ROOT,
        test_inject={
            "massive_request_func": _massive_request_factory(details, events),
            "panel": [
                {"identifier": "AAPL", "as_of_dates": ["2020-12-31"]},
            ],
        },
    )
    bundle = write_safe_artifacts(report, tmp_path, run_id="test-run", code_commit_sha="abc123")
    assert bundle.exists()
    assert bundle.name == "test-run"
    assert bundle.parent.name == "LONG-002B-AMEND-001"
    assert (bundle / "feasibility_report.json").exists()
