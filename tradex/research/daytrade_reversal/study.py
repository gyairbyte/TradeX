"""Study execution engine, split evaluation orchestrator, and holdout protection guard."""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .baseline import build_baseline_pool, match_event_baselines
from .bootstrap import run_joint_cluster_bootstrap
from .calendar import to_market_time
from .events import (
    classify_overlapping_events,
    compute_session_threshold,
    detect_events_in_session,
)
from .freeze import EvaluationFreezeRecord, verify_freeze_state
from .gates import evaluate_gates_and_disposition
from .models import (
    BaselineObservation,
    DaytradeSession,
    EventObservation,
    StudyResult,
)
from .outcomes import calculate_horizon_outcomes_for_bar
from .spec import DaytradeSpec


class HoldoutAccessDeniedError(Exception):
    """Raised when holdout data access is attempted without a verified 'supported' validation run."""


class StudyExecutionError(Exception):
    """Raised for methodological or execution errors during study execution."""


def verify_holdout_access_prerequisites(
    validation_artifact_dir: Path,
    spec: DaytradeSpec,
    freeze_record: EvaluationFreezeRecord | None = None,
    repo_root: Path | None = None,
) -> None:
    """Verify that validation was executed cleanly, earned 'supported', and matches frozen code.

    Fails closed by raising HoldoutAccessDeniedError before any holdout parsing begins.
    """
    vdir = Path(validation_artifact_dir).expanduser().resolve()
    if not vdir.is_dir():
        raise HoldoutAccessDeniedError(
            f"Validation artifact directory does not exist: {vdir}"
        )

    study_file = vdir / "study.json"
    if not study_file.is_file():
        raise HoldoutAccessDeniedError(
            f"Validation study.json not found in: {vdir}"
        )

    try:
        study_data = json.loads(study_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HoldoutAccessDeniedError(
            f"Failed to parse validation study.json: {e}"
        ) from e

    # 1. Validation split check
    if study_data.get("split") != "validation":
        raise HoldoutAccessDeniedError(
            f"Supplied study artifact split is '{study_data.get('split')}', expected 'validation'"
        )

    # 2. Validation disposition must be strictly 'supported'
    disposition = study_data.get("disposition")
    if disposition != "supported":
        raise HoldoutAccessDeniedError(
            f"Holdout access denied: validation disposition is '{disposition}', "
            "must be strictly 'supported'."
        )

    # 3. Spec hash check
    spec_lock_file = vdir / "spec.lock.json"
    if spec_lock_file.is_file():
        spec_data = json.loads(spec_lock_file.read_text(encoding="utf-8"))
        recorded_spec_sha = spec_data.get("sha256")
        if recorded_spec_sha != spec.sha256:
            raise HoldoutAccessDeniedError(
                f"Spec hash mismatch in validation artifact: {recorded_spec_sha} vs current {spec.sha256}"
            )

    # 4. Code freeze verification
    if freeze_record is not None:
        try:
            verify_freeze_state(freeze_record, repo_root=repo_root, require_clean=True)
        except Exception as e:
            raise HoldoutAccessDeniedError(
                f"Holdout access denied: evaluator code freeze check failed: {e}"
            ) from e


def load_and_evaluate_holdout(
    validation_artifact_dir: Path,
    spec: DaytradeSpec,
    holdout_loader: Callable[[], list[DaytradeSession]],
    freeze_record: EvaluationFreezeRecord | None = None,
    repo_root: Path | None = None,
) -> StudyResult:
    """Safely load and evaluate holdout data strictly guarded by the validation gate.

    The holdout_loader function will NEVER be invoked if validation prerequisites fail.
    """
    verify_holdout_access_prerequisites(
        validation_artifact_dir=validation_artifact_dir,
        spec=spec,
        freeze_record=freeze_record,
        repo_root=repo_root,
    )

    # Only reached if prerequisites pass!
    holdout_sessions = holdout_loader()
    return evaluate_split(
        split_name="holdout",
        sessions=holdout_sessions,
        spec=spec,
    )


def evaluate_split(
    split_name: str,
    sessions: list[DaytradeSession],
    spec: DaytradeSpec,
    split_end_dt: datetime | None = None,
    integrity_error: str | None = None,
) -> StudyResult:
    """Execute the locked DAYTRADE-001 reversal study on a prepared dataset split."""
    # Organize sessions by ticker
    sessions_by_ticker: dict[str, list[DaytradeSession]] = defaultdict(list)
    for s in sessions:
        sessions_by_ticker[s.ticker].append(s)

    for ticker_sessions in sessions_by_ticker.values():
        ticker_sessions.sort(key=lambda s: s.session_date)

    all_events: list[EventObservation] = []
    all_qualifying_non_events: list[BaselineObservation] = []
    all_clusters: set[tuple[str, date]] = set()

    for ticker, t_sessions in sessions_by_ticker.items():
        valid_prior_sessions: list[DaytradeSession] = []

        for session in t_sessions:
            if not session.is_valid:
                continue

            all_clusters.add((ticker, session.session_date))

            # Need at least 20 prior valid sessions to establish threshold
            if len(valid_prior_sessions) >= spec.trailing_sessions:
                threshold = compute_session_threshold(valid_prior_sessions)
                if threshold is not None:
                    evs, non_evs = detect_events_in_session(
                        session=session,
                        threshold=threshold,
                        split_name=split_name,
                    )

                    # Compute forward outcomes for events
                    for ev in evs:
                        ev_bar = next(
                            (b for b in session.bars if b.bar_start == ev.event_bar_start),
                            None,
                        )
                        if ev_bar is not None:
                            ev.outcomes = calculate_horizon_outcomes_for_bar(
                                bar=ev_bar,
                                session_bars=session.bars,
                                split_end_dt=split_end_dt,
                            )
                            # Only retain events with valid primary horizon outcome
                            if 1 in ev.outcomes:
                                all_events.append(ev)

                    # Compute forward outcomes for non-events
                    for ne_bar, _ in non_evs:
                        outcomes = calculate_horizon_outcomes_for_bar(
                            bar=ne_bar,
                            session_bars=session.bars,
                            split_end_dt=split_end_dt,
                        )
                        if outcomes:
                            min_str = to_market_time(ne_bar.bar_start).strftime("%H:%M")
                            base_obs = BaselineObservation(
                                ticker=ticker,
                                session_date=session.session_date,
                                split=split_name,
                                minute_of_day=min_str,
                                bar_start=ne_bar.bar_start,
                                available_at=ne_bar.available_at,
                                outcomes=outcomes,
                            )
                            all_qualifying_non_events.append(base_obs)

            # Accumulate valid session into rolling history for subsequent sessions
            valid_prior_sessions.append(session)

    # Overlapping events classification using canonical 5-minute analysis window
    classify_overlapping_events(all_events)
    overlapping_count = sum(1 for e in all_events if e.is_overlapping)
    overlapping_rate = (
        (overlapping_count / float(len(all_events))) if all_events else 0.0
    )

    # Matched baseline reference calculation (arithmetic mean of qualifying non-events)
    baseline_pool = build_baseline_pool(all_qualifying_non_events)
    match_event_baselines(
        events=all_events,
        baseline_pool=baseline_pool,
        horizon=1,
        friction_bps=spec.primary_cost_bps_per_side,
    )

    # Aggregate performance metrics
    event_count = len(all_events)
    represented_tickers = len({e.ticker for e in all_events})

    # Ticker concentration
    ticker_counts: dict[str, int] = defaultdict(int)
    for e in all_events:
        ticker_counts[e.ticker] += 1

    max_ticker_pct = (
        (max(ticker_counts.values()) / float(event_count) * 100.0)
        if event_count > 0
        else 0.0
    )

    # Primary net return (2 bps/side)
    primary_net_rets = [
        e.outcomes[1].net_return_2bps
        for e in all_events
        if 1 in e.outcomes
    ]
    mean_primary_net = (
        float(np.mean(primary_net_rets)) if primary_net_rets else None
    )
    median_primary_net = (
        float(np.median(primary_net_rets)) if primary_net_rets else None
    )

    # Uplift
    uplifts = [
        e.uplift_1m_net
        for e in all_events
        if e.uplift_1m_net is not None
    ]
    mean_uplift = float(np.mean(uplifts)) if uplifts else None
    median_uplift = float(np.median(uplifts)) if uplifts else None

    # Baseline return
    baseline_rets = [
        e.matched_baseline_1m_net
        for e in all_events
        if e.matched_baseline_1m_net is not None
    ]
    mean_baseline = float(np.mean(baseline_rets)) if baseline_rets else None
    median_baseline = float(np.median(baseline_rets)) if baseline_rets else None

    # Secondary returns
    gross_1m = [e.outcomes[1].gross_return for e in all_events if 1 in e.outcomes]
    gross_2m = [e.outcomes[2].gross_return for e in all_events if 2 in e.outcomes]
    gross_5m = [e.outcomes[5].gross_return for e in all_events if 5 in e.outcomes]

    win_rate_1m = (sum(1 for r in gross_1m if r > 0) / float(len(gross_1m))) if gross_1m else 0.0
    win_rate_2m = (sum(1 for r in gross_2m if r > 0) / float(len(gross_2m))) if gross_2m else 0.0
    win_rate_5m = (sum(1 for r in gross_5m if r > 0) / float(len(gross_5m))) if gross_5m else 0.0

    net_0bps = [e.outcomes[1].net_return_0bps for e in all_events if 1 in e.outcomes]
    net_5bps = [e.outcomes[1].net_return_5bps for e in all_events if 1 in e.outcomes]

    # Per-ticker primary net results
    per_ticker_net_means: dict[str, float] = {}
    for ticker in ticker_counts:
        t_rets = [
            e.outcomes[1].net_return_2bps
            for e in all_events
            if e.ticker == ticker and 1 in e.outcomes
        ]
        if t_rets:
            per_ticker_net_means[ticker] = float(np.mean(t_rets))

    positive_tickers_count = sum(1 for mean_ret in per_ticker_net_means.values() if mean_ret > 0)
    pct_positive_tickers = (
        (positive_tickers_count / float(represented_tickers) * 100.0)
        if represented_tickers > 0
        else 0.0
    )

    # Monthly primary results
    monthly_counts: dict[str, int] = defaultdict(int)
    monthly_rets: dict[str, list[float]] = defaultdict(list)
    for e in all_events:
        m_str = e.session_date.strftime("%Y-%m")
        monthly_counts[m_str] += 1
        if 1 in e.outcomes:
            monthly_rets[m_str].append(e.outcomes[1].net_return_2bps)

    monthly_primary_results = {
        m: {
            "event_count": monthly_counts[m],
            "mean_net_return_2bps": float(np.mean(monthly_rets[m])) if monthly_rets[m] else None,
        }
        for m in sorted(monthly_counts.keys())
    }

    # Joint cluster bootstrap
    sorted_clusters = sorted(all_clusters)
    event_ci, uplift_ci = run_joint_cluster_bootstrap(
        events=all_events,
        non_events=all_qualifying_non_events,
        all_clusters=sorted_clusters,
        resamples=spec.bootstrap_resamples,
        seed=spec.bootstrap_seed,
        confidence_level_pct=spec.bootstrap_confidence_level_pct,
        horizon=1,
    )

    # Gates and 5-step precedence evaluation
    disposition, disp_step, disp_reason, gates_dict = evaluate_gates_and_disposition(
        event_count=event_count,
        represented_tickers=represented_tickers,
        max_ticker_concentration_pct=max_ticker_pct,
        mean_primary_net_return_2bps=mean_primary_net,
        event_ci=event_ci,
        mean_uplift_2bps=mean_uplift,
        uplift_ci=uplift_ci,
        pct_positive_tickers=pct_positive_tickers,
        per_ticker_net_means=per_ticker_net_means,
        split_quality=None,
        integrity_error=integrity_error,
    )

    metrics: dict[str, Any] = {
        "eligible_minute_count": len(all_events) + len(all_qualifying_non_events),
        "event_count": event_count,
        "represented_ticker_count": represented_tickers,
        "events_per_ticker": {t: ticker_counts[t] for t in sorted(ticker_counts.keys())},
        "events_per_month": {m: monthly_counts[m] for m in sorted(monthly_counts.keys())},
        "maximum_single_ticker_event_concentration": max_ticker_pct,
        "overlapping_event_count": overlapping_count,
        "overlapping_event_rate": overlapping_rate,
        "mean_gross_forward_return_1m": float(np.mean(gross_1m)) if gross_1m else None,
        "mean_gross_forward_return_2m": float(np.mean(gross_2m)) if gross_2m else None,
        "mean_gross_forward_return_5m": float(np.mean(gross_5m)) if gross_5m else None,
        "median_gross_forward_return_1m": float(np.median(gross_1m)) if gross_1m else None,
        "median_gross_forward_return_2m": float(np.median(gross_2m)) if gross_2m else None,
        "median_gross_forward_return_5m": float(np.median(gross_5m)) if gross_5m else None,
        "win_rate_1m": win_rate_1m,
        "win_rate_2m": win_rate_2m,
        "win_rate_5m": win_rate_5m,
        "mean_net_forward_return_0bps": float(np.mean(net_0bps)) if net_0bps else None,
        "mean_net_forward_return_2bps": mean_primary_net,
        "mean_net_forward_return_5bps": float(np.mean(net_5bps)) if net_5bps else None,
        "median_net_forward_return_0bps": float(np.median(net_0bps)) if net_0bps else None,
        "median_net_forward_return_2bps": median_primary_net,
        "median_net_forward_return_5bps": float(np.median(net_5bps)) if net_5bps else None,
        "same_ticker_time_of_day_baseline_mean": mean_baseline,
        "same_ticker_time_of_day_baseline_median": median_baseline,
        "event_minus_baseline_difference_mean": mean_uplift,
        "event_minus_baseline_difference_median": median_uplift,
        "per_ticker_primary_results": {
            t: {
                "event_count": ticker_counts[t],
                "mean_net_return_2bps": per_ticker_net_means.get(t),
            }
            for t in sorted(ticker_counts.keys())
        },
        "monthly_primary_results": monthly_primary_results,
    }

    bootstrap_dict = {
        "primary_net_return": {
            "point_estimate": event_ci.point_estimate,
            "ci_lower": event_ci.ci_lower,
            "ci_upper": event_ci.ci_upper,
            "resamples": event_ci.resamples,
            "seed": event_ci.seed,
            "status": event_ci.status,
            "error_reason": event_ci.error_reason,
        },
        "event_minus_baseline_uplift": {
            "point_estimate": uplift_ci.point_estimate,
            "ci_lower": uplift_ci.ci_lower,
            "ci_upper": uplift_ci.ci_upper,
            "resamples": uplift_ci.resamples,
            "seed": uplift_ci.seed,
            "status": uplift_ci.status,
            "error_reason": uplift_ci.error_reason,
        },
    }

    return StudyResult(
        task_id=spec.task_id,
        split=split_name,
        disposition=disposition,
        disposition_step=disp_step,
        disposition_reason=disp_reason,
        metrics=metrics,
        gates=gates_dict,
        bootstrap=bootstrap_dict,
        data_quality={},
        provenance={"spec_sha256": spec.sha256},
    )
