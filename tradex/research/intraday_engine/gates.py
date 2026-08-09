"""Locked validation-gate evaluator for INTRA-001C."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .metrics import paired_symbol_outperformance
from .models import GateResult, StudyMetrics, StudyOutcome


@dataclass(frozen=True)
class SampleMinimums:
    executed_candidate_trades_min: int = 300
    represented_stock_symbols_min: int = 25
    represented_etfs_min: int = 8
    stock_stratum_trades_min: int = 100
    etf_stratum_trades_min: int = 75
    paired_symbol_overlap_min: int = 15
    single_ticker_max_pct_of_trades: float = 10.0
    single_ticker_max_pct_of_net_profit: float = 20.0


def _check_sample_minimums(
    candidate: StudyMetrics, sample: SampleMinimums
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if candidate.total_trades < sample.executed_candidate_trades_min:
        reasons.append(
            f"executed_candidate_trades_{candidate.total_trades}_below_{sample.executed_candidate_trades_min}"
        )
    if candidate.represented_stock_symbols < sample.represented_stock_symbols_min:
        reasons.append(
            f"represented_stock_symbols_{candidate.represented_stock_symbols}_below_{sample.represented_stock_symbols_min}"
        )
    if candidate.represented_etf_symbols < sample.represented_etfs_min:
        reasons.append(
            f"represented_etfs_{candidate.represented_etf_symbols}_below_{sample.represented_etfs_min}"
        )
    if candidate.stock_stratum_trade_count < sample.stock_stratum_trades_min:
        reasons.append(
            f"stock_stratum_trades_{candidate.stock_stratum_trade_count}_below_{sample.stock_stratum_trades_min}"
        )
    if candidate.etf_stratum_trade_count < sample.etf_stratum_trades_min:
        reasons.append(
            f"etf_stratum_trades_{candidate.etf_stratum_trade_count}_below_{sample.etf_stratum_trades_min}"
        )
    if candidate.trade_count_concentration * 100 > sample.single_ticker_max_pct_of_trades:
        reasons.append(
            f"trade_count_concentration_{candidate.trade_count_concentration * 100:.2f}%_exceeds_{sample.single_ticker_max_pct_of_trades}%"
        )
    if candidate.net_profit_concentration is not None and (
        candidate.net_profit_concentration * 100 > sample.single_ticker_max_pct_of_net_profit
    ):
        reasons.append(
            f"net_profit_concentration_{candidate.net_profit_concentration * 100:.2f}%_exceeds_{sample.single_ticker_max_pct_of_net_profit}%"
        )
    return (not reasons), reasons


def _pf_order_passes_threshold(order: float | None, threshold: float) -> bool:
    if order is None:
        return False
    if math.isinf(order):
        return True
    return order >= threshold


def _pf_order_gte(candidate: float | None, baseline: float | None) -> bool | None:
    """Compare profit-factor orders; None when either is not computable."""
    if candidate is None or baseline is None:
        return None
    if math.isinf(candidate) and not math.isinf(baseline):
        return True
    if math.isinf(baseline) and not math.isinf(candidate):
        return False
    if math.isinf(candidate) and math.isinf(baseline):
        return True
    return candidate >= baseline


def evaluate_gates(
    candidate: StudyMetrics,
    baseline_a: StudyMetrics,
    baseline_b: StudyMetrics,
    candidate_10bps: StudyMetrics,
    *,
    sample_minimums: SampleMinimums | None = None,
    data_sufficiency_passed: bool = True,
    pf_threshold: float = 1.05,
    positive_symbol_threshold: float = 0.55,
    paired_outperform_threshold: float = 0.55,
    mdd_tolerance_pct: float = 2.0,
    expectancy_lift_vs_a: float = 0.05,
    expectancy_lift_vs_b: float = 0.03,
) -> StudyOutcome:
    """Evaluate validation gates and produce a locked disposition."""
    if sample_minimums is None:
        sample_minimums = SampleMinimums()

    gate_results: list[GateResult] = []

    sample_met, sample_reasons = _check_sample_minimums(candidate, sample_minimums)
    if not data_sufficiency_passed:
        sample_met = False
        sample_reasons.append("data_sufficiency_failed")

    gate_results.append(
        GateResult(
            gate="1_sample_and_data_sufficiency",
            passed=sample_met,
            reason="; ".join(sample_reasons) if sample_reasons else "ok",
        )
    )

    def _gate(name: str, passed: bool | None, reason: str) -> None:
        gate_results.append(GateResult(gate=name, passed=passed, reason=reason))

    _gate(
        "2_candidate_pooled_expectancy_positive_5bps",
        candidate.pooled_expectancy > 0,
        f"pooled_expectancy={candidate.pooled_expectancy:.4f}",
    )

    cand_med = candidate.median_per_symbol_expectancy
    base_a_med = baseline_a.median_per_symbol_expectancy
    base_b_med = baseline_b.median_per_symbol_expectancy

    if cand_med is None or base_a_med is None:
        passed = None
        reason = "median_per_symbol_expectancy_not_computable"
    else:
        passed = cand_med >= base_a_med + expectancy_lift_vs_a
        reason = f"candidate={cand_med:.4f}_baseline_a={base_a_med:.4f}_lift_required={expectancy_lift_vs_a}"
    _gate("3_candidate_median_expectancy_vs_baseline_a", passed, reason)

    if cand_med is None or base_b_med is None:
        passed = None
        reason = "median_per_symbol_expectancy_not_computable"
    else:
        passed = cand_med >= base_b_med + expectancy_lift_vs_b
        reason = f"candidate={cand_med:.4f}_baseline_b={base_b_med:.4f}_lift_required={expectancy_lift_vs_b}"
    _gate("4_candidate_median_expectancy_vs_baseline_b", passed, reason)

    cand_pf = candidate.median_per_symbol_profit_factor_order
    if cand_pf is None:
        passed = None
        reason = "profit_factor_median_not_computable"
    else:
        passed = _pf_order_passes_threshold(cand_pf, pf_threshold)
        reason = f"median_pf_order={cand_pf}"
    _gate("5_candidate_median_profit_factor_threshold", passed, reason)

    vs_a = _pf_order_gte(cand_pf, baseline_a.median_per_symbol_profit_factor_order)
    vs_b = _pf_order_gte(cand_pf, baseline_b.median_per_symbol_profit_factor_order)
    if vs_a is None or vs_b is None:
        passed = None
        reason = "profit_factor_median_not_comparable"
    else:
        passed = vs_a and vs_b
        reason = f"candidate={cand_pf}_vs_a={baseline_a.median_per_symbol_profit_factor_order}_vs_b={baseline_b.median_per_symbol_profit_factor_order}"
    _gate("6_candidate_median_profit_factor_not_below_baselines", passed, reason)

    pos_rate = candidate.positive_symbol_rate
    if pos_rate is None:
        passed = None
        reason = "positive_symbol_rate_not_computable"
    else:
        passed = pos_rate >= positive_symbol_threshold
        reason = f"positive_symbol_rate={pos_rate:.4f}"
    _gate("7_positive_symbol_rate", passed, reason)

    overlap, rate = paired_symbol_outperformance(
        candidate.per_symbol, baseline_a.per_symbol
    )
    if overlap < sample_minimums.paired_symbol_overlap_min:
        passed = None
        reason = f"paired_overlap_{overlap}_below_{sample_minimums.paired_symbol_overlap_min}"
    else:
        passed = rate >= paired_outperform_threshold
        reason = f"paired_overlap={overlap}_outperform_rate={rate:.4f}"
    _gate("8_paired_symbol_outperformance_vs_baseline_a", passed, reason)

    cand_mdd = candidate.median_per_symbol_maximum_drawdown_pct
    base_mdd = baseline_a.median_per_symbol_maximum_drawdown_pct
    if cand_mdd is None or base_mdd is None:
        passed = None
        reason = "median_mdd_not_computable"
    else:
        passed = cand_mdd >= base_mdd - mdd_tolerance_pct
        reason = f"candidate_mdd={cand_mdd:.4f}_baseline_mdd={base_mdd:.4f}_tolerance={mdd_tolerance_pct}"
    _gate("9_median_drawdown_not_worse_than_baseline", passed, reason)

    strata_ok = (
        candidate.stock_stratum_pooled_expectancy >= 0
        and candidate.etf_stratum_pooled_expectancy >= 0
    )
    _gate(
        "10_stock_and_etf_strata_nonneg_expectancy",
        strata_ok,
        f"stock={candidate.stock_stratum_pooled_expectancy:.4f}_etf={candidate.etf_stratum_pooled_expectancy:.4f}",
    )

    _gate(
        "11_candidate_pooled_expectancy_nonneg_10bps",
        candidate_10bps.pooled_expectancy >= 0,
        f"pooled_expectancy_10bps={candidate_10bps.pooled_expectancy:.4f}",
    )

    conc_ok = (
        candidate.trade_count_concentration * 100
        <= sample_minimums.single_ticker_max_pct_of_trades
    ) and (
        candidate.net_profit_concentration is None
        or candidate.net_profit_concentration * 100
        <= sample_minimums.single_ticker_max_pct_of_net_profit
    )
    _gate("12_concentration_limits", conc_ok, "concentration_within_limits")

    # Determine disposition.
    if not sample_met:
        disposition = "inconclusive"
        reason = "sample_or_data_sufficiency_minimums_not_met"
    elif any(g.passed is None for g in gate_results):
        disposition = "inconclusive"
        reason = "required_gate_not_computable"
    elif all(g.passed for g in gate_results):
        disposition = "supported"
        reason = "all_gates_passed"
    else:
        disposition = "not_supported"
        failed = [g.gate for g in gate_results if g.passed is False]
        reason = f"gates_failed: {', '.join(failed)}"

    return StudyOutcome(
        disposition=disposition,
        reason=reason,
        gate_results=gate_results,
        sample_met=sample_met,
    )
