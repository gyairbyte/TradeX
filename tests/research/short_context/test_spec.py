"""Tests for context-study spec loading and validation."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tradex.market.models import ShortContextPolicy
from tradex.research.short_context.models import ValidationError
from tradex.research.short_context.spec import load_spec


def test_valid_spec_round_trip(tmp_path: Path) -> None:
    data = {
        "schema_version": 1,
        "study_name": "test",
        "target_tickers": ["AAPL", "MSFT"],
        "default_market_proxy": "SPY",
        "ticker_context": {
            "AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"},
            "MSFT": {"market_proxy": "SPY", "sector_proxy": None},
        },
        "candidate_policies": ["market_rs"],
        "primary_horizon_bars": 3,
        "primary_slippage_bps": 5.0,
        "horizons": [1, 3, 5],
        "slippage_scenarios_bps": [0.0, 5.0, 10.0],
        "commission_bps": 0.0,
        "minimum_holdout_events": 10,
        "minimum_holdout_tickers": 2,
        "minimum_event_retention_pct": 25.0,
        "minimum_ticker_coverage_pct": 50.0,
        "baseline_score_threshold": 40,
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    spec, raw = load_spec(path)
    assert spec.study_name == "test"
    assert spec.target_tickers == ("AAPL", "MSFT")
    assert spec.candidate_policies == (ShortContextPolicy.MARKET_RS,)
    assert raw is not None


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["extra_key"] = 1
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="unknown top-level keys"):
        load_spec(path)


def test_unknown_context_key_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["ticker_context"]["AAPL"]["bad_key"] = "x"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="unknown keys"):
        load_spec(path)


def test_target_cannot_be_own_proxy(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["ticker_context"]["AAPL"]["market_proxy"] = "AAPL"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="cannot be its own market_proxy"):
        load_spec(path)


def test_lowercase_ticker_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["target_tickers"] = ["aapl"]
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="uppercase"):
        load_spec(path)


def test_duplicate_policy_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["candidate_policies"] = ["market_rs", "market_rs"]
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="duplicate candidate policy"):
        load_spec(path)


def test_off_policy_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["candidate_policies"] = ["off"]
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="cannot be 'off'"):
        load_spec(path)


def test_boolean_value_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["minimum_holdout_events"] = True
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="must not be a boolean"):
        load_spec(path)


def test_nan_value_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["minimum_event_retention_pct"] = math.nan
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="finite"):
        load_spec(path)


def test_inf_value_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["minimum_ticker_coverage_pct"] = math.inf
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="finite"):
        load_spec(path)


def test_percentage_above_100_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["minimum_event_retention_pct"] = 101.0
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="<= 100"):
        load_spec(path)


def test_primary_horizon_not_in_horizons_rejected(tmp_path: Path) -> None:
    data = _minimal_spec()
    data["primary_horizon_bars"] = 7
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="primary_horizon_bars"):
        load_spec(path)


def _minimal_spec() -> dict:
    return {
        "schema_version": 1,
        "study_name": "test",
        "target_tickers": ["AAPL"],
        "default_market_proxy": "SPY",
        "ticker_context": {
            "AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"},
        },
        "candidate_policies": ["market_rs"],
        "primary_horizon_bars": 3,
        "primary_slippage_bps": 5.0,
        "horizons": [1, 3, 5],
        "slippage_scenarios_bps": [0.0, 5.0, 10.0],
        "commission_bps": 0.0,
        "minimum_holdout_events": 10,
        "minimum_holdout_tickers": 1,
        "minimum_event_retention_pct": 25.0,
        "minimum_ticker_coverage_pct": 50.0,
        "baseline_score_threshold": 40,
    }
