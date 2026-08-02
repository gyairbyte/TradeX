"""CLI tests for the score-validation package."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.research.score_validation.cli import main

from .conftest import write_bars_and_manifest


def _assert_exit(args: list[str], code: int = 0) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    assert exc_info.value.code == code


def test_root_help():
    _assert_exit(["--help"], 0)


def test_snapshot_help():
    _assert_exit(["snapshot", "--help"], 0)


def test_evaluate_help():
    _assert_exit(["evaluate", "--help"], 0)


def test_evaluate_offline_end_to_end(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    result_dir = tmp_path / "results"
    ret = main(
        [
            "evaluate",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(result_dir),
            "--warmup-bars",
            "50",
        ]
    )
    assert ret == 0
    assert (result_dir / "study.json").is_file()
    assert (result_dir / "events.csv").is_file()
    assert (result_dir / "report.md").is_file()
    assert (result_dir / "manifest.lock.json").is_file()


def test_snapshot_mocked_end_to_end(tmp_path: Path):
    out = tmp_path / "dataset"

    def fake_history(ticker, start, end, provider=None):
        idx = pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC")
        return pd.DataFrame(
            {
                "open": [100.0] * 120,
                "high": [101.0] * 120,
                "low": [99.0] * 120,
                "close": [100.5] * 120,
                "volume": [1e6] * 120,
            },
            index=idx,
        )

    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.side_effect = fake_history
        ret = main(
            [
                "snapshot",
                "--tickers",
                "AAPL,MSFT",
                "--start",
                "2020-01-01",
                "--end",
                "2020-05-31",
                "--output-dir",
                str(out),
                "--development-split",
                "2020-01-01,2020-03-31",
                "--validation-split",
                "2020-04-01,2020-05-15",
                "--holdout-split",
                "2020-05-16,2020-05-31",
                "--provider",
                "yahoo",
            ]
        )
    assert ret == 0
    assert (out / "manifest.json").is_file()
    assert (out / "AAPL.csv").is_file()
    assert (out / "MSFT.csv").is_file()


def test_checksum_failure_exits_nonzero(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(data, indent=2))
    result_dir = tmp_path / "results"
    ret = main(
        [
            "evaluate",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(result_dir),
        ]
    )
    assert ret != 0


def test_invalid_comma_arguments_exit_nonzero(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    result_dir = tmp_path / "results"
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "evaluate",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(result_dir),
                "--horizons",
                "1,foo,5",
            ]
        )
    assert exc_info.value.code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["--horizons", "1,,5"],
        ["--thresholds", "20,"],
        ["--slippage-bps", "0,,2.5"],
        ["--score-buckets", ",0,20,40"],
    ],
)
def test_empty_comma_segments_rejected(tmp_path: Path, args: list[str]):
    """Leading, trailing, and doubled commas must be rejected."""
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    result_dir = tmp_path / "results"
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "evaluate",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(result_dir),
            ]
            + args
        )
    assert exc_info.value.code != 0


def test_snapshot_empty_ticker_segment_rejected(tmp_path: Path):
    """A nonempty ticker list with an empty segment must not silently discard it."""
    result_dir = tmp_path / "results"
    ret = main(
        [
            "snapshot",
            "--tickers",
            "AAPL,,MSFT",
            "--start",
            "2020-01-01",
            "--end",
            "2020-12-31",
            "--output-dir",
            str(result_dir),
            "--development-split",
            "2020-01-01,2020-04-30",
            "--validation-split",
            "2020-05-01,2020-08-31",
            "--holdout-split",
            "2020-09-01,2020-12-31",
        ]
    )
    assert ret != 0


def test_no_network_in_evaluation(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    result_dir = tmp_path / "results"
    components = {
        n: True
        for n in [
            "ema_structure",
            "volume_confirmation",
            "rsi_momentum",
            "macd_positive",
            "pullback_ema",
        ]
    }
    points = {
        n: 10
        for n in [
            "ema_structure",
            "volume_confirmation",
            "rsi_momentum",
            "macd_positive",
            "pullback_ema",
        ]
    }
    with patch("tradex.research.score_validation.events.short_term_score") as fake:
        fake.return_value = {
            "score": 50,
            "reasons": ["test"],
            "last_close": 100.0,
            "components": components,
            "component_points": points,
        }
        ret = main(
            [
                "evaluate",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(result_dir),
                "--warmup-bars",
                "50",
            ]
        )
    assert ret == 0
    assert (result_dir / "events.csv").is_file()
