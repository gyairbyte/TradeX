"""Safe-artifact writer for LONG-002B feasibility reports."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import FeasibilityReport


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8")


def write_safe_artifacts(
    report: FeasibilityReport,
    repo_root: Path | str,
    *,
    run_id: str | None = None,
    code_commit_sha: str = "",
) -> Path:
    """Write the LONG-002B safe artifact bundle and return the bundle directory."""
    root = Path(repo_root)
    run_id = run_id or _now_utc()
    bundle = root / "docs" / "research" / "artifacts" / "LONG-002B" / run_id
    bundle.mkdir(parents=True, exist_ok=True)

    report.code_commit_sha = code_commit_sha
    manifest: dict[str, Any] = {
        "task_id": report.task_id,
        "run_id": run_id,
        "bundle_path": str(bundle.relative_to(root)),
        "generated_at": _now_utc(),
        "code_commit_sha": code_commit_sha,
        "long_002_spec_sha256": report.long_002_spec_sha256,
        "probe_spec_sha256": report.probe_spec_sha256,
        "data_contract_sha256": report.data_contract_sha256,
        "overall_disposition": report.overall_disposition,
        "overall_evidence_confidence": report.overall_evidence_confidence,
        "total_http_requests": report.total_http_requests,
        "runtime_seconds": report.runtime_seconds,
        "files": {},
    }

    # Main report
    report_path = bundle / "feasibility_report.json"
    report_bytes = _json_bytes(report.to_dict())
    report_path.write_bytes(report_bytes)
    manifest["files"]["feasibility_report.json"] = hashlib.sha256(report_bytes).hexdigest()

    # Provider contract matrix
    contract_rows = []
    for family in report.data_families:
        for record in family.records:
            contract_rows.append({
                "family": record.family,
                "provider": record.provider,
                "symbol": record.symbol,
                "as_of_date": record.as_of_date,
                "endpoint_pattern": record.endpoint_pattern,
                "http_status": record.http_status,
                "error_classification": record.error_classification,
                "retry_count": record.retry_count,
                "request_timestamp_utc": record.request_timestamp_utc,
            })
    contract_path = bundle / "provider_contract_matrix.csv"
    _write_csv(contract_path, contract_rows)
    manifest["files"]["provider_contract_matrix.csv"] = sha256_of_file(contract_path)

    # Coverage summary
    coverage_rows = []
    for family in report.data_families:
        coverage_rows.append({
            "family": family.family,
            "disposition": family.disposition,
            "evidence_confidence": family.evidence_confidence,
            "provider_selected": family.provider_selected,
            "provider_role": family.provider_role,
            "request_count": family.request_count,
            "blockers": "; ".join(family.blockers),
            "limitations": "; ".join(family.limitations),
        })
    coverage_path = bundle / "coverage_summary.csv"
    _write_csv(coverage_path, coverage_rows)
    manifest["files"]["coverage_summary.csv"] = sha256_of_file(coverage_path)

    # Data quality summary
    quality_rows = []
    for family in report.data_families:
        quality_rows.append({
            "family": family.family,
            "total_records": len(family.records),
            "successful_requests": sum(1 for r in family.records if r.error_classification == "none"),
            "auth_failures": sum(1 for r in family.records if r.error_classification == "authentication"),
            "transient_failures": sum(1 for r in family.records if r.error_classification == "transient"),
            "response_failures": sum(1 for r in family.records if r.error_classification == "response"),
            "unsupported_failures": sum(1 for r in family.records if r.error_classification == "unsupported_capability"),
        })
    quality_path = bundle / "data_quality_summary.csv"
    _write_csv(quality_path, quality_rows)
    manifest["files"]["data_quality_summary.csv"] = sha256_of_file(quality_path)

    manifest_path = bundle / "artifact_manifest.json"
    manifest_bytes = _json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    # Checksums file
    checksums_path = bundle / "checksums.sha256"
    lines = [f"{sha}  {name}" for name, sha in manifest["files"].items()]
    lines.append(f"{hashlib.sha256(manifest_bytes).hexdigest()}  artifact_manifest.json")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return bundle


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
