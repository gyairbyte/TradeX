"""Point-in-time (PIT) market capitalization calculation using SEC EDGAR company facts.

Implements strict point-in-time shares outstanding resolution:
pit_market_cap = latest defensible shares outstanding known at decision time * as_traded_close
via SEC EDGAR facts:
- dei/EntityCommonStockSharesOutstanding
- us-gaap/CommonStockSharesOutstanding

Strict Invariants:
1. Only defensible point-in-time shares outstanding concepts are allowed.
   Weighted-average shares (e.g. us-gaap/WeightedAverageNumberOfSharesOutstandingBasic)
   are income-statement denominators, NOT point-in-time shares outstanding, and are PROHIBITED.
2. Availability Timing Hierarchy:
   A. Where an SEC acceptance timestamp can be resolved for the accession:
      acceptance_timestamp <= decision_timestamp_utc.
   B. If only filing DATE is available and exact acceptance time cannot be established:
      conservative rule: the fact becomes usable beginning at the NEXT trading session's
      09:00 snapshot, NOT during the filing date itself (session_date > filing_date).
3. If no filed shares fact exists on or before decision cutoff, PIT market cap is None (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PitSharesFact:
    """Auditable point-in-time shares outstanding fact."""

    shares_outstanding: float
    filing_date: str
    report_period_end: str
    form: str
    accn: str
    concept: str
    acceptance_timestamp_utc: str | None = None
    derived_availability_utc: str | None = None
    availability_source: str = "date_only_next_session_conservative"
    availability_confidence: str = "conservative"

    def to_dict(self) -> dict[str, Any]:
        return {
            "shares_outstanding": self.shares_outstanding,
            "filing_date": self.filing_date,
            "report_period_end": self.report_period_end,
            "form": self.form,
            "accn": self.accn,
            "concept": self.concept,
            "acceptance_timestamp_utc": self.acceptance_timestamp_utc,
            "derived_availability_utc": self.derived_availability_utc,
            "availability_source": self.availability_source,
            "availability_confidence": self.availability_confidence,
        }


def is_sec_fact_available(
    filing_date: str,
    acceptance_timestamp_utc: str | None,
    decision_timestamp_utc: str,
    session_date: str,
) -> tuple[bool, str, str, str]:
    """Determine whether an SEC filing fact is knowable at decision_timestamp_utc.

    Hierarchy:
    A. Where an SEC acceptance timestamp can be resolved:
       acceptance_timestamp_utc <= decision_timestamp_utc.
    B. Where only filing DATE is available:
       the fact becomes usable beginning at the NEXT trading session's 09:00 snapshot,
       NOT during the filing date itself (session_date > filing_date).

    Returns (is_available, derived_availability_timestamp, availability_source, availability_confidence).
    """
    if acceptance_timestamp_utc and acceptance_timestamp_utc.strip():
        clean_acc = acceptance_timestamp_utc.strip()
        is_avail = clean_acc <= decision_timestamp_utc
        return is_avail, clean_acc, "exact_acceptance_timestamp", "high"

    # Rule B: Date-only filing is unavailable all filing day; available beginning next session
    is_avail = session_date > filing_date
    derived_avail = f"{filing_date}T23:59:59Z_next_session"
    return is_avail, derived_avail, "date_only_next_session_conservative", "conservative"


def extract_pit_shares_fact(
    company_facts: dict[str, Any],
    decision_timestamp_utc: str | None = None,
    session_date: str | None = None,
    accession_acceptance_map: dict[str, str] | None = None,
) -> PitSharesFact | None:
    """Extract latest defensible shares outstanding fact filed on or before cutoff time.

    Strictly accepts only:
    - dei/EntityCommonStockSharesOutstanding
    - us-gaap/CommonStockSharesOutstanding

    Rejects weighted-average shares and fails closed when shares are ambiguous or unverified.
    """
    if not company_facts or not isinstance(company_facts, dict):
        return None

    facts_root = company_facts.get("facts", {})
    if not isinstance(facts_root, dict):
        return None

    candidates: list[PitSharesFact] = []

    # 1. Inspect dei/EntityCommonStockSharesOutstanding
    dei_facts = facts_root.get("dei", {})
    if isinstance(dei_facts, dict):
        entity_shares = dei_facts.get("EntityCommonStockSharesOutstanding", {})
        if isinstance(entity_shares, dict):
            units = entity_shares.get("units", {}).get("shares", [])
            if isinstance(units, list):
                for entry in units:
                    if not isinstance(entry, dict):
                        continue
                    filed = str(entry.get("filed") or "")
                    val = entry.get("val")
                    accn = str(entry.get("accn") or "")
                    if not filed or val is None or not isinstance(val, (int, float)) or val <= 0:
                        continue

                    acc_ts = accession_acceptance_map.get(accn) if accession_acceptance_map else None

                    if decision_timestamp_utc and session_date:
                        avail, derived_avail, src, conf = is_sec_fact_available(
                            filed, acc_ts, decision_timestamp_utc, session_date
                        )
                        if not avail:
                            continue
                    elif session_date:
                        if filed > session_date:
                            continue
                        derived_avail = filed
                        src = "date_only_legacy"
                        conf = "legacy"
                    else:
                        continue

                    candidates.append(
                        PitSharesFact(
                            shares_outstanding=float(val),
                            filing_date=filed,
                            report_period_end=str(entry.get("end") or filed),
                            form=str(entry.get("form") or "UNKNOWN"),
                            accn=accn,
                            concept="dei/EntityCommonStockSharesOutstanding",
                            acceptance_timestamp_utc=acc_ts,
                            derived_availability_utc=derived_avail,
                            availability_source=src,
                            availability_confidence=conf,
                        )
                    )

    # 2. Inspect us-gaap/CommonStockSharesOutstanding
    gaap_facts = facts_root.get("us-gaap", {})
    if isinstance(gaap_facts, dict):
        gaap_shares = gaap_facts.get("CommonStockSharesOutstanding", {})
        if isinstance(gaap_shares, dict):
            units = gaap_shares.get("units", {}).get("shares", [])
            if isinstance(units, list):
                for entry in units:
                    if not isinstance(entry, dict):
                        continue
                    filed = str(entry.get("filed") or "")
                    val = entry.get("val")
                    accn = str(entry.get("accn") or "")
                    if not filed or val is None or not isinstance(val, (int, float)) or val <= 0:
                        continue

                    acc_ts = accession_acceptance_map.get(accn) if accession_acceptance_map else None

                    if decision_timestamp_utc and session_date:
                        avail, derived_avail, src, conf = is_sec_fact_available(
                            filed, acc_ts, decision_timestamp_utc, session_date
                        )
                        if not avail:
                            continue
                    elif session_date:
                        if filed > session_date:
                            continue
                        derived_avail = filed
                        src = "date_only_legacy"
                        conf = "legacy"
                    else:
                        continue

                    candidates.append(
                        PitSharesFact(
                            shares_outstanding=float(val),
                            filing_date=filed,
                            report_period_end=str(entry.get("end") or filed),
                            form=str(entry.get("form") or "UNKNOWN"),
                            accn=accn,
                            concept="us-gaap/CommonStockSharesOutstanding",
                            acceptance_timestamp_utc=acc_ts,
                            derived_availability_utc=derived_avail,
                            availability_source=src,
                            availability_confidence=conf,
                        )
                    )

    if not candidates:
        return None

    # Sort candidates by latest filing date (or acceptance timestamp), breaking ties by latest report period end date
    candidates.sort(
        key=lambda f: (f.acceptance_timestamp_utc or f.filing_date, f.filing_date, f.report_period_end),
        reverse=True,
    )
    return candidates[0]


def calculate_pit_market_cap(
    shares_fact: PitSharesFact | None,
    as_traded_close: float,
) -> tuple[float | None, str | None]:
    """Calculate PIT market cap = shares_outstanding * as_traded_close.

    Returns (market_cap, rejection_reason).
    """
    if shares_fact is None:
        return None, "missing_pit_shares_fact"
    if shares_fact.shares_outstanding <= 0:
        return None, "non_positive_shares_outstanding"
    if as_traded_close <= 0:
        return None, "non_positive_as_traded_close"

    market_cap = shares_fact.shares_outstanding * as_traded_close
    return market_cap, None


def compute_security_pit_market_caps(
    company_facts: dict[str, Any] | None,
    session_dates: list[str],
    as_traded_closes: dict[str, float],
    cutoff_time: str = "20:30",
    accession_acceptance_map: dict[str, str] | None = None,
) -> tuple[dict[str, float], dict[str, str], dict[str, PitSharesFact]]:
    """Compute point-in-time market caps and audit reason codes for each session date.

    Returns:
        (market_caps, market_cap_reasons, pit_shares_facts)
        Where reason codes include:
        - valid_ge_3b
        - valid_below_3b
        - missing_shares
        - ambiguous_shares
        - unavailable_at_cutoff
    """
    from tradex.research.long_002c.calendar import get_decision_timestamp_utc

    market_caps: dict[str, float] = {}
    market_cap_reasons: dict[str, str] = {}
    pit_shares_facts: dict[str, PitSharesFact] = {}

    has_any_shares = False
    if company_facts and isinstance(company_facts, dict):
        facts_root = company_facts.get("facts", {})
        if isinstance(facts_root, dict):
            dei = facts_root.get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
            gaap = facts_root.get("us-gaap", {}).get("CommonStockSharesOutstanding", {})
            if dei or gaap:
                has_any_shares = True

    for session_date in session_dates:
        dec_ts_utc = get_decision_timestamp_utc(session_date, cutoff_time)
        shares_fact = (
            extract_pit_shares_fact(
                company_facts=company_facts,
                decision_timestamp_utc=dec_ts_utc,
                session_date=session_date,
                accession_acceptance_map=accession_acceptance_map,
            )
            if company_facts
            else None
        )

        if shares_fact is None:
            reason = "unavailable_at_cutoff" if has_any_shares else "missing_shares"
            market_cap_reasons[session_date] = reason
            continue

        close_price = as_traded_closes.get(session_date)
        if close_price is None or close_price <= 0:
            market_cap_reasons[session_date] = "non_positive_as_traded_close"
            continue

        mcap, err = calculate_pit_market_cap(shares_fact, close_price)
        if mcap is not None:
            market_caps[session_date] = mcap
            market_cap_reasons[session_date] = (
                "valid_ge_3b" if mcap >= 3_000_000_000.0 else "valid_below_3b"
            )
            pit_shares_facts[session_date] = shares_fact
        else:
            market_cap_reasons[session_date] = err or "missing_shares"

    return market_caps, market_cap_reasons, pit_shares_facts
