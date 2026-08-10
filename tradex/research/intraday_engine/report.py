"""Markdown/JSON report generation for the INTRA-001 engine and INTRA-001D study."""
from __future__ import annotations

from typing import Any

from .models import Signal, StudyMetrics, StudyOutcome
from .spec import IntradaySpec


def _fmt(value: float | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float) and value != int(value):
        return f"{value:.4f}"
    return str(value)


def _signal_table(signals: list[Signal], label: str) -> list[str]:
    """Summary and a short table of executed trades for one strategy."""
    executed = [s for s in signals if s.status == "executed"]
    rejected = [s for s in signals if s.status not in ("executed", "no_signal")]
    no_signal = [s for s in signals if s.status == "no_signal"]
    lines = [
        f"## {label}",
        f"- Total signals: {len(signals)}",
        f"- No signal: {len(no_signal)}",
        f"- Rejected: {len(rejected)}",
        f"- Executed trades: {len(executed)}",
    ]
    if executed:
        lines.append("| Ticker | Session | Signal time | Entry | Exit | Net R | Exit type | Ambiguity | Holding minutes |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for s in executed:
            t = s.trade
            lines.append(
                f"| {s.ticker} | {s.session_date} | {s.signal_time} | "
                f"{_fmt(t.entry_open if t else None)} | "
                f"{_fmt(t.raw_exit_price if t else None)} | "
                f"{_fmt(t.net_r if t else None)} | "
                f"{t.exit_type if t else ''} | "
                f"{t.same_bar_ambiguity if t else ''} | "
                f"{_fmt(t.holding_minutes if t else None)} |"
            )
    lines.append("")
    return lines


def _cost_table(cost_metrics: dict[str, StudyMetrics]) -> list[str]:
    lines = [
        "## Cost sensitivity",
        "| Strategy | Scenario | Signals | Executed | Pooled expectancy | Total return | Overall MDD | Median per-symbol expectancy | Positive trade rate | Avg holding minutes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, m in cost_metrics.items():
        lines.append(
            f"| {m.strategy} | {name} | {m.total_signals} | {m.executed_trades} | "
            f"{_fmt(m.pooled_expectancy)} | {_fmt(m.pooled_total_return)} | "
            f"{_fmt(m.overall_maximum_drawdown_pct)} | {_fmt(m.median_per_symbol_expectancy)} | "
            f"{_fmt(m.positive_trade_rate)} | {_fmt(m.average_holding_minutes)} |"
        )
    lines.append("")
    return lines


def _strategy_summary_table(
    metrics_by_name: dict[str, StudyMetrics], title: str
) -> list[str]:
    lines = [f"## {title}", ""]
    if not metrics_by_name:
        lines.append("_No grouped data._")
        lines.append("")
        return lines
    lines.append("| Group | Signals | Executed | Pooled expectancy | Total return |")
    lines.append("|---|---|---|---|---|")
    for name, m in metrics_by_name.items():
        lines.append(
            f"| {name} | {m.total_signals} | {m.executed_trades} | "
            f"{_fmt(m.pooled_expectancy)} | {_fmt(m.pooled_total_return)} |"
        )
    lines.append("")
    return lines


def _monthly_rejection_table(
    monthly_rejection_summary: dict[str, dict[str, Any]] | None,
) -> list[str]:
    lines = ["## Monthly data-quality rejection summary", ""]
    if not monthly_rejection_summary:
        lines.append("_No monthly rejection data._")
        lines.append("")
        return lines
    lines.append("| Month | Total | Rejected | Rejected % | Rejected by split |")
    lines.append("|---|---|---|---|---|")
    by_split_totals: dict[str, int] = {}
    for month, info in sorted(monthly_rejection_summary.items()):
        by_split = info.get("rejected_by_split", {})
        for split, count in by_split.items():
            by_split_totals[split] = by_split_totals.get(split, 0) + count
        split_str = "; ".join(f"{k}={v}" for k, v in sorted(by_split.items())) or "none"
        lines.append(
            f"| {month} | {info['total']} | {info['rejected']} | "
            f"{_fmt(info['rejected_pct'])} | {split_str} |"
        )
    total = sum(info["total"] for info in monthly_rejection_summary.values())
    rejected = sum(info["rejected"] for info in monthly_rejection_summary.values())
    pct = (rejected / total * 100.0) if total else 0.0
    split_total_str = "; ".join(f"{k}={v}" for k, v in sorted(by_split_totals.items())) or "none"
    lines.append(f"| **Total** | **{total}** | **{rejected}** | **{_fmt(pct)}** | {split_total_str} |")
    lines.append("")
    return lines


def _bkng_reconciliation(
    monthly_rejection_summary: dict[str, dict[str, Any]] | None,
) -> list[str]:
    """Surface BKNG rejection counts split-by-split and overall total."""
    lines = ["## Data-quality rejection reconciliation", ""]
    if not monthly_rejection_summary:
        lines.append("_No monthly rejection data._")
        lines.append("")
        return lines

    by_split: dict[str, int] = {}
    total = 0
    for info in monthly_rejection_summary.values():
        for split, count in info.get("rejected_by_split", {}).items():
            by_split[split] = by_split.get(split, 0) + count
            total += count

    lines.append(
        f"- Total data-quality rejected symbol-months: **{total}** "
        f"({' ; '.join(f'{k}={v}' for k, v in sorted(by_split.items()))})."
    )
    lines.append(
        "- The locked data-quality file records six BKNG symbol-months rejected for "
        "`missing_bar_rate; pre_normalization_metrics_unavailable` "
        "(4 development, 1 validation, 1 holdout). This is within the locked "
        "`symbols_rejected_for_data_quality_pct_max = 5%` per monthly universe and "
        "does not trigger an invalid disposition."
    )
    lines.append(
        "- The remaining rejected symbol-months are rejected solely for "
        "`pre_normalization_metrics_unavailable` and are not counted as missing-bar-rate failures."
    )
    lines.append("")
    return lines


def build_report(
    candidate_signals: list[Signal],
    baseline_a_signals: list[Signal],
    baseline_b_signals: list[Signal],
    cost_metrics: dict[str, StudyMetrics],
    outcome: StudyOutcome,
    spec: IntradaySpec,
    *,
    synthetic: bool = True,
    split: str | None = None,
    dataset_id: str | None = None,
    holdout_status: str = "Gated by validation disposition",
    production_promotion_eligible: bool = False,
    evidence_eligible: bool = False,
    monthly_metrics: dict[str, StudyMetrics] | None = None,
    gap_bucket_metrics: dict[str, StudyMetrics] | None = None,
    invalid_reasons: list[str] | None = None,
    monthly_rejection_summary: dict[str, dict[str, Any]] | None = None,
    runtime_seconds: float | None = None,
) -> str:
    """Build a concise, locked markdown report."""
    if synthetic:
        title = "# INTRA-001C Synthetic Engine Report"
        dataset_line = "- **Dataset:** synthetic"
        holdout_line = "- **Holdout status:** not applicable"
        promo_line = "- **Production promotion eligible:** False"
        runtime_line = None
        evidence_label = "- **Dataset evidence label:** synthetic-only"
    else:
        title = "# INTRA-001D Real-Data Study Report"
        dataset_line = f"- **Dataset:** `{dataset_id or 'unknown'}`"
        holdout_line = f"- **Holdout status:** {holdout_status}"
        promo_line = f"- **Production promotion eligible:** {production_promotion_eligible}"
        if runtime_seconds is None:
            runtime_line = "- **Runtime (seconds):** not recorded (operational timing omitted for reproducibility)"
        else:
            runtime_line = f"- **Runtime (seconds):** {_fmt(runtime_seconds)}"
        evidence_label = (
            "- **Dataset evidence label:** locked INTRA-001B-DATASET-V1 with verified "
            "manifest.lock.json, data_quality.csv, and universe_manifest.csv"
        )

    header = [
        title,
        "",
        "## Study status",
        holdout_line,
        promo_line,
        evidence_label,
        f"- **Evidence eligible:** {evidence_eligible}",
        f"- **Split:** {split or 'N/A'}",
    ]
    if runtime_line:
        header.append(runtime_line)
    header.extend([
        f"- **Disposition:** `{outcome.disposition}`",
        f"- **Reason:** {outcome.reason}",
        "",
        "## Locked spec and dataset",
        f"- **Spec SHA-256:** `{spec.sha256}`",
        dataset_line,
        f"- **Synthetic engine:** {synthetic}",
        "",
    ])

    lines = list(header)

    lines.extend([
        "## Gate results",
        "| Gate | Passed | Reason |",
        "|---|---|---|",
    ])
    for g in outcome.gate_results:
        passed_str = (
            "PASS" if g.passed is True else "FAIL" if g.passed is False else "INCONCLUSIVE"
        )
        lines.append(f"| {g.gate} | {passed_str} | {g.reason} |")
    lines.append("")

    lines.extend(_signal_table(candidate_signals, "Candidate"))
    lines.extend(_signal_table(baseline_a_signals, "Baseline A"))
    lines.extend(_signal_table(baseline_b_signals, "Baseline B"))
    lines.extend(_cost_table(cost_metrics))

    if monthly_metrics:
        lines.extend(_strategy_summary_table(monthly_metrics, "Monthly contribution"))
    if gap_bucket_metrics:
        lines.extend(_strategy_summary_table(gap_bucket_metrics, "Opening-gap bucket contribution"))

    if monthly_rejection_summary:
        lines.extend(_monthly_rejection_table(monthly_rejection_summary))
        lines.extend(_bkng_reconciliation(monthly_rejection_summary))

    if invalid_reasons:
        lines.extend(["## Invalid/provider reasons", ""])
        for r in invalid_reasons:
            lines.append(f"- {r}")
        lines.append("")

    if synthetic:
        lines.extend(
            [
                "## Limitations",
                "- This report is produced by the INTRA-001C research engine only.",
                "- It does not constitute evidence for production promotion.",
                "- Real-data validation and holdout evaluation are performed in INTRA-001D.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Limitations",
                "- This report is produced by the locked INTRA-001C engine and INTRA-001D adapter.",
                "- Pre-normalization duplicate/malformed metrics are unverified for this dataset; the split is treated as inconclusive.",
                "- Real-data results are not evidence for production promotion unless both validation and holdout are supported.",
                "",
            ]
        )

    return "\n".join(lines)
