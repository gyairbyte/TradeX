"""Deterministic safe artifact generation and checksum verification for DAYTRADE-002B."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .freeze import EvaluationFreezeRecord
from .models import StudyResult, sanitize_json_value
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
        f"# {result.task_id} Early-to-Late Momentum Study Report — Split: {result.split.upper()}",
        "",
        f"- **Task ID:** `{result.task_id}`",
        f"- **Study Name:** `{result.study_name}`",
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
        f"- **Eligible Ticker-Sessions:** {m.get('eligible_ticker_session_count', 0)}",
        f"- **Event Count:** {m.get('event_count', 0)}",
        f"- **Represented ETFs:** {m.get('represented_etf_count', 0)}",
        f"- **Event Session Count (Dates):** {m.get('event_session_count', 0)}",
        f"- **Long Events:** {m.get('long_event_count', 0)}",
        f"- **Short Events:** {m.get('short_event_count', 0)}",
        f"- **Maximum ETF Concentration:** {m.get('maximum_single_etf_event_concentration', 0.0):.2f}%",
        f"- **Multi-Signal Session Count:** {m.get('multi_signal_session_count', 0)} ({m.get('multi_signal_session_rate', 0.0) * 100.0:.2f}%)",
        f"- **Gross Win Rate (30m):** {m.get('win_rate_gross_30m', 0.0) * 100.0:.2f}%",
        f"- **Mean Gross Signed Return:** {m.get('mean_gross_signed_return_30m')}",
        f"- **Mean Net Return (2 bps/side):** {m.get('mean_net_signed_return_2bps')}",
        f"- **Median Net Return (2 bps/side):** {m.get('median_net_signed_return_2bps')}",
        f"- **Mean Baseline Net Return (2 bps):** {m.get('matched_non_event_baseline_mean')}",
        f"- **Median Baseline Net Return (2 bps):** {m.get('matched_non_event_baseline_median')}",
        f"- **Mean Uplift:** {m.get('event_minus_baseline_mean')}",
        f"- **Median Uplift:** {m.get('event_minus_baseline_median')}",
        "",
        "## Statistical Inference (Session-Date Cluster Bootstrap)",
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

    return "\n".join(lines)


def write_artifact_bundle(
    output_dir: Path | str,
    result: StudyResult,
    spec: DaytradeSpec,
    freeze: EvaluationFreezeRecord | None = None,
    manifest: Any | None = None,
) -> dict[str, str]:
    """Write the complete, deterministic study artifact bundle and checksums.sha256.

    Returns:
        Mapping of relative filename -> hex SHA-256 digest.
    """
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. study.json
    write_json_artifact(result.to_dict(), out_dir / "study.json")

    # 2. spec.lock.json
    spec_lock_payload = {
        "task_id": spec.task_id,
        "spec_sha256": spec.sha256,
        "universe": list(spec.universe),
        "split": result.split,
        "threshold_percentile": spec.percentile,
        "primary_cost_bps_per_side": spec.primary_cost_bps_per_side,
    }
    write_json_artifact(spec_lock_payload, out_dir / "spec.lock.json")

    # 3. freeze.json (if present)
    if freeze is not None:
        write_json_artifact(freeze.to_dict(), out_dir / "freeze.json")

    # 4. manifest.lock.json (if present)
    if manifest is not None:
        write_json_artifact(manifest.to_dict(), out_dir / "manifest.lock.json")

    # 5. bootstrap.json
    write_json_artifact(result.bootstrap, out_dir / "bootstrap.json")

    # 6. metrics.json
    write_json_artifact(result.metrics, out_dir / "metrics.json")

    # 7. data_quality.csv
    dq_csv = out_dir / "data_quality.csv"
    with dq_csv.open("w", newline="", encoding="utf-8") as f:
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
        for r in sorted(result.quality_reports, key=lambda x: (x.ticker, x.session_date)):
            writer.writerow([
                r.ticker,
                r.session_date.isoformat(),
                r.total_bars,
                r.expected_bars,
                r.missing_bars,
                f"{r.missing_rate_pct:.4f}",
                r.duplicate_bars,
                f"{r.duplicate_rate_pct:.4f}",
                r.malformed_timestamp_count,
                r.malformed_ohlcv_count,
                r.excluded,
                ";".join(r.exclusion_reasons),
            ])

    # 8. events.csv
    events_csv = out_dir / "events.csv"
    with events_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ticker",
            "session_date",
            "direction",
            "signal_return",
            "threshold",
            "entry_time",
            "exit_time",
            "entry_price",
            "exit_price",
            "gross_return",
            "net_return_0bps",
            "net_return_2bps",
            "net_return_5bps",
            "matched_baseline_net_2bps",
            "uplift_net_2bps",
            "split",
        ])
        for e in sorted(result.events, key=lambda x: (x.session_date, x.ticker)):
            writer.writerow([
                e.ticker,
                e.session_date.isoformat(),
                e.direction,
                f"{e.signal_return:.6f}",
                f"{e.threshold:.6f}",
                e.entry_time.isoformat(),
                e.exit_time.isoformat(),
                f"{e.entry_price:.4f}",
                f"{e.exit_price:.4f}",
                f"{e.gross_return:.6f}",
                f"{e.net_return_0bps:.6f}",
                f"{e.net_return_2bps:.6f}",
                f"{e.net_return_5bps:.6f}",
                f"{e.matched_baseline_net_2bps:.6f}" if e.matched_baseline_net_2bps is not None else "",
                f"{e.uplift_net_2bps:.6f}" if e.uplift_net_2bps is not None else "",
                e.split,
            ])

    # 9. baseline_summary.csv
    baseline_csv = out_dir / "baseline_summary.csv"
    with baseline_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ticker",
            "direction",
            "non_event_count",
            "mean_net_return_2bps",
        ])
        # Group non_events by ticker and direction
        from collections import defaultdict
        ne_by_bucket = defaultdict(list)
        for ne in result.non_events:
            ne_by_bucket[(ne.ticker, ne.direction)].append(ne.net_return_2bps)

        for (sym, direct), rets in sorted(ne_by_bucket.items()):
            mean_r = sum(rets) / float(len(rets))
            writer.writerow([sym, direct, len(rets), f"{mean_r:.6f}"])

    # 10. per_etf.csv
    per_etf_csv = out_dir / "per_etf.csv"
    with per_etf_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "event_count", "mean_net_return_2bps", "win_rate_gross"])
        per_etf_data = result.metrics.get("per_etf_primary_results", {})
        for sym, d in sorted(per_etf_data.items()):
            writer.writerow([
                sym,
                d.get("event_count", 0),
                f"{d.get('mean_net_signed_return_2bps', 0.0):.6f}" if d.get('mean_net_signed_return_2bps') is not None else "",
                f"{d.get('win_rate_gross', 0.0):.4f}",
            ])

    # 11. monthly.csv
    monthly_csv = out_dir / "monthly.csv"
    with monthly_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "event_count", "mean_net_return_2bps"])
        per_month_data = result.metrics.get("per_month_primary_results", {})
        for mo, d in sorted(per_month_data.items()):
            writer.writerow([
                mo,
                d.get("event_count", 0),
                f"{d.get('mean_net_signed_return_2bps', 0.0):.6f}" if d.get('mean_net_signed_return_2bps') is not None else "",
            ])

    # 12. direction.csv
    direction_csv = out_dir / "direction.csv"
    with direction_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["direction", "event_count", "mean_net_return_2bps", "mean_uplift_2bps"])
        long_side = result.metrics.get("long_side_primary_results", {})
        short_side = result.metrics.get("short_side_primary_results", {})
        writer.writerow([
            "LONG",
            long_side.get("event_count", 0),
            f"{long_side.get('mean_net_signed_return_2bps', 0.0):.6f}" if long_side.get('mean_net_signed_return_2bps') is not None else "",
            f"{long_side.get('mean_uplift_2bps', 0.0):.6f}" if long_side.get('mean_uplift_2bps') is not None else "",
        ])
        writer.writerow([
            "SHORT",
            short_side.get("event_count", 0),
            f"{short_side.get('mean_net_signed_return_2bps', 0.0):.6f}" if short_side.get('mean_net_signed_return_2bps') is not None else "",
            f"{short_side.get('mean_uplift_2bps', 0.0):.6f}" if short_side.get('mean_uplift_2bps') is not None else "",
        ])

    # 13. report.md
    report_md = out_dir / "report.md"
    report_content = generate_markdown_report(result)
    report_md.write_text(report_content, encoding="utf-8")

    # 14. checksums.sha256
    checksums: dict[str, str] = {}
    for p in sorted(out_dir.iterdir()):
        if p.name == "checksums.sha256" or not p.is_file():
            continue
        checksums[p.name] = sha256_of_file(p)

    checksums_file = out_dir / "checksums.sha256"
    lines = [f"{digest}  {name}" for name, digest in sorted(checksums.items())]
    checksums_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    checksums["checksums.sha256"] = sha256_of_file(checksums_file)
    return checksums
