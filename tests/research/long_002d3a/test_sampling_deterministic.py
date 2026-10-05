"""Deterministic pilot sampling tests for LONG-002D3A."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.long_002d3a.sampler import sample_pilot_cases
from tradex.research.long_002d3a.spec import (
    DEV_END,
    DEV_START,
    PILOT_QUOTA_PER_STRATUM,
    PILOT_SEED,
    PILOT_SIZE,
    STRATA_PRECEDENCE,
)


@pytest.fixture(scope="module")
def stage_c_dir() -> Path:
    p = Path("data/research/long_002c")
    if not p.exists():
        pytest.skip(f"Stage C data directory not available: {p}")
    return p


def test_pilot_sampling_size_and_quotas(stage_c_dir: Path) -> None:
    cases = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)
    assert len(cases) == PILOT_SIZE == 24

    strata_counts: dict[str, int] = {}
    for c in cases:
        strata_counts[c.sample_stratum] = strata_counts.get(c.sample_stratum, 0) + 1

    assert set(strata_counts.keys()) == set(STRATA_PRECEDENCE)
    for count in strata_counts.values():
        assert count == PILOT_QUOTA_PER_STRATUM == 6


def test_pilot_sampling_ticker_diversity(stage_c_dir: Path) -> None:
    cases = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)
    tickers = [c.ticker_at_decision for c in cases]
    assert len(tickers) == PILOT_SIZE == 24
    assert len(set(tickers)) == PILOT_SIZE == 24, "Every pilot case must have a unique ticker"


def test_pilot_sampling_annual_diversity(stage_c_dir: Path) -> None:
    cases = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)
    strata_years: dict[str, set[str]] = {s: set() for s in STRATA_PRECEDENCE}
    for c in cases:
        strata_years[c.sample_stratum].add(c.year)
        assert DEV_START <= c.as_of_date <= DEV_END

    expected_dev_years = {"2016", "2017", "2018", "2019", "2020"}
    for stratum, years in strata_years.items():
        # Stratum must cover development years (at least 4 out of 5, typically all 5)
        assert len(years & expected_dev_years) >= 4, f"{stratum} covers {years}"


def test_pilot_sampling_opaque_case_ids(stage_c_dir: Path) -> None:
    cases = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)
    for idx, c in enumerate(cases, start=1):
        expected_id = f"D3A-PILOT-{idx:03d}"
        assert c.case_id == expected_id
        # Case ID must not reveal stratum, date, or ticker
        assert c.sample_stratum not in c.case_id
        assert c.ticker_at_decision not in c.case_id
        assert c.as_of_date not in c.case_id


def test_pilot_sampling_determinism_and_seed_stability(stage_c_dir: Path) -> None:
    cases_run1 = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)
    cases_run2 = sample_pilot_cases(stage_c_dir, seed=PILOT_SEED)

    assert len(cases_run1) == len(cases_run2) == 24
    for c1, c2 in zip(cases_run1, cases_run2):
        assert c1.case_id == c2.case_id
        assert c1.immutable_security_id == c2.immutable_security_id
        assert c1.as_of_date == c2.as_of_date
        assert c1.ticker_at_decision == c2.ticker_at_decision
        assert c1.sample_stratum == c2.sample_stratum


def test_pilot_sampling_different_seed_yields_different_sample(stage_c_dir: Path) -> None:
    cases_seed1 = sample_pilot_cases(stage_c_dir, seed=20261003)
    cases_seed2 = sample_pilot_cases(stage_c_dir, seed=99999999)

    keys1 = [c.to_observation_key() for c in cases_seed1]
    keys2 = [c.to_observation_key() for c in cases_seed2]
    assert keys1 != keys2, "Different seed must produce different sample"
