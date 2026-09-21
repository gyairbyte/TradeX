"""Candidate manifest builder and multi-ticker interval management for LONG-002C.

Builds an auditable historical candidate manifest from point-in-time reference snapshots,
classifies securities into supported common stock, excluded types, and fail-closed unknowns,
groups multi-interval tickers under a single immutable_security_id, and records comprehensive
audit provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from tradex.research.long_002c.identity import (
    CLASSIFICATION_EXCLUDED_SECURITY_TYPE,
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    CLASSIFICATION_UNKNOWN_FAIL_CLOSED,
    SecurityIdentity,
    SecurityMaster,
    classify_security,
    extract_share_class_discriminator,
    make_immutable_id,
)
from tradex.research.long_002c.spec import WARMUP_START


@dataclass
class TickerInterval:
    """Effective-dated ticker interval for an immutable security."""

    symbol: str
    start_date: str | None
    end_date: str | None
    source: str = "snapshot_observation"  # "authoritative_lifecycle" | "snapshot_observation"
    confidence: str = "discrete_observation"  # "authoritative" | "discrete_observation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TickerInterval:
        return cls(
            symbol=str(data["symbol"]),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            source=data.get("source", "snapshot_observation"),
            confidence=data.get("confidence", "discrete_observation"),
        )


@dataclass
class CandidateSecurity:
    """Auditable candidate security in the development manifest."""

    immutable_security_id: str
    primary_symbol: str
    cik: str | None = None
    composite_figi: str | None = None
    share_class_figi: str | None = None
    company_name: str = ""
    primary_exchange: str = "XNAS"
    security_type: str = CLASSIFICATION_SUPPORTED_COMMON_STOCK
    first_seen_date: str = ""
    last_seen_date: str = ""
    discovery_sources: list[str] = field(default_factory=list)
    ticker_intervals: list[TickerInterval] = field(default_factory=list)
    ticker_observations: list[tuple[str, str]] = field(default_factory=list)
    classification_provenance: dict[str, Any] = field(default_factory=dict)
    listing_lifecycle_provenance: dict[str, Any] = field(default_factory=dict)
    reference_source_provenance: dict[str, Any] = field(default_factory=dict)

    def resolve_interval(self, session_date: str) -> TickerInterval | None:
        """Resolve the active verified ticker interval covering session_date.

        Returns None if date is not covered by any verified interval (fails closed).
        """
        for interval in self.ticker_intervals:
            if interval.start_date and interval.end_date and interval.start_date <= session_date <= interval.end_date:
                return interval
            if interval.start_date and not interval.end_date and interval.start_date <= session_date:
                return interval
            if interval.end_date and not interval.start_date and session_date <= interval.end_date:
                return interval
        return None

    def attach_authoritative_lifecycle(
        self,
        intervals: list[TickerInterval],
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Attach authoritative lifecycle intervals (e.g. from EDGAR formerNames or corporate actions)."""
        self.ticker_intervals = intervals
        if provenance:
            self.listing_lifecycle_provenance.update(provenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "immutable_security_id": self.immutable_security_id,
            "primary_symbol": self.primary_symbol,
            "cik": self.cik,
            "composite_figi": self.composite_figi,
            "share_class_figi": self.share_class_figi,
            "company_name": self.company_name,
            "primary_exchange": self.primary_exchange,
            "security_type": self.security_type,
            "first_seen_date": self.first_seen_date,
            "last_seen_date": self.last_seen_date,
            "discovery_sources": self.discovery_sources,
            "ticker_intervals": [ti.to_dict() for ti in self.ticker_intervals],
            "ticker_observations": self.ticker_observations,
            "classification_provenance": self.classification_provenance,
            "listing_lifecycle_provenance": self.listing_lifecycle_provenance,
            "reference_source_provenance": self.reference_source_provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateSecurity:
        intervals = [
            TickerInterval.from_dict(ti) if isinstance(ti, dict) else ti
            for ti in data.get("ticker_intervals", [])
        ]
        raw_obs = data.get("ticker_observations", [])
        obs = [tuple(o) for o in raw_obs] if raw_obs else []
        return cls(
            immutable_security_id=data["immutable_security_id"],
            primary_symbol=data["primary_symbol"],
            cik=data.get("cik"),
            composite_figi=data.get("composite_figi"),
            share_class_figi=data.get("share_class_figi"),
            company_name=data.get("company_name", ""),
            primary_exchange=data.get("primary_exchange", ""),
            security_type=data.get("security_type", CLASSIFICATION_SUPPORTED_COMMON_STOCK),
            first_seen_date=data.get("first_seen_date", ""),
            last_seen_date=data.get("last_seen_date", ""),
            discovery_sources=data.get("discovery_sources", []),
            ticker_intervals=intervals,
            ticker_observations=obs,
            classification_provenance=data.get("classification_provenance", {}),
            listing_lifecycle_provenance=data.get("listing_lifecycle_provenance", {}),
            reference_source_provenance=data.get("reference_source_provenance", {}),
        )


@dataclass
class ManifestAuditMetrics:
    """Observed provenance and classification metrics from universe enumeration."""

    snapshot_dates_evaluated: list[str]
    total_raw_records_evaluated: int
    unique_symbols_seen: int
    unique_securities_discovered: int
    supported_common_stock_count: int
    excluded_security_type_count: int
    unknown_fail_closed_count: int
    with_cik_count: int
    with_figi_count: int
    cik_coverage_pct: float
    figi_coverage_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_candidate_manifest_from_snapshots(
    snapshot_data_by_date: dict[str, list[dict[str, Any]]],
) -> tuple[list[CandidateSecurity], ManifestAuditMetrics]:
    """Build candidate manifest from dated reference snapshots.

    Discovers all unique securities active across any of the snapshot dates,
    classifies securities strictly according to Item 5, and links historical
    ticker intervals to a single immutable_security_id.
    """
    sorted_dates = sorted(snapshot_data_by_date.keys())
    total_raw_records = 0
    unique_symbols: set[str] = set()
    supported_count = 0
    excluded_count = 0
    unknown_count = 0

    # Intermediate storage by immutable_security_id
    securities_by_id: dict[str, dict[str, Any]] = {}

    for pit_date in sorted_dates:
        records = snapshot_data_by_date[pit_date]
        total_raw_records += len(records)

        for rec in records:
            # Exclude securities delisted before WARMUP_START (2015-01-01)
            delisted_utc = str(rec.get("delisted_utc") or "").strip()
            if delisted_utc and delisted_utc[:10] < WARMUP_START:
                continue

            raw_sym = str(rec.get("ticker") or "").strip().upper()
            if raw_sym:
                unique_symbols.add(raw_sym)

            classification = classify_security(rec)
            if classification == CLASSIFICATION_EXCLUDED_SECURITY_TYPE:
                excluded_count += 1
                continue
            elif classification == CLASSIFICATION_UNKNOWN_FAIL_CLOSED:
                unknown_count += 1
                continue
            elif classification == CLASSIFICATION_SUPPORTED_COMMON_STOCK:
                supported_count += 1
            else:
                unknown_count += 1
                continue

            cik = str(rec.get("cik") or "").strip() or None
            composite_figi = str(rec.get("composite_figi") or "").strip() or None
            share_class_figi = str(rec.get("share_class_figi") or "").strip() or None
            company_name = str(rec.get("name") or "").strip()
            exchange = str(rec.get("primary_exchange") or "").strip().upper()
            discriminator = extract_share_class_discriminator(rec)

            # Strict 4-tier hierarchy:
            # 1. verified share_class_figi
            # 2. verified composite/security FIGI
            # 3. CIK + verified stable share-class discriminator
            # 4. fail closed unknown_security_identity
            try:
                sec_id = make_immutable_id(
                    symbol=raw_sym,
                    cik=cik,
                    composite_figi=composite_figi,
                    share_class_figi=share_class_figi,
                    share_class_discriminator=discriminator,
                    allow_unverified=False,
                )
            except ValueError:
                # Fails closed on generic CIK without discriminator or unverified symbol
                unknown_count += 1
                supported_count -= 1
                continue

            clean_date = pit_date[:10]
            disc_source = rec.get("discovery_source") or f"snapshot:{pit_date}"
            if sec_id not in securities_by_id:
                securities_by_id[sec_id] = {
                    "immutable_security_id": sec_id,
                    "primary_symbol": raw_sym,
                    "cik": cik,
                    "composite_figi": composite_figi,
                    "share_class_figi": share_class_figi,
                    "company_name": company_name,
                    "primary_exchange": exchange,
                    "security_type": CLASSIFICATION_SUPPORTED_COMMON_STOCK,
                    "first_seen_date": clean_date,
                    "last_seen_date": clean_date,
                    "discovery_sources": [disc_source],
                    "ticker_observations": [(raw_sym, clean_date)],
                }
            else:
                entry = securities_by_id[sec_id]
                entry["last_seen_date"] = clean_date
                if disc_source not in entry["discovery_sources"]:
                    entry["discovery_sources"].append(disc_source)
                entry["ticker_observations"].append((raw_sym, clean_date))
                # Update attributes if previously missing
                if not entry["cik"] and cik:
                    entry["cik"] = cik
                if not entry["composite_figi"] and composite_figi:
                    entry["composite_figi"] = composite_figi
                if not entry["share_class_figi"] and share_class_figi:
                    entry["share_class_figi"] = share_class_figi
                if not entry["company_name"] and company_name:
                    entry["company_name"] = company_name

    candidates: list[CandidateSecurity] = []
    with_cik = 0
    with_figi = 0

    for sec_id, data in sorted(securities_by_id.items(), key=lambda x: x[1]["primary_symbol"]):
        if data["cik"]:
            with_cik += 1
        if data["composite_figi"]:
            with_figi += 1

        # Build ticker intervals from observations
        obs = data["ticker_observations"]
        distinct_syms = {sym for sym, _ in obs}
        intervals: list[TickerInterval] = []
        if len(distinct_syms) > 1:
            # Multi-ticker security across snapshots:
            # Invariant: Sparse snapshots DO NOT prove actual ticker-change effective dates.
            # Retain known discrete observations; do NOT bridge intermediate dates without authoritative lifecycle.
            curr_sym, first_date = obs[0]
            last_date = first_date
            for sym, d in obs[1:]:
                if sym == curr_sym:
                    last_date = d
                else:
                    intervals.append(
                        TickerInterval(
                            symbol=curr_sym,
                            start_date=first_date,
                            end_date=last_date,
                            source="snapshot_observation",
                            confidence="discrete_observation",
                        )
                    )
                    curr_sym = sym
                    first_date = d
                    last_date = d
            intervals.append(
                TickerInterval(
                    symbol=curr_sym,
                    start_date=first_date,
                    end_date=last_date,
                    source="snapshot_observation",
                    confidence="discrete_observation",
                )
            )
        elif obs:
            curr_sym, first_date = obs[0]
            last_date = obs[-1][1]
            intervals.append(
                TickerInterval(
                    symbol=curr_sym,
                    start_date=first_date,
                    end_date=last_date,
                    source="snapshot_observation",
                    confidence="single_symbol_known",
                )
            )

        candidate = CandidateSecurity(
            immutable_security_id=sec_id,
            primary_symbol=data["primary_symbol"],
            cik=data["cik"],
            composite_figi=data["composite_figi"],
            share_class_figi=data["share_class_figi"],
            company_name=data["company_name"],
            primary_exchange=data["primary_exchange"],
            security_type=data["security_type"],
            first_seen_date=data["first_seen_date"],
            last_seen_date=data["last_seen_date"],
            discovery_sources=data.get("discovery_sources", []),
            ticker_intervals=intervals,
            ticker_observations=obs,
        )
        candidates.append(candidate)

    total_candidates = len(candidates)
    cik_cov = (with_cik / total_candidates * 100.0) if total_candidates > 0 else 0.0
    figi_cov = (with_figi / total_candidates * 100.0) if total_candidates > 0 else 0.0

    metrics = ManifestAuditMetrics(
        snapshot_dates_evaluated=sorted_dates,
        total_raw_records_evaluated=total_raw_records,
        unique_symbols_seen=len(unique_symbols),
        unique_securities_discovered=total_candidates,
        supported_common_stock_count=supported_count,
        excluded_security_type_count=excluded_count,
        unknown_fail_closed_count=unknown_count,
        with_cik_count=with_cik,
        with_figi_count=with_figi,
        cik_coverage_pct=round(cik_cov, 2),
        figi_coverage_pct=round(figi_cov, 2),
    )

    return candidates, metrics


def register_manifest_in_security_master(
    manifest: list[CandidateSecurity],
    master: SecurityMaster | None = None,
) -> SecurityMaster:
    """Register all candidate securities and their ticker intervals in a SecurityMaster."""
    sec_master = master or SecurityMaster()
    for cand in manifest:
        if cand.ticker_intervals:
            for ti in cand.ticker_intervals:
                if not (ti.start_date and ti.end_date):
                    continue
                identity = SecurityIdentity(
                    immutable_security_id=cand.immutable_security_id,
                    ticker_at_decision=ti.symbol,
                    effective_start=ti.start_date,
                    effective_end=ti.end_date,
                    cik=cand.cik,
                    composite_figi=cand.composite_figi,
                    share_class_figi=cand.share_class_figi,
                    company_name=cand.company_name,
                    primary_exchange=cand.primary_exchange,
                    security_type=cand.security_type,
                )
                sec_master.register_security(identity)
        else:
            identity = SecurityIdentity(
                immutable_security_id=cand.immutable_security_id,
                ticker_at_decision=cand.primary_symbol,
                effective_start=cand.first_seen_date,
                effective_end=cand.last_seen_date,
                cik=cand.cik,
                composite_figi=cand.composite_figi,
                share_class_figi=cand.share_class_figi,
                company_name=cand.company_name,
                primary_exchange=cand.primary_exchange,
                security_type=cand.security_type,
            )
            sec_master.register_security(identity)
    return sec_master


def get_monthly_discovery_dates(start_year: int = 2015, end_year: int = 2020) -> list[str]:
    """Return the first regular XNYS trading session date for each month from start_year through end_year inclusive.

    For 2015-01 through 2020-12, this yields exactly 72 monthly snapshots.
    """
    from tradex.research.long_002c.calendar import get_trading_sessions

    discovery_dates: list[str] = []
    for yr in range(start_year, end_year + 1):
        for mo in range(1, 13):
            # Probe first 28 days of month
            sessions = get_trading_sessions(f"{yr}-{mo:02d}-01", f"{yr}-{mo:02d}-28")
            if sessions:
                discovery_dates.append(sessions[0])
            else:
                sessions_ext = get_trading_sessions(f"{yr}-{mo:02d}-01", f"{yr}-{mo:02d}-31")
                if sessions_ext:
                    discovery_dates.append(sessions_ext[0])
    return sorted(discovery_dates)


def build_full_development_discovery_manifest(
    massive: Any,
    custom_dates: list[str] | None = None,
    include_inactive: bool = True,
    on_progress: Any | None = None,
) -> tuple[list[CandidateSecurity], ManifestAuditMetrics, dict[str, Any]]:
    """Build complete candidate discovery manifest across 72 monthly snapshots + inactive snapshot.

    Guarantees:
    - 72 monthly active snapshots (2015-01 through 2020-12) by default
    - 1 inactive snapshot at DEV_END (date=2020-12-31, active=False)
    - Detailed 2016 vs 2020 classification coverage comparison
    """
    monthly_dates = custom_dates or get_monthly_discovery_dates(2015, 2020)
    snapshot_records_by_date: dict[str, list[dict[str, Any]]] = {}

    # 1. Fetch monthly active snapshots
    for idx, d in enumerate(monthly_dates, 1):
        if on_progress:
            on_progress("active_snapshot", idx, len(monthly_dates), d)
        recs, _, _ = massive.fetch_reference_snapshot(d, active=True, safety_max_pages=50)
        snapshot_records_by_date[d] = recs

    # 2. Fetch DEV_END inactive reference snapshot if requested
    if include_inactive:
        if on_progress:
            on_progress("inactive_snapshot", 1, 1, "2020-12-31")
        inactive_recs, _, _ = massive.fetch_reference_snapshot("2020-12-31", active=False, safety_max_pages=50)
        for r in inactive_recs:
            r["discovery_source"] = "inactive_delisted_20201231"
        snapshot_records_by_date["2020-12-31-inactive"] = inactive_recs

    # 3. Assemble candidate manifest
    candidates, metrics = build_candidate_manifest_from_snapshots(snapshot_records_by_date)

    # 4. Compute 2016 vs 2020 classification coverage comparison
    def _metrics_for_year(year: int) -> dict[str, Any]:
        yr_dates = [d for d in monthly_dates if d.startswith(str(year))]
        total_raw = sum(len(snapshot_records_by_date.get(d, [])) for d in yr_dates)
        common_count = 0
        with_cik = 0
        with_figi = 0
        for d in yr_dates:
            for r in snapshot_records_by_date.get(d, []):
                if classify_security(r) == CLASSIFICATION_SUPPORTED_COMMON_STOCK:
                    common_count += 1
                if r.get("cik"):
                    with_cik += 1
                if r.get("composite_figi") or r.get("share_class_figi"):
                    with_figi += 1
        return {
            "year": year,
            "monthly_snapshots": len(yr_dates),
            "total_raw_records": total_raw,
            "supported_common_stock_records": common_count,
            "common_stock_pct": round(common_count / total_raw * 100.0, 1) if total_raw > 0 else 0.0,
            "cik_coverage_pct": round(with_cik / total_raw * 100.0, 1) if total_raw > 0 else 0.0,
            "figi_coverage_pct": round(with_figi / total_raw * 100.0, 1) if total_raw > 0 else 0.0,
        }

    cov_2016 = _metrics_for_year(2016)
    cov_2020 = _metrics_for_year(2020)

    comparison_summary = {
        "coverage_2016": cov_2016,
        "coverage_2020": cov_2020,
        "classification_limitation_statement": (
            "2016 reference snapshots reflect lower CIK and explicit security-type coverage compared to 2020. "
            "Under locked LONG-002 research rules, any security lacking verified common stock classification or "
            "lacking verified share-class identity strictly fails closed into unknown_fail_closed / "
            "unknown_security_identity, preventing survivor and lookahead bias."
        ),
    }

    return candidates, metrics, comparison_summary
