"""End-to-end pipeline verification on deterministic synthetic fixtures for development, validation, and holdout."""
from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

import tradex.research.daytrade_momentum.freeze as freeze_mod
from tradex.research.daytrade_momentum.artifacts import write_artifact_bundle
from tradex.research.daytrade_momentum.calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from tradex.research.daytrade_momentum.dataset import DaytradeDatasetManifest
from tradex.research.daytrade_momentum.freeze import freeze_evaluation_state
from tradex.research.daytrade_momentum.models import (
    DataQualityReport,
    DaytradeSession,
)
from tradex.research.daytrade_momentum.quality import audit_ticker_session
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.study import evaluate_split
from tradex.research.daytrade_momentum.synthetic import (
    generate_synthetic_session_bars,
)


@pytest.fixture(autouse=True)
def mock_clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock clean worktree for e2e tests."""
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)


def build_synthetic_history_and_split(
    spec: DaytradeSpec,
    history_dates: list[date],
    split_dates: list[date],
) -> tuple[dict[str, list[DaytradeSession]], list[DataQualityReport]]:
    """Generate synthetic multi-session data for history and target split."""
    all_dates = history_dates + split_dates
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    all_reports: list[DataQualityReport] = []

    for sym in spec.universe:
        ticker_sessions: list[DaytradeSession] = []
        base_px = 100.0

        for idx, s_date in enumerate(all_dates):
            grid = build_regular_session_grid(s_date)

            # Alternate between strong move (event) and mild move (baseline)
            # 20 history sessions: provide normal modest variance
            if idx < len(history_dates):
                # Mild move: signal return ~ +0.5%
                sig_px = base_px * 1.005
                exit_px = base_px * 1.006
            else:
                # Target split sessions: alternate events and baselines
                if idx % 2 == 0:
                    # Event: +2.0% signal return (exceeds 80th percentile)
                    sig_px = base_px * 1.020
                    # Positive forward move: +0.8% from 15:30 to 15:59
                    exit_px = base_px * 1.028
                else:
                    # Baseline: +0.2% signal return
                    sig_px = base_px * 1.002
                    exit_px = base_px * 1.003

            entry_px = sig_px * 1.001

            df = generate_synthetic_session_bars(
                sym,
                s_date,
                base_price=base_px,
                signal_09_59_close=sig_px,
                entry_15_30_open=entry_px,
                exit_15_59_close=exit_px,
            )
            sess, rep = audit_ticker_session(sym, s_date, df, grid)
            ticker_sessions.append(sess)
            all_reports.append(rep)

            base_px = exit_px

        sessions_by_ticker[sym] = ticker_sessions

    return sessions_by_ticker, all_reports


def test_e2e_development_split_pipeline(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, temp_output_dir: Path
) -> None:
    """Verify complete end-to-end evaluation on development split."""
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=50)

    # 25 warmup sessions + 10 development sessions
    history_sessions = get_regular_trading_sessions(
        locked_spec.warmup.start, locked_spec.warmup.end, exclude_early_closes=True
    )[:25]
    dev_sessions = get_regular_trading_sessions(
        locked_spec.development.start, locked_spec.development.end, exclude_early_closes=True
    )[:10]

    sessions_by_ticker, reports = build_synthetic_history_and_split(
        locked_spec, history_sessions, dev_sessions
    )

    result = evaluate_split(
        split_name="development",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    assert result.split == "development"
    assert result.disposition in ("supported", "inconclusive", "rejected")
    assert len(result.metrics) >= 30
    assert result.provenance["task_id"] == "DAYTRADE-002B"
    assert result.provenance["spec_sha256"] == locked_spec.sha256

    # Output artifact bundle
    bundle_dir = temp_output_dir / "dev_bundle"
    checksums = write_artifact_bundle(
        output_dir=bundle_dir,
        result=result,
        spec=fast_spec,
    )
    assert (bundle_dir / "study.json").is_file()
    assert (bundle_dir / "checksums.sha256").is_file()
    assert len(checksums) >= 12


def test_e2e_validation_split_pipeline(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, temp_output_dir: Path
) -> None:
    """Verify complete end-to-end evaluation on validation split with required freeze binding."""
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=50)

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date=locked_spec.context_anchor_date,
        end_date=locked_spec.validation.end,
        source_files={f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe},
    )
    manifest_sha = manifest.compute_sha256()

    # Freeze evaluation code bound to manifest
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256=manifest_sha,
        require_clean=False,
    )

    # 25 development sessions (as history) + 10 validation sessions
    history_sessions = get_regular_trading_sessions(
        locked_spec.development.start, locked_spec.development.end, exclude_early_closes=True
    )[:25]
    val_sessions = get_regular_trading_sessions(
        locked_spec.validation.start, locked_spec.validation.end, exclude_early_closes=True
    )[:10]

    sessions_by_ticker, reports = build_synthetic_history_and_split(
        locked_spec, history_sessions, val_sessions
    )

    result = evaluate_split(
        split_name="validation",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        freeze=freeze,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    assert result.split == "validation"
    assert result.disposition in ("supported", "inconclusive", "rejected")
    assert result.provenance["evaluator_code_sha"] == freeze.evaluation_code_sha

    # Output artifact bundle
    val_bundle_dir = temp_output_dir / "val_bundle"
    checksums = write_artifact_bundle(
        output_dir=val_bundle_dir,
        result=result,
        spec=fast_spec,
        freeze=freeze,
    )
    assert (val_bundle_dir / "study.json").is_file()
    assert (val_bundle_dir / "freeze.json").is_file()
    assert (val_bundle_dir / "checksums.sha256").is_file()
    assert len(checksums) >= 13


def test_first_development_threshold_with_context_anchor(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Verify context anchor (2025-12-31) provides prior close for Jan 2, never enters threshold history,

    and exactly 20 warmup sessions enable the very first development session (2026-02-02) to evaluate.
    """
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=20)
    context_anchor_d = date(2025, 12, 31)

    # 20 warmup sessions: Jan 2 through Jan 30, 2026
    warmup_sessions = get_regular_trading_sessions(
        locked_spec.warmup.start, locked_spec.warmup.end, exclude_early_closes=True
    )[:20]
    first_dev_session = date(2026, 2, 2)

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    reports: list[DataQualityReport] = []

    for sym in locked_spec.universe:
        ticker_sessions: list[DaytradeSession] = []

        # 1. Context anchor session (2025-12-31): provides 15:59 close only
        anchor_df = generate_synthetic_session_bars(sym, context_anchor_d, base_price=100.0, exit_15_59_close=100.0)
        s_anchor, r_anchor = audit_ticker_session(sym, context_anchor_d, anchor_df, build_regular_session_grid(context_anchor_d))
        ticker_sessions.append(s_anchor)
        reports.append(r_anchor)

        # 2. 20 warmup sessions
        curr_price = 100.0
        for w_d in warmup_sessions:
            sig_px = curr_price * 1.005  # modest move
            exit_px = curr_price * 1.006
            w_df = generate_synthetic_session_bars(
                sym, w_d, base_price=curr_price, signal_09_59_close=sig_px, exit_15_59_close=exit_px
            )
            s_w, r_w = audit_ticker_session(sym, w_d, w_df, build_regular_session_grid(w_d))
            ticker_sessions.append(s_w)
            reports.append(r_w)
            curr_price = exit_px

        # 3. First development session (2026-02-02): strong move (+2.0%)
        dev_sig_px = curr_price * 1.020
        dev_exit_px = curr_price * 1.025
        dev_df = generate_synthetic_session_bars(
            sym, first_dev_session, base_price=curr_price, signal_09_59_close=dev_sig_px, exit_15_59_close=dev_exit_px
        )
        s_dev, r_dev = audit_ticker_session(sym, first_dev_session, dev_df, build_regular_session_grid(first_dev_session))
        ticker_sessions.append(s_dev)
        reports.append(r_dev)

        sessions_by_ticker[sym] = ticker_sessions

    res = evaluate_split(
        split_name="development",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    # Context anchor and warmup sessions must NOT enter target development events/non-events
    for ev in res.events:
        assert ev.session_date == first_dev_session
        assert ev.threshold > 0.0
    for ne in res.non_events:
        assert ne.session_date == first_dev_session

    assert res.split == "development"
    assert res.metrics["eligible_ticker_session_count"] == len(locked_spec.universe)


def test_validation_walkback_across_invalid_late_dev_sessions(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Verify validation split walks back across earlier authorized sessions to find 20 valid sessions

    when late development sessions are invalid under DQ rules.
    """
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=20)

    all_dev_sessions = get_regular_trading_sessions(
        locked_spec.development.start, locked_spec.development.end, exclude_early_closes=True
    )
    dev_history = all_dev_sessions[-26:]
    prior_session = dev_history[0]
    early_dev = dev_history[1:21]  # 20 valid sessions
    late_dev_invalid = dev_history[21:]  # 5 invalid sessions immediately preceding validation

    val_sessions = get_regular_trading_sessions(
        locked_spec.validation.start, locked_spec.validation.end, exclude_early_closes=True
    )[:2]

    # Freeze
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="val_manifest_sha_123",
        require_clean=False,
    )

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    reports: list[DataQualityReport] = []

    for sym in locked_spec.universe:
        ticker_sessions: list[DaytradeSession] = []
        base_px = 100.0

        # Prior session: supplies 15:59 close to early_dev[0]
        df_p = generate_synthetic_session_bars(sym, prior_session, base_price=base_px, exit_15_59_close=base_px)
        s_p, r_p = audit_ticker_session(sym, prior_session, df_p, build_regular_session_grid(prior_session))
        ticker_sessions.append(s_p)
        reports.append(r_p)

        # Early dev (20 valid sessions)
        for d in early_dev:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, signal_09_59_close=base_px * 1.005, exit_15_59_close=base_px * 1.006
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.006

        # Late dev (5 invalid sessions: drop 25 bars > 5%, but keep exit 15:59 close)
        drop_mins = [f"{10 + i // 60:02d}:{i % 60:02d}" for i in range(25)]
        for d in late_dev_invalid:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, exit_15_59_close=base_px * 1.001, drop_minutes=drop_mins
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.001

        # Validation target sessions
        for d in val_sessions:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, signal_09_59_close=base_px * 1.020, exit_15_59_close=base_px * 1.028
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.028

        sessions_by_ticker[sym] = ticker_sessions

    res = evaluate_split(
        split_name="validation",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        freeze=freeze,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    # First validation session successfully acquired a 20-valid threshold because
    # it walked back through late invalid sessions into early dev and warmup!
    assert res.split == "validation"
    assert res.metrics["eligible_ticker_session_count"] == len(val_sessions) * len(locked_spec.universe)
    for ev in res.events:
        assert ev.session_date in val_sessions
        assert ev.split == "validation"


def test_holdout_dual_partition_walkback_and_isolation(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, temp_output_dir: Path
) -> None:
    """Verify holdout evaluation correctly uses preholdout for threshold history walkback,

    while strictly isolating holdout events, non-events, baselines, and metrics.
    """
    from tests.research.daytrade_momentum.test_holdout_guard import (
        create_mock_supported_validation_bundle,
    )

    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=20)
    vdir = temp_output_dir / "val_bundle"
    create_mock_supported_validation_bundle(vdir, locked_spec)

    # 26 preholdout history sessions (ending 2026-06-30): 1 prior + 20 valid early + 5 invalid late
    val_sessions = get_regular_trading_sessions(
        locked_spec.validation.start, locked_spec.validation.end, exclude_early_closes=True
    )
    history_sessions = val_sessions[-26:]
    prior_session = history_sessions[0]
    early_val = history_sessions[1:21]  # 20 valid sessions
    late_val_invalid = history_sessions[21:]  # 5 invalid sessions immediately preceding holdout

    holdout_sessions = get_regular_trading_sessions(
        locked_spec.holdout.start, locked_spec.holdout.end, exclude_early_closes=True
    )[:2]

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    reports: list[DataQualityReport] = []

    for sym in locked_spec.universe:
        ticker_sessions: list[DaytradeSession] = []
        base_px = 100.0

        # Prior session
        df_p = generate_synthetic_session_bars(sym, prior_session, base_price=base_px, exit_15_59_close=base_px)
        s_p, r_p = audit_ticker_session(sym, prior_session, df_p, build_regular_session_grid(prior_session))
        ticker_sessions.append(s_p)
        reports.append(r_p)

        # Early validation (20 valid sessions)
        for d in early_val:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, signal_09_59_close=base_px * 1.005, exit_15_59_close=base_px * 1.006
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.006

        # Late validation (5 invalid sessions: drop 25 bars > 5%, but keep 15:59 close)
        drop_mins = [f"{10 + i // 60:02d}:{i % 60:02d}" for i in range(25)]
        for d in late_val_invalid:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, exit_15_59_close=base_px * 1.001, drop_minutes=drop_mins
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.001

        # Holdout target sessions (2 sessions)
        for d in holdout_sessions:
            df = generate_synthetic_session_bars(
                sym, d, base_price=base_px, signal_09_59_close=base_px * 1.020, exit_15_59_close=base_px * 1.028
            )
            s, r = audit_ticker_session(sym, d, df, build_regular_session_grid(d))
            ticker_sessions.append(s)
            reports.append(r)
            base_px = base_px * 1.028

        sessions_by_ticker[sym] = ticker_sessions

    res = evaluate_split(
        split_name="holdout",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        validation_artifact_dir=vdir,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    assert res.split == "holdout"
    assert res.metrics["eligible_ticker_session_count"] == len(holdout_sessions) * len(locked_spec.universe)
    assert len(res.events) > 0

    # Strict isolation: preholdout history sessions NEVER enter holdout events or non-events
    for ev in res.events:
        assert ev.session_date in holdout_sessions
        assert ev.split == "holdout"
    for ne in res.non_events:
        assert ne.session_date in holdout_sessions
        assert ne.split == "holdout"
