"""End-to-end pipeline verification on deterministic synthetic fixtures for development and validation."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from tradex.research.daytrade_momentum.artifacts import write_artifact_bundle
from tradex.research.daytrade_momentum.calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from tradex.research.daytrade_momentum.freeze import freeze_evaluation_state
from tradex.research.daytrade_momentum.models import (
    DataQualityReport,
    DaytradeSession,
)
from tradex.research.daytrade_momentum.quality import audit_ticker_session
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.study import evaluate_split
from tradex.research.daytrade_momentum.synthetic import generate_synthetic_session_bars


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
    import dataclasses
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
    import dataclasses
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=50)

    # Freeze evaluation code
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
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
