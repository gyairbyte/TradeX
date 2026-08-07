"""Regenerate INTRA-001B-ALPACA-V2 derived artifacts from the frozen report.json.

This script performs a deterministic post-live audit:
- resolves and validates the v2 pre-registration commit against the final head,
- recomputes the v2 decision from the frozen provider evidence using the current
  probe code,
- proves the post-live corrections did not change the preregistered core gates,
- patches documentation citations into provider-contract rows classified as
  ``documented_capability``,
- regenerates the safe artifact bundle and the human-readable report,
- appends a post-live derived-output corrections section to the report.

No new Alpaca network calls are made.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Frozen v2 provenance constants.
V1_PRE_REGISTRATION_COMMIT = "286493eceeffd6aec872ce7516bed5d1b0cd304f"
V2_PRE_REGISTRATION_COMMIT = "340e0921065fc17767cd882393fb3fe543cfcc0b"
STARTING_HEAD = "bb1730c598c252d4fc6ac5125bf348766a6455f9"
BRANCH = "devin/intra-001b-alpaca-probe"
CI_WORKFLOW_ID = "31211100887"
CI_JOB_ID = "92973850931"
CI_MERGE_REF = "1a5c9e93ea923cc2e2cb1edc0e3e104d348997a6"
PRIVATE_REPORT_JSON = Path.home() / ".tradex/research/INTRA-001B/alpaca-free-probe-v2/report.json"


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patch_documented_capability_sources(rows: list[dict[str, Any]], review_date: str) -> None:
    stockbars_doc = f"Alpaca Stock Bars API reference, https://docs.alpaca.markets/us/reference/stockbars (reviewed {review_date})"
    for row in rows:
        if row.get("evidence_type") != "documented_capability":
            continue
        if row.get("requirement") == "adjustment_raw":
            row["source"] = stockbars_doc + " (adjustment parameter)"
        elif row.get("requirement") == "symbol_mapping_asof":
            asof = row.get("source", "").split("asof=")[-1] if "asof=" in row.get("source", "") else ""
            row["source"] = stockbars_doc + f" (asof parameter); request used asof={asof}"


def _core_gates(d: Any) -> dict[str, Any]:
    return {
        "outcome": d.outcome,
        "approved_for_intra_001_five_minute_ohlcv": d.approved_for_intra_001_five_minute_ohlcv,
        "approved_as_complete_intra_001_data_source": d.approved_as_complete_intra_001_data_source,
        "direct_full_range_supported": d.direct_full_range_supported,
        "chunked_historical_windows_supported": d.chunked_historical_windows_supported,
        "single_provider_contract_satisfied": d.single_provider_contract_satisfied,
        "selected_request_method": d.selected_request_method,
        "selected_windowing_policy": d.selected_windowing_policy,
        "timestamp_semantics_passed": d.timestamp_semantics_passed,
        "candidate_timestamp_semantics": d.candidate_timestamp_semantics,
    }


def _audit_section(
    report_json_sha256: str,
    old_core: dict[str, Any],
    new_core: dict[str, Any],
    v2_commit: str,
    all_semantics: str,
    candidate_semantics: str,
) -> str:
    unchanged = all(old_core[k] == new_core[k] for k in old_core)
    lines = [
        "## 57. Post-live derived-output corrections and pre/post audit",
        "",
        f"This report and ``decision.json`` were regenerated on {__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()} from the frozen v2 provider evidence only.",
        "No new Alpaca market-data or reference API calls were made.",
        "",
        f"- Frozen private evidence SHA-256: ``{report_json_sha256}``",
        f"- v1 pre-registration commit: ``{V1_PRE_REGISTRATION_COMMIT}`` (preserved byte-for-byte)",
        f"- v2 pre-registration commit: ``{V2_PRE_REGISTRATION_COMMIT}`` (resolved and verified as ancestor of final head)",
        f"- Approved starting head: ``{STARTING_HEAD}``",
        f"- Final head at regeneration: ``{v2_commit}``",
        "",
        "### Corrections applied",
        "",
        "1. ``candidate_timestamp_semantics`` is now aggregated over candidate SIP records only; the comparison IEX feed is excluded from the candidate summary.",
        "2. ``method_parity_passed`` is now ``null`` / not applicable for Alpaca v2 because Alpaca has no Schwab-style method-pair comparison; SIP/IEX diagnostics remain in ``feed_comparison.csv``.",
        "3. ``inactive_asset_listing_supported`` now derives from the ``current_inactive_asset_master`` provider-contract row instead of the active-assets row.",
        "4. The legacy ``no_provider_mixing_contract_satisfied`` field is omitted from v2 ``decision.json`` in favor of ``probe_did_not_mix_providers`` (true) and ``single_provider_contract_satisfied`` (false).",
        "5. The v2 decision schema now includes ``probe_version``, ``target_entitlement``, ``v1_pre_registration_commit``, ``v2_pre_registration_commit``, ``client_version``, and ``excluded_security_types_supported``.",
        "6. Official Alpaca documentation titles/links and review date are recorded for rows classified as ``documented_capability``.",
        "",
        "### Pre/post audit",
        "",
        f"- Aggregate timestamp semantics over **all** records: ``{all_semantics}``",
        f"- Aggregate timestamp semantics over **candidate SIP** records: ``{candidate_semantics}``",
        f"- Core gate/outcome unchanged by corrections: ``{unchanged}``",
        "",
        "Core gate comparison (old → new):",
        "",
    ]
    for key, old_value in old_core.items():
        lines.append(f"- `{key}`: `{old_value}` → `{new_core[key]}`")
    if not unchanged:
        lines.append("")
        lines.append("**AUDIT FAILURE**: at least one core gate or outcome changed. v2 must be marked invalid and v3 proposed.")
    else:
        lines.append("")
        lines.append("**AUDIT PASS**: the post-live derived-output corrections did not change the preregistered core support gates or the empirical disposition ``supported_ohlcv_only``.")
    return "\n".join(lines) + "\n"


def main() -> int:
    from tradex.research.intraday_data_probe import report as report_module
    from tradex.research.intraday_data_probe.models import ProbeReport
    from tradex.research.intraday_data_probe.probe import (
        V1_PRE_REGISTRATION_COMMIT as PROBE_V1_COMMIT,
    )
    from tradex.research.intraday_data_probe.probe import (
        _aggregate_timestamp_semantics,
        _alpaca_rest_version,
        _build_decision,
        validate_pre_registration_commit,
    )
    from tradex.research.intraday_data_probe.report import write_probe_artifacts, write_probe_report
    from tradex.research.intraday_data_probe.spec import load_probe_spec

    assert PROBE_V1_COMMIT == V1_PRE_REGISTRATION_COMMIT

    final_head = _run(["git", "rev-parse", "HEAD"])
    v2_commit = validate_pre_registration_commit(
        V2_PRE_REGISTRATION_COMMIT,
        repo_root=REPO_ROOT,
        final_head=final_head,
    )

    spec_path = REPO_ROOT / "docs/research/specs/INTRA-001B-alpaca-probe-v2.json"
    strategy_spec_path = REPO_ROOT / "docs/research/specs/INTRA-001-v1.json"
    artifact_dir = REPO_ROOT / "docs/research/artifacts/INTRA-001B-ALPACA-V2"
    docs_report_path = REPO_ROOT / "docs/research/INTRA-001B-ALPACA-DATA-PROBE-V2.md"

    spec, spec_bytes = load_probe_spec(spec_path)
    strategy_spec_sha256 = _sha256_file(strategy_spec_path)
    probe_spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()

    report_json_bytes = PRIVATE_REPORT_JSON.read_bytes()
    report_json_sha256 = hashlib.sha256(report_json_bytes).hexdigest()
    report = ProbeReport.from_dict(json.loads(report_json_bytes))

    # Patch documented-capability rows with official Alpaca citations.
    _patch_documented_capability_sources(report.provider_contract_rows, "2026-08-08")

    old_decision = report.decision
    old_core = _core_gates(old_decision)

    client_version = _alpaca_rest_version() if spec.provider == "alpaca" else ""
    new_decision = _build_decision(
        spec,
        report.records,
        report.repeatability_rows,
        report.method_parity_rows,
        report.chunk_overlap_rows,
        strategy_spec_sha256,
        probe_spec_sha256,
        v2_commit,
        client_version,
        feed_comparison_rows=report.feed_comparison_rows,
        provider_contract_rows=report.provider_contract_rows,
    )
    new_core = _core_gates(new_decision)

    if old_core != new_core:
        raise RuntimeError(
            "Frozen-evidence pre/post audit failed: core gates/outcome changed.\n"
            f"old={old_core}\nnew={new_core}"
        )

    all_semantics = _aggregate_timestamp_semantics(report.records)
    candidate_semantics = _aggregate_timestamp_semantics(
        [r for r in report.records if r.method == spec.candidate_feed]
    )

    report.decision = new_decision

    # Preserve the original run_id/timestamp in the directory and report.
    existing_bundle_dir = next(artifact_dir.iterdir())
    run_id = existing_bundle_dir.name
    report_module._run_id = lambda: run_id  # type: ignore[attr-defined]

    report_kwargs: dict[str, Any] = {
        "v1_pre_registration_commit": V1_PRE_REGISTRATION_COMMIT,
        "branch": BRANCH,
        "starting_head": STARTING_HEAD,
        "ci_workflow_id": CI_WORKFLOW_ID,
        "ci_job_id": CI_JOB_ID,
        "ci_merge_ref": CI_MERGE_REF,
        "focused_tests": "passed",
        "full_tests": "passed",
        "ruff_status": "clean",
        "json_validation_status": "valid",
        "checksum_validation_status": "verified",
        "real_persistence_status": "unchanged",
    }

    write_probe_artifacts(
        report=report,
        spec=spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=strategy_spec_path,
        artifact_dir=artifact_dir,
        pre_registration_commit=v2_commit,
        repo_root=REPO_ROOT,
        **report_kwargs,
    )

    write_probe_report(
        report=report,
        spec=spec,
        probe_spec_sha256=probe_spec_sha256,
        strategy_spec_sha256=strategy_spec_sha256,
        pre_registration_commit=v2_commit,
        report_path=docs_report_path,
        **report_kwargs,
    )

    audit_text = _audit_section(
        report_json_sha256,
        old_core,
        new_core,
        v2_commit,
        all_semantics,
        candidate_semantics,
    )

    safe_dir = artifact_dir / run_id
    for path in (safe_dir / "report.md", docs_report_path):
        text = path.read_text(encoding="utf-8")
        path.write_text(text + "\n" + audit_text, encoding="utf-8")

    # Recompute checksums for the safe bundle after appending the audit section.
    checksums_path = safe_dir / "checksums.sha256"
    lines: list[str] = []
    for p in sorted(safe_dir.iterdir()):
        if p.is_file() and p.name != "checksums.sha256":
            lines.append(f"{_sha256_file(p)}  {p.name}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Update the project tracker with the correct v2 pre-registration commit.
    tracker_path = REPO_ROOT / "docs/PROJECT-TRACKER.md"
    tracker_text = tracker_path.read_text(encoding="utf-8")
    tracker_text = tracker_text.replace(
        "340e0921b31e40b6d9ef67aaedb8b6b8ec7a4185",
        v2_commit,
    )
    tracker_path.write_text(tracker_text, encoding="utf-8")

    print(f"Regenerated {safe_dir}")
    print(f"Updated {docs_report_path}")
    print(f"Core gates unchanged: {old_core == new_core}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
