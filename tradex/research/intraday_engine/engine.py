"""High-level engine that evaluates a synthetic ticker universe across sessions."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from .baseline_a import evaluate_baseline_a_session
from .baseline_b import evaluate_baseline_b_session
from .candidate import evaluate_candidate_session
from .gates import SampleMinimums, evaluate_gates
from .metrics import compute_grouped_metrics, compute_study_metrics
from .models import (
    CostScenario,
    DataQualitySummary,
    Session,
    Signal,
    StudyMetrics,
    StudyResult,
    TickerMeta,
)
from .normalize import evaluate_data_contract, evaluate_data_sufficiency, normalize_to_sessions
from .report import build_report
from .spec import IntradaySpec


@dataclass
class TickerInput:
    """Complete point-in-time input for one ticker."""

    ticker: str
    meta: TickerMeta
    sessions: list[Session]
    quality_summary: DataQualitySummary | None = None
    evaluation_session_dates: set[date] | None = None


def _primary_scenario(costs: list[CostScenario]) -> CostScenario:
    """Return the 5bps/0 commission primary scenario, falling back to the first."""
    for c in costs:
        if c.entry_slippage_bps == 5.0 and c.entry_commission_bps == 0.0:
            return c
    return costs[0]


def _evaluate_ticker_for_scenario(
    ticker_input: TickerInput,
    spec: IntradaySpec,
    cost_scenario: CostScenario,
) -> tuple[list[Signal], list[Signal], list[Signal]]:
    """Return candidate, baseline A, and baseline B signals under one cost scenario."""
    candidate: list[Signal] = []
    baseline_a: list[Signal] = []
    baseline_b: list[Signal] = []
    sessions = sorted(ticker_input.sessions, key=lambda s: s.session_date)
    eval_dates = ticker_input.evaluation_session_dates
    for i, session in enumerate(sessions):
        prior = sessions[:i]
        if eval_dates is not None and session.session_date not in eval_dates:
            continue
        candidate.extend(
            evaluate_candidate_session(
                ticker_input.ticker,
                ticker_input.meta,
                session,
                prior,
                cost_scenario,
                spec,
            )
        )
        baseline_a.extend(
            evaluate_baseline_a_session(
                ticker_input.ticker,
                ticker_input.meta,
                session,
                prior,
                cost_scenario,
                spec,
            )
        )
        baseline_b.extend(
            evaluate_baseline_b_session(
                ticker_input.ticker,
                ticker_input.meta,
                session,
                prior,
                cost_scenario,
                spec,
            )
        )
    return candidate, baseline_a, baseline_b


def _collect_quality_results(
    ticker_inputs: list[TickerInput],
    *,
    extra_sufficiency_fail: bool = False,
    extra_sufficiency_reasons: list[str] | None = None,
) -> tuple[bool, bool, list[str], list[str], list[DataQualitySummary]]:
    """Evaluate data contract and sufficiency across all ticker inputs.

    Returns ``(data_contract_valid, data_sufficiency_passed, contract_reasons,
    sufficiency_reasons, quality_summaries)``.  Contract violations make a study
    ``invalid``; sufficiency shortfalls make it ``inconclusive``.
    """
    from collections import Counter

    summaries = [ti.quality_summary for ti in ticker_inputs if ti.quality_summary is not None]
    contract_reasons: list[str] = []
    sufficiency_counter: Counter[str] = Counter()
    any_sufficiency_fail = extra_sufficiency_fail
    if extra_sufficiency_reasons:
        for r in extra_sufficiency_reasons:
            sufficiency_counter[r] += 1
    for summary in summaries:
        valid, reasons = evaluate_data_contract(summary)
        if not valid:
            contract_reasons.extend(f"{summary.ticker}:{r}" for r in reasons)
        suff_ok, suff_reasons = evaluate_data_sufficiency(summary)
        if not suff_ok:
            any_sufficiency_fail = True
            for r in suff_reasons:
                sufficiency_counter[r] += 1
    data_contract_valid = not contract_reasons
    sufficiency_reasons = [
        f"{reason} ({count} symbol-month{'s' if count != 1 else ''})"
        for reason, count in sorted(sufficiency_counter.items())
    ]
    return data_contract_valid, not any_sufficiency_fail, contract_reasons, sufficiency_reasons, summaries


def run_study(
    ticker_inputs: list[TickerInput],
    spec: IntradaySpec,
    *,
    synthetic: bool = True,
    evidence_eligible: bool = False,
    generated_at: datetime | None = None,
    sample_minimums: SampleMinimums | None = None,
    extra_sufficiency_fail: bool = False,
    extra_sufficiency_reasons: list[str] | None = None,
) -> StudyResult:
    """Run the full engine across all tickers, sessions, and cost scenarios."""
    # Synthetic artifacts are never evidence-eligible.
    if synthetic:
        evidence_eligible = False

    if generated_at is None:
        generated_at = datetime(2025, 1, 1, tzinfo=UTC)
        generated_at_fixed = True
    else:
        generated_at_fixed = False

    # Combine the explicit primary scenario with all sensitivity scenarios.
    all_scenarios = [spec.primary_cost_scenario()] + spec.all_cost_scenarios()
    seen: set[str] = set()
    cost_scenarios: list[CostScenario] = []
    for c in all_scenarios:
        if c.name not in seen:
            seen.add(c.name)
            cost_scenarios.append(c)

    primary = _primary_scenario(cost_scenarios)

    ticker_meta_map = {ti.ticker: ti.meta for ti in ticker_inputs}

    # Strategy x cost metrics, plus a flat cost_scenarios map for backward-compatible access.
    metrics_by_strategy: dict[str, dict[str, StudyMetrics]] = {
        "candidate": {},
        "baseline_a": {},
        "baseline_b": {},
    }
    cost_metrics: dict[str, StudyMetrics] = {}

    candidate_signals_primary: list[Signal] = []
    baseline_a_signals_primary: list[Signal] = []
    baseline_b_signals_primary: list[Signal] = []

    for costs in cost_scenarios:
        cand: list[Signal] = []
        base_a: list[Signal] = []
        base_b: list[Signal] = []
        for ti in ticker_inputs:
            c, a, b = _evaluate_ticker_for_scenario(ti, spec, costs)
            cand.extend(c)
            base_a.extend(a)
            base_b.extend(b)

        cand_metrics = compute_study_metrics("candidate", cand, ticker_meta_map, costs)
        base_a_metrics = compute_study_metrics("baseline_a", base_a, ticker_meta_map, costs)
        base_b_metrics = compute_study_metrics("baseline_b", base_b, ticker_meta_map, costs)

        metrics_by_strategy["candidate"][costs.name] = cand_metrics
        metrics_by_strategy["baseline_a"][costs.name] = base_a_metrics
        metrics_by_strategy["baseline_b"][costs.name] = base_b_metrics

        cost_metrics[f"candidate:{costs.name}"] = cand_metrics
        cost_metrics[f"baseline_a:{costs.name}"] = base_a_metrics
        cost_metrics[f"baseline_b:{costs.name}"] = base_b_metrics

        if costs is primary:
            candidate_signals_primary = cand
            baseline_a_signals_primary = base_a
            baseline_b_signals_primary = base_b

    candidate_5bps = metrics_by_strategy["candidate"][primary.name]
    baseline_a_5bps = metrics_by_strategy["baseline_a"][primary.name]
    baseline_b_5bps = metrics_by_strategy["baseline_b"][primary.name]
    candidate_10bps = metrics_by_strategy["candidate"].get(
        "slippage_10bps", candidate_5bps
    )

    (
        data_contract_valid,
        data_sufficiency_passed,
        contract_reasons,
        sufficiency_reasons,
        quality_summaries,
    ) = _collect_quality_results(
        ticker_inputs,
        extra_sufficiency_fail=extra_sufficiency_fail,
        extra_sufficiency_reasons=extra_sufficiency_reasons,
    )

    outcome = evaluate_gates(
        candidate_5bps,
        baseline_a_5bps,
        baseline_b_5bps,
        candidate_10bps,
        sample_minimums=sample_minimums,
        data_sufficiency_passed=data_sufficiency_passed,
        data_contract_valid=data_contract_valid,
        contract_reasons=contract_reasons,
        sufficiency_reasons=sufficiency_reasons,
    )

    monthly_metrics: dict[str, StudyMetrics] = {}
    gap_bucket_metrics: dict[str, StudyMetrics] = {}
    for strategy, signals in [
        ("candidate", candidate_signals_primary),
        ("baseline_a", baseline_a_signals_primary),
        ("baseline_b", baseline_b_signals_primary),
    ]:
        for key, m in compute_grouped_metrics(
            strategy, signals, ticker_meta_map, primary, by_month=True
        ).items():
            monthly_metrics[f"{strategy}:{key}"] = m
        for key, m in compute_grouped_metrics(
            strategy, signals, ticker_meta_map, primary, by_gap=True
        ).items():
            gap_bucket_metrics[f"{strategy}:{key}"] = m

    report = build_report(
        candidate_signals_primary,
        baseline_a_signals_primary,
        baseline_b_signals_primary,
        cost_metrics,
        outcome,
        spec,
        synthetic=synthetic,
        monthly_metrics=monthly_metrics,
        gap_bucket_metrics=gap_bucket_metrics,
    )

    trades = defaultdict(list)
    for s in candidate_signals_primary + baseline_a_signals_primary + baseline_b_signals_primary:
        if s.trade is not None:
            trades[s.strategy].append(s.trade)

    return StudyResult(
        spec_sha256=spec.sha256,
        engine_version="1.0.0",
        synthetic=synthetic,
        evidence_eligible=evidence_eligible,
        generated_at=generated_at,
        generated_at_fixed=generated_at_fixed,
        cost_scenarios=cost_metrics,
        metrics_by_strategy=metrics_by_strategy,
        data_quality_summaries=quality_summaries,
        monthly_metrics=monthly_metrics,
        gap_bucket_metrics=gap_bucket_metrics,
        candidate_signals=candidate_signals_primary,
        baseline_a_signals=baseline_a_signals_primary,
        baseline_b_signals=baseline_b_signals_primary,
        trades=dict(trades),
        report_markdown=report,
        outcome=outcome,
        invalid_reasons=contract_reasons if not data_contract_valid else [],
    )


def build_ticker_input_from_df(
    ticker: str,
    meta: TickerMeta,
    df: pd.DataFrame,
    spec: IntradaySpec,
) -> TickerInput:
    """Normalize a raw OHLCV DataFrame into a ``TickerInput``."""
    sessions, summary = normalize_to_sessions(df, ticker)
    return TickerInput(ticker=ticker, meta=meta, sessions=sessions, quality_summary=summary)
