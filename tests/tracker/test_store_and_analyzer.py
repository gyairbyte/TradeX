"""Characterization tests for signal store and coil analyzer."""

import pandas as pd
import pytest

from tradex.tracker import analyzer, store


def _signal_row(ticker: str = "COIL", score: int = 60) -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": ticker,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": "volume surge",
    }])


@pytest.mark.xfail(strict=True, reason="Coil appearances count scan rows, not distinct sessions (DATA-002/COIL-001)")
def test_coil_counts_distinct_sessions_not_scan_rows(fresh_signal_db):
    """Three scans of the same ticker in one day should count as one appearance."""
    for _ in range(3):
        store.record_signals(_signal_row(), "intraday")

    coils = analyzer.detect_coils("intraday", days=7, min_appearances=2)
    row = coils[coils["ticker"] == "COIL"]
    assert not row.empty
    assert row.iloc[0]["appearances"] == 1, "appearances should count sessions, not scan rows"
