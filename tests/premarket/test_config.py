"""Tests for GapScanConfig validation."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tradex.premarket.config import GapScanConfig


def test_default_config():
    c = GapScanConfig()
    assert c.min_abs_gap_pct == 2.0
    assert c.min_price == 0.0
    assert c.min_premarket_volume == 0
    assert c.max_spread_bps is None
    assert c.require_spread is False
    assert c.liquidity_lookback_sessions == 20


def test_config_to_dict_round_trip():
    c = GapScanConfig(min_abs_gap_pct=5.0, require_catalyst=True)
    d = c.to_dict()
    assert d["min_abs_gap_pct"] == 5.0
    assert d["require_catalyst"] is True


def test_config_rejects_boolean_for_number():
    with pytest.raises(TypeError):
        GapScanConfig(min_abs_gap_pct=True)  # type: ignore[arg-type]


def test_config_rejects_numeric_string():
    with pytest.raises(TypeError):
        GapScanConfig(min_abs_gap_pct="2.0")  # type: ignore[arg-type]


def test_config_rejects_nan():
    with pytest.raises(ValueError):
        GapScanConfig(min_abs_gap_pct=float("nan"))


def test_config_rejects_infinite():
    with pytest.raises(ValueError):
        GapScanConfig(min_price=float("inf"))


def test_config_rejects_negative():
    with pytest.raises(ValueError):
        GapScanConfig(min_abs_gap_pct=-1.0)


def test_config_rejects_non_integer_volume():
    with pytest.raises(TypeError):
        GapScanConfig(min_premarket_volume=1.5)  # type: ignore[arg-type]


def test_config_rejects_non_positive_data_age():
    with pytest.raises(ValueError):
        GapScanConfig(max_data_age_minutes=0.0)
    with pytest.raises(ValueError):
        GapScanConfig(max_data_age_minutes=-5.0)


def test_config_rejects_non_positive_spread_limit():
    with pytest.raises(ValueError):
        GapScanConfig(max_spread_bps=0.0)
    with pytest.raises(ValueError):
        GapScanConfig(max_spread_bps=-1.0)


def test_config_rejects_non_positive_catalyst_lookback():
    with pytest.raises(ValueError):
        GapScanConfig(catalyst_lookback_hours=0.0)


def test_config_rejects_insufficient_liquidity_lookback():
    with pytest.raises(ValueError):
        GapScanConfig(liquidity_lookback_sessions=4)


def test_config_allows_valid_positive_optional_limits():
    c = GapScanConfig(max_data_age_minutes=30.0, max_spread_bps=50.0)
    assert c.max_data_age_minutes == 30.0
    assert c.max_spread_bps == 50.0


def test_config_is_frozen():
    c = GapScanConfig()
    with pytest.raises(FrozenInstanceError):
        c.min_abs_gap_pct = 3.0  # type: ignore[misc]
