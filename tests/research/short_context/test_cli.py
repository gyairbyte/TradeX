"""Tests for the short_context CLI."""
from __future__ import annotations

import pytest

from tradex.research.short_context.cli import main


def test_main_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "snapshot" in out
    assert "evaluate" in out


def test_snapshot_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["snapshot", "--help"])
    assert exc.value.code == 0
    assert "context-spec" in capsys.readouterr().out


def test_evaluate_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["evaluate", "--help"])
    assert exc.value.code == 0
    assert "manifest" in capsys.readouterr().out


def test_snapshot_without_spec_exits(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["snapshot", "--output-dir", str(tmp_path), "--start", "2020-01-01", "--end", "2020-12-31"])
    assert exc.value.code != 0
