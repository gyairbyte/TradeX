"""Security identity resolution, immutable IDs, and ticker rename/reuse handling.

Enforces canonical joins on immutable_security_id, prevents ticker-only joins,
preserves ticker rename continuity, and isolates ticker reuse across distinct entities.
Disallows symbol-only fallback for official canonical research identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecurityIdentity:
    """Canonical security identity representation."""

    immutable_security_id: str
    ticker_at_decision: str
    effective_start: str = "2010-01-01"
    effective_end: str = "2030-12-31"
    cik: str | None = None
    composite_figi: str | None = None
    share_class_figi: str | None = None
    company_name: str | None = None
    primary_exchange: str | None = None
    security_type: str = "unknown"  # "common_stock" | "unknown" | other exclusions; default unknown (fail closed)
    listing_date: str | None = None
    delisting_date: str | None = None

    @property
    def is_common_stock(self) -> bool:
        return self.security_type in (CLASSIFICATION_SUPPORTED_COMMON_STOCK, "common_stock")


CLASSIFICATION_SUPPORTED_COMMON_STOCK = "supported_common_stock"
CLASSIFICATION_EXCLUDED_SECURITY_TYPE = "excluded_security_type"
CLASSIFICATION_UNKNOWN_FAIL_CLOSED = "unknown_fail_closed"

_EXCLUDED_KEYWORDS = (
    "ADR", "ADS", "DEPOSITARY", "DEPOSITORY", "PREFERRED", "PFD",
    "WARRANT", "WT", "RIGHT", "UNIT", "ETF", "ETN", "INDEX", "TRUST", "FUND",
)

_MAJOR_US_EXCHANGES = {"XNYS", "XNAS", "XASE", "NYSE", "NASDAQ", "AMEX", "BATS", "ARCA"}


def classify_security(record: dict[str, Any]) -> str:
    """Classify security into supported_common_stock, excluded_security_type, or unknown_fail_closed.

    Strictly satisfies Item 5:
    - Never claim SIC code proves common stock.
    - Massive type must equal 'CS'.
    - Exclude ADRs, ETFs, warrants, preferreds, units, funds by type and name inspection.
    - Fail closed on ambiguous or missing classifications.
    """
    sec_type = str(record.get("type") or "").strip().upper()
    market = str(record.get("market") or "").strip().lower()
    locale = str(record.get("locale") or "").strip().lower()
    exchange = str(record.get("primary_exchange") or "").strip().upper()
    name = str(record.get("name") or "").strip().upper()

    # If security type indicates non-common stock, explicitly exclude
    if sec_type in {"ADRC", "ETF", "WAR", "PFD", "UNIT", "RIGHT", "FUND"}:
        return CLASSIFICATION_EXCLUDED_SECURITY_TYPE

    # Check name against exclusion keywords
    for kw in _EXCLUDED_KEYWORDS:
        if kw in name.split() or f" {kw}" in name or f"({kw})" in name or f"-{kw}" in name or f"/{kw}" in name:
            return CLASSIFICATION_EXCLUDED_SECURITY_TYPE

    if market and market != "stocks":
        return CLASSIFICATION_EXCLUDED_SECURITY_TYPE
    if locale and locale != "us":
        return CLASSIFICATION_EXCLUDED_SECURITY_TYPE

    # Common stock must have type 'CS'
    if sec_type == "CS":
        if exchange and exchange not in _MAJOR_US_EXCHANGES:
            return CLASSIFICATION_EXCLUDED_SECURITY_TYPE
        return CLASSIFICATION_SUPPORTED_COMMON_STOCK

    return CLASSIFICATION_UNKNOWN_FAIL_CLOSED


class SecurityMaster:
    """Effective-dated security master managing immutable IDs across ticker lifecycles."""

    def __init__(self) -> None:
        # List of known SecurityIdentity records
        self._records: list[SecurityIdentity] = []
        # Mapping by immutable_security_id
        self._by_id: dict[str, list[SecurityIdentity]] = {}

    def register_security(self, identity: SecurityIdentity) -> None:
        """Register a security identity interval."""
        self._records.append(identity)
        self._by_id.setdefault(identity.immutable_security_id, []).append(identity)

    def resolve(self, ticker: str, as_of_date: str) -> SecurityIdentity | None:
        """Resolve a (ticker, as_of_date) to an immutable SecurityIdentity.

        Returns None if identity cannot be defensibly resolved (fail closed).
        """
        norm_ticker = ticker.upper().strip()
        matches = [
            rec
            for rec in self._records
            if rec.ticker_at_decision.upper() == norm_ticker
            and rec.effective_start <= as_of_date <= rec.effective_end
        ]
        if not matches:
            return None
        # If multiple records match (which would indicate an unresolved collision), fail closed
        if len(matches) > 1:
            return None
        return matches[0]

    def resolve_historical_ticker(self, immutable_security_id: str, as_of_date: str) -> str | None:
        """Resolve the effective historical ticker for an immutable security ID on a given date."""
        records = self._by_id.get(immutable_security_id, [])
        for rec in records:
            if rec.effective_start <= as_of_date <= rec.effective_end:
                return rec.ticker_at_decision
        return None

    def get_security_by_id(self, immutable_security_id: str, as_of_date: str | None = None) -> SecurityIdentity | None:
        """Retrieve security identity by immutable ID."""
        records = self._by_id.get(immutable_security_id, [])
        if not records:
            return None
        if as_of_date is None:
            return records[-1]
        for rec in records:
            if rec.effective_start <= as_of_date <= rec.effective_end:
                return rec
        return None

    def all_identities(self) -> list[SecurityIdentity]:
        return list(self._records)


def extract_share_class_discriminator(record: dict[str, Any]) -> str | None:
    """Extract verified stable share-class discriminator from security reference record."""
    name = str(record.get("name") or "").upper()
    ticker = str(record.get("ticker") or "").upper()

    for cl in ["CLASS A", "CL A", "COM CL A", "CL. A", "CLASS. A"]:
        if cl in name:
            return "CLASS_A"
    for cl in ["CLASS B", "CL B", "COM CL B", "CL. B", "CLASS. B"]:
        if cl in name:
            return "CLASS_B"
    for cl in ["CLASS C", "CL C", "COM CL C", "CL. C", "CLASS. C"]:
        if cl in name:
            return "CLASS_C"

    if ticker.endswith((".A", "/A")):
        return "CLASS_A"
    if ticker.endswith((".B", "/B")):
        return "CLASS_B"
    if ticker.endswith((".C", "/C")):
        return "CLASS_C"

    return None


def make_immutable_id(
    symbol: str,
    cik: str | None = None,
    composite_figi: str | None = None,
    share_class_figi: str | None = None,
    share_class_discriminator: str | None = None,
    allow_unverified: bool = False,
) -> str:
    """Generate a stable, reproducible immutable security ID following the locked research hierarchy.

    Hierarchy:
    1. verified share_class_figi when available -> FIGI_{share_class_figi}
    2. verified composite/security FIGI where it uniquely represents the historical share class -> FIGI_{composite_figi}
    3. CIK + another verified stable share-class discriminator only when the discriminator
       proves one unique security -> CIK_{padded_cik}_{discriminator}
    4. otherwise fail closed with unknown_security_identity.
    Generic CIK_<cik>_CS is strictly rejected when share-class discriminator is missing.
    """
    sc_figi = str(share_class_figi or "").strip().upper()
    if sc_figi:
        return f"FIGI_{sc_figi}"

    comp_figi = str(composite_figi or "").strip().upper()
    if comp_figi:
        return f"FIGI_{comp_figi}"

    clean_cik = str(cik or "").strip()
    discrim = str(share_class_discriminator or "").strip().upper()
    # Reject generic CIK fallback without specific share-class discriminator
    if clean_cik and discrim and discrim not in {"CS", "COMMON", "UNKNOWN", "NONE", ""}:
        padded_cik = clean_cik.zfill(10)
        return f"CIK_{padded_cik}_{discrim}"

    if allow_unverified and symbol and symbol.strip():
        return f"US_EQ_{symbol.strip().upper()}_CS"

    raise ValueError(
        f"unknown_security_identity: Symbol-only identity '{symbol}' cannot qualify for official canonical identity without "
        f"verified share_class_figi, composite_figi, or (CIK + verified stable share-class discriminator). "
        f"Generic CIK without share-class discriminator is rejected to prevent dual-class collision."
    )
