"""Safe artifact bundle and report writer for INTRA-001B reference probe."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .models import ProviderCandidateResult, ReferenceProbeDecision
from .spec import ReferenceProbeSpec


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


def _unwanted_markers() -> set[str]:
    return {"WARRANT", "RIGHT", "UNIT", "PFD"}


def _security_type_mapping_rows(
    security_type_counts: dict[str, int],
) -> list[dict[str, Any]]:
    unwanted = _unwanted_markers()
    rows = []
    for stype, count in sorted(security_type_counts.items()):
        if stype in unwanted:
            marker = "exclude"
        elif stype in {"CS", "ETF"}:
            marker = "include"
        else:
            marker = "review"
        rows.append(
            {
                "provider_type_value": stype,
                "mapped_category": stype,
                "exclusion_marker": marker,
                "observed_count": count,
            }
        )
    return rows


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
    observations = [obs.to_dict() for obs in candidate_result.observations]

    if observations:
        request_rows = []
        coverage_rows = []
        repeat_rows = []
        for obs in observations:
            request_rows.append(
                {
                    "provider": obs["provider"],
                    "pit_date": obs["pit_date"],
                    "state": obs["state"],
                    "requested_at": obs["requested_at"],
                    "elapsed_seconds": obs["elapsed_seconds"],
                    "http_status": obs["http_status"],
                    "row_count": obs["row_count"],
                    "raw_sha256": obs["raw_sha256"],
                    "repeat_match": obs.get("repeat_match"),
                    "repeat_seconds": obs.get("repeat_seconds"),
                    "repeat_sha256": obs.get("repeat_sha256"),
                }
            )
            coverage_rows.append(
                {
                    "pit_date": obs["pit_date"],
                    "state": obs["state"],
                    "row_count": obs["row_count"],
                    "repeat_match": obs.get("repeat_match"),
                    "raw_sha256": obs["raw_sha256"],
                }
            )
            repeat_rows.append(
                {
                    "provider": obs["provider"],
                    "pit_date": obs["pit_date"],
                    "state": obs["state"],
                    "repeat_match": obs.get("repeat_match"),
                    "raw_sha256": obs["raw_sha256"],
                    "repeat_sha256": obs.get("repeat_sha256"),
                    "repeat_seconds": obs.get("repeat_seconds"),
                }
            )

        _write_csv(out / "request_audit.csv", request_rows)
        files["request_audit.csv"] = _hash_file(out / "request_audit.csv")

        _write_csv(out / "historical_coverage.csv", coverage_rows)
        files["historical_coverage.csv"] = _hash_file(out / "historical_coverage.csv")

        _write_csv(out / "repeatability.csv", repeat_rows)
        files["repeatability.csv"] = _hash_file(out / "repeatability.csv")

    mapping_rows = _security_type_mapping_rows(candidate_result.security_type_counts)
    _write_csv(out / "security_type_mapping.csv", mapping_rows)
    files["security_type_mapping.csv"] = _hash_file(out / "security_type_mapping.csv")

    return files


def _write_readme(out: Path, decision: ReferenceProbeDecision) -> dict[str, str]:
    readme = (
        f"INTRA-001B-REFERENCE safe artifact bundle\n"
        f"Run ID: {out.name}\n"
        f"Task: {decision.task_id}\n"
        f"Provider: {decision.provider or 'none selected'}\n"
        f"Outcome: {decision.outcome}\n"
        f"Dataset used: {decision.dataset_used or 'n/a'}\n"
        f"Pre-registration commit: {decision.v1_pre_registration_commit}\n"
        f"Final head: {decision.final_head}\n"
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
    additional_files: dict[str, bytes] | None = None,
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
        provider_path = out / "provider_candidate_result.json"
        _write_json(provider_path, candidate_result.to_dict())
        files["provider_candidate_result.json"] = _hash_file(provider_path)

        _write_csv(
            out / "observations.csv",
            [obs.to_dict() for obs in candidate_result.observations],
        )
        files["observations.csv"] = _hash_file(out / "observations.csv")

        _write_csv(
            out / "capability_matrix.csv",
            [row.to_dict() for row in candidate_result.capability_rows],
        )
        files["capability_matrix.csv"] = _hash_file(out / "capability_matrix.csv")

        security_rows = [
            {"security_type": k, "count": v} for k, v in candidate_result.security_type_counts.items()
        ]
        _write_csv(out / "security_type_counts.csv", security_rows)
        files["security_type_counts.csv"] = _hash_file(out / "security_type_counts.csv")

        exchange_rows = [
            {"exchange": k, "count": v} for k, v in candidate_result.exchange_counts.items()
        ]
        _write_csv(out / "exchange_counts.csv", exchange_rows)
        files["exchange_counts.csv"] = _hash_file(out / "exchange_counts.csv")

        files.update(_write_audit_files(out, candidate_result))

    report_md = report_markdown or _default_report(decision, candidate_result, spec)
    report_path = out / "report.md"
    report_path.write_text(report_md)
    files["report.md"] = _hash_file(report_path)

    if additional_files:
        for name, data in additional_files.items():
            p = out / name
            p.write_bytes(data)
            files[name] = _hash_file(p)

    manifest_path = out / "artifact_manifest.json"
    _write_json(manifest_path, {"schema_version": spec.safe_artifact_schema_version, "files": files})

    checksum_path = out / "checksums.sha256"
    lines = [f"{h}  {name}\n" for name, h in sorted(files.items())]
    checksum_path.write_text("".join(lines))

    return out


def _default_report(
    decision: ReferenceProbeDecision,
    candidate: ProviderCandidateResult | None,
    spec: ReferenceProbeSpec,
) -> str:
    lines = [
        "# INTRA-001B-REFERENCE Reference Provider Probe Report",
        "",
        f"- **Task ID:** {decision.task_id}",
        f"- **Probe version:** {decision.probe_version}",
        f"- **Provider:** {decision.provider or 'none selected'}",
        f"- **Outcome:** {decision.outcome}",
        f"- **Approved as reference provider:** {decision.approved_as_reference_provider}",
        f"- **Reason:** {decision.reason}",
        f"- **Candidate order:** {', '.join(decision.candidate_order)}",
        f"- **Pre-registration commit:** {decision.v1_pre_registration_commit}",
        f"- **Final head:** {decision.final_head}",
        f"- **Branch:** {decision.branch}",
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
    lines.append("## Decision gates")
    lines.append("")
    lines.append("| Gate | Passed |")
    lines.append("|------|--------|")
    lines.append(f"| PIT date support | {decision.pit_date_support} |")
    lines.append(f"| Active/delisted coverage | {decision.active_delisted_coverage} |")
    lines.append(f"| Security-type exclusions possible | {decision.security_type_exclusions_possible} |")
    lines.append(f"| Security-type taxonomy granular | {decision.security_type_taxonomy_granular} |")
    lines.append(f"| Primary exchange provenance | {decision.primary_exchange_provenance} |")
    lines.append(f"| Reproducible | {decision.reproducible} |")
    lines.append(f"| Free under current entitlement | {decision.free_under_current_entitlement} |")
    lines.append(f"| Full repeatability passed | {decision.full_repeatability_passed} |")
    lines.append("")

    if decision.dataset_used:
        lines.append(f"- **Dataset used:** {decision.dataset_used}")
        lines.append("")

    if decision.candidate_dispositions:
        lines.append("## Candidate dispositions")
        lines.append("")
        for name, reason in decision.candidate_dispositions:
            lines.append(f"- **{name}:** {reason}")
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
