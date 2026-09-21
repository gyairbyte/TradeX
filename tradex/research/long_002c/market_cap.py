"""Point-in-time (PIT) market capitalization calculation using SEC EDGAR company facts.

Implements strict point-in-time shares outstanding resolution:
pit_market_cap = latest defensible shares outstanding known at decision time * as_traded_close
via SEC EDGAR facts:
- us-gaap/CommonStockSharesOutstanding
- dei/EntityCommonStockSharesOutstanding

Rules:
1. Strict `filed <= session_date` filter. Future filings, restatements, or backfilled facts
   are strictly excluded to prevent lookahead and survivor bias.
2. Latest defensible fact is chosen by latest filing date (`filed`), breaking ties by latest
   report period end date (`end`).
3. If no filed shares fact exists on or before session_date, PIT market cap is None (fail closed).
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "shares_outstanding": self.shares_outstanding,
            "filing_date": self.filing_date,
            "report_period_end": self.report_period_end,
            "form": self.form,
            "accn": self.accn,
            "concept": self.concept,
        }


def extract_pit_shares_fact(company_facts: dict[str, Any], session_date: str) -> PitSharesFact | None:
    """Extract latest defensible shares outstanding fact filed on or before session_date."""
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
                    filed = entry.get("filed")
                    val = entry.get("val")
                    if not filed or val is None or not isinstance(val, (int, float)) or val <= 0:
                        continue
                    if filed <= session_date:
                        candidates.append(
                            PitSharesFact(
                                shares_outstanding=float(val),
                                filing_date=str(filed),
                                report_period_end=str(entry.get("end") or filed),
                                form=str(entry.get("form") or "UNKNOWN"),
                                accn=str(entry.get("accn") or ""),
                                concept="dei/EntityCommonStockSharesOutstanding",
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
                    filed = entry.get("filed")
                    val = entry.get("val")
                    if not filed or val is None or not isinstance(val, (int, float)) or val <= 0:
                        continue
                    if filed <= session_date:
                        candidates.append(
                            PitSharesFact(
                                shares_outstanding=float(val),
                                filing_date=str(filed),
                                report_period_end=str(entry.get("end") or filed),
                                form=str(entry.get("form") or "UNKNOWN"),
                                accn=str(entry.get("accn") or ""),
                                concept="us-gaap/CommonStockSharesOutstanding",
                            )
                        )

    # 3. Fallback for dual-class common stock issuers: us-gaap/WeightedAverageNumberOfSharesOutstandingBasic
    if not candidates and isinstance(gaap_facts, dict):
        weighted_shares = gaap_facts.get("WeightedAverageNumberOfSharesOutstandingBasic", {})
        if isinstance(weighted_shares, dict):
            units = weighted_shares.get("units", {}).get("shares", [])
            if isinstance(units, list):
                for entry in units:
                    if not isinstance(entry, dict):
                        continue
                    filed = entry.get("filed")
                    val = entry.get("val")
                    if not filed or val is None or not isinstance(val, (int, float)) or val <= 0:
                        continue
                    if filed <= session_date:
                        candidates.append(
                            PitSharesFact(
                                shares_outstanding=float(val),
                                filing_date=str(filed),
                                report_period_end=str(entry.get("end") or filed),
                                form=str(entry.get("form") or "UNKNOWN"),
                                accn=str(entry.get("accn") or ""),
                                concept="us-gaap/WeightedAverageNumberOfSharesOutstandingBasic",
                            )
                        )

    if not candidates:
        return None

    # Sort candidates by latest filing date, breaking ties by latest report period end date
    candidates.sort(key=lambda f: (f.filing_date, f.report_period_end), reverse=True)
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
