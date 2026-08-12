"""LONG-002B bounded provider-probe orchestrator."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .clients import (
    BudgetError,
    Long002AlpacaClient,
    Long002EdgarClient,
    Long002MassiveClient,
    Long002ProviderAuthError,
    Long002ProviderEntitlementError,
    Long002ProviderResponseError,
    Long002ProviderTransientError,
    Long002ProviderUnsupportedError,
    RequestBudget,
    resolve_credentials,
)
from .models import DataFamilyResult, FeasibilityReport, ProviderRequestRecord
from .spec import load_probe_spec, sha256_of_file


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, Long002ProviderAuthError):
        return "authentication"
    if isinstance(exc, Long002ProviderEntitlementError):
        return "entitlement"
    if isinstance(exc, Long002ProviderUnsupportedError):
        return "unsupported_capability"
    if isinstance(exc, Long002ProviderTransientError):
        return "transient"
    if isinstance(exc, Long002ProviderResponseError):
        return "response"
    return "unknown"


def _record(
    family: str,
    provider: str,
    symbol: str | None,
    as_of_date: str | None,
    endpoint_pattern: str,
    status: int | None,
    error: str,
    retry: int,
    summary: dict[str, Any],
    provenance: dict[str, Any],
) -> ProviderRequestRecord:
    return ProviderRequestRecord(
        family=family,
        provider=provider,
        symbol=symbol,
        as_of_date=as_of_date,
        endpoint_pattern=endpoint_pattern,
        http_status=status,
        error_classification=error,
        retry_count=retry,
        request_timestamp_utc=_now_utc(),
        response_summary=summary,
        provenance=provenance,
    )


def _safe_bar_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Return a safe summary for a daily-bar response without raw OHLCV."""
    bars = summary.get("bars", [])
    safe: dict[str, Any] = {
        "provider": summary.get("provider"),
        "symbol": summary.get("symbol"),
        "http_status": summary.get("http_status"),
        "error_classification": summary.get("error_classification"),
        "bar_count": summary.get("bar_count", len(bars)),
        "page_count": summary.get("page_count"),
        "pagination_complete": summary.get("pagination_complete"),
        "feed": summary.get("feed"),
        "adjustment": summary.get("adjustment"),
        "retry_count": summary.get("retry_count"),
    }
    if bars:
        safe["first_bar_timestamp"] = bars[0].get("t") if isinstance(bars[0], dict) else None
        safe["last_bar_timestamp"] = bars[-1].get("t") if isinstance(bars[-1], dict) else None
        safe["bar_payload_sha256"] = hashlib.sha256(
            json.dumps(bars, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    return safe


def _safe_snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a safe summary for a Massive snapshot without the raw row payload."""
    return {
        "provider": snapshot.get("provider"),
        "pit_date": snapshot.get("pit_date"),
        "active": snapshot.get("active"),
        "status": snapshot.get("status"),
        "error": snapshot.get("error"),
        "row_count": snapshot.get("row_count"),
        "page_count": snapshot.get("page_count"),
        "pagination_complete": snapshot.get("pagination_complete"),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "probe_tickers_found": snapshot.get("probe_tickers_found", []),
    }


def _run_family(
    family_name: str,
    family_spec: dict[str, Any],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> DataFamilyResult:
    """Run a single data-family probe, respecting the stop condition and fallbacks."""
    result = DataFamilyResult(family=family_name, disposition="not_supported", evidence_confidence="limited_but_usable_evidence")
    preferred = family_spec["preferred_provider"]["name"]
    fallbacks = [fb["name"] for fb in family_spec.get("fallback_order", [])]
    providers = [preferred] + fallbacks

    min_contract = family_spec.get("minimum_usable_contract", {})

    if family_name == "daily_market_data":
        return _probe_daily_market_data(providers, panel, budget, creds, min_contract, test_inject)
    if family_name == "security_master_and_corporate_actions":
        return _probe_security_master(providers, panel, budget, creds, min_contract, test_inject, context)
    if family_name == "issuer_fundamentals_and_shares":
        return _probe_fundamentals(providers, panel, budget, creds, min_contract, test_inject, context)
    if family_name == "earnings_event_timing":
        return _probe_earnings(providers, panel, budget, creds, min_contract, test_inject)
    return result


def _probe_daily_market_data(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> DataFamilyResult:
    result = DataFamilyResult(family="daily_market_data")
    selected = None
    role = None
    for provider in providers:
        if provider == "massive/polygon":
            # Massive bars endpoint is unverified in this client; record unsupported.
            result.records.append(_record(
                "daily_market_data", "massive/polygon", None, None,
                "v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
                None, "unsupported_capability", 0,
                {"reason": "Massive daily bars client not implemented in this probe"},
                {"provider": "massive/polygon"},
            ))
            continue
        if provider == "alpaca":
            if not creds.get("alpaca_api_key") or not creds.get("alpaca_secret_key"):
                result.records.append(_record(
                    "daily_market_data", "alpaca", None, None,
                    "/v2/stocks/{symbol}/bars", None, "authentication", 0,
                    {"reason": "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY"},
                    {"provider": "alpaca"},
                ))
                continue
            client = Long002AlpacaClient(
                str(creds["alpaca_api_key"]),
                str(creds["alpaca_secret_key"]),
                budget=budget,
                request_func=test_inject.get("alpaca_request_func") if test_inject else None,
            )
            successes = 0
            failures = 0
            for item in panel:
                symbol = item["identifier"]
                for as_of in item["as_of_dates"][:1]:
                    start = f"{as_of}T00:00:00Z"
                    end = f"{as_of}T23:59:59Z"
                    try:
                        summary = client.fetch_daily_bars(symbol, start, end, feed="sip", adjustment="raw")
                    except BudgetError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        failures += 1
                        result.records.append(_record(
                            "daily_market_data", "alpaca", symbol, as_of,
                            "/v2/stocks/{symbol}/bars", None, _classify_error(exc), 0,
                            {}, {"exception": str(exc)},
                        ))
                        continue
                    if summary.get("http_status") == 200 and summary.get("bar_count", 0) > 0:
                        successes += 1
                    else:
                        failures += 1
                    result.records.append(_record(
                        "daily_market_data", "alpaca", symbol, as_of,
                        "/v2/stocks/{symbol}/bars",
                        summary.get("http_status"),
                        summary.get("error_classification", "none"),
                        summary.get("retry_count", 0),
                        _safe_bar_summary(summary),
                        {"feed": "sip", "adjustment": "raw"},
                    ))
            result.request_count = sum(1 for r in result.records if r.provider == "alpaca")
            if successes >= 1:
                selected = "alpaca"
                role = "fallback" if providers[0] != "alpaca" else "primary"
                result.disposition = "supported_with_documented_limitations"
                result.evidence_confidence = "limited_but_usable_evidence"
                result.summary = {"successes": successes, "failures": failures, "note": "Single-day probes only; full history not retrieved"}
                result.provider_selected = selected
                result.provider_role = role
                result.limitations.append("Only one as-of date per symbol probed; does not prove 2015-2025 coverage.")
                result.limitations.append("Alpaca feed semantics (sip/iex) and adjustment policy require further verification for LONG-002.")
                if "massive/polygon" in providers:
                    result.limitations.append("Massive/Polygon daily bars endpoint not directly exercised; Alpaca used as fallback.")
                break
            result.blockers.append("Alpaca returned no usable daily bars for the probe panel.")
        if provider == "schwab":
            result.records.append(_record(
                "daily_market_data", "schwab", None, None,
                "Schwab priceHistory", None, "unsupported_capability", 0,
                {"reason": "Schwab OAuth token not configured in this environment"},
                {"provider": "schwab"},
            ))

    if selected is None:
        result.disposition = "not_supported"
        result.evidence_confidence = "invalid_evidence"
        result.blockers.append("No provider returned usable daily market data within budget.")
    return result


def _probe_security_master(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> DataFamilyResult:
    result = DataFamilyResult(family="security_master_and_corporate_actions")
    selected = None
    role = None
    for provider in providers:
        if provider == "massive":
            if not creds.get("massive_api_key"):
                result.records.append(_record(
                    "security_master_and_corporate_actions", "massive", None, None,
                    "/v3/reference/tickers", None, "authentication", 0,
                    {"reason": "Missing MASSIVE_API_KEY"}, {"provider": "massive"},
                ))
                continue
            client = Long002MassiveClient(
                str(creds["massive_api_key"]),
                budget=budget,
                request_func=test_inject.get("massive_request_func") if test_inject else None,
            )
            pit_dates = sorted({d for item in panel for d in item["as_of_dates"][:1]})
            successes = 0
            for pit_date in pit_dates:
                try:
                    active = client.fetch_reference_snapshot(pit_date, True, safety_max_pages=3)
                except BudgetError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    result.records.append(_record(
                        "security_master_and_corporate_actions", "massive", None, pit_date,
                        "/v3/reference/tickers", None, _classify_error(exc), 0,
                        {}, {"exception": str(exc)},
                    ))
                    continue
                status = active.get("status")
                error = active.get("error")
                safe_summary = _safe_snapshot_summary(active)
                if status == 200 and active.get("row_count", 0) > 0:
                    successes += 1
                    # Check for at least one probe-panel symbol in the snapshot.
                    tickers = {str(r.get("ticker") or "").upper() for r in active.get("rows", [])}
                    found = [i["identifier"] for i in panel if i["identifier"].upper() in tickers]
                    safe_summary["probe_tickers_found"] = found
                    # Build CIK mapping for fundamentals family.
                    symbol_to_cik = context.setdefault("symbol_to_cik", {})
                    for r in active.get("rows", []):
                        ticker = str(r.get("ticker") or "").upper()
                        cik = r.get("cik")
                        if ticker and cik:
                            symbol_to_cik[ticker] = str(cik).strip().lstrip("0") or "0"
                else:
                    safe_summary["probe_tickers_found"] = []
                result.records.append(_record(
                    "security_master_and_corporate_actions", "massive", None, pit_date,
                    "/v3/reference/tickers", status,
                    "none" if not error else "response",
                    0,
                    safe_summary,
                    {"state": "active"},
                ))
            result.request_count = sum(1 for r in result.records if r.provider == "massive")
            if successes >= 1:
                selected = "massive"
                role = "primary"
                result.disposition = "supported_with_documented_limitations"
                result.evidence_confidence = "limited_but_usable_evidence"
                result.summary = {"active_snapshots_with_data": successes}
                result.provider_selected = selected
                result.provider_role = role
                result.limitations.append("Reference ticker endpoint exercised; split/dividend/merge endpoints not probed in this run.")
                break
            result.blockers.append("Massive reference snapshots returned no rows.")
        if provider == "alpaca":
            result.records.append(_record(
                "security_master_and_corporate_actions", "alpaca", None, None,
                "assets", None, "unsupported_capability", 0,
                {"reason": "Alpaca security master endpoints not exercised in this probe"},
                {"provider": "alpaca"},
            ))
        if provider == "sec_edgar":
            result.records.append(_record(
                "security_master_and_corporate_actions", "sec_edgar", None, None,
                "submissions metadata", None, "unsupported_capability", 0,
                {"reason": "EDGAR security master queried only via fundamentals family"},
                {"provider": "sec_edgar"},
            ))
    if selected is None:
        result.disposition = "not_supported"
        result.evidence_confidence = "invalid_evidence"
        result.blockers.append("No provider returned a usable security master snapshot.")
    return result


def _probe_fundamentals(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> DataFamilyResult:
    result = DataFamilyResult(family="issuer_fundamentals_and_shares")
    selected = None
    role = None
    for provider in providers:
        if provider == "sec_edgar":
            client = Long002EdgarClient(
                budget=budget,
                request_func=test_inject.get("edgar_request_func") if test_inject else None,
            )
            successes = 0
            failures = 0
            symbol_to_cik = {}
            if test_inject:
                symbol_to_cik.update(test_inject.get("symbol_to_cik", {}))
            symbol_to_cik.update(context.get("symbol_to_cik", {}))
            for item in panel[:4]:
                symbol = item["identifier"]
                cik = symbol_to_cik.get(symbol.upper())
                if not cik:
                    result.records.append(_record(
                        "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                        "submissions/CIK{cik}.json", None, "unknown", 0,
                        {"reason": "CIK not resolved for symbol"}, {"provider": "sec_edgar"},
                    ))
                    failures += 1
                    continue
                try:
                    submissions = client.fetch_submissions(cik)
                    facts = client.fetch_company_facts(cik)
                except BudgetError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    result.records.append(_record(
                        "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                        "submissions/CIK{cik}.json", None, _classify_error(exc), 0,
                        {}, {"cik": cik, "exception": str(exc)},
                    ))
                    continue
                if submissions or facts:
                    successes += 1
                else:
                    failures += 1
                result.records.append(_record(
                    "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                    "submissions/CIK{cik}.json", 200 if submissions else None, "none" if submissions else "data_unavailable", 0,
                    {"submissions_present": bool(submissions), "facts_present": bool(facts), "cik": cik},
                    {"cik": cik},
                ))
            result.request_count = sum(1 for r in result.records if r.provider == "sec_edgar")
            if successes >= 1:
                selected = "sec_edgar"
                role = "primary"
                result.disposition = "supported_with_documented_limitations"
                result.evidence_confidence = "limited_but_usable_evidence"
                result.summary = {"successes": successes, "failures": failures}
                result.provider_selected = selected
                result.provider_role = role
                result.limitations.append("CIK resolution must come from a separate security master or manual mapping in LONG-002.")
                result.limitations.append("Filing acceptance-time availability and shares outstanding facts require a full build pipeline.")
                break
            result.blockers.append("EDGAR fundamentals could not be retrieved for the probe panel.")
        if provider == "massive":
            result.records.append(_record(
                "issuer_fundamentals_and_shares", "massive", None, None,
                "financial endpoints", None, "unsupported_capability", 0,
                {"reason": "Massive financial endpoints not exercised"}, {"provider": "massive"},
            ))
        if provider == "yahoo":
            result.records.append(_record(
                "issuer_fundamentals_and_shares", "yahoo", None, None,
                "finance quote/history", None, "unsupported_capability", 0,
                {"reason": "Yahoo used only as diagnostic, not PIT facts"}, {"provider": "yahoo"},
            ))
    if selected is None:
        result.disposition = "not_supported"
        result.evidence_confidence = "invalid_evidence"
        result.blockers.append("No provider returned usable fundamentals/shares data.")
    return result


def _probe_earnings(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> DataFamilyResult:
    result = DataFamilyResult(family="earnings_event_timing")
    selected = None
    for provider in providers:
        if provider == "massive":
            result.records.append(_record(
                "earnings_event_timing", "massive", None, None,
                "historical earnings schedule", None, "unsupported_capability", 0,
                {"reason": "Massive historical earnings endpoint not identified in this probe"},
                {"provider": "massive"},
            ))
        if provider == "yahoo_earnings_calendar":
            result.records.append(_record(
                "earnings_event_timing", "yahoo_earnings_calendar", None, None,
                "calendar/earnings", None, "unsupported_capability", 0,
                {"reason": "Yahoo earnings calendar is current/prospective only"},
                {"provider": "yahoo_earnings_calendar"},
            ))
        if provider == "sec_edgar":
            result.records.append(_record(
                "earnings_event_timing", "sec_edgar", None, None,
                "filing acceptance timestamps", None, "unsupported_capability", 0,
                {"reason": "EDGAR provides actual disclosure timing, not future schedule"},
                {"provider": "sec_edgar"},
            ))
    if selected is None:
        result.disposition = "not_supported"
        result.evidence_confidence = "invalid_evidence"
        result.blockers.append("No provider demonstrated historical known-at-the-decision-time earnings scheduling.")
        result.limitations.append("An 'unknown' earnings treatment may be required for LONG-002 unless a historical earnings calendar source is identified.")
    return result


def _overall_disposition(families: list[DataFamilyResult]) -> str:
    labels = [f.disposition for f in families]
    if "invalid_evidence" in labels or all(l == "not_supported" for l in labels):
        return "not_supported"
    if "not_supported" in labels:
        return "supported_with_documented_limitations"
    if all(l == "supported" for l in labels):
        return "supported"
    return "supported_with_documented_limitations"


def run_probe(
    repo_root: Path | str | None = None,
    *,
    test_inject: dict[str, Any] | None = None,
) -> FeasibilityReport:
    """Execute the bounded LONG-002B feasibility probe."""
    root = Path(repo_root or ".")
    spec, probe_sha = load_probe_spec(root)
    long_002_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002-v1.json")

    budget = RequestBudget(max_requests=spec["hard_network_budget"]["max_total_http_requests"])
    creds = resolve_credentials() if not test_inject else {}

    start = time.monotonic()
    context: dict[str, Any] = {}
    families: list[DataFamilyResult] = []
    try:
        for family_name, family_spec in spec["data_families"].items():
            requests_before = budget.used
            family_result = _run_family(family_name, family_spec, spec["probe_panel"]["locked_panel"], budget, creds, test_inject, context)
            family_result.request_count = budget.used - requests_before
            families.append(family_result)
    except BudgetError:
        pass
    runtime = time.monotonic() - start

    overall = _overall_disposition(families)
    report = FeasibilityReport(
        task_id="LONG-002B",
        overall_disposition=overall,
        overall_evidence_confidence="limited_but_usable_evidence" if overall != "not_supported" else "invalid_evidence",
        total_http_requests=budget.used,
        runtime_seconds=runtime,
        code_commit_sha="",
        long_002_spec_sha256=long_002_sha,
        probe_spec_sha256=probe_sha,
        data_contract_sha256=sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002B-data-contract-v1.json"),
        data_families=families,
    )
    report.recommended_next_action = _recommended_next_action(report)
    report.limitations = _collect_limitations(families)
    report.blockers = _collect_blockers(families)
    return report


def _recommended_next_action(report: FeasibilityReport) -> str:
    if report.overall_disposition == "supported":
        return "Proceed to a separately approved LONG-002C assignment under the unchanged contract"
    if report.overall_disposition == "supported_with_documented_limitations":
        return "Request a specific Gary-approved data-sufficiency amendment before LONG-002C for the unsupported families"
    return "Perform no further LONG-002 work on the unsupported families until provider capability improves or a Gary-approved amendment is granted"


def _collect_limitations(families: list[DataFamilyResult]) -> list[str]:
    out: list[str] = []
    for f in families:
        out.extend(f.limitations)
    return out


def _collect_blockers(families: list[DataFamilyResult]) -> list[str]:
    out: list[str] = []
    for f in families:
        out.extend(f.blockers)
    return out
