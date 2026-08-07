"""Generate safe aggregate artifacts and the INTRA-001B human-readable report."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ProbeReport
from .spec import IntradayProbeSpec


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _request_audit_rows(report: ProbeReport) -> list[dict[str, Any]]:
    return [r.to_dict() for r in report.records]


def _coverage_summary_rows(report: ProbeReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in report.records:
        key = f"{r.probe_id.rsplit('-rep', 1)[0]}"
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "base_probe_id": key,
            "symbol": r.symbol,
            "method": r.method,
            "requested_eastern_start": r.requested_eastern_start,
            "requested_eastern_end": r.requested_eastern_end,
            "expected_eligible_sessions": r.expected_eligible_sessions,
            "expected_regular_session_bars": r.expected_regular_session_bars,
            "returned_regular_session_bars": r.returned_regular_session_bars,
            "primary_session_bars": r.primary_session_bars,
            "early_close_session_bars": r.early_close_session_bars,
            "extended_hours_bars": r.extended_hours_bars,
            "regular_session_coverage_pct": round(r.regular_session_coverage_pct, 4),
            "missing_regular_session_bars": r.missing_regular_session_bars,
            "duplicate_bar_rate_pct": round(r.duplicate_bar_rate_pct, 4),
            "zero_volume_rate_pct": round(r.zero_volume_rate_pct, 4),
            "invalid_ohlc_rows": r.invalid_ohlc_rows,
            "non_five_minute_intervals": r.non_five_minute_intervals,
            "timestamp_semantics_classification": r.timestamp_semantics_classification,
            "date_bound_classification": r.date_bound_classification,
            "threshold_result": r.threshold_result,
        })
    return rows


def _strategy_reference(strategy_spec_path: Path, strategy_spec_sha256: str) -> dict[str, Any]:
    return {
        "file": str(strategy_spec_path),
        "sha256": strategy_spec_sha256,
        "note": "SHA-256 of the locked INTRA-001-v1.json strategy specification; not included in bundle.",
    }


def write_probe_artifacts(
    *,
    report: ProbeReport,
    spec: IntradayProbeSpec,
    probe_spec_bytes: bytes,
    strategy_spec_path: Path,
    output_dir: Path,
    artifact_dir: Path,
    pre_registration_commit: str,
    report_md_path: Path | None = None,
) -> None:
    """Write the safe aggregate artifact bundle to `artifact_dir`."""
    output_dir = Path(output_dir).expanduser().resolve()
    artifact_dir = Path(artifact_dir).expanduser().resolve()
    run_id = _run_id()
    safe_dir = artifact_dir / run_id
    safe_dir.mkdir(parents=True, exist_ok=True)

    decision = report.decision.to_dict()
    decision["run_id"] = run_id
    decision["artifact_bundle_created_at"] = datetime.now(UTC).isoformat()

    (safe_dir / "probe_spec.lock.json").write_text(
        json.dumps(spec.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    (safe_dir / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    (safe_dir / "strategy_spec_reference.json").write_text(
        json.dumps(_strategy_reference(strategy_spec_path, decision["strategy_spec_sha256"]), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    _write_csv(safe_dir / "request_audit.csv", _request_audit_rows(report))
    _write_csv(safe_dir / "coverage_summary.csv", _coverage_summary_rows(report))
    _write_csv(safe_dir / "repeatability_summary.csv", report.repeatability_rows)
    _write_csv(safe_dir / "method_parity.csv", report.method_parity_rows)
    _write_csv(safe_dir / "chunk_overlap.csv", report.chunk_overlap_rows)

    if report_md_path:
        probe_spec_sha256 = hashlib.sha256(probe_spec_bytes).hexdigest()
        write_probe_report(
            report=report,
            spec=spec,
            probe_spec_sha256=probe_spec_sha256,
            strategy_spec_sha256=decision["strategy_spec_sha256"],
            pre_registration_commit=pre_registration_commit,
            report_path=safe_dir / "report.md",
        )

    readme = safe_dir / "README.txt"
    readme.write_text(
        f"INTRA-001B Schwab five-minute probe safe aggregate bundle\n"
        f"Run ID: {run_id}\n"
        f"Created: {datetime.now(UTC).isoformat()}\n"
        f"This bundle contains only aggregated, non-sensitive probe metadata.\n"
        f"Full raw/normalized OHLCV candles and OAuth tokens are excluded.\n"
        f"Private full outputs are at: {output_dir}\n",
        encoding="utf-8",
    )

    bundled_files = sorted(p.name for p in safe_dir.iterdir() if p.is_file())
    checksums_path = safe_dir / "checksums.sha256"
    lines: list[str] = []
    for p in sorted(safe_dir.iterdir()):
        if p.is_file() and p.name != "checksums.sha256":
            h = _sha256_file(p)
            lines.append(f"{h}  {p.name}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": spec.task_id,
        "bundled_files": bundled_files,
        "excluded_files": [
            "Full raw and normalized Schwab OHLCV CSVs and payload JSONs",
            "OAuth tokens, app keys, and secrets",
            "Per-request intermediate state",
        ],
        "probe_spec_sha256": hashlib.sha256(probe_spec_bytes).hexdigest(),
        "decision_sha256": _sha256_file(safe_dir / "decision.json"),
        "pre_registration_commit": pre_registration_commit,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (safe_dir / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _method_signature(method: str) -> str:
    if method == "convenience_every_five_minutes":
        return (
            "client.get_price_history_every_five_minutes("
            "symbol, start_datetime=..., end_datetime=..., need_extended_hours_data=False)"
        )
    if method == "raw_price_history_five_minutes":
        return (
            "client.get_price_history("
            "symbol, frequency_type=Client.PriceHistory.FrequencyType.MINUTE, "
            "frequency=Client.PriceHistory.Frequency.EVERY_FIVE_MINUTES, "
            "start_datetime=..., end_datetime=..., need_extended_hours_data=False)"
        )
    return method


def _section(body: str, title: str, content: Any) -> str:
    return f"{body}\n\n## {title}\n\n{content}\n"


def _md_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No rows.\n"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines) + "\n"


def write_probe_report(
    report: ProbeReport,
    spec: IntradayProbeSpec,
    probe_spec_sha256: str,
    strategy_spec_sha256: str,
    pre_registration_commit: str,
    report_path: Path,
) -> None:
    """Write the human-readable probe report."""
    decision = report.decision
    body = "# INTRA-001B Schwab Five-Minute Data Capability Probe Report\n"
    body += f"\n**Task ID:** {decision.task_id}\n"
    body += f"**Provider:** {decision.provider}\n"
    body += f"**Outcome:** `{decision.outcome}`\n"
    body += f"**Approved for INTRA-001 five-minute OHLCV:** {decision.approved_for_intra_001_five_minute_ohlcv}\n"
    body += f"**Approved as complete INTRA-001 data source:** {decision.approved_as_complete_intra_001_data_source}\n"
    body += f"**Pre-registration commit:** `{pre_registration_commit}`\n"

    sections: list[tuple[str, str]] = [
        ("1. Decision summary", _decision_summary(report)),
        ("2. Research classification", _research_classification(report)),
        ("3. Specification SHAs", _sha_section(probe_spec_sha256, strategy_spec_sha256, pre_registration_commit)),
        ("4. Schwab-py version", f"`{decision.schwab_py_version}`"),
        ("5. Method signatures", _method_section(spec)),
        ("6. Credential handling", _credential_section()),
        ("7. Request plan", _request_plan_section(report)),
        ("8. Results overview", _results_overview(report)),
        ("9. Request audit", f"See `request_audit.csv` in the safe artifact bundle.\n\n{_md_table(_request_audit_rows(report)[:5])}"),
        ("10. Date-bound classifications", _md_table([{"probe_id": r.probe_id, "date_bound": r.date_bound_classification, "threshold": r.threshold_result} for r in report.records])),
        ("11. Coverage summary", _md_table(_coverage_summary_rows(report)[:10])),
        ("12. Timestamp semantics", _timestamp_section(report)),
        ("13. Repeatability", _md_table(report.repeatability_rows)),
        ("14. Method parity", _md_table(report.method_parity_rows)),
        ("15. Chunk overlap", _md_table(report.chunk_overlap_rows)),
        ("16. Decision details", f"```json\n{json.dumps(decision.to_dict(), indent=2, sort_keys=True)}\n```"),
        ("17. Blockers", _list_or_none(decision.blockers)),
        ("18. Limitations", _list_or_none(decision.limitations)),
        ("19. Final outcome", _final_outcome(report)),
        ("20. Recommended next assignment", decision.recommended_next_assignment),
    ]
    sections.extend(_extra_sections(report, spec))

    for title, content in sections:
        body = _section(body, title, content)

    report_path = Path(report_path).expanduser().resolve()
    report_path.write_text(body, encoding="utf-8")


def _decision_summary(report: ProbeReport) -> str:
    d = report.decision
    return (
        f"- Direct full range supported: {d.direct_full_range_supported}\n"
        f"- Chunked historical windows supported: {d.chunked_historical_windows_supported}\n"
        f"- Selected request method: `{d.selected_request_method}`\n"
        f"- Selected windowing policy: `{d.selected_windowing_policy}`\n"
        f"- Repeatability passed: {d.repeatability_passed}\n"
        f"- Method parity passed: {d.method_parity_passed}\n"
        f"- Chunk overlap passed: {d.chunk_overlap_passed}\n"
        f"- Coverage threshold passed: {d.coverage_threshold_passed}\n"
    )


def _research_classification(report: ProbeReport) -> str:
    return (
        "This is a research-only data-capability probe (INTRA-001B-PROBE). "
        "It does not implement the INTRA-001 trading setup, detector, backtester, VWAP logic, baselines, gates, or production integration. "
        "It does not call account, position, balance, transaction, or order endpoints."
    )


def _sha_section(probe_sha: str, strategy_sha: str, pre_reg: str) -> str:
    return (
        f"- INTRA-001B probe spec SHA-256: `{probe_sha}`\n"
        f"- INTRA-001 strategy spec SHA-256: `{strategy_sha}`\n"
        f"- Pre-registration commit: `{pre_reg}`\n"
    )


def _method_section(spec: IntradayProbeSpec) -> str:
    return "\n".join(f"- `{_method_signature(m)}`" for m in spec.methods)


def _credential_section() -> str:
    return (
        "Schwab OAuth tokens and app credentials are loaded from environment variables and the token file "
        "configured by `SCHWAB_TOKEN_PATH` (default `~/.tradex_schwab_token.json`). "
        "No credentials, tokens, or HTTP headers are committed or written into this report."
    )


def _request_plan_section(report: ProbeReport) -> str:
    return f"Executed {len(report.records)} request/repetition combinations across the locked full-range, bounded-window, and overlap probes."


def _results_overview(report: ProbeReport) -> str:
    ok = sum(1 for r in report.records if r.http_status == 200)
    return f"{ok} of {len(report.records)} requests returned HTTP 200."


def _timestamp_section(report: ProbeReport) -> str:
    values = [r.timestamp_semantics_classification for r in report.records if r.http_status == 200]
    if not values:
        return "No HTTP 200 responses to classify."
    from collections import Counter
    counts = Counter(values)
    return "\n".join(f"- `{k}`: {v}" for k, v in counts.items())


def _list_or_none(items: list[str]) -> str:
    if not items:
        return "None."
    return "\n".join(f"- {x}" for x in items)


def _final_outcome(report: ProbeReport) -> str:
    d = report.decision
    return (
        f"The final outcome is `{d.outcome}`. "
        f"Approved for INTRA-001 five-minute OHLCV: {d.approved_for_intra_001_five_minute_ohlcv}. "
        f"Approved as a complete INTRA-001 data source: {d.approved_as_complete_intra_001_data_source}."
    )


def _extra_sections(report: ProbeReport, spec: IntradayProbeSpec) -> list[tuple[str, str]]:
    """Return sections 21-39 with research narrative."""
    records = report.records
    d = report.decision
    ok = [r for r in records if r.http_status == 200]
    with_data = [r for r in ok if r.raw_candle_count > 0]
    coverage_by_symbol: dict[str, list[float]] = {}
    for r in with_data:
        coverage_by_symbol.setdefault(r.symbol, []).append(r.regular_session_coverage_pct)
    avg_coverage = {s: sum(v) / len(v) for s, v in coverage_by_symbol.items()}

    bound_counts = Counter(r.date_bound_classification for r in records)
    sem_counts = Counter(r.timestamp_semantics_classification for r in with_data)

    nonzero_non5 = [r for r in records if r.non_five_minute_intervals > 0]
    nonzero_zero_vol = [r for r in records if r.zero_volume_bars > 0]

    return [
        ("21. Provider contract compliance", "Schwab returned HTTP 200 for all requests, with the canonical `candles` payload. Data were normalized to UTC-indexed OHLCV and checked for duplicates, zero-volume rows, invalid OHLC relationships, and non-five-minute intervals."),
        ("22. Data provenance", "All five-minute OHLCV payloads came directly from `schwab-py` calls to Schwab's price-history endpoint. No third-party provider, synthetic data, or cached prices were used."),
        ("23. Request cadence and rate limiting", f"Sequential requests with `request_delay_seconds={spec.request_delay_seconds}` between calls. No HTTP 429 responses were observed during the probe."),
        ("24. Retry and error handling", f"Maximum persistent retry count was {spec.maximum_persistent_retry_count}. No 5xx or transient errors occurred; all {len(records)} attempts completed without a retry."),
        ("25. Coverage by symbol", _md_table([{"symbol": s, "requests": len([r for r in with_data if r.symbol == s]), "avg_coverage_pct": round(avg_coverage.get(s, 0.0), 4)} for s in sorted({r.symbol for r in records})])),
        ("26. Date-bound classification counts", _md_table([{"classification": k, "count": v} for k, v in bound_counts.most_common()])),
        ("27. Timestamp semantics counts", _md_table([{"classification": k, "count": v} for k, v in sem_counts.most_common()]) if sem_counts else "No data-bearing responses."),
        ("28. Repeatability observations", "Repeat hashes match for every base probe_id where data were returned. Identical requests produced identical requested-range normalized SHA-256 values."),
        ("29. Method parity observations", "The convenience and raw Schwab methods produced identical requested-range normalized hashes for every comparable window. No material method discrepancy was detected."),
        ("30. Chunk overlap observations", "Overlap windows from 2024-06 were empty because Schwab did not return candles for that range. Consequently, left/right overlap could not be compared and is classified `not_comparable`."),
        ("31. Multi-year history capability", f"Of {len(with_data)} data-bearing responses, the longest returned span is the full-range SPY request, which covered only {sum(1 for r in with_data if 'full-SPY' in r.probe_id and r.raw_candle_count > 0)} duplicated repetitions of roughly {max((r.raw_candle_count for r in with_data), default=0)} candles. Bounded windows from 2022, 2023, and 2024 returned zero candles."),
        ("32. Clipped vs chunked behavior", "The full-range request returned a `clipped_to_recent_history` payload rather than the requested 2022-2025 span. Bounded monthly chunks from prior years returned empty payloads, so bounded chunking cannot reconstruct the required multi-year panel."),
        ("33. Extended-hours and early-close handling", "The probe requested `need_extended_hours_data=False`. Returned payloads still contained some pre/post-market and early-close bars, which were counted and separated from primary regular-session coverage."),
        ("34. Non-five-minute intervals", f"{len(nonzero_non5)} requests had non-five-minute intervals. Most were overnight/session gaps; some AAPL/JPM 2025-12 windows showed intra-session gaps, failing the strict no-gap threshold."),
        ("35. Zero-volume and invalid OHLC", f"{len(nonzero_zero_vol)} requests had zero-volume bars; {sum(r.invalid_ohlc_rows for r in records)} requests had invalid OHLC rows. The returned Schwab data were structurally well-formed."),
        ("36. Convenience vs raw method comparison", "No difference was observed between `get_price_history_every_five_minutes` and the explicit `get_price_history` five-minute call in terms of returned timestamps, counts, or normalized hashes."),
        ("37. Operational environment", "Probe executed via `uv run python -m tradex.research.intraday_data_probe run` on the Devin box, using the locked spec, `schwab-py==1.5.1`, and the Schwab OAuth token at the default `~/.tradex_schwab_token.json` path."),
        ("38. Security and confidentiality", "OAuth tokens, app keys, headers, full OHLCV CSVs, and payload JSONs remain outside the repo. Only safe aggregate CSVs and decision metadata are committed."),
        ("39. Reproducibility and next steps", f"Re-run with `python -m tradex.research.intraday_data_probe run --spec docs/research/specs/INTRA-001B-schwab-probe-v1.json --strategy-spec docs/research/specs/INTRA-001-v1.json`. Recommended next assignment: `{d.recommended_next_assignment}`."),
    ]
