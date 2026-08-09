"""High-level engine that evaluates a synthetic ticker universe across sessions."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from .baseline_a import evaluate_baseline_a_session
from .baseline_b import evaluate_baseline_b_session
from .candidate import evaluate_candidate_session
from .gates import evaluate_gates
from .metrics import compute_study_metrics
from .models import CostScenario, Session, Signal, StudyMetrics, StudyResult, TickerMeta
from .normalize import normalize_to_sessions
from .spec import IntradaySpec


@dataclass
class TickerInput:
    """Complete point-in-time input for one ticker."""

    ticker: str
    meta: TickerMeta
    sessions: list[Session]


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
    for i, session in enumerate(sessions):
        prior = sessions[:i]
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


def run_study(
    ticker_inputs: list[TickerInput],
    spec: IntradaySpec,
    *,
    synthetic: bool = True,
    evidence_eligible: bool = False,
) -> StudyResult:
    """Run the full engine across all tickers, sessions, and cost scenarios."""
    from .report import build_report

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

    cost_metrics: dict[str, StudyMetrics] = {}
    candidate_signals_primary: list[Signal] = []
    baseline_a_signals_primary: list[Signal] = []
    baseline_b_signals_primary: list[Signal] = []
    candidate_5bps: StudyMetrics | None = None
    baseline_a_5bps: StudyMetrics | None = None
    baseline_b_5bps: StudyMetrics | None = None
    candidate_10bps: StudyMetrics | None = None

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

        cost_metrics[costs.name] = cand_metrics

        if costs is primary:
            candidate_signals_primary = cand
            baseline_a_signals_primary = base_a
            baseline_b_signals_primary = base_b
            candidate_5bps = cand_metrics
            baseline_a_5bps = base_a_metrics
            baseline_b_5bps = base_b_metrics
        if costs.name == "slippage_10bps":
            candidate_10bps = cand_metrics

    if candidate_5bps is None:
        candidate_5bps = cost_metrics[cost_scenarios[0].name]
    if candidate_10bps is None:
        candidate_10bps = candidate_5bps
    if baseline_a_5bps is None:
        baseline_a_5bps = compute_study_metrics(
            "baseline_a", baseline_a_signals_primary, ticker_meta_map, primary
        )
    if baseline_b_5bps is None:
        baseline_b_5bps = compute_study_metrics(
            "baseline_b", baseline_b_signals_primary, ticker_meta_map, primary
        )

    outcome = evaluate_gates(
        candidate_5bps,
        baseline_a_5bps,
        baseline_b_5bps,
        candidate_10bps,
    )

    report = build_report(
        candidate_signals_primary,
        baseline_a_signals_primary,
        baseline_b_signals_primary,
        cost_metrics,
        outcome,
        spec,
        synthetic=synthetic,
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
        generated_at=datetime.now(UTC),
        cost_scenarios=cost_metrics,
        candidate_signals=candidate_signals_primary,
        baseline_a_signals=baseline_a_signals_primary,
        baseline_b_signals=baseline_b_signals_primary,
        trades=dict(trades),
        report_markdown=report,
        outcome=outcome,
    )


def build_ticker_input_from_df(
    ticker: str,
    meta: TickerMeta,
    df: pd.DataFrame,
    spec: IntradaySpec,
) -> TickerInput:
    """Normalize a raw OHLCV DataFrame into a ``TickerInput``."""
    sessions, _ = normalize_to_sessions(df, ticker)
    return TickerInput(ticker=ticker, meta=meta, sessions=sessions)
