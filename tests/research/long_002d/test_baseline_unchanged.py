"""Tests verifying that the frozen development baseline reference is unmodified."""
from __future__ import annotations

import pytest

from tradex.research.long_002d.baseline import load_frozen_baseline_reference
from tradex.research.long_002d.spec import (
    FROZEN_BASELINE_ID,
    FROZEN_BASELINE_TOP_10_CLEAN_RATE,
    FROZEN_BASELINE_TOP_10_LIFT,
    FROZEN_BASELINE_TOP_25_CLEAN_RATE,
    FROZEN_BASELINE_TOP_25_LIFT,
)


def test_frozen_baseline_reference_constants():
    """Verify that frozen baseline reference values match Stage C ground truth exactly."""
    ref = load_frozen_baseline_reference(None)

    assert ref.comparator_id == FROZEN_BASELINE_ID == "volatility_aware_momentum_5"
    assert ref.formula == "0.5 * momentum_5_pct + 0.5 * atr_pct_14_pct"
    assert ref.common_population_observations == 758731
    assert ref.common_population_clean_events == 67257
    assert pytest.approx(ref.common_population_base_rate, abs=1e-5) == 0.088644

    assert ref.top_10_observation_count == 76407
    assert ref.top_10_clean_count == 11731
    assert pytest.approx(ref.top_10_clean_rate, abs=1e-5) == FROZEN_BASELINE_TOP_10_CLEAN_RATE == 0.153533
    assert pytest.approx(ref.top_10_lift, abs=1e-4) == FROZEN_BASELINE_TOP_10_LIFT == 1.7320

    assert ref.top_25_observation_count == 190288
    assert ref.top_25_clean_count == 24144
    assert pytest.approx(ref.top_25_clean_rate, abs=1e-5) == FROZEN_BASELINE_TOP_25_CLEAN_RATE == 0.126881
    assert pytest.approx(ref.top_25_lift, abs=1e-4) == FROZEN_BASELINE_TOP_25_LIFT == 1.4314
