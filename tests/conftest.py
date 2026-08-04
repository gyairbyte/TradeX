"""Shared pytest fixtures and configuration for TradeX tests."""

import pytest

from tradex.tracker import store


@pytest.fixture
def fresh_signal_db(tmp_path, monkeypatch):
    """Point the tracker store at a temporary database and initialize it."""
    db_path = tmp_path / "signals.db"
    monkeypatch.setenv("TRADEX_DB_PATH", str(db_path))
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init()
    yield db_path
    # No explicit cleanup needed; tmp_path is removed by pytest.
