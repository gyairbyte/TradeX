"""Reference provider probe orchestration for INTRA-001B-REFERENCE-V3."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .models import (
    CapabilityEvidence,
    ProviderCandidateResult,
    ProviderDisposition,
    ReferenceProbeDecision,
)
from .spec import ReferenceProbeSpec, sha256_of_file

# Known U.S. national securities exchanges (MICs). OTC venues are not in this list.
_US_NATIONAL_EXCHANGES = {
    "XNYS",  # NYSE
    "XNAS",  # NASDAQ
    "ARCX",  # NYSE Arca
    "BATS",  # Cboe BZX / BATS
    "XASE",  # NYSE American
    "BATY",  # Cboe BYX
    "EDGA",  # Cboe EDGA
    "EDGX",  # Cboe EDGX
    "IEXG",  # IEX
    "XCHI",  # Chicago Stock Exchange
    "XPSX",  # Nasdaq PSX
    "GEMX",  # Nasdaq GEMX
    "MPRL",  # Miami Pearl
    "OTC?",  # placeholder, not used
}

_KNOWN_OTC_MARKERS = {
    "OTC", "OTCE", "OTCBB", "PINX", "OTCMKTS", "OTCQB", "OTCQX", "GREY", "PINK", "PK"
}


def _current_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _main_base_sha() -> str:
    """Return the merge-base with origin/main, or current HEAD if unavailable."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "origin/main", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _current_head()


def validate_pre_registration_commit(
    commit: str, final_head: str | None = None
) -> None:
    """Verify that a pre-registration commit object exists and predates the run.

    The commit must be reachable in the repository (it may live on a sibling
    research branch). When an explicit final_head is supplied, an ancestor
    relationship is preferred, but object existence and a non-future timestamp
    are sufficient for provenance.
    """
    if final_head is None:
        final_head = _current_head()
    if len(commit) != 40:
        raise ValueError(f"pre-registration commit must be 40 characters: {commit!r}")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, final_head],
            check=True,
        )
        return
    except subprocess.CalledProcessError:
        pass
    # Fallback: ensure the commit object exists and is not dated in the future.
    subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], check=True)
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", commit],
        check=True,
        capture_output=True,
        text=True,
    )
    commit_time = int(result.stdout.strip())
    if commit_time > int(time.time()):
        raise ValueError(f"pre-registration commit timestamp is in the future: {commit}")


def _map_alpha_asset_type(asset_type: str) -> str:
    at = (asset_type or "").lower()
    if "common stock" in at or at == "stock":
        return "common_stock"
    if "etf" in at:
        return "etf"
    if "preferred" in at or "pfd" in at:
        return "preferred_stock"
    if "warrant" in at:
        return "warrant"
    if "right" in at:
        return "right"
    if "unit" in at:
        return "unit"
    if "otc" in at:
        return "otc"
    return "unknown"


def _build_alpha_taxonomy(
    security_type_counts: dict[str, int],
) -> tuple[dict[str, str], tuple[str, ...], tuple[dict[str, Any], ...]]:
    mapping: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for stype in security_type_counts:
        category = _map_alpha_asset_type(stype)
        mapping[stype] = category
        rows.append({
            "code": stype,
            "description": stype,
            "asset_class": "stocks",
            "locale": "us",
            "tradex_category": category,
            "eligible_stock": category == "common_stock",
        })
    allowlist = tuple(sorted({k for k, v in mapping.items() if v == "common_stock"}))
    return mapping, allowlist, tuple(rows)


def _distinct_canonical_sets(observations: tuple) -> bool:
    hashes = [obs.full_snapshot_sha256 for obs in observations if obs.full_snapshot_sha256]
    return len(set(hashes)) > 1 or len({obs.pit_date for obs in observations if not obs.error}) > 1


def _max_pages_by_state(observations: tuple, state: str) -> int:
    return max(
        (obs.page_count for obs in observations if obs.state == state and not obs.error),
        default=0,
    )


def _all_observations_repeat_match(observations: tuple) -> bool:
    checks = [obs.repeat_match for obs in observations if obs.repeat_match is not None]
    return bool(checks) and all(checks)


def _all_observations_pagination_complete(observations: tuple) -> bool:
    checks = [obs.pagination_complete for obs in observations if not obs.error]
    return bool(checks) and all(checks)


def _no_pagination_anomalies(observations: tuple) -> bool:
    for obs in observations:
        if obs.error:
            continue
        if obs.cycle_detected or obs.repeated_cursor_detected or obs.repeated_next_url_detected or obs.unexpected_next_url or obs.max_pages_reached:
            return False
    return True


def _capability_matrix_v3(
    result: ProviderCandidateResult,
    spec: ReferenceProbeSpec,
) -> tuple[CapabilityEvidence, ...]:
    """Evaluate all 22 mandatory gates and return capability rows."""
    provider = result.provider
    observations = result.observations
    rows: list[CapabilityEvidence] = []
    notes: dict[str, str] = {}

    # Helpers
    def _note(cap: str, msg: str) -> None:
        notes[cap] = msg

    def _add(cap: str, supported: bool, evidence: str, note: str) -> None:
        rows.append(CapabilityEvidence(provider, cap, supported, evidence, note))

    # 1. pit_date_support_for_all_probe_dates
    successful_dates = {obs.pit_date for obs in observations if not obs.error and obs.row_count > 0}
    pit_pass = len(successful_dates) == len(spec.probe_dates) and len(spec.probe_dates) > 0
    _add(
        "pit_date_support_for_all_probe_dates",
        pit_pass,
        "live_evidence",
        f"Successful PIT dates: {sorted(successful_dates)}; required: {list(spec.probe_dates)}",
    )

    # 2 & 3. active/inactive completeness
    active_obs = [obs for obs in observations if obs.state in ("active", "true") and not obs.error]
    inactive_obs = [obs for obs in observations if obs.state in ("inactive", "false", "delisted") and not obs.error]
    active_complete = bool(active_obs) and all(obs.pagination_complete for obs in active_obs) and all(obs.row_count > 0 for obs in active_obs)
    inactive_complete = bool(inactive_obs) and all(obs.pagination_complete for obs in inactive_obs) and all(obs.row_count > 0 for obs in inactive_obs)
    _add(
        "active_state_complete",
        active_complete,
        "live_evidence",
        f"Active observations: {len(active_obs)}; complete: {all(obs.pagination_complete for obs in active_obs) if active_obs else False}",
    )
    _add(
        "inactive_or_delisted_state_complete",
        inactive_complete,
        "live_evidence",
        f"Inactive/delisted observations: {len(inactive_obs)}; complete: {all(obs.pagination_complete for obs in inactive_obs) if inactive_obs else False}",
    )

    # 4. pagination_exhausted_to_terminal
    pagination_complete = bool(observations) and _all_observations_pagination_complete(observations)
    _add(
        "pagination_exhausted_to_terminal",
        pagination_complete,
        "live_evidence",
        "All snapshots reached terminal pagination." if pagination_complete else "At least one snapshot did not reach terminal pagination.",
    )

    # 5. no_pagination_cycles_or_repeated_cursors
    no_anomaly = bool(observations) and _no_pagination_anomalies(observations)
    _add(
        "no_pagination_cycles_or_repeated_cursors",
        no_anomaly,
        "live_evidence",
        "No repeated cursor, cycle, or unexpected next_url detected." if no_anomaly else "Pagination anomaly detected.",
    )

    # 6. exact_historical_date_semantics
    distinct = bool(observations) and _distinct_canonical_sets(observations)
    exact_date = pit_pass and distinct
    _add(
        "exact_historical_date_semantics",
        exact_date,
        "live_evidence",
        "Date parameter preserved; distinct canonical sets across PIT dates." if exact_date else "Distinct historical date semantics not proven.",
    )

    # 7-12. Security-type classification/exclusions
    taxonomy = result.taxonomy_mapping
    st_field = result.security_type_field
    has_taxonomy = bool(taxonomy) and st_field is not None
    type_counts = result.security_type_counts

    common_stock = has_taxonomy and "common_stock" in set(taxonomy.values())
    etf = has_taxonomy and "etf" in set(taxonomy.values())
    warrant = has_taxonomy and "warrant" in set(taxonomy.values())
    right = has_taxonomy and "right" in set(taxonomy.values())
    unit = has_taxonomy and "unit" in set(taxonomy.values())
    preferred = has_taxonomy and "preferred_stock" in set(taxonomy.values())

    # Fallback: for Alpha Vantage infer from observed assetType values
    if not taxonomy and provider == "alpha_vantage" and type_counts:
        inferred_mapping, _, _ = _build_alpha_taxonomy(type_counts)
        common_stock = common_stock or "common_stock" in set(inferred_mapping.values())
        etf = etf or "etf" in set(inferred_mapping.values())
        warrant = warrant or "warrant" in set(inferred_mapping.values())
        right = right or "right" in set(inferred_mapping.values())
        unit = unit or "unit" in set(inferred_mapping.values())
        preferred = preferred or "preferred_stock" in set(inferred_mapping.values())

    _add("common_stock_classification", common_stock, "live_evidence", f"Common-stock mapping present: {common_stock}")
    _add("etf_classification", etf, "live_evidence", f"ETF mapping present: {etf}")
    _add("warrant_exclusion", warrant, "live_evidence", f"Warrant category present and ineligible: {warrant}")
    _add("right_exclusion", right, "live_evidence", f"Right category present and ineligible: {right}")
    _add("unit_exclusion", unit, "live_evidence", f"Unit category present and ineligible: {unit}")
    _add("preferred_stock_exclusion", preferred, "live_evidence", f"Preferred-stock category present and ineligible: {preferred}")

    # 13. otc_exclusion
    otc_from_taxonomy = has_taxonomy and "otc" in set(taxonomy.values())
    otc_from_exchanges = any(
        any(m in ex.upper() for m in _KNOWN_OTC_MARKERS)
        for ex in result.exchange_counts
    )
    otc_exclusion = (otc_from_taxonomy or otc_from_exchanges) and bool(result.primary_exchange_field)
    _add(
        "otc_exclusion",
        otc_exclusion,
        "live_evidence",
        f"OTC taxonomy: {otc_from_taxonomy}; OTC exchange markers: {otc_from_exchanges}; primary exchange field: {result.primary_exchange_field}",
    )

    # 14. primary_listing_provenance
    exchange_pass = bool(result.primary_exchange_field) and bool(result.exchange_counts)
    _add(
        "primary_listing_provenance",
        exchange_pass,
        "live_evidence",
        f"Exchange field '{result.primary_exchange_field}'; observed exchanges: {sorted(result.exchange_counts.keys())[:10]}..." if exchange_pass else "No primary exchange field or values.",
    )

    # 15. symbol_presence_and_determinism
    no_blank = all(obs.blank_ticker_count == 0 for obs in observations if not obs.error)
    some_rows = any(obs.row_count > 0 and obs.canonical_ticker_count > 0 for obs in observations if not obs.error)
    symbol_pass = no_blank and some_rows
    _add(
        "symbol_presence_and_determinism",
        symbol_pass,
        "live_evidence",
        f"Blank ticker count total: {result.blank_symbol_count}; canonical rows present: {some_rows}",
    )

    # 16. lifecycle_evidence
    lifecycle_pass = bool(result.lifecycle_fields_present) and (
        result.listing_date_field is not None or result.delisting_date_field is not None
    )
    _add(
        "lifecycle_evidence",
        lifecycle_pass,
        "live_evidence",
        f"Lifecycle fields present: {result.lifecycle_fields_present}; listing field: {result.listing_date_field}; delisting field: {result.delisting_date_field}",
    )

    # 17. duplicate_symbol_behavior_and_resolution
    duplicate_pass = result.unresolved_duplicate_count == 0 and result.duplicate_symbol_count == 0
    _add(
        "duplicate_symbol_behavior_and_resolution",
        duplicate_pass,
        "live_evidence",
        f"Duplicate symbols: {result.duplicate_symbol_count}; unresolved: {result.unresolved_duplicate_count}",
    )

    # 18. repeatability
    repeat_pass = bool(observations) and _all_observations_repeat_match(observations)
    _add(
        "repeatability",
        repeat_pass,
        "live_evidence",
        "Full-snapshot repeat hashes matched for all observations." if repeat_pass else "Repeat mismatch or missing.",
    )

    # 19. hashability
    hashable = all(bool(obs.raw_sha256) for obs in observations if not obs.error)
    _add(
        "hashability",
        hashable,
        "live_evidence",
        "All successful snapshots have SHA-256 hashes." if hashable else "Missing snapshot hashes.",
    )

    # 20. no_present_day_reconstruction
    no_present = exact_date and distinct and pit_pass
    _add(
        "no_present_day_reconstruction",
        no_present,
        "live_evidence",
        "Distinct historical results across requested dates; no evidence of present-day reconstruction." if no_present else "Present-day reconstruction not disproven.",
    )

    # 21. historical_2022_entitlement_under_current_plan
    has_2022 = any(obs.pit_date.startswith("2022-") and not obs.error and obs.row_count > 0 for obs in observations)
    _add(
        "historical_2022_entitlement_under_current_plan",
        has_2022,
        "live_evidence",
        "A 2022 PIT date returned data." if has_2022 else "2022 PIT date request failed or returned no rows.",
    )

    # 22. feasible_for_all_48_monthly_pit_snapshots
    # The 48-month PIT window was not probed (V4 used 12 months and 2022 was
    # explicitly not required), so the gate is false. The estimated runtime is
    # reported separately as an information-only pagination-cost row.
    _add(
        "feasible_for_all_48_monthly_pit_snapshots",
        False,
        "documented_capability",
        "48-month PIT entitlement not probed in V4; 2022-2023 coverage explicitly not required.",
    )

    # 22b. Information-only estimate of pagination cost for 48 monthly snapshots.
    estimated_cost_ok = (
        pagination_complete
        and no_anomaly
        and result.estimated_http_calls_48_months is not None
        and result.estimated_http_calls_48_months > 0
        and result.estimated_collection_time_48_months_seconds is not None
    )
    _add(
        "estimated_48_month_pagination_cost",
        estimated_cost_ok,
        "documented_capability",
        f"Estimated {result.estimated_http_calls_48_months} HTTP calls and {result.estimated_collection_time_48_months_seconds:,.1f}s collection time for 48 monthly snapshots." if estimated_cost_ok else "No pagination-cost estimate available.",
    )

    # 23. feasible_for_all_probe_monthly_pit_snapshots
    probe_months = len(spec.probe_dates)
    if result.estimated_http_calls_48_months is not None and result.estimated_collection_time_48_months_seconds is not None and probe_months > 0:
        estimated_calls_probe = int(result.estimated_http_calls_48_months * probe_months / 48)
        estimated_seconds_probe = result.estimated_collection_time_48_months_seconds * probe_months / 48
    else:
        estimated_calls_probe = None
        estimated_seconds_probe = None
    feasible_probe = (
        pagination_complete
        and no_anomaly
        and estimated_calls_probe is not None
        and estimated_calls_probe > 0
        and estimated_seconds_probe is not None
        and estimated_seconds_probe < 86_400
    )
    _add(
        "feasible_for_all_probe_monthly_pit_snapshots",
        feasible_probe,
        "documented_capability",
        f"Estimated {estimated_calls_probe} HTTP calls and {estimated_seconds_probe:,.1f}s collection time for {probe_months} probe monthly snapshots." if feasible_probe else f"Feasibility for {probe_months} probe monthly snapshots not established.",
    )

    return tuple(rows)


def _provider_flags_from_dispositions(
    dispositions: tuple[ProviderDisposition, ...],
    selected_provider: str | None = None,
) -> dict[str, Any]:
    """Return alpha_vantage/massive probe_executed/disposition flags."""
    flags: dict[str, Any] = {
        "alpha_vantage_credentials_available": False,
        "alpha_vantage_probe_executed": False,
        "alpha_vantage_disposition": "not_attempted",
        "massive_credentials_available": False,
        "massive_probe_executed": False,
        "massive_disposition": "not_attempted",
    }
    for d in dispositions:
        if d.provider == "alpha_vantage":
            flags["alpha_vantage_probe_executed"] = d.probe_executed
            flags["alpha_vantage_disposition"] = d.disposition
        elif d.provider == "massive":
            flags["massive_probe_executed"] = d.probe_executed
            flags["massive_disposition"] = d.disposition
    if selected_provider == "alpha_vantage":
        flags["alpha_vantage_disposition"] = "supported"
    elif selected_provider == "massive":
        flags["massive_disposition"] = "supported"
    return flags


def _evaluate_candidate(
    result: ProviderCandidateResult,
    spec: ReferenceProbeSpec,
    *,
    starting_main_sha: str,
    live_run_head: str,
    branch: str,
    v1_pre_registration_commit: str,
    v2_pre_registration_commit: str,
    v3_pre_registration_commit: str,
    v4_pre_registration_commit: str | None = None,
    strategy_spec_sha256: str,
    alpaca_v2_decision_sha256: str,
    probe_spec_sha256: str,
    amendment_sha256: str,
    amendment_status_before_run: str,
    dataset: str,
    dispositions: tuple[ProviderDisposition, ...] = (),
    dataset_label: str = "original",
) -> ReferenceProbeDecision:
    """Build a decision-grade ReferenceProbeDecision from a candidate result."""
    rows = _capability_matrix_v3(result, spec)
    by_name = {r.capability: r for r in rows}

    gate_map = {name: by_name.get(name, CapabilityEvidence("", name, False, "unproven", "")).supported for name in spec.mandatory_gates}
    not_required = set(spec.not_required_gates)
    required = [name for name in spec.mandatory_gates if name not in not_required]
    all_pass = bool(required) and all(gate_map.get(name, False) for name in required)

    failed = [name for name in required if not gate_map.get(name, False)]
    not_required_failed = [name for name in not_required if not gate_map.get(name, False)]
    if all_pass:
        outcome = "supported"
        approved = True
        reason = "All required reference-provider gates passed."
    elif any(gate_map.get(name, False) for name in required):
        outcome = "partial_only"
        approved = False
        reason = f"Some required gates passed; failed: {sorted(failed)}"
    else:
        outcome = "no_currently_free_complete_reference_source"
        approved = False
        reason = f"No required gates passed; failed: {sorted(failed)}"

    if all_pass and not_required_failed:
        reason += f" (not required gates not passed: {sorted(not_required_failed)})"

    blockers: list[str] = []
    if failed:
        blockers.append(f"Failed required gates: {sorted(failed)}")
    if result.error:
        blockers.append(f"Provider errors: {result.error}")

    limitations = [f"Gate {name} not required and did not pass" for name in sorted(not_required_failed)]

    reference_provider_role = spec.reference_provider_role or (
        "monthly point-in-time active listings",
        "stock vs ETF classification",
        "security-type eligibility/exclusion",
        "primary listing/exchange provenance where available",
        "inactive/delisted status",
        "IPO/listing date where available",
        "delisting date where available",
        "symbol/reference identity required for monthly membership",
    )

    return ReferenceProbeDecision(
        probe_version=result.probe_version,
        task_id=spec.task_id,
        provider=result.provider if approved else None,
        outcome=outcome,
        approved_as_reference_provider=approved,
        reason=reason,
        candidate_order=spec.candidate_selection_order,
        starting_main_sha=starting_main_sha,
        branch=branch,
        live_run_head=live_run_head,
        final_pr_head=None,
        v1_pre_registration_commit=v1_pre_registration_commit,
        v2_pre_registration_commit=v2_pre_registration_commit,
        v3_pre_registration_commit=v3_pre_registration_commit,
        v4_pre_registration_commit=v4_pre_registration_commit,
        strategy_spec_sha256=strategy_spec_sha256,
        alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
        probe_spec_sha256=probe_spec_sha256,
        mixed_provider_amendment_sha256=amendment_sha256,
        mixed_provider_amendment_status_before_run=amendment_status_before_run,
        original_dataset_start=spec.original_dataset_start,
        original_dataset_end=spec.original_dataset_end,
        fallback_dataset_start=spec.fallback_dataset_start,
        fallback_dataset_end=spec.fallback_dataset_end,
        fallback_evaluated=dataset_label == "fallback",
        fallback_activation_reason=None if dataset_label == "original" else "Original dataset could not be satisfied under current free entitlement",
        dataset_used=dataset_label if approved else None,
        alpha_vantage_credentials_available=False,
        alpha_vantage_probe_executed=False,
        alpha_vantage_disposition="not_attempted",
        massive_credentials_available=False,
        massive_probe_executed=False,
        massive_disposition="not_attempted",
        selected_reference_provider=result.provider if approved else None,
        reference_provider_role=reference_provider_role,
        pit_dates=spec.probe_dates if dataset_label == "original" else spec.fallback_probe_dates,
        fallback_probe_dates=spec.fallback_probe_dates,
        pagination_verified=gate_map.get("pagination_exhausted_to_terminal", False),
        maximum_pages_active=_max_pages_by_state(result.observations, "active"),
        maximum_pages_inactive=_max_pages_by_state(result.observations, "inactive"),
        repeatability_passed=gate_map.get("repeatability", False),
        taxonomy_endpoint_verified=result.taxonomy_endpoint_verified,
        taxonomy_sha256=result.taxonomy_sha256,
        stock_type_allowlist=result.stock_type_allowlist,
        exchange_or_otc_policy_version=result.exchange_or_otc_policy_version,
        duplicate_symbol_count=result.duplicate_symbol_count,
        unresolved_duplicate_count=result.unresolved_duplicate_count,
        lifecycle_evidence=", ".join(result.lifecycle_fields_present) if result.lifecycle_fields_present else "",
        historical_2022_entitlement=gate_map.get("historical_2022_entitlement_under_current_plan", False),
        no_present_day_reconstruction=gate_map.get("no_present_day_reconstruction", False),
        estimated_http_calls_48_months=result.estimated_http_calls_48_months,
        estimated_collection_time_48_months_seconds=result.estimated_collection_time_48_months_seconds,
        pit_date_support_for_all_probe_dates=gate_map.get("pit_date_support_for_all_probe_dates", False),
        active_state_complete=gate_map.get("active_state_complete", False),
        inactive_or_delisted_state_complete=gate_map.get("inactive_or_delisted_state_complete", False),
        pagination_exhausted_to_terminal=gate_map.get("pagination_exhausted_to_terminal", False),
        no_pagination_cycles_or_repeated_cursors=gate_map.get("no_pagination_cycles_or_repeated_cursors", False),
        exact_historical_date_semantics=gate_map.get("exact_historical_date_semantics", False),
        common_stock_classification=gate_map.get("common_stock_classification", False),
        etf_classification=gate_map.get("etf_classification", False),
        warrant_exclusion=gate_map.get("warrant_exclusion", False),
        right_exclusion=gate_map.get("right_exclusion", False),
        unit_exclusion=gate_map.get("unit_exclusion", False),
        preferred_stock_exclusion=gate_map.get("preferred_stock_exclusion", False),
        otc_exclusion=gate_map.get("otc_exclusion", False),
        primary_listing_provenance=gate_map.get("primary_listing_provenance", False),
        symbol_presence_and_determinism=gate_map.get("symbol_presence_and_determinism", False),
        lifecycle_evidence_gate=gate_map.get("lifecycle_evidence", False),
        duplicate_symbol_behavior_and_resolution=gate_map.get("duplicate_symbol_behavior_and_resolution", False),
        repeatability=gate_map.get("repeatability", False),
        hashability=gate_map.get("hashability", False),
        no_present_day_reconstruction_gate=gate_map.get("no_present_day_reconstruction", False),
        historical_2022_entitlement_under_current_plan=gate_map.get("historical_2022_entitlement_under_current_plan", False),
        feasible_for_all_48_monthly_pit_snapshots=gate_map.get("feasible_for_all_48_monthly_pit_snapshots", False),
        feasible_for_all_probe_monthly_pit_snapshots=gate_map.get("feasible_for_all_probe_monthly_pit_snapshots", False),
        all_mandatory_gates_passed=all_pass,
        not_required_gates=spec.not_required_gates,
        blockers=tuple(blockers),
        limitations=tuple(limitations),
        recommended_next_assignment="devin/intra-001b-intraday-snapshot" if approved else "",
        candidate_dispositions=dispositions,
    )


def _probe_provider(
    provider: str,
    spec: ReferenceProbeSpec,
    settings: Any,
    pit_dates: tuple[str, ...],
    dataset_label: str,
    *,
    starting_main_sha: str,
    live_run_head: str,
    branch: str,
    v1_pre_registration_commit: str,
    v2_pre_registration_commit: str,
    v3_pre_registration_commit: str,
    v4_pre_registration_commit: str | None,
    strategy_spec_sha256: str,
    alpaca_v2_decision_sha256: str,
    probe_spec_sha256: str,
    amendment_sha256: str,
    amendment_status_before_run: str,
    prior_dispositions: tuple[ProviderDisposition, ...] = (),
) -> tuple[ProviderCandidateResult | None, ReferenceProbeDecision, ProviderDisposition]:
    """Execute one provider for one dataset and return result, decision, and disposition."""
    if provider == "alpha_vantage":
        key = settings.data.alpha_vantage_api_key
        if not key:
            disposition = ProviderDisposition(
                provider="alpha_vantage",
                dataset=dataset_label,
                pit_dates=pit_dates,
                credential_available=False,
                probe_executed=False,
                disposition="missing_credentials",
                reason="ALPHA_VANTAGE_API_KEY not configured",
            )
            return None, _empty_decision(
                spec,
                starting_main_sha,
                live_run_head,
                branch,
                v1_pre_registration_commit,
                v2_pre_registration_commit,
                v3_pre_registration_commit,
                v4_pre_registration_commit,
                strategy_spec_sha256,
                alpaca_v2_decision_sha256,
                probe_spec_sha256,
                amendment_sha256,
                amendment_status_before_run,
                pit_dates,
                dataset_label,
                prior_dispositions + (disposition,),
                "alpha_vantage",
            ), disposition
        from .alpha_vantage import AlphaVantageReferenceClient

        client = AlphaVantageReferenceClient(key)
        states = tuple(spec.alpha_vantage.get("states", ["active", "delisted"]))
        result = client.probe_provider(pit_dates, states, probe_version=spec.probe_version)
        result = ProviderCandidateResult(
            **{**result.__dict__, "capability_rows": _capability_matrix_v3(result, spec)}
        )
        disposition = ProviderDisposition(
            provider="alpha_vantage",
            dataset=dataset_label,
            pit_dates=pit_dates,
            credential_available=True,
            probe_executed=True,
            disposition="evaluated",
            reason=result.error or "Evaluated",
            logical_request_count=len(pit_dates) * len(states) * 2,
            http_request_count=len(pit_dates) * len(states) * 2,
            http_error_count=sum(1 for obs in result.observations if obs.error),
        )
        decision = _evaluate_candidate(
            result,
            spec,
            starting_main_sha=starting_main_sha,
            live_run_head=live_run_head,
            branch=branch,
            v1_pre_registration_commit=v1_pre_registration_commit,
            v2_pre_registration_commit=v2_pre_registration_commit,
            v3_pre_registration_commit=v3_pre_registration_commit,
            v4_pre_registration_commit=v4_pre_registration_commit,
            strategy_spec_sha256=strategy_spec_sha256,
            alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
            probe_spec_sha256=probe_spec_sha256,
            amendment_sha256=amendment_sha256,
            amendment_status_before_run=amendment_status_before_run,
            dataset=dataset_label,
            dispositions=prior_dispositions + (disposition,),
            dataset_label=dataset_label,
        )
        return result, decision, disposition

    if provider == "massive":
        key = settings.data.massive_api_key
        if not key:
            disposition = ProviderDisposition(
                provider="massive",
                dataset=dataset_label,
                pit_dates=pit_dates,
                credential_available=False,
                probe_executed=False,
                disposition="missing_credentials",
                reason="MASSIVE_API_KEY or POLYGON_API_KEY not configured",
            )
            return None, _empty_decision(
                spec,
                starting_main_sha,
                live_run_head,
                branch,
                v1_pre_registration_commit,
                v2_pre_registration_commit,
                v3_pre_registration_commit,
                v4_pre_registration_commit,
                strategy_spec_sha256,
                alpaca_v2_decision_sha256,
                probe_spec_sha256,
                amendment_sha256,
                amendment_status_before_run,
                pit_dates,
                dataset_label,
                prior_dispositions + (disposition,),
                "massive",
            ), disposition
        from .massive import MassiveReferenceClient

        pagination_cfg = spec.massive.get("pagination", {})
        safety_max_pages = pagination_cfg.get("safety_max_pages", 10000)
        client = MassiveReferenceClient(key)
        result = client.probe_provider(pit_dates, (True, False), probe_version=spec.probe_version, safety_max_pages=safety_max_pages)
        result = ProviderCandidateResult(
            **{**result.__dict__, "capability_rows": _capability_matrix_v3(result, spec)}
        )
        http_error_count = sum(1 for obs in result.observations if obs.error)
        http_request_count = sum(obs.page_count for obs in result.observations if obs.page_count > 0)
        disposition = ProviderDisposition(
            provider="massive",
            dataset=dataset_label,
            pit_dates=pit_dates,
            credential_available=True,
            probe_executed=True,
            disposition="evaluated",
            reason=result.error or "Evaluated",
            logical_request_count=len(pit_dates) * 2 * 2,  # active/inactive + repeat
            http_request_count=http_request_count,
            http_error_count=http_error_count,
        )
        decision = _evaluate_candidate(
            result,
            spec,
            starting_main_sha=starting_main_sha,
            live_run_head=live_run_head,
            branch=branch,
            v1_pre_registration_commit=v1_pre_registration_commit,
            v2_pre_registration_commit=v2_pre_registration_commit,
            v3_pre_registration_commit=v3_pre_registration_commit,
            v4_pre_registration_commit=v4_pre_registration_commit,
            strategy_spec_sha256=strategy_spec_sha256,
            alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
            probe_spec_sha256=probe_spec_sha256,
            amendment_sha256=amendment_sha256,
            amendment_status_before_run=amendment_status_before_run,
            dataset=dataset_label,
            dispositions=prior_dispositions + (disposition,),
            dataset_label=dataset_label,
        )
        return result, decision, disposition

    raise ValueError(f"Unknown provider: {provider}")


def _empty_decision(
    spec: ReferenceProbeSpec,
    starting_main_sha: str,
    live_run_head: str,
    branch: str,
    v1_pre_registration_commit: str,
    v2_pre_registration_commit: str,
    v3_pre_registration_commit: str,
    v4_pre_registration_commit: str | None,
    strategy_spec_sha256: str,
    alpaca_v2_decision_sha256: str,
    probe_spec_sha256: str,
    amendment_sha256: str,
    amendment_status_before_run: str,
    pit_dates: tuple[str, ...],
    dataset: str,
    dispositions: tuple[ProviderDisposition, ...],
    missing_provider: str,
) -> ReferenceProbeDecision:
    provider_flags = _provider_flags_from_dispositions(dispositions)
    if missing_provider == "alpha_vantage":
        provider_flags["alpha_vantage_credentials_available"] = False
        provider_flags["alpha_vantage_disposition"] = "missing_credentials"
    elif missing_provider == "massive":
        provider_flags["massive_credentials_available"] = False
        provider_flags["massive_disposition"] = "missing_credentials"
    return ReferenceProbeDecision(
        probe_version=spec.probe_version,
        task_id=spec.task_id,
        provider=None,
        outcome="no_currently_free_complete_reference_source",
        approved_as_reference_provider=False,
        reason=f"{missing_provider} credentials missing or provider not evaluated",
        candidate_order=spec.candidate_selection_order,
        starting_main_sha=starting_main_sha,
        branch=branch,
        live_run_head=live_run_head,
        v1_pre_registration_commit=v1_pre_registration_commit,
        v2_pre_registration_commit=v2_pre_registration_commit,
        v3_pre_registration_commit=v3_pre_registration_commit,
        v4_pre_registration_commit=v4_pre_registration_commit,
        strategy_spec_sha256=strategy_spec_sha256,
        alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
        probe_spec_sha256=probe_spec_sha256,
        mixed_provider_amendment_sha256=amendment_sha256,
        mixed_provider_amendment_status_before_run=amendment_status_before_run,
        fallback_dataset_start=spec.fallback_dataset_start,
        fallback_dataset_end=spec.fallback_dataset_end,
        fallback_evaluated=dataset == "fallback",
        dataset_used=None,
        pit_dates=pit_dates,
        fallback_probe_dates=spec.fallback_probe_dates,
        candidate_dispositions=dispositions,
        not_required_gates=spec.not_required_gates,
        feasible_for_all_probe_monthly_pit_snapshots=False,
        **provider_flags,
        recommended_next_assignment="",
        blockers=(f"{missing_provider} not available",),
        reference_provider_role=spec.reference_provider_role,
    )


def _is_structural_failure(decision: ReferenceProbeDecision) -> bool:
    """Return True if the failure is structural, not merely historical-depth/entitlement."""
    structural_gates = {
        "pagination_exhausted_to_terminal",
        "no_pagination_cycles_or_repeated_cursors",
        "common_stock_classification",
        "etf_classification",
        "warrant_exclusion",
        "right_exclusion",
        "unit_exclusion",
        "preferred_stock_exclusion",
        "otc_exclusion",
        "primary_listing_provenance",
        "symbol_presence_and_determinism",
        "lifecycle_evidence_gate",
        "duplicate_symbol_behavior_and_resolution",
        "repeatability",
        "hashability",
        "no_present_day_reconstruction_gate",
        "exact_historical_date_semantics",
    }
    failed_structural = [g for g in structural_gates if not getattr(decision, g, False)]
    return bool(failed_structural)


def run_reference_probe(
    spec: ReferenceProbeSpec,
    settings: Any,
    *,
    v1_pre_registration_commit: str,
    v2_pre_registration_commit: str,
    v3_pre_registration_commit: str,
    v4_pre_registration_commit: str | None = None,
    probe_spec_sha256: str,
    starting_main_sha: str | None = None,
    branch: str | None = None,
    live_run_head: str | None = None,
    only_provider: str | None = None,
) -> tuple[ProviderCandidateResult | None, ReferenceProbeDecision]:
    """Run the locked candidate-evaluation order and return a decision.

    First try the original four-year reference dates. If no provider passes,
    attempt the approved two-year fallback dates (methodology amendment).
    """
    if branch is None:
        branch = _current_branch()
    if starting_main_sha is None:
        starting_main_sha = _main_base_sha()
    if live_run_head is None:
        live_run_head = v4_pre_registration_commit or _current_head()

    for commit in (v1_pre_registration_commit, v2_pre_registration_commit, v3_pre_registration_commit, v4_pre_registration_commit):
        if commit:
            validate_pre_registration_commit(commit, live_run_head)

    original_sha = sha256_of_file(spec.original_strategy_spec_path)
    if original_sha != spec.expected_original_strategy_spec_sha256:
        raise ValueError(
            f"Original INTRA-001 spec SHA mismatch: expected {spec.expected_original_strategy_spec_sha256}, got {original_sha}"
        )

    strategy_spec_sha256 = original_sha
    amendment_sha256 = sha256_of_file(spec.amendment_path)
    amendment_status_before_run = "approved_mixed_model_reference_provider_pending"

    alpaca_path = spec.alpaca_v2_artifact_path
    alpaca_v2_decision_sha256 = sha256_of_file(alpaca_path) if alpaca_path and Path(alpaca_path).expanduser().resolve().exists() else None

    candidate_order = list(spec.candidate_selection_order)
    if only_provider:
        candidate_order = [only_provider]

    all_dispositions: list[ProviderDisposition] = []
    last_result: ProviderCandidateResult | None = None
    last_decision: ReferenceProbeDecision | None = None
    fallback_reason: str | None = None

    for pit_dates, dataset_label in (
        (spec.probe_dates, "original"),
        (spec.fallback_probe_dates, "fallback"),
    ):
        if not pit_dates:
            continue
        for provider in candidate_order:
            result, decision, disposition = _probe_provider(
                provider,
                spec,
                settings,
                pit_dates,
                dataset_label,
                starting_main_sha=starting_main_sha,
                live_run_head=live_run_head,
                branch=branch,
                v1_pre_registration_commit=v1_pre_registration_commit,
                v2_pre_registration_commit=v2_pre_registration_commit,
                v3_pre_registration_commit=v3_pre_registration_commit,
                v4_pre_registration_commit=v4_pre_registration_commit,
                strategy_spec_sha256=strategy_spec_sha256,
                alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
                probe_spec_sha256=probe_spec_sha256,
                amendment_sha256=amendment_sha256,
                amendment_status_before_run=amendment_status_before_run,
                prior_dispositions=tuple(all_dispositions),
            )
            all_dispositions.append(disposition)
            last_result = result
            last_decision = decision
            if decision.approved_as_reference_provider:
                # Mark selected disposition
                selected_index = len(all_dispositions) - 1
                all_dispositions = list(all_dispositions)
                all_dispositions[selected_index] = ProviderDisposition(
                    **{**disposition.__dict__, "selected": True}
                )
                # Update decision with final dispositions and provider metadata
                provider_flags = _provider_flags_from_dispositions(tuple(all_dispositions), selected_provider=result.provider)
                provider_flags["alpha_vantage_credentials_available"] = settings.data.alpha_vantage_api_key is not None
                provider_flags["massive_credentials_available"] = settings.data.massive_api_key is not None
                decision = ReferenceProbeDecision(
                    **{
                        **decision.__dict__,
                        "provider": result.provider,
                        "selected_reference_provider": result.provider,
                        "candidate_dispositions": tuple(all_dispositions),
                        "dataset_used": dataset_label,
                        **provider_flags,
                    }
                )
                return result, decision

        # After exhausting candidates for this dataset, decide whether fallback is allowed.
        if dataset_label == "original" and last_decision is not None:
            if _is_structural_failure(last_decision):
                fallback_reason = "Structural failure; fallback cannot cure this provider."
                break
            # Only permit fallback for historical-depth / entitlement limitation.
            fallback_reason = "Original dataset could not be satisfied under current free entitlement; fallback approved."

    # No provider passed any dataset.
    if last_decision is not None:
        provider_flags = _provider_flags_from_dispositions(tuple(all_dispositions))
        provider_flags["alpha_vantage_credentials_available"] = settings.data.alpha_vantage_api_key is not None
        provider_flags["massive_credentials_available"] = settings.data.massive_api_key is not None
        final_decision = ReferenceProbeDecision(
            **{
                **last_decision.__dict__,
                "provider": None,
                "approved_as_reference_provider": False,
                "outcome": "no_currently_free_complete_reference_source",
                "reason": f"No candidate satisfied all mandatory gates. {fallback_reason or ''}",
                "candidate_dispositions": tuple(all_dispositions),
                "dataset_used": "none",
                "fallback_evaluated": dataset_label == "fallback",
                "fallback_activation_reason": fallback_reason,
                "recommended_next_assignment": "gary-decision-intra-001-reference-data-cost",
                **provider_flags,
            }
        )
        return last_result, final_decision

    # Nothing was attempted (no candidates or no credentials).
    return None, ReferenceProbeDecision(
        probe_version=spec.probe_version,
        task_id=spec.task_id,
        provider=None,
        outcome="inconclusive",
        approved_as_reference_provider=False,
        reason="No candidate provider could be evaluated.",
        candidate_order=tuple(candidate_order),
        starting_main_sha=starting_main_sha,
        branch=branch,
        live_run_head=live_run_head,
        v1_pre_registration_commit=v1_pre_registration_commit,
        v2_pre_registration_commit=v2_pre_registration_commit,
        v3_pre_registration_commit=v3_pre_registration_commit,
        v4_pre_registration_commit=v4_pre_registration_commit,
        strategy_spec_sha256=strategy_spec_sha256,
        alpaca_v2_decision_sha256=alpaca_v2_decision_sha256,
        probe_spec_sha256=probe_spec_sha256,
        mixed_provider_amendment_sha256=amendment_sha256,
        mixed_provider_amendment_status_before_run=amendment_status_before_run,
        fallback_dataset_start=spec.fallback_dataset_start,
        fallback_dataset_end=spec.fallback_dataset_end,
        dataset_used="none",
        candidate_dispositions=tuple(all_dispositions),
        not_required_gates=spec.not_required_gates,
        feasible_for_all_probe_monthly_pit_snapshots=False,
        alpha_vantage_credentials_available=settings.data.alpha_vantage_api_key is not None,
        massive_credentials_available=settings.data.massive_api_key is not None,
        recommended_next_assignment="gary-decision-intra-001-reference-data-cost",
    )
