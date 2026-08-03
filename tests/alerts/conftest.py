"""Shared fixtures for alert policy tests."""
from __future__ import annotations

import pytest

from tradex.alerts.policy import AlertPolicy
from tradex.alerts.store import AlertStore


@pytest.fixture
def tmp_alert_store(tmp_path):
    """Return an isolated AlertStore using a temporary file.

    The database is created on first use.
    """
    return AlertStore(tmp_path / "alerts.db")


@pytest.fixture
def tmp_alert_policy(tmp_alert_store):
    """Return an isolated AlertPolicy using a temporary state file."""
    return AlertPolicy(store=tmp_alert_store)


@pytest.fixture
def null_transport():
    """Return a transport that always returns all channels disabled."""
    def _transport(subject: str, body: str, color_key: str = "test") -> dict[str, bool]:
        return {"discord": False, "email": False}
    return _transport


@pytest.fixture
def success_transport():
    """Return a transport that reports Discord success."""
    def _transport(subject: str, body: str, color_key: str = "test") -> dict[str, bool]:
        return {"discord": True, "email": False}
    return _transport


@pytest.fixture
def configured_checker():
    """Return an is_configured callable that reports channels are configured."""
    def _checker() -> bool:
        return True
    return _checker
