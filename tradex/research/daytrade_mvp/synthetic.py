"""Synthetic smoke setup and deterministic fixture generator (DAYTRADE-001A).

This module contains:
1. SYNTH_DAYTRADE_001: An architectural smoke setup proving multi-resolution evaluation.
2. generate_synthetic_multi_res_data: A deterministic fixture generator.

CRITICAL INVARIANTS:
- Synthetic example ONLY.
- NOT a real trading hypothesis.
- NOT production-promotion eligible (production_promotion_eligible = False).
- ZERO provider calls.
- NEVER uses real tickers.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from .models import (
    CompletedBar,
    MultiResolutionSeries,
    Resolution,
    SetupEvaluationResult,
    SetupEvaluationStatus,
)
from .setup import DaytradeSetup


class SyntheticDaytradeSetup(DaytradeSetup):
    """Synthetic multi-resolution setup used solely for testing and architectural validation."""

    @property
    def setup_id(self) -> str:
        return "SYNTH-DAYTRADE-001"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def required_resolutions(self) -> frozenset[Resolution]:
        return frozenset(
            {
                Resolution.DAILY,
                Resolution.TICK_133,
                Resolution.MINUTE_1,
                Resolution.TICK_50,
            }
        )

    @property
    def is_synthetic(self) -> bool:
        return True

    @property
    def production_promotion_eligible(self) -> bool:
        return False

    def evaluate(
        self, series: MultiResolutionSeries, as_of: datetime
    ) -> SetupEvaluationResult:
        """Evaluate synthetic 4-tier alignment across Daily, 133-tick, 1-min, and 50-tick."""
        daily_bars = series.get_bars(Resolution.DAILY, as_of=as_of)
        tick_133_bars = series.get_bars(Resolution.TICK_133, as_of=as_of)
        min_1_bars = series.get_bars(Resolution.MINUTE_1, as_of=as_of)
        tick_50_bars = series.get_bars(Resolution.TICK_50, as_of=as_of)

        last_daily = daily_bars[-1]
        last_133 = tick_133_bars[-1]
        last_1m = min_1_bars[-1]
        last_50 = tick_50_bars[-1]

        # Tier 1: Daily context (macro bullish)
        daily_ok = last_daily.close >= last_daily.open
        # Tier 2: 133-tick structural momentum
        tick_133_ok = last_133.close >= last_133.open
        # Tier 3: 1-minute setup alignment
        min_1_ok = last_1m.close >= last_1m.open
        # Tier 4: 50-tick precision entry timing & micro-volume confirmation
        tick_50_ok = (last_50.close >= last_50.open) and (last_50.volume >= 50.0)

        evidence: dict[str, Any] = {
            "daily_close": last_daily.close,
            "daily_open": last_daily.open,
            "tick_133_close": last_133.close,
            "tick_133_open": last_133.open,
            "min_1_close": last_1m.close,
            "min_1_open": last_1m.open,
            "tick_50_close": last_50.close,
            "tick_50_open": last_50.open,
            "tick_50_volume": last_50.volume,
            "tiers_passed": {
                "daily": daily_ok,
                "tick_133": tick_133_ok,
                "minute_1": min_1_ok,
                "tick_50": tick_50_ok,
            },
        }

        if daily_ok and tick_133_ok and min_1_ok and tick_50_ok:
            entry_price = round(last_50.close, 2)
            stop_price = round(min(last_50.low, last_1m.low) - 0.05, 2)
            risk = round(entry_price - stop_price, 2)
            target_price = round(entry_price + (2.0 * max(risk, 0.10)), 2)

            return SetupEvaluationResult(
                status=SetupEvaluationStatus.SETUP_DETECTED,
                setup_id=self.setup_id,
                setup_version=self.version,
                as_of=as_of,
                reasons=(
                    (
                        "Synthetic 4-tier alignment confirmed: Daily bullish context, "
                        "133-tick momentum, 1-min setup, 50-tick entry timing."
                    ),
                ),
                evidence=evidence,
                detected_entry=entry_price,
                detected_stop=stop_price,
                detected_target=target_price,
            )

        failed_tiers = [
            tier for tier, passed in evidence["tiers_passed"].items() if not passed
        ]
        return SetupEvaluationResult(
            status=SetupEvaluationStatus.NO_SETUP,
            setup_id=self.setup_id,
            setup_version=self.version,
            as_of=as_of,
            reasons=(f"Synthetic alignment incomplete; failed tiers: {', '.join(failed_tiers)}",),
            evidence=evidence,
        )


SYNTH_DAYTRADE_001 = SyntheticDaytradeSetup()


def generate_synthetic_multi_res_data(
    ticker: str = "SYNTH-DEMO",
    session_date: date | None = None,
    qualify_all: bool = True,
    include_future: bool = True,
) -> MultiResolutionSeries:
    """Generate deterministic synthetic multi-resolution bars for testing.

    Bars cover DAILY, TICK_133, MINUTE_1, and TICK_50.
    Evaluation decision timestamp for tests is 2026-09-25 09:35:00 UTC.
    If include_future=True, bars past 09:35:00 UTC are added to verify PIT filtering.
    """
    if session_date is None:
        session_date = date(2026, 9, 25)

    series = MultiResolutionSeries(ticker=ticker, session_date=session_date)

    # 1. Daily bar (prior completed session)
    series.add_bar(
        CompletedBar(
            timestamp=datetime(2026, 9, 24, 20, 0, tzinfo=UTC),
            open=100.0,
            high=102.5,
            low=99.5,
            close=102.0,
            volume=1_000_000.0,
            resolution=Resolution.DAILY,
        )
    )

    # 2. 1-Minute bars (09:31 to 09:35 UTC)
    min_data = [
        (datetime(2026, 9, 25, 9, 31, tzinfo=UTC), 102.1, 102.3, 102.0, 102.2, 500.0),
        (datetime(2026, 9, 25, 9, 32, tzinfo=UTC), 102.2, 102.4, 102.1, 102.3, 600.0),
        (datetime(2026, 9, 25, 9, 33, tzinfo=UTC), 102.3, 102.5, 102.2, 102.4, 750.0),
        (datetime(2026, 9, 25, 9, 34, tzinfo=UTC), 102.4, 102.6, 102.3, 102.5, 800.0),
        (datetime(2026, 9, 25, 9, 35, tzinfo=UTC), 102.5, 102.8, 102.4, 102.7, 950.0),
    ]
    for ts, o, h, l, c, v in min_data:
        series.add_bar(
            CompletedBar(
                timestamp=ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                resolution=Resolution.MINUTE_1,
            )
        )

    # 3. 133-Tick bars (roughly every 75-90 seconds)
    tick_133_data = [
        (datetime(2026, 9, 25, 9, 31, 15, tzinfo=UTC), 102.1, 102.3, 102.0, 102.25, 133.0),
        (datetime(2026, 9, 25, 9, 32, 30, tzinfo=UTC), 102.25, 102.45, 102.2, 102.35, 133.0),
        (datetime(2026, 9, 25, 9, 33, 45, tzinfo=UTC), 102.35, 102.55, 102.3, 102.5, 133.0),
        (datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC), 102.5, 102.8, 102.45, 102.75, 133.0),
    ]
    for ts, o, h, l, c, v in tick_133_data:
        series.add_bar(
            CompletedBar(
                timestamp=ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                resolution=Resolution.TICK_133,
            )
        )

    # 4. 50-Tick bars (roughly every 20-40 seconds)
    tick_50_close = 102.75 if qualify_all else 102.40  # qualify vs. fail
    tick_50_data = [
        (datetime(2026, 9, 25, 9, 31, 5, tzinfo=UTC), 102.1, 102.2, 102.05, 102.15, 50.0),
        (datetime(2026, 9, 25, 9, 32, 10, tzinfo=UTC), 102.15, 102.35, 102.1, 102.3, 50.0),
        (datetime(2026, 9, 25, 9, 33, 15, tzinfo=UTC), 102.3, 102.45, 102.25, 102.4, 50.0),
        (datetime(2026, 9, 25, 9, 34, 20, tzinfo=UTC), 102.4, 102.6, 102.35, 102.55, 50.0),
        (
            datetime(2026, 9, 25, 9, 35, 0, tzinfo=UTC),
            102.55,
            102.8,
            102.35 if not qualify_all else 102.5,
            tick_50_close,
            50.0,
        ),
    ]
    for ts, o, h, l, c, v in tick_50_data:
        series.add_bar(
            CompletedBar(
                timestamp=ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                resolution=Resolution.TICK_50,
            )
        )

    # 5. Future bars (past as_of = 09:35:00 UTC) for leakage testing
    if include_future:
        # Future 1-min bar at 09:36
        series.add_bar(
            CompletedBar(
                timestamp=datetime(2026, 9, 25, 9, 36, tzinfo=UTC),
                open=102.7,
                high=103.5,
                low=102.6,
                close=103.2,
                volume=1500.0,
                resolution=Resolution.MINUTE_1,
            )
        )
        # Future 50-tick bar at 09:35:25
        series.add_bar(
            CompletedBar(
                timestamp=datetime(2026, 9, 25, 9, 35, 25, tzinfo=UTC),
                open=102.75,
                high=103.0,
                low=102.7,
                close=102.9,
                volume=50.0,
                resolution=Resolution.TICK_50,
            )
        )
        # Future 133-tick bar at 09:36:15
        series.add_bar(
            CompletedBar(
                timestamp=datetime(2026, 9, 25, 9, 36, 15, tzinfo=UTC),
                open=102.75,
                high=103.5,
                low=102.7,
                close=103.1,
                volume=133.0,
                resolution=Resolution.TICK_133,
            )
        )

    return series
