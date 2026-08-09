"""Markdown/JSON report generation for the INTRA-001C engine."""
from __future__ import annotations

from .models import Signal, StudyMetrics, StudyOutcome
from .spec import IntradaySpec


def _fmt(value: float | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float) and value != int(value):
        return f"{value:.4f}"
    return str(value)


def _signal_table(signals: list[Signal], label: str) -> list[str]:
    executed = [s for s in signals if s.status == "executed"]
    rejected = [s for s in signals if s.status != "executed"]
    lines = [
        f"## {label}",
        f"- Total signals: {len(signals)}",
        f"- Executed trades: {len(executed)}",
        f"- Rejected/no-signal: {len(rejected)}",
    ]
    if executed:
        lines.append("| Ticker | Session | Signal time | Entry | Exit | Net R | Exit type | Ambiguity |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for s in executed:
            t = s.trade
            lines.append(
                f"| {s.ticker} | {s.session_date} | {s.signal_time} | "
                f"{_fmt(t.entry_open if t else None)} | "
                f"{_fmt(t.raw_exit_price if t else None)} | "
                f"{_fmt(t.net_r if t else None)} | "
                f"{t.exit_type if t else ''} | "
                f"{t.same_bar_ambiguity if t else ''} |"
            )
    lines.append("")
    return lines


def _cost_table(cost_metrics: dict[str, StudyMetrics]) -> list[str]:
    lines = [
        "## Cost sensitivity",
        "| Scenario | Trades | Pooled expectancy | Total return | Overall MDD | Median per-symbol expectancy |",
        "|---|---|---|---|---|---|",
    ]
    for name, m in cost_metrics.items():
        lines.append(
            f"| {name} | {m.total_trades} | {_fmt(m.pooled_expectancy)} | "
            f"{_fmt(m.pooled_total_return)} | {_fmt(m.overall_maximum_drawdown_pct)} | "
            f"{_fmt(m.median_per_symbol_expectancy)} |"
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
) -> str:
    """Build a concise markdown report."""
    lines = [
        "# INTRA-001C Synthetic Engine Report",
        "",
        f"- **Spec SHA-256:** `{spec.sha256}`",
        f"- **Synthetic:** {synthetic}",
        "- **Evidence eligible:** False",
        f"- **Disposition:** `{outcome.disposition}`",
        f"- **Reason:** {outcome.reason}",
        "",
        "## Gate results",
        "| Gate | Passed | Reason |",
        "|---|---|---|",
    ]
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

    lines.extend(
        [
            "## Limitations",
            "- This report is produced by the INTRA-001C research engine only.",
            "- It does not constitute evidence for production promotion.",
            "- Real-data validation and holdout evaluation are performed in INTRA-001D.",
            "",
        ]
    )

    return "\n".join(lines)
