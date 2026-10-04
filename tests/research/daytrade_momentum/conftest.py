"""Pytest fixtures for DAYTRADE-002B momentum research engine tests."""
from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest

from tradex.research.daytrade_momentum.calendar import get_regular_trading_sessions
from tradex.research.daytrade_momentum.spec import DaytradeSpec, load_and_verify_spec


@pytest.fixture
def locked_spec() -> DaytradeSpec:
    """Return verified locked DAYTRADE-002A specification."""
    return load_and_verify_spec()


@pytest.fixture
def sample_trading_days() -> list[date]:
    """Return 30 consecutive regular trading sessions from early 2025."""
    start = date(2025, 1, 2)
    end = date(2025, 2, 28)
    sessions = get_regular_trading_sessions(start, end, exclude_early_closes=True)
    return sessions[:30]


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that is automatically cleaned up."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def temp_dataset_root() -> Generator[Path, None, None]:
    """Provide a temporary directory outside git repo for private dataset storage."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)
