"""Per-symbol and pooled metric calculations for the INTRA-001C engine."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from .models import CostScenario, PerSymbolMetrics, Signal, StudyMetrics, Trade


def _safe_mean(values: list[float | None]) -> float | None:
    filtered = [v for v in values if v is not None and math.isfinite(v)]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _safe_median(values: list[float | None]) -> float | None:
    """Return median, filtering None and preserving finite/infinite values."""
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None
    s = sorted(filtered)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    mid = (s[n // 2 - 1] + s[n // 2]) / 2.0
    if math.isinf(mid):
        return mid
    return mid


def _compute_drawdown(equity_curve: list[float]) -> list[float]:
    peak = equity_curve[0]
    dd: list[float] = []
    for val in equity_curve:
        peak = max(peak, val)
        dd.append(100.0 * (val - peak) / peak)
    return dd


def _profit_factor_case(
    trade_count: int, gross_profit: float, gross_loss: float
) -> tuple[str, float | None, float | None]:
    if trade_count == 0:
        return "no_trade", None, None
    if gross_profit == 0 and gross_loss == 0:
        return "break_even", 0.0, 0.0
    if gross_profit == 0 and gross_loss < 0:
        return "no_profit", 0.0, 0.0
    if gross_profit > 0 and gross_loss == 0:
        return "no_loss_positive", None, float("inf")
    if gross_profit > 0 and gross_loss < 0:
        value = gross_profit / abs(gross_loss)
        return "finite", value, value
    # Defensive: treat other sign combinations as finite with the computed ratio.
    denom = abs(gross_loss)
    value = gross_profit / denom if denom else None
    return "finite", value, value


def _per_symbol(trades: list[Trade], is_etf: bool) -> PerSymbolMetrics:
    trades = sorted(trades, key=lambda t: t.signal_time)
    net_r = [t.net_r for t in trades if t.net_r is not None and math.isfinite(t.net_r)]
    trade_count = len(net_r)
    total_return = sum(net_r) if net_r else 0.0
    mean_expectancy = total_return / trade_count if trade_count else 0.0
    equity_curve = [100.0]
    for r in net_r:
        equity_curve.append(equity_curve[-1] + r)
    dd = _compute_drawdown(equity_curve)
    max_dd = min(dd) if dd else 0.0

    gross_profit = sum(r for r in net_r if r > 0)
    gross_loss = sum(r for r in net_r if r < 0)
    case, value, order = _profit_factor_case(trade_count, gross_profit, gross_loss)

    return PerSymbolMetrics(
        ticker=trades[0].ticker if trades else "",
        is_etf=is_etf,
        trade_count=trade_count,
        total_return=total_return,
        mean_expectancy=mean_expectancy,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor_value=value,
        profit_factor_case=case,
        profit_factor_order=order,
        maximum_drawdown_pct=max_dd,
        equity_curve=equity_curve,
        positive=mean_expectancy > 0,
    )


def _ticker_meta_etf(ticker: str, ticker_meta_map: dict[str, Any]) -> bool:
    meta = ticker_meta_map.get(ticker)
    return bool(getattr(meta, "is_etf", False)) if meta else False


def _month_key(session_date: date) -> str:
    return session_date.strftime("%Y-%m")


def _opening_gap_bucket(gap_pct: float | None) -> str:
    if gap_pct is None:
        return "unknown"
    if gap_pct < -0.01:
        return "below_minus_1pct"
    if gap_pct < 0:
        return "minus_1pct_to_0"
    if gap_pct == 0:
        return "zero"
    if gap_pct <= 0.01:
        return "0_to_plus_1pct"
    return "above_plus_1pct"


def _compute_signal_counts(
    signals: list[Signal],
) -> tuple[int, int, int, int, dict[str, int], dict[str, int], float | None, float | None]:
    """Return total, executed, rejected, no_signal, rejection_counts, exit_counts, positive_trade_rate, avg_holding_minutes."""
    total = len(signals)
    executed = [s for s in signals if s.status == "executed" and s.trade is not None]
    rejected = [s for s in signals if s.status not in ("executed", "no_signal")]
    no_signal = [s for s in signals if s.status == "no_signal"]

    rejection_counts: dict[str, int] = defaultdict(int)
    for s in rejected:
        rejection_counts[s.status] += 1

    exit_counts: dict[str, int] = defaultdict(int)
    positive = 0
    holding_minutes: list[float] = []
    for s in executed:
        t = s.trade
        if t is None:
            continue
        exit_counts[t.exit_type or "unknown"] += 1
        if t.net_r is not None and t.net_r > 0:
            positive += 1
        holding_minutes.append(t.holding_minutes)

    positive_rate = positive / len(executed) if executed else None
    avg_holding = _safe_mean(holding_minutes)

    return (
        total,
        len(executed),
        len(rejected),
        len(no_signal),
        dict(rejection_counts),
        dict(exit_counts),
        positive_rate,
        avg_holding,
    )


def compute_study_metrics(
    strategy: str,
    signals: list[Signal],
    ticker_meta_map: dict[str, Any],
    cost_scenario: CostScenario,
) -> StudyMetrics:
    """Compute aggregate metrics for one strategy and cost scenario."""
    (
        total_signals,
        executed_trades,
        rejected_signals,
        no_signal_count,
        rejection_counts,
        exit_counts,
        positive_trade_rate,
        average_holding_minutes,
    ) = _compute_signal_counts(signals)

    trades = [s.trade for s in signals if s.status == "executed" and s.trade is not None]
    trades = sorted(trades, key=lambda t: t.signal_time)

    by_ticker: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_ticker[t.ticker].append(t)

    per_symbol: dict[str, PerSymbolMetrics] = {}
    for ticker, tlist in by_ticker.items():
        per_symbol[ticker] = _per_symbol(tlist, _ticker_meta_etf(ticker, ticker_meta_map))

    total_trades = len(trades)
    net_r = [t.net_r for t in trades if t.net_r is not None and math.isfinite(t.net_r)]
    pooled_expectancy = sum(net_r) / total_trades if total_trades else 0.0
    pooled_total_return = sum(net_r)

    equity_curve = [100.0]
    for r in net_r:
        equity_curve.append(equity_curve[-1] + r)
    dd = _compute_drawdown(equity_curve)
    overall_mdd = min(dd) if dd else 0.0

    stock_trades = [t for t in trades if not _ticker_meta_etf(t.ticker, ticker_meta_map)]
    etf_trades = [t for t in trades if _ticker_meta_etf(t.ticker, ticker_meta_map)]
    stock_net_r = [t.net_r for t in stock_trades if t.net_r is not None]
    etf_net_r = [t.net_r for t in etf_trades if t.net_r is not None]
    stock_expectancy = sum(stock_net_r) / len(stock_trades) if stock_trades else 0.0
    etf_expectancy = sum(etf_net_r) / len(etf_trades) if etf_trades else 0.0

    represented = list(per_symbol.values())
    stock_represented = [m for m in represented if not m.is_etf and m.trade_count > 0]
    etf_represented = [m for m in represented if m.is_etf and m.trade_count > 0]

    means = [m.mean_expectancy for m in represented if m.trade_count > 0]
    total_returns = [m.total_return for m in represented if m.trade_count > 0]
    mdds = [m.maximum_drawdown_pct for m in represented if m.trade_count > 0]
    pf_orders = [
        m.profit_factor_order
        for m in represented
        if m.trade_count > 0 and m.profit_factor_order is not None
    ]
    pf_values_all = [
        (m.profit_factor_value if m.profit_factor_value is not None else float("inf"))
        for m in represented
        if m.trade_count > 0 and m.profit_factor_case != "no_trade"
    ]

    # Median computability for profit factor: at least half of represented symbols.
    n_represented = len([m for m in represented if m.trade_count > 0])
    computable_pf = len(pf_orders)
    pf_median_order: float | None = None
    pf_median_value: float | None = None
    if n_represented > 0 and computable_pf >= math.ceil(n_represented / 2):
        pf_median_order = _safe_median(pf_orders)
        raw_median_value = _safe_median(pf_values_all)
        if raw_median_value is not None and math.isinf(raw_median_value):
            pf_median_value = None
        else:
            pf_median_value = raw_median_value

    positive_count = sum(1 for m in represented if m.trade_count > 0 and m.positive)
    positive_rate = positive_count / n_represented if n_represented else None

    # Concentration rules use per-symbol aggregated contributions.
    trade_counts = [m.trade_count for m in represented if m.trade_count > 0]
    max_trade_count = max(trade_counts) if trade_counts else 0
    trade_count_concentration = max_trade_count / total_trades if total_trades else 0.0

    positive_totals = [
        m.total_return for m in represented if m.trade_count > 0 and m.total_return > 0
    ]
    negative_totals = [
        m.total_return for m in represented if m.trade_count > 0 and m.total_return < 0
    ]
    net_profit_concentration: float | None = None
    absolute_loss_concentration: float | None = None
    if pooled_total_return > 0:
        if positive_totals:
            net_profit_concentration = max(positive_totals) / pooled_total_return
    else:
        if negative_totals:
            absolute_loss_concentration = max(abs(v) for v in negative_totals) / sum(
                abs(v) for v in negative_totals
            )

    return StudyMetrics(
        strategy=strategy,
        cost_scenario=cost_scenario,
        total_signals=total_signals,
        executed_trades=executed_trades,
        rejected_signals=rejected_signals,
        no_signal_count=no_signal_count,
        total_trades=total_trades,
        pooled_expectancy=pooled_expectancy,
        pooled_total_return=pooled_total_return,
        overall_maximum_drawdown_pct=overall_mdd,
        median_per_symbol_expectancy=_safe_median(means),
        equal_weighted_per_symbol_mean_expectancy=(
            sum(means) / len(means) if means else None
        ),
        positive_symbol_rate=positive_rate,
        median_per_symbol_total_return=_safe_median(total_returns),
        median_per_symbol_maximum_drawdown_pct=_safe_median(mdds),
        median_per_symbol_profit_factor_order=pf_median_order,
        median_per_symbol_profit_factor_value=pf_median_value,
        trade_count_concentration=trade_count_concentration,
        net_profit_concentration=net_profit_concentration,
        absolute_loss_concentration=absolute_loss_concentration,
        stock_stratum_trade_count=len(stock_trades),
        etf_stratum_trade_count=len(etf_trades),
        stock_stratum_pooled_expectancy=stock_expectancy,
        etf_stratum_pooled_expectancy=etf_expectancy,
        represented_stock_symbols=len(stock_represented),
        represented_etf_symbols=len(etf_represented),
        rejection_counts=rejection_counts,
        exit_counts=exit_counts,
        positive_trade_rate=positive_trade_rate,
        average_holding_minutes=average_holding_minutes,
        per_symbol=per_symbol,
    )


def compute_grouped_metrics(
    strategy: str,
    signals: list[Signal],
    ticker_meta_map: dict[str, Any],
    cost_scenario: CostScenario,
    *,
    by_month: bool = False,
    by_gap: bool = False,
) -> dict[str, StudyMetrics]:
    """Compute per-group metrics (month or opening-gap bucket) for a strategy."""
    if by_month:
        group_fn = lambda s: _month_key(s.trade.session_date) if s.trade else "unknown"
    elif by_gap:
        group_fn = lambda s: _opening_gap_bucket(s.trade.opening_gap_pct if s.trade else None)
    else:
        return {}

    grouped: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        grouped[group_fn(s)].append(s)

    result: dict[str, StudyMetrics] = {}
    for key, group in grouped.items():
        result[key] = compute_study_metrics(strategy, group, ticker_meta_map, cost_scenario)
    return result


def paired_symbol_outperformance(
    candidate_per_symbol: dict[str, PerSymbolMetrics],
    baseline_per_symbol: dict[str, PerSymbolMetrics],
) -> tuple[int, float]:
    """Return paired overlap count and outperformance rate of candidate vs baseline."""
    overlap = 0
    outperf = 0
    for ticker, cand in candidate_per_symbol.items():
        base = baseline_per_symbol.get(ticker)
        if base is None or cand.trade_count == 0 or base.trade_count == 0:
            continue
        overlap += 1
        if cand.mean_expectancy > base.mean_expectancy:
            outperf += 1
    rate = outperf / overlap if overlap else 0.0
    return overlap, rate
