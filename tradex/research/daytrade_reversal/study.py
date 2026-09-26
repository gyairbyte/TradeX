"""Split evaluation orchestrator and strictly guarded holdout evaluation."""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from .baseline import build_baseline_pool, match_event_baselines
from .bootstrap import run_joint_cluster_bootstrap
from .calendar import to_market_time
from .dataset import DaytradeDatasetManifest, sha256_of_file
from .events import (
    classify_overlapping_events,
    compute_session_threshold,
    detect_events_in_session,
)
from .freeze import EvaluationFreezeRecord, verify_freeze_state
from .gates import evaluate_gates_and_disposition
from .models import (
    BaselineObservation,
    DataQualityReport,
    DaytradeSession,
    EventObservation,
    StudyResult,
)
from .outcomes import calculate_horizon_outcomes_for_bar
from .quality import evaluate_split_quality, get_expected_split_sessions
from .spec import DAYTRADE_001B_SPEC_SHA256, DaytradeSpec


class HoldoutAccessDeniedError(PermissionError):
    """Raised when holdout data access is requested without satisfying all validation prerequisites."""


def verify_holdout_access_prerequisites(
    validation_artifact_dir: Path | str,
    spec: DaytradeSpec,
    repo_root: Path | None = None,
) -> None:
    """Verify that validation achieved 'supported' disposition and satisfies all evidence requirements."""
    vdir = Path(validation_artifact_dir).expanduser().resolve()
    if not vdir.is_dir():
        raise HoldoutAccessDeniedError(f"Validation artifact directory does not exist: {vdir}")

    # 1. Parse and verify checksums.sha256
    checksum_file = vdir / "checksums.sha256"
    if not checksum_file.is_file():
        raise HoldoutAccessDeniedError(f"Validation checksums.sha256 not found in: {vdir}")

    checksum_lines = checksum_file.read_text(encoding="utf-8").splitlines()
    recorded_checksums: dict[str, str] = {}
    for line in checksum_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            recorded_checksums[parts[1].strip()] = parts[0].strip()

    mandatory_artifacts = [
        "study.json",
        "spec.lock.json",
        "freeze.json",
        "manifest.lock.json",
        "bootstrap.json",
        "metrics.json",
        "data_quality.csv",
        "report.md",
    ]

    for req_fn in mandatory_artifacts:
        fp = vdir / req_fn
        if not fp.is_file():
            raise HoldoutAccessDeniedError(f"Missing required validation artifact: {req_fn}")
        if req_fn not in recorded_checksums:
            raise HoldoutAccessDeniedError(f"Missing checksum entry in checksums.sha256 for: {req_fn}")
        actual_sha = sha256_of_file(fp)
        if actual_sha != recorded_checksums[req_fn]:
            raise HoldoutAccessDeniedError(
                f"Checksum mismatch for {req_fn}: expected {recorded_checksums[req_fn]}, got {actual_sha}"
            )

    # 2. Verify spec.lock.json
    spec_lock_file = vdir / "spec.lock.json"
    try:
        spec_lock_data = json.loads(spec_lock_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HoldoutAccessDeniedError(f"Failed to parse spec.lock.json: {e}") from e

    rec_spec_sha = spec_lock_data.get("spec_sha256")
    if rec_spec_sha != spec.sha256:
        raise HoldoutAccessDeniedError(
            f"Spec hash mismatch in spec.lock.json: {rec_spec_sha} vs current {spec.sha256}"
        )
    if rec_spec_sha != DAYTRADE_001B_SPEC_SHA256:
        raise HoldoutAccessDeniedError(
            f"Spec hash in spec.lock.json does not match canonical DAYTRADE_001B_SPEC_SHA256: {rec_spec_sha}"
        )

    # 3. Verify manifest.lock.json
    manifest_file = vdir / "manifest.lock.json"
    try:
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = DaytradeDatasetManifest.from_dict(manifest_data)
        manifest.validate_against_spec(spec)
    except Exception as e:
        raise HoldoutAccessDeniedError(f"Holdout access denied: manifest verification failed: {e}") from e

    # 4. Verify freeze.json
    freeze_file = vdir / "freeze.json"
    try:
        freeze_data = json.loads(freeze_file.read_text(encoding="utf-8"))
        freeze_record = EvaluationFreezeRecord.from_dict(freeze_data)
        verify_freeze_state(freeze_record, repo_root=repo_root, require_clean=True, require_manifest=True)
    except Exception as e:
        raise HoldoutAccessDeniedError(f"Holdout access denied: evaluator code freeze check failed: {e}") from e

    if freeze_record.spec_sha256 != spec.sha256:
        raise HoldoutAccessDeniedError(
            f"Freeze record spec SHA mismatch: {freeze_record.spec_sha256} vs {spec.sha256}"
        )
    if freeze_record.manifest_sha256 != manifest.manifest_sha256:
        raise HoldoutAccessDeniedError(
            f"Freeze record manifest SHA mismatch: {freeze_record.manifest_sha256} vs {manifest.manifest_sha256}"
        )

    # 5. Verify study.json
    study_file = vdir / "study.json"
    try:
        study_data = json.loads(study_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HoldoutAccessDeniedError(f"Failed to parse validation study.json: {e}") from e

    if study_data.get("split") != "validation":
        raise HoldoutAccessDeniedError(
            f"Supplied study artifact split is '{study_data.get('split')}', expected 'validation'"
        )

    disposition = study_data.get("disposition")
    if disposition != "supported":
        raise HoldoutAccessDeniedError(
            f"Holdout access denied: validation disposition is '{disposition}', must be strictly 'supported'."
        )

    evaluator_sha = study_data.get("evaluator_code_sha")
    if evaluator_sha != freeze_record.evaluation_code_sha:
        raise HoldoutAccessDeniedError(
            f"study.json evaluator_code_sha '{evaluator_sha}' mismatch with freeze '{freeze_record.evaluation_code_sha}'"
        )

    study_spec_sha = study_data.get("spec_sha256")
    if study_spec_sha != spec.sha256:
        raise HoldoutAccessDeniedError(
            f"study.json spec_sha256 '{study_spec_sha}' mismatch with locked spec '{spec.sha256}'"
        )

    study_manifest_sha = study_data.get("manifest_sha256")
    if study_manifest_sha != manifest.manifest_sha256:
        raise HoldoutAccessDeniedError(
            f"study.json manifest_sha256 '{study_manifest_sha}' mismatch with validation manifest '{manifest.manifest_sha256}'"
        )

    if study_data.get("provider") != "alpaca" or study_data.get("feed") != "sip":
        raise HoldoutAccessDeniedError("study.json provider or feed mismatch with locked contract")

    if study_data.get("evidence_confidence_cap") != "limited_but_usable_evidence":
        raise HoldoutAccessDeniedError("study.json evidence_confidence_cap invalid")


def load_and_evaluate_holdout(
    validation_artifact_dir: Path | str,
    spec: DaytradeSpec,
    holdout_loader: Callable[[], tuple[list[DaytradeSession], list[DataQualityReport]] | list[DaytradeSession]],
    repo_root: Path | None = None,
) -> StudyResult:
    """Safely load and evaluate holdout data strictly guarded by the validation gate.

    The holdout_loader function will NEVER be invoked if validation prerequisites fail.
    """
    verify_holdout_access_prerequisites(
        validation_artifact_dir=validation_artifact_dir,
        spec=spec,
        repo_root=repo_root,
    )

    # Only reached if prerequisites pass!
    res = holdout_loader()
    if isinstance(res, tuple):
        holdout_sessions, holdout_dq = res
    else:
        holdout_sessions = res
        holdout_dq = []

    return evaluate_split(
        split_name="holdout",
        sessions=holdout_sessions,
        spec=spec,
        data_quality_reports=holdout_dq,
    )


def evaluate_split(
    split_name: str,
    sessions: list[DaytradeSession],
    spec: DaytradeSpec,
    data_quality_reports: list[DataQualityReport] | None = None,
    integrity_error: str | None = None,
    freeze_record: EvaluationFreezeRecord | None = None,
    manifest_sha256: str | None = None,
) -> StudyResult:
    """Execute the locked DAYTRADE-001 reversal study on a prepared dataset split."""
    name = split_name.lower().strip()
    target_dates = spec.get_split_dates(name)
    split_end_dt = spec.get_split_end_datetime(name)

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
            session_d_str = session.session_date.isoformat()
            is_target = target_dates.start <= session_d_str <= target_dates.end
            is_history = session_d_str < target_dates.start

            # Ignore future sessions outside target split
            if not (is_target or is_history):
                continue

            if not session.is_valid:
                continue

            if is_target:
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
    )

    # Statistical inference: joint cluster bootstrap
    cluster_list = sorted(all_clusters)
    event_ci, uplift_ci = run_joint_cluster_bootstrap(
        events=all_events,
        non_events=all_qualifying_non_events,
        all_clusters=cluster_list,
        resamples=spec.bootstrap_resamples,
        seed=spec.bootstrap_seed,
    )

    # Event counts and concentrations
    event_count = len(all_events)
    ticker_counts: dict[str, int] = defaultdict(int)
    for e in all_events:
        ticker_counts[e.ticker] += 1

    represented_tickers = len(ticker_counts)
    max_concentration_pct = (
        (max(ticker_counts.values()) / float(event_count) * 100.0)
        if event_count > 0
        else 0.0
    )

    # Primary net return mean (1m, 2 bps)
    primary_net_returns = [
        e.outcomes[1].net_return_2bps
        for e in all_events
        if 1 in e.outcomes
    ]
    mean_primary_net = (
        float(np.mean(primary_net_returns)) if primary_net_returns else None
    )

    # Uplift return mean
    uplift_returns = [
        e.uplift_1m_net
        for e in all_events
        if e.uplift_1m_net is not None
    ]
    mean_uplift = (
        float(np.mean(uplift_returns)) if uplift_returns else None
    )

    # Multi-horizon summary
    h1_gross = [e.outcomes[1].gross_return for e in all_events if 1 in e.outcomes]
    h2_gross = [e.outcomes[2].gross_return for e in all_events if 2 in e.outcomes]
    h5_gross = [e.outcomes[5].gross_return for e in all_events if 5 in e.outcomes]

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

    # Monthly primary net results
    monthly_events: dict[str, list[float]] = defaultdict(list)
    for e in all_events:
        if 1 in e.outcomes:
            month_key = e.session_date.strftime("%Y-%m")
            monthly_events[month_key].append(e.outcomes[1].net_return_2bps)

    monthly_summary: dict[str, dict[str, Any]] = {}
    for m_key, m_rets in sorted(monthly_events.items()):
        monthly_summary[m_key] = {
            "event_count": len(m_rets),
            "mean_net_return_2bps": float(np.mean(m_rets)) if m_rets else None,
        }

    # Data Quality accounting for the target split
    expected_sessions = get_expected_split_sessions(target_dates.start, target_dates.end)
    total_expected_ticker_sessions = len(spec.universe) * len(expected_sessions)
    split_quality = evaluate_split_quality(
        data_quality_reports or [],
        split_name=split_name,
        total_expected_ticker_sessions=total_expected_ticker_sessions,
    )

    # Evaluate gates and 5-step disposition precedence
    disposition, disp_step, disp_reason, gates_dict = evaluate_gates_and_disposition(
        event_count=event_count,
        represented_tickers=represented_tickers,
        max_ticker_concentration_pct=max_concentration_pct,
        mean_primary_net_return_2bps=mean_primary_net,
        event_ci=event_ci,
        mean_uplift_2bps=mean_uplift,
        uplift_ci=uplift_ci,
        pct_positive_tickers=pct_positive_tickers,
        per_ticker_net_means=per_ticker_net_means,
        split_quality=split_quality,
        integrity_error=integrity_error,
    )

    # Metrics bundle
    metrics: dict[str, Any] = {
        "event_count": event_count,
        "represented_ticker_count": represented_tickers,
        "maximum_single_ticker_event_concentration": max_concentration_pct,
        "overlapping_event_count": overlapping_count,
        "overlapping_event_rate": overlapping_rate,
        "mean_net_forward_return_2bps": mean_primary_net,
        "mean_net_forward_return_0bps": float(np.mean(net_0bps)) if net_0bps else None,
        "mean_net_forward_return_5bps": float(np.mean(net_5bps)) if net_5bps else None,
        "mean_gross_forward_return_1m": float(np.mean(h1_gross)) if h1_gross else None,
        "mean_gross_forward_return_2m": float(np.mean(h2_gross)) if h2_gross else None,
        "mean_gross_forward_return_5m": float(np.mean(h5_gross)) if h5_gross else None,
        "same_ticker_time_of_day_baseline_mean": (
            float(np.mean([e.matched_baseline_1m_net for e in all_events if e.matched_baseline_1m_net is not None]))
            if any(e.matched_baseline_1m_net is not None for e in all_events)
            else None
        ),
        "event_minus_baseline_difference_mean": mean_uplift,
        "pct_positive_representation_tickers": pct_positive_tickers,
        "win_rate_1m": (
            sum(1 for r in primary_net_returns if r > 0) / float(len(primary_net_returns))
            if primary_net_returns
            else 0.0
        ),
        "monthly_primary_results": monthly_summary,
        "data_quality_summary": asdict(split_quality),
    }

    bootstrap_results: dict[str, Any] = {
        "primary_net_return": asdict(event_ci),
        "event_minus_baseline_uplift": asdict(uplift_ci),
    }

    provenance = {
        "spec_sha256": spec.sha256,
        "evaluator_code_sha": freeze_record.evaluation_code_sha if freeze_record else None,
        "manifest_sha256": manifest_sha256,
        "provider": "alpaca",
        "feed": "sip",
        "timeframe": "1Min",
        "adjustment": "split",
        "calendar": "XNYS",
        "timezone": "America/New_York",
        "evidence_confidence_cap": "limited_but_usable_evidence",
        "production_promotion_eligible": False,
    }

    return StudyResult(
        task_id=spec.task_id,
        split=split_name,
        disposition=disposition,
        disposition_step=disp_step,
        disposition_reason=disp_reason,
        metrics=metrics,
        gates=gates_dict,
        bootstrap=bootstrap_results,
        data_quality=asdict(split_quality),
        provenance=provenance,
    )
