"""Tests for the backtest CLI."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from tradex.backtest.cli import main


def _csv(tmp_path, bars: pd.DataFrame) -> Path:
    path = tmp_path / "bars.csv"
    bars.reset_index().rename(columns={"index": "datetime"}).to_csv(path, index=False)
    return path


def test_help_runs_without_network_or_credentials():
    proc = subprocess.run(
        ["uv", "run", "python", "-m", "tradex.backtest", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--csv" in proc.stdout


def test_offline_csv_run(tmp_path, short_term_qualifying_bars):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(csv),
            "--ticker",
            "SPY",
            "--min-score",
            "40",
            "--warmup-bars",
            "60",
            "--holding-bars",
            "3",
            "--stop-loss-pct",
            "5",
            "--take-profit-pct",
            "10",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Total return" in proc.stdout
    assert "Ticker:        SPY" in proc.stdout


def test_json_output_has_no_nan_or_infinity(tmp_path, short_term_qualifying_bars):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    json_path = tmp_path / "result.json"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(csv),
            "--ticker",
            "SPY",
            "--min-score",
            "40",
            "--warmup-bars",
            "60",
            "--json-output",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(json_path.read_text())
    assert data["ticker"] == "SPY"
    assert "metrics" in data


def test_trades_and_equity_outputs(tmp_path, short_term_qualifying_bars):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    trades_path = tmp_path / "trades.csv"
    equity_path = tmp_path / "equity.csv"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(csv),
            "--ticker",
            "SPY",
            "--min-score",
            "40",
            "--warmup-bars",
            "60",
            "--trades-output",
            str(trades_path),
            "--equity-output",
            str(equity_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert trades_path.exists()
    assert equity_path.exists()
    trades_df = pd.read_csv(trades_path)
    assert "ticker" in trades_df.columns
    equity_df = pd.read_csv(equity_path, index_col=0)
    assert "position_ticker" in equity_df.columns


def test_no_trade_run_succeeds(tmp_path):
    n = 80
    close = pd.Series([100.0] * n)
    bars = pd.DataFrame(
        {
            "open": (close - 0.5).to_numpy(),
            "high": (close + 1.0).to_numpy(),
            "low": (close - 1.0).to_numpy(),
            "close": close.to_numpy(),
            "volume": [1e6] * n,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
    )
    csv = _csv(tmp_path, bars)
    trades_path = tmp_path / "trades.csv"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(csv),
            "--ticker",
            "FLAT",
            "--min-score",
            "100",
            "--warmup-bars",
            "60",
            "--trades-output",
            str(trades_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Trades:        0 executed" in proc.stdout
    # No-trade CSV must still contain the stable trade-schema header.
    trades_df = pd.read_csv(trades_path)
    assert list(trades_df.columns) == [
        "ticker",
        "signal_time",
        "entry_time",
        "exit_time",
        "score",
        "reasons",
        "raw_entry_price",
        "entry_fill_price",
        "raw_exit_price",
        "exit_fill_price",
        "stop_price",
        "target_price",
        "exit_reason",
        "bars_held",
        "gross_return_pct",
        "net_return_pct",
        "commission_bps",
        "slippage_bps",
        "quantity",
        "starting_cash",
        "ending_cash",
    ]
    assert len(trades_df) == 0


def test_invalid_csv_fails_cleanly(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("not,a,csv\n1,2,3\n")
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(bad_csv),
            "--ticker",
            "BAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Error" in proc.stderr


def test_provider_mode_calls_fetch_daily_history(tmp_path, short_term_qualifying_bars, monkeypatch):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    fetched = {}

    def _fake_fetch(ticker, start, end, provider=None):
        fetched["called"] = True
        fetched["provider"] = provider
        return pd.read_csv(csv, parse_dates=["datetime"], index_col="datetime")

    monkeypatch.setattr("tradex.data.history.fetch_daily_history", _fake_fetch)
    rc = main(
        [
            "--ticker",
            "AAPL",
            "--start",
            "2020-01-01",
            "--end",
            "2020-04-30",
            "--provider",
            "schwab",
        ]
    )
    assert rc == 0
    assert fetched.get("called") is True
    assert fetched.get("provider") == "schwab"


def test_provider_mode_resolves_omitted_provider_from_env(tmp_path, short_term_qualifying_bars, monkeypatch):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    fetched = {}

    def _fake_fetch(ticker, start, end, provider=None):
        fetched["provider"] = provider
        return pd.read_csv(csv, parse_dates=["datetime"], index_col="datetime")

    monkeypatch.setattr("tradex.data.history.fetch_daily_history", _fake_fetch)
    monkeypatch.setenv("DATA_PROVIDER", "yahoo")
    rc = main(
        [
            "--ticker",
            "AAPL",
            "--start",
            "2020-01-01",
            "--end",
            "2020-04-30",
        ]
    )
    assert rc == 0
    assert fetched.get("provider") == "yahoo"


def test_provider_mode_records_resolved_provider_as_data_source(tmp_path, short_term_qualifying_bars, monkeypatch):
    csv = _csv(tmp_path, short_term_qualifying_bars)

    def _fake_fetch(ticker, start, end, provider=None):
        return pd.read_csv(csv, parse_dates=["datetime"], index_col="datetime")

    monkeypatch.setattr("tradex.data.history.fetch_daily_history", _fake_fetch)
    result_path = tmp_path / "result.json"
    rc = main(
        [
            "--ticker",
            "AAPL",
            "--start",
            "2020-01-01",
            "--end",
            "2020-04-30",
            "--provider",
            "SCHWAB",
            "--json-output",
            str(result_path),
        ]
    )
    assert rc == 0
    data = json.loads(result_path.read_text())
    assert data["data_source"] == "schwab"


def test_invalid_config_fails_cleanly(tmp_path, short_term_qualifying_bars):
    csv = _csv(tmp_path, short_term_qualifying_bars)
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tradex.backtest",
            "--csv",
            str(csv),
            "--ticker",
            "SPY",
            "--stop-loss-pct",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Error" in proc.stderr
