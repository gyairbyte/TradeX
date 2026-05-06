"""
Historical pattern miner.

For each ticker in the universe:
  1. Download 3 years of daily OHLCV + indicators
  2. Scan forward looking for run-up or decline events (move >= threshold in move_days)
  3. For each event, extract the pre-event window (lookback_days before the move started)
  4. Normalize the window so prices from different stocks are comparable
  5. Return all extracted windows for fingerprinting

Normalization strategy:
  - Price series: pct change from window start (so NVDA $800 and AMD $150 are comparable)
  - Volume series: ratio to 20-day average at window start (relative, not absolute)
  - Indicators (RSI, MACD diff, BB width): used as-is (already normalized by construction)

This module is compute-heavy on first run. Results are cached to
~/.tradex/pattern_events.db so subsequent runs are fast.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from tradex.signals.indicators import add_indicators
from tradex.patterns.config import PatternConfig, PROFILES


# ── S&P 500 + Nasdaq 100 universe for mining ──────────────────────────────────
# A broad but manageable universe. The miner will skip any that fail.
MINING_UNIVERSE = [
    # Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ORCL", "AMD",
    # Financials
    "JPM", "BAC", "GS", "MS", "BLK", "SCHW", "C", "WFC",
    # Healthcare
    "UNH", "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO",
    # Industrials / energy
    "CAT", "DE", "XOM", "CVX", "COP",
    # High-growth / momentum
    "PLTR", "CRWD", "NET", "SNOW", "DDOG", "ARM", "SMCI", "MU", "MSTR",
    # ETFs (have their own move dynamics)
    "SPY", "QQQ", "SOXL", "TQQQ", "ARKK",
]


def _fetch_history(ticker: str, years: int) -> pd.DataFrame | None:
    """Download daily OHLCV for `years` years and compute indicators."""
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    try:
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df.empty or len(df) < 60:
            return None

        # Handle MultiIndex columns from newer yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        return add_indicators(df).dropna()
    except Exception:
        return None


def _find_events(df: pd.DataFrame, cfg: PatternConfig, event_type: str) -> list[int]:
    """
    Return list of integer positions (iloc indices) where events start.
    An event starts at position i if the price moved >= threshold
    over the next move_days bars.
    """
    closes = df["close"].values
    events = []
    i = 0
    while i < len(closes) - cfg.move_days:
        entry = closes[i]
        exit_ = closes[i + cfg.move_days]
        pct = (exit_ - entry) / entry * 100

        if event_type == "runup" and pct >= cfg.runup_pct:
            events.append(i)
            i += cfg.move_days  # skip forward to avoid overlapping windows
        elif event_type == "decline" and pct <= -cfg.decline_pct:
            events.append(i)
            i += cfg.move_days
        else:
            i += 1
    return events


def _normalize_window(window: pd.DataFrame) -> dict[str, list[float]] | None:
    """
    Normalize a pre-event window so it can be averaged across stocks.
    Returns None if the window is too short or has bad data.
    """
    if len(window) < 5 or window["close"].iloc[0] == 0:
        return None

    base_close = window["close"].iloc[0]
    base_vol_avg = window["volume"].mean()
    if base_vol_avg == 0:
        return None

    return {
        # Price: cumulative % return from window start
        "price_pct":    ((window["close"] / base_close) - 1).mul(100).round(4).tolist(),
        # Volume: ratio to window's own average (so a spike on day 8 reads as 2.5x)
        "volume_ratio": (window["volume"] / base_vol_avg).round(4).tolist(),
        # Indicators: already normalized
        "rsi":          window["rsi"].round(2).tolist(),
        "macd_diff":    window["macd_diff"].round(4).tolist(),
        "bb_width":     window["bb_width"].round(4).tolist(),
        "atr":          window["atr"].round(4).tolist(),
    }


def mine_events(
    tickers: list[str] | None = None,
    cfg: PatternConfig | None = None,
    event_type: str = "runup",   # "runup" | "decline" | "both"
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Mine historical events from a universe of tickers.

    Returns a DataFrame where each row is one pre-event window:
      ticker, event_type, event_date, move_pct, normalized series columns...

    This is the raw material for fingerprint.py to average into a fingerprint.
    """
    if cfg is None:
        cfg = PROFILES["standard"]
    if tickers is None:
        tickers = MINING_UNIVERSE

    types = ["runup", "decline"] if event_type == "both" else [event_type]
    all_rows = []

    for ticker in tickers:
        if verbose:
            print(f"  Mining {ticker}…", end=" ", flush=True)

        df = _fetch_history(ticker, cfg.history_years)
        if df is None:
            if verbose:
                print("skip (no data)")
            continue

        ticker_events = 0
        for etype in types:
            event_positions = _find_events(df, cfg, etype)
            for pos in event_positions:
                # Pre-event window: lookback_days BEFORE the move starts
                win_start = pos - cfg.lookback_days
                if win_start < 0:
                    continue
                window = df.iloc[win_start:pos]
                normalized = _normalize_window(window)
                if normalized is None:
                    continue

                # Actual move that followed
                entry_close = df["close"].iloc[pos]
                exit_close  = df["close"].iloc[min(pos + cfg.move_days, len(df) - 1)]
                move_pct    = (exit_close - entry_close) / entry_close * 100

                all_rows.append({
                    "ticker":     ticker,
                    "event_type": etype,
                    "event_date": str(df.index[pos].date()),
                    "move_pct":   round(float(move_pct), 2),
                    **{k: v for k, v in normalized.items()},
                })
                ticker_events += 1

        if verbose:
            print(f"{ticker_events} events")

    result = pd.DataFrame(all_rows)
    if verbose:
        print(f"\nTotal events mined: {len(result)}")
    return result
