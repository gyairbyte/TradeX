"""Split evaluation orchestrator and strictly guarded holdout evaluation."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

from .baseline import build_baseline_pool, match_event_baselines
from .bootstrap import run_session_date_cluster_bootstrap
from .calendar import (
    get_immediately_preceding_regular_session,
    get_regular_trading_sessions,
)
from .dataset import (
    load_private_dataset,
    sha256_of_file,
)
from .events import (
    calculate_first_half_hour_return,
    classify_session_observation,
    compute_ticker_threshold,
)
from .freeze import EvaluationFreezeRecord, verify_freeze_state
from .gates import evaluate_gates_and_disposition
from .models import (
    BaselineObservation,
    DataQualityReport,
    DaytradeSession,
    EventObservation,
    HoldoutAccessDeniedError,
    StudyResult,
)
from .outcomes import calculate_gross_win_rate
from .quality import evaluate_split_quality
from .spec import (
    DAYTRADE_002A_SPEC_SHA256,
    LOCKED_FROZEN_UNIVERSE,
    DaytradeSpec,
)


def verify_holdout_access_prerequisites(
    validation_artifact_dir: Path | str,
    spec: DaytradeSpec,
    repo_root: Path | None = None,
) -> None:
    """Verify that validation achieved 'supported' disposition and satisfies all 23 locked checks.

    Clarification 4:
    Must execute and fail closed BEFORE reading target holdout bars, creating provider clients,
    or reading provider credentials.
    """
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

    # 2. Verify spec.lock.json (spec SHA match)
    spec_lock_file = vdir / "spec.lock.json"
    spec_lock_data = json.loads(spec_lock_file.read_text(encoding="utf-8"))
    rec_spec_sha = spec_lock_data.get("spec_sha256")
    if rec_spec_sha != DAYTRADE_002A_SPEC_SHA256:
        raise HoldoutAccessDeniedError(
            f"Spec hash mismatch in spec.lock.json: expected {DAYTRADE_002A_SPEC_SHA256}, got {rec_spec_sha}"
        )

    # 3. Verify manifest.lock.json (manifest contract, provider, feed, timeframe, adjustment, calendar, timezone, universe)
    manifest_lock_file = vdir / "manifest.lock.json"
    manifest_data = json.loads(manifest_lock_file.read_text(encoding="utf-8"))
    if manifest_data.get("provider") != "alpaca":
        raise HoldoutAccessDeniedError(f"Manifest provider mismatch: {manifest_data.get('provider')}")
    if manifest_data.get("feed") != "sip":
        raise HoldoutAccessDeniedError(f"Manifest feed mismatch: {manifest_data.get('feed')}")
    if manifest_data.get("timeframe") != "1Min":
        raise HoldoutAccessDeniedError(f"Manifest timeframe mismatch: {manifest_data.get('timeframe')}")
    if manifest_data.get("adjustment") != "split":
        raise HoldoutAccessDeniedError(f"Manifest adjustment mismatch: {manifest_data.get('adjustment')}")
    if manifest_data.get("calendar") != "XNYS":
        raise HoldoutAccessDeniedError(f"Manifest calendar mismatch: {manifest_data.get('calendar')}")
    if manifest_data.get("timezone") != "America/New_York":
        raise HoldoutAccessDeniedError(f"Manifest timezone mismatch: {manifest_data.get('timezone')}")
    if tuple(manifest_data.get("universe", [])) != LOCKED_FROZEN_UNIVERSE:
        raise HoldoutAccessDeniedError("Manifest universe mismatch with locked 15 ETFs")

    manifest_sha = manifest_data.get("manifest_sha256")

    # 4. Verify freeze.json (evaluator code HEAD and file hashes match current state)
    freeze_file = vdir / "freeze.json"
    freeze_data = json.loads(freeze_file.read_text(encoding="utf-8"))
    freeze_record = EvaluationFreezeRecord.from_dict(freeze_data)
    if freeze_record.spec_sha256 != DAYTRADE_002A_SPEC_SHA256:
        raise HoldoutAccessDeniedError("Freeze spec SHA mismatch with canonical DAYTRADE-002A")
    if freeze_record.manifest_sha256 and freeze_record.manifest_sha256 != manifest_sha:
        raise HoldoutAccessDeniedError("Freeze manifest SHA does not match validation manifest lineage")

    verify_freeze_state(freeze_record, repo_root=repo_root, spec=spec)

    # 5. Verify study.json (split == validation, disposition == supported, provenance)
    study_file = vdir / "study.json"
    study_data = json.loads(study_file.read_text(encoding="utf-8"))
    if study_data.get("split") != "validation":
        raise HoldoutAccessDeniedError(f"Validation artifact split mismatch: {study_data.get('split')}")
    if study_data.get("disposition") != "supported":
        raise HoldoutAccessDeniedError(
            f"Validation split achieved disposition '{study_data.get('disposition')}'; "
            "holdout access is strictly prohibited unless validation earns 'supported'."
        )

    study_prov = study_data.get("provenance", {})
    if study_prov.get("spec_sha256") != DAYTRADE_002A_SPEC_SHA256:
        raise HoldoutAccessDeniedError("Study provenance spec SHA mismatch")
    if study_prov.get("evaluator_code_sha") != freeze_record.evaluation_code_sha:
        raise HoldoutAccessDeniedError("Study evaluator SHA mismatch with freeze")
    if study_prov.get("manifest_sha256") and study_prov.get("manifest_sha256") != manifest_sha:
        raise HoldoutAccessDeniedError("Study manifest SHA mismatch with manifest.lock")
    if study_prov.get("evidence_confidence_cap") != "limited_but_usable_evidence":
        raise HoldoutAccessDeniedError("Evidence confidence cap mismatch")
    if study_prov.get("production_promotion_eligible") is not False:
        raise HoldoutAccessDeniedError("Production promotion eligible must be False")

    # 6. Verify strategy-registry invariant remains empty
    if APPROVED_PRODUCTION_STRATEGIES != ():
        raise HoldoutAccessDeniedError("Strategy registry is not empty: APPROVED_PRODUCTION_STRATEGIES != ()")


def evaluate_split(
    split_name: str,
    spec: DaytradeSpec,
    dataset_root: Path | str,
    *,
    freeze: EvaluationFreezeRecord | None = None,
    validation_artifact_dir: Path | str | None = None,
    repo_root: Path | None = None,
    custom_sessions: dict[str, list[DaytradeSession]] | None = None,
    custom_reports: list[DataQualityReport] | None = None,
) -> StudyResult:
    """Execute evaluation of a dataset split (development, validation, or holdout).

    Locked guard rules:
    - Warmup is not an evaluatable performance split;
    - Validation requires a valid EvaluationFreezeRecord;
    - Holdout strictly requires passing verify_holdout_access_prerequisites;
    - Preholdout observations provide threshold history only and NEVER enter holdout metrics/baselines.
    """
    split = split_name.lower().strip()
    if split == "warmup":
        raise ValueError("Warmup is history-only and cannot be evaluated as a target performance split.")
    if split not in ("development", "validation", "holdout"):
        raise ValueError(f"Unsupported split '{split}'. Must be 'development', 'validation', or 'holdout'.")

    # Guard validation freeze requirement
    if split == "validation" and freeze is None:
        raise ValueError("Validation split evaluation strictly requires a bound EvaluationFreezeRecord.")

    # Guard holdout prerequisites
    if split == "holdout":
        if validation_artifact_dir is None:
            raise HoldoutAccessDeniedError("Holdout evaluation requires --validation-artifact-dir pointing to supported validation evidence.")
        verify_holdout_access_prerequisites(validation_artifact_dir, spec, repo_root=repo_root)

    # Load private dataset or use custom injected synthetic data
    if custom_sessions is not None and custom_reports is not None:
        sessions_by_ticker = custom_sessions
        quality_reports = custom_reports
    else:
        sessions_by_ticker, quality_reports = load_private_dataset(
            dataset_root=dataset_root,
            spec=spec,
            split_name=split,
            include_history=True,
            repo_root=repo_root,
        )

    # Determine split dates and target calendar sessions
    split_dates = spec.get_split_dates(split)
    target_sessions = get_regular_trading_sessions(split_dates.start, split_dates.end, exclude_early_closes=True)
    target_sessions_set = set(target_sessions)

    # Evaluate split-level data quality
    split_quality = evaluate_split_quality(
        split_name=split,
        quality_reports=quality_reports,
        expected_sessions=target_sessions,
        universe_symbols=spec.universe,
    )

    # Extract chronologically ordered session objects per ticker
    events: list[EventObservation] = []
    non_events: list[BaselineObservation] = []
    eligible_ticker_sessions_count = 0

    # For each ticker, process sessions chronologically
    for sym in spec.universe:
        ticker_sessions = sessions_by_ticker.get(sym, [])
        ticker_sessions_sorted = sorted(ticker_sessions, key=lambda s: s.session_date)

        # Map session_date -> session
        session_map = {s.session_date: s for s in ticker_sessions_sorted}

        # Track history of valid signal returns for rolling threshold
        # (Clarification 2: observation enters threshold history if session.is_valid and signal is computable)
        valid_history_returns: list[float] = []

        for s in ticker_sessions_sorted:
            s_date = s.session_date
            is_target_split = s_date in target_sessions_set

            # Find the immediately preceding regular XNYS session
            prev_regular_date = get_immediately_preceding_regular_session(s_date, exclude_early_closes=True)
            prev_session = session_map.get(prev_regular_date) if prev_regular_date else None

            # Calculate first-half-hour return
            # (Clarification 2: requires only usable 15:59 close from previous regular session)
            sig_ret = calculate_first_half_hour_return(s, prev_session)

            # Compute threshold using rolling 20 valid prior signal sessions
            thresh = compute_ticker_threshold(valid_history_returns)

            # If this session is within target split and meets eligibility, classify
            if is_target_split and s.is_valid and sig_ret is not None and thresh is not None:
                eligible_ticker_sessions_count += 1
                ev, ne = classify_session_observation(s, sig_ret, thresh, split)
                if ev is not None:
                    events.append(ev)
                elif ne is not None:
                    non_events.append(ne)

            # Update threshold history AFTER evaluating current session
            # (Clarification 2: session must be valid and sig_ret computable to enter threshold history)
            if s.is_valid and sig_ret is not None:
                valid_history_returns.append(sig_ret)

    # Build direction-matched baseline pool strictly within target split
    baseline_pool = build_baseline_pool(non_events)
    match_event_baselines(events, baseline_pool, friction_bps=spec.primary_cost_bps_per_side)

    # Run Session-Date Cluster Bootstrap (Clarification 3)
    # Clusters are target-split session dates that contain eligible observations
    cluster_dates = sorted(target_sessions_set)
    primary_ci, uplift_ci = run_session_date_cluster_bootstrap(
        events=events,
        non_events=non_events,
        eligible_session_dates=cluster_dates,
        resamples=spec.bootstrap_resamples,
        seed=spec.bootstrap_seed,
        confidence_level_pct=spec.bootstrap_confidence_level_pct,
        friction_bps=spec.primary_cost_bps_per_side,
    )

    # Compute Core Metrics
    event_count = len(events)
    represented_etf_set = {e.ticker for e in events}
    represented_etf_count = len(represented_etf_set)

    event_dates_set = {e.session_date for e in events}
    event_session_count = len(event_dates_set)

    # Count multi-signal sessions (>= 2 ETF events on same date)
    date_event_counts: dict[date, int] = defaultdict(int)
    for e in events:
        date_event_counts[e.session_date] += 1
    multi_signal_session_count = sum(1 for cnt in date_event_counts.values() if cnt >= 2)
    multi_signal_session_rate = (
        float(multi_signal_session_count) / float(event_session_count)
        if event_session_count > 0 else 0.0
    )

    # Single ETF event concentration
    etf_event_counts: dict[str, int] = defaultdict(int)
    for e in events:
        etf_event_counts[e.ticker] += 1
    max_single_etf_count = max(etf_event_counts.values()) if etf_event_counts else 0
    max_concentration_pct = (
        (float(max_single_etf_count) / float(event_count)) * 100.0
        if event_count > 0 else 0.0
    )

    # Long and Short counts
    long_events = [e for e in events if e.direction == "LONG"]
    short_events = [e for e in events if e.direction == "SHORT"]
    long_event_count = len(long_events)
    short_event_count = len(short_events)

    # Return distributions
    gross_returns = [e.gross_return for e in events]
    net_returns_0bps = [e.net_return_0bps for e in events]
    net_returns_2bps = [e.net_return_2bps for e in events]
    net_returns_5bps = [e.net_return_5bps for e in events]

    mean_gross_signed_return = float(np.mean(gross_returns)) if gross_returns else 0.0
    median_gross_signed_return = float(np.median(gross_returns)) if gross_returns else 0.0
    win_rate_gross = calculate_gross_win_rate(gross_returns)

    mean_net_0bps = float(np.mean(net_returns_0bps)) if net_returns_0bps else 0.0
    mean_net_2bps = float(np.mean(net_returns_2bps)) if net_returns_2bps else 0.0
    mean_net_5bps = float(np.mean(net_returns_5bps)) if net_returns_5bps else 0.0

    median_net_0bps = float(np.median(net_returns_0bps)) if net_returns_0bps else 0.0
    median_net_2bps = float(np.median(net_returns_2bps)) if net_returns_2bps else 0.0
    median_net_5bps = float(np.median(net_returns_5bps)) if net_returns_5bps else 0.0

    # Baseline & Uplift summary
    valid_base_refs = [e.matched_baseline_net_2bps for e in events if e.matched_baseline_net_2bps is not None]
    valid_uplifts = [e.uplift_net_2bps for e in events if e.uplift_net_2bps is not None]

    matched_baseline_mean = float(np.mean(valid_base_refs)) if valid_base_refs else None
    matched_baseline_median = float(np.median(valid_base_refs)) if valid_base_refs else None

    uplift_mean = float(np.mean(valid_uplifts)) if valid_uplifts else None
    uplift_median = float(np.median(valid_uplifts)) if valid_uplifts else None

    # Per-ETF primary results & breadth
    per_etf_results: dict[str, Any] = {}
    positive_etfs_count = 0
    for sym in represented_etf_set:
        sym_events = [e for e in events if e.ticker == sym]
        sym_net_2bps = [e.net_return_2bps for e in sym_events]
        sym_gross = [e.gross_return for e in sym_events]
        sym_mean_net = float(np.mean(sym_net_2bps)) if sym_net_2bps else 0.0
        if sym_mean_net > 0.0:
            positive_etfs_count += 1
        per_etf_results[sym] = {
            "event_count": len(sym_events),
            "mean_net_signed_return_2bps": sym_mean_net,
            "win_rate_gross": calculate_gross_win_rate(sym_gross),
        }

    pct_positive_etfs = (
        (float(positive_etfs_count) / float(represented_etf_count)) * 100.0
        if represented_etf_count > 0 else 0.0
    )

    # Per-month primary results
    per_month_results: dict[str, Any] = {}
    events_per_month: dict[str, int] = defaultdict(int)
    for e in events:
        mo_str = e.session_date.strftime("%Y-%m")
        events_per_month[mo_str] += 1
    for mo_str in sorted(events_per_month.keys()):
        mo_events = [e for e in events if e.session_date.strftime("%Y-%m") == mo_str]
        mo_net = [e.net_return_2bps for e in mo_events]
        per_month_results[mo_str] = {
            "event_count": len(mo_events),
            "mean_net_signed_return_2bps": float(np.mean(mo_net)) if mo_net else 0.0,
        }

    # Long and Short sub-cohort results
    long_net = [e.net_return_2bps for e in long_events]
    short_net = [e.net_return_2bps for e in short_events]
    long_uplifts = [e.uplift_net_2bps for e in long_events if e.uplift_net_2bps is not None]
    short_uplifts = [e.uplift_net_2bps for e in short_events if e.uplift_net_2bps is not None]

    long_side_results = {
        "event_count": len(long_events),
        "mean_net_signed_return_2bps": float(np.mean(long_net)) if long_net else 0.0,
        "mean_uplift_2bps": float(np.mean(long_uplifts)) if long_uplifts else None,
        "win_rate_gross": calculate_gross_win_rate([e.gross_return for e in long_events]),
    }
    short_side_results = {
        "event_count": len(short_events),
        "mean_net_signed_return_2bps": float(np.mean(short_net)) if short_net else 0.0,
        "mean_uplift_2bps": float(np.mean(short_uplifts)) if short_uplifts else None,
        "win_rate_gross": calculate_gross_win_rate([e.gross_return for e in short_events]),
    }

    # Assemble all 30 locked metrics
    metrics = {
        "eligible_ticker_session_count": eligible_ticker_sessions_count,
        "event_count": event_count,
        "represented_etf_count": represented_etf_count,
        "event_session_count": event_session_count,
        "events_per_etf": dict(etf_event_counts),
        "events_per_month": dict(events_per_month),
        "long_event_count": long_event_count,
        "short_event_count": short_event_count,
        "maximum_single_etf_event_concentration": max_concentration_pct,
        "multi_signal_session_count": multi_signal_session_count,
        "multi_signal_session_rate": multi_signal_session_rate,
        "mean_gross_signed_return_30m": mean_gross_signed_return,
        "median_gross_signed_return_30m": median_gross_signed_return,
        "win_rate_gross_30m": win_rate_gross,
        "mean_net_signed_return_0bps": mean_net_0bps,
        "mean_net_signed_return_2bps": mean_net_2bps,
        "mean_net_signed_return_5bps": mean_net_5bps,
        "median_net_signed_return_0bps": median_net_0bps,
        "median_net_signed_return_2bps": median_net_2bps,
        "median_net_signed_return_5bps": median_net_5bps,
        "matched_non_event_baseline_mean": matched_baseline_mean,
        "matched_non_event_baseline_median": matched_baseline_median,
        "event_minus_baseline_mean": uplift_mean,
        "event_minus_baseline_median": uplift_median,
        "per_etf_primary_results": per_etf_results,
        "per_month_primary_results": per_month_results,
        "long_side_primary_results": long_side_results,
        "short_side_primary_results": short_side_results,
        "data_quality_summary": {
            "total_ticker_sessions": split_quality.total_ticker_sessions,
            "excluded_ticker_sessions": split_quality.excluded_ticker_sessions,
            "excluded_rate_pct": split_quality.excluded_rate_pct,
            "exceeds_split_gate": split_quality.exceeds_split_gate,
            "exclusion_breakdown": split_quality.exclusion_breakdown,
        },
        "provider_provenance_summary": {
            "provider": "alpaca",
            "feed": "sip",
            "timeframe": "1Min",
            "adjustment": "split",
            "calendar": "XNYS",
            "timezone": "America/New_York",
            "status": "synthetic_fixtures_only",
        },
    }

    # Evaluate all 6 validation gates & disposition
    disp, disp_step, disp_reason, gates = evaluate_gates_and_disposition(
        event_count=event_count,
        represented_etfs=represented_etf_count,
        event_session_count=event_session_count,
        max_etf_concentration_pct=max_concentration_pct,
        mean_primary_net_return_2bps=mean_net_2bps if event_count > 0 else None,
        primary_ci=primary_ci,
        mean_uplift_2bps=uplift_mean,
        uplift_ci=uplift_ci,
        pct_positive_etfs=pct_positive_etfs,
        per_etf_net_means={sym: d["mean_net_signed_return_2bps"] for sym, d in per_etf_results.items()},
        split_quality=split_quality,
        integrity_error=None,
    )

    provenance = {
        "task_id": "DAYTRADE-002B",
        "spec_sha256": spec.sha256,
        "evaluator_code_sha": freeze.evaluation_code_sha if freeze else "unfrozen_synthetic",
        "manifest_sha256": freeze.manifest_sha256 if freeze and freeze.manifest_sha256 else "",
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
        task_id="DAYTRADE-002B",
        study_name="DAYTRADE-002: Early-to-Late ETF Intraday Momentum",
        split=split,
        disposition=disp,
        disposition_step=disp_step,
        disposition_reason=disp_reason,
        gates=gates,
        metrics=metrics,
        bootstrap={
            "primary_net_return": primary_ci.to_dict(),
            "event_minus_baseline_uplift": uplift_ci.to_dict(),
        },
        quality_summary=split_quality,
        provenance=provenance,
        events=events,
        non_events=non_events,
        quality_reports=quality_reports,
    )


def load_and_evaluate_holdout(
    spec: DaytradeSpec,
    dataset_root: Path | str,
    validation_artifact_dir: Path | str,
    *,
    freeze: EvaluationFreezeRecord | None = None,
    repo_root: Path | None = None,
) -> StudyResult:
    """Safely verify prerequisites and evaluate the locked holdout split."""
    return evaluate_split(
        split_name="holdout",
        spec=spec,
        dataset_root=dataset_root,
        freeze=freeze,
        validation_artifact_dir=validation_artifact_dir,
        repo_root=repo_root,
    )
