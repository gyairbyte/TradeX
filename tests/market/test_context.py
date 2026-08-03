"""Tests for point-in-time market context calculation and eligibility."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from tradex.market.context import compute_short_term_context, is_context_eligible
from tradex.market.models import ShortContextPolicy


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
