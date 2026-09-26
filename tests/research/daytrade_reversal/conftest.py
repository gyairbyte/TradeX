"""Pytest fixtures for DAYTRADE-001C1 reversal study engine testing."""
from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest

from tradex.research.daytrade_reversal.calendar import get_regular_trading_sessions
from tradex.research.daytrade_reversal.spec import DaytradeSpec, load_and_verify_spec


@pytest.fixture
def locked_spec() -> DaytradeSpec:
    """Return the verified locked DAYTRADE-001B specification."""
    return load_and_verify_spec()


@pytest.fixture
def sample_trading_days() -> list[date]:
    """Return 25 consecutive regular trading days from early 2025."""
    start = date(2025, 1, 2)
    end = date(2025, 2, 10)
    sessions = get_regular_trading_sessions(start, end, exclude_early_close=True)
    return sessions[:25]


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that is automatically cleaned up."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)
