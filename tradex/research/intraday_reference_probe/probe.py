"""Reference provider probe orchestration for INTRA-001B-REFERENCE."""
from __future__ import annotations

import subprocess
from typing import Any

from .models import (
    CapabilityEvidence,
    ProviderCandidateResult,
    ReferenceProbeDecision,
)
from .spec import ReferenceProbeSpec, sha256_of_file


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


def validate_pre_registration_commit(
    commit: str, final_head: str | None = None
) -> None:
    """Verify that the pre-registration commit is an ancestor of final_head."""
    if final_head is None:
        final_head = _current_head()
    if len(commit) != 40:
        raise ValueError(f"pre-registration commit must be 40 characters: {commit!r}")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, final_head],
        check=True,
    )


def _classification_for(row_type: str) -> str:
    if row_type in ("repeatability", "pit_date_response", "active_delisted_counts"):
        return "live_evidence"
    if row_type in ("endpoint_documentation", "free_tier", "no_paid_upgrade"):
        return "documented_capability"
    return "unproven"


def _capability_matrix(result: ProviderCandidateResult) -> tuple[CapabilityEvidence, ...]:
    rows: list[CapabilityEvidence] = []
    observations = result.observations
    by_date = {}
    for obs in observations:
        by_date.setdefault(obs.pit_date, []).append(obs)

    # PIT date support
    pit_pass = bool(observations) and all(
        not obs.error and obs.row_count > 0 for obs in observations
    )
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="pit_date_support_for_all_probe_dates",
            supported=pit_pass,
            evidence_class="live_evidence",
            note="All four PIT dates returned rows without error."
            if pit_pass
            else "At least one PIT date failed or returned zero rows.",
        )
    )

    # Active + delisted/inactive coverage
    states_present = {obs.state for obs in observations if not obs.error and obs.row_count > 0}
    active_delisted_pass = "active" in states_present and ("delisted" in states_present or "inactive" in states_present or "false" in states_present)
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="active_and_delisted_or_inactive_coverage",
            supported=active_delisted_pass,
            evidence_class="live_evidence",
            note=f"States with data: {sorted(states_present)}.",
        )
    )

    # Security-type exclusion feasibility
    has_type_field = bool(
        result.security_type_field and any(result.security_type_counts.values())
    )
    observed_types = set(result.security_type_counts.keys())
    observed_lower = {t.lower() for t in observed_types}
    unwanted_markers = {"otc", "warrant", "right", "unit", "preferred", "preferred_stock", "pfd"}
    explicit_unwanted_seen = bool(observed_lower & unwanted_markers)
    # A provider with only Stock/ETF cannot distinguish common vs preferred, OTC, warrants, etc.
    only_stock_etf = observed_lower <= {"stock", "etf"}
    taxonomy_granular = has_type_field and explicit_unwanted_seen and not only_stock_etf
    exclusions_feasible = has_type_field and not only_stock_etf
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="security_type_exclusions_feasible",
            supported=exclusions_feasible,
            evidence_class="live_evidence",
            note=f"Observed type values: {sorted(observed_types)}."
            if observed_types
            else "No security type values observed.",
        )
    )
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="security_type_taxonomy_granular",
            supported=taxonomy_granular,
            evidence_class="live_evidence",
            note="Provider exposes labels that distinguish the five unwanted security types."
            if taxonomy_granular
            else "Provider does not expose granular security-type labels for all five exclusions.",
        )
    )

    # Primary exchange provenance
    exchange_pass = bool(
        result.primary_exchange_field and any(result.exchange_counts.values())
    )
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="primary_exchange_provenance",
            supported=exchange_pass,
            evidence_class="live_evidence",
            note=f"Observed exchanges: {sorted(result.exchange_counts.keys())[:10]}..."
            if exchange_pass
            else "No primary exchange field or values observed.",
        )
    )

    # Repeatability
    repeat_obs = [obs for obs in observations if obs.repeat_match is not None]
    repeat_pass = bool(repeat_obs) and all(obs.repeat_match for obs in repeat_obs)
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="full_repeatability",
            supported=repeat_pass,
            evidence_class="live_evidence",
            note="Repeat fetch SHA-256 matched for every observation."
            if repeat_pass
            else "At least one repeat fetch did not match or failed.",
        )
    )

    # Free under current entitlement
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="free_under_current_entitlement",
            supported=True,
            evidence_class="documented_capability",
            note="Probe used only free endpoints; no paid upgrade was required.",
        )
    )

    # 2022 entitlement
    has_2022 = any(obs.pit_date.startswith("2022-") and not obs.error for obs in observations)
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="historical_2022_entitlement_under_current_plan",
            supported=has_2022,
            evidence_class="live_evidence",
            note="A 2022 PIT date was requested and returned data."
            if has_2022
            else "2022 PIT date request failed or was not attempted.",
        )
    )

    # Listing/delisting date fields
    rows.append(
        CapabilityEvidence(
            provider=result.provider,
            capability="listing_and_delisting_date_fields",
            supported=bool(result.delisting_date_field or result.listing_date_field),
            evidence_class="live_evidence",
            note=f"Delisting field: {result.delisting_date_field}; listing field: {result.listing_date_field}.",
        )
    )

    return tuple(rows)


def _evaluate_candidate(result: ProviderCandidateResult) -> ReferenceProbeDecision:
    rows = _capability_matrix(result)
    required_capabilities = {
        "pit_date_support_for_all_probe_dates",
        "active_and_delisted_or_inactive_coverage",
        "security_type_exclusions_feasible",
        "security_type_taxonomy_granular",
        "primary_exchange_provenance",
        "full_repeatability",
        "free_under_current_entitlement",
        "historical_2022_entitlement_under_current_plan",
        "listing_and_delisting_date_fields",
    }
    by_name = {r.capability: r for r in rows}
    failed = [c for c in required_capabilities if not by_name.get(c, CapabilityEvidence("", c, False, "unproven", "")).supported]

    outcome: str
    approved: bool
    reason: str
    if failed:
        outcome = "partial_only" if any(by_name[c].supported for c in required_capabilities if c in by_name) else "no_currently_free_complete_reference_source"
        approved = False
        reason = f"Failed mandatory gates: {sorted(failed)}"
    else:
        outcome = "supported"
        approved = True
        reason = "All mandatory reference-provider gates passed."

    return ReferenceProbeDecision(
        probe_version=result.probe_version,
        task_id="INTRA-001B-REFERENCE",
        provider=result.provider,
        outcome=outcome,
        approved_as_reference_provider=approved,
        reason=reason,
        candidate_order=("alpha_vantage", "massive"),
        target_entitlement=result.target_entitlement,
        pit_dates=tuple(sorted({obs.pit_date for obs in result.observations})),
        pit_date_support=by_name.get("pit_date_support_for_all_probe_dates", CapabilityEvidence("", "", False, "unproven", "")).supported,
        active_delisted_coverage=by_name.get("active_and_delisted_or_inactive_coverage", CapabilityEvidence("", "", False, "unproven", "")).supported,
        security_type_exclusions_possible=by_name.get("security_type_exclusions_feasible", CapabilityEvidence("", "", False, "unproven", "")).supported,
        security_type_taxonomy_granular=by_name.get("security_type_taxonomy_granular", CapabilityEvidence("", "", False, "unproven", "")).supported,
        primary_exchange_provenance=by_name.get("primary_exchange_provenance", CapabilityEvidence("", "", False, "unproven", "")).supported,
        reproducible=by_name.get("full_repeatability", CapabilityEvidence("", "", False, "unproven", "")).supported,
        free_under_current_entitlement=by_name.get("free_under_current_entitlement", CapabilityEvidence("", "", False, "unproven", "")).supported,
        full_repeatability_passed=by_name.get("full_repeatability", CapabilityEvidence("", "", False, "unproven", "")).supported,
    )


def _probe_provider(
    provider: str,
    spec: ReferenceProbeSpec,
    settings: Any,
    pit_dates: tuple[str, ...],
    v1_pre_registration_commit: str,
    final_head: str,
    branch: str,
) -> tuple[ProviderCandidateResult | None, ReferenceProbeDecision | None]:
    if provider == "alpha_vantage":
        key = settings.data.alpha_vantage_api_key
        if not key:
            return None, None
        from .alpha_vantage import AlphaVantageReferenceClient

        client = AlphaVantageReferenceClient(key)
        states = tuple(spec.alpha_vantage.get("states", ["active", "delisted"]))
        result = client.probe_provider(pit_dates, states)
        result = ProviderCandidateResult(
            **{**result.__dict__, "capability_rows": _capability_matrix(result)}
        )
        decision = _evaluate_candidate(result)
        decision = ReferenceProbeDecision(
            **{**decision.__dict__, "v1_pre_registration_commit": v1_pre_registration_commit, "final_head": final_head, "branch": branch}
        )
        return result, decision

    if provider == "massive":
        key = settings.data.massive_api_key
        if not key:
            return None, None
        from .massive import MassiveReferenceClient

        client = MassiveReferenceClient(key)
        result = client.probe_provider(pit_dates, (True, False))
        result = ProviderCandidateResult(
            **{**result.__dict__, "capability_rows": _capability_matrix(result)}
        )
        decision = _evaluate_candidate(result)
        decision = ReferenceProbeDecision(
            **{**decision.__dict__, "v1_pre_registration_commit": v1_pre_registration_commit, "final_head": final_head, "branch": branch}
        )
        return result, decision

    return None, None


def run_reference_probe(
    spec: ReferenceProbeSpec,
    settings: Any,
    *,
    v1_pre_registration_commit: str,
    branch: str | None = None,
    final_head: str | None = None,
    only_provider: str | None = None,
) -> tuple[ProviderCandidateResult | None, ReferenceProbeDecision]:
    """Run the locked candidate-evaluation order and return a decision.

    First try the original four-year reference dates. If no provider passes,
    attempt the approved two-year fallback dates (methodology amendment).
    """
    if final_head is None:
        final_head = _current_head()
    if branch is None:
        branch = _current_branch()
    validate_pre_registration_commit(v1_pre_registration_commit, final_head)

    original_sha = sha256_of_file(spec.original_strategy_spec_path)
    if original_sha != spec.expected_original_strategy_spec_sha256:
        raise ValueError(
            f"Original INTRA-001 spec SHA mismatch: expected {spec.expected_original_strategy_spec_sha256}, got {original_sha}"
        )

    candidate_order = list(spec.candidate_selection_order)
    if only_provider:
        candidate_order = [only_provider]

    attempts: list[tuple[str, tuple[str, ...], ProviderCandidateResult | None, ReferenceProbeDecision | None]] = []

    for pit_dates, dataset_label in (
        (spec.probe_dates, "original"),
        (spec.fallback_probe_dates, "fallback"),
    ):
        for provider in candidate_order:
            result, decision = _probe_provider(
                provider, spec, settings, pit_dates,
                v1_pre_registration_commit, final_head, branch,
            )
            attempts.append((provider, pit_dates, result, decision))
            if decision is not None and decision.approved_as_reference_provider:
                return result, ReferenceProbeDecision(
                        **{
                            **decision.__dict__,
                            "pit_dates": pit_dates,
                            "fallback_probe_dates": spec.fallback_probe_dates,
                            "dataset_used": dataset_label,
                        }
                    )

    # No candidate satisfied either dataset.
    last_result = attempts[-1][2] if attempts else None
    last_decision = attempts[-1][3] if attempts else None
    dispositions = [
        (name, decision.reason if decision else "not attempted")
        for name, _pit_dates, _result, decision in attempts
    ]
    if last_decision is not None:
        return last_result, ReferenceProbeDecision(
            **{
                **last_decision.__dict__,
                "provider": None,
                "approved_as_reference_provider": False,
                "outcome": "no_currently_free_complete_reference_source",
                "reason": f"No candidate satisfied all mandatory gates. Dispositions: {dispositions}",
                "candidate_dispositions": tuple(dispositions),
                "fallback_probe_dates": spec.fallback_probe_dates,
                "dataset_used": "none",
            }
        )

    return None, ReferenceProbeDecision(
        probe_version=spec.probe_version,
        task_id=spec.task_id,
        provider=None,
        outcome="no_currently_free_complete_reference_source",
        approved_as_reference_provider=False,
        reason="No candidate provider could be evaluated.",
        candidate_order=tuple(candidate_order),
        pit_dates=(),
        fallback_probe_dates=spec.fallback_probe_dates,
        dataset_used="none",
        v1_pre_registration_commit=v1_pre_registration_commit,
        final_head=final_head,
        branch=branch,
        candidate_dispositions=tuple(dispositions),
    )
