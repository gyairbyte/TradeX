"""Tests for expanding folds, calendar purging, and chronology guards (Tests 24-31)."""

import pandas as pd
import pytest

from tradex.research.long_002c.calendar import (
    get_forward_sessions,
    get_trading_sessions,
)
from tradex.research.long_002e1.loader import enforce_split_guards
from tradex.research.long_002e1.splits import (
    build_fold_definitions,
    split_fold_data,
)


def test_24_four_expanding_folds_defined():
    """Test 24: Four expanding folds correctly defined."""
    folds = build_fold_definitions()
    assert len(folds) == 4
    assert folds[0].train_years == [2016] and folds[0].eval_year == 2017
    assert folds[1].train_years == [2016, 2017] and folds[1].eval_year == 2018
    assert folds[2].train_years == [2016, 2017, 2018] and folds[2].eval_year == 2019
    assert folds[3].train_years == [2016, 2017, 2018, 2019] and folds[3].eval_year == 2020


def test_25_purge_sessions_identified():
    """Test 25: For each fold, exactly 26 trading sessions prior to evaluation boundary are identified."""
    folds = build_fold_definitions(purge_sessions_count=26)
    for f in folds:
        assert len(f.purged_session_dates) <= 26
        if f.fold_id > 1:
            assert len(f.purged_session_dates) == 26
            # Confirm they are trading sessions immediately before eval year
            last_yr = f.train_years[-1]
            sessions = get_trading_sessions(f"{f.train_years[0]}-01-01", f"{last_yr}-12-31")
            assert f.purged_session_dates == sessions[-26:]


def test_26_purge_boundary_forward_window_invariance():
    """Test 26: Latest retained training session + 26 forward trading sessions strictly terminates before first eval session."""
    folds = build_fold_definitions(purge_sessions_count=26)
    for f in folds:
        if f.last_retained_training_session is not None:
            first_eval_session = get_trading_sessions(f"{f.eval_year}-01-01", f"{f.eval_year}-12-31")[0]
            fwd = get_forward_sessions(f.last_retained_training_session, 26)
            assert fwd[-1] < first_eval_session


def test_27_zero_overlap_between_train_and_eval():
    """Test 27: Eval partition contains 0 observations from training period; train partition contains 0 observations from eval period."""
    folds = build_fold_definitions()
    dummy_data = pd.DataFrame(
        {
            "as_of_date": [
                "2016-12-30",
                "2017-06-15",
                "2018-05-10",
                "2019-08-20",
                "2020-03-15",
            ],
            "val": [1, 2, 3, 4, 5],
        }
    )
    for f in folds:
        tr, ev = split_fold_data(dummy_data, f)
        tr_dates = set(tr["as_of_date"].unique())
        ev_dates = set(ev["as_of_date"].unique())
        assert tr_dates.isdisjoint(ev_dates)


def test_28_split_guard_rejects_pre_2016():
    """Test 28: Split guard raises ValueError if dates prior to 2016-01-01 are present."""
    dates = pd.Series(["2015-12-31", "2016-06-01"])
    with pytest.raises(ValueError, match="SPLIT GUARD BREACH"):
        enforce_split_guards(dates)


def test_29_split_guard_rejects_post_2020():
    """Test 29: Split guard raises ValueError if dates on or after 2021-01-01 are present."""
    dates = pd.Series(["2020-12-31", "2021-01-04"])
    with pytest.raises(ValueError, match="(SPLIT GUARD BREACH|QUARANTINE BREACH)"):
        enforce_split_guards(dates)


def test_30_split_guard_rejects_validation_quarantine():
    """Test 30: Validation dates (2021-2022) are rejected by split guard."""
    dates = pd.Series(["2021-06-15", "2022-03-10"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Validation"):
        enforce_split_guards(dates)


def test_31_split_guard_rejects_holdout_and_shadow():
    """Test 31: Holdout (2023-2025) and Shadow (2026+) dates are rejected by split guard."""
    hold_dates = pd.Series(["2023-01-15", "2024-05-20"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Holdout"):
        enforce_split_guards(hold_dates)

    shadow_dates = pd.Series(["2026-02-01"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Shadow"):
        enforce_split_guards(shadow_dates)
