"""Tests for immutable security ID resolution, ticker rename/reuse, and eligibility gates."""
from __future__ import annotations

import pandas as pd

from tradex.research.long_002c.dataset import (
    build_decision_observations_for_security,
    compute_atr,
)
from tradex.research.long_002c.identity import (
    SecurityIdentity,
    SecurityMaster,
    make_immutable_id,
)


def test_immutable_id_generation() -> None:
    """Verify stable, canonical ID generation and fail-closed symbol-only rejection."""
    import pytest

    id1 = make_immutable_id("AAPL", cik="0000320193", composite_figi="BBG000B9XRY4")
    assert id1 == "FIGI_BBG000B9XRY4"

    id2 = make_immutable_id("AAPL", cik="0000320193")
    assert id2 == "CIK_0000320193_CS"

    # Symbol-only identity cannot qualify for official canonical identity
    with pytest.raises(ValueError, match="Symbol-only identity"):
        make_immutable_id("XYZ")

    # Only allowed when explicitly flagged as unverified
    id3 = make_immutable_id("XYZ", allow_unverified=True)
    assert id3 == "US_EQ_XYZ_CS"


def test_ticker_rename_continuity() -> None:
    """Security history remains contiguous across ticker changes through immutable ID."""
    master = SecurityMaster()
    sec_id = "CIK_0001326801_CS"  # Meta Platforms

    # Before rename: FB
    fb_identity = SecurityIdentity(
        immutable_security_id=sec_id,
        ticker_at_decision="FB",
        effective_start="2012-05-18",
        effective_end="2022-06-08",
        cik="0001326801",
    )
    # After rename: META
    meta_identity = SecurityIdentity(
        immutable_security_id=sec_id,
        ticker_at_decision="META",
        effective_start="2022-06-09",
        effective_end="2030-12-31",
        cik="0001326801",
    )
    master.register_security(fb_identity)
    master.register_security(meta_identity)

    # Resolution in 2018 returns FB
    res_2018 = master.resolve("FB", "2018-05-01")
    assert res_2018 is not None
    assert res_2018.immutable_security_id == sec_id
    assert res_2018.ticker_at_decision == "FB"

    # Both periods link to the same immutable security ID
    res_2022 = master.resolve("META", "2022-07-01")
    assert res_2022 is not None
    assert res_2022.immutable_security_id == sec_id
    assert res_2022.ticker_at_decision == "META"


def test_ticker_reuse_isolation() -> None:
    """Distinct entities reusing the same ticker symbol have distinct immutable IDs."""
    master = SecurityMaster()
    # Company A used ticker 'SYM' from 2010 to 2015
    comp_a = SecurityIdentity(
        immutable_security_id="CIK_0000000111_CS",
        ticker_at_decision="SYM",
        effective_start="2010-01-01",
        effective_end="2015-12-31",
        cik="0000000111",
    )
    # Company B took ticker 'SYM' in 2018
    comp_b = SecurityIdentity(
        immutable_security_id="CIK_0000000222_CS",
        ticker_at_decision="SYM",
        effective_start="2018-01-01",
        effective_end="2025-12-31",
        cik="0000000222",
    )
    master.register_security(comp_a)
    master.register_security(comp_b)

    res_a = master.resolve("SYM", "2014-06-01")
    assert res_a is not None
    assert res_a.immutable_security_id == "CIK_0000000111_CS"

    res_b = master.resolve("SYM", "2019-06-01")
    assert res_b is not None
    assert res_b.immutable_security_id == "CIK_0000000222_CS"

    # Gap period fails closed (None)
    assert master.resolve("SYM", "2016-06-01") is None


def test_unknown_security_identity_fails_closed() -> None:
    """Unregistered security fails closed to None."""
    master = SecurityMaster()
    assert master.resolve("UNKNOWN_XYZ", "2018-01-01") is None


def test_wilders_atr_calculation() -> None:
    """Verify Wilder's ATR formula."""
    # 20 bars of high/low/close with constant 2.0 range
    highs = [10.0 + (i * 0.1) + 1.0 for i in range(25)]
    lows = [10.0 + (i * 0.1) - 1.0 for i in range(25)]
    closes = [10.0 + (i * 0.1) for i in range(25)]

    atr = compute_atr(highs, lows, closes, period=14)
    assert atr is not None
    assert round(atr, 1) == 2.0


def test_null_is_not_zero_in_features() -> None:
    """Insufficient lookback produces None/null, never 0.0."""
    identity = SecurityIdentity(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        effective_start="2016-01-01",
        effective_end="2016-01-10",
        security_type="common_stock",
    )
    # Only 5 bars of data
    dates = ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07", "2016-01-08"]
    df = pd.DataFrame(
        {
            "open": [10.0] * 5,
            "high": [11.0] * 5,
            "low": [9.0] * 5,
            "close": [10.0] * 5,
            "volume": [1000000] * 5,
            "as_traded_close": [10.0] * 5,
        },
        index=dates,
    )
    obs, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-10",
    )
    assert len(obs) > 0
    # 20-day dollar volume median must be None, NOT 0.0
    assert obs[0].dollar_volume_20d_median is None
    assert obs[0].atr_14 is None
    assert obs[0].data_complete is False
    assert elig[0].cohort_type == "insufficient_history"
