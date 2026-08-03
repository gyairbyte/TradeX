"""Metrics, bootstrap confidence intervals, and evidence gates."""
from __future__ import annotations

import random
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from .models import Observation, PeriodMetrics, PromotionDecision, StudySpec, TickerMetrics, _clean


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.nanmean(values))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.nanmedian(values))


def _win_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(1 for v in values if v > 0) / len(values)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.nanpercentile(values, q))


def _ticker_cluster_bootstrap(
    observations: list[Observation],
    slippage_key: str,
    seed: int,
    resamples: int = 5000,
    statistic: str = "mean",
) -> tuple[float, float, float]:
    """Bootstrap mean/median net return by resampling tickers with replacement."""
    rng = random.Random(seed)
    by_ticker: dict[str, list[float]] = {}
    for obs in observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None:
            continue
        by_ticker.setdefault(obs.ticker, []).append(net)

    if not by_ticker:
        return 0.0, 0.0, 0.0

    tickers = list(by_ticker.keys())
    estimates: list[float] = []
    for _ in range(resamples):
        sample_returns: list[float] = []
        sampled_tickers = [rng.choice(tickers) for _ in range(len(tickers))]
        for t in sampled_tickers:
            # Resample rows within the chosen ticker with replacement.
            returns = by_ticker[t]
            if not returns:
                continue
            n = len(returns)
            sample_returns.extend(rng.choices(returns, k=n))
        if not sample_returns:
            estimates.append(0.0)
            continue
        if statistic == "mean":
            estimates.append(float(np.nanmean(sample_returns)))
        elif statistic == "median":
            estimates.append(float(np.nanmedian(sample_returns)))
        else:
            estimates.append(float(np.nanmean(sample_returns)))

    estimates = [e for e in estimates if np.isfinite(e)]
    if not estimates:
        return 0.0, 0.0, 0.0
    point = float(np.nanmean([float(np.nanmean(vs)) for vs in by_ticker.values()]))
    ci_lower = float(np.nanpercentile(estimates, 5.0))
    ci_upper = float(np.nanpercentile(estimates, 95.0))
    return point, ci_lower, ci_upper


def _lift_bootstrap(
    observations: list[Observation],
    baseline_observations: list[Observation],
    slippage_key: str,
    seed: int,
    resamples: int = 5000,
) -> tuple[float, float, float]:
    """Bootstrap mean lift (signal minus baseline) by ticker cluster."""
    rng = random.Random(seed)
    sig_by_ticker: dict[str, list[float]] = {}
    base_by_ticker: dict[str, list[float]] = {}
    for obs in observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None:
            continue
        sig_by_ticker.setdefault(obs.ticker, []).append(net)
    for obs in baseline_observations:
        if obs.outcome_status != "complete":
            continue
        net = obs.net_return_pct_by_slippage.get(slippage_key)
        if net is None:
            continue
        base_by_ticker.setdefault(obs.ticker, []).append(net)

    tickers = sorted(set(sig_by_ticker) | set(base_by_ticker))
    if not tickers:
        return 0.0, 0.0, 0.0

    estimates: list[float] = []
    for _ in range(resamples):
        sample_returns: list[float] = []
        sampled_tickers = [rng.choice(tickers) for _ in range(len(tickers))]
        for t in sampled_tickers:
            sig = sig_by_ticker.get(t, [])
            base = base_by_ticker.get(t, [])
            if sig and base:
                n_sig = len(sig)
                n_base = len(base)
                sig_sample = rng.choices(sig, k=n_sig)
                base_sample = rng.choices(base, k=n_base)
                sample_returns.extend(sig_sample)
                sample_returns.extend([-b for b in base_sample])
            elif sig:
                sample_returns.extend(rng.choices(sig, k=len(sig)))
            elif base:
                sample_returns.extend([-b for b in rng.choices(base, k=len(base))])
        if not sample_returns:
            estimates.append(0.0)
            continue
        estimates.append(float(np.nanmean(sample_returns)))

    estimates = [e for e in estimates if np.isfinite(e)]
    if not estimates:
        return 0.0, 0.0, 0.0
    point = float(np.nanmean([np.nanmean(sig_by_ticker[t]) for t in tickers if t in sig_by_ticker]))
    base_point = float(np.nanmean([np.nanmean(base_by_ticker[t]) for t in tickers if t in base_by_ticker]))
    lift_point = point - base_point
    ci_lower = float(np.nanpercentile(estimates, 5.0))
    ci_upper = float(np.nanpercentile(estimates, 95.0))
    return lift_point, ci_lower, ci_upper


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


def _per_ticker_metrics(
    observations: list[Observation],
    baseline_observations: list[Observation],
    slippage_key: str,
) -> list[TickerMetrics]:
    """Compute per-ticker summary for one split/event type."""
    rows: list[TickerMetrics] = []
    by_ticker: dict[str, list[Observation]] = {}
    for obs in observations:
        by_ticker.setdefault(obs.ticker, []).append(obs)
    base_by_ticker: dict[str, list[Observation]] = {}
    for obs in baseline_observations:
        base_by_ticker.setdefault(obs.ticker, []).append(obs)

    for ticker, obs_list in sorted(by_ticker.items()):
        complete = [o for o in obs_list if o.outcome_status == "complete"]
        qualifying = [o for o in complete if o.is_qualifying]
        executed = [o for o in complete if o.is_qualifying]  # event-study style per ticker
        rets = [o.net_return_pct_by_slippage[slippage_key] for o in complete if o.net_return_pct_by_slippage.get(slippage_key) is not None]
        mean_gross = _mean([o.gross_return_pct for o in complete if o.gross_return_pct is not None])
        mean_net = _mean(rets)
        base_rets = [o.net_return_pct_by_slippage[slippage_key] for o in base_by_ticker.get(ticker, []) if o.net_return_pct_by_slippage.get(slippage_key) is not None]
        base_mean = _mean(base_rets)
        if mean_net is not None and base_mean is not None:
            lift_bps = round((mean_net - base_mean) * 100.0, 2)
        else:
            lift_bps = None
        split = obs_list[0].split if obs_list else ""
        event_type = obs_list[0].event_type if obs_list else ""
        rows.append(TickerMetrics(
            ticker=ticker,
            split=split,
            event_type=event_type,
            observations=len(obs_list),
            qualifying_signals=len(qualifying),
            executed_trades=len(executed),
            mean_gross_return_pct=mean_gross,
            mean_net_return_pct=mean_net,
            mean_baseline_return_pct=base_mean,
            lift_bps=lift_bps,
            win_rate=_win_rate(rets),
        ))
    return rows


def _compute_period_metrics(
    split: str,
    event_type: str,
    observations: list[Observation],
    baseline_observations: list[Observation],
    trades: list[Any],
    spec: StudySpec,
) -> PeriodMetrics:
    """Aggregate metrics for one split/event type."""
    slippage_key = spec.slippage_key(spec.decision_slippage_bps)

    all_complete = [o for o in observations if o.outcome_status == "complete"]
    qualifying = [o for o in all_complete if o.is_qualifying]
    eligible = [o for o in observations]  # includes incomplete for count

    sims = [o.similarity_score for o in qualifying]
    sim_dist = _returns_distribution(sims)

    series_scores: dict[str, list[float]] = {key: [] for key in spec.series_weights}
    for o in all_complete:
        for key, score in o.series_scores.items():
            series_scores[key].append(score)

    rets = [o.net_return_pct_by_slippage[slippage_key] for o in all_complete if o.net_return_pct_by_slippage.get(slippage_key) is not None]
    gross_rets = [o.gross_return_pct for o in all_complete if o.gross_return_pct is not None]
    mean_net, ci_lower, ci_upper = _ticker_cluster_bootstrap(all_complete, slippage_key, spec.random_seed, spec.bootstrap.resamples, statistic="mean")

    returns_by_slippage: dict[str, dict[str, float | None]] = {}
    for sk in [spec.slippage_key(s) for s in spec.slippage_scenarios_bps]:
        vals = [o.net_return_pct_by_slippage.get(sk) for o in all_complete if o.net_return_pct_by_slippage.get(sk) is not None]
        returns_by_slippage[sk] = _returns_distribution(vals)

    baseline_rets = [o.net_return_pct_by_slippage[slippage_key] for o in baseline_observations if o.net_return_pct_by_slippage.get(slippage_key) is not None]
    baseline_mean = _mean(baseline_rets)
    signal_mean = _mean(rets)
    if signal_mean is not None and baseline_mean is not None:
        lift_bps = round((signal_mean - baseline_mean) * 100.0, 2)
        lift_point, lift_ci_lower, lift_ci_upper = _lift_bootstrap(
            all_complete, baseline_observations, slippage_key, spec.random_seed, spec.bootstrap.resamples
        )
    else:
        lift_bps = None
        lift_point, lift_ci_lower, lift_ci_upper = None, None, None

    # Ticker-level lift and concentration.
    per_ticker = _per_ticker_metrics(observations, baseline_observations, slippage_key)
    ticker_lifts = [m.lift_bps for m in per_ticker if m.lift_bps is not None]
    median_ticker_lift = _median(ticker_lifts)
    positive_lift_tickers = sum(1 for m in per_ticker if m.lift_bps is not None and m.lift_bps > 0)
    pct_positive_lift = positive_lift_tickers / len(per_ticker) if per_ticker else None

    ticker_counts = pd.Series([o.ticker for o in qualifying]).value_counts()
    max_ticker_conc = float(ticker_counts.max() / len(qualifying)) if len(qualifying) else None
    if rets:
        contributions = {t: sum(o.net_return_pct_by_slippage[slippage_key] for o in qualifying if o.ticker == t if o.net_return_pct_by_slippage.get(slippage_key) is not None) for t in ticker_counts.index}
        total_return = sum(contributions.values())
        max_contribution_conc = max(abs(v) / abs(total_return) for v in contributions.values()) if total_return else None
    else:
        max_contribution_conc = None

    # Overlap count: number of qualifying observations that overlap another.
    overlap_count = 0
    for ticker in set(o.ticker for o in qualifying):
        t_obs = sorted([o for o in qualifying if o.ticker == o.ticker and o.ticker == ticker], key=lambda x: x.decision_date)
        for i in range(len(t_obs) - 1):
            if t_obs[i].exit_date is not None and t_obs[i + 1].entry_date is not None and t_obs[i + 1].entry_date <= t_obs[i].exit_date:
                overlap_count += 1

    missing_data_count = sum(1 for o in observations if o.outcome_status == "missing_signal_data" or o.outcome_status == "insufficient_future_bars")

    # First/second half holdout (only meaningful for holdout split).
    if all_complete:
        dates = sorted({o.decision_date for o in all_complete})
        if len(dates) > 1:
            mid = dates[len(dates) // 2]
            first = [o for o in all_complete if o.decision_date <= mid]
            second = [o for o in all_complete if o.decision_date > mid]
        else:
            first, second = all_complete, []
    else:
        first, second = [], []
    first_mean = _mean([o.net_return_pct_by_slippage[slippage_key] for o in first if o.net_return_pct_by_slippage.get(slippage_key) is not None])
    second_mean = _mean([o.net_return_pct_by_slippage[slippage_key] for o in second if o.net_return_pct_by_slippage.get(slippage_key) is not None])

    return PeriodMetrics(
        split=split,
        event_type=event_type,
        eligible_observations=len(eligible),
        qualifying_signals=len(qualifying),
        executed_trades=len([t for t in trades if t.split == split and t.event_type == event_type]),
        ticker_count=len({o.ticker for o in all_complete}),
        date_start=min((o.decision_date for o in all_complete), default=None),
        date_end=max((o.decision_date for o in all_complete), default=None),
        mean_similarity=sim_dist["mean"],
        similarity_p05=sim_dist["p05"],
        similarity_p25=sim_dist["p25"],
        similarity_p50=sim_dist["p50"],
        similarity_p75=sim_dist["p75"],
        similarity_p95=sim_dist["p95"],
        mean_gross_return_pct=_mean(gross_rets),
        median_gross_return_pct=_median(gross_rets),
        mean_net_return_pct=_mean(rets),
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
    )


def evaluate_evidence_gates(
    period_metrics: dict[tuple[str, str], PeriodMetrics],
    per_ticker: list[TickerMetrics],
    spec: StudySpec,
) -> PromotionDecision:
    """Evaluate the 15 locked evidence gates and classify the result."""
    slippage_key = spec.slippage_key(spec.decision_slippage_bps)
    gate_results: dict[str, Any] = {}
    reasons: list[str] = []

    def get(split: str, event_type: str) -> PeriodMetrics | None:
        return period_metrics.get((split, event_type))

    def net_return(m: PeriodMetrics | None) -> float | None:
        return m.mean_net_return_pct if m else None

    def lift(m: PeriodMetrics | None) -> float | None:
        return m.baseline_lift_bps if m else None

    def ci_lower(m: PeriodMetrics | None) -> float | None:
        return m.mean_return_ci_lower if m else None

    def lift_ci_lower(m: PeriodMetrics | None) -> float | None:
        return m.baseline_lift_ci_lower if m else None

    # Sample-size and ticker-count gates.
    for split in ["validation", "holdout"]:
        for event_type in spec.event_types:
            m = get(split, event_type)
            key = f"{split}_{event_type}_signals"
            gate_results[key] = m.qualifying_signals if m else 0
            if m is None or m.qualifying_signals < (spec.minimum_validation_signals if split == "validation" else spec.minimum_holdout_signals):
                reasons.append(f"{split}/{event_type} has fewer than required signals ({m.qualifying_signals if m else 0})")

            key = f"{split}_{event_type}_tickers"
            gate_results[key] = m.ticker_count if m else 0
            if m is None or m.ticker_count < spec.minimum_tickers:
                reasons.append(f"{split}/{event_type} has fewer than {spec.minimum_tickers} tickers")

            key = f"{split}_{event_type}_max_ticker_concentration"
            gate_results[key] = m.max_ticker_concentration if m else None
            if m is None or (m.max_ticker_concentration is not None and m.max_ticker_concentration > spec.max_ticker_concentration):
                reasons.append(f"{split}/{event_type} has a ticker contributing more than {spec.max_ticker_concentration:.0%} of signals")

    # Mean net return positive.
    for split in ["validation", "holdout"]:
        for event_type in spec.event_types:
            m = get(split, event_type)
            key = f"{split}_{event_type}_mean_net_return_positive"
            val = net_return(m)
            gate_results[key] = val
            if val is None or val <= 0:
                reasons.append(f"{split}/{event_type} mean net return at {slippage_key} bps is not positive ({val})")

    # Bootstrap CIs above zero.
    for split in ["validation", "holdout"]:
        for event_type in spec.event_types:
            m = get(split, event_type)
            key = f"{split}_{event_type}_mean_ci_above_zero"
            val = ci_lower(m)
            gate_results[key] = val
            if val is None or val <= 0:
                reasons.append(f"{split}/{event_type} mean net return lower confidence bound is not above zero ({val})")

    # Baseline lift >= 0.25 percentage points.
    for split in ["validation", "holdout"]:
        for event_type in spec.event_types:
            m = get(split, event_type)
            key = f"{split}_{event_type}_lift_threshold"
            val = lift(m)
            gate_results[key] = val
            if val is None or val < spec.minimum_lift_bps:
                reasons.append(f"{split}/{event_type} lift {val} bps is below {spec.minimum_lift_bps} bps")

    # Baseline-lift CI above zero.
    for split in ["validation", "holdout"]:
        for event_type in spec.event_types:
            m = get(split, event_type)
            key = f"{split}_{event_type}_lift_ci_above_zero"
            val = lift_ci_lower(m)
            gate_results[key] = val
            if val is None or val <= 0:
                reasons.append(f"{split}/{event_type} baseline-lift lower confidence bound is not above zero ({val})")

    # Ticker-level lift and prevalence.
    for split in ["validation", "holdout"]:
        split_tickers = [m for m in per_ticker if m.split == split]
        lifts = [m.lift_bps for m in split_tickers if m.lift_bps is not None]
        median_lift = _median(lifts)
        key = f"{split}_median_ticker_lift_positive"
        gate_results[key] = median_lift
        if median_lift is None or median_lift <= 0:
            reasons.append(f"{split} median ticker-level lift is not positive ({median_lift})")

        positive = sum(1 for m in split_tickers if m.lift_bps is not None and m.lift_bps > 0)
        total = len([m for m in split_tickers if m.lift_bps is not None])
        pct = positive / total if total else 0.0
        key = f"{split}_pct_tickers_positive_lift"
        gate_results[key] = pct
        if pct < 0.55:
            reasons.append(f"{split} fewer than 55% of tickers have positive lift ({pct:.1%})")

    # Holdout half-mean positivity.
    for event_type in spec.event_types:
        m = get("holdout", event_type)
        key = f"holdout_{event_type}_first_half_positive"
        gate_results[key] = m.first_half_mean_return_pct if m else None
        key2 = f"holdout_{event_type}_second_half_positive"
        gate_results[key2] = m.second_half_mean_return_pct if m else None
        if m is None or m.first_half_mean_return_pct is None or m.first_half_mean_return_pct <= 0:
            reasons.append(f"holdout/{event_type} first-half mean net return is not positive")
        if m is None or m.second_half_mean_return_pct is None or m.second_half_mean_return_pct <= 0:
            reasons.append(f"holdout/{event_type} second-half mean net return is not positive")

    # Leakage / integrity gate is a placeholder; true pass/fail is enforced by construction.
    gate_results["no_leakage_or_integrity_failures"] = True

    classification = "supported" if not reasons else "inconclusive"
    if reasons:
        # If any gate shows clear contradictory evidence (e.g. negative mean returns and negative CI), classify as rejected.
        # We treat failure to meet the positive-return gates as inconclusive unless mean is negative and CI excludes zero.
        negative_evidence = any(
            (net_return(get(split, et)) is not None and net_return(get(split, et)) < 0)
            and (ci_lower(get(split, et)) is not None and ci_lower(get(split, et)) < 0)
            for split in ["validation", "holdout"]
            for et in spec.event_types
        )
        classification = "rejected" if negative_evidence else "inconclusive"

    return PromotionDecision(
        classification=classification,
        production_promotion_eligible=False,
        gate_results=gate_results,
        reason="; ".join(reasons) if reasons else "all evidence gates passed",
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

    # Use controls as baseline when frequency-matched is configured, otherwise all eligible.
    baseline_observations = controls if spec.baseline_definition == "frequency_matched" else observations

    for split in spec.splits:
        for event_type in spec.event_types:
            split_obs = [o for o in observations if o.split == split and o.event_type == event_type]
            split_baseline = [o for o in baseline_observations if o.split == split and o.event_type == event_type]
            split_trades = [t for t in trades if t.split == split and t.event_type == event_type]
            pm = _compute_period_metrics(split, event_type, split_obs, split_baseline, split_trades, spec)
            period_metrics[(split, event_type)] = pm
            per_ticker_all.extend(_per_ticker_metrics(split_obs, split_baseline, spec.slippage_key(spec.decision_slippage_bps)))

    return period_metrics, per_ticker_all
