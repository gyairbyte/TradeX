"""
Live pattern matcher.

Compares a stock's current lookback window against stored fingerprints
and returns a similarity score (0–100).

Similarity method: Pearson correlation averaged across series. Correlation
handles different scales naturally, but it measures shape resemblance, not
causality or expected return.

Score interpretation:
  90–100 : High shape similarity to the stored fingerprint
  75–89  : Strong shape similarity to the stored fingerprint
  60–74  : Moderate shape similarity
  <60    : Low shape similarity / noise

Predictive value is unvalidated. This module is used by the dashboard for
experimental research and is not part of production scoring or automatic alerts.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import fetch
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


def _extract_live_window(
    ticker: str,
    lookback_days: int,
    provider: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> dict | None:
    """
    Fetch the most recent `lookback_days` bars and extract normalized series.
    Uses intraday→short→long fallback depending on available data.
    """
    try:
        df = fetch(ticker, "short", provider=provider, settings=settings)
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
    *,
    settings: TradeXSettings | None = None,
) -> dict:
    """
    Compare a ticker's current pattern against the stored fingerprint.

    Returns:
        similarity_score : 0–100
        series_scores    : per-series breakdown
        match_tier       : "strong" | "moderate" | "weak"
        interpretation   : plain-English description
    """
    if settings is None:
        settings = load_runtime_settings()
    effective_source = (provider or settings.data.data_provider).lower()
    fp = load_fingerprint(event_type, profile, source=provider, settings=settings)
    if fp is None:
        return {
            "ticker": ticker, "event_type": event_type, "profile": profile,
            "source": effective_source,
            "similarity_score": 0,
            "error": f"No {event_type} fingerprint for profile '{profile}' and source '{effective_source}' — run build first",
        }

    lookback = fp["lookback_days"]
    live = _extract_live_window(ticker, lookback, provider=provider, settings=settings)
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
        note = "High shape similarity to the stored fingerprint. Predictive value is unvalidated."
    elif similarity >= cfg.alert_threshold:
        tier = "strong"
        note = "High shape similarity to the stored fingerprint. Predictive value is unvalidated."
    elif similarity >= 60:
        tier = "moderate"
        note = "Moderate shape similarity to the stored fingerprint. Predictive value is unvalidated."
    else:
        tier = "weak"
        note = "Low shape similarity to the stored fingerprint. Predictive value is unvalidated."

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
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """
    Run pattern matching across a watchlist.
    Returns a DataFrame ranked by similarity score.
    """
    cfg = PROFILES[profile]
    threshold = min_similarity if min_similarity is not None else cfg.alert_threshold

    columns = [
        "ticker", "similarity_score", "match_tier", "event_type", "profile",
        "fp_events", "score_price", "score_volume", "score_rsi", "interpretation",
    ]
    rows = []
    for ticker in tickers:
        result = match_ticker(
            ticker, event_type=event_type, profile=profile, provider=provider, settings=settings
        )
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

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("similarity_score", ascending=False)
        .reset_index(drop=True)
    )
