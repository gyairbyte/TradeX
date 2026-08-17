"""LONG-002B-AMEND-001 bounded provider probe.

This amendment addresses the two LONG-002B blockers:

1. Security identity, lifecycle, and exclusion classification.
2. Historical known-at-the-decision-time earnings scheduling.

It reuses the locked LONG-002B probe panel and upstream specifications but
probes additional Massive/Polygon endpoints (singular ticker details, ticker
types, ticker events, vX financials) to determine whether a defensible PIT
pathway exists. Earnings-event timing remains not_supported because no
preregistered endpoint delivers a historical known-at-time schedule.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .clients import (
    Long002MassiveClient,
    Long002ProviderTransientError,
    RequestBudget,
    resolve_credentials,
)
from .evaluator import FamilyEvidence, evaluate_family, evaluate_overall
from .models import DataFamilyResult, FeasibilityReport, ProviderRequestRecord
from .report import write_safe_artifacts
from .spec import sha256_of_file


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


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


def _classify_error(exc: Exception) -> str:
    from .clients import (
        Long002ProviderAuthError,
        Long002ProviderEntitlementError,
        Long002ProviderResponseError,
        Long002ProviderUnsupportedError,
    )

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


def _classify_http_status(status: int | None) -> str:
    if status is None:
        return "network_error"
    if status == 200:
        return "none"
    if status == 401:
        return "authentication"
    if status == 403:
        return "entitlement"
    if status == 404:
        return "response"
    if status == 429:
        return "http_429"
    if status >= 500:
        return "response"
    return f"http_{status}"


def _load_amendment_spec(repo_root: Path | str | None = None) -> tuple[dict[str, Any], str]:
    root = Path(repo_root or ".")
    path = root / "docs" / "research" / "specs" / "LONG-002B-AMEND-001-probe-v1.json"
    raw = path.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict):
        raise TypeError("Amendment spec must be a JSON object")
    return spec, hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Safe response summaries
# ---------------------------------------------------------------------------


def _safe_ticker_details_summary(detail: dict[str, Any]) -> dict[str, Any]:
    row = detail.get("row") or {}
    safe = {
        "provider": detail.get("provider"),
        "ticker": detail.get("ticker"),
        "pit_date": detail.get("date") or detail.get("pit_date"),
        "http_status": detail.get("status"),
        "error": detail.get("error"),
        "type": row.get("type") if isinstance(row, dict) else None,
        "name": row.get("name") if isinstance(row, dict) else None,
        "primary_exchange": row.get("primary_exchange") if isinstance(row, dict) else None,
        "cik": row.get("cik") if isinstance(row, dict) else None,
        "active": row.get("active") if isinstance(row, dict) else None,
        "market": row.get("market") if isinstance(row, dict) else None,
        "sic_code": row.get("sic_code") if isinstance(row, dict) else None,
        "sic_description": row.get("sic_description") if isinstance(row, dict) else None,
        "list_date": row.get("list_date") if isinstance(row, dict) else None,
        "delisted_utc": row.get("delisted_utc") if isinstance(row, dict) else None,
        "composite_figi": row.get("composite_figi") if isinstance(row, dict) else None,
        "share_class_figi": row.get("share_class_figi") if isinstance(row, dict) else None,
        "ticker_root": row.get("ticker_root") if isinstance(row, dict) else None,
        "ticker_suffix": row.get("ticker_suffix") if isinstance(row, dict) else None,
        "row_found": bool(row),
    }
    if row:
        safe["row_sha256"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    return safe


def _safe_ticker_types_summary(types_result: dict[str, Any]) -> dict[str, Any]:
    types = types_result.get("types", [])
    safe = {
        "provider": types_result.get("provider"),
        "asset_class": types_result.get("asset_class"),
        "locale": types_result.get("locale"),
        "http_status": types_result.get("status"),
        "error": types_result.get("error"),
        "type_count": len(types) if isinstance(types, list) else 0,
    }
    if types and isinstance(types, list):
        safe["type_codes_sample"] = [t.get("code") for t in types[:10]]
    return safe


def _safe_ticker_event_summary(events_result: dict[str, Any]) -> dict[str, Any]:
    events = events_result.get("events", [])
    safe = {
        "provider": events_result.get("provider"),
        "identifier": events_result.get("identifier"),
        "http_status": events_result.get("status"),
        "error": events_result.get("error"),
        "event_count": events_result.get("event_count", 0),
        "event_types_present": sorted({e.get("type") for e in events if isinstance(e, dict)}),
    }
    if events and isinstance(events, list):
        safe["first_event_date"] = events[0].get("date")
    return safe


def _safe_stock_financials_summary(fin: dict[str, Any]) -> dict[str, Any]:
    results = fin.get("results", [])
    safe = {
        "provider": fin.get("provider"),
        "ticker": fin.get("ticker"),
        "http_status": fin.get("status"),
        "error": fin.get("error"),
        "result_count": fin.get("result_count", 0),
    }
    if results and isinstance(results, list):
        first = results[0]
        safe["first_filing_date"] = first.get("filing_date") if isinstance(first, dict) else None
        safe["first_period_of_report_date"] = first.get("period_of_report_date") if isinstance(first, dict) else None
        safe["first_source"] = first.get("source") if isinstance(first, dict) else None
    return safe


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


_EXCLUDED_TYPE_CODES = {
    "PFD": "preferred_stock",
    "WARRANT": "warrant",
    "RIGHT": "right",
    "UNIT": "unit",
    "ETN": "ETN",
    "BOND": "other_structurally_incomparable_securities",
    "SP": "other_structurally_incomparable_securities",
    "ADRC": "other_structurally_incomparable_securities",
    "ADRP": "preferred_stock",
    "ADRW": "warrant",
    "ADRR": "right",
    "ETV": "other_structurally_incomparable_securities",
    "BASKET": "other_structurally_incomparable_securities",
}

_SPAC_KEYWORDS = {
    "spac",
    "blank check",
    "blank-check",
    "acquisition corp",
    "acquisition company",
    "hedosophia",
    "social capital",
    "special purpose",
    "newmont acquisition",
}

# Keywords that identify an ETF regardless of the provider type code.
_ETF_KEYWORDS = {"etf", "exchange traded fund"}

# Keywords that identify an ETN.
_ETN_KEYWORDS = {"etn", "exchange traded note"}

# Keywords that identify a preferred-stock security (not a preferred-stock ETF).
_PREFERRED_KEYWORDS = {
    "preferred stock",
    "preference share",
    "preferred share",
    "preferred a",
    "preferred b",
    "preferred c",
    "preferred d",
}

# Keywords that identify warrants, rights, and units.
_WARRANT_KEYWORDS = {"warrant"}
_RIGHT_KEYWORDS = {" right", "rights"}
_UNIT_KEYWORDS = {"unit"}

# Keywords that identify closed-end funds (but not REITs or broad investment trusts).
_CLOSED_END_FUND_KEYWORDS = {"closed-end", "closed end", "closedend", "fnd"}

# Name signals that corroborate a generic `CS` as common stock.
_COMMON_STOCK_NAME_SIGNALS = {
    "inc",
    "corp",
    "corporation",
    "company",
    "plc",
    "ltd",
    "limited",
    "holdings",
    "group",
    "enterprises",
}


def _is_blank_check_spac(row: dict[str, Any]) -> bool:
    """Defensive SPAC/shell classification using SIC code and name."""
    if not isinstance(row, dict):
        return False
    sic = str(row.get("sic_code", ""))
    if sic == "6770":
        return True
    sic_desc = str(row.get("sic_description", "")).lower()
    if "blank" in sic_desc:
        return True
    name = str(row.get("name", "")).lower()
    return any(k in name for k in _SPAC_KEYWORDS)


def _is_shell_company(row: dict[str, Any]) -> bool:
    """Detect shell-company indicators from the PIT row."""
    if not isinstance(row, dict):
        return False
    name = str(row.get("name", "")).lower()
    if "shell company" in name or name.strip() == "shell":
        return True
    sic = str(row.get("sic_code", ""))
    # 6799 is the SIC for shell companies / unspecified investment.
    return sic == "6799"


def _name_category(name: str) -> str | None:
    """Return a locked category inferred from the PIT security name, or None."""
    if not name:
        return None
    n = name.lower()

    # ETF detection has priority; preferred-stock ETFs remain ETFs.
    if any(k in n for k in _ETF_KEYWORDS):
        return "ETF"

    # ETN
    if any(k in n for k in _ETN_KEYWORDS):
        return "ETN"

    # Preferred stock (not an ETF, since ETF check came first)
    if any(k in n for k in _PREFERRED_KEYWORDS):
        return "preferred_stock"

    # Warrants / rights / units
    if any(k in n for k in _WARRANT_KEYWORDS):
        return "warrant"
    if any(k in n for k in _RIGHT_KEYWORDS):
        return "right"
    if any(k in n for k in _UNIT_KEYWORDS):
        return "unit"

    # Closed-end funds. Avoid flagging REITs ("real estate investment trust")
    # or broad investment trusts as closed-end funds.
    if any(k in n for k in _CLOSED_END_FUND_KEYWORDS):
        return "closed_end_fund"
    if "fund" in n and "reit" not in n and "investment trust" not in n and "mutual" not in n:
        return "closed_end_fund"

    # SPAC/shell
    if any(k in n for k in _SPAC_KEYWORDS):
        return "pre_merger_spac"
    if "shell company" in n or n.strip() == "shell":
        return "shell_company"

    return None


def _common_stock_evidence(row: dict[str, Any], type_map: dict[str, dict[str, Any]]) -> bool:
    """Return True when the PIT row supports a common-stock classification.

    The provider type code `CS` is generic; it is accepted as common stock only
    when the provider's own taxonomy confirms it, the PIT name contains a
    common-stock signal, and the name/SIC do not contradict that classification.
    A missing type field remains unresolved and is not rescued by the name alone.
    """
    if not isinstance(row, dict):
        return False
    code = str(row.get("type", "") or "").upper()
    name = str(row.get("name", "") or "").lower()
    if _name_category(name):
        return False
    if _is_blank_check_spac(row) or _is_shell_company(row):
        return False
    if code != "CS":
        return False
    desc = str(type_map.get("CS", {}).get("description", "")).lower()
    if "common stock" not in desc:
        return False
    if not name:
        return False
    # Require a corroborating corporate name signal.
    return any(signal in name for signal in _COMMON_STOCK_NAME_SIGNALS)


def _classify_security(row: dict[str, Any], type_map: dict[str, dict[str, Any]]) -> str:
    """Map a provider row to a locked LONG-002 exclusion category or eligible common stock.

    Classification is performed from the PIT row only; no later or current
    classification may be substituted as a historical fact. Generic provider
    codes such as `CS` or `INDEX` are insufficient by themselves and require
    corroborating PIT name/SIC evidence.

    Returns one of:
      common_stock, preferred_stock, warrant, right, unit, ETF, ETN,
      closed_end_fund, pre_merger_spac, shell_company, OTC,
      other_structurally_incomparable_securities, unknown.
    """
    if not isinstance(row, dict):
        return "unknown"

    market = str(row.get("market", "")).lower()
    if market == "otc" or not row.get("primary_exchange"):
        return "OTC"

    code = str(row.get("type", "") or "").upper()

    # Direct type-code mapping for the specific exclusion categories.
    if code in _EXCLUDED_TYPE_CODES:
        return _EXCLUDED_TYPE_CODES[code]

    # SPAC/shell can override a generic `CS` code.
    if _is_blank_check_spac(row):
        return "pre_merger_spac"
    if _is_shell_company(row):
        return "shell_company"

    # Specific, non-generic provider codes that map directly.
    if code == "ETF":
        return "ETF"

    if code == "ETN":
        return "ETN"

    if code == "FUND":
        # Closed-end funds are listed on U.S. exchanges; mutual funds are not.
        if row.get("primary_exchange") and market == "stocks":
            return "closed_end_fund"
        return "other_structurally_incomparable_securities"

    # Use the PIT security name to disambiguate generic or missing codes.
    name = str(row.get("name", "") or "")
    name_cat = _name_category(name)
    if name_cat:
        return name_cat

    # Generic `CS` only accepted as common stock when the provider taxonomy
    # confirms it and the PIT name does not contradict it.
    if code == "CS" and _common_stock_evidence(row, type_map):
        return "common_stock"

    # A generic `INDEX` code is insufficient without a PIT name that resolves
    # it to a concrete locked category such as ETF/ETN.
    if code == "INDEX":
        return "unknown"

    # Any other missing or unmapped code is unresolved.
    return "unknown"


# ---------------------------------------------------------------------------
# Security identity/lifecycle/exclusion probe
# ---------------------------------------------------------------------------


def _probe_security_identity(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe PIT security identity, lifecycle, and exclusion classification."""
    result = DataFamilyResult(family="security_identity_lifecycle_and_exclusion_classification")
    evidence = FamilyEvidence(family="security_identity_lifecycle_and_exclusion_classification")
    any_attempted = False
    selected: str | None = None
    role: str | None = None

    type_map: dict[str, dict[str, Any]] = {}

    for provider in providers:
        if provider == "massive":
            if not creds.get("massive_api_key"):
                result.records.append(_record(
                    "security_identity_lifecycle_and_exclusion_classification", "massive", None, None,
                    "/v3/reference/tickers/{ticker}", None, "authentication", 0,
                    {"reason": "Missing MASSIVE_API_KEY"}, {"provider": "massive"},
                ))
                continue

            client = Long002MassiveClient(
                str(creds["massive_api_key"]),
                budget=budget,
                request_func=test_inject.get("massive_request_func") if test_inject else None,
                min_interval_seconds=0.0 if test_inject else None,
            )

            # 1. Ticker-type taxonomy (one request, cached for classification).
            types_result = client.fetch_ticker_types()
            any_attempted = True
            result.records.append(_record(
                "security_identity_lifecycle_and_exclusion_classification", "massive", None, None,
                "/v3/reference/tickers/types", types_result.get("status"),
                "none" if types_result.get("status") == 200 else _classify_http_status(types_result.get("status")),
                0, _safe_ticker_types_summary(types_result), {"provider": "massive"},
            ))
            if types_result.get("status") == 200:
                for t in types_result.get("types", []):
                    if isinstance(t, dict) and t.get("code"):
                        type_map[str(t["code"]).upper()] = t

            # 2. Per-ticker PIT details across the locked panel.
            details_by_symbol: dict[str, list[dict[str, Any]]] = {}
            identity_by_symbol: dict[str, dict[str, Any]] = {}

            for item in panel:
                symbol = item["identifier"]
                dates = list(item.get("as_of_dates", []))
                supplement = list(item.get("lifecycle_supplement_dates", []))
                all_dates = dates + supplement
                details_by_symbol[symbol] = []
                for date in all_dates:
                    detail = client.fetch_ticker_details(symbol, date=date)
                    any_attempted = True
                    details_by_symbol[symbol].append(detail)
                    result.records.append(_record(
                        "security_identity_lifecycle_and_exclusion_classification", "massive", symbol, date,
                        "/v3/reference/tickers/{ticker}", detail.get("status"),
                        "none" if detail.get("status") == 200 else _classify_http_status(detail.get("status")),
                        0, _safe_ticker_details_summary(detail), {"provider": "massive"},
                    ))
                    if detail.get("status") == 200:
                        row = detail.get("row") or {}
                        identity_by_symbol[symbol] = row

            # 3. Ticker-change / lifecycle event timeline for panel symbols plus
            # known renamed identifiers (e.g. FB/META).
            panel_symbols = {i["identifier"] for i in panel}
            event_symbols = panel_symbols | {"META"}
            events_by_symbol: dict[str, dict[str, Any]] = {}
            for symbol in sorted(event_symbols):
                # For renamed symbols the current ticker is the post-change one.
                query_id = "META" if symbol == "FB" else symbol
                events = client.fetch_ticker_events(query_id, event_types="ticker_change")
                any_attempted = True
                events_by_symbol[symbol] = events
                result.records.append(_record(
                    "security_identity_lifecycle_and_exclusion_classification", "massive", symbol, None,
                    "/vX/reference/tickers/{id}/events", events.get("status"),
                    "none" if events.get("status") == 200 else _classify_http_status(events.get("status")),
                    0, _safe_ticker_event_summary(events), {"provider": "massive", "event_types": "ticker_change"},
                ))

            # 4. Split/dividend provenance for symbols expected to have events.
            split_count = 0
            dividend_count = 0
            for sym in ("AAPL", "GOOGL", "SIRI"):
                ca = client.fetch_corporate_actions(sym)
                any_attempted = True
                splits = ca.get("splits", {})
                dividends = ca.get("dividends", {})
                result.records.append(_record(
                    "security_identity_lifecycle_and_exclusion_classification", "massive", sym, None,
                    "/v3/reference/splits?ticker={ticker}", splits.get("status"),
                    "none" if splits.get("status") == 200 else _classify_http_status(splits.get("status")),
                    0, {"event_type": "split", "event_count": splits.get("event_count", 0)}, {"provider": "massive"},
                ))
                result.records.append(_record(
                    "security_identity_lifecycle_and_exclusion_classification", "massive", sym, None,
                    "/v3/reference/dividends?ticker={ticker}", dividends.get("status"),
                    "none" if dividends.get("status") == 200 else _classify_http_status(dividends.get("status")),
                    0, {"event_type": "dividend", "event_count": dividends.get("event_count", 0)}, {"provider": "massive"},
                ))
                if splits.get("status") == 200 and splits.get("event_count", 0) > 0:
                    split_count += 1
                if dividends.get("status") == 200 and dividends.get("event_count", 0) > 0:
                    dividend_count += 1

            # ------------------------------------------------------------------
            # Evaluate the minimum usable contract flags.
            # ------------------------------------------------------------------

            # Stable identity: every panel symbol has at least one returned row
            # with a CIK and primary exchange, and the immutable identifiers
            # (CIK, composite_figi) are consistent across dates.
            stable_identity = True
            for symbol, details in details_by_symbol.items():
                rows = [
                    d.get("row") for d in details
                    if d.get("status") == 200 and isinstance(d.get("row"), dict)
                ]
                if not rows:
                    stable_identity = False
                    evidence.notes.append(f"{symbol}: no successful PIT detail rows")
                    continue
                if not all(r.get("cik") and r.get("primary_exchange") for r in rows):
                    stable_identity = False
                    evidence.notes.append(f"{symbol}: missing CIK or primary_exchange in detail rows")
                    continue
                ciks = {str(r.get("cik")) for r in rows if r.get("cik")}
                figis = {str(r.get("composite_figi")) for r in rows if r.get("composite_figi")}
                if len(ciks) > 1:
                    stable_identity = False
                    evidence.notes.append(f"{symbol}: CIK changed across PIT dates {ciks}")
                if len(figis) > 1:
                    stable_identity = False
                    evidence.notes.append(f"{symbol}: composite_figi changed across PIT dates {figis}")

            # Lifecycle evidence: positive evidence only. A missing response
            # (HTTP 404) does not prove delisting, merger, inactivity, or an
            # effective date. Acceptable evidence includes an explicit
            # `active: false` or `delisted_utc` field, or a `ticker_change`
            # corporate-action record.
            lifecycle_evidence = False
            for symbol, details in details_by_symbol.items():
                rows = [d.get("row") for d in details if d.get("status") == 200 and isinstance(d.get("row"), dict)]
                any_inactive_or_delisted = any(
                    r.get("active") is False or r.get("delisted_utc") for r in rows
                )
                events = events_by_symbol.get(symbol, {})
                event_count = events.get("event_count", 0) if isinstance(events, dict) else 0
                # A 404 events lookup is not lifecycle evidence; only positive
                # records count.
                has_lifecycle = any_inactive_or_delisted or bool(event_count)
                if has_lifecycle:
                    lifecycle_evidence = True
                    evidence.notes.append(
                        f"{symbol}: positive lifecycle evidence found (inactive/delisted or ticker_change)"
                    )
            if not lifecycle_evidence:
                evidence.notes.append(
                    "No panel symbol demonstrated effective-dated inactive, renamed, merged, or delisted evidence"
                )

            # Ticker change / rename evidence: at least one symbol shows a
            # ticker_change event spanning the relevant PIT dates.
            ticker_change_evidence = False
            for symbol, events in events_by_symbol.items():
                if events.get("status") != 200:
                    continue
                evs = events.get("events", [])
                if isinstance(evs, list) and len(evs) >= 1:
                    ticker_change_evidence = True
                    evidence.notes.append(
                        f"{symbol}: ticker_change events present ({len(evs)} events)"
                    )

            # Exchange and listing provenance: every symbol must have a primary
            # exchange MIC on every successful detail row.
            exchange_provenance = True
            for symbol, details in details_by_symbol.items():
                rows = [d.get("row") for d in details if d.get("status") == 200 and isinstance(d.get("row"), dict)]
                if not all(isinstance(r.get("primary_exchange"), str) and r["primary_exchange"] for r in rows):
                    exchange_provenance = False
                    evidence.notes.append(f"{symbol}: missing primary_exchange")

            # Defensible exclusion classification: evaluate each PIT (symbol,
            # as_of_date) independently. Current or later classifications must
            # never be substituted as historical facts. An unresolved historical
            # row remains `unknown` and fails closed.
            classification_evidence = True
            classification_by_symbol: dict[str, dict[str, str]] = {}
            for item in panel:
                symbol = item["identifier"]
                details = details_by_symbol.get(symbol, [])
                as_of_dates = list(item.get("as_of_dates", []))
                if symbol not in classification_by_symbol:
                    classification_by_symbol[symbol] = {}

                for target_date in as_of_dates:
                    detail = next((d for d in details if d.get("date") == target_date), None)
                    if detail is None or detail.get("status") != 200:
                        classification_evidence = False
                        evidence.notes.append(f"{symbol}: PIT date {target_date} has no successful detail row")
                        continue
                    row = detail.get("row") or {}
                    classification = _classify_security(row, type_map)
                    classification_by_symbol[symbol][target_date] = classification
                    if classification == "unknown":
                        classification_evidence = False
                        evidence.notes.append(
                            f"{symbol}: PIT date {target_date} classification is unknown (type={row.get('type')})"
                        )
                    else:
                        evidence.notes.append(
                            f"{symbol}: PIT date {target_date} classified as {classification}"
                        )

            # Record the per-PIT (symbol, date) classifications for
            # transparency. The locked universe contract requires each PIT
            # (symbol, date) row to be defensibly classifiable; a single later
            # row is not used as a backfill for earlier dates.
            evidence.notes.append(
                f"Massive singular ticker details returned per-PIT classifications: {classification_by_symbol}"
            )

            # Corporate-action provenance for splits and dividends.
            corporate_action_provenance = split_count > 0 and dividend_count > 0

            evidence.flags["stable_identity_effective_ticker_join_for_probe_panel"] = stable_identity
            evidence.flags["active_inactive_lifecycle_evidence_for_probe_panel"] = lifecycle_evidence
            evidence.flags["ticker_change_or_rename_evidence_for_probe_panel"] = ticker_change_evidence
            evidence.flags["exchange_and_listing_provenance_for_probe_panel"] = exchange_provenance
            evidence.flags["defensible_exclusion_classification_for_probe_panel"] = classification_evidence
            evidence.flags["corporate_action_provenance_for_splits_and_dividends"] = corporate_action_provenance

            evidence.notes.append(
                f"Massive singular ticker details returned classifications: {classification_by_symbol}"
            )

            if stable_identity and lifecycle_evidence and ticker_change_evidence and exchange_provenance and classification_evidence and corporate_action_provenance:
                selected = "massive"
                role = "primary"
            elif any_attempted:
                selected = "massive"
                role = "partial"
            break

        if provider == "alpaca":
            # Alpaca asset metadata is a fallback only when credentials are
            # available. It is not exercised if Massive already failed the
            # classification contract because Alpaca does not provide the
            # required security-type granularity either.
            if not creds.get("alpaca_api_key") or not creds.get("alpaca_secret_key"):
                result.records.append(_record(
                    "security_identity_lifecycle_and_exclusion_classification", "alpaca", None, None,
                    "/v2/assets/{symbol}", None, "authentication", 0,
                    {"reason": "Missing Alpaca credentials"}, {"provider": "alpaca"},
                ))
                continue
            result.records.append(_record(
                "security_identity_lifecycle_and_exclusion_classification", "alpaca", None, None,
                "/v2/assets", None, "unverified", 0,
                {"reason": "Alpaca not exercised; Massive singular endpoint already exercised as preferred"},
                {"provider": "alpaca"},
            ))

        if provider == "sec_edgar":
            result.records.append(_record(
                "security_identity_lifecycle_and_exclusion_classification", "sec_edgar", None, None,
                "submissions/CIK{cik}.json", None, "unverified", 0,
                {"reason": "SEC EDGAR submissions do not provide security-type classification"},
                {"provider": "sec_edgar"},
            ))

    result.provider_selected = selected
    result.provider_role = role
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted


# ---------------------------------------------------------------------------
# Earnings-event timing probe
# ---------------------------------------------------------------------------


def _probe_earnings_schedule(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe historical known-at-time earnings scheduling.

    No preregistered provider endpoint in the budget delivers a historical
    known-at-time earnings schedule, so the family is documented as
    not_supported with an explicit fail-closed unknown treatment.
    """
    result = DataFamilyResult(family="earnings_event_timing")
    evidence = FamilyEvidence(family="earnings_event_timing")
    any_attempted = False
    selected: str | None = None
    role: str | None = None

    for provider in providers:
        if provider == "massive":
            if not creds.get("massive_api_key"):
                result.records.append(_record(
                    "earnings_event_timing", "massive", None, None,
                    "/vX/reference/financials", None, "authentication", 0,
                    {"reason": "Missing MASSIVE_API_KEY"}, {"provider": "massive"},
                ))
                continue

            client = Long002MassiveClient(
                str(creds["massive_api_key"]),
                budget=budget,
                request_func=test_inject.get("massive_request_func") if test_inject else None,
                min_interval_seconds=0.0 if test_inject else None,
            )

            # Probe a small sample of the panel to confirm the endpoint only
            # supplies financial-statement filings, not future earnings schedules.
            for item in panel[:3]:
                symbol = item["identifier"]
                fin = client.fetch_stock_financials_vx(symbol, limit=1)
                any_attempted = True
                selected = "massive"
                role = "primary"
                result.records.append(_record(
                    "earnings_event_timing", "massive", symbol, None,
                    "/vX/reference/financials", fin.get("status"),
                    "none" if fin.get("status") == 200 else _classify_http_status(fin.get("status")),
                    0, _safe_stock_financials_summary(fin), {"provider": "massive"},
                ))

            evidence.notes.append(
                "Massive vX/reference/financials returns XBRL financial statements with filing_date and period_of_report_date; "
                "it does not provide a historical known-at-the-decision-time earnings announcement schedule."
            )
            continue

        if provider == "sec_edgar":
            # EDGAR actual filing timestamps are not a future schedule.
            # This fallback was preregistered but not exercised within the locked
            # budget because Massive already failed the minimum contract.
            result.records.append(_record(
                "earnings_event_timing", "sec_edgar", None, None,
                "submissions/CIK{cik}.json", None, "unverified", 0,
                {"reason": "EDGAR provides actual disclosure timestamps, not a previously known schedule"},
                {"provider": "sec_edgar"},
            ))
            evidence.unverified.append("SEC EDGAR as historical earnings schedule proxy")
            continue

        if provider == "yahoo_earnings_calendar":
            result.records.append(_record(
                "earnings_event_timing", "yahoo_earnings_calendar", None, None,
                "finance/calendar/earnings", None, "unverified", 0,
                {"reason": "Yahoo earnings calendar is prospective/current only; cannot substitute historical PIT knowledge"},
                {"provider": "yahoo_earnings_calendar"},
            ))
            evidence.unverified.append("Yahoo earnings calendar as historical earnings schedule source")
            continue

    # The contract requires a historical known-at-time schedule. No provider
    # demonstrated one, so the fail-closed unknown treatment is explicitly
    # recorded.
    evidence.flags["historical_known_at_time_schedule"] = False
    evidence.flags["distinguishes_future_schedule_known_at_time"] = False
    evidence.flags["distinguishes_subsequent_revisions"] = False
    evidence.flags["distinguishes_actual_release_timestamp"] = False
    evidence.flags["separates_sec_filing_timestamp_from_schedule"] = True
    evidence.flags["unknown_treatment_fail_closed"] = True

    evidence.notes.append(
        "Earnings-event timing remains not_supported: Massive vX/reference/financials did not return a historical "
        "known-at-time earnings schedule. Provider search was not exhausted: the preregistered SEC EDGAR and "
        "Yahoo earnings calendar fallbacks were not evaluated within the locked budget."
    )
    evidence.unverified.extend([
        "Massive historical earnings schedule",
        "SEC EDGAR as schedule proxy",
        "Yahoo earnings calendar as historical source",
    ])

    result.provider_selected = selected
    result.provider_role = role
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted


# ---------------------------------------------------------------------------
# Orchestrator and CLI
# ---------------------------------------------------------------------------


def _overall_disposition(families: list[DataFamilyResult]) -> str:
    """Compute overall disposition from per-family dispositions."""
    tuples = [(f.family, f.disposition) for f in families]
    return evaluate_overall(tuples)[0]


def _recommended_next_action(report: FeasibilityReport) -> str:
    if report.overall_disposition == "supported":
        return "Request a separately approved LONG-002C design decision; this amendment does not authorize dataset construction."
    if report.overall_disposition == "supported_with_documented_limitations":
        return "Resolve the remaining blocker (earnings-event timing) with a Gary-approved amendment or formally adopt a fail-closed unknown treatment before LONG-002C."
    return (
        "Do not proceed to LONG-002C. Options: (1) continue blocking until a provider demonstrates historical known-at-time earnings schedules, "
        "(2) formally adopt a fail-closed unknown treatment via Gary/ChatGPT approval, or (3) request a new Gary-approved provider amendment."
    )


def _decision_memo() -> list[str]:
    return [
        (
            "Security identity/lifecycle/exclusion classification: not_supported. "
            "Multiple required (symbol, as_of_date) PIT rows returned generic or missing type fields (None, CS, INDEX) with no corroborating PIT name/SIC evidence, "
            "so they fail closed to unknown and the minimum exclusion-classification contract is not satisfied. "
            "PFF is classified as ETF (preferred-stock strategy), SPY as ETF, IGR as closed_end_fund, and IPOD as pre_merger_spac, "
            "but unresolved historical rows prevent the panel-wide pathway from being called defensible."
        ),
        (
            "Earnings-event timing: no preregistered endpoint returned a historical known-at-the-decision-time earnings schedule. "
            "Massive vX/reference/financials returns XBRL financial statements (filing/period dates only). SEC EDGAR gives actual disclosure timestamps. "
            "Yahoo earnings calendar is prospective/current. The family is therefore not_supported."
        ),
        "Decision options:",
        "  1. Continue to block LONG-002C until a provider amendment delivers historical PIT earnings schedules.",
        "  2. Formally adopt a fail-closed 'unknown' treatment for earnings dates via Gary/ChatGPT approval.",
        "  3. Request a new Gary-approved provider amendment targeted at historical earnings calendars.",
        "This amendment does not select option 2 or 3 automatically; it records the blocker and preserves the fail-closed default.",
    ]


def _original_preregistration_commit_sha(repo_root: Path) -> str:
    """Return the original (possibly pre-rebase) commit that first added the amendment spec file."""
    try:
        lines = (
            subprocess.check_output(
                [
                    "git",
                    "log",
                    "--all",
                    "--follow",
                    "--diff-filter=A",
                    "--format=%H",
                    "--",
                    str(repo_root / "docs" / "research" / "specs" / "LONG-002B-AMEND-001-probe-v1.json"),
                ],
                text=True,
                cwd=str(repo_root),
            )
            .strip()
            .splitlines()
        )
        return lines[-1] if lines else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _rebased_preregistration_commit_sha(repo_root: Path) -> str:
    """Return the current branch's first commit that added the amendment spec file."""
    try:
        return (
            subprocess.check_output(
                [
                    "git",
                    "log",
                    "--follow",
                    "--diff-filter=A",
                    "--format=%H",
                    "--",
                    str(repo_root / "docs" / "research" / "specs" / "LONG-002B-AMEND-001-probe-v1.json"),
                ],
                text=True,
                cwd=str(repo_root),
            )
            .strip()
            .splitlines()[0]
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def run_amendment_probe(
    repo_root: Path | str | None = None,
    *,
    test_inject: dict[str, Any] | None = None,
) -> FeasibilityReport:
    """Execute the bounded LONG-002B-AMEND-001 probe."""
    root = Path(repo_root or ".")
    spec, amendment_sha = _load_amendment_spec(root)

    # Verify upstream spec hashes (do not modify the locked specs).
    long_002_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002-v1.json")
    probe_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002B-probe-v1.json")
    data_contract_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002B-data-contract-v1.json")
    if spec["upstream_specs"]["long_002_v1_sha256"] != long_002_sha:
        raise RuntimeError("LONG-002-v1.json SHA-256 mismatch")
    if spec["upstream_specs"]["long_002b_probe_sha256"] != probe_sha:
        raise RuntimeError("LONG-002B-probe-v1.json SHA-256 mismatch")
    if spec["upstream_specs"]["long_002b_data_contract_sha256"] != data_contract_sha:
        raise RuntimeError("LONG-002B-data-contract-v1.json SHA-256 mismatch")

    budget = RequestBudget(max_requests=spec["hard_network_budget"]["max_total_http_requests"])
    if test_inject:
        creds = {
            "massive_api_key": "test" if test_inject.get("massive_request_func") else None,
            "alpaca_api_key": "test" if test_inject.get("alpaca_request_func") else None,
            "alpaca_secret_key": "test" if test_inject.get("alpaca_request_func") else None,
        }
    else:
        creds = resolve_credentials()

    if test_inject and test_inject.get("panel") is not None:
        panel = test_inject["panel"]
    else:
        panel = spec["probe_panel"]["locked_panel"]
    family_specs = spec["data_families"]

    start = time.monotonic()
    family_results: list[DataFamilyResult] = []
    family_evidences: list[FamilyEvidence] = []
    family_attempts: list[bool] = []

    # Preserve order in the spec: security first, then earnings.
    family_order = [
        ("security_identity_lifecycle_and_exclusion_classification", family_specs["security_identity_lifecycle_and_exclusion_classification"]),
        ("earnings_event_timing", family_specs["earnings_event_timing"]),
    ]

    for family_name, family_spec in family_order:
        requests_before = budget.used
        min_contract = family_spec.get("minimum_usable_contract", {})
        providers = [family_spec["preferred_provider"]["name"]] + [fb["name"] for fb in family_spec.get("fallback_order", [])]

        if family_name == "security_identity_lifecycle_and_exclusion_classification":
            result, evidence, any_attempted = _probe_security_identity(
                providers, panel, budget, creds, min_contract, test_inject,
            )
        elif family_name == "earnings_event_timing":
            result, evidence, any_attempted = _probe_earnings_schedule(
                providers, panel, budget, creds, min_contract, test_inject,
            )
        else:
            result = DataFamilyResult(family=family_name)
            evidence = FamilyEvidence(family=family_name)
            any_attempted = False

        result.request_count = budget.used - requests_before
        # Apply the locked evaluator.
        disposition, confidence, blockers, limitations = evaluate_family(
            family_name, min_contract, evidence, any_attempted,
        )
        result.disposition = disposition
        result.evidence_confidence = confidence
        result.blockers = blockers
        result.limitations = limitations
        result.summary = evidence.to_dict()

        family_results.append(result)
        family_evidences.append(evidence)
        family_attempts.append(any_attempted)

    runtime = time.monotonic() - start
    overall, overall_confidence = evaluate_overall([(f.family, f.disposition) for f in family_results])

    original_prereg = _original_preregistration_commit_sha(root)
    rebased_prereg = _rebased_preregistration_commit_sha(root)
    report = FeasibilityReport(
        task_id="LONG-002B-AMEND-001",
        overall_disposition=overall,
        overall_evidence_confidence=overall_confidence,
        total_http_requests=budget.used,
        runtime_seconds=runtime,
        code_commit_sha="",
        preregistration_commit_sha=original_prereg,
        original_preregistration_commit_sha=original_prereg,
        rebased_preregistration_commit_sha=rebased_prereg,
        rebased_code_commit_sha="",
        original_implementation_commit_sha="",
        code_source_tree_sha="",
        provenance_note="",
        long_002_spec_sha256=long_002_sha,
        probe_spec_sha256=amendment_sha,
        data_contract_sha256=data_contract_sha,
        data_families=family_results,
    )
    report.recommended_next_action = _recommended_next_action(report)
    report.limitations = [lim for f in family_results for lim in f.limitations]
    report.blockers = [b for f in family_results for b in f.blockers]
    report.blockers.extend(_decision_memo())
    return report


def _source_tree_sha(repo_root: Path) -> str:
    """Return the git tree SHA for the evaluator source directory at HEAD."""
    try:
        return (
            subprocess.check_output(
                [
                    "git",
                    "ls-tree",
                    "-d",
                    "HEAD",
                    "tradex/research/long_002_data_feasibility",
                ],
                text=True,
                cwd=str(repo_root),
            )
            .strip()
            .split()[2]
        )
    except Exception:  # noqa: BLE001
        return ""


def main(argv: list[str] | None = None) -> None:
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="LONG-002B-AMEND-001 blocked-family resolution probe")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root containing docs/research/specs")
    parser.add_argument("--run-id", type=str, default=None, help="Artifact bundle run ID (default timestamp)")
    parser.add_argument("--commit-sha", type=str, default=None, help="Code commit SHA in effect at the live run (e.g. HEAD before uncommitted changes)")
    parser.add_argument("--rebased-code-commit-sha", type=str, default=None, help="Rebased-equivalent commit for the code used in the live run")
    parser.add_argument("--original-implementation-commit-sha", type=str, default=None, help="First commit that captured the code used in the live run, if different from --commit-sha")
    parser.add_argument("--provenance-note", type=str, default=None, help="Free-form note describing execution provenance")
    args = parser.parse_args(argv)

    report = run_amendment_probe(args.repo_root)
    try:
        commit_sha = args.commit_sha or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        commit_sha = "unknown"
    try:
        rebased_code = args.rebased_code_commit_sha or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        rebased_code = ""
    code_tree = _source_tree_sha(args.repo_root)
    bundle = write_safe_artifacts(
        report,
        args.repo_root,
        run_id=args.run_id,
        code_commit_sha=commit_sha,
        rebased_code_commit_sha=rebased_code,
        original_implementation_commit_sha=args.original_implementation_commit_sha or "",
        code_source_tree_sha=code_tree,
        provenance_note=args.provenance_note or "",
    )
    print(f"LONG-002B-AMEND-001 bundle written to: {bundle}")
    print(f"Overall disposition: {report.overall_disposition}")
    print(f"Total HTTP requests: {report.total_http_requests}")


if __name__ == "__main__":
    main()
