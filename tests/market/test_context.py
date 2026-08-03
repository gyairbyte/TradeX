"""Tests for point-in-time market context calculation and eligibility."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from tradex.market.context import compute_short_term_context, is_context_eligible
from tradex.market.models import ShortContextPolicy, ShortTermMarketContext


def _trending_df(n: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range(start=datetime(2020, 1, 1, tzinfo=UTC), periods=n)
    opens = 100.0 + np.arange(n) * 0.5
    closes = opens + 0.2
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + 0.1,
            "low": np.minimum(opens, closes) - 0.1,
            "close": closes,
            "volume": np.full(n, 1_000_000, dtype=int),
        },
        index=dates,
    )


def test_context_computes_bullish_regime_and_rs() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    sector = _trending_df(80)
    as_of = target.index[-1].to_pydatetime()
    ctx = compute_short_term_context(
        as_of=as_of,
        ticker_df=target,
        market_proxy="SPY",
        market_df=market,
        sector_proxy="XLK",
        sector_df=sector,
    )
    assert ctx.market_regime_bullish is True
    assert ctx.sector_regime_bullish is True
    assert ctx.market_context_time is not None


def test_context_rejects_naive_as_of() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    naive = datetime(2020, 4, 1)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_short_term_context(
            as_of=naive,
            ticker_df=target,
            market_proxy="SPY",
            market_df=market,
        )


def test_context_is_point_in_time_no_future_bars() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    as_of = target.index[50].to_pydatetime()
    ctx = compute_short_term_context(
        as_of=as_of,
        ticker_df=target,
        market_proxy="SPY",
        market_df=market,
    )
    assert ctx.market_context_time == as_of
    assert ctx.as_of == as_of


def test_is_context_eligible_off_always() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    as_of = target.index[-1].to_pydatetime()
    ctx = compute_short_term_context(as_of, target, "SPY", market)
    eligible, status, _ = is_context_eligible(ctx, ShortContextPolicy.OFF)
    assert eligible is True
    assert status == "off"


def test_is_context_eligible_market_rs_when_bullish() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    as_of = target.index[-1].to_pydatetime()
    ctx = compute_short_term_context(as_of, target, "SPY", market)
    eligible, status, reasons = is_context_eligible(ctx, ShortContextPolicy.MARKET_RS)
    assert status in ("eligible", "unavailable", "filtered")
    if eligible:
        assert not reasons
    else:
        assert reasons


def test_is_context_eligible_market_sector_rs_missing_sector() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    as_of = target.index[-1].to_pydatetime()
    ctx = compute_short_term_context(as_of, target, "SPY", market)
    eligible, status, _ = is_context_eligible(ctx, ShortContextPolicy.MARKET_SECTOR_RS)
    assert eligible is False
    assert status == "unavailable"


def test_context_incomplete_when_sector_proxy_configured_but_missing() -> None:
    """A configured sector proxy without sector data must make context incomplete."""
    target = _trending_df(80)
    market = _trending_df(80)
    as_of = target.index[-1].to_pydatetime()
    ctx = compute_short_term_context(
        as_of=as_of,
        ticker_df=target,
        market_proxy="SPY",
        market_df=market,
        sector_proxy="XLK",
        sector_df=None,
    )
    assert ctx.context_complete is False
    assert "sector_regime" in ctx.missing_contexts
    assert "sector_relative_strength" in ctx.missing_contexts
    assert ctx.errors.get("sector_regime") == "sector data not provided"


def test_market_sector_rs_does_not_require_positive_market_rs() -> None:
    """market_sector_rs requires market regime + sector regime + sector RS only."""
    ctx = ShortTermMarketContext(
        as_of=datetime(2020, 1, 1, tzinfo=UTC),
        market_proxy="SPY",
        sector_proxy="XLK",
        market_regime_available=True,
        market_regime_bullish=True,
        sector_regime_available=True,
        sector_regime_bullish=True,
        market_relative_strength_available=True,
        market_relative_strength_positive=False,
        sector_relative_strength_available=True,
        sector_relative_strength_positive=True,
        market_close=100.0,
        market_ema20=95.0,
        market_ema50=90.0,
        market_ema20_slope_5=1.0,
        sector_close=50.0,
        sector_ema20=48.0,
        sector_ema50=45.0,
        sector_ema20_slope_5=0.5,
        market_rs_ratio=1.0,
        market_rs_ema20=1.1,
        market_rs_change_20_pct=-0.05,
        sector_rs_ratio=1.0,
        sector_rs_ema20=0.95,
        sector_rs_change_20_pct=0.05,
    )
    market_eligible, market_status, _ = is_context_eligible(ctx, ShortContextPolicy.MARKET_RS)
    sector_eligible, sector_status, _ = is_context_eligible(ctx, ShortContextPolicy.MARKET_SECTOR_RS)
    assert market_eligible is False
    assert market_status == "filtered"
    assert sector_eligible is True
    assert sector_status == "eligible"
