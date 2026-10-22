"""Deterministic tests for warmed vs cold market-wide ORB scanning (DAYTRADE-003G).

Verifies:
- Equivalence: Warm scan and cold scan yield identical candidates, ranks, order intents,
  breakout triggers, theoretical stop offsets, setup explanations, and exclusions on identical data.
- API call avoidance: Warm scan performs ZERO historical daily-bar and ZERO prior-14-session
  opening-volume provider calls. Cold scan performs >0 calls for both.
- Actual session D opening range (09:30-09:34 ET) is retrieved and evaluated in warm scan.
- Doji setups receive NO_ORDER and rank #21 is not backfilled in warm scan.
- Missing, corrupt, or incompatible cache safely falls back to cold scan with explicit notification.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from tradex.market.hours import MARKET_TIMEZONE
from tradex.research.daytrade_orb.demo_fixture import DEMO_AS_OF_TIME, DEMO_SESSION_DATE
from tradex.research.daytrade_orb.models import (
    DailyBar,
    Direction,
    MinuteBar,
    OpeningRangeVolumeObservation,
    OrderStatus,
)
from tradex.research.daytrade_orb.preparation import (
    PreparationStatus,
    prepare_market,
)
from tradex.research.daytrade_orb.provider import MockORBProvider
from tradex.research.daytrade_orb.scanner import run_market_scan


class CallCountingMockProvider(MockORBProvider):
    """Subclass of MockORBProvider that counts method invocations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.discover_universe_calls: int = 0
        self.fetch_daily_bars_calls: int = 0
        self.fetch_opening_range_bars_calls: int = 0
        self.fetch_prior_opening_range_volumes_calls: int = 0

    def discover_universe(self) -> list[str]:
        self.discover_universe_calls += 1
        return super().discover_universe()

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyBar]]:
        self.fetch_daily_bars_calls += 1
        return super().fetch_daily_bars(symbols, start_date, end_date)

    def fetch_opening_range_bars(
        self,
        symbols: list[str],
        session_date: date,
    ) -> dict[str, list[MinuteBar]]:
        self.fetch_opening_range_bars_calls += 1
        return super().fetch_opening_range_bars(symbols, session_date)

    def fetch_prior_opening_range_volumes(
        self,
        symbols: list[str],
        prior_sessions: list[date],
    ) -> dict[str, list[OpeningRangeVolumeObservation]]:
        self.fetch_prior_opening_range_volumes_calls += 1
        return super().fetch_prior_opening_range_volumes(symbols, prior_sessions)


def test_warm_scan_and_cold_scan_exact_equivalence(tmp_path: Path):
    """Warm scan and cold scan produce 100% identical strategy outcomes on identical inputs."""
    # Step 1: Run preparation to populate local cache
    prep_provider = CallCountingMockProvider.create_populated()
    prep_res = prepare_market(
        provider=prep_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        cache_dir=tmp_path,
    )
    assert prep_res.status == PreparationStatus.READY

    # Step 2: Run Cold Scan (use_cache=False)
    cold_provider = CallCountingMockProvider.create_populated()
    cold_result = run_market_scan(
        provider=cold_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=False,
    )
    assert cold_result.was_warmed is False
    assert cold_result.top_n_selected > 0

    # Step 3: Run Warm Scan (use_cache=True, loads prepared snapshot from tmp_path)
    warm_provider = CallCountingMockProvider.create_populated()
    warm_result = run_market_scan(
        provider=warm_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=True,
        cache_dir=tmp_path,
    )
    assert warm_result.was_warmed is True

    # Assert outcomes are strictly identical:
    assert len(warm_result.candidates) == len(cold_result.candidates)
    assert warm_result.top_n_selected == cold_result.top_n_selected
    assert warm_result.eligible_candidates_count == cold_result.eligible_candidates_count

    for w_row, c_row in zip(warm_result.candidates, cold_result.candidates, strict=True):
        assert w_row.rank == c_row.rank
        assert w_row.symbol == c_row.symbol
        assert w_row.direction == c_row.direction
        assert w_row.or_open == pytest.approx(c_row.or_open, abs=1e-4)
        assert w_row.or_high == pytest.approx(c_row.or_high, abs=1e-4)
        assert w_row.or_low == pytest.approx(c_row.or_low, abs=1e-4)
        assert w_row.or_close == pytest.approx(c_row.or_close, abs=1e-4)
        assert w_row.or_volume == pytest.approx(c_row.or_volume, abs=1e-4)
        assert w_row.adv14 == pytest.approx(c_row.adv14, abs=1e-4)
        assert w_row.atr14 == pytest.approx(c_row.atr14, abs=1e-4)
        assert w_row.rv14 == pytest.approx(c_row.rv14, abs=1e-4)
        if c_row.stop_entry_trigger is None:
            assert w_row.stop_entry_trigger is None
        else:
            assert w_row.stop_entry_trigger == pytest.approx(c_row.stop_entry_trigger, abs=1e-4)
        assert w_row.theoretical_stop_offset == pytest.approx(c_row.theoretical_stop_offset, abs=1e-4)
        assert w_row.order_intent_status == c_row.order_intent_status
        assert w_row.explanation == c_row.explanation

    # Exclusions must also match
    assert len(warm_result.exclusions) == len(cold_result.exclusions)
    w_ex = {(e.symbol, e.category, e.reason) for e in warm_result.exclusions}
    c_ex = {(e.symbol, e.category, e.reason) for e in cold_result.exclusions}
    assert w_ex == c_ex


def test_warm_scan_avoids_historical_api_calls(tmp_path: Path):
    """Acceptance requirement: A warmed scan makes ZERO historical daily-bar and prior-OR-volume calls."""
    # Prepare cache
    prep_provider = CallCountingMockProvider.create_populated()
    prepare_market(
        provider=prep_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        cache_dir=tmp_path,
    )

    # Cold scan request counts
    cold_provider = CallCountingMockProvider.create_populated()
    run_market_scan(
        provider=cold_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=False,
    )
    assert cold_provider.discover_universe_calls == 1
    assert cold_provider.fetch_daily_bars_calls == 1
    assert cold_provider.fetch_prior_opening_range_volumes_calls == 1
    assert cold_provider.fetch_opening_range_bars_calls == 1

    # Warm scan request counts
    warm_provider = CallCountingMockProvider.create_populated()
    res = run_market_scan(
        provider=warm_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=True,
        cache_dir=tmp_path,
    )
    assert res.was_warmed is True
    # Zero calls to discover_universe, fetch_daily_bars, fetch_prior_opening_range_volumes!
    assert warm_provider.discover_universe_calls == 0
    assert warm_provider.fetch_daily_bars_calls == 0
    assert warm_provider.fetch_prior_opening_range_volumes_calls == 0
    # Exactly 1 call to retrieve session D opening-range bars:
    assert warm_provider.fetch_opening_range_bars_calls == 1


def test_warm_scan_doji_and_no_backfill_behavior(tmp_path: Path):
    """Warm scan preserves locked Doji NO_ORDER and no-backfill rules."""
    prep_provider = MockORBProvider.create_populated()
    prepare_market(
        provider=prep_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        cache_dir=tmp_path,
    )

    warm_provider = MockORBProvider.create_populated()
    res = run_market_scan(
        provider=warm_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=True,
        cache_dir=tmp_path,
    )
    assert res.was_warmed is True

    # Find Doji in candidates
    doji_rows = [r for r in res.candidates if r.direction == Direction.DOJI]
    assert len(doji_rows) > 0
    for doji in doji_rows:
        assert doji.order_intent_status == OrderStatus.NO_ORDER_DOJI
        assert doji.stop_entry_trigger is None
        assert "produces NO ORDER" in doji.explanation
        assert "Rank #21 is not backfilled" in doji.explanation


def test_missing_cache_falls_back_to_cold_scan(tmp_path: Path):
    """When no cache exists for the session date, scanner executes cold scan with notice."""
    provider = CallCountingMockProvider.create_populated()

    # Empty tmp_path -> no cache exists
    res = run_market_scan(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=True,
        cache_dir=tmp_path,
    )

    assert res.was_warmed is False
    assert provider.fetch_daily_bars_calls == 1
    assert provider.fetch_prior_opening_range_volumes_calls == 1
    assert any("No prepared market snapshot found" in w for w in res.warnings)


def test_incompatible_cache_falls_back_to_cold_scan(tmp_path: Path):
    """When cached artifact is for a different session date, falls back to cold scan."""
    provider = CallCountingMockProvider.create_populated()

    # Prepare for session 2024-01-02
    prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        cache_dir=tmp_path,
    )

    # Now scan for session 2024-01-03
    scan_date_2 = date(2024, 1, 3)
    scan_provider = CallCountingMockProvider.create_populated()
    res = run_market_scan(
        provider=scan_provider,
        session_date=scan_date_2,
        as_of_time=datetime(2024, 1, 3, 9, 35, 0, tzinfo=MARKET_TIMEZONE),
        use_cache=True,
        cache_dir=tmp_path,
    )

    assert res.was_warmed is False
    assert scan_provider.fetch_daily_bars_calls == 1
    assert any("Cold scan fallback" in w or "No prepared market snapshot found" in w for w in res.warnings)


def test_corrupted_cache_falls_back_to_cold_scan(tmp_path: Path):
    """When cached artifact is corrupted, fails closed against corrupt cache and runs cold scan."""
    provider = CallCountingMockProvider.create_populated()

    prep_res = prepare_market(
        provider=provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        cache_dir=tmp_path,
    )

    # Corrupt the cache file
    prep_res.artifact_path.write_text("{this is corrupted json", encoding="utf-8")

    scan_provider = CallCountingMockProvider.create_populated()
    res = run_market_scan(
        provider=scan_provider,
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        use_cache=True,
        cache_dir=tmp_path,
    )

    assert res.was_warmed is False
    assert scan_provider.fetch_daily_bars_calls == 1
    assert any("Cold scan fallback (FAILED)" in w for w in res.warnings)
