"""
Coil detector and signal state analyzer.

Reads signal history from the store and answers questions like:
  - Is this stock coiling? (score rising over N days without breaking out)
  - How long has this setup been building?
  - Is the score accelerating (getting stronger each scan)?
  - Which stocks have appeared the most this week without a clear breakout yet?

A "coil" is defined as:
  - Score >= threshold for at least MIN_COIL_DAYS consecutive scans
  - Score trending upward (not flat or declining)
  - No large price move yet (close change < BREAKOUT_PCT between first and last signal)

This is the pre-signal detection layer — surfaces setups BEFORE they resolve.
"""
import pandas as pd
import numpy as np
from tradex.tracker import store

MIN_COIL_DAYS = 2          # minimum appearances to qualify as a coil
COIL_SCORE_THRESHOLD = 45  # minimum score to count as "active signal"
BREAKOUT_PCT = 3.0         # if price moved more than this %, it already broke out


def _score_trend(scores: list[float]) -> float:
    """
    Returns the slope of the score over time (positive = building, negative = fading).
    Uses linear regression on score values.
    """
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores), dtype=float)
    slope = np.polyfit(x, scores, 1)[0]
    return round(float(slope), 2)


def detect_coils(timeframe: str, days: int = 7, min_appearances: int = MIN_COIL_DAYS) -> pd.DataFrame:
    """
    Scan signal history for tickers that are actively coiling.

    Returns a DataFrame of coiling stocks ranked by coil strength
    (combination of appearance count, score trend, and latest score).
    """
    appearances = store.get_recent_appearances(timeframe, days=days)
    if appearances.empty:
        return pd.DataFrame()

    qualified = appearances[appearances["appearances"] >= min_appearances]
    rows = []

    for _, row in qualified.iterrows():
        ticker = row["ticker"]
        history = store.get_history(ticker, timeframe, days=days)
        if history.empty or len(history) < min_appearances:
            continue

        scores = history["score"].tolist()
        closes = history["last_close"].tolist()

        latest_score = scores[-1]
        if latest_score < COIL_SCORE_THRESHOLD:
            continue

        # Check if price already made a big move (already broke out — not a coil anymore)
        if len(closes) >= 2 and closes[0] > 0:
            price_change_pct = abs((closes[-1] - closes[0]) / closes[0]) * 100
            if price_change_pct >= BREAKOUT_PCT:
                continue

        trend = _score_trend(scores)
        coil_strength = round(
            (latest_score * 0.4) + (row["appearances"] * 5) + max(trend * 10, 0),
            1
        )

        rows.append({
            "ticker":          ticker,
            "coil_strength":   coil_strength,
            "appearances":     int(row["appearances"]),
            "latest_score":    int(latest_score),
            "peak_score":      int(row["peak_score"]),
            "score_trend":     trend,
            "trend_direction": "building" if trend > 0.5 else "stable" if trend > -0.5 else "fading",
            "first_seen":      row["first_seen"],
            "last_seen":       row["last_seen"],
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


def get_ticker_state(ticker: str, timeframe: str, days: int = 14) -> dict:
    """
    Full state report for a single ticker: history, trend, coil status,
    and a plain-English summary of what's happening.
    """
    history = store.get_history(ticker, timeframe, days=days)
    if history.empty:
        return {"ticker": ticker, "status": "no history", "summary": "Not seen in recent scans."}

    scores = history["score"].tolist()
    closes = history["last_close"].tolist()
    trend = _score_trend(scores)
    appearances = len(history)
    latest_score = scores[-1]
    days_building = (
        pd.to_datetime(history["scan_time"].iloc[-1]) -
        pd.to_datetime(history["scan_time"].iloc[0])
    ).days

    is_coiling = (
        appearances >= MIN_COIL_DAYS
        and latest_score >= COIL_SCORE_THRESHOLD
        and (len(closes) < 2 or abs((closes[-1] - closes[0]) / closes[0]) * 100 < BREAKOUT_PCT)
    )

    if is_coiling and trend > 0.5:
        status = "coiling — building pressure"
        summary = (
            f"{ticker} has appeared {appearances}x over {days_building} days "
            f"with a score trending up (slope: +{trend}). "
            f"No breakout yet. Setup is strengthening — watch closely."
        )
    elif is_coiling:
        status = "coiling — stable"
        summary = (
            f"{ticker} has appeared {appearances}x over {days_building} days "
            f"with a steady score ({latest_score}). Potential setup holding, not yet accelerating."
        )
    elif trend < -1.0:
        status = "fading"
        summary = f"{ticker} was signaling but score is declining. Setup may be breaking down."
    else:
        status = "watching"
        summary = f"{ticker} has appeared {appearances}x but hasn't met coil criteria yet."

    return {
        "ticker":       ticker,
        "timeframe":    timeframe,
        "status":       status,
        "summary":      summary,
        "appearances":  appearances,
        "days_building": days_building,
        "latest_score": latest_score,
        "score_trend":  trend,
        "score_history": scores,
        "close_history": closes,
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
            "score_trend":   state.get("score_trend", 0),
            "summary":       state.get("summary", ""),
        })
    return pd.DataFrame(rows).sort_values("latest_score", ascending=False).reset_index(drop=True)
