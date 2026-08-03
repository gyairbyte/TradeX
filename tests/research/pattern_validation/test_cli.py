"""Tests for the pattern-validation CLI."""
from __future__ import annotations

import pytest

from tradex.research.pattern_validation.cli import main


def test_cli_help_requires_no_credentials():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_snapshot_help_requires_no_credentials():
    with pytest.raises(SystemExit) as exc:
        main(["snapshot", "--help"])
    assert exc.value.code == 0


def test_evaluate_help_requires_no_credentials():
    with pytest.raises(SystemExit) as exc:
        main(["evaluate", "--help"])
    assert exc.value.code == 0


def test_snapshot_and_evaluate_roundtrip(tmp_path, tiny_study_dates, tiny_spec):
    snap = tmp_path / "snap"
    eval_out = tmp_path / "eval"
    # Build spec JSON for CLI.
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(tiny_spec.to_json(indent=2), encoding="utf-8")

    def fetch_fn(ticker, start, end, provider):
        from .conftest import make_synthetic_bars
        return make_synthetic_bars(ticker, start, end, seed=abs(hash(ticker)) % 10000)

    from tradex.research.pattern_validation.snapshot import create_snapshot
    manifest_path = create_snapshot(
        tickers=list(tiny_spec.tickers),
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=snap,
        splits=tiny_study_dates["splits"],
        fetch_fn=fetch_fn,
        overwrite=True,
    )

    rc = main([
        "evaluate",
        "--manifest", str(manifest_path),
        "--output", str(eval_out),
        "--spec", str(spec_path),
        "--overwrite",
    ])
    assert rc == 0
    assert (eval_out / "study.json").exists()
