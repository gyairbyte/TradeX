"""Synthetic deterministic demo fixture for ORB Candidate Preview (DAYTRADE-003E).

Provides clearly labeled synthetic market observation data:
- Session: 2024-01-02 09:35:00 ET (valid XNYS trading date)
- 15 completed contiguous prior XNYS sessions (2023-12-08 through 2023-12-29)
- Over 20 eligible symbols (testing Top-20 cutoff and rank > 20 exclusion)
- LONG, SHORT, and DOJI setups within the Top 20
- Identical RV values testing alphabetical tie-breaking
- Technical filter rejections: price <= $5, ADV < 1M, ATR <= 0.50, RV < 1.0
- Data unavailable: missing history, missing OR observations, zero baseline, no-print
- Data integrity blocked: corrupt daily bar, future-bar leakage
"""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .indicators import get_prior_xnys_sessions
from .models import (
    DailyBar,
    MinuteBar,
    OpeningRangeVolumeObservation,
)
from .snapshot import ORBSnapshot, SnapshotSymbolPayload

MARKET_TIMEZONE = ZoneInfo("America/New_York")
DEMO_SESSION_DATE = date(2024, 1, 2)
DEMO_AS_OF_TIME = datetime(2024, 1, 2, 9, 35, 0, tzinfo=MARKET_TIMEZONE)


def _generate_synthetic_daily_bars(
    symbol: str,
    prior_sessions: list[date],
    base_price: float,
    daily_volume: float,
    daily_range: float = 2.0,
) -> list[DailyBar]:
    """Generate 15 contiguous completed daily bars for Wilder ATR14 and ADV14."""
    bars: list[DailyBar] = []
    for i, s_date in enumerate(prior_sessions):
        # Deterministic slight price drift
        p = base_price + (i * 0.10)
        half_range = daily_range / 2.0
        high = p + half_range
        low = p - half_range
        open_p = p - (half_range * 0.4)
        close_p = p + (half_range * 0.4)
        vol = daily_volume + (i * 10_000)
        bars.append(
            DailyBar(
                symbol=symbol,
                session_date=s_date,
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_p, 2),
                volume=round(vol, 2),
            )
        )
    return bars


def _generate_synthetic_prior_or_volumes(
    symbol: str,
    prior_14_sessions: list[date],
    base_or_vol: float,
) -> list[OpeningRangeVolumeObservation]:
    """Generate 14 exact prior XNYS opening-range volume observations."""
    obs: list[OpeningRangeVolumeObservation] = []
    for i, s_date in enumerate(prior_14_sessions):
        vol = base_or_vol + (i * 1_000)
        obs.append(
            OpeningRangeVolumeObservation(
                symbol=symbol,
                session_date=s_date,
                volume=round(vol, 2),
            )
        )
    return obs


def _generate_synthetic_or_bars(
    symbol: str,
    session_date: date,
    open_price: float,
    close_price: float,
    high_price: float,
    low_price: float,
    total_volume: float,
) -> list[MinuteBar]:
    """Generate 5 regular-session 1-minute opening range bars (09:30-09:34 ET)."""
    bars: list[MinuteBar] = []
    minute_times = [
        time(9, 30),
        time(9, 31),
        time(9, 32),
        time(9, 33),
        time(9, 34),
    ]
    vol_per_bar = total_volume / 5.0
    # Intermediate prices
    prices = [
        (open_price, max(open_price, low_price + 0.1), low_price, open_price + 0.05),
        (open_price + 0.05, high_price - 0.1, low_price, open_price + 0.1),
        (open_price + 0.1, high_price, low_price, open_price + 0.15),
        (open_price + 0.15, high_price - 0.05, low_price, close_price - 0.05),
        (close_price - 0.05, high_price, min(close_price, low_price + 0.1), close_price),
    ]

    for m_time, (o, h, l, c) in zip(minute_times, prices):
        ts = datetime.combine(session_date, m_time, tzinfo=MARKET_TIMEZONE)
        bars.append(
            MinuteBar(
                symbol=symbol,
                timestamp=ts,
                session_date=session_date,
                open=round(o, 2),
                high=round(max(h, o, c), 2),
                low=round(min(l, o, c), 2),
                close=round(c, 2),
                volume=round(vol_per_bar, 2),
            )
        )
    return bars


def create_demo_snapshot() -> ORBSnapshot:
    """Create the synthetic ORB preview snapshot containing 32 synthetic securities."""
    prior_15_sessions = get_prior_xnys_sessions(DEMO_SESSION_DATE, 15)
    prior_14_sessions = prior_15_sessions[1:]  # Last 14 sessions

    symbols_payload: dict[str, SnapshotSymbolPayload] = {}

    # Define 23 eligible setups with descending RV targets:
    # We want 12 LONG, 9 SHORT, 2 DOJI (one in Top 20, one beyond Top 20 or rejected)
    # Plus two symbols with identical RV to test ticker alphabetical tie-breaker.
    eligible_specs = [
        # (symbol, base_price, direction, rv_mult, base_or_vol)
        ("SYNTH_L01", 150.0, "LONG", 4.50, 100_000.0),
        ("SYNTH_S01", 120.0, "SHORT", 4.20, 100_000.0),
        ("SYNTH_L02", 85.0, "LONG", 3.80, 100_000.0),
        ("SYNTH_DOJI_TOP", 65.0, "DOJI", 3.50, 100_000.0),  # Top-20 DOJI! Rank ~4
        ("SYNTH_S02", 210.0, "SHORT", 3.20, 100_000.0),
        ("SYNTH_L03", 45.0, "LONG", 3.00, 100_000.0),
        ("SYNTH_TIE_B", 95.0, "LONG", 2.80, 100_000.0),  # Tie test B
        ("SYNTH_TIE_A", 110.0, "LONG", 2.80, 100_000.0),  # Tie test A (A should rank before B)
        ("SYNTH_S03", 75.0, "SHORT", 2.60, 100_000.0),
        ("SYNTH_L04", 130.0, "LONG", 2.40, 100_000.0),
        ("SYNTH_S04", 180.0, "SHORT", 2.20, 100_000.0),
        ("SYNTH_L05", 55.0, "LONG", 2.00, 100_000.0),
        ("SYNTH_S05", 90.0, "SHORT", 1.90, 100_000.0),
        ("SYNTH_L06", 40.0, "LONG", 1.80, 100_000.0),
        ("SYNTH_S06", 160.0, "SHORT", 1.70, 100_000.0),
        ("SYNTH_L07", 220.0, "LONG", 1.60, 100_000.0),
        ("SYNTH_S07", 35.0, "SHORT", 1.50, 100_000.0),
        ("SYNTH_L08", 70.0, "LONG", 1.40, 100_000.0),
        ("SYNTH_S08", 105.0, "SHORT", 1.30, 100_000.0),
        ("SYNTH_L09", 140.0, "LONG", 1.25, 100_000.0),  # Rank 20
        # Beyond Top 20 eligible candidates:
        ("SYNTH_L10_CUTOFF", 50.0, "LONG", 1.20, 100_000.0),  # Rank 21
        ("SYNTH_S09_CUTOFF", 80.0, "SHORT", 1.15, 100_000.0),  # Rank 22
        ("SYNTH_L11_CUTOFF", 60.0, "LONG", 1.10, 100_000.0),  # Rank 23
    ]

    for sym, base_p, direction, rv_mult, base_or_vol in eligible_specs:
        daily_bars = _generate_synthetic_daily_bars(
            symbol=sym,
            prior_sessions=prior_15_sessions,
            base_price=base_p,
            daily_volume=2_000_000.0,  # Passes ADV14 >= 1M
            daily_range=2.5,  # Passes ATR14 > $0.50
        )
        prior_or_obs = _generate_synthetic_prior_or_volumes(
            symbol=sym,
            prior_14_sessions=prior_14_sessions,
            base_or_vol=base_or_vol,
        )
        # Mean prior OR volume will be approx base_or_vol + 6500 = ~106500
        mean_vol = sum(o.volume for o in prior_or_obs) / 14.0
        current_or_vol = mean_vol * rv_mult  # Ensures target RV14

        if direction == "LONG":
            open_p = base_p
            close_p = base_p + 1.20
            high_p = base_p + 1.80
            low_p = base_p - 0.40
        elif direction == "SHORT":
            open_p = base_p
            close_p = base_p - 1.20
            high_p = base_p + 0.40
            low_p = base_p - 1.80
        else:  # DOJI
            open_p = base_p
            close_p = base_p  # open == close
            high_p = base_p + 0.90
            low_p = base_p - 0.90

        or_bars = _generate_synthetic_or_bars(
            symbol=sym,
            session_date=DEMO_SESSION_DATE,
            open_price=open_p,
            close_price=close_p,
            high_price=high_p,
            low_price=low_p,
            total_volume=current_or_vol,
        )

        symbols_payload[sym] = SnapshotSymbolPayload(
            symbol=sym,
            daily_bars=daily_bars,
            opening_range_bars=or_bars,
            prior_opening_range_volumes=prior_or_obs,
            primary_exchange="XNAS",
        )

    # 4 Technical Filter Rejections:
    # 1. PENNY: price <= $5.00
    p_bars = _generate_synthetic_daily_bars("REJ_PENNY", prior_15_sessions, 4.20, 2_000_000.0, 1.0)
    p_prior = _generate_synthetic_prior_or_volumes("REJ_PENNY", prior_14_sessions, 100_000.0)
    p_or = _generate_synthetic_or_bars("REJ_PENNY", DEMO_SESSION_DATE, 4.20, 4.50, 4.70, 4.10, 200_000.0)
    symbols_payload["REJ_PENNY"] = SnapshotSymbolPayload(
        symbol="REJ_PENNY",
        daily_bars=p_bars,
        opening_range_bars=p_or,
        prior_opening_range_volumes=p_prior,
    )

    # 2. LOWADV: ADV14 < 1,000,000
    a_bars = _generate_synthetic_daily_bars("REJ_LOWADV", prior_15_sessions, 45.0, 650_000.0, 1.5)
    a_prior = _generate_synthetic_prior_or_volumes("REJ_LOWADV", prior_14_sessions, 50_000.0)
    a_or = _generate_synthetic_or_bars("REJ_LOWADV", DEMO_SESSION_DATE, 45.0, 46.0, 46.5, 44.8, 100_000.0)
    symbols_payload["REJ_LOWADV"] = SnapshotSymbolPayload(
        symbol="REJ_LOWADV",
        daily_bars=a_bars,
        opening_range_bars=a_or,
        prior_opening_range_volumes=a_prior,
    )

    # 3. LOWATR: ATR14 <= $0.50
    v_bars = _generate_synthetic_daily_bars("REJ_LOWATR", prior_15_sessions, 50.0, 2_000_000.0, 0.30)
    v_prior = _generate_synthetic_prior_or_volumes("REJ_LOWATR", prior_14_sessions, 100_000.0)
    v_or = _generate_synthetic_or_bars("REJ_LOWATR", DEMO_SESSION_DATE, 50.0, 50.20, 50.30, 49.90, 200_000.0)
    symbols_payload["REJ_LOWATR"] = SnapshotSymbolPayload(
        symbol="REJ_LOWATR",
        daily_bars=v_bars,
        opening_range_bars=v_or,
        prior_opening_range_volumes=v_prior,
    )

    # 4. LOWRV: RV14 < 1.0
    r_bars = _generate_synthetic_daily_bars("REJ_LOWRV", prior_15_sessions, 75.0, 2_000_000.0, 2.0)
    r_prior = _generate_synthetic_prior_or_volumes("REJ_LOWRV", prior_14_sessions, 100_000.0)
    r_or = _generate_synthetic_or_bars("REJ_LOWRV", DEMO_SESSION_DATE, 75.0, 76.5, 77.0, 74.5, 50_000.0)  # RV ~ 0.5
    symbols_payload["REJ_LOWRV"] = SnapshotSymbolPayload(
        symbol="REJ_LOWRV",
        daily_bars=r_bars,
        opening_range_bars=r_or,
        prior_opening_range_volumes=r_prior,
    )

    # 4 DATA_UNAVAILABLE symbols:
    # 1. MISSHIST: only 5 daily bars (needs 15)
    mh_bars = _generate_synthetic_daily_bars("UNAV_MISSHIST", prior_15_sessions[:5], 60.0, 2_000_000.0, 2.0)
    mh_prior = _generate_synthetic_prior_or_volumes("UNAV_MISSHIST", prior_14_sessions, 100_000.0)
    mh_or = _generate_synthetic_or_bars("UNAV_MISSHIST", DEMO_SESSION_DATE, 60.0, 61.5, 62.0, 59.5, 200_000.0)
    symbols_payload["UNAV_MISSHIST"] = SnapshotSymbolPayload(
        symbol="UNAV_MISSHIST",
        daily_bars=mh_bars,
        opening_range_bars=mh_or,
        prior_opening_range_volumes=mh_prior,
    )

    # 2. MISSORV: only 10 prior OR volume observations (needs 14)
    mo_bars = _generate_synthetic_daily_bars("UNAV_MISSORV", prior_15_sessions, 80.0, 2_000_000.0, 2.0)
    mo_prior = _generate_synthetic_prior_or_volumes("UNAV_MISSORV", prior_14_sessions[:10], 100_000.0)
    mo_or = _generate_synthetic_or_bars("UNAV_MISSORV", DEMO_SESSION_DATE, 80.0, 81.5, 82.0, 79.5, 200_000.0)
    symbols_payload["UNAV_MISSORV"] = SnapshotSymbolPayload(
        symbol="UNAV_MISSORV",
        daily_bars=mo_bars,
        opening_range_bars=mo_or,
        prior_opening_range_volumes=mo_prior,
    )

    # 3. ZERORV: mean prior OR volume is 0.0
    zr_bars = _generate_synthetic_daily_bars("UNAV_ZERORV", prior_15_sessions, 90.0, 2_000_000.0, 2.0)
    zr_prior = [OpeningRangeVolumeObservation(symbol="UNAV_ZERORV", session_date=d, volume=0.0) for d in prior_14_sessions]
    zr_or = _generate_synthetic_or_bars("UNAV_ZERORV", DEMO_SESSION_DATE, 90.0, 91.5, 92.0, 89.5, 50_000.0)
    symbols_payload["UNAV_ZERORV"] = SnapshotSymbolPayload(
        symbol="UNAV_ZERORV",
        daily_bars=zr_bars,
        opening_range_bars=zr_or,
        prior_opening_range_volumes=zr_prior,
    )

    # 4. NOPRINT: 0 opening range bars (NO_OPENING_PRINT_NO_SETUP)
    np_bars = _generate_synthetic_daily_bars("UNAV_NOPRINT", prior_15_sessions, 100.0, 2_000_000.0, 2.0)
    np_prior = _generate_synthetic_prior_or_volumes("UNAV_NOPRINT", prior_14_sessions, 100_000.0)
    symbols_payload["UNAV_NOPRINT"] = SnapshotSymbolPayload(
        symbol="UNAV_NOPRINT",
        daily_bars=np_bars,
        opening_range_bars=[],  # 0 bars
        prior_opening_range_volumes=np_prior,
    )

    # 2 INTEGRITY_BLOCKED symbols:
    # 1. CORRUPT_DAILY: captured parse/integrity error (e.g. high < low or negative volume)
    symbols_payload["BLOCKED_CORRUPT"] = SnapshotSymbolPayload(
        symbol="BLOCKED_CORRUPT",
        daily_bars=[],
        opening_range_bars=[],
        prior_opening_range_volumes=[],
        integrity_error="DailyBar high 10.0 must be >= max(open=15.0, close=12.0) for BLOCKED_CORRUPT",
    )

    # 2. FUTURELEAK: minute bar with timestamp >= 09:35 ET
    fl_bars = _generate_synthetic_daily_bars("BLOCKED_FUTURE", prior_15_sessions, 110.0, 2_000_000.0, 2.0)
    fl_prior = _generate_synthetic_prior_or_volumes("BLOCKED_FUTURE", prior_14_sessions, 100_000.0)
    fl_or = _generate_synthetic_or_bars("BLOCKED_FUTURE", DEMO_SESSION_DATE, 110.0, 111.0, 112.0, 109.0, 150_000.0)
    # Add a 6th bar at 09:35:00 ET (future bar leakage!)
    future_ts = datetime.combine(DEMO_SESSION_DATE, time(9, 35), tzinfo=MARKET_TIMEZONE)
    fl_or.append(
        MinuteBar(
            symbol="BLOCKED_FUTURE",
            timestamp=future_ts,
            session_date=DEMO_SESSION_DATE,
            open=111.0,
            high=111.5,
            low=110.8,
            close=111.2,
            volume=20_000.0,
        )
    )
    symbols_payload["BLOCKED_FUTURE"] = SnapshotSymbolPayload(
        symbol="BLOCKED_FUTURE",
        daily_bars=fl_bars,
        opening_range_bars=fl_or,
        prior_opening_range_volumes=fl_prior,
    )

    return ORBSnapshot(
        session_date=DEMO_SESSION_DATE,
        as_of_time=DEMO_AS_OF_TIME,
        source_type="synthetic_demo",
        source_label="TradeX Research Synthetic Demo Universe",
        completeness_status="watchlist_only",
        symbols=symbols_payload,
        notes="Synthetic toy snapshot for research candidate preview validation (32 total symbols).",
    )


def get_demo_snapshot_dict() -> dict[str, Any]:
    """Return JSON-serializable dictionary representation of the synthetic demo snapshot."""
    snapshot = create_demo_snapshot()
    syms_dict: dict[str, Any] = {}

    for sym, payload in snapshot.symbols.items():
        if payload.integrity_error:
            # Emit malformed structure so that parsing JSON reproduces the integrity error
            syms_dict[sym] = {
                "symbol": sym,
                "primary_exchange": payload.primary_exchange,
                "daily_bars": [
                    {
                        "session_date": "2023-12-29",
                        "open": 15.0,
                        "high": 10.0,  # Corrupt: high < open
                        "low": 9.0,
                        "close": 12.0,
                        "volume": 1000.0,
                    }
                ],
                "opening_range_bars": [],
                "prior_opening_range_volumes": [],
            }
            continue

        daily_list = [
            {
                "session_date": b.session_date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in payload.daily_bars
        ]
        or_list = [
            {
                "timestamp": b.timestamp.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in payload.opening_range_bars
        ]
        prior_list = [
            {
                "session_date": obs.session_date.isoformat(),
                "volume": obs.volume,
            }
            for obs in payload.prior_opening_range_volumes
        ]
        syms_dict[sym] = {
            "symbol": sym,
            "primary_exchange": payload.primary_exchange,
            "daily_bars": daily_list,
            "opening_range_bars": or_list,
            "prior_opening_range_volumes": prior_list,
        }

    return {
        "schema_version": "1.0",
        "session_date": snapshot.session_date.isoformat(),
        "as_of_time": snapshot.as_of_time.isoformat(),
        "source_type": snapshot.source_type,
        "source_label": snapshot.source_label,
        "completeness_status": snapshot.completeness_status,
        "notes": snapshot.notes,
        "symbols": syms_dict,
    }


def get_demo_snapshot_json(indent: int = 2) -> str:
    """Return JSON string representation of the synthetic demo snapshot."""
    return json.dumps(get_demo_snapshot_dict(), indent=indent)
