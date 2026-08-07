"""Safe artifact bundle and report writer for INTRA-001B-REFERENCE-V3."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .models import ProviderCandidateResult, ReferenceProbeDecision
from .spec import ReferenceProbeSpec

EXPECTED_SAFE_ARTIFACTS = (
    "README.txt",
    "artifact_manifest.json",
    "checksums.sha256",
    "probe_spec.lock.json",
    "strategy_spec_reference.json",
    "alpaca_v2_reference.json",
    "request_audit.csv",
    "provider_capability_matrix.csv",
    "security_type_mapping.csv",
    "security_type_taxonomy.csv",
    "historical_coverage.csv",
    "pagination_audit.csv",
    "repeatability.csv",
    "decision.json",
    "report.md",
)


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = sorted(rows[0].keys())
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fieldnames})


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_run_id() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")


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


def _security_type_mapping_rows(
    result: ProviderCandidateResult,
) -> list[dict[str, Any]]:
    rows = []
    if result.taxonomy_mapping:
        for stype, category in sorted(result.taxonomy_mapping.items()):
            if category == "common_stock":
                marker = "include"
            elif category in {"etf", "preferred_stock", "warrant", "right", "unit", "otc", "unknown", "other"}:
                marker = "exclude"
            else:
                marker = "review"
            rows.append({
                "provider_type_value": stype,
                "mapped_category": category,
                "exclusion_marker": marker,
                "observed_count": result.security_type_counts.get(stype, 0),
            })
    else:
        for stype, count in sorted(result.security_type_counts.items()):
            category = _map_alpha_asset_type(stype)
            if category == "common_stock":
                marker = "include"
            elif category in {"etf", "preferred_stock", "warrant", "right", "unit", "otc", "unknown", "other"}:
                marker = "exclude"
            else:
                marker = "review"
            rows.append({
                "provider_type_value": stype,
                "mapped_category": category,
                "exclusion_marker": marker,
                "observed_count": count,
            })
    return rows


def _security_type_taxonomy_rows(
    result: ProviderCandidateResult,
) -> list[dict[str, Any]]:
    if result.ticker_types:
        rows = []
        for entry in result.ticker_types:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("code") or "").strip().upper()
            if not code:
                continue
            category = result.taxonomy_mapping.get(code, "unknown")
            rows.append({
                "provider_code": code,
                "provider_description": str(entry.get("description") or "").strip(),
                "provider_asset_class": str(entry.get("asset_class") or "").strip(),
                "provider_locale": str(entry.get("locale") or "").strip(),
                "tradex_category": category,
                "eligible_stock": category == "common_stock",
            })
        return rows
    if result.taxonomy_mapping:
        return [
            {
                "provider_code": code,
                "provider_description": code,
                "provider_asset_class": "stocks",
                "provider_locale": "us",
                "tradex_category": category,
                "eligible_stock": category == "common_stock",
            }
            for code, category in sorted(result.taxonomy_mapping.items())
        ]
    return []


def _request_audit_rows(result: ProviderCandidateResult) -> list[dict[str, Any]]:
    rows = []
    for obs in result.observations:
        rows.append({
            "provider": obs.provider,
            "pit_date": obs.pit_date,
            "state": obs.state,
            "requested_at": obs.requested_at,
            "elapsed_seconds": obs.elapsed_seconds,
            "http_status": obs.http_status,
            "row_count": obs.row_count,
            "page_count": obs.page_count,
            "pagination_complete": obs.pagination_complete,
            "max_pages_reached": obs.max_pages_reached,
            "raw_sha256": obs.raw_sha256,
            "full_snapshot_sha256": obs.full_snapshot_sha256 or "",
            "repeat_match": obs.repeat_match,
            "repeat_sha256": obs.repeat_sha256 or "",
            "error": obs.error or "",
        })
    return rows


def _historical_coverage_rows(result: ProviderCandidateResult) -> list[dict[str, Any]]:
    seen = set()
    rows = []
    for obs in result.observations:
        key = (obs.pit_date, obs.state)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "pit_date": obs.pit_date,
            "state": obs.state,
            "row_count": obs.row_count,
            "canonical_ticker_count": obs.canonical_ticker_count,
            "pagination_complete": obs.pagination_complete,
            "full_snapshot_sha256": obs.full_snapshot_sha256 or "",
        })
    return rows


def _repeatability_rows(result: ProviderCandidateResult) -> list[dict[str, Any]]:
    rows = []
    for obs in result.observations:
        if obs.repeat_match is None:
            continue
        rows.append({
            "provider": obs.provider,
            "pit_date": obs.pit_date,
            "state": obs.state,
            "repeat_match": obs.repeat_match,
            "raw_sha256": obs.raw_sha256,
            "repeat_sha256": obs.repeat_sha256 or "",
            "repeat_seconds": obs.repeat_seconds,
        })
    return rows


def _pagination_audit_rows(result: ProviderCandidateResult) -> list[dict[str, Any]]:
    return [page.to_dict() for page in result.pagination_pages]


def _capability_matrix_rows(result: ProviderCandidateResult) -> list[dict[str, Any]]:
    return [row.to_dict() for row in result.capability_rows]


def _write_reference_files(out: Path, spec: ReferenceProbeSpec) -> dict[str, str]:
    files: dict[str, str] = {}
    original_spec = Path(spec.original_strategy_spec_path)
    if original_spec.exists():
        ref = {
            "original_strategy_spec_path": spec.original_strategy_spec_path,
            "sha256": _hash_file(original_spec),
        }
        p = out / "strategy_spec_reference.json"
        _write_json(p, ref)
        files["strategy_spec_reference.json"] = _hash_file(p)

    alpaca_path = Path(spec.alpaca_v2_artifact_path) if spec.alpaca_v2_artifact_path else None
    if alpaca_path and alpaca_path.exists():
        ref = {
            "artifact_path": str(alpaca_path.relative_to(Path.cwd()) if Path.cwd() in alpaca_path.parents else alpaca_path),
            "sha256": _hash_file(alpaca_path),
        }
        p = out / "alpaca_v2_reference.json"
        _write_json(p, ref)
        files["alpaca_v2_reference.json"] = _hash_file(p)
    return files


def _write_audit_files(out: Path, candidate_result: ProviderCandidateResult) -> dict[str, str]:
    files: dict[str, str] = {}

    request_rows = _request_audit_rows(candidate_result)
    _write_csv(out / "request_audit.csv", request_rows)
    files["request_audit.csv"] = _hash_file(out / "request_audit.csv")

    coverage_rows = _historical_coverage_rows(candidate_result)
    _write_csv(out / "historical_coverage.csv", coverage_rows)
    files["historical_coverage.csv"] = _hash_file(out / "historical_coverage.csv")

    repeat_rows = _repeatability_rows(candidate_result)
    _write_csv(out / "repeatability.csv", repeat_rows)
    files["repeatability.csv"] = _hash_file(out / "repeatability.csv")

    pagination_rows = _pagination_audit_rows(candidate_result)
    _write_csv(out / "pagination_audit.csv", pagination_rows)
    files["pagination_audit.csv"] = _hash_file(out / "pagination_audit.csv")

    capability_rows = _capability_matrix_rows(candidate_result)
    _write_csv(out / "provider_capability_matrix.csv", capability_rows)
    files["provider_capability_matrix.csv"] = _hash_file(out / "provider_capability_matrix.csv")

    mapping_rows = _security_type_mapping_rows(candidate_result)
    _write_csv(out / "security_type_mapping.csv", mapping_rows)
    files["security_type_mapping.csv"] = _hash_file(out / "security_type_mapping.csv")

    taxonomy_rows = _security_type_taxonomy_rows(candidate_result)
    _write_csv(out / "security_type_taxonomy.csv", taxonomy_rows)
    files["security_type_taxonomy.csv"] = _hash_file(out / "security_type_taxonomy.csv")

    return files


def _write_readme(out: Path, decision: ReferenceProbeDecision) -> dict[str, str]:
    readme = (
        f"INTRA-001B-REFERENCE-V3 safe artifact bundle\n"
        f"Run ID: {out.name}\n"
        f"Task: {decision.task_id}\n"
        f"Provider: {decision.provider or 'none selected'}\n"
        f"Outcome: {decision.outcome}\n"
        f"Dataset used: {decision.dataset_used or 'n/a'}\n"
        f"v1 pre-registration commit: {decision.v1_pre_registration_commit or 'n/a'}\n"
        f"v2 pre-registration commit: {decision.v2_pre_registration_commit or 'n/a'}\n"
        f"v3 pre-registration commit: {decision.v3_pre_registration_commit or 'n/a'}\n"
        f"Final head: {decision.final_pr_head or decision.live_run_head or 'n/a'}\n"
        f"Branch: {decision.branch}\n"
        f"Ran at: {decision.ran_at}\n\n"
        "This bundle contains research-only audit artifacts for the reference-provider probe.\n"
        "It does not authorize production changes.\n"
    )
    p = out / "README.txt"
    p.write_text(readme)
    return {"README.txt": _hash_file(p)}


def write_reference_probe_artifacts(
    spec: ReferenceProbeSpec,
    decision: ReferenceProbeDecision,
    candidate_result: ProviderCandidateResult | None,
    output_dir: str | Path,
    *,
    probe_spec_raw: bytes,
    report_markdown: str | None = None,
) -> Path:
    """Write the locked safe artifact bundle and return the bundle directory."""
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    # Clean stale manifest/checksum files so they are always regenerated.
    for stale in (out / "artifact_manifest.json", out / "checksums.sha256"):
        if stale.exists():
            stale.unlink()

    files: dict[str, str] = {}
    files.update(_write_readme(out, decision))
    files.update(_write_reference_files(out, spec))

    probe_lock = out / "probe_spec.lock.json"
    probe_lock.write_bytes(probe_spec_raw)
    files["probe_spec.lock.json"] = _hash_file(probe_lock)

    decision_path = out / "decision.json"
    _write_json(decision_path, decision.to_dict())
    files["decision.json"] = _hash_file(decision_path)

    if candidate_result is not None:
        files.update(_write_audit_files(out, candidate_result))

    report_md = report_markdown or _default_report(decision, candidate_result, spec)
    report_path = out / "report.md"
    report_path.write_text(report_md)
    files["report.md"] = _hash_file(report_path)

    # Manifest lists all safe artifacts except itself.
    manifest_path = out / "artifact_manifest.json"
    _write_json(manifest_path, {"schema_version": spec.safe_artifact_schema_version, "files": dict(sorted(files.items()))})
    files["artifact_manifest.json"] = _hash_file(manifest_path)

    # Checksum lists all safe artifacts except itself.
    checksum_path = out / "checksums.sha256"
    lines = [f"{h}  {name}\n" for name, h in sorted(files.items())]
    checksum_path.write_text("".join(lines))
    files["checksums.sha256"] = _hash_file(checksum_path)

    # Enforce exact safe-artifact contract.
    actual = set(files.keys())
    expected = set(EXPECTED_SAFE_ARTIFACTS)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        raise RuntimeError(f"Safe artifact contract violation: missing={sorted(missing)} extra={sorted(extra)}")

    return out


def _default_report(
    decision: ReferenceProbeDecision,
    candidate: ProviderCandidateResult | None,
    spec: ReferenceProbeSpec,
) -> str:
    lines = [
        "# INTRA-001B-REFERENCE-V3 Reference Provider Probe Report",
        "",
        f"- **Task ID:** {decision.task_id}",
        f"- **Probe version:** {decision.probe_version}",
        f"- **Provider:** {decision.provider or 'none selected'}",
        f"- **Outcome:** {decision.outcome}",
        f"- **Approved as reference provider:** {decision.approved_as_reference_provider}",
        f"- **Reason:** {decision.reason}",
        f"- **Candidate order:** {', '.join(decision.candidate_order)}",
        f"- **Starting main SHA:** {decision.starting_main_sha}",
        f"- **Branch:** {decision.branch}",
        f"- **Live run head:** {decision.live_run_head}",
        f"- **Final PR head:** {decision.final_pr_head or 'n/a'}",
        f"- **v1 pre-registration commit:** {decision.v1_pre_registration_commit}",
        f"- **v2 pre-registration commit:** {decision.v2_pre_registration_commit}",
        f"- **v3 pre-registration commit:** {decision.v3_pre_registration_commit}",
        f"- **Ran at:** {decision.ran_at}",
        "",
        "## Locked methodology",
        "",
        f"- Original strategy spec: `{spec.original_strategy_spec_path}`",
        f"- Original spec SHA-256: `{spec.expected_original_strategy_spec_sha256}`",
        f"- Amendment: `{spec.amendment_path}`",
        f"- No paid upgrade: `{spec.no_paid_upgrade}`",
        f"- No composite reference stack: `{spec.no_composite_reference_stack}`",
        "",
        "## Probe dates",
        "",
    ]
    for d in decision.pit_dates:
        lines.append(f"- {d}")
    lines.append("")
    if decision.fallback_probe_dates:
        lines.append("## Fallback probe dates")
        lines.append("")
        for d in decision.fallback_probe_dates:
            lines.append(f"- {d}")
        lines.append("")
    lines.append("## Decision gates")
    lines.append("")
    lines.append("| Gate | Passed |")
    lines.append("|------|--------|")
    gate_names = [
        "pit_date_support_for_all_probe_dates",
        "active_state_complete",
        "inactive_or_delisted_state_complete",
        "pagination_exhausted_to_terminal",
        "no_pagination_cycles_or_repeated_cursors",
        "exact_historical_date_semantics",
        "common_stock_classification",
        "etf_classification",
        "warrant_exclusion",
        "right_exclusion",
        "unit_exclusion",
        "preferred_stock_exclusion",
        "otc_exclusion",
        "primary_listing_provenance",
        "symbol_presence_and_determinism",
        "lifecycle_evidence",
        "duplicate_symbol_behavior_and_resolution",
        "repeatability",
        "hashability",
        "no_present_day_reconstruction",
        "historical_2022_entitlement_under_current_plan",
        "feasible_for_all_48_monthly_pit_snapshots",
    ]
    for name in gate_names:
        value = getattr(decision, name, False)
        lines.append(f"| {name} | {value} |")
    lines.append(f"| **All mandatory gates passed** | {decision.all_mandatory_gates_passed} |")
    lines.append("")

    if decision.dataset_used:
        lines.append(f"- **Dataset used:** {decision.dataset_used}")
        lines.append("")

    if decision.candidate_dispositions:
        lines.append("## Candidate dispositions")
        lines.append("")
        for disp in decision.candidate_dispositions:
            d = disp if isinstance(disp, dict) else disp.to_dict()
            lines.append(f"- **{d['provider']}** ({d['dataset']}): {d['disposition']} — {d['reason']}")
        lines.append("")

    if candidate is not None:
        lines.append("## Provider candidate summary")
        lines.append("")
        lines.append(f"- **Provider:** {candidate.provider}")
        lines.append(f"- **Target entitlement:** {candidate.target_entitlement}")
        if candidate.primary_exchange_field:
            lines.append(f"- **Primary exchange field:** {candidate.primary_exchange_field}")
        if candidate.security_type_field:
            lines.append(f"- **Security type field:** {candidate.security_type_field}")
        if candidate.delisting_date_field:
            lines.append(f"- **Delisting date field:** {candidate.delisting_date_field}")
        if candidate.listing_date_field:
            lines.append(f"- **Listing date field:** {candidate.listing_date_field}")
        lines.append("")
        if candidate.error:
            lines.append(f"**Errors:** {candidate.error}")
            lines.append("")
        lines.append("### Security type counts")
        lines.append("")
        for k, v in sorted(candidate.security_type_counts.items()):
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("### Exchange counts")
        lines.append("")
        for k, v in sorted(candidate.exchange_counts.items()):
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("### Pagination summary")
        lines.append("")
        lines.append(f"- Max active pages: {candidate.max_pages_active}")
        lines.append(f"- Max inactive pages: {candidate.max_pages_inactive}")
        if candidate.estimated_http_calls_48_months:
            lines.append(f"- Estimated HTTP calls for 48 monthly snapshots: {candidate.estimated_http_calls_48_months}")
        if candidate.estimated_collection_time_48_months_seconds:
            lines.append(f"- Estimated collection time (seconds): {candidate.estimated_collection_time_48_months_seconds:,.0f}")
        lines.append("")
        lines.append("## Capability matrix")
        lines.append("")
        lines.append("| Capability | Supported | Evidence class | Note |")
        lines.append("|------------|-----------|----------------|------|")
        for row in candidate.capability_rows:
            note = (row.note or "").replace("|", "\\|")
            lines.append(f"| {row.capability} | {row.supported} | {row.evidence_class} | {note} |")
        lines.append("")

    lines.append("---")
    lines.append("This report is a research artifact only. It does not authorize production changes.")
    return "\n".join(lines) + "\n"
