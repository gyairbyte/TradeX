"""Unit tests for the point-in-time capture command-line interface."""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.capture import build_parser, main


def test_cli_parser_options() -> None:
    parser = build_parser()

    # Valid evening arguments
    args = parser.parse_args(["earnings", "--slot", "evening", "--symbols", "AAPL,MSFT", "--source", "yahoo"])
    assert args.subcommand == "earnings"
    assert args.slot == "evening"
    assert args.symbols == "AAPL,MSFT"
    assert args.source == "yahoo"

    # Valid morning arguments
    args_m = parser.parse_args(["earnings", "--slot", "morning", "--symbols", "NVDA"])
    assert args_m.slot == "morning"

    # Invalid slot rejected
    with pytest.raises(SystemExit):
        parser.parse_args(["earnings", "--slot", "afternoon", "--symbols", "NVDA"])

    # Missing symbols rejected
    with pytest.raises(SystemExit):
        parser.parse_args(["earnings", "--slot", "morning"])


def test_cli_main_succeeded_exit_code_0(capsys, tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    with patch("tradex.pit.earnings.get_next_earnings", return_value=date(2026, 9, 15)), \
         patch("tradex.pit.earnings.datetime") as mock_dt:
        mock_dt.now.return_value = clock
        mock_dt.combine = datetime.combine
        mock_dt.fromisoformat = datetime.fromisoformat

        exit_code = main([
            "earnings",
            "--slot", "morning",
            "--symbols", "AAPL,MSFT",
            "--db-path", str(db_path),
        ])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Status:               succeeded" in captured.out
        assert "Requested Count:      2" in captured.out
        assert "Known Count:          2" in captured.out
        assert "api_key" not in captured.out.lower()
        assert "password" not in captured.out.lower()


def test_cli_main_partial_exit_code_2(capsys, tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    def mock_lookup(symbol: str, **kwargs):
        if symbol == "AAPL":
            return date(2026, 9, 15)
        raise RuntimeError("simulated error")

    with patch("tradex.pit.earnings._default_earnings_lookup", side_effect=mock_lookup), \
         patch("tradex.pit.earnings.datetime") as mock_dt:
        mock_dt.now.return_value = clock
        mock_dt.combine = datetime.combine
        mock_dt.fromisoformat = datetime.fromisoformat

        exit_code = main([
            "earnings",
            "--slot", "morning",
            "--symbols", "AAPL,XYZ",
            "--db-path", str(db_path),
        ])

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Status:               partial" in captured.out
        assert "Known Count:          1" in captured.out
        assert "Error Count:          1" in captured.out


def test_cli_main_failed_exit_code_1(capsys, tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    with patch("tradex.pit.earnings._default_earnings_lookup", side_effect=RuntimeError("all fail")), \
         patch("tradex.pit.earnings.datetime") as mock_dt:
        mock_dt.now.return_value = clock
        mock_dt.combine = datetime.combine
        mock_dt.fromisoformat = datetime.fromisoformat

        exit_code = main([
            "earnings",
            "--slot", "morning",
            "--symbols", "AAPL",
            "--db-path", str(db_path),
        ])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Status:               failed" in captured.out
        assert "Known Count:          0" in captured.out
        assert "Error Count:          1" in captured.out


def test_cli_main_validation_error_exit_code_1(capsys, tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    # Invalid symbols string (only whitespace/commas)
    exit_code = main([
        "earnings",
        "--slot", "morning",
        "--symbols", " , , ",
        "--db-path", str(db_path),
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
