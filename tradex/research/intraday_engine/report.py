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


def build_report(
    candidate_signals: list[Signal],
    baseline_a_signals: list[Signal],
    baseline_b_signals: list[Signal],
    cost_metrics: dict[str, StudyMetrics],
    outcome: StudyOutcome,
    spec: IntradaySpec,
    *,
    synthetic: bool = True,
    monthly_metrics: dict[str, StudyMetrics] | None = None,
    gap_bucket_metrics: dict[str, StudyMetrics] | None = None,
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

    if monthly_metrics:
        lines.extend(_strategy_summary_table(monthly_metrics, "Monthly contribution"))
    if gap_bucket_metrics:
        lines.extend(_strategy_summary_table(gap_bucket_metrics, "Opening-gap bucket contribution"))

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
