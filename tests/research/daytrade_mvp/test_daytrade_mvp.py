"""Targeted deterministic tests for DAYTRADE-001A multi-resolution research foundation."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from tradex.research.daytrade_mvp import (
    SYNTH_DAYTRADE_001,
    CompletedBar,
    DaytradeSetup,
    MultiResolutionSeries,
    Resolution,
    SetupEvaluationResult,
    SetupEvaluationStatus,
    evaluate_setup,
    generate_synthetic_multi_res_data,
)
from tradex.strategies.registry import (
    APPROVED_PRODUCTION_STRATEGIES,
    has_production_strategy_capability,
)


def test_completed_bar_validation() -> None:
    """CompletedBar enforces timezone-awareness, OHLC validity, and positive volume."""
    now_utc = datetime(2026, 9, 25, 9, 30, tzinfo=UTC)

    # Valid bar
    bar = CompletedBar(
        timestamp=now_utc,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
        resolution=Resolution.MINUTE_1,
        bar_start=now_utc - timedelta(minutes=1),
    )
    assert bar.resolution == Resolution.MINUTE_1
    assert bar.open == 100.0

    # Naive timestamp rejected
    with pytest.raises(ValueError, match="must be timezone-aware"):
        CompletedBar(
            timestamp=datetime(2026, 9, 25, 9, 30),  # noqa: DTZ001
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=100.0,
            resolution=Resolution.MINUTE_1,
        )

    # Naive bar_start rejected
    with pytest.raises(ValueError, match="Bar start must be timezone-aware"):
        CompletedBar(
            timestamp=now_utc,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=100.0,
            resolution=Resolution.MINUTE_1,
            bar_start=datetime(2026, 9, 25, 9, 29),  # noqa: DTZ001
        )

    # bar_start > timestamp rejected
    with pytest.raises(ValueError, match="cannot be later than bar completion"):
        CompletedBar(
            timestamp=now_utc,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=100.0,
            resolution=Resolution.MINUTE_1,
            bar_start=now_utc + timedelta(minutes=1),
        )

    # high < low rejected
    with pytest.raises(ValueError, match="cannot be less than low"):
        CompletedBar(
            timestamp=now_utc,
            open=100.0,
            high=95.0,
            low=99.0,
            close=98.0,
            volume=100.0,
            resolution=Resolution.MINUTE_1,
        )

    # volume < 0 rejected
    with pytest.raises(ValueError, match="cannot be negative"):
        CompletedBar(
            timestamp=now_utc,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=-1.0,
            resolution=Resolution.MINUTE_1,
        )


def test_multi_resolution_coexistence() -> None:
    """All four resolutions (Daily, 133-tick, 1-min, 50-tick) coexist for one ticker/session."""
    series = generate_synthetic_multi_res_data(ticker="SYNTH-XYZ", include_future=False)

    assert series.ticker == "SYNTH-XYZ"
    assert series.session_date == date(2026, 9, 25)

    resolutions = series.available_resolutions()
    assert resolutions == frozenset(
        {
            Resolution.DAILY,
            Resolution.TICK_133,
            Resolution.MINUTE_1,
            Resolution.TICK_50,
        }
    )

    daily_bars = series.get_bars(Resolution.DAILY)
    assert len(daily_bars) == 1
    assert daily_bars[0].resolution == Resolution.DAILY

    tick_133_bars = series.get_bars(Resolution.TICK_133)
    assert len(tick_133_bars) == 4
    assert all(b.resolution == Resolution.TICK_133 for b in tick_133_bars)

    min_1_bars = series.get_bars(Resolution.MINUTE_1)
    assert len(min_1_bars) == 5
    assert all(b.resolution == Resolution.MINUTE_1 for b in min_1_bars)

    tick_50_bars = series.get_bars(Resolution.TICK_50)
    assert len(tick_50_bars) == 5
    assert all(b.resolution == Resolution.TICK_50 for b in tick_50_bars)

    assert series.bar_count() == 1 + 4 + 5 + 5


def test_point_in_time_filtering() -> None:
    """Point-in-time filtering strictly blocks bars whose timestamp > as_of."""
    series = generate_synthetic_multi_res_data(include_future=True)
    as_of = datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC)

    # Without as_of, future bars are present in the unfiltered series
    all_min_bars = series.get_bars(Resolution.MINUTE_1)
    assert any(b.timestamp > as_of for b in all_min_bars)

    all_tick_50_bars = series.get_bars(Resolution.TICK_50)
    assert any(b.timestamp > as_of for b in all_tick_50_bars)

    # With as_of, future bars are strictly filtered out
    pit_min_bars = series.get_bars(Resolution.MINUTE_1, as_of=as_of)
    assert len(pit_min_bars) == 5
    assert all(b.timestamp <= as_of for b in pit_min_bars)
    assert pit_min_bars[-1].timestamp == as_of

    pit_tick_50_bars = series.get_bars(Resolution.TICK_50, as_of=as_of)
    assert len(pit_tick_50_bars) == 5
    assert all(b.timestamp <= as_of for b in pit_tick_50_bars)

    # Calling with naive as_of raises ValueError
    with pytest.raises(ValueError, match="as_of timestamp must be timezone-aware"):
        series.get_bars(Resolution.MINUTE_1, as_of=datetime(2026, 9, 25, 9, 35))  # noqa: DTZ001


def test_no_future_bar_leakage_and_materialized_isolation() -> None:
    """Setup receives a newly materialized PIT series with zero access path to future bars."""
    series = generate_synthetic_multi_res_data(include_future=True)
    as_of = datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC)

    received_series_container: list[MultiResolutionSeries] = []

    class InspectingSetup(DaytradeSetup):
        @property
        def setup_id(self) -> str:
            return "TEST-INSPECT-001"

        @property
        def version(self) -> str:
            return "0.1.0"

        @property
        def required_resolutions(self) -> frozenset[Resolution]:
            return frozenset({Resolution.MINUTE_1, Resolution.TICK_50})

        def evaluate(
            self, eval_series: MultiResolutionSeries, eval_as_of: datetime
        ) -> SetupEvaluationResult:
            received_series_container.append(eval_series)
            # Inspect that future bars cannot be accessed even by omitting as_of
            unfiltered_query_min_bars = eval_series.get_bars(Resolution.MINUTE_1)
            future_leakage = [b for b in unfiltered_query_min_bars if b.timestamp > eval_as_of]
            assert len(future_leakage) == 0, f"Future bars leaked: {future_leakage}"

            unfiltered_query_50_bars = eval_series.get_bars(Resolution.TICK_50)
            future_leakage_50 = [b for b in unfiltered_query_50_bars if b.timestamp > eval_as_of]
            assert len(future_leakage_50) == 0, f"Future 50-tick leaked: {future_leakage_50}"

            return SetupEvaluationResult(
                status=SetupEvaluationStatus.SETUP_DETECTED,
                setup_id=self.setup_id,
                setup_version=self.version,
                as_of=eval_as_of,
                reasons=("Zero future leakage verified",),
                evidence={"future_bars_found": 0},
            )

    result = evaluate_setup(InspectingSetup(), series, as_of=as_of)
    assert result.status == SetupEvaluationStatus.SETUP_DETECTED

    # Verify that the passed series is a newly materialized object, not the original series
    assert len(received_series_container) == 1
    passed_series = received_series_container[0]
    assert passed_series is not series
    assert passed_series.bar_count() < series.bar_count()


def test_missing_required_resolution_fail_closed() -> None:
    """Missing required resolution produces deterministic INVALID_INPUT fail-closed result."""
    # Create series that has Daily, 133-tick, and 1-minute, but NO 50-tick bars
    series = MultiResolutionSeries(ticker="SYNTH-INCOMPLETE", session_date=date(2026, 9, 25))
    series.add_bar(
        CompletedBar(
            timestamp=datetime(2026, 9, 24, 20, 0, tzinfo=UTC),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=500_000.0,
            resolution=Resolution.DAILY,
        )
    )
    series.add_bar(
        CompletedBar(
            timestamp=datetime(2026, 9, 25, 9, 31, tzinfo=UTC),
            open=101.0,
            high=101.5,
            low=100.9,
            close=101.2,
            volume=1000.0,
            resolution=Resolution.MINUTE_1,
        )
    )
    series.add_bar(
        CompletedBar(
            timestamp=datetime(2026, 9, 25, 9, 31, 15, tzinfo=UTC),
            open=101.0,
            high=101.4,
            low=101.0,
            close=101.3,
            volume=133.0,
            resolution=Resolution.TICK_133,
        )
    )

    as_of = datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC)
    result = evaluate_setup(SYNTH_DAYTRADE_001, series, as_of=as_of)

    assert result.status == SetupEvaluationStatus.INVALID_INPUT
    assert result.setup_id == "SYNTH-DAYTRADE-001"
    assert "Missing required resolution data" in result.reasons[0]
    assert "50_tick" in result.evidence["missing_resolutions"]
    assert result.detected_entry is None


def test_synthetic_example_deterministic() -> None:
    """SYNTH_DAYTRADE_001 returns deterministic SETUP_DETECTED when qualified and NO_SETUP otherwise."""
    as_of = datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC)

    # 1. Qualified input -> SETUP_DETECTED
    series_qualified = generate_synthetic_multi_res_data(qualify_all=True)
    res_1 = evaluate_setup(SYNTH_DAYTRADE_001, series_qualified, as_of=as_of)
    assert res_1.status == SetupEvaluationStatus.SETUP_DETECTED
    assert res_1.detected_entry is not None
    assert res_1.detected_stop is not None
    assert res_1.detected_target is not None
    assert res_1.detected_stop < res_1.detected_entry < res_1.detected_target
    assert res_1.evidence["tiers_passed"] == {
        "daily": True,
        "tick_133": True,
        "minute_1": True,
        "tick_50": True,
    }

    # 2. Identical run returns identical output (determinism)
    res_1_repeat = evaluate_setup(SYNTH_DAYTRADE_001, series_qualified, as_of=as_of)
    assert res_1 == res_1_repeat

    # 3. Unqualified input (50-tick close < open) -> NO_SETUP
    series_unqualified = generate_synthetic_multi_res_data(qualify_all=False)
    res_2 = evaluate_setup(SYNTH_DAYTRADE_001, series_unqualified, as_of=as_of)
    assert res_2.status == SetupEvaluationStatus.NO_SETUP
    assert "tick_50" in res_2.reasons[0]
    assert res_2.evidence["tiers_passed"]["tick_50"] is False
    assert res_2.detected_entry is None

    # 4. Strict invariants on synthetic setup
    assert SYNTH_DAYTRADE_001.is_synthetic is True
    assert SYNTH_DAYTRADE_001.production_promotion_eligible is False


def test_no_provider_calls() -> None:
    """Execution of multi-resolution evaluator and synthetic setups makes zero provider calls."""
    with (
        patch("tradex.data.fetcher.fetch", side_effect=AssertionError("Provider fetch called")),
        patch(
            "tradex.data.history.fetch_daily_history",
            side_effect=AssertionError("Provider daily history called"),
        ),
    ):
        series = generate_synthetic_multi_res_data()
        as_of = datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC)
        result = evaluate_setup(SYNTH_DAYTRADE_001, series, as_of=as_of)
        assert result.status in (
            SetupEvaluationStatus.SETUP_DETECTED,
            SetupEvaluationStatus.NO_SETUP,
        )


def test_registry_invariants() -> None:
    """Production strategy registry remains strictly empty and rejects research setups."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()

    # Synthetic setup is NOT authorized for journal or alerts
    assert not has_production_strategy_capability(
        "SYNTH-DAYTRADE-001", "0.1.0", "journal_execution"
    )
    assert not has_production_strategy_capability(
        "SYNTH-DAYTRADE-001", "0.1.0", "automatic_alerts"
    )
    assert not has_production_strategy_capability(
        "DAYTRADE-001", "0.1.0", "journal_execution"
    )


def test_import_safety_and_no_side_effects() -> None:
    """Importing daytrade_mvp creates no side effects or mutations."""
    import tradex.research.daytrade_mvp as daytrade_pkg

    assert hasattr(daytrade_pkg, "evaluate_setup")
    assert hasattr(daytrade_pkg, "Resolution")
    assert daytrade_pkg.__version__ == "0.1.0"
    assert APPROVED_PRODUCTION_STRATEGIES == ()
