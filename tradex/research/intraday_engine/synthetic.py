"""Deterministic synthetic data generator for the INTRA-001C engine."""
from __future__ import annotations

import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .calendar import build_sessions as cal_build_sessions
from .engine import TickerInput
from .models import TickerMeta
from .normalize import normalize_to_sessions
from .spec import IntradaySpec


def _clamp_ohlc(open_p, high_p, low_p, close_p):
    """Ensure OHLC consistency."""
    high_p = max(high_p, open_p, close_p)
    low_p = min(low_p, open_p, close_p)
    return open_p, high_p, low_p, close_p


def _generate_session(
    session,
    base_price: float,
    volume_base: float,
    scenario: str = "target",
    seed_offset: int = 0,
) -> pd.DataFrame:
    """Generate one session of OHLCV bars for a synthetic scenario."""
    rng = np.random.default_rng(seed_offset)
    grid = sorted(session.grid)
    records = []
    cum_pv = 0.0
    cum_v = 0.0
    vwap = base_price
    prev_close = base_price
    first_six_volume_factor = float(rng.uniform(2.5, 5.0))
    first_six_volume = volume_base * first_six_volume_factor
    rest_volume = volume_base
    signal_low: float | None = None
    signal_close: float | None = None

    for i, g in enumerate(grid):
        if i < 6:
            # Rising opening drive with elevated volume.
            open_p = base_price * (1 + i * 0.0012)
            close_p = open_p * 1.0015
            vol = first_six_volume
        elif i == 12:
            if scenario == "none":
                # No engineered reclaim; continue with a normal bar.
                open_p = prev_close
                close_p = open_p * (1 + rng.normal(0.0002, 0.0005))
                high_p = max(open_p, close_p) * 1.001
                low_p = min(open_p, close_p) * 0.999
            else:
                # 10:30 bar: engineered pullback/reclaim.
                open_p = prev_close
                close_p = max(vwap * 1.004, open_p * 1.002)
                low_p = vwap * 0.995
                high_p = close_p * 1.001
                open_p, high_p, low_p, close_p = _clamp_ohlc(open_p, high_p, low_p, close_p)
                signal_low = low_p
                signal_close = close_p
            vol = rest_volume
            # typical price and volume update for VWAP.
            typical = (high_p + low_p + close_p) / 3.0
            cum_pv += typical * vol
            cum_v += vol
            if cum_v > 0:
                vwap = cum_pv / cum_v
            records.append(
                {
                    "datetime": g,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                }
            )
            prev_close = close_p
            continue
        else:
            open_p = prev_close
            drift = rng.normal(0.0002, 0.0005)
            close_p = open_p * (1 + drift)
            vol = rest_volume

        # Post-entry exit shaping at the bar following the reclaim (idx 13).
        if i == 13 and signal_close is not None and signal_low is not None:
            entry_fill = signal_close * 1.0005
            stop = signal_low - max(0.01, signal_close * 0.0005)
            risk = entry_fill - stop
            target = entry_fill + 1.5 * risk

            if scenario == "target":
                open_p = signal_close
                close_p = target * 1.001
                high_p = close_p * 1.001
                low_p = open_p * 0.999
            elif scenario == "stop":
                open_p = signal_close
                close_p = stop * 0.99
                low_p = close_p * 0.999
                high_p = open_p * 1.001
            elif scenario == "gap_stop":
                open_p = stop * 0.98
                close_p = open_p * 0.999
                high_p = open_p * 1.001
                low_p = close_p * 0.999
            elif scenario == "gap_target":
                open_p = target * 1.02
                close_p = open_p * 0.999
                high_p = open_p * 1.001
                low_p = close_p * 0.999
            elif scenario == "same_bar":
                open_p = signal_close
                close_p = open_p * 1.0001
                low_p = stop * 0.99
                high_p = target * 1.01
            elif scenario == "time":
                open_p = signal_close
                close_p = open_p * (1 + rng.normal(0.0, 0.0005))
                high_p = max(open_p, close_p) * 1.001
                low_p = min(open_p, close_p) * 0.999
                # Keep inside stop/target band.
                low_p = max(low_p, stop * 1.01)
                high_p = min(high_p, target * 0.99)
                close_p = min(max(close_p, low_p), high_p)
            else:
                close_p = open_p * (1 + drift)

            open_p, high_p, low_p, close_p = _clamp_ohlc(open_p, high_p, low_p, close_p)

        elif i > 13:
            # Mild continuation.
            close_p = open_p * (1 + rng.normal(0.0001, 0.0003))

        high_p = max(open_p, close_p) * 1.001
        low_p = min(open_p, close_p) * 0.999
        typical = (high_p + low_p + close_p) / 3.0
        cum_pv += typical * vol
        cum_v += vol
        if cum_v > 0:
            vwap = cum_pv / cum_v

        records.append(
            {
                "datetime": g,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": vol,
            }
        )
        prev_close = close_p

    df = pd.DataFrame(records)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    return df


def _generate_ticker_sessions(
    ticker: str,
    is_etf: bool,
    sessions: list,
    base_price: float,
    volume_base: float,
    seed: int,
) -> TickerInput:
    """Generate a deterministic multi-session DataFrame for one ticker."""
    scenarios = [
        "target",
        "stop",
        "time",
        "gap_target",
        "gap_stop",
        "same_bar",
        "none",
    ]
    all_records: list[dict] = []
    for idx, session in enumerate(sessions):
        scenario = scenarios[idx % len(scenarios)]
        df = _generate_session(
            session, base_price, volume_base, scenario=scenario, seed_offset=seed + idx
        )
        all_records.extend(df.reset_index().to_dict("records"))

    combined = pd.DataFrame(all_records)
    combined["datetime"] = pd.to_datetime(combined["datetime"], utc=True)
    combined = combined.set_index("datetime").sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]

    normalized, summary = normalize_to_sessions(combined, ticker)
    meta = TickerMeta(
        ticker=ticker,
        is_etf=is_etf,
        is_eligible=True,
        prior_close=base_price,
        prior_20_median_dollar_volume=base_price * volume_base,
    )
    return TickerInput(ticker=ticker, meta=meta, sessions=normalized, quality_summary=summary)


def generate_synthetic_inputs(
    spec: IntradaySpec,
    *,
    seed: int = 20260801,
    n_stock_tickers: int = 5,
    n_etf_tickers: int = 2,
    n_sessions: int = 50,
    start_date: date | None = None,
) -> list[TickerInput]:
    """Generate a deterministic synthetic ticker universe for the engine."""
    if start_date is None:
        start_date = date(2025, 1, 2)
    end_date = start_date + timedelta(days=n_sessions * 2)
    sessions = cal_build_sessions(start_date, end_date)
    sessions = sessions[:n_sessions]

    rng = random.Random(seed)
    inputs: list[TickerInput] = []
    for i in range(n_stock_tickers):
        ticker = f"SYNTH-STK-{i+1:03d}"
        base_price = float(rng.uniform(20, 150))
        volume_base = float(rng.uniform(1_000_000, 5_000_000))
        inputs.append(
            _generate_ticker_sessions(
                ticker, False, sessions, base_price, volume_base, seed=seed + i + 1
            )
        )
    for i in range(n_etf_tickers):
        ticker = f"SYNTH-ETF-{i+1:03d}"
        base_price = float(rng.uniform(30, 120))
        volume_base = float(rng.uniform(2_000_000, 8_000_000))
        inputs.append(
            _generate_ticker_sessions(
                ticker, True, sessions, base_price, volume_base, seed=seed + 1000 + i + 1
            )
        )
    return inputs
