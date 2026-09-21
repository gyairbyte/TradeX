"""Security identity resolution, immutable IDs, and ticker rename/reuse handling.

Enforces canonical joins on immutable_security_id, prevents ticker-only joins,
preserves ticker rename continuity, and isolates ticker reuse across distinct entities.
Disallows symbol-only fallback for official canonical research identity.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityIdentity:
    """Canonical security identity representation."""

    immutable_security_id: str
    ticker_at_decision: str
    effective_start: str
    effective_end: str
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
        return self.security_type == "common_stock"


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


def make_immutable_id(
    symbol: str,
    cik: str | None = None,
    composite_figi: str | None = None,
    share_class: str = "CS",
    allow_unverified: bool = False,
) -> str:
    """Generate a stable, reproducible immutable security ID.

    Requires CIK + share class or composite FIGI for official canonical identity.
    Disallows symbol-only fallback unless explicitly flagged for unverified debugging (allow_unverified=True).
    """
    if composite_figi and composite_figi.strip():
        return f"FIGI_{composite_figi.strip().upper()}"
    if cik and str(cik).strip():
        padded_cik = str(cik).strip().zfill(10)
        return f"CIK_{padded_cik}_{share_class.strip().upper()}"
    if allow_unverified:
        return f"US_EQ_{symbol.strip().upper()}_{share_class.strip().upper()}"
    raise ValueError(
        f"Symbol-only identity '{symbol}' cannot qualify for official-run canonical identity. "
        f"Verified CIK + share class or composite FIGI is required to prevent lookahead and survivor bias."
    )
