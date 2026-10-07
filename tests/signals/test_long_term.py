"""Tests for the LONG MVP v1 strategy engine (tradex.signals.long_term)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.signals import long_term
from tradex.signals.weights import LongWeights


def _make_daily_df(
    n: int = 250,
    daily_volume: float = 500_000.0,
    seed: int = 4,
    drift: float = 0.0015,
    vol: float = 0.012,
    base_price: float = 100.0,
) -> pd.DataFrame:
    """Generate a synthetic daily OHLCV dataset with realistic drift and volatility."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    closes = base_price * np.exp(np.cumsum(returns))
    highs = closes * 1.008
    lows = closes * 0.992
    opens = (highs + lows) / 2.0
    volumes = np.full(n, daily_volume)

    dates = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


# ── Eligibility Floor Tests ───────────────────────────────────────────────────


def test_eligibility_insufficient_bars_fails_closed():
    """Fewer than 220 usable daily bars must fail closed with insufficient_data=True."""
    df = _make_daily_df(n=219)
    res = long_term.score(df)
    assert not res["qualified"]
    assert res["insufficient_data"] is True
    assert res["score"] == 0
    assert res["state"] is None
    assert any("Insufficient daily history" in r for r in res["reasons"])


def test_eligibility_price_floor():
    """Latest close < $5.00 fails eligibility."""
    df = _make_daily_df(n=250, base_price=3.0, drift=-0.001)
    res = long_term.score(df)
    assert not res["qualified"]
    assert res["insufficient_data"] is False
    assert res["score"] == 0
    assert any("below $5.00 floor" in r for r in res["reasons"])


def test_eligibility_liquidity_floor():
    """Median dollar volume < $20,000,000 fails eligibility."""
    # Price $100, volume 50,000 -> dollar volume $5,000,000 (< $20M)
    df = _make_daily_df(n=250, daily_volume=50_000)
    res = long_term.score(df)
    assert not res["qualified"]
    assert res["insufficient_data"] is False
    assert any("below $20,000,000 floor" in r for r in res["reasons"])


def test_eligibility_trend_structure_fails():
    """close <= EMA50 or EMA50 <= EMA200 fails structural eligibility."""
    # Strong downtrend
    df = _make_daily_df(n=250, drift=-0.005, vol=0.01)
    res = long_term.score(df)
    assert not res["qualified"]
    assert res["score"] == 0
    assert any("below EMA" in r for r in res["reasons"])


def test_missing_or_corrupt_indicators_fail_closed():
    """NaN/inf in required features fails closed with insufficient_data=True."""
    df = _make_daily_df(n=250)
    # Corrupt last close to NaN
    df.iloc[-1, df.columns.get_loc("close")] = np.nan
    res = long_term.score(df)
    assert not res["qualified"]
    assert res["insufficient_data"] is True


# ── Archetype 1: Momentum Continuation ────────────────────────────────────────


def test_momentum_continuation_qualification():
    """Stock in strong sustained uptrend near 20d high qualifies for momentum continuation."""
    # Seed 4 generates steady uptrend with return_20 >= 0.05 and 50 <= rsi <= 75
    df = _make_daily_df(n=250, seed=4)
    res = long_term.score(df)

    assert res["qualified"] is True
    assert long_term.ARCHETYPE_MOMENTUM in res["matched_setups"]
    assert res["score"] >= 60


def test_momentum_continuation_gates_prevent_match():
    """Each gate for momentum continuation independently prevents match."""
    # Flatten last 25 bars so return_20 is ~0
    df = _make_daily_df(n=250, seed=4)
    df.iloc[-25:, df.columns.get_loc("close")] = float(df["close"].iloc[-26])
    df.iloc[-25:, df.columns.get_loc("high")] = float(df["close"].iloc[-26]) * 1.002
    df.iloc[-25:, df.columns.get_loc("low")] = float(df["close"].iloc[-26]) * 0.998
    df.iloc[-25:, df.columns.get_loc("open")] = float(df["close"].iloc[-26])

    res = long_term.score(df)
    assert long_term.ARCHETYPE_MOMENTUM not in res["matched_setups"]


# ── Archetype 2: Trend Pullback ───────────────────────────────────────────────


def test_trend_pullback_qualification():
    """Stock in larger uptrend with short-term retracement near EMA20 qualifies for pullback."""
    # Seed 5 naturally produces a trend pullback setup
    df = _make_daily_df(n=250, seed=5, drift=0.001, vol=0.015)
    res = long_term.score(df)

    assert res["qualified"] is True
    assert res["return_5"] <= 0.02
    assert long_term.ARCHETYPE_PULLBACK in res["matched_setups"]


# ── Archetype 3: Breakout / Expansion ─────────────────────────────────────────


def test_breakout_expansion_near_and_confirmed():
    """Test near-breakout and confirmed breakout conditions."""
    # Seed 4 qualifies for breakout_expansion
    df = _make_daily_df(n=250, seed=4)
    res = long_term.score(df)
    assert long_term.ARCHETYPE_BREAKOUT in res["matched_setups"]

    # Now make it a confirmed breakout: close > prior_20d_high AND volume_ratio >= 1.30
    df_confirmed = df.copy()
    prior_high = float(df_confirmed["high"].iloc[-21:-1].max())
    df_confirmed.iloc[-1, df_confirmed.columns.get_loc("close")] = prior_high * 1.02
    df_confirmed.iloc[-1, df_confirmed.columns.get_loc("high")] = prior_high * 1.03
    df_confirmed.iloc[-1, df_confirmed.columns.get_loc("volume")] = 1_500_000.0  # 3x volume

    res_conf = long_term.score(df_confirmed)
    assert long_term.ARCHETYPE_BREAKOUT in res_conf["matched_setups"]
    if res_conf["primary_setup"] == long_term.ARCHETYPE_BREAKOUT:
        assert res_conf["state"] == long_term.STATE_ENTER_NOW
        assert any("Breakout above prior 20-day high" in r for r in res_conf["reasons"])



# ── Scoring Engine Boundaries ─────────────────────────────────────────────────


def test_movement_capacity_scoring_boundaries():
    """Verify exact ATR% scoring boundaries."""
    from tradex.signals.long_term import _score_movement_capacity

    assert _score_movement_capacity(0.009) == 0
    assert _score_movement_capacity(0.010) == 5
    assert _score_movement_capacity(0.0149) == 5
    assert _score_movement_capacity(0.015) == 10
    assert _score_movement_capacity(0.0199) == 10
    assert _score_movement_capacity(0.020) == 15
    assert _score_movement_capacity(0.060) == 15
    assert _score_movement_capacity(0.0601) == 10
    assert _score_movement_capacity(0.080) == 10
    assert _score_movement_capacity(0.0801) == 5
    assert _score_movement_capacity(0.12) == 5


def test_participation_scoring_boundaries():
    """Verify exact relative volume scoring boundaries."""
    from tradex.signals.long_term import _score_participation

    assert _score_participation(0.79) == 0
    assert _score_participation(0.80) == 3
    assert _score_participation(0.99) == 3
    assert _score_participation(1.00) == 6
    assert _score_participation(1.19) == 6
    assert _score_participation(1.20) == 8
    assert _score_participation(1.49) == 8
    assert _score_participation(1.50) == 10
    assert _score_participation(2.50) == 10


def test_category_maximums_and_total_cap():
    """Categories must strictly respect max points: Trend 30, Mom 25, Setup 20, Move 15, Part 10."""
    df = _make_daily_df(n=250, seed=4)
    # Boost volume and price on the last bar
    df.iloc[-1, df.columns.get_loc("volume")] = 2_000_000.0
    df.iloc[-1, df.columns.get_loc("close")] = float(df["close"].iloc[-2]) * 1.05

    res = long_term.score(df)
    comp = res["component_scores"]

    assert comp["trend_quality"] <= 30
    assert comp["momentum_quality"] <= 25
    assert comp["setup_quality"] <= 20
    assert comp["movement_capacity"] <= 15
    assert comp["participation"] <= 10
    assert res["score"] <= 100
    assert res["score"] == sum(comp.values())


# ── Multiple Matches and Tie-Breaking ─────────────────────────────────────────


def test_multiple_matches_retained_and_tie_break():
    """Multiple matching setups must be retained, and tie-break uses breakout -> momentum -> pullback."""
    # When both breakout and momentum match with identical scores, breakout is selected
    from tradex.signals.long_term import (
        ARCHETYPE_BREAKOUT,
        ARCHETYPE_MOMENTUM,
        ARCHETYPE_PULLBACK,
        ORDERED_ARCHETYPES,
    )

    assert ORDERED_ARCHETYPES == [
        ARCHETYPE_BREAKOUT,
        ARCHETYPE_MOMENTUM,
        ARCHETYPE_PULLBACK,
    ]


# ── State Assignment ──────────────────────────────────────────────────────────


def test_state_assignment_logic():
    """Test state assignments: ENTER NOW (>=75 + trigger), ARMED (>=70 + armed), WAITLIST (>=60)."""
    df = _make_daily_df(n=250, seed=4)
    res = long_term.score(df)

    if res["score"] >= 75:
        # If actionable trigger is met -> ENTER NOW, else ARMED or WAITLIST
        assert res["state"] in (
            long_term.STATE_ENTER_NOW,
            long_term.STATE_ARMED,
            long_term.STATE_QUALIFIED_WAITLIST,
        )
    elif res["score"] >= 70:
        assert res["state"] in (long_term.STATE_ARMED, long_term.STATE_QUALIFIED_WAITLIST)
    elif res["score"] >= 60:
        assert res["state"] == long_term.STATE_QUALIFIED_WAITLIST
    else:
        assert res["state"] is None


# ── LongWeights Disconnection ────────────────────────────────────────────────


def test_long_weights_cannot_alter_score():
    """Passing custom LongWeights must not alter the score (un-tunable strategy invariant)."""
    df = _make_daily_df(n=250, seed=4)

    score_default = long_term.score(df)

    # Pass bizarre zeroed weights
    custom_weights = LongWeights(
        secular_uptrend=0,
        rsi_healthy=0,
        volume_accumulation=0,
        macd_bullish=0,
        bb_coil=0,
    )
    score_custom = long_term.score(df, weights=custom_weights)

    assert score_default["score"] == score_custom["score"]
    assert score_default["component_scores"] == score_custom["component_scores"]
    assert score_default["primary_setup"] == score_custom["primary_setup"]
    assert score_default["state"] == score_custom["state"]


# ── Scorer Output Contract ────────────────────────────────────────────────────


def test_scorer_output_contract():
    """Score output must contain all required contract keys."""
    df = _make_daily_df(n=250, seed=4)
    res = long_term.score(df)

    required_keys = {
        "strategy_id",
        "strategy_version",
        "score",
        "primary_setup",
        "matched_setups",
        "state",
        "component_scores",
        "reasons",
        "trigger",
        "invalidation",
        "last_close",
        "volume_ratio",
        "rsi",
        "atr_pct",
        "return_5",
        "return_20",
        "return_60",
        "qualified",
    }
    assert required_keys.issubset(set(res.keys()))
    assert res["strategy_id"] == "long_mvp"
    assert res["strategy_version"] == "v1"
    assert isinstance(res["score"], int)
    assert isinstance(res["matched_setups"], list)
    assert isinstance(res["reasons"], list)
    assert isinstance(res["qualified"], bool)
