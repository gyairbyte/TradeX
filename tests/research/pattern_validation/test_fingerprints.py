"""Tests for development-only fingerprint construction."""
from __future__ import annotations

from datetime import date

import pytest

from tradex.research.pattern_validation.fingerprints import build_development_fingerprints
from tradex.research.pattern_validation.models import Split, StudySpec, ValidationError


def test_fingerprints_use_development_split_only(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    assert "runup" in fingerprints
    assert "decline" in fingerprints
    for fp in fingerprints.values():
        assert fp.source == "synthetic"
        assert fp.profile == "standard"
        assert fp.n_events >= tiny_spec.min_events


def test_fingerprints_are_immutable_and_hashed(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    fp = fingerprints["runup"]
    assert fp.fingerprint_sha256
    assert len(fp.series) == len(tiny_spec.series_weights)
    assert "mean" in fp.series["price_pct"]
    assert "std" in fp.series["price_pct"]
    assert "upper" in fp.series["price_pct"]
    assert "lower" in fp.series["price_pct"]


def test_fingerprint_config_hash_matches_spec(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    assert fingerprints["runup"].config_hash == fingerprints["decline"].config_hash
    assert fingerprints["runup"].lookback_days == tiny_spec.lookback_days


def test_fingerprints_fail_without_enough_events(tiny_bars):
    spec = StudySpec(
        tickers=("AAPL", "MSFT"),
        provider="synthetic",
        start_date=date(2020, 1, 2),
        end_date=date(2020, 12, 31),
        splits={"development": Split(date(2020, 1, 2), date(2020, 1, 31))},
        min_events=5,
    )
    with pytest.raises(ValidationError):
        build_development_fingerprints(tiny_bars, spec)
