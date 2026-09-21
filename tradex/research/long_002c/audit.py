"""Evidence-backed universe construction and PIT eligibility audit for LONG-002C.

Executes real, bounded provider queries against Massive, SEC EDGAR, and Alpaca,
enforces cryptographic provenance, persistent response caching, strict security classification,
and point-in-time shares outstanding resolution.
Labels planning assumptions as planning_estimate_only and separates them from observed metrics.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from tradex.research.long_002c.cache import ResponseCache
from tradex.research.long_002c.identity import (
    CLASSIFICATION_EXCLUDED_SECURITY_TYPE,
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    classify_security,
)
from tradex.research.long_002c.manifest import build_candidate_manifest_from_snapshots
from tradex.research.long_002c.market_cap import calculate_pit_market_cap, extract_pit_shares_fact
from tradex.research.long_002c.providers import AlpacaDailyClient, EdgarClient, MassiveRefClient
from tradex.research.long_002c.spec import DEV_END, DEV_START, REPO_ROOT

# Explicitly labeled planning hypotheses
PLANNING_ESTIMATES = {
    "status": "planning_estimate_only (unverified baseline hypotheses)",
    "description": "Initial design planning figures; NOT observed repository evidence.",
    "annual_candidate_estimates": {
        "2016": {"us_common_stocks_active": 3600, "mcap_gte_3b": 850, "sp500": 505},
        "2017": {"us_common_stocks_active": 3550, "mcap_gte_3b": 920, "sp500": 505},
        "2018": {"us_common_stocks_active": 3500, "mcap_gte_3b": 980, "sp500": 505},
        "2019": {"us_common_stocks_active": 3520, "mcap_gte_3b": 1050, "sp500": 505},
        "2020": {"us_common_stocks_active": 3650, "mcap_gte_3b": 1150, "sp500": 505},
    },
    "estimated_unique_candidates_2016_2020": 1250,
}

SAMPLE_CANDIDATE_PANEL = [
    {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."},
    {"ticker": "MSFT", "cik": "0000789019", "name": "Microsoft Corp"},
    {"ticker": "AMZN", "cik": "0001018724", "name": "Amazon Com Inc"},
    {"ticker": "FB", "cik": "0001326801", "name": "Facebook Inc"},
    {"ticker": "JNJ", "cik": "0000200406", "name": "Johnson & Johnson"},
    {"ticker": "JPM", "cik": "0000019617", "name": "JPMorgan Chase & Co"},
    {"ticker": "XOM", "cik": "0000034088", "name": "Exxon Mobil Corp"},
    {"ticker": "GE", "cik": "0000040545", "name": "General Electric Co"},
    {"ticker": "IBM", "cik": "0000051143", "name": "International Business Machines Corp"},
    {"ticker": "WMT", "cik": "0000104169", "name": "Walmart Inc"},
    {"ticker": "PG", "cik": "0000080424", "name": "Procter & Gamble Co"},
    {"ticker": "PFE", "cik": "0000078003", "name": "Pfizer Inc"},
    {"ticker": "KO", "cik": "0000021344", "name": "Coca-Cola Co"},
    {"ticker": "DIS", "cik": "0000027419", "name": "Walt Disney Co"},
    {"ticker": "BA", "cik": "0000012927", "name": "Boeing Co"},
    {"ticker": "INTC", "cik": "0000050863", "name": "Intel Corp"},
    {"ticker": "CSCO", "cik": "0000858877", "name": "Cisco Systems Inc"},
    {"ticker": "V", "cik": "0001403161", "name": "Visa Inc"},
    {"ticker": "MA", "cik": "0001141391", "name": "Mastercard Inc"},
    {"ticker": "HD", "cik": "0000354950", "name": "Home Depot Inc"},
    {"ticker": "UNH", "cik": "0000731766", "name": "UnitedHealth Group Inc"},
    {"ticker": "CVX", "cik": "0000093410", "name": "Chevron Corp"},
    {"ticker": "MRK", "cik": "0000310158", "name": "Merck & Co Inc"},
    {"ticker": "NVDA", "cik": "0001045810", "name": "NVIDIA Corp"},
    {"ticker": "BAC", "cik": "0000070858", "name": "Bank of America Corp"},
]


def execute_bounded_universe_audit(
    creds: dict[str, str | None],
    sample_dates: list[str] | None = None,
    candidate_panel: list[dict[str, str]] | None = None,
    cache: ResponseCache | None = None,
) -> dict[str, Any]:
    """Execute evidence-backed bounded preflight audit using real provider calls."""
    cache = cache or ResponseCache()
    sample_dates = sample_dates or ["2016-01-04", "2018-01-02", "2020-01-02"]
    panel = candidate_panel or SAMPLE_CANDIDATE_PANEL

    massive_key = creds.get("massive_api_key")
    alpaca_k = creds.get("alpaca_api_key")
    alpaca_s = creds.get("alpaca_secret_key")

    massive = MassiveRefClient(massive_key, cache=cache) if massive_key else None
    alpaca = (
        AlpacaDailyClient(alpaca_k, alpaca_s, cache=cache)
        if (alpaca_k and alpaca_s)
        else None
    )
    edgar = EdgarClient(cache=cache)

    audit_timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    print("\n" + "=" * 70)
    print("=== EVIDENCE-BACKED HISTORICAL UNIVERSE & PIT ELIGIBILITY AUDIT ===")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. Planning Estimates vs Observed Metrics Banner
    # -------------------------------------------------------------
    print("\n[Section 1: Planning Estimates vs Observed Data]")
    print(f"  Status: {PLANNING_ESTIMATES['status']}")
    print(f"  Estimated unique candidates across 2016-2020: ~{PLANNING_ESTIMATES['estimated_unique_candidates_2016_2020']}")
    for yr, d in PLANNING_ESTIMATES["annual_candidate_estimates"].items():
        print(f"    - {yr}: ~{d['us_common_stocks_active']} active common stocks, ~{d['mcap_gte_3b']} >= $3B mcap (PLANNING ONLY)")

    # -------------------------------------------------------------
    # 2. Reference Snapshot Probes across Sample Dates
    # -------------------------------------------------------------
    print("\n[Section 2: Massive Reference Snapshot Probes]")
    snapshot_records_by_date: dict[str, list[dict[str, Any]]] = {}
    snapshot_metrics_list: list[dict[str, Any]] = []

    if massive:
        for pit_date in sample_dates:
            t0 = time.monotonic()
            recs, prov = massive.fetch_reference_snapshot(pit_date, active=True, safety_max_pages=1)
            dur = time.monotonic() - t0
            snapshot_records_by_date[pit_date] = recs

            total_recs = len(recs)
            common_stocks = 0
            excluded_sec = 0
            unknown_sec = 0
            with_cik = 0
            with_figi = 0

            for r in recs:
                c = classify_security(r)
                if c == CLASSIFICATION_SUPPORTED_COMMON_STOCK:
                    common_stocks += 1
                elif c == CLASSIFICATION_EXCLUDED_SECURITY_TYPE:
                    excluded_sec += 1
                else:
                    unknown_sec += 1

                if r.get("cik"):
                    with_cik += 1
                if r.get("composite_figi"):
                    with_figi += 1

            cik_pct = (with_cik / total_recs * 100.0) if total_recs > 0 else 0.0
            figi_pct = (with_figi / total_recs * 100.0) if total_recs > 0 else 0.0
            common_pct = (common_stocks / total_recs * 100.0) if total_recs > 0 else 0.0

            m = {
                "pit_date": pit_date,
                "raw_tickers_returned": total_recs,
                "supported_common_stock": common_stocks,
                "common_stock_pct": round(common_pct, 1),
                "excluded_security_type": excluded_sec,
                "unknown_fail_closed": unknown_sec,
                "with_cik": with_cik,
                "cik_coverage_pct": round(cik_pct, 1),
                "with_figi": with_figi,
                "figi_coverage_pct": round(figi_pct, 1),
                "request_duration_seconds": round(dur, 2),
                "response_sha256": prov[0].response_sha256 if prov else "",
            }
            snapshot_metrics_list.append(m)

            print(
                f"  Snapshot {pit_date}: {total_recs} raw tickers ({dur:.2f}s) | "
                f"Common Stock: {common_stocks} ({common_pct:.1f}%) | "
                f"CIK Cov: {cik_pct:.1f}% | FIGI Cov: {figi_pct:.1f}%"
            )
    else:
        print("  WARNING: Massive API key missing; reference snapshots skipped.")

    # -------------------------------------------------------------
    # 3. Candidate Manifest & Multi-Dated Ticker Aggregation
    # -------------------------------------------------------------
    print("\n[Section 3: Candidate Manifest Pipeline]")
    if snapshot_records_by_date:
        candidates, manifest_metrics = build_candidate_manifest_from_snapshots(snapshot_records_by_date)
        print(f"  Discovered unique common stock securities across snapshots: {len(candidates)}")
        print(f"  CIK coverage across candidates: {manifest_metrics.cik_coverage_pct}% ({manifest_metrics.with_cik_count}/{len(candidates)})")
        print(f"  FIGI coverage across candidates: {manifest_metrics.figi_coverage_pct}% ({manifest_metrics.with_figi_count}/{len(candidates)})")
    else:
        candidates = []
        manifest_metrics = None
        print("  Manifest pipeline skipped (no snapshots).")

    # -------------------------------------------------------------
    # 4. Bounded Sample Candidate Audit (Bars, EDGAR Facts, PIT Mcap)
    # -------------------------------------------------------------
    print(f"\n[Section 4: Bounded Candidate Audit ({len(panel)} Securities)]")
    candidate_audit_results: list[dict[str, Any]] = []
    bars_available_count = 0
    edgar_facts_available_count = 0
    pit_shares_available_count = 0
    pit_mcap_gte_3b_count = 0

    probe_date = "2016-01-04"

    for item in panel:
        ticker = item["ticker"]
        cik = item["cik"]
        name = item["name"]

        # 4a. Alpaca Daily Bars Probe
        has_bars = False
        bar_count = 0
        as_traded_close = None
        if alpaca:
            try:
                bars, _ = alpaca.fetch_daily_bars(ticker, "2016-01-01T00:00:00Z", "2016-01-31T23:59:59Z")
                if bars:
                    has_bars = True
                    bar_count = len(bars)
                    as_traded_close = float(bars[0].get("c", 0.0))
                    bars_available_count += 1
            except Exception:  # noqa: BLE001
                has_bars = False

        # 4b. SEC EDGAR Company Facts Probe
        has_edgar_facts = False
        shares_fact = None
        mcap = None
        mcap_gte_3b = False

        try:
            facts_data, _ = edgar.fetch_company_facts(cik)
            if facts_data and "facts" in facts_data:
                has_edgar_facts = True
                edgar_facts_available_count += 1
                shares_fact = extract_pit_shares_fact(facts_data, session_date=probe_date)
                if shares_fact:
                    pit_shares_available_count += 1
                    if as_traded_close and as_traded_close > 0:
                        mcap, _ = calculate_pit_market_cap(shares_fact, as_traded_close)
                        if mcap is not None and mcap >= 3_000_000_000.0:
                            mcap_gte_3b = True
                            pit_mcap_gte_3b_count += 1
        except Exception:  # noqa: BLE001
            has_edgar_facts = False

        res = {
            "ticker": ticker,
            "cik": cik,
            "name": name,
            "probe_date": probe_date,
            "alpaca_bars_jan_2016": has_bars,
            "bar_count": bar_count,
            "as_traded_close": as_traded_close,
            "edgar_facts_available": has_edgar_facts,
            "pit_shares_outstanding": shares_fact.shares_outstanding if shares_fact else None,
            "shares_filing_date": shares_fact.filing_date if shares_fact else None,
            "shares_concept": shares_fact.concept if shares_fact else None,
            "pit_market_cap": mcap,
            "pit_market_cap_gte_3b": mcap_gte_3b,
        }
        candidate_audit_results.append(res)
        mcap_str = f"${(mcap / 1e9):.1f}B" if mcap else "N/A"
        print(f"  - {ticker:<5} (CIK {cik}): Bars={bar_count:>2} | Shares={bool(shares_fact)} | Mcap={mcap_str:<8} | >=$3B={mcap_gte_3b}")

    n_sample = len(panel)
    bars_pct = (bars_available_count / n_sample * 100.0) if n_sample > 0 else 0.0
    facts_pct = (edgar_facts_available_count / n_sample * 100.0) if n_sample > 0 else 0.0
    shares_pct = (pit_shares_available_count / n_sample * 100.0) if n_sample > 0 else 0.0
    mcap_pct = (pit_mcap_gte_3b_count / n_sample * 100.0) if n_sample > 0 else 0.0

    print(f"\n  Candidate Sample Summary ({probe_date}):")
    print(f"    - Alpaca Jan 2016 Bars Coverage: {bars_pct:.1f}% ({bars_available_count}/{n_sample})")
    print(f"    - EDGAR Company Facts Coverage: {facts_pct:.1f}% ({edgar_facts_available_count}/{n_sample})")
    print(f"    - PIT Shares Outstanding Coverage: {shares_pct:.1f}% ({pit_shares_available_count}/{n_sample})")
    print(f"    - Point-in-Time Market Cap >= $3B: {mcap_pct:.1f}% ({pit_mcap_gte_3b_count}/{n_sample})")

    # -------------------------------------------------------------
    # 5. Corporate Actions Budget & Recalculation
    # -------------------------------------------------------------
    print("\n[Section 5: Corporate-Action Budget Recalculation]")
    # Test corporate actions on a bounded panel of 3 sample securities
    corp_sample = panel[:3]
    corp_sample_results: list[dict[str, Any]] = []
    if massive:
        for c in corp_sample:
            t_sym = c["ticker"]
            splits, divs, _prov_corp = massive.fetch_corporate_actions(t_sym)
            corp_sample_results.append({
                "ticker": t_sym,
                "splits_count": len(splits),
                "dividends_count": len(divs),
                "calls_made": 2,
            })
            print(f"  Corporate Actions for {t_sym}: {len(splits)} splits, {len(divs)} dividends (2 requests)")

    # Formulaic budget
    est_universe_candidates = 1250  # planning estimate baseline
    req_per_sec = 2  # 1 split + 1 dividend
    total_corp_reqs = est_universe_candidates * req_per_sec
    pacing_sec = 12.1
    uncached_total_sec = total_corp_reqs * pacing_sec
    uncached_hours = round(uncached_total_sec / 3600.0, 2)

    corp_budget = {
        "calls_per_security": req_per_sec,
        "endpoints": ["/v3/reference/splits", "/v3/reference/dividends"],
        "rate_limit": "5 req/min (12.1s delay between uncached calls)",
        "sample_securities_tested": len(corp_sample_results),
        "hypothetical_1000_securities_calls": 2000,
        "hypothetical_1000_securities_uncached_hours": round((2000 * pacing_sec) / 3600.0, 2),
        "hypothetical_1250_securities_calls": total_corp_reqs,
        "hypothetical_1250_securities_uncached_hours": uncached_hours,
        "cached_subsequent_calls": 0,
        "cached_subsequent_hours": 0.0,
        "cache_directory": str(cache.cache_dir),
    }

    print("  Budget Specification:")
    print(f"    - Calls per security: {req_per_sec} (1 splits + 1 dividends)")
    print(f"    - Rate limit pacing: {pacing_sec}s per request (5 req/min)")
    print("    - Uncached cost for 1,000 securities: 2,000 requests (~6.72 hours)")
    print(f"    - Uncached cost for 1,250 securities: 2,500 requests (~{uncached_hours} hours)")
    print(f"    - Persistent cache: Enabled under {cache.cache_dir}")
    print("    - Subsequent execution cost on cache hits: 0 network requests (0.0 hours)")

    # -------------------------------------------------------------
    # 6. Assemble Full Audit Bundle
    # -------------------------------------------------------------
    audit_bundle = {
        "audit_version": "1.0",
        "audit_timestamp_utc": audit_timestamp,
        "development_window": {"start": DEV_START, "end": DEV_END},
        "planning_estimates": PLANNING_ESTIMATES,
        "reference_snapshot_metrics": snapshot_metrics_list,
        "candidate_manifest_summary": manifest_metrics.to_dict() if manifest_metrics else None,
        "bounded_candidate_sample_metrics": {
            "probe_session_date": probe_date,
            "sample_size": n_sample,
            "alpaca_bars_available_count": bars_available_count,
            "alpaca_bars_coverage_pct": bars_pct,
            "edgar_facts_available_count": edgar_facts_available_count,
            "edgar_facts_coverage_pct": facts_pct,
            "pit_shares_available_count": pit_shares_available_count,
            "pit_shares_coverage_pct": shares_pct,
            "pit_mcap_gte_3b_count": pit_mcap_gte_3b_count,
            "pit_mcap_gte_3b_pct": mcap_pct,
            "details": candidate_audit_results,
        },
        "corporate_actions_budget": corp_budget,
    }

    # Persist audit artifact
    out_dir = REPO_ROOT / "data" / "research" / "long_002c"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "evidence_backed_universe_audit.json"
    out_file.write_text(json.dumps(audit_bundle, indent=2), encoding="utf-8")
    print(f"\nAudit complete. Artifact written to: {out_file}")

    return audit_bundle
