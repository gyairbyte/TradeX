"""Characterization tests for the screener engine."""
from unittest.mock import patch

import pytest

from tradex.screener import engine


@pytest.mark.xfail(strict=True, reason="Engine returns empty DataFrame instead of an error summary when all fetches fail (COR-013)")
def test_engine_reports_provider_failures():
    """When every fetch fails, the engine should distinguish fetch errors from zero signals."""
    with patch.object(engine, "fetch", side_effect=RuntimeError("network")), \
         patch.object(engine, "days_until_earnings", return_value=None):
        result = engine.run(["AAPL", "MSFT"], timeframe="intraday")

    # Desired behavior: result should expose an error count or error summary
    assert hasattr(result, "errors") or "errors" in result
    assert result.errors["AAPL"] is not None
    assert result.total_scanned == 2
    assert result.total_signals == 0
