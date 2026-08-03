"""Metrics, bootstrap confidence intervals, and evidence gates."""
from __future__ import annotations

import random
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from .models import Observation, PeriodMetrics, PromotionDecision, StudySpec, TickerMetrics


def _rnd(value: Any, digits: int = 6) -> Any:
    """Round finite floats to a stable decimal precision; pass through other types."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if not np.isfinite(f):
            return None
        return round(f, digits)
    if isinstance(value, (list, tuple)):
        return [_rnd(v, digits) for v in value]
    if isinstance(value, dict):
        return {str(k): _rnd(v, digits) for k, v in value.items()}
    try:
        f = float(value)
        if not np.isfinite(f):
            return None
        return round(f, digits)
    except (TypeError, ValueError):
        return value


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return _rnd(float(np.nanmean(values)))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return _rnd(float(np.nanmedian(values)))


def _win_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return _rnd(sum(1 for v in values if v > 0) / len(values))


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return _rnd(float(np.nanpercentile(values, q)))


def _returns_distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "count": len(values),
        "mean": _mean(values),
        "median": _median(values),
        "p05": _percentile(values, 5.0),
        "p25": _percentile(values, 25.0),
        "p50": _percentile(values, 50.0),
        "p75": _percentile(values, 75.0),
        "p95": _percentile(values, 95.0),
        "win_rate": _win_rate(values),
    }


def _ticker_cluster_bootstrap(
    observations: list[Observation],
    slippage_key: str,
    seed: int,
    resamples: int = 5000,
) -> tuple[float | None, float | None, float | None]:
    """Two-level ticker-cluster bootstrap of the pooled mean return.

    At each replicate, sample tickers with replacement and then sample that
    ticker's returns with replacement. The point estimate is the pooled mean
    of all original returns. The 95% CI uses the 2.5th and 97.5th percentiles.
    """
    by_ticker: dict[str, list[float]] = {}
    for obs in observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None or not np.isfinite(net):
            continue
        by_ticker.setdefault(obs.ticker, []).append(net)

    if not by_ticker:
        return None, None, None

    tickers = list(by_ticker.keys())
    all_returns = [r for returns in by_ticker.values() for r in returns]
    point = _rnd(float(np.nanmean(all_returns)))

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        for t in rng.choices(tickers, k=len(tickers)):
            row = by_ticker[t]
            sample.extend(rng.choices(row, k=len(row)))
        if not sample:
            estimates.append(0.0)
        else:
            estimates.append(float(np.nanmean(sample)))

    estimates = [e for e in estimates if np.isfinite(e)]
    if not estimates:
        return point, None, None
    ci_lower = _rnd(float(np.nanpercentile(estimates, 2.5)))
    ci_upper = _rnd(float(np.nanpercentile(estimates, 97.5)))
    return point, ci_lower, ci_upper


def _lift_bootstrap(
    signal_observations: list[Observation],
    control_observations: list[Observation],
    slippage_key: str,
    seed: int,
    resamples: int = 5000,
) -> tuple[float | None, float | None, float | None]:
    """Two-level ticker-cluster bootstrap of mean(signal) - mean(control)."""
    sig_by_ticker: dict[str, list[float]] = {}
    for obs in signal_observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None or not np.isfinite(net):
            continue
        sig_by_ticker.setdefault(obs.ticker, []).append(net)

    base_by_ticker: dict[str, list[float]] = {}
    for obs in control_observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None or not np.isfinite(net):
            continue
        base_by_ticker.setdefault(obs.ticker, []).append(net)

    if not sig_by_ticker or not base_by_ticker:
        return None, None, None

    sig_tickers = list(sig_by_ticker.keys())
    base_tickers = list(base_by_ticker.keys())

    sig_point = _rnd(float(np.nanmean([r for rs in sig_by_ticker.values() for r in rs])))
    base_point = _rnd(float(np.nanmean([r for rs in base_by_ticker.values() for r in rs])))
    point = _rnd((sig_point or 0.0) - (base_point or 0.0))

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sig_sample: list[float] = []
        for t in rng.choices(sig_tickers, k=len(sig_tickers)):
            row = sig_by_ticker[t]
            sig_sample.extend(rng.choices(row, k=len(row)))
        base_sample: list[float] = []
        for t in rng.choices(base_tickers, k=len(base_tickers)):
            row = base_by_ticker[t]
            base_sample.extend(rng.choices(row, k=len(row)))
        if sig_sample and base_sample:
            estimates.append(float(np.nanmean(sig_sample)) - float(np.nanmean(base_sample)))
        else:
            estimates.append(0.0)

    estimates = [e for e in estimates if np.isfinite(e)]
    if not estimates:
        return point, None, None
    ci_lower = _rnd(float(np.nanpercentile(estimates, 2.5)))
    ci_upper = _rnd(float(np.nanpercentile(estimates, 97.5)))
    return point, ci_lower, ci_upper


def _component_scores_distribution(
    observations: list[Observation],
    key: str,
) -> dict[str, float | None]:
    values = [o.series_scores.get(key) for o in observations if o.series_scores.get(key) is not None]
    return _returns_distribution(values)


def _per_ticker_metrics(
    observations: list[Observation],
    baseline_observations: list[Observation],
    slippage_key: str,
) -> list[TickerMetrics]:
    """Compute per-ticker summary for one split/event type."""
    by_ticker: dict[str, list[Observation]] = {}
    for obs in observations:
        by_ticker.setdefault(obs.ticker, []).append(obs)

    base_by_ticker: dict[str, list[Observation]] = {}
    for obs in baseline_observations:
        base_by_ticker.setdefault(obs.ticker, []).append(obs)

    all_tickers = sorted(set(by_ticker) | set(base_by_ticker))
    rows: list[TickerMetrics] = []
    for ticker in all_tickers:
        obs_list = by_ticker.get(ticker, [])
        complete = [o for o in obs_list if o.outcome_status == "complete"]
        qualifying = [o for o in complete if o.is_qualifying]

        qualifying_rets = [o.net_return_pct_by_slippage[slippage_key] for o in qualifying if o.net_return_pct_by_slippage.get(slippage_key) is not None]
        gross_rets = [o.gross_return_pct for o in qualifying if o.gross_return_pct is not None]
        mean_net = _mean(qualifying_rets)
        mean_gross = _mean(gross_rets)

        base_rets = [
            o.net_return_pct_by_slippage[slippage_key]
            for o in base_by_ticker.get(ticker, [])
            if o.outcome_status == "complete" and o.net_return_pct_by_slippage.get(slippage_key) is not None
        ]
        base_mean = _mean(base_rets)

        lift_bps = None
        if mean_net is not None and base_mean is not None:
            lift_bps = _rnd((mean_net - base_mean) * 100.0)

        rows.append(TickerMetrics(
            ticker=ticker,
            split=obs_list[0].split if obs_list else (baseline_observations[0].split if baseline_observations else ""),
            event_type=obs_list[0].event_type if obs_list else (baseline_observations[0].event_type if baseline_observations else ""),
            observations=len(obs_list),
            qualifying_signals=len(qualifying),
            executed_trades=0,  # populated by caller from trades
            mean_gross_return_pct=mean_gross,
            mean_net_return_pct=mean_net,
            mean_baseline_return_pct=base_mean,
            lift_bps=lift_bps,
            win_rate=_win_rate(qualifying_rets),
        ))
    return rows


def _compute_period_metrics(
    split: str,
    event_type: str,
    observations: list[Observation],
    baseline_observations: list[Observation],
    trades: list[Any],
    spec: StudySpec,
) -> tuple[PeriodMetrics, list[TickerMetrics]]:
    """Aggregate metrics for one split/event type."""
    slippage_key = spec.slippage_key(spec.decision_slippage_bps)

    eligible = [o for o in observations if o.outcome_status in {"complete", "insufficient_future_bars", "missing_signal_data"}]
    all_complete = [o for o in observations if o.outcome_status == "complete"]
    qualifying = [o for o in all_complete if o.is_qualifying]
    executed = [t for t in trades if t.split == split and t.event_type == event_type]

    sims = [o.similarity_score for o in qualifying]
    sim_dist = _returns_distribution(sims)

    component_scores: dict[str, dict[str, float | None]] = {}
    for key in spec.series_weights:
        component_scores[key] = _component_scores_distribution(qualifying, key)

    returns_by_slippage: dict[str, dict[str, float | None]] = {}
    for sk in [spec.slippage_key(s) for s in spec.slippage_scenarios_bps]:
        vals = [o.net_return_pct_by_slippage.get(sk) for o in qualifying if o.net_return_pct_by_slippage.get(sk) is not None]
        returns_by_slippage[sk] = _returns_distribution(vals)

    # Signal return statistics (qualifying observations only).
    rets = [o.net_return_pct_by_slippage[slippage_key] for o in qualifying if o.net_return_pct_by_slippage.get(slippage_key) is not None]
    gross_rets = [o.gross_return_pct for o in qualifying if o.gross_return_pct is not None]
    mean_net, ci_lower, ci_upper = _ticker_cluster_bootstrap(qualifying, slippage_key, spec.random_seed, spec.bootstrap.resamples)

    # Baseline and lift.
    baseline_rets = [
        o.net_return_pct_by_slippage[slippage_key]
        for o in baseline_observations
        if o.outcome_status == "complete" and o.net_return_pct_by_slippage.get(slippage_key) is not None
    ]
    baseline_mean = _mean(baseline_rets)
    signal_mean = _mean(rets)
    if signal_mean is not None and baseline_mean is not None:
        lift_bps = _rnd((signal_mean - baseline_mean) * 100.0)
        lift_point, lift_ci_lower, lift_ci_upper = _lift_bootstrap(
            qualifying, baseline_observations, slippage_key, spec.random_seed, spec.bootstrap.resamples
        )
    else:
        lift_bps = None
        lift_point, lift_ci_lower, lift_ci_upper = None, None, None

    # Per-ticker metrics for this split/event type.
    per_ticker = _per_ticker_metrics(observations, baseline_observations, slippage_key)
    for i, tm in enumerate(per_ticker):
        per_ticker[i] = TickerMetrics(
            ticker=tm.ticker,
            split=tm.split,
            event_type=tm.event_type,
            observations=tm.observations,
            qualifying_signals=tm.qualifying_signals,
            executed_trades=len([t for t in executed if t.ticker == tm.ticker]),
            mean_gross_return_pct=tm.mean_gross_return_pct,
            mean_net_return_pct=tm.mean_net_return_pct,
            mean_baseline_return_pct=tm.mean_baseline_return_pct,
            lift_bps=tm.lift_bps,
            win_rate=tm.win_rate,
        )

    ticker_lifts = [m.lift_bps for m in per_ticker if m.lift_bps is not None]
    median_ticker_lift = _median(ticker_lifts)
    positive_lift_tickers = sum(1 for m in per_ticker if m.lift_bps is not None and m.lift_bps > 0)
    pct_positive_lift = _rnd(positive_lift_tickers / len(ticker_lifts)) if ticker_lifts else None

    ticker_counts = pd.Series([o.ticker for o in qualifying]).value_counts()
    max_ticker_conc = None
    if len(qualifying):
        max_ticker_conc = _rnd(float(ticker_counts.max() / len(qualifying)))

    max_contribution_conc = None
    if rets:
        contributions = {
            t: sum(
                o.net_return_pct_by_slippage[slippage_key]
                for o in qualifying
                if o.ticker == t and o.net_return_pct_by_slippage.get(slippage_key) is not None
            )
            for t in ticker_counts.index
        }
        total_return = sum(contributions.values())
        if total_return and abs(total_return) > 1e-12:
            max_contribution_conc = _rnd(max(abs(v) / abs(total_return) for v in contributions.values()))

    overlap_count = 0
    for ticker in set(o.ticker for o in qualifying):
        t_obs = sorted([o for o in qualifying if o.ticker == ticker], key=lambda x: x.decision_date)
        for i in range(len(t_obs) - 1):
            if t_obs[i].exit_date is not None and t_obs[i + 1].entry_date is not None and t_obs[i + 1].entry_date <= t_obs[i].exit_date:
                overlap_count += 1

    missing_data_count = sum(1 for o in observations if o.outcome_status in {"missing_signal_data", "insufficient_future_bars"})

    # First/second half holdout split by date count.
    if qualifying:
        dates = sorted({o.decision_date for o in qualifying})
        if len(dates) > 1:
            mid = dates[len(dates) // 2]
            first = [o for o in qualifying if o.decision_date <= mid]
            second = [o for o in qualifying if o.decision_date > mid]
        else:
            first, second = qualifying, []
    else:
        first, second = [], []
    first_mean = _mean([o.net_return_pct_by_slippage[slippage_key] for o in first if o.net_return_pct_by_slippage.get(slippage_key) is not None])
    second_mean = _mean([o.net_return_pct_by_slippage[slippage_key] for o in second if o.net_return_pct_by_slippage.get(slippage_key) is not None])

    return PeriodMetrics(
        split=split,
        event_type=event_type,
        eligible_observations=len(eligible),
        qualifying_signals=len(qualifying),
        executed_trades=len(executed),
        ticker_count=len({o.ticker for o in qualifying}),
        date_start=min((o.decision_date for o in qualifying), default=None),
        date_end=max((o.decision_date for o in qualifying), default=None),
        mean_similarity=sim_dist["mean"],
        similarity_p05=sim_dist["p05"],
        similarity_p25=sim_dist["p25"],
        similarity_p50=sim_dist["p50"],
        similarity_p75=sim_dist["p75"],
        similarity_p95=sim_dist["p95"],
        component_scores=component_scores,
        mean_gross_return_pct=_mean(gross_rets),
        median_gross_return_pct=_median(gross_rets),
        mean_net_return_pct=mean_net,
        median_net_return_pct=_median(rets),
        win_rate=_win_rate(rets),
        returns_by_slippage=returns_by_slippage,
        baseline_mean_return_pct=baseline_mean,
        baseline_lift_bps=lift_bps,
        baseline_lift_ci_lower=lift_ci_lower,
        baseline_lift_ci_upper=lift_ci_upper,
        mean_return_ci_lower=ci_lower,
        mean_return_ci_upper=ci_upper,
        win_rate_lift=(_win_rate(rets) - _win_rate(baseline_rets)) if rets and baseline_rets else None,
        max_ticker_concentration=max_ticker_conc,
        max_contribution_concentration=max_contribution_conc,
        overlap_count=overlap_count,
        missing_data_count=missing_data_count,
        first_half_mean_return_pct=first_mean,
        second_half_mean_return_pct=second_mean,
        median_ticker_lift_bps=median_ticker_lift,
        pct_tickers_positive_lift=pct_positive_lift,
    ), per_ticker


def evaluate_evidence_gates(
    period_metrics: dict[tuple[str, str], PeriodMetrics],
    per_ticker: list[TickerMetrics],
    spec: StudySpec,
) -> PromotionDecision:
    """Evaluate the locked evidence gates independently for run-up and decline."""
    gate_results: dict[str, Any] = {"no_leakage_or_integrity_failures": True}
    event_classifications: dict[str, str] = {}
    all_reasons: list[str] = []

    for event_type in spec.event_types:
        val = period_metrics.get(("validation", event_type))
        ho = period_metrics.get(("holdout", event_type))
        reasons: list[str] = []

        def check(name: str, passes: bool, value: Any, fail_message: str) -> None:
            gate_results[f"{event_type}_{name}_value"] = value
            gate_results[f"{event_type}_{name}_passed"] = passes
            if not passes:
                reasons.append(f"{event_type}/{name}: {fail_message} ({value})")

        # Sample-size gates.
        check(
            "validation_signals",
            val is not None and val.qualifying_signals >= spec.minimum_validation_signals,
            val.qualifying_signals if val else 0,
            f"fewer than {spec.minimum_validation_signals} validation signals",
        )
        check(
            "holdout_signals",
            ho is not None and ho.qualifying_signals >= spec.minimum_holdout_signals,
            ho.qualifying_signals if ho else 0,
            f"fewer than {spec.minimum_holdout_signals} holdout signals",
        )
        check(
            "validation_tickers",
            val is not None and val.ticker_count >= spec.minimum_tickers,
            val.ticker_count if val else 0,
            f"fewer than {spec.minimum_tickers} validation tickers",
        )
        check(
            "holdout_tickers",
            ho is not None and ho.ticker_count >= spec.minimum_tickers,
            ho.ticker_count if ho else 0,
            f"fewer than {spec.minimum_tickers} holdout tickers",
        )
        check(
            "validation_max_ticker_concentration",
            val is not None and (val.max_ticker_concentration is None or val.max_ticker_concentration <= spec.max_ticker_concentration),
            val.max_ticker_concentration if val else None,
            f"ticker concentration above {spec.max_ticker_concentration}",
        )
        check(
            "holdout_max_ticker_concentration",
            ho is not None and (ho.max_ticker_concentration is None or ho.max_ticker_concentration <= spec.max_ticker_concentration),
            ho.max_ticker_concentration if ho else None,
            f"ticker concentration above {spec.max_ticker_concentration}",
        )

        # Mean net return positive.
        check(
            "validation_mean_net_return_positive",
            val is not None and val.mean_net_return_pct is not None and val.mean_net_return_pct > 0,
            val.mean_net_return_pct if val else None,
            "validation mean net return not positive",
        )
        check(
            "holdout_mean_net_return_positive",
            ho is not None and ho.mean_net_return_pct is not None and ho.mean_net_return_pct > 0,
            ho.mean_net_return_pct if ho else None,
            "holdout mean net return not positive",
        )

        # Bootstrap CI above zero.
        check(
            "validation_mean_ci_above_zero",
            val is not None and val.mean_return_ci_lower is not None and val.mean_return_ci_lower > 0,
            val.mean_return_ci_lower if val else None,
            "validation mean return CI lower bound not above zero",
        )
        check(
            "holdout_mean_ci_above_zero",
            ho is not None and ho.mean_return_ci_lower is not None and ho.mean_return_ci_lower > 0,
            ho.mean_return_ci_lower if ho else None,
            "holdout mean return CI lower bound not above zero",
        )

        # Lift threshold and CI.
        check(
            "validation_lift_threshold",
            val is not None and val.baseline_lift_bps is not None and val.baseline_lift_bps >= spec.minimum_lift_bps,
            val.baseline_lift_bps if val else None,
            f"validation lift below {spec.minimum_lift_bps} bps",
        )
        check(
            "holdout_lift_threshold",
            ho is not None and ho.baseline_lift_bps is not None and ho.baseline_lift_bps >= spec.minimum_lift_bps,
            ho.baseline_lift_bps if ho else None,
            f"holdout lift below {spec.minimum_lift_bps} bps",
        )
        check(
            "validation_lift_ci_above_zero",
            val is not None and val.baseline_lift_ci_lower is not None and val.baseline_lift_ci_lower > 0,
            val.baseline_lift_ci_lower if val else None,
            "validation lift CI lower bound not above zero",
        )
        check(
            "holdout_lift_ci_above_zero",
            ho is not None and ho.baseline_lift_ci_lower is not None and ho.baseline_lift_ci_lower > 0,
            ho.baseline_lift_ci_lower if ho else None,
            "holdout lift CI lower bound not above zero",
        )

        # Ticker-level lift and breadth.
        check(
            "validation_median_ticker_lift_positive",
            val is not None and val.median_ticker_lift_bps is not None and val.median_ticker_lift_bps > 0,
            val.median_ticker_lift_bps if val else None,
            "validation median ticker-level lift not positive",
        )
        check(
            "holdout_median_ticker_lift_positive",
            ho is not None and ho.median_ticker_lift_bps is not None and ho.median_ticker_lift_bps > 0,
            ho.median_ticker_lift_bps if ho else None,
            "holdout median ticker-level lift not positive",
        )
        check(
            "validation_pct_tickers_positive_lift",
            val is not None and val.pct_tickers_positive_lift is not None and val.pct_tickers_positive_lift >= 0.55,
            val.pct_tickers_positive_lift if val else None,
            "fewer than 55% of validation tickers have positive lift",
        )
        check(
            "holdout_pct_tickers_positive_lift",
            ho is not None and ho.pct_tickers_positive_lift is not None and ho.pct_tickers_positive_lift >= 0.55,
            ho.pct_tickers_positive_lift if ho else None,
            "fewer than 55% of holdout tickers have positive lift",
        )

        # Holdout half positivity.
        check(
            "holdout_first_half_positive",
            ho is not None and ho.first_half_mean_return_pct is not None and ho.first_half_mean_return_pct > 0,
            ho.first_half_mean_return_pct if ho else None,
            "holdout first-half mean net return not positive",
        )
        check(
            "holdout_second_half_positive",
            ho is not None and ho.second_half_mean_return_pct is not None and ho.second_half_mean_return_pct > 0,
            ho.second_half_mean_return_pct if ho else None,
            "holdout second-half mean net return not positive",
        )

        # Classify this event type.
        sample_gates = [f"{event_type}_validation_signals_passed", f"{event_type}_holdout_signals_passed", f"{event_type}_validation_tickers_passed", f"{event_type}_holdout_tickers_passed", f"{event_type}_validation_max_ticker_concentration_passed", f"{event_type}_holdout_max_ticker_concentration_passed"]
        return_gates = [f"{event_type}_validation_mean_net_return_positive_passed", f"{event_type}_holdout_mean_net_return_positive_passed", f"{event_type}_validation_mean_ci_above_zero_passed", f"{event_type}_holdout_mean_ci_above_zero_passed", f"{event_type}_validation_lift_threshold_passed", f"{event_type}_holdout_lift_threshold_passed", f"{event_type}_validation_lift_ci_above_zero_passed", f"{event_type}_holdout_lift_ci_above_zero_passed", f"{event_type}_validation_median_ticker_lift_positive_passed", f"{event_type}_holdout_median_ticker_lift_positive_passed", f"{event_type}_validation_pct_tickers_positive_lift_passed", f"{event_type}_holdout_pct_tickers_positive_lift_passed", f"{event_type}_holdout_first_half_positive_passed", f"{event_type}_holdout_second_half_positive_passed"]
        return_value_gates = [f"{event_type}_validation_mean_net_return_positive_value", f"{event_type}_holdout_mean_net_return_positive_value", f"{event_type}_validation_mean_ci_above_zero_value", f"{event_type}_holdout_mean_ci_above_zero_value", f"{event_type}_validation_lift_threshold_value", f"{event_type}_holdout_lift_threshold_value", f"{event_type}_validation_lift_ci_above_zero_value", f"{event_type}_holdout_lift_ci_above_zero_value", f"{event_type}_validation_median_ticker_lift_positive_value", f"{event_type}_holdout_median_ticker_lift_positive_value", f"{event_type}_validation_pct_tickers_positive_lift_value", f"{event_type}_holdout_pct_tickers_positive_lift_value", f"{event_type}_holdout_first_half_positive_value", f"{event_type}_holdout_second_half_positive_value"]
        sample_pass = all(gate_results.get(g) is True for g in sample_gates)
        return_pass = all(gate_results.get(g) is True for g in return_gates)
        return_unavailable = any(gate_results.get(g) is None for g in return_value_gates)

        if not sample_pass:
            classification = "inconclusive"
        elif return_pass:
            classification = "supported"
        elif return_unavailable:
            classification = "inconclusive"
        else:
            classification = "rejected"

        event_classifications[event_type] = classification
        gate_results[f"{event_type}_classification"] = classification
        if reasons:
            all_reasons.extend(reasons)

    # Overall classification: rejected if any event type is rejected; otherwise
    # inconclusive if any; otherwise supported.
    if any(c == "rejected" for c in event_classifications.values()):
        overall = "rejected"
    elif any(c == "inconclusive" for c in event_classifications.values()):
        overall = "inconclusive"
    else:
        overall = "supported"

    gate_results["event_classifications"] = event_classifications
    gate_results["overall_classification"] = overall

    return PromotionDecision(
        classification=overall,
        production_promotion_eligible=False,
        gate_results=gate_results,
        reason="; ".join(all_reasons) if all_reasons else "all evidence gates passed",
    )


def compute_all_metrics(
    observations: list[Observation],
    controls: list[Observation],
    trades: list[Any],
    spec: StudySpec,
) -> tuple[dict[tuple[str, str], PeriodMetrics], list[TickerMetrics]]:
    """Compute period metrics and per-ticker metrics for every split/event type."""
    period_metrics: dict[tuple[str, str], PeriodMetrics] = {}
    per_ticker_all: list[TickerMetrics] = []

    for split in spec.splits:
        for event_type in spec.event_types:
            split_obs = [o for o in observations if o.split == split and o.event_type == event_type]
            split_controls = [o for o in controls if o.split == split and o.event_type == event_type]
            split_trades = [t for t in trades if t.split == split and t.event_type == event_type]
            pm, per_ticker = _compute_period_metrics(split, event_type, split_obs, split_controls, split_trades, spec)
            period_metrics[(split, event_type)] = pm
            per_ticker_all.extend(per_ticker)

    return period_metrics, per_ticker_all
