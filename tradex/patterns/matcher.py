"""
Live pattern matcher.

Compares a stock's current lookback window against stored fingerprints
and returns a similarity score (0–100).

Similarity method: Pearson correlation averaged across series.
  - Correlation handles different scales naturally (no need for extra normalization)
  - We weight price_pct and volume_ratio highest since they're most predictive
  - RSI, MACD, BB are secondary confirmation

Score interpretation:
  90–100 : Near-perfect match — very strong pattern signal
  75–89  : Strong match — worth alerting
  60–74  : Moderate match — watch but don't act alone
  <60    : Weak / noise
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from tradex.data.fetcher import DEFAULT_PROVIDER, fetch
from tradex.signals.indicators import add_indicators
from tradex.patterns.fingerprint import load_fingerprint
from tradex.patterns.config import PatternConfig, PROFILES

# Weights for each series in the combined similarity score
SERIES_WEIGHTS = {
    "price_pct":    0.35,
    "volume_ratio": 0.30,
    "rsi":          0.15,
    "macd_diff":    0.10,
    "bb_width":     0.10,
}


def _series_similarity(live: list[float], fp_mean: list[float]) -> float:
    """
    Pearson correlation between live series and fingerprint mean.
    Returns 0.0 if either series is constant or too short.
    Maps correlation (-1 to 1) → similarity (0 to 100).
    """
    n = min(len(live), len(fp_mean))
    if n < 3:
        return 0.0
    a = np.array(live[-n:], dtype=float)
    b = np.array(fp_mean[-n:], dtype=float)

    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0

    corr = float(np.corrcoef(a, b)[0, 1])
    # Map [-1, 1] → [0, 100]
    return round((corr + 1) / 2 * 100, 1)


def _extract_live_window(ticker: str, lookback_days: int, provider: str | None = None) -> dict | None:
    """
    Fetch the most recent `lookback_days` bars and extract normalized series.
    Uses intraday→short→long fallback depending on available data.
    """
    try:
        df = fetch(ticker, "short", provider=provider)
        df = add_indicators(df).dropna()
    except Exception as e:
        return None

    if len(df) < lookback_days:
        return None

    window = df.iloc[-lookback_days:]
    base_close   = window["close"].iloc[0]
    base_vol_avg = window["volume"].mean()

    if base_close == 0 or base_vol_avg == 0:
        return None

    return {
        "price_pct":    ((window["close"] / base_close) - 1).mul(100).round(4).tolist(),
        "volume_ratio": (window["volume"] / base_vol_avg).round(4).tolist(),
        "rsi":          window["rsi"].round(2).tolist(),
        "macd_diff":    window["macd_diff"].round(4).tolist(),
        "bb_width":     window["bb_width"].round(4).tolist(),
    }


def match_ticker(
    ticker: str,
    event_type: str = "runup",
    profile: str = "standard",
    provider: str | None = None,
) -> dict:
    """
    Compare a ticker's current pattern against the stored fingerprint.

    Returns:
        similarity_score : 0–100
        series_scores    : per-series breakdown
        match_tier       : "strong" | "moderate" | "weak"
        interpretation   : plain-English description
    """
    effective_source = (provider or DEFAULT_PROVIDER).lower()
    fp = load_fingerprint(event_type, profile, source=provider)
    if fp is None:
        return {
            "ticker": ticker, "event_type": event_type, "profile": profile,
            "source": effective_source,
            "similarity_score": 0,
            "error": f"No {event_type} fingerprint for profile '{profile}' and source '{effective_source}' — run build first",
        }

    lookback = fp["lookback_days"]
    live = _extract_live_window(ticker, lookback, provider=provider)
    if live is None:
        return {
            "ticker": ticker, "event_type": event_type, "profile": profile,
            "source": effective_source,
            "similarity_score": 0, "error": "Could not extract live window",
        }

    series_scores = {}
    weighted_sum  = 0.0
    weight_total  = 0.0

    for key, weight in SERIES_WEIGHTS.items():
        if key not in live or key not in fp["series"]:
            continue
        score = _series_similarity(live[key], fp["series"][key]["mean"])
        series_scores[key] = score
        weighted_sum  += score * weight
        weight_total  += weight

    similarity = round(weighted_sum / weight_total, 1) if weight_total > 0 else 0.0

    cfg = PROFILES[profile]
    if similarity >= 90:
        tier = "very strong"
        note = f"Near-perfect match to historical {event_type} pattern."
    elif similarity >= cfg.alert_threshold:
        tier = "strong"
        note = f"Strong match — historically this pattern preceded a {event_type} in {fp['n_events']} events."
    elif similarity >= 60:
        tier = "moderate"
        note = "Partial match — watch closely but don't act on similarity alone."
    else:
        tier = "weak"
        note = "Low similarity — current pattern does not resemble historical events."

    return {
        "ticker":           ticker,
        "event_type":       event_type,
        "profile":          profile,
        "source":           fp.get("source", effective_source),
        "similarity_score": similarity,
        "match_tier":       tier,
        "series_scores":    series_scores,
        "fingerprint_events": fp["n_events"],
        "interpretation":   note,
        "live_series":      live,
        "fp_series":        {k: fp["series"][k]["mean"] for k in fp["series"]},
    }


def run_match_screen(
    tickers: list[str],
    event_type: str = "runup",
    profile: str = "standard",
    min_similarity: float | None = None,
    provider: str | None = None,
) -> pd.DataFrame:
    """
    Run pattern matching across a watchlist.
    Returns a DataFrame ranked by similarity score.
    """
    cfg = PROFILES[profile]
    threshold = min_similarity if min_similarity is not None else cfg.alert_threshold

    rows = []
    for ticker in tickers:
        result = match_ticker(ticker, event_type=event_type, profile=profile, provider=provider)
        if "error" not in result and result["similarity_score"] >= threshold:
            rows.append({
                "ticker":            result["ticker"],
                "similarity_score":  result["similarity_score"],
                "match_tier":        result["match_tier"],
                "event_type":        result["event_type"],
                "profile":           result["profile"],
                "fp_events":         result.get("fingerprint_events", 0),
                "score_price":       result["series_scores"].get("price_pct", 0),
                "score_volume":      result["series_scores"].get("volume_ratio", 0),
                "score_rsi":         result["series_scores"].get("rsi", 0),
                "interpretation":    result["interpretation"],
            })
        elif "error" in result:
            print(f"[skip] {ticker}: {result['error']}")

    return (
        pd.DataFrame(rows)
        .sort_values("similarity_score", ascending=False)
        .reset_index(drop=True)
    )
