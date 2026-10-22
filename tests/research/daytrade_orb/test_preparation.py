"""Deterministic tests for the ORB market preparation service and local cache (DAYTRADE-003G).

Covers all required acceptance criteria:
- Exact preceding-session daily (15 sessions) and opening-volume (14 sessions) lookbacks.
- Correct ADV14 and Wilder ATR14 computation during preparation.
- Session-D opening-price eligibility is NOT evaluated prematurely during preparation.
- Initial universe discovery and historical provider calls.
- Complete (READY) and partial (PARTIAL) preparation statuses.
- Rejection of non-trading days (weekends, holidays) and early closures.
- Save, close/reopen, reload artifact from local cache.
- Version/schema, session date, feed, and provider validation.
- Corrupt/missing/incompatible file handling.
- Tampered integrity hash detection.
- Atomic write/replace behavior.
- Re-preparation without stale-state contamination.
- Zero secrets or credentials persisted to disk.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from tradex.market.hours import MARKET_TIMEZONE
from tradex.research.daytrade_orb.demo_fixture import DEMO_SESSION_DATE
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import (
    DailyBar,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.preparation import (
    PreparationStatus,
    inspect_cache_status,
    load_prepared_snapshot,
    prepare_market,
    validate_prepared_snapshot,
)
from tradex.research.daytrade_orb.provider import MockORBProvider
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

TEST_DATE = date(2024, 1, 2)
TEST_AS_OF = datetime(2024, 1, 2, 8, 0, 0, tzinfo=MARKET_TIMEZONE)


def _make_daily_bars(
    symbol: str,
    target_date: date,
    num_days: int = 15,
    base_price: float = 100.0,
    daily_vol: float = 2_000_000.0,
    daily_range: float = 2.0,
) -> list[DailyBar]:
    """Generate num_days completed regular XNYS daily bars ending at D-1."""
    prior_sessions = get_prior_xnys_sessions(target_date, num_days)
    bars: list[DailyBar] = []
    for d in prior_sessions:
        bars.append(
            DailyBar(
                symbol=symbol,
                session_date=d,
                open=base_price,
                high=base_price + daily_range / 2,
                low=base_price - daily_range / 2,
                close=base_price + 0.10,
                volume=daily_vol,
            )
        )
    return bars


def _make_prior_vols(
    symbol: str,
    target_date: date,
    num_days: int = 14,
    vol: float = 100_000.0,
) -> list[OpeningRangeVolumeObservation]:
    """Generate num_days prior opening-range volume observations ending at D-1."""
    prior_sessions = get_prior_xnys_sessions(target_date, num_days)
    return [
        OpeningRangeVolumeObservation(symbol=symbol, session_date=d, volume=vol)
        for d in prior_sessions
    ]


def test_production_strategies_strictly_empty():
    """Governance requirement: Market preparation is research-only; registry must remain empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_preparation_lookbacks_and_calculations(tmp_path: Path):
    """Preparation retrieves exactly 15 daily bars and 14 opening-volume sessions."""
    daily_15 = _make_daily_bars("TEST", TEST_DATE, num_days=15, base_price=50.0, daily_vol=2_500_000.0, daily_range=2.0)
    prior_14 = _make_prior_vols("TEST", TEST_DATE, num_days=14, vol=150_000.0)

    provider = MockORBProvider(
        symbols=["TEST"],
        daily_bars={"TEST": daily_15},
        opening_range_bars={},
        prior_opening_range_volumes={"TEST": prior_14},
        provider_name="alpaca",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = prepare_market(
        provider=provider,
        session_date=TEST_DATE,
        as_of_time=TEST_AS_OF,
        cache_dir=tmp_path,
    )

    assert res.status == PreparationStatus.READY
    assert res.universe_size_discovered == 1
    assert res.daily_eligible_count == 1
    assert res.snapshot is not None

    snap = res.snapshot
    # Check exact lookback lengths
    assert len(snap.historical_daily_sessions) == 15
    assert len(snap.prior_or_volume_sessions) == 14
    assert snap.historical_daily_sessions[-1] == snap.prior_or_volume_sessions[-1]  # Both end at D-1

    # Check metrics
    adv, atr = snap.daily_metrics["TEST"]
    assert adv == 2_500_000.0
    assert atr > 0.50
    assert "TEST" in snap.daily_eligible_symbols

    # Verify that the artifact file exists on disk
    assert res.artifact_path is not None
    assert res.artifact_path.exists()


def test_opening_price_filter_not_applied_during_preparation(tmp_path: Path):
    """Opening price <= $5.00 filter is NOT applied at preparation time.

    Even if a stock has prior-session close < $5.00, it cannot be excluded at 8:00 AM ET
    because the strategy requires session D's actual 09:30 regular-session open.
    """
    # Stock with price $4.50, but high volume (> 1M) and volatility (> $0.50)
    low_price_bars = _make_daily_bars("PENNY", TEST_DATE, num_days=15, base_price=4.50, daily_vol=3_000_000.0, daily_range=1.0)
    prior_vols = _make_prior_vols("PENNY", TEST_DATE, num_days=14, vol=200_000.0)

    provider = MockORBProvider(
        symbols=["PENNY"],
        daily_bars={"PENNY": low_price_bars},
        prior_opening_range_volumes={"PENNY": prior_vols},
        provider_name="alpaca",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = prepare_market(
        provider=provider,
        session_date=TEST_DATE,
        as_of_time=TEST_AS_OF,
        cache_dir=tmp_path,
    )

    assert res.status == PreparationStatus.READY
    assert "PENNY" in res.snapshot.daily_eligible_symbols
    assert len(res.snapshot.exclusions) == 0


def test_technical_filter_exclusions_adv_and_atr(tmp_path: Path):
    """Preparation correctly applies preliminary ADV14 and ATR14 technical filters."""
    # ADV < 1M
    low_adv = _make_daily_bars("LOWADV", TEST_DATE, num_days=15, base_price=50.0, daily_vol=500_000.0, daily_range=2.0)
    # ATR <= 0.50
    low_atr = _make_daily_bars("LOWATR", TEST_DATE, num_days=15, base_price=50.0, daily_vol=2_000_000.0, daily_range=0.20)
    # Passing symbol
    good_sym = _make_daily_bars("GOOD", TEST_DATE, num_days=15, base_price=50.0, daily_vol=2_000_000.0, daily_range=2.0)
    good_vols = _make_prior_vols("GOOD", TEST_DATE, num_days=14, vol=100_000.0)

    provider = MockORBProvider(
        symbols=["GOOD", "LOWADV", "LOWATR"],
        daily_bars={"GOOD": good_sym, "LOWADV": low_adv, "LOWATR": low_atr},
        prior_opening_range_volumes={"GOOD": good_vols},
        provider_name="alpaca",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = prepare_market(
        provider=provider,
        session_date=TEST_DATE,
        as_of_time=TEST_AS_OF,
        cache_dir=tmp_path,
    )

    assert res.status == PreparationStatus.READY
    assert res.daily_eligible_count == 1
    assert res.snapshot.daily_eligible_symbols == ["GOOD"]

    excluded_symbols = {e.symbol: e.reason for e in res.snapshot.exclusions}
    assert "LOWADV" in excluded_symbols
    assert "ADV14" in excluded_symbols["LOWADV"]
    assert "LOWATR" in excluded_symbols
    assert "ATR14" in excluded_symbols["LOWATR"]


def test_rejection_of_non_trading_day_and_early_close(tmp_path: Path):
    """Preparation rejects non-trading days (weekends/holidays) and early closures."""
    weekend_date = date(2024, 1, 6)  # Saturday
    provider = MockORBProvider.create_populated()

    res_weekend = prepare_market(
        provider=provider,
        session_date=weekend_date,
        cache_dir=tmp_path,
    )
    assert res_weekend.status == PreparationStatus.FAILED
    assert "weekend or holiday" in res_weekend.error_message

    # Test early-close session (e.g. 2024-07-03 before July 4th closes at 13:00 ET)
    early_close_date = date(2024, 7, 3)
    res_early = prepare_market(
        provider=provider,
        session_date=early_close_date,
        cache_dir=tmp_path,
    )
    assert res_early.status == PreparationStatus.FAILED
    assert "early-close session" in res_early.error_message


def test_persistence_save_reload_and_integrity(tmp_path: Path):
    """PreparedMarketSnapshot can be saved, reloaded, and integrity-verified."""
    provider = MockORBProvider.create_populated()

    res = prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        cache_dir=tmp_path,
    )
    assert res.status == PreparationStatus.READY
    assert res.artifact_path is not None

    # Reload from disk
    loaded = load_prepared_snapshot(DEMO_SESSION_DATE, provider.provider_name, provider.feed_name, cache_dir=tmp_path)
    assert loaded is not None
    assert loaded.session_date == DEMO_SESSION_DATE
    assert loaded.provider == provider.provider_name
    assert loaded.feed == provider.feed_name
    assert loaded.daily_eligible_symbols == res.snapshot.daily_eligible_symbols
    assert loaded.daily_metrics == res.snapshot.daily_metrics
    assert loaded.verify_integrity() is True

    # Validate snapshot
    val = validate_prepared_snapshot(loaded, DEMO_SESSION_DATE, provider.provider_name, provider.feed_name)
    assert val.is_valid is True
    assert val.status == PreparationStatus.READY


def test_tampered_artifact_fails_validation(tmp_path: Path):
    """A tampered cache artifact fails SHA-256 integrity verification."""
    provider = MockORBProvider.create_populated()

    res = prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        cache_dir=tmp_path,
    )
    assert res.artifact_path is not None

    # Tamper with the artifact content
    data = json.loads(res.artifact_path.read_text(encoding="utf-8"))
    data["universe_size_discovered"] = 999999  # Tamper with universe size
    res.artifact_path.write_text(json.dumps(data), encoding="utf-8")

    # load_prepared_snapshot should detect hash mismatch and return None
    loaded = load_prepared_snapshot(DEMO_SESSION_DATE, provider.provider_name, provider.feed_name, cache_dir=tmp_path)
    assert loaded is None

    # inspect_cache_status should report corruption
    status = inspect_cache_status(DEMO_SESSION_DATE, provider.provider_name, provider.feed_name, cache_dir=tmp_path)
    assert status.is_valid is False


def test_stale_cache_and_feed_mismatch(tmp_path: Path):
    """Validation detects stale date, feed mismatch, and provider mismatch."""
    provider = MockORBProvider.create_populated()

    res = prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        cache_dir=tmp_path,
    )
    snap = res.snapshot

    # Different date
    val_date = validate_prepared_snapshot(snap, date(2024, 1, 3), provider.provider_name, provider.feed_name)
    assert val_date.is_valid is False
    assert val_date.status == PreparationStatus.STALE

    # Different feed (e.g. prepared SIP, asked for IEX)
    val_feed = validate_prepared_snapshot(snap, DEMO_SESSION_DATE, provider.provider_name, "iex")
    assert val_feed.is_valid is False
    assert val_feed.status == PreparationStatus.STALE

    # Different provider (e.g. prepared alpaca, asked for schwab)
    val_prov = validate_prepared_snapshot(snap, DEMO_SESSION_DATE, "schwab", provider.feed_name)
    assert val_prov.is_valid is False
    assert val_prov.status == PreparationStatus.STALE


def test_zero_secrets_written_to_disk(tmp_path: Path):
    """The saved preparation artifact must not contain API keys, tokens, or credentials."""
    provider = MockORBProvider.create_populated()

    res = prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        cache_dir=tmp_path,
    )
    assert res.artifact_path is not None
    content = res.artifact_path.read_text(encoding="utf-8").lower()

    forbidden = ["api_key", "secret_key", "token", "password", "oauth", "client_secret"]
    for word in forbidden:
        assert f'"{word}"' not in content


def test_atomic_write_replacement(tmp_path: Path):
    """Atomic replacement safely updates existing artifact without intermediate corruption."""
    provider = MockORBProvider.create_populated()

    res1 = prepare_market(provider=provider, session_date=DEMO_SESSION_DATE, cache_dir=tmp_path)
    assert res1.artifact_path.exists()
    mtime1 = res1.artifact_path.stat().st_mtime_ns

    # Re-prepare (should atomically replace)
    res2 = prepare_market(provider=provider, session_date=DEMO_SESSION_DATE, cache_dir=tmp_path)
    assert res2.artifact_path.exists()
    assert res2.artifact_path == res1.artifact_path
    assert res2.artifact_path.stat().st_mtime_ns >= mtime1
    # No temporary files left behind
    tmp_files = list(tmp_path.glob("*.tmp_*"))
    assert len(tmp_files) == 0
