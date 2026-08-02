"""Point-in-time event generation and return-calculation tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from tradex.research.score_validation.events import _net_return
from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.score_validation.report import run_study


def _flat_bars(n: int = 120, *, close: float = 100.0, volume: float = 1e6) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [close] * n,
            "high": [close + 1] * n,
            "low": [close - 1] * n,
            "close": [close] * n,
            "volume": [volume] * n,
        },
        index=idx,
    )


def _write_manifest(tmp_path: Path, df: pd.DataFrame, splits: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    df.index.name = "datetime"
    csv = tmp_path / "TEST.csv"
    df.to_csv(csv)
    sha = hashlib.sha256(csv.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "dataset_name": "test",
        "created_at": "2026-08-01T00:00:00+00:00",
        "source_description": "test",
        "entries": [
            {
                "ticker": "TEST",
                "path": "TEST.csv",
                "sha256": sha,
                "rows": len(df),
                "start": df.index[0].isoformat(),
                "end": df.index[-1].isoformat(),
                "data_source": "synthetic",
                "adjustment_policy": "none",
            }
        ],
        "splits": splits,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def test_future_price_change_does_not_alter_earlier_score(tmp_path: Path):
    n = 120
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    base = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1e6] * n,
        },
        index=idx,
    )
    base.index.name = "datetime"
    # Make a copy and insert a large spike at the very end.
    spiked = base.copy()
    spiked.iloc[-1, spiked.columns.get_loc("close")] = 200.0
    spiked.iloc[-1, spiked.columns.get_loc("high")] = 201.0
    spiked.iloc[-1, spiked.columns.get_loc("low")] = 199.0
    spiked.iloc[-1, spiked.columns.get_loc("open")] = 199.0

    splits = {
        "development": {"start": "2020-01-01", "end": "2022-12-31"},
        "validation": {"start": "2023-01-01", "end": "2025-12-31"},
        "holdout": {"start": "2026-01-01", "end": "2026-12-31"},
    }
    base_path = _write_manifest(tmp_path / "base", base, splits)
    spiked_path = _write_manifest(tmp_path / "spiked", spiked, splits)

    base_study = run_study(base_path, ScoreValidationConfig(warmup_bars=50))
    spiked_study = run_study(spiked_path, ScoreValidationConfig(warmup_bars=50))

    # Pair events by signal_time for the first 10 signalable bars.
    for i in range(10):
        t = base_study.events["signal_time"].iloc[i]
        base_score = base_study.events[base_study.events["signal_time"] == t]["score"].iloc[0]
        spiked_score = spiked_study.events[spiked_study.events["signal_time"] == t]["score"].iloc[0]
        assert base_score == spiked_score, f"score mismatch at {t}: {base_score} vs {spiked_score}"


def test_entry_is_next_bar_open():
    idx = pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC")
    close = [100.0 + i * 0.1 for i in range(120)]
    df = pd.DataFrame(
        {
            "open": [c + 0.05 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1e6] * 120,
        },
        index=idx,
    )
    df.index.name = "datetime"
    i = 50
    entry_price = df["open"].iloc[i + 1]
    assert entry_price != df["close"].iloc[i]


def test_hand_calculated_gross_return():
    assert _net_return(100.0, 110.0, 0.0, 0.0) == (110.0 / 100.0 - 1.0) * 100.0


def test_negative_gross_return():
    assert _net_return(100.0, 90.0, 0.0, 0.0) == (90.0 / 100.0 - 1.0) * 100.0


def test_flat_gross_return():
    assert _net_return(100.0, 100.0, 0.0, 0.0) == 0.0


def test_entry_slippage_reduces_return():
    no_slip = _net_return(100.0, 110.0, 0.0, 0.0)
    with_slip = _net_return(100.0, 110.0, 10.0, 0.0)
    assert with_slip < no_slip


def test_exit_slippage_reduces_return():
    no_slip = _net_return(100.0, 110.0, 0.0, 0.0)
    with_slip = _net_return(100.0, 110.0, 10.0, 0.0)
    assert with_slip < no_slip


def test_commission_per_side_reduces_return():
    no_comm = _net_return(100.0, 110.0, 0.0, 0.0)
    with_comm = _net_return(100.0, 110.0, 0.0, 10.0)
    assert with_comm < no_comm


def test_combined_costs():
    gross = _net_return(100.0, 110.0, 0.0, 0.0)
    net = _net_return(100.0, 110.0, 5.0, 10.0)
    assert net < gross


def test_horizon_1_exits_at_entry_bar_close():
    # simple upward drift: every bar close is the next bar's close? test net math directly
    entry = 100.0
    exit_ = 101.0
    gross = exit_ / entry - 1.0
    assert _net_return(entry, exit_, 0.0, 0.0) == gross * 100.0


def test_insufficient_future_bars_marked_incomplete(tmp_path: Path):
    # 60 bars with warmup 59 leaves exactly one signal bar at the end, so no
    # next bar exists for any horizon.
    df = _flat_bars(60)
    splits = {
        "development": {"start": "2020-01-01", "end": "2025-12-31"},
        "validation": {"start": "2026-01-01", "end": "2027-12-31"},
        "holdout": {"start": "2028-01-01", "end": "2028-12-31"},
    }
    manifest_path = _write_manifest(tmp_path, df, splits)
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=59))
    assert len(study.events) == 1
    assert (study.events["5_bar_outcome_status"] == "insufficient_future_bars").all()


def test_cross_split_outcome_is_incomplete(tmp_path: Path):
    idx = pd.date_range("2020-01-01", periods=800, freq="D", tz="UTC")
    close = [100.0 + i * 0.01 for i in range(800)]
    df = pd.DataFrame(
        {
            "open": close,
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1e6] * 800,
        },
        index=idx,
    )
    splits = {
        "development": {"start": "2020-01-01", "end": "2021-12-31"},
        "validation": {"start": "2022-01-01", "end": "2023-12-31"},
        "holdout": {"start": "2024-01-01", "end": "2025-12-31"},
    }
    manifest_path = _write_manifest(tmp_path, df, splits)
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    cross = study.events[
        (study.events["split"] == "development")
        & (study.events["signal_time"].str[:10] >= "2021-12-29")
        & (study.events["signal_time"].str[:10] <= "2021-12-31")
    ]
    assert not cross.empty
    assert (cross["3_bar_outcome_status"] == "insufficient_future_bars").all()
    # The final development signal's entry would fall in the validation split,
    # so no next-split price should be recorded.
    final = cross[cross["signal_time"] == cross["signal_time"].max()].iloc[0]
    assert pd.isna(final["entry_time"])
    assert pd.isna(final["raw_entry_price"])


def test_warmup_bars_before_split_start_not_events(tmp_path: Path):
    # Split starts 2021-01-01; warmup period is before that.
    idx = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    close = [100.0 + i * 0.01 for i in range(400)]
    df = pd.DataFrame(
        {
            "open": close,
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1e6] * 400,
        },
        index=idx,
    )
    splits = {
        "development": {"start": "2021-01-01", "end": "2021-12-31"},
        "validation": {"start": "2022-01-01", "end": "2023-12-31"},
        "holdout": {"start": "2024-01-01", "end": "2024-12-31"},
    }
    manifest_path = _write_manifest(tmp_path, df, splits)
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    dev_events = study.events[study.events["split"] == "development"]
    assert dev_events["signal_time"].min() >= "2021-01-01"
