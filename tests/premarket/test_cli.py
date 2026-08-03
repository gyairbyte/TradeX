"""Tests for the pre-market scanner CLI."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.premarket.cli import main
from tradex.premarket.config import GapScanConfig
from tradex.premarket.models import GapScanReport


def _empty_report(tickers: list[str]) -> GapScanReport:
    return GapScanReport(
        session_date=date(2024, 1, 3),
        as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        requested_provider="yahoo",
        actual_provider="yahoo",
        config=GapScanConfig(),
        requested_tickers=tickers,
        results=pd.DataFrame(columns=["ticker", "prev_close", "pre_market", "gap_pct", "direction", "tier", "note"]),
        observations=pd.DataFrame(columns=["ticker", "status", "filter_reasons"]),
    )


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_scan_help():
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--help"])
    assert exc.value.code == 0


def test_cli_scan_runs_with_mocked_report(tmp_path):
    report = _empty_report(["AAPL"])
    with patch("tradex.premarket.cli.scan_gaps_with_report", return_value=report) as mock_scan:
        code = main(["scan", "--tickers", "AAPL", "--min-gap", "2.0"])
    assert code == 0
    mock_scan.assert_called_once()
    args = mock_scan.call_args
    assert args[0][0] == ["AAPL"]
    assert args[1]["config"].min_abs_gap_pct == 2.0


def test_cli_scan_writes_json_and_csv(tmp_path):
    report = _empty_report(["AAPL"])
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "results.csv"
    with patch("tradex.premarket.cli.scan_gaps_with_report", return_value=report):
        code = main([
            "scan", "--tickers", "AAPL",
            "--json-output", str(json_path),
            "--csv-output", str(csv_path),
        ])
    assert code == 0
    assert json_path.exists()
    assert csv_path.exists()
    data = json.loads(json_path.read_text())
    assert data["requested_tickers"] == ["AAPL"]
    assert data["counts"]["requested"] == 1


def test_cli_rejects_invalid_min_gap():
    with pytest.raises(SystemExit):
        main(["scan", "--tickers", "AAPL", "--min-gap", "abc"])


def test_cli_rejects_empty_ticker():
    with pytest.raises(SystemExit):
        main(["scan", "--tickers", ","])
