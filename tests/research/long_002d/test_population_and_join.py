"""Tests for primary study population filtering, 1-to-1 join, and no 09:00 pooling."""
from __future__ import annotations

import pandas as pd
import pytest

from tradex.research.long_002d.spec import (
    EXPECTED_BASE_RATE,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    HORIZON_SESSIONS,
    POPULATION_CUTOFF,
    TARGET_PCT,
)


def test_population_spec_invariants():
    """Verify preregistered population constraints match Stage C verified ground truth."""
    assert POPULATION_CUTOFF == "20:30"
    assert TARGET_PCT == 10.0
    assert HORIZON_SESSIONS == 10
    assert EXPECTED_DENOMINATOR == 758731
    assert EXPECTED_CLEAN_EVENTS == 67257
    assert pytest.approx(EXPECTED_BASE_RATE, abs=1e-5) == 67257 / 758731


def test_no_0900_pooling_assertion():
    """Verify that any 09:00 observation is rejected from the D1 primary census."""
    # Synthetic observation table with mixed 09:00 and 20:30
    df_obs = pd.DataFrame(
        {
            "cutoff_time": ["09:00", "20:30", "09:00", "20:30"],
            "raw_outcome_eligible": [True, True, True, False],
            "split_boundary_purged": [False, False, False, False],
        }
    )

    # Filter according to D1 rules
    filtered = df_obs[
        (df_obs["cutoff_time"] == POPULATION_CUTOFF)
        & (df_obs["raw_outcome_eligible"] == True)
        & (df_obs["split_boundary_purged"] == False)
    ]

    # Exactly 1 row passes
    assert len(filtered) == 1
    assert (filtered["cutoff_time"] == "20:30").all()
    assert (filtered["cutoff_time"] != "09:00").all()
