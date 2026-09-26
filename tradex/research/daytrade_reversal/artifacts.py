"""Deterministic safe artifact generation and checksum verification."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .freeze import EvaluationFreezeRecord
from .models import DataQualityReport, EventObservation, StudyResult, sanitize_json_value
from .spec import DaytradeSpec


def sha256_of_file(path: Path) -> str:
    """Return hex SHA-256 digest of file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_artifact(data: Any, path: Path) -> None:
    """Serialize data to JSON with no NaN/Infinity and stable formatting."""
    sanitized = sanitize_json_value(data)
    text = json.dumps(sanitized, indent=2, sort_keys=True, allow_nan=False)
    path.write_text(text, encoding="utf-8")


def generate_markdown_report(result: StudyResult) -> str:
    """Generate a clean Markdown summary report for the study execution."""
    lines: list[str] = [
        f"# {result.task_id} Reversal Study Report — Split: {result.split.upper()}",
        "",
        f"- **Task ID:** `{result.task_id}`",
        f"- **Split:** `{result.split}`",
        f"- **Disposition:** **`{result.disposition.upper()}`**",
        f"- **Disposition Step:** `{result.disposition_step}`",
        f"- **Disposition Reason:** {result.disposition_reason}",
        "- **Evidence Confidence Cap:** `limited_but_usable_evidence`",
        "- **Production Promotion Eligible:** `False`",
        "",
        "## Validation Gates",
        "",
        "| Gate | Passed | Details |",
        "|---|---|---|",
    ]

    for g_name, g_res in sorted(result.gates.items()):
        status_icon = "PASS" if g_res.passed else "FAIL"
        details_str = json.dumps(g_res.detail, sort_keys=True)
        lines.append(f"| `{g_name}` | **{status_icon}** | `{details_str}` |")

    p = result.provenance
    m = result.metrics
    lines.extend([
        "",
        "## Core Metrics",
        "",
        f"- **Total Eligible Minutes:** {m.get('eligible_minute_count', 0)}",
        f"- **Event Count:** {m.get('event_count', 0)}",
        f"- **Represented Tickers:** {m.get('represented_ticker_count', 0)}",
        f"- **Maximum Ticker Concentration:** {m.get('maximum_single_ticker_event_concentration', 0.0):.2f}%",
        f"- **Overlapping Events:** {m.get('overlapping_event_count', 0)} ({m.get('overlapping_event_rate', 0.0) * 100.0:.2f}%)",
        f"- **Mean Net Return (2 bps/side):** {m.get('mean_net_forward_return_2bps')}",
        f"- **Median Net Return (2 bps/side):** {m.get('median_net_forward_return_2bps')}",
        f"- **Mean Baseline Net Return:** {m.get('same_ticker_time_of_day_baseline_mean')}",
        f"- **Median Baseline Net Return:** {m.get('same_ticker_time_of_day_baseline_median')}",
        f"- **Mean Uplift:** {m.get('event_minus_baseline_difference_mean')}",
        f"- **Median Uplift:** {m.get('event_minus_baseline_difference_median')}",
        f"- **Win Rate (1m gross):** {m.get('win_rate_1m', 0.0) * 100.0:.2f}%",
        f"- **Win Rate (2m gross):** {m.get('win_rate_2m', 0.0) * 100.0:.2f}%",
        f"- **Win Rate (5m gross):** {m.get('win_rate_5m', 0.0) * 100.0:.2f}%",
        "",
        "## Statistical Inference (Joint Cluster Bootstrap)",
        "",
        f"- **Primary Net Return CI:** `{json.dumps(result.bootstrap.get('primary_net_return', {}))}`",
        f"- **Event Uplift CI:** `{json.dumps(result.bootstrap.get('event_minus_baseline_uplift', {}))}`",
        "",
        "## Provenance",
        "",
        f"- **Provider:** `{p.get('provider', 'alpaca')}`",
        f"- **Feed:** `{p.get('feed', 'sip')}`",
        f"- **Timeframe:** `{p.get('timeframe', '1Min')}`",
        f"- **Adjustment:** `{p.get('adjustment', 'split')}`",
        f"- **Calendar:** `{p.get('calendar', 'XNYS')}`",
        f"- **Timezone:** `{p.get('timezone', 'America/New_York')}`",
        f"- **Split:** `{result.split}`",
        f"- **Spec SHA-256:** `{p.get('spec_sha256', '')}`",
        f"- **Evaluator Code SHA:** `{p.get('evaluator_code_sha', '')}`",
        f"- **Manifest SHA-256:** `{p.get('manifest_sha256', '')}`",
        f"- **Evidence Confidence Cap:** `{p.get('evidence_confidence_cap', 'limited_but_usable_evidence')}`",
        f"- **Production Promotion Eligible:** `{p.get('production_promotion_eligible', False)}`",
    ])

    prov_sum = m.get("provider_provenance_summary", {})
    if isinstance(prov_sum, dict) and prov_sum.get("status") != "unavailable":
        lines.extend([
            "",
            "## Acquisition Provenance",
            "",
            f"- **Total Symbols:** {prov_sum.get('total_symbols', 'N/A')}",
            f"- **Total Requests:** {prov_sum.get('total_requests', 'N/A')}",
            f"- **Total HTTP Pages:** {prov_sum.get('total_pages', 'N/A')}",
            f"- **Total HTTP Retries:** {prov_sum.get('total_retries', 'N/A')}",
            f"- **Total HTTP Errors:** {prov_sum.get('total_errors', 'N/A')}",
            f"- **Total Malformed Timestamps:** {prov_sum.get('total_malformed_timestamps', 'N/A')}",
            f"- **Pagination Complete:** {prov_sum.get('pagination_complete', 'N/A')}",
        ])

    lines.extend([
        "",
        "## Limitations",
        "",
        "- Fixed 2026 Dow 30 snapshot applied to 2025 introduces survivorship and constituent selection limitations.",
        "- Maximum evidence confidence is strictly capped at `limited_but_usable_evidence`.",
    ])

    return "\n".join(lines) + "\n"


def write_artifact_bundle(
    output_dir: Path,
    result: StudyResult,
    spec: DaytradeSpec,
    freeze_record: EvaluationFreezeRecord | None = None,
    events: list[EventObservation] | None = None,
    data_quality_reports: list[DataQualityReport] | None = None,
    manifest_data: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write the complete, safe artifact bundle and return file checksums dictionary."""
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    events_to_write = events if events is not None else getattr(result, "events", [])
    dq_reports_to_write = (
        data_quality_reports
        if data_quality_reports is not None
        else getattr(result, "data_quality_reports", [])
    )

    written_files: list[str] = []

    # 1. study.json
    study_path = out / "study.json"
    write_json_artifact(result.to_json_dict(), study_path)
    written_files.append("study.json")

    # 2. spec.lock.json
    spec_lock_path = out / "spec.lock.json"
    spec_lock_data = {
        "task_id": spec.task_id,
        "spec_version": spec.spec_version,
        "spec_sha256": spec.sha256,
        "spec": spec.raw_dict,
    }
    write_json_artifact(spec_lock_data, spec_lock_path)
    written_files.append("spec.lock.json")

    # 3. freeze.json
    if freeze_record is not None:
        freeze_path = out / "freeze.json"
        write_json_artifact(freeze_record.to_dict(), freeze_path)
        written_files.append("freeze.json")

    # 4. manifest.lock.json
    if manifest_data is not None:
        man_path = out / "manifest.lock.json"
        write_json_artifact(manifest_data, man_path)
        written_files.append("manifest.lock.json")

    # 5. metrics.json
    metrics_path = out / "metrics.json"
    write_json_artifact(result.metrics, metrics_path)
    written_files.append("metrics.json")

    # 6. bootstrap.json
    boot_path = out / "bootstrap.json"
    write_json_artifact(result.bootstrap, boot_path)
    written_files.append("bootstrap.json")

    # 7. data_quality.csv
    dq_path = out / "data_quality.csv"
    with dq_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ticker",
            "session_date",
            "total_bars",
            "expected_bars",
            "missing_bars",
            "missing_rate_pct",
            "duplicate_bars",
            "duplicate_rate_pct",
            "malformed_timestamp_count",
            "malformed_ohlcv_count",
            "excluded",
            "exclusion_reasons",
        ])
        for r in dq_reports_to_write:
            writer.writerow([
                r.ticker,
                r.session_date.isoformat(),
                r.total_bars,
                r.expected_bars,
                r.missing_bars,
                f"{r.missing_rate_pct:.2f}",
                r.duplicate_bars,
                f"{r.duplicate_rate_pct:.2f}",
                r.malformed_timestamp_count,
                r.malformed_ohlcv_count,
                r.excluded,
                ";".join(r.exclusion_reasons),
            ])
    written_files.append("data_quality.csv")

    # 8. events.csv
    events_path = out / "events.csv"
    with events_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "event_id",
            "ticker",
            "session_date",
            "split",
            "bar_start",
            "return",
            "threshold",
            "is_overlapping",
            "net_return_1m_2bps",
            "matched_baseline_1m_2bps",
            "uplift_1m_2bps",
        ])
        for e in events_to_write:
            net_ret = e.outcomes[1].net_return_2bps if 1 in e.outcomes else ""
            writer.writerow([
                e.event_id,
                e.ticker,
                e.session_date.isoformat(),
                e.split,
                e.event_bar_start.isoformat(),
                f"{e.event_return:.6f}",
                f"{e.threshold:.6f}",
                e.is_overlapping,
                f"{net_ret:.6f}" if isinstance(net_ret, float) else "",
                f"{e.matched_baseline_1m_net:.6f}" if isinstance(e.matched_baseline_1m_net, float) else "",
                f"{e.uplift_1m_net:.6f}" if isinstance(e.uplift_1m_net, float) else "",
            ])
    written_files.append("events.csv")

    # 9. baseline_summary.csv
    base_path = out / "baseline_summary.csv"
    with base_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["mean_baseline_net_2bps", result.metrics.get("same_ticker_time_of_day_baseline_mean")])
        writer.writerow(["median_baseline_net_2bps", result.metrics.get("same_ticker_time_of_day_baseline_median")])
        writer.writerow(["mean_uplift_net_2bps", result.metrics.get("event_minus_baseline_difference_mean")])
        writer.writerow(["median_uplift_net_2bps", result.metrics.get("event_minus_baseline_difference_median")])
    written_files.append("baseline_summary.csv")

    # 10. per_ticker.csv
    pt_path = out / "per_ticker.csv"
    with pt_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "event_count", "mean_net_return_2bps"])
        for ticker, t_info in sorted(result.metrics.get("per_ticker_primary_results", {}).items()):
            if isinstance(t_info, dict):
                writer.writerow([ticker, t_info.get("event_count"), t_info.get("mean_net_return_2bps")])
            else:
                writer.writerow([ticker, "", t_info])
    written_files.append("per_ticker.csv")

    # 11. monthly.csv
    monthly_path = out / "monthly.csv"
    with monthly_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "event_count", "mean_net_return_2bps"])
        for m, m_info in sorted(result.metrics.get("monthly_primary_results", {}).items()):
            if isinstance(m_info, dict):
                writer.writerow([m, m_info.get("event_count"), m_info.get("mean_net_return_2bps")])
            else:
                writer.writerow([m, "", m_info])
    written_files.append("monthly.csv")

    # 12. report.md
    report_text = generate_markdown_report(result)
    report_path = out / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    written_files.append("report.md")

    # 13. checksums.sha256
    checksums: dict[str, str] = {}
    for filename in sorted(written_files):
        fp = out / filename
        checksums[filename] = sha256_of_file(fp)

    checksum_lines = [f"{checksums[fn]}  {fn}" for fn in sorted(checksums.keys())]
    (out / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    return checksums
