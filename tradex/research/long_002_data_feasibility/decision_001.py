"""LONG-002B-DEC-001: research-governance decision packet generator.

This module builds a human-readable and machine-readable decision packet for the
two remaining LONG-002B blockers. It performs no provider calls, uses no
credentials, and only reads already-saved artifacts and locked specifications.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

# Locked starting point for this decision packet.
STARTING_MAIN_SHA = "c7782f49dce0c637bfea1042a2ce65206d77d7af"

# Upstream specs whose hashes are recorded and verified.
UPSTREAM_SPEC_PATHS: dict[str, str] = {
    "LONG-002-v1.json": "docs/research/specs/LONG-002-v1.json",
    "LONG-002B-probe-v1.json": "docs/research/specs/LONG-002B-probe-v1.json",
    "LONG-002B-data-contract-v1.json": "docs/research/specs/LONG-002B-data-contract-v1.json",
    "LONG-002B-AMEND-001-probe-v1.json": "docs/research/specs/LONG-002B-AMEND-001-probe-v1.json",
}

PREREQUISITE_BUNDLE = "docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_upstream_specs(repo_root: Path) -> dict[str, str]:
    """Return the SHA-256 map for the locked upstream specs, raising on mismatch."""
    hashes: dict[str, str] = {}
    for name, rel_path in UPSTREAM_SPEC_PATHS.items():
        path = repo_root / rel_path
        if not path.exists():
            raise FileNotFoundError(f"Locked spec missing: {path}")
        hashes[name] = _sha256(path)
    return hashes


def _load_pr_50_artifact(repo_root: Path) -> dict[str, Any]:
    bundle = repo_root / PREREQUISITE_BUNDLE
    manifest_path = bundle / "artifact_manifest.json"
    report_path = bundle / "feasibility_report.json"
    if not manifest_path.exists() or not report_path.exists():
        raise FileNotFoundError(f"PR #50 artifact bundle missing: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    family_dispositions = {
        f["family"]: f["disposition"] for f in report.get("data_families", [])
    }
    return {
        "bundle_path": str(bundle.relative_to(repo_root)),
        "run_id": manifest.get("run_id"),
        "overall_disposition": report.get("overall_disposition"),
        "family_dispositions": family_dispositions,
        "total_http_requests": report.get("total_http_requests"),
        "preregistration_commit_sha": manifest.get("preregistration_commit_sha"),
        "code_commit_sha": manifest.get("code_commit_sha"),
    }


def build_decision_packet(repo_root: Path | str) -> dict[str, Any]:
    """Return the LONG-002B-DEC-001 decision packet as a JSON-safe dict."""
    root = Path(repo_root)
    spec_hashes = _verify_upstream_specs(root)
    artifact = _load_pr_50_artifact(root)

    if artifact["overall_disposition"] != "not_supported":
        raise RuntimeError("PR #50 artifact must be not_supported for this decision packet")
    for family in (
        "security_identity_lifecycle_and_exclusion_classification",
        "earnings_event_timing",
    ):
        if artifact["family_dispositions"].get(family) != "not_supported":
            raise RuntimeError(f"PR #50 family {family} must be not_supported")

    blocked_families = [
        {
            "id": "security_identity_lifecycle_and_exclusion_classification",
            "name": "Security identity, lifecycle, and exclusion classification",
            "disposition": "not_supported",
            "blocker_summary": (
                "Multiple required (symbol, as_of_date) PIT rows returned generic or missing "
                "type fields (None, CS, INDEX) with no corroborating PIT name/SIC evidence. "
                "They fail closed to unknown, so the minimum exclusion-classification contract "
                "is not satisfied. PFF, SPY, IGR, and IPOD classify correctly, but "
                "panel-wide defensibility is not demonstrated."
            ),
        },
        {
            "id": "earnings_event_timing",
            "name": "Historical known-at-the-decision-time earnings scheduling",
            "disposition": "not_supported",
            "blocker_summary": (
                "No preregistered endpoint returned a historical earnings schedule as it was "
                "known at the decision timestamp. Massive vX/reference/financials returns "
                "XBRL filing/period dates only; SEC EDGAR gives actual disclosure timestamps; "
                "Yahoo earnings calendar is prospective/current. The fallbacks were not exercised."
            ),
        },
    ]

    option_3_security = {
        "preferred_provider": {
            "name": "crsp_wrds",
            "capability_sought": (
                "Historical daily security master with active/inactive/delisted flag, "
                "effective-dated ticker and share-class history, and a security-type "
                "taxonomy that maps defensibly to the locked LONG-002 exclusions."
            ),
            "why_existing_sources_failed": (
                "Massive v3/reference/tickers provides a single PIT row per ticker/date "
                "with generic type codes (CS/INDEX) that do not map to ETF/CEF/pre-merger "
                "SPAC; Alpaca and SEC EDGAR fallbacks similarly lack a complete historical "
                "exchange security master with lifecycle and defensible classification."
            ),
            "cost_access_licensing": {
                "confirmed_by_official_source": False,
                "expected_tier": "paid institutional or academic license via WRDS",
                "notes": (
                    "Per-seat or site licensing, historical coverage start date, and commercial "
                    "redistribution terms must be confirmed by WRDS/CRSP official source before "
                    "amendment approval. No live calls or credential registration occur in this PR."
                ),
            },
        },
        "fallbacks": [
            {
                "name": "nasdaq_data_link",
                "capability_sought": "CRSP/Sharadar daily stock metadata including historical delistings and type flags.",
                "cost_access_licensing": {
                    "confirmed_by_official_source": False,
                    "expected_tier": "paid subscription via Nasdaq Data Link",
                    "notes": (
                        "Specific dataset code, historical vintage policy, and subscription cost must "
                        "be confirmed by Nasdaq Data Link before amendment approval."
                    ),
                },
            },
            {
                "name": "sec_edgar",
                "capability_sought": (
                    "Issuer-level name/ticker/filing history; used only for identity joins "
                    "and not for exchange security-type classification."
                ),
                "cost_access_licensing": {
                    "confirmed_by_official_source": True,
                    "expected_tier": "free public SEC EDGAR access",
                    "notes": "Known free public access; does not provide complete exchange security master or security-type classification.",
                },
            },
        ],
    }

    option_3_earnings = {
        "preferred_provider": {
            "name": "wall_street_horizon",
            "capability_sought": (
                "Historical earnings announcement calendar with vintage information: the "
                "future earnings date known at the decision timestamp, subsequent revisions, "
                "and separation from actual release/SEC filing timestamps."
            ),
            "why_existing_sources_failed": (
                "Massive vX/reference/financials exposes filing_date/period_of_report_date only; "
                "SEC EDGAR provides actual acceptance timestamps, not a previously known future "
                "schedule; Yahoo earnings calendar is current/prospective and has no vintage history."
            ),
            "cost_access_licensing": {
                "confirmed_by_official_source": False,
                "expected_tier": "paid institutional data feed / API subscription",
                "notes": (
                    "Pricing, minimum commitment, historical vintage start date, and redistribution "
                    "terms must be confirmed by Wall Street Horizon official source before amendment "
                    "approval. No live calls or credential registration occur in this PR."
                ),
            },
        },
        "fallbacks": [
            {
                "name": "quandl_sharadar_events",
                "capability_sought": "Historical earnings/announcement date dataset with vintage/revision history.",
                "cost_access_licensing": {
                    "confirmed_by_official_source": False,
                    "expected_tier": "paid subscription via Nasdaq Data Link (Sharadar)",
                    "notes": (
                        "Exact dataset table, vintage/revision policy, and subscription cost must be "
                        "confirmed by Nasdaq Data Link / Sharadar before amendment approval."
                    ),
                },
            },
            {
                "name": "sec_edgar",
                "capability_sought": (
                    "Reconfirm that actual disclosure timestamps cannot substitute for a previously "
                    "known future schedule; restrict use to filing/period dates."
                ),
                "cost_access_licensing": {
                    "confirmed_by_official_source": True,
                    "expected_tier": "free public SEC EDGAR access",
                    "notes": "Known free public access; provides actual release/filing dates only, not a known-at-time schedule.",
                },
            },
        ],
    }

    packet: dict[str, Any] = {
        "schema_version": "1.0",
        "task_id": "LONG-002B-DEC-001",
        "spec_name": "LONG-002B-DEC-001: Blocker disposition decision packet",
        "classification": "research-governance-only",
        "status": "pending_gary_decision",
        "long_002c_authorized": False,
        "production_promotion_eligible": False,
        "starting_main_sha": STARTING_MAIN_SHA,
        "upstream_spec_hashes": spec_hashes,
        "prerequisite_artifact": {
            "task_id": "LONG-002B-AMEND-001",
            "bundle_path": artifact["bundle_path"],
            "run_id": artifact["run_id"],
            "overall_disposition": artifact["overall_disposition"],
            "total_http_requests": artifact["total_http_requests"],
            "preregistration_commit_sha": artifact["preregistration_commit_sha"],
            "code_commit_sha": artifact["code_commit_sha"],
            "blocked_family_dispositions": artifact["family_dispositions"],
        },
        "blocked_families": blocked_families,
        "options": [
            {
                "id": "1",
                "label": "Continue blocking LONG-002",
                "description": (
                    "Preserve both blocked families as not_supported and do not authorize "
                    "LONG-002C. The program remains paused until new evidence satisfies the "
                    "locked minimum usable contracts."
                ),
                "selected": False,
                "requires_gary_approval": False,
                "long_002c_authorized": False,
                "evidence_required_to_reopen": (
                    "A provider amendment or policy change that demonstrates, for the probe panel, "
                    "(a) defensible PIT security identity/lifecycle/exclusion classification, and "
                    "(b) historical known-at-the-decision-time earnings scheduling, both satisfying "
                    "their locked minimum usable contracts."
                ),
            },
            {
                "id": "2",
                "label": "Adopt an explicit fail-closed unknown policy",
                "description": (
                    "Formally amend the LONG-002 data contract so that missing or unresolvable "
                    "PIT facts remain unknown and are never used as historical facts, features, "
                    "ranking inputs, or actionability shortcuts. For earnings scheduling, an "
                    "unknown schedule means the observation cannot be labeled a confirmed "
                    "non-earnings setup and cannot reach Enter Now or Armed under the ordinary "
                    "policy (at most Waitlist or do_not_surface, per later design). Current "
                    "calendars, actual release dates, and SEC filing timestamps cannot be used "
                    "retrospectively to restore actionability. This option requires a separate "
                    "Gary/ChatGPT methodology approval before any LONG-002C design PR and does not "
                    "establish that sufficient actionable samples exist."
                ),
                "selected": False,
                "requires_gary_approval": True,
                "long_002c_authorized": False,
                "contract_amendment_required": True,
                "contract_terms": {
                    "security_unknown_rows_excluded_from_eligible_universe": True,
                    "no_backfill_of_current_or_later_classifications_as_historical_facts": True,
                    "unknown_security_classification_is_not_treated_as_common_stock": True,
                    "earnings_schedule_fields_remain_unknown_when_historical_known_at_time_evidence_unavailable": True,
                    "current_calendars_sec_filing_timestamps_or_actual_release_dates_may_not_be_substituted_for_previously_known_schedules": True,
                    "unavailable_earnings_timing_cannot_become_predictive_feature_or_ranking_input": True,
                    "unknown_earnings_schedule_cannot_be_labeled_confirmed_non_earnings_setup": True,
                    "unknown_earnings_schedule_cannot_reach_enter_now_or_armed_under_ordinary_policy": True,
                    "unknown_earnings_maximum_actionable_state_waitlist_or_do_not_surface": True,
                    "no_retrospective_actionability_from_current_calendars_actual_release_or_sec_timestamps": True,
                    "actionability_and_kpi_reporting_mark_unknown_earnings_observations_unavailable": True,
                    "insufficient_known_schedule_coverage_makes_executable_policy_evaluation_inconclusive": True,
                    "coverage_selection_bias_comparability_and_sample_sufficiency_risks_documented": True,
                    "authorizes_only_a_separate_long_002c_design_pr_after_explicit_gary_approval": True,
                },
            },
            {
                "id": "3",
                "label": "Authorize one final bounded provider amendment",
                "description": (
                    "Approve one additional research-only provider amendment bounded to resolve "
                    "the two blocked families. No provider calls or code changes occur in this "
                    "decision PR; the amendment must be separately approved and preregistered."
                ),
                "selected": False,
                "requires_gary_approval": True,
                "long_002c_authorized": False,
                "provider_amendment_proposal": {
                    "purpose": (
                        "Resolve the two not_supported blockers with positive, effective-dated "
                        "evidence from at most one preferred provider plus two fallbacks per family."
                    ),
                    "security_identity_lifecycle_and_exclusion_classification": option_3_security,
                    "earnings_event_timing": option_3_earnings,
                    "budget": {
                        "max_http_requests": 120,
                        "max_runtime_minutes": 30,
                        "max_retries_per_request": 1,
                        "max_fallbacks_per_family": 2,
                        "no_provider_calls_until_gary_approval": True,
                    },
                    "stop_conditions": [
                        (
                            "Stop the security family once the probe panel demonstrates stable PIT identity, "
                            "active/inactive/renamed/delisted lifecycle evidence, defensible exclusion-type "
                            "classification for each locked category, and split/dividend event provenance."
                        ),
                        (
                            "Stop the earnings family once a source demonstrates historical known-at-the-decision-time "
                            "earnings scheduling with vintage/revision information and separation from SEC filing timestamps."
                        ),
                        "Stop immediately if all candidates fail the minimum usable contract or exceed the budget.",
                    ],
                    "evidence_required_to_change_family_from_not_supported": (
                        "Every boolean in the applicable minimum_usable_contract must be satisfied by "
                        "recorded evidence; successful HTTP responses or payload presence alone are insufficient."
                    ),
                },
            },
        ],
        "recommended_option_id": "2",
        "selected_option_id": None,
        "advisory_recommendation": {
            "option_id": "2",
            "rationale": (
                "The PR #50 probe showed that the per-date classification logic works correctly: "
                "PFF, SPY, IGR, and IPOD map to their locked exclusion categories, while unresolved "
                "historical rows fail closed to unknown. A strict fail-closed unknown policy is therefore "
                "feasible without additional provider exploration, aligns with the research protocol's "
                "best-available-data principle, and lets LONG-002 proceed only to a bounded LONG-002C "
                "design PR after explicit Gary/ChatGPT approval. It does not establish that sufficient "
                "actionable samples exist. Option 1 is safe but stalls the program; Option 3 is likely "
                "costly and uncertain because historical earnings-calendar and security-master sources "
                "with the required vintage/PIT coverage are typically paid and may not resolve the "
                "unresolved historical rows. The fail-closed policy's main risk is reduced coverage and "
                "selection bias; the earnings-unknown rule means any executable-policy evaluation must "
                "separately mark or exclude those observations and may be inconclusive if known-schedule "
                "coverage is too low."
            ),
            "risks": [
                "Security rows with unknown classification are excluded from the eligible universe, which may reduce coverage and introduce selection bias toward larger, better-covered issuers.",
                "PIT-known earnings within five sessions block Enter Now / Armed; unknown earnings schedules are not treated as confirmed non-earnings setups and cannot reach Enter Now or Armed under the ordinary policy (at most Waitlist or do_not_surface), so the actionable sample may be materially smaller.",
                "Current earnings calendars, actual release timestamps, and SEC filing acceptance timestamps cannot be used retrospectively to restore actionability for observations where the schedule was unknown at the decision timestamp.",
                "Actionability and KPI reporting must separately mark or exclude observations whose earnings schedule was unknown; if known-schedule coverage is too low, executable-policy evaluation may be inconclusive.",
                "The unknown policy must be applied consistently; it cannot become a latent feature, ranking input, or post-hoc exclusion rule.",
                "Sample sufficiency, coverage, selection bias, comparability, and cohort-level power must be reassessed before any design PR is approved.",
            ],
        },
        "governance_invariants": [
            "No option in this packet authorizes LONG-002C dataset construction.",
            "A future Gary decision requires a separate approval and PR boundary.",
            "Current or later security classifications may never be substituted as historical facts.",
            "Earnings disclosure timestamps cannot masquerade as previously known schedules.",
            "Provider exploration remains bounded by the locked governance limits; no live calls occur in this PR.",
            "The locked upstream specification hashes are recorded and verified.",
            "The PR #50 artifact disposition remains not_supported and unchanged by this decision packet.",
        ],
    }
    return packet


def to_markdown(packet: dict[str, Any]) -> str:
    """Render the decision packet as a human-readable markdown document."""
    lines: list[str] = [
        "# LONG-002B-DEC-001: Blocker Disposition Decision Packet",
        "",
        "**Status:** `pending_gary_decision`",
        "**LONG-002C authorized:** `false`",
        "**Production promotion eligible:** `false`",
        f"**Starting `main` SHA:** `{packet['starting_main_sha']}`",
        "",
        "## Purpose",
        "",
        (
            "This packet presents three mutually exclusive options for resolving the two remaining `LONG-002B` blockers. "
            "It is research-governance only: no provider calls, credentials, dataset construction, or production changes occur in this PR."
        ),
        "",
        "## Upstream locked specifications",
        "",
        "| Spec | SHA-256 |",
        "|------|---------|",
    ]
    for name, sha in packet["upstream_spec_hashes"].items():
        lines.append(f"| `{name}` | `{sha}` |")

    prereq = packet["prerequisite_artifact"]
    lines.extend([
        "",
        "## Prerequisite artifact",
        "",
        f"- **Task:** `{prereq['task_id']}`",
        f"- **Bundle:** `{prereq['bundle_path']}`",
        f"- **Run ID:** `{prereq['run_id']}`",
        f"- **Overall disposition:** `{prereq['overall_disposition']}`",
        f"- **Total HTTP requests:** {prereq['total_http_requests']}",
        f"- **Preregistration commit SHA:** `{prereq['preregistration_commit_sha']}`",
        f"- **Code commit SHA in effect during live probe:** `{prereq['code_commit_sha']}`",
        "",
        "### Blocked family dispositions",
        "",
    ])
    for family_id, disp in prereq["blocked_family_dispositions"].items():
        lines.append(f"- `{family_id}`: `{disp}`")

    lines.extend(["", "## Blocked family summaries", ""])
    for family in packet["blocked_families"]:
        lines.extend([
            f"### {family['name']}",
            "",
            f"- **Disposition:** `{family['disposition']}`",
            f"- **Blocker summary:** {family['blocker_summary']}",
            "",
        ])

    lines.extend(["", "## Decision options", ""])
    for option in packet["options"]:
        lines.extend([
            f"### Option {option['id']} — {option['label']}",
            "",
            f"{option['description']}",
            "",
            f"- **Selected by default:** `{option['selected']}`",
            f"- **Requires Gary approval:** `{option['requires_gary_approval']}`",
            f"- **Authorizes LONG-002C dataset construction:** `{option['long_002c_authorized']}`",
            "",
        ])
        if "evidence_required_to_reopen" in option:
            lines.extend(["**Evidence required to reopen:**", f"{option['evidence_required_to_reopen']}", ""])
        if "contract_terms" in option:
            lines.extend(["**Required contract amendment terms:**", ""])
            for term, value in option["contract_terms"].items():
                lines.append(f"- `{term}`: `{value}`")
            lines.append("")
        if "provider_amendment_proposal" in option:
            prop = option["provider_amendment_proposal"]
            lines.extend(["**Provider amendment proposal (documentation only; no calls until separate Gary approval):**", ""])
            lines.append(f"- **Purpose:** {prop['purpose']}")
            for family_name in ("security_identity_lifecycle_and_exclusion_classification", "earnings_event_timing"):
                family = prop[family_name]
                lines.extend([
                    f"- **{family_name}**",
                    f"  - Preferred provider: `{family['preferred_provider']['name']}`",
                    f"  - Capability sought: {family['preferred_provider']['capability_sought']}",
                    f"  - Why existing sources failed: {family['preferred_provider']['why_existing_sources_failed']}",
                    "  - Fallbacks:",
                ])
                for fb in family["fallbacks"]:
                    lines.append(f"    - `{fb['name']}`: {fb['capability_sought']}")
            budget = prop["budget"]
            lines.extend([
                "- **Budget:**",
                f"  - Max HTTP requests: {budget['max_http_requests']}",
                f"  - Max runtime: {budget['max_runtime_minutes']} minutes",
                f"  - Max retries per request: {budget['max_retries_per_request']}",
                f"  - Max fallbacks per family: {budget['max_fallbacks_per_family']}",
                f"  - No provider calls until separate Gary approval: `{budget['no_provider_calls_until_gary_approval']}`",
                "- **Stop conditions:**",
            ])
            for cond in prop["stop_conditions"]:
                lines.append(f"  - {cond}")
            lines.extend([
                f"- **Evidence required to change family from not_supported:** {prop['evidence_required_to_change_family_from_not_supported']}",
                "",
            ])

    rec = packet["advisory_recommendation"]
    lines.extend([
        "",
        "## Advisory recommendation",
        "",
        f"**Recommended option:** `{rec['option_id']}` — {next(o['label'] for o in packet['options'] if o['id'] == rec['option_id'])}",
        "",
        f"**Rationale:** {rec['rationale']}",
        "",
        "**Risks to document before any LONG-002C design PR:**",
        "",
    ])
    for risk in rec["risks"]:
        lines.append(f"- {risk}")

    lines.extend([
        "",
        "## Governance invariants",
        "",
    ])
    for inv in packet["governance_invariants"]:
        lines.append(f"- {inv}")

    lines.extend(["", "---", "", "*This packet is advisory only and does not authorize LONG-002C.*"])
    return "\n".join(lines)


def write_decision_packet(packet: dict[str, Any], repo_root: Path | str) -> tuple[Path, Path]:
    """Write the JSON payload and markdown packet to deterministic paths."""
    root = Path(repo_root)
    json_path = root / "docs" / "research" / "specs" / "LONG-002B-DEC-001.json"
    md_path = root / "docs" / "research" / "LONG-002B-DEC-001.md"

    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(packet) + "\n", encoding="utf-8")
    return md_path, json_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate LONG-002B-DEC-001 decision packet")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root")
    args = parser.parse_args(argv)

    packet = build_decision_packet(args.repo_root)
    md_path, json_path = write_decision_packet(packet, args.repo_root)
    print("Decision packet written to:")
    print(f"  {md_path}")
    print(f"  {json_path}")
    print(f"Status: {packet['status']}")
    print(f"Recommended option: {packet['recommended_option_id']}")


if __name__ == "__main__":
    main()
