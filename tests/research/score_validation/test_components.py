"""Production short-term scorer compatibility for the validation study."""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.signals.short_term import score
from tradex.signals.weights import ShortWeights


def _qualifying_bars() -> pd.DataFrame:
    n = 120
    t = np.arange(n)
    close = 100 + 0.2 * t + 0.5 * np.sin(t / 3)
    close[-10:] += np.linspace(0, 1.5, 10)
    vol = np.ones(n) * 1e6
    vol[-5:] = 3e6
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": vol,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
    )


def test_score_returns_existing_keys():
    df = _qualifying_bars()
    result = score(df)
    assert "score" in result
    assert "reasons" in result
    assert "last_close" in result
    assert "volume_ratio" in result
    assert "rsi" in result
    assert 0 <= result["score"] <= 100
    assert isinstance(result["reasons"], list)


def test_score_and_reasons_unchanged_by_component_refactor():
    """The refactored scorer must produce identical scores and reasons."""
    df = _qualifying_bars()
    result = score(df)

    # Hand-verify the same conditions the original function used.
    from tradex.signals.indicators import add_indicators

    last = add_indicators(df).iloc[-1]
    expected_reasons = []
    if last["close"] > last["ema_20"] > last["ema_50"]:
        expected_reasons.append("Price above EMA20 > EMA50 — bullish structure")
    if last["volume_ratio"] >= 1.3:
        expected_reasons.append(f"Volume confirming move ({last['volume_ratio']:.1f}x avg)")
    if 50 <= last["rsi"] <= 70:
        expected_reasons.append(f"RSI in momentum zone ({last['rsi']:.0f})")
    if last["macd"] > 0 and last["macd_diff"] > 0:
        expected_reasons.append("MACD positive and expanding")
    ema_proximity = abs(last["close"] - last["ema_20"]) / last["ema_20"]
    if ema_proximity < 0.015 and last["ema_20"] > last["ema_50"]:
        expected_reasons.append("Pullback to EMA20 in uptrend — entry opportunity")

    weights = ShortWeights()
    total = 0
    for reason in expected_reasons:
        if "EMA20 > EMA50" in reason:
            total += weights.ema_structure
        if "Volume confirming" in reason:
            total += weights.volume_confirmation
        if "RSI in momentum" in reason:
            total += weights.rsi_momentum
        if "MACD positive" in reason:
            total += weights.macd_positive
        if "Pullback to EMA20" in reason:
            total += weights.pullback_ema
    expected_score = min(total, 100)
    assert result["score"] == expected_score
    assert result["reasons"] == expected_reasons


def test_component_flags_match_score():
    result = score(_qualifying_bars())
    components = result["components"]
    points = result["component_points"]
    assert set(components) == {
        "ema_structure",
        "volume_confirmation",
        "rsi_momentum",
        "macd_positive",
        "pullback_ema",
    }
    assert all(isinstance(v, bool) for v in components.values())
    assert all(isinstance(v, (int, float)) for v in points.values())
    assert sum(points.values()) == result["score"] or sum(points.values()) > 100


def test_explicit_custom_weights_work():
    weights = ShortWeights(
        ema_structure=10,
        volume_confirmation=10,
        rsi_momentum=10,
        macd_positive=10,
        pullback_ema=10,
    )
    result = score(_qualifying_bars(), weights=weights)
    assert result["score"] <= 50
    assert result["component_points"]["ema_structure"] == 10


def test_default_production_uses_saved_weights(monkeypatch, tmp_path):
    from tradex.signals import weights as weights_module

    weights_path = tmp_path / "weights.json"
    monkeypatch.setattr(weights_module, "WEIGHTS_PATH", weights_path)

    custom = ShortWeights(
        ema_structure=100,
        volume_confirmation=0,
        rsi_momentum=0,
        macd_positive=0,
        pullback_ema=0,
    )
    saved = weights_module.Weights.defaults()
    saved.short = custom
    weights_module.save(saved)

    result = score(_qualifying_bars())
    if result["components"]["ema_structure"]:
        assert result["score"] == 100

    weights_module.reset_to_defaults()
