"""Stage B Eligibility Screening for discovered LONG-002C candidates.

Screens candidate securities against exact locked LONG-002 Stage B eligibility criteria:
1. Security classification: must be verified supported common stock.
2. Ticker resolution: effective historical ticker intervals must be verified.
3. Historical daily bars: requires >=63 completed trading sessions up to decision date.
4. Trading history cohort:
   - >=252 sessions: established cohort
   - 63-251 sessions: recent IPO cohort ONLY with verified listing/prospectus provenance within 365 days;
     else unverified_history_truncated (fail closed).
   - <63 sessions: insufficient_trading_history (fail closed).
5. Price floor:
   - as-traded close >= $5.00
   - prior 20-session median as-traded close >= $5.00
6. Liquidity thresholds:
   - prior 20-session median as-traded dollar volume >= $20,000,000 ($20M)
   - prior 60-session median as-traded dollar volume >= $10,000,000 ($10M)
7. Market cap / index pathway:
   - verified point-in-time allowed index membership; OR
   - valid point-in-time market cap >= $3B (via SEC EDGAR facts * as-traded close).
   (When index membership is unsupported point-in-time, it fails closed to False).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002c.calendar import get_trading_sessions
from tradex.research.long_002c.identity import CLASSIFICATION_SUPPORTED_COMMON_STOCK
from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002c.market_cap import compute_security_pit_market_caps
from tradex.research.long_002c.providers import (
    AlpacaDailyClient,
    EdgarClient,
    ProviderDataUnavailable,
)
from tradex.research.long_002c.spec import DEV_END, DEV_START, WARMUP_START, enforce_split_guard


def screen_candidate_security(
    candidate: CandidateSecurity,
    alpaca: AlpacaDailyClient,
    edgar: EdgarClient,
    trading_sessions: list[str] | None = None,
    dev_start: str = DEV_START,
    dev_end: str = DEV_END,
    warmup_start: str = WARMUP_START,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Evaluate whether a candidate security qualifies for Stage B on >=1 development session.

    Returns:
        (is_eligible, rejection_reasons, detail_metrics)
    """
    enforce_split_guard(dev_end)

    # 1. Classification check
    if candidate.security_type != CLASSIFICATION_SUPPORTED_COMMON_STOCK:
        return False, [f"excluded_classification_{candidate.security_type}"], {
            "eligible_sessions": 0,
            "reason": f"Classification '{candidate.security_type}' is not verified common stock (fail closed)",
        }

    # 2. Ingest interval-aware daily bars for candidate verified intervals
    from tradex.research.long_002c.bars import load_interval_aware_daily_bars

    df_bars, _, bar_meta = load_interval_aware_daily_bars(
        candidate=candidate,
        alpaca=alpaca,
        warmup_start=warmup_start,
        dev_end=dev_end,
        load_split_adjusted=False,
    )

    if bar_meta.get("provider_failure"):
        fail_info = bar_meta["provider_failure"]
        fail_type = fail_info.get("failure_type", "provider_request_failed")
        return False, [fail_type], {
            "immutable_security_id": candidate.immutable_security_id,
            "primary_symbol": candidate.primary_symbol,
            "cik": candidate.cik,
            "eligible_sessions": 0,
            "first_eligible_date": None,
            "is_provider_failure": True,
            "provider_failure": fail_info,
            "rejection_counts": {fail_type: 1},
            "reason": f"Provider failure for {candidate.primary_symbol}: {fail_info.get('reason')}",
            "bar_meta": bar_meta,
        }

    if df_bars.empty:
        return False, ["true_no_trading_bars"], {
            "immutable_security_id": candidate.immutable_security_id,
            "primary_symbol": candidate.primary_symbol,
            "cik": candidate.cik,
            "eligible_sessions": 0,
            "first_eligible_date": None,
            "is_provider_failure": False,
            "rejection_counts": {"true_no_trading_bars": 1},
            "reason": f"Genuine empty bars returned for {candidate.primary_symbol} across verified intervals",
            "bar_meta": bar_meta,
        }

    bar_dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in df_bars.index]
    bar_date_set = set(bar_dates)

    all_sessions = trading_sessions or get_trading_sessions(warmup_start, dev_end)
    dev_sessions = [s for s in all_sessions if dev_start <= s <= dev_end]

    # 3. Market cap resolution via SEC EDGAR
    company_facts = None
    acceptance_map = None
    if candidate.cik:
        try:
            company_facts, _ = edgar.fetch_company_facts(candidate.cik)
            if hasattr(edgar, "fetch_submissions"):
                subs_data, _ = edgar.fetch_submissions(candidate.cik)
                if subs_data:
                    acceptance_map = EdgarClient.get_accession_acceptance_map(subs_data)
        except ProviderDataUnavailable as exc:
            fail_type = getattr(exc, "failure_type", "edgar_provider_failed")
            return False, [fail_type], {
                "immutable_security_id": candidate.immutable_security_id,
                "primary_symbol": candidate.primary_symbol,
                "cik": candidate.cik,
                "eligible_sessions": 0,
                "first_eligible_date": None,
                "is_provider_failure": True,
                "provider_failure": {
                    "provider": "sec_edgar",
                    "failure_type": fail_type,
                    "reason": str(exc),
                    "url": getattr(exc, "url", None),
                    "status_code": getattr(exc, "status_code", None),
                },
                "rejection_counts": {fail_type: 1},
                "reason": f"EDGAR provider failure for CIK {candidate.cik}: {exc}",
                "bar_meta": bar_meta,
            }

    as_traded_closes_dict = {
        d: float(df_bars.loc[d, "as_traded_close"].iloc[-1])
        if isinstance(df_bars.loc[d, "as_traded_close"], pd.Series)
        else float(df_bars.loc[d, "as_traded_close"])
        for d in dev_sessions
        if d in bar_date_set
    }

    market_caps, _market_cap_reasons, pit_shares_facts = compute_security_pit_market_caps(
        company_facts=company_facts,
        session_dates=dev_sessions,
        as_traded_closes=as_traded_closes_dict,
        cutoff_time="20:30",
        accession_acceptance_map=acceptance_map,
    )

    # 4. Check eligibility across development sessions
    eligible_sessions = 0
    first_eligible_date: str | None = None
    rejection_counts: dict[str, int] = {}

    for session_date in dev_sessions:
        if session_date not in bar_date_set:
            continue

        idx = bar_dates.index(session_date)
        hist_slice = df_bars.iloc[: idx + 1]
        n_hist = len(hist_slice)

        # A. History cohort
        if n_hist < 63:
            rejection_counts["insufficient_trading_history"] = rejection_counts.get("insufficient_trading_history", 0) + 1
            continue
        elif 63 <= n_hist < 252:
            # Requires positive listing provenance within 365 calendar days
            has_listing = False
            listing_provenance = candidate.listing_lifecycle_provenance
            listing_date_str = (
                listing_provenance.get("listing_date")
                if isinstance(listing_provenance, dict)
                else None
            )
            if listing_date_str:
                try:
                    dt_listing = date.fromisoformat(listing_date_str[:10])
                    dt_session = date.fromisoformat(session_date[:10])
                    if 0 <= (dt_session - dt_listing).days <= 365:
                        has_listing = True
                except ValueError:
                    has_listing = False
            if not has_listing:
                rejection_counts["unverified_history_truncated"] = rejection_counts.get("unverified_history_truncated", 0) + 1
                continue

        # B. As-traded close and 20d median close >= $5.00
        as_traded_close = float(hist_slice["as_traded_close"].iloc[-1])
        if as_traded_close < 5.0:
            rejection_counts["price_below_5"] = rejection_counts.get("price_below_5", 0) + 1
            continue

        closes_20 = hist_slice["as_traded_close"].iloc[-20:].tolist() if n_hist >= 20 else []
        if not closes_20 or float(np.median(closes_20)) < 5.0:
            rejection_counts["price_below_5"] = rejection_counts.get("price_below_5", 0) + 1
            continue

        # C. 20-session median as-traded dollar volume >= $20M
        vols_20 = hist_slice["volume"].iloc[-20:].tolist() if n_hist >= 20 else []
        dvol_20 = [c * v for c, v in zip(closes_20, vols_20)]
        if len(dvol_20) < 20 or float(np.median(dvol_20)) < 20_000_000.0:
            rejection_counts["dollar_volume_20d_below_20m"] = rejection_counts.get("dollar_volume_20d_below_20m", 0) + 1
            continue

        # D. 60-session median as-traded dollar volume >= $10M
        closes_60 = hist_slice["as_traded_close"].iloc[-60:].tolist() if n_hist >= 60 else []
        vols_60 = hist_slice["volume"].iloc[-60:].tolist() if n_hist >= 60 else []
        dvol_60 = [c * v for c, v in zip(closes_60, vols_60)]
        if len(dvol_60) < 60 or float(np.median(dvol_60)) < 10_000_000.0:
            rejection_counts["dollar_volume_60d_below_10m"] = rejection_counts.get("dollar_volume_60d_below_10m", 0) + 1
            continue

        # E. Market cap >= $3B (or verified index membership; index membership is unsupported PIT)
        mcap = market_caps.get(session_date)
        if mcap is None or mcap < 3_000_000_000.0:
            rejection_counts["market_cap_below_3b_or_missing"] = rejection_counts.get("market_cap_below_3b_or_missing", 0) + 1
            continue

        # Session passed all Stage B criteria
        eligible_sessions += 1
        if first_eligible_date is None:
            first_eligible_date = session_date

    is_eligible = eligible_sessions > 0
    reasons = [] if is_eligible else list(rejection_counts.keys())
    exact_acc_count = sum(
        1 for f in pit_shares_facts.values() if f.availability_source == "exact_acceptance_timestamp"
    )
    conservative_date_count = sum(
        1 for f in pit_shares_facts.values() if f.availability_source == "date_only_next_session_conservative"
    )

    details = {
        "immutable_security_id": candidate.immutable_security_id,
        "primary_symbol": candidate.primary_symbol,
        "cik": candidate.cik,
        "eligible_sessions": eligible_sessions,
        "first_eligible_date": first_eligible_date,
        "rejection_counts": rejection_counts,
        "exact_acceptance_shares_count": exact_acc_count,
        "conservative_date_only_shares_count": conservative_date_count,
    }
    return is_eligible, reasons, details


def screen_candidates_manifest(
    candidates: list[CandidateSecurity],
    alpaca: AlpacaDailyClient,
    edgar: EdgarClient,
    max_candidates: int | None = None,
    on_progress: Callable[[int, int, str, bool], None] | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Screen candidate securities in a manifest against Stage B criteria.

    Returns:
        (eligible_security_ids, rejected_security_ids, screening_summary)
    """
    eligible_ids: list[str] = []
    rejected_ids: list[str] = []
    provider_failed_ids: list[str] = []
    provider_failures: dict[str, Any] = {}
    provider_failure_reason_counts: dict[str, int] = {}
    genuine_no_bars_count = 0
    details_by_id: dict[str, Any] = {}
    aggregated_rejection_reasons: dict[str, int] = {}

    all_sessions = get_trading_sessions(WARMUP_START, DEV_END)
    cands_to_eval = candidates[:max_candidates] if max_candidates else candidates

    total_with_mcap = 0
    total_with_ticker_res = 0
    total_with_common_stock = 0
    early_2016_attrition_count = 0
    total_exact_acceptance_shares = 0
    total_conservative_date_shares = 0

    for idx, cand in enumerate(cands_to_eval, 1):
        sec_id = cand.immutable_security_id
        is_elig, reasons, details = screen_candidate_security(
            candidate=cand,
            alpaca=alpaca,
            edgar=edgar,
            trading_sessions=all_sessions,
        )
        if details.get("is_provider_failure"):
            provider_failed_ids.append(sec_id)
            provider_failures[sec_id] = details.get("provider_failure", {})
            for r in reasons:
                provider_failure_reason_counts[r] = provider_failure_reason_counts.get(r, 0) + 1
        elif is_elig:
            eligible_ids.append(sec_id)
        else:
            rejected_ids.append(sec_id)
            if "true_no_trading_bars" in reasons:
                genuine_no_bars_count += 1
            for r in reasons:
                aggregated_rejection_reasons[r] = aggregated_rejection_reasons.get(r, 0) + 1
            for r, cnt in details.get("rejection_counts", {}).items():
                if cnt > 0 and r not in reasons:
                    aggregated_rejection_reasons[r] = aggregated_rejection_reasons.get(r, 0) + 1

        details_by_id[sec_id] = details

        if cand.security_type == CLASSIFICATION_SUPPORTED_COMMON_STOCK:
            total_with_common_stock += 1

        if cand.cik:
            total_with_mcap += 1

        total_exact_acceptance_shares += details.get("exact_acceptance_shares_count", 0)
        total_conservative_date_shares += details.get("conservative_date_only_shares_count", 0)

        # Check ticker intervals resolution
        bar_meta = details.get("bar_meta", {})
        if not bar_meta.get("unresolved_gaps"):
            total_with_ticker_res += 1

        # Early 2016 attrition: security did not trade or was not eligible in early 2016
        first_elig = details.get("first_eligible_date")
        if not first_elig or first_elig > "2016-03-31":
            early_2016_attrition_count += 1

        if on_progress:
            on_progress(idx, len(cands_to_eval), cand.primary_symbol, is_elig)

    n_eval = len(cands_to_eval)
    total_resolved_shares = total_exact_acceptance_shares + total_conservative_date_shares
    alpaca_metrics = alpaca.get_audit_metrics() if hasattr(alpaca, "get_audit_metrics") else {}
    edgar_metrics = edgar.get_audit_metrics() if hasattr(edgar, "get_audit_metrics") else {}
    alpaca_failures_count = sum(1 for p in provider_failures.values() if p.get("provider", "alpaca") == "alpaca")
    edgar_failures_count = sum(1 for p in provider_failures.values() if p.get("provider") == "sec_edgar")
    summary = {
        "total_evaluated": n_eval,
        "eligible_count": len(eligible_ids),
        "rejected_count": len(rejected_ids),
        "provider_failures_count": len(provider_failed_ids),
        "unresolved_provider_failures_count": len(provider_failed_ids),
        "unresolved_alpaca_provider_failures": alpaca_failures_count,
        "unresolved_edgar_provider_failures": edgar_failures_count,
        "genuine_no_bars_count": genuine_no_bars_count,
        "pass_rate_pct": round(len(eligible_ids) / n_eval * 100.0, 2) if n_eval else 0.0,
        "eligible_security_ids": sorted(eligible_ids),
        "rejected_security_ids": sorted(rejected_ids),
        "provider_failed_security_ids": sorted(provider_failed_ids),
        "provider_failures": provider_failures,
        "provider_failure_reason_counts": provider_failure_reason_counts,
        "rejection_reason_counts": aggregated_rejection_reasons,
        "pit_market_cap_coverage_pct": round(total_with_mcap / n_eval * 100.0, 2) if n_eval else 0.0,
        "ticker_resolution_coverage_pct": round(total_with_ticker_res / n_eval * 100.0, 2) if n_eval else 0.0,
        "classification_coverage_pct": round(total_with_common_stock / n_eval * 100.0, 2) if n_eval else 0.0,
        "early_2016_attrition_pct": round(early_2016_attrition_count / n_eval * 100.0, 2) if n_eval else 0.0,
        "exact_acceptance_shares_count": total_exact_acceptance_shares,
        "conservative_date_only_shares_count": total_conservative_date_shares,
        "exact_acceptance_shares_pct": round(total_exact_acceptance_shares / total_resolved_shares * 100.0, 2) if total_resolved_shares else 0.0,
        "conservative_date_only_shares_pct": round(total_conservative_date_shares / total_resolved_shares * 100.0, 2) if total_resolved_shares else 0.0,
        "alpaca_audit_metrics": alpaca_metrics,
        "edgar_audit_metrics": edgar_metrics,
    }

    return eligible_ids, rejected_ids, summary
