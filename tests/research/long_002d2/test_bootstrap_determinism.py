"""Tests for paired calendar-block bootstrap determinism and properties."""
from __future__ import annotations

import numpy as np

from tradex.research.long_002d2.bootstrap import run_paired_calendar_block_bootstrap


def _create_synthetic_dates_and_results(n_dates: int = 100) -> tuple[list[str], dict[str, dict]]:
    dates = [f"2017-01-{i+1:02d}" if i < 30 else f"2017-02-{i-29:02d}" for i in range(n_dates)]
    results = {}
    for i, d in enumerate(dates):
        # K(date) = 10
        # cand_clean = 2 (20%), vam5_clean = 1 (10%)
        results[d] = {
            "k_date": 10,
            "cand_clean": 2 if i % 2 == 0 else 1,
            "vam5_clean": 1 if i % 3 == 0 else 0,
        }
    return dates, results


def test_bootstrap_exact_determinism() -> None:
    """Verify that two independent bootstrap runs with the same seed yield identical outputs."""
    dates, results = _create_synthetic_dates_and_results(63)
    summaries1, dists1 = run_paired_calendar_block_bootstrap(
        dates, results, block_sizes=(21, 42), replicates=100, seed=20260928
    )
    summaries2, dists2 = run_paired_calendar_block_bootstrap(
        dates, results, block_sizes=(21, 42), replicates=100, seed=20260928
    )

    for b in (21, 42):
        s1 = summaries1[b]
        s2 = summaries2[b]
        assert s1.mean_delta == s2.mean_delta
        assert s1.median_delta == s2.median_delta
        assert s1.std_err == s2.std_err
        assert s1.ci_2_5 == s2.ci_2_5
        assert s1.ci_97_5 == s2.ci_97_5
        np.testing.assert_array_equal(dists1[b], dists2[b])


def test_bootstrap_paired_property() -> None:
    """Verify that if candidate equals baseline on every date, delta is identically zero."""
    dates, _ = _create_synthetic_dates_and_results(42)
    # Identical results for candidate and baseline
    results = {
        d: {"k_date": 10, "cand_clean": 3, "vam5_clean": 3}
        for d in dates
    }
    summaries, dists = run_paired_calendar_block_bootstrap(
        dates, results, block_sizes=(21,), replicates=50, seed=20260928
    )
    s21 = summaries[21]
    assert s21.mean_delta == 0.0
    assert s21.median_delta == 0.0
    assert s21.std_err == 0.0
    assert s21.ci_2_5 == 0.0
    assert s21.ci_97_5 == 0.0
    assert np.all(dists[21] == 0.0)


def test_bootstrap_block_partitioning() -> None:
    """Verify non-overlapping sequential blocks partition the session list."""
    dates, results = _create_synthetic_dates_and_results(63)
    # 63 sessions / 21 sessions per block = exactly 3 blocks
    summaries, dists = run_paired_calendar_block_bootstrap(
        dates, results, block_sizes=(21,), replicates=10, seed=20260928
    )
    assert 21 in summaries
    assert len(dists[21]) == 10
