"""Tests for the full study runner and artifact writer."""
from __future__ import annotations

import json

from tradex.research.pattern_validation.report import run_study, write_study
from tradex.research.pattern_validation.snapshot import create_snapshot


def _synthetic_fetcher(ticker, start, end, provider):
    from .conftest import make_synthetic_bars
    return make_synthetic_bars(ticker, start, end, seed=abs(hash(ticker)) % 10000)


def test_run_study_produces_required_artifacts(tmp_path, tiny_study_dates, tiny_spec):
    snap = tmp_path / "snap"
    manifest_path = create_snapshot(
        tickers=list(tiny_spec.tickers),
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=snap,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    from tradex.research.pattern_validation.snapshot import load_snapshot
    manifest, bars = load_snapshot(manifest_path)
    study = run_study(manifest, bars, tiny_spec)
    out = tmp_path / "eval"
    artifacts = write_study(study, out, overwrite=True)

    required = {
        "study.json",
        "study_spec.lock.json",
        "manifest.lock.json",
        "development_fingerprints.json",
        "observations.csv",
        "qualifying_signals.csv",
        "frequency_matched_controls.csv",
        "event_study.csv",
        "executable_trades.csv",
        "baseline_comparison.csv",
        "ticker_summary.csv",
        "period_summary.csv",
        "data_quality.csv",
        "promotion_decision.json",
        "report.md",
        "artifact_manifest.json",
    }
    missing = required - set(artifacts.keys())
    assert not missing, f"missing artifacts: {missing}"
    assert all((out / name).exists() for name in required)

    # Study.json is deterministic and JSON-safe.
    study_data = json.loads((out / "study.json").read_text(encoding="utf-8"))
    assert study_data["spec_sha256"] == tiny_spec.sha256
    assert study_data["promotion_decision"]["production_promotion_eligible"] is False


def test_report_contains_neutral_language(tmp_path, tiny_study_dates, tiny_spec):
    snap = tmp_path / "snap"
    manifest_path = create_snapshot(
        tickers=list(tiny_spec.tickers),
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=snap,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    from tradex.research.pattern_validation.snapshot import load_snapshot
    manifest, bars = load_snapshot(manifest_path)
    study = run_study(manifest, bars, tiny_spec)
    report = study.report_markdown
    assert "shape resemblance" in report
    assert "causality" in report
    assert "Predictive value" not in report
