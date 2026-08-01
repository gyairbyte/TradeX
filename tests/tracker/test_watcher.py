"""Characterization tests for the scheduled watcher."""
from unittest.mock import MagicMock, patch

import pytest

from tradex.tracker import watcher


@pytest.mark.xfail(strict=True, reason="Watcher provider argument is not propagated to screener_run (COR-004)")
def test_run_once_passes_provider_to_screener(fresh_signal_db):
    """run_once must forward the provider argument to screener_run."""
    captured = {}

    def fake_screener_run(*args, **kwargs):
        captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    with patch.object(watcher, "screener_run", side_effect=fake_screener_run), \
         patch.object(watcher, "_check_alerts"), \
         patch.object(watcher, "run_outcome_pass"):
        watcher.run_once(
            ["AAPL"],
            timeframe="intraday",
            min_score=30,
            provider="alpaca",
        )

    assert "provider" in captured["kwargs"]
    assert captured["kwargs"]["provider"] == "alpaca"
