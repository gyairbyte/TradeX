"""
Coil detector and signal state analyzer.

Reads signal history from the store and answers questions like:
  - Is this stock coiling? (score rising over N days without breaking out)
  - How long has this setup been building?
  - Is the score accelerating (getting stronger each scan)?
  - Which stocks have appeared the most this week without a clear breakout yet?

A "coil" is defined as:
  - Score >= threshold for at least MIN_COIL_DAYS distinct trading sessions
  - Score stable or trending upward
  - No large price move yet (close change < BREAKOUT_PCT between first and last session)

This is the pre-signal detection layer — surfaces setups BEFORE they resolve.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.config import TradeXSettings
from tradex.tracker import store

MIN_COIL_DAYS = 2          # minimum distinct sessions to qualify as a coil
COIL_SCORE_THRESHOLD = 45  # minimum score to count as "active signal"
BREAKOUT_PCT = 3.0         # if price moved more than this %, it already broke out


def _score_trend(scores: list[float]) -> float:
    """
    Returns the slope of the score over distinct sessions (positive = building, negative = fading).
    Uses linear regression on score values.
    """
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores), dtype=float)
    slope = np.polyfit(x, scores, 1)[0]
    return round(float(slope), 2)


def _coil_strength(
    latest_score: float,
    appearances: int,
    active_sessions: int,
    trend: float,
) -> float:
    """Bounded 0–100 coil strength that rewards persistence without over-weighting scan frequency."""
    latest_component = latest_score * 0.4
    persistence = min(appearances / 5, 1.0) * 20
    frequency = (active_sessions / appearances * 20) if appearances > 0 else 0
    trend_component = max(min(trend * 10, 20), 0)
    return round(min(100.0, latest_component + persistence + frequency + trend_component), 1)


def _fading_strength(
    peak_score: float,
    latest_score: float,
    trend: float,
) -> float:
    """Bounded 0–100 fade strength that rewards a meaningful decline from peak."""
    peak_drop = max(0.0, peak_score - latest_score)
    threshold_drop = max(0.0, COIL_SCORE_THRESHOLD - latest_score)
    trend_drop = max(0.0, -trend)
    return round(min(100.0, peak_drop * 2 + threshold_drop * 1.5 + trend_drop * 20), 1)


def _price_broke_out(closes: list[float]) -> bool:
    """Return True if the price move across the first/last close exceeds BREAKOUT_PCT."""
    if len(closes) < 2 or closes[0] == 0:
        return False
    price_change_pct = abs((closes[-1] - closes[0]) / closes[0]) * 100
    return price_change_pct >= BREAKOUT_PCT


def _daily_points_for_ticker(
    ticker: str, timeframe: str, days: int, *, settings: TradeXSettings | None = None
) -> pd.DataFrame:
    """Latest scored observation per distinct XNYS trading session for one ticker."""
    return store.get_daily_score_history(ticker, timeframe, days=days, settings=settings)


def _daily_points_all(
    timeframe: str, days: int, *, settings: TradeXSettings | None = None
) -> pd.DataFrame:
    """Latest scored observation per ticker per distinct trading session."""
    return store.get_all_daily_scores(timeframe, days=days, settings=settings)


def _extract_history(df: pd.DataFrame) -> tuple[list[float], list[float], list[str]]:
    """Return (scores, closes, statuses) lists from a daily-score DataFrame."""
    if df.empty:
        return [], [], []
    df = df.sort_values("trading_date").reset_index(drop=True)
    scores = df["score"].astype(float).tolist()
    closes = df["last_close"].astype(float).tolist()
    statuses = df["status"].astype(str).tolist()
    return scores, closes, statuses


def detect_coils(
    timeframe: str,
    days: int = 7,
    min_appearances: int = MIN_COIL_DAYS,
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """
    Scan signal history for tickers that are actively coiling.

    Returns a DataFrame of coiling stocks ranked by coil strength
    (combination of distinct-session persistence, active-session ratio,
    latest score, and trend).
    """
    all_points = _daily_points_all(timeframe, days=days, settings=settings)
    if all_points.empty:
        return pd.DataFrame()

    grouped = all_points.groupby("ticker")
    rows = []

    for ticker, group in grouped:
        scores, closes, statuses = _extract_history(group)
        appearances = len(scores)
        if appearances < min_appearances:
            continue

        latest_score = scores[-1]
        if latest_score < COIL_SCORE_THRESHOLD:
            continue

        if _price_broke_out(closes):
            continue

        peak_score = max(scores)
        trend = _score_trend(scores)
        if trend < -0.5:
            continue

        active_sessions = sum(1 for s in scores if s >= COIL_SCORE_THRESHOLD)
        coil_strength = _coil_strength(latest_score, appearances, active_sessions, trend)

        rows.append({
            "ticker":          ticker,
            "coil_strength":   coil_strength,
            "appearances":     appearances,
            "active_sessions": active_sessions,
            "observed_sessions": appearances,
            "latest_score":    int(latest_score),
            "latest_status":   statuses[-1],
            "peak_score":      int(peak_score),
            "score_trend":     trend,
            "trend_direction": "building" if trend > 0.5 else "stable" if trend > -0.5 else "fading",
            "first_seen":      group["scan_time"].iloc[0],
            "last_seen":       group["scan_time"].iloc[-1],
            "last_close":      round(closes[-1], 2),
            "score_history":   scores,
        })

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values("coil_strength", ascending=False)
        .reset_index(drop=True)
    )


def detect_fading_setups(
    timeframe: str,
    days: int = 7,
    min_appearances: int = MIN_COIL_DAYS,
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """
    Scan signal history for tickers that were coiling but are now fading.

    A fading setup has had at least one session above the coil threshold, has
    persisted across multiple sessions, but the latest score is below the
    threshold or meaningfully below its prior peak with a declining session trend.
    """
    all_points = _daily_points_all(timeframe, days=days, settings=settings)
    if all_points.empty:
        return pd.DataFrame()

    grouped = all_points.groupby("ticker")
    rows = []

    for ticker, group in grouped:
        scores, closes, _statuses = _extract_history(group)
        appearances = len(scores)
        if appearances < min_appearances:
            continue

        peak_score = max(scores)
        if peak_score < COIL_SCORE_THRESHOLD:
            continue

        latest_score = scores[-1]
        trend = _score_trend(scores)

        # Fading if the latest score has dropped below threshold or the trend is
        # declining and the latest score is below the peak.
        below_threshold = latest_score < COIL_SCORE_THRESHOLD
        declining_from_peak = trend < -0.5 and latest_score < peak_score
        if not (below_threshold or declining_from_peak):
            continue

        active_sessions = sum(1 for s in scores if s >= COIL_SCORE_THRESHOLD)
        fade_strength = _fading_strength(peak_score, latest_score, trend)

        rows.append({
            "ticker":          ticker,
            "fade_strength":   fade_strength,
            "appearances":     appearances,
            "active_sessions": active_sessions,
            "latest_score":    int(latest_score),
            "peak_score":      int(peak_score),
            "score_trend":     trend,
            "trend_direction": "fading" if trend < -0.5 else "stable" if trend < 0.5 else "building",
            "last_close":      round(closes[-1], 2),
            "last_seen":       group["scan_time"].iloc[-1],
            "score_history":   scores,
        })

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values("fade_strength", ascending=False)
        .reset_index(drop=True)
    )


def get_ticker_state(ticker: str, timeframe: str, days: int = 14) -> dict:
    """
    Full state report for a single ticker: history, trend, coil status,
    and a plain-English summary of what's happening.
    """
    history = _daily_points_for_ticker(ticker, timeframe, days=days)
    if history.empty:
        return {"ticker": ticker, "status": "no history", "summary": "Not seen in recent scans."}

    scores, closes, statuses = _extract_history(history)
    appearances = len(scores)
    trend = _score_trend(scores)
    latest_score = scores[-1]
    peak_score = max(scores)

    first_seen_dt = pd.to_datetime(history["scan_time"].iloc[0])
    last_seen_dt = pd.to_datetime(history["scan_time"].iloc[-1])
    days_building = (last_seen_dt - first_seen_dt).days

    is_active = (
        appearances >= MIN_COIL_DAYS
        and latest_score >= COIL_SCORE_THRESHOLD
        and not _price_broke_out(closes)
    )

    is_fading = (
        peak_score >= COIL_SCORE_THRESHOLD
        and (
            latest_score < COIL_SCORE_THRESHOLD
            or (trend < -0.5 and latest_score < peak_score)
        )
    )

    if is_active and trend > 0.5:
        status = "coiling — building pressure"
        summary = (
            f"{ticker} has appeared {appearances}x over {days_building} days "
            f"with a score trending up (slope: +{trend}). "
            f"No breakout yet. Setup is strengthening — watch closely."
        )
    elif is_active:
        status = "coiling — stable"
        summary = (
            f"{ticker} has appeared {appearances}x over {days_building} days "
            f"with a steady score ({latest_score}). Potential setup holding, not yet accelerating."
        )
    elif is_fading:
        status = "fading"
        summary = f"{ticker} was signaling but score is declining. Setup may be breaking down."
    else:
        status = "watching"
        summary = f"{ticker} has appeared {appearances}x but hasn't met coil criteria yet."

    return {
        "ticker":        ticker,
        "timeframe":     timeframe,
        "status":        status,
        "summary":       summary,
        "appearances":   appearances,
        "days_building": days_building,
        "latest_score":  latest_score,
        "peak_score":    peak_score,
        "score_trend":   trend,
        "score_history": scores,
        "close_history": closes,
        "last_status":   statuses[-1],
    }


def get_watchlist_states(tickers: list[str], timeframe: str, days: int = 7) -> pd.DataFrame:
    """Batch version of get_ticker_state — useful for dashboard overview."""
    rows = []
    for ticker in tickers:
        state = get_ticker_state(ticker, timeframe, days=days)
        rows.append({
            "ticker":        state["ticker"],
            "status":        state["status"],
            "appearances":   state.get("appearances", 0),
            "days_building": state.get("days_building", 0),
            "latest_score":  state.get("latest_score", 0),
            "peak_score":    state.get("peak_score", 0),
            "score_trend":   state.get("score_trend", 0),
            "summary":       state.get("summary", ""),
        })
    return pd.DataFrame(rows).sort_values("latest_score", ascending=False).reset_index(drop=True)
