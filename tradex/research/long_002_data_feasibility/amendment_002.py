"""LONG-002B-AMEND-002: Option 2 fail-closed unknown policy selection record.

This module records Gary's selection of Option 2 from the LONG-002B-DEC-001
decision packet and locks the contract amendment that must govern all later
LONG-002C design work. It performs no provider calls and uses no credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

# Merge commit of PR #51 (LONG-002B-DEC-001) on main.
STARTING_MAIN_SHA = "f6413a2ba66859a78c536242fa787d1cdf204eb2"

# Upstream locked specifications whose hashes are recorded.
UPSTREAM_SPEC_PATHS: dict[str, str] = {
    "LONG-002-v1.json": "docs/research/specs/LONG-002-v1.json",
    "LONG-002B-probe-v1.json": "docs/research/specs/LONG-002B-probe-v1.json",
    "LONG-002B-data-contract-v1.json": "docs/research/specs/LONG-002B-data-contract-v1.json",
    "LONG-002B-AMEND-001-probe-v1.json": "docs/research/specs/LONG-002B-AMEND-001-probe-v1.json",
}

# Merged decision packet from PR #51.
DECISION_PACKET_MD = "docs/research/LONG-002B-DEC-001.md"
DECISION_PACKET_JSON = "docs/research/specs/LONG-002B-DEC-001.json"

# Prior amendment artifact (PR #50).
AMEND_001_BUNDLE = "docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_upstream_specs(repo_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, rel_path in UPSTREAM_SPEC_PATHS.items():
        path = repo_root / rel_path
        if not path.exists():
            raise FileNotFoundError(f"Locked spec missing: {path}")
        hashes[name] = _sha256(path)
    return hashes


def _load_decision_packet(repo_root: Path) -> dict[str, Any]:
    path = repo_root / DECISION_PACKET_JSON
    if not path.exists():
        raise FileNotFoundError(f"Decision packet missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_amendment_001_artifact(repo_root: Path) -> dict[str, Any]:
    bundle = repo_root / AMEND_001_BUNDLE
    manifest_path = bundle / "artifact_manifest.json"
    report_path = bundle / "feasibility_report.json"
    if not manifest_path.exists() or not report_path.exists():
        raise FileNotFoundError(f"PR #50 artifact bundle missing: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "bundle_path": str(bundle.relative_to(repo_root)),
        "run_id": manifest.get("run_id"),
        "overall_disposition": report.get("overall_disposition"),
        "manifest_sha256": _sha256(manifest_path),
        "report_sha256": _sha256(report_path),
    }


def build_selection_record(repo_root: Path | str) -> dict[str, Any]:
    """Return the LONG-002B-AMEND-002 selection record as a JSON-safe dict."""
    root = Path(repo_root)
    spec_hashes = _verify_upstream_specs(root)
    decision_packet = _load_decision_packet(root)
    amend_001_artifact = _load_amendment_001_artifact(root)

    # Preserve prior feasibility findings; do not rewrite them.
    if decision_packet.get("status") != "pending_gary_decision":
        raise RuntimeError("Decision packet status must be pending_gary_decision before selection")
    if decision_packet.get("long_002c_authorized") is not False:
        raise RuntimeError("Decision packet must not have authorized LONG-002C")
    option_2 = next((o for o in decision_packet.get("options", []) if o.get("id") == "2"), None)
    if option_2 is None:
        raise RuntimeError("Option 2 not found in decision packet")
    if not option_2.get("requires_gary_approval"):
        raise RuntimeError("Option 2 must require Gary approval")

    decision_md_hash = _sha256(root / DECISION_PACKET_MD)
    decision_json_hash = _sha256(root / DECISION_PACKET_JSON)

    record: dict[str, Any] = {
        "schema_version": "1.0",
        "amendment_id": "LONG-002B-AMEND-002",
        "task_id": "LONG-002",
        "classification": "research-governance-only",
        "status": "gary_approved",
        "selected_option_id": "2",
        "selected_option_label": option_2["label"],
        "gary_approval_source": "GitHub PR #51 review/selection (merge commit f6413a2ba66859a78c536242fa787d1cdf204eb2)",
        "fail_closed_unknown_policy_approved": True,
        "long_002c_design_pr_authorized": True,
        "long_002c_dataset_construction_authorized": False,
        "production_promotion_eligible": False,
        "starting_main_sha": STARTING_MAIN_SHA,
        "pr_51_merge_commit": STARTING_MAIN_SHA,
        "authorization_boundary": (
            "This amendment authorizes only a separate LONG-002C design/specification PR. "
            "It does not authorize LONG-002C dataset construction, implementation, provider calls, "
            "historical outcome analysis, model fitting, validation/holdout access, or any production change."
        ),
        "upstream_spec_hashes": spec_hashes,
        "decision_packet_reference": {
            "markdown_path": DECISION_PACKET_MD,
            "markdown_sha256": decision_md_hash,
            "json_path": DECISION_PACKET_JSON,
            "json_sha256": decision_json_hash,
            "selected_option_recommendation": decision_packet.get("advisory_recommendation", {}).get("option_id"),
        },
        "amendment_001_artifact_reference": amend_001_artifact,
        "locked_security_policy": {
            "per_date_classification": (
                "Every security classification is evaluated independently for its historical "
                "(symbol, as_of_date)."
            ),
            "no_backfill": "Current or later classifications never backfill historical facts.",
            "unknown_not_common_stock": "Unknown security classification is never treated as common stock.",
            "unknown_excluded_from_universe": (
                "A row without defensible PIT classification is excluded from the eligible universe."
            ),
            "locked_exclusions_apply": (
                "ETFs, ETNs, closed-end funds, preferreds, warrants, rights, units, OTC securities, "
                "pre-merger SPACs/shells, and structurally incomparable securities retain their locked treatment."
            ),
            "measure_selection_bias": (
                "Exclusion coverage, cohort selection bias, comparability, and sample sufficiency must be "
                "measured during later authorized work."
            ),
            "coverage_failure_inconclusive": (
                "Coverage failure may make later research inconclusive; thresholds may not be weakened "
                "after results are observed."
            ),
        },
        "locked_earnings_policy": {
            "schedule_unknown_when_unavailable": (
                "When a historical PIT earnings schedule is unavailable, the schedule remains unknown."
            ),
            "no_confirmed_non_earnings": (
                "The observation cannot be labeled a confirmed non-earnings setup."
            ),
            "no_enter_now_or_armed": (
                "Under the ordinary policy it cannot reach Enter Now or Armed."
            ),
            "maximum_actionable_state": (
                "Its maximum possible presentation is Waitlist or do_not_surface, with the exact "
                "presentation choice deferred to the separately approved LONG-002C design."
            ),
            "no_retrospective_proxies": (
                "Current calendars, SEC filing timestamps, actual earnings-release dates, or "
                "later-reconstructed dates cannot retrospectively restore actionability."
            ),
            "no_feature_or_ranking_use": (
                "Unknown earnings timing cannot become a feature, ranking input, implicit absence indicator, "
                "zero value, or post-hoc exclusion."
            ),
            "actionability_and_kpi_marked_unavailable": (
                "Actionability and KPI reporting must mark affected observations unavailable and report "
                "known-schedule coverage separately."
            ),
            "insufficient_coverage_inconclusive": (
                "Insufficient known-schedule coverage makes executable-policy evaluation inconclusive."
            ),
            "no_weakening_for_sample_size": (
                "Later phases may not weaken this rule to recover sample size or improve performance."
            ),
        },
        "governance_invariants": [
            "Option 2 is explicitly selected and Gary-approved; Options 1 and 3 are not selected or authorized.",
            "Prior not_supported feasibility findings from LONG-002B and LONG-002B-AMEND-001 remain unchanged.",
            "Security unknowns are excluded rather than treated as eligible common stock.",
            "Current or later security classifications may never be backfilled as historical facts.",
            "Earnings unknowns cannot be confirmed as non-earnings setups.",
            "Earnings unknowns cannot reach Enter Now or Armed under the ordinary policy.",
            "No retrospective earnings proxy can restore actionability.",
            "Unknown earnings observations are unavailable for actionability/KPI evaluation.",
            "Insufficient schedule coverage produces an inconclusive result rather than a relaxed gate.",
            "Only a LONG-002C design PR is authorized; dataset construction, provider calls, outcome analysis, and production promotion remain unauthorized.",
            "All referenced upstream specification hashes remain unchanged.",
        ],
    }
    return record


def to_markdown(record: dict[str, Any]) -> str:
    """Render the selection record as a human-readable markdown document."""
    lines: list[str] = [
        "# LONG-002B-AMEND-002: Option 2 — Fail-closed unknown policy selection",
        "",
        "**Amendment:** `LONG-002B-AMEND-002`",
        "**Selection source:** Gary/ChatGPT selection from `LONG-002B-DEC-001`",
        "**PR #51 merge commit:** `{}`".format(record["pr_51_merge_commit"]),
        "**Starting `main` SHA:** `{}`".format(record["starting_main_sha"]),
        "**Decision status:** `gary_approved`",
        "**Selected option:** `{}` — {}".format(record["selected_option_id"], record["selected_option_label"]),
        "**Fail-closed unknown policy approved:** `true`",
        "**LONG-002C design PR authorized:** `true`",
        "**LONG-002C dataset construction authorized:** `false`",
        "**Production promotion eligible:** `false`",
        "",
        "## Authorization boundary",
        "",
        record["authorization_boundary"],
        "",
        "## Upstream locked specification hashes",
        "",
        "| Spec | SHA-256 |",
        "|------|---------|",
    ]
    for name, sha in record["upstream_spec_hashes"].items():
        lines.append(f"| `{name}` | `{sha}` |")

    dec = record["decision_packet_reference"]
    lines.extend([
        "",
        "## Decision packet reference (PR #51)",
        "",
        f"- **Markdown:** `{dec['markdown_path']}` — `{dec['markdown_sha256']}`",
        f"- **JSON:** `{dec['json_path']}` — `{dec['json_sha256']}`",
        f"- **Advisory recommendation in packet:** Option {dec['selected_option_recommendation']}",
        "",
        "## LONG-002B-AMEND-001 artifact reference (PR #50)",
        "",
        f"- **Bundle:** `{record['amendment_001_artifact_reference']['bundle_path']}`",
        f"- **Run ID:** `{record['amendment_001_artifact_reference']['run_id']}`",
        f"- **Overall disposition:** `{record['amendment_001_artifact_reference']['overall_disposition']}`",
        f"- **Manifest SHA-256:** `{record['amendment_001_artifact_reference']['manifest_sha256']}`",
        f"- **Feasibility report SHA-256:** `{record['amendment_001_artifact_reference']['report_sha256']}`",
        "",
        "## Locked security policy",
        "",
    ])
    for key, value in record["locked_security_policy"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")

    lines.extend(["", "## Locked earnings policy", ""])
    for key, value in record["locked_earnings_policy"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")

    lines.extend(["", "## Governance invariants", ""])
    for inv in record["governance_invariants"]:
        lines.append(f"- {inv}")

    lines.extend(["", "---", "", "*This amendment is a versioned overlay; prior locked specifications and artifacts are referenced by hash and not modified.*"])
    return "\n".join(lines)


def write_selection_record(record: dict[str, Any], repo_root: Path | str) -> tuple[Path, Path]:
    """Write the JSON selection record and markdown amendment to deterministic paths."""
    root = Path(repo_root)
    json_path = root / "docs" / "research" / "specs" / "LONG-002B-AMEND-002.json"
    md_path = root / "docs" / "research" / "LONG-002B-AMEND-002.md"

    json_path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(record) + "\n", encoding="utf-8")
    return md_path, json_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate LONG-002B-AMEND-002 selection record")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root")
    args = parser.parse_args(argv)

    record = build_selection_record(args.repo_root)
    md_path, json_path = write_selection_record(record, args.repo_root)
    print("Selection record written to:")
    print(f"  {md_path}")
    print(f"  {json_path}")
    print(f"Status: {record['status']}")
    print(f"Selected option: {record['selected_option_id']}")


if __name__ == "__main__":
    main()
