"""
Cross-timeframe confluence scoring.

Runs all three scorers on a single ticker simultaneously and returns a
combined confluence score. A stock scoring well across multiple timeframes
is a much higher conviction setup than one that only looks good on one.

Confluence uses fixed absolute weights (intraday 30%, short 40%, long 30%).
Missing timeframes contribute zero and are recorded explicitly in the result
metadata. Tiers reflect both the corrected score and how many timeframes
actually contributed.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import fetch
from tradex.earnings import days_until_earnings
from tradex.signals import intraday, long_term, short_term

# Weight by timeframe — the denominator is always the sum of all three weights
# so missing timeframes penalize the confluence score.
_WEIGHTS = {
    "intraday": 0.30,
    "short": 0.40,
    "long": 0.30,
}

_TIME_FRAME_ORDER = ["intraday", "short", "long"]


def _coverage_fields(available: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    available_tfs = [tf for tf in _TIME_FRAME_ORDER if tf in available]
    missing_tfs = [tf for tf in _TIME_FRAME_ORDER if tf not in available]
    return {
        "available_timeframes": available_tfs,
        "missing_timeframes": missing_tfs,
        "timeframe_count": len(available_tfs),
        "timeframe_coverage": f"{len(available_tfs)}/3",
        "complete_timeframe_coverage": len(available_tfs) == 3,
    }


def _compute_confluence(available: dict[str, Any]) -> int:
    """Compute the fixed-denominator weighted score. Missing timeframes contribute zero."""
    raw = sum(available[tf]["score"] * _WEIGHTS[tf] for tf in available)
    return max(0, min(100, round(raw)))


def _active_timeframes(available: dict[str, Any]) -> list[str]:
    return [tf for tf in _TIME_FRAME_ORDER if tf in available and available[tf]["score"] >= 50]


def _select_tier(confluence: int, available_tfs: list[str], active_tfs: list[str]) -> str:
    if not available_tfs:
        return "no data"

    all_three = len(available_tfs) == 3 and len(active_tfs) == 3
    at_least_two_active = len(active_tfs) >= 2 and len(available_tfs) >= 2

    if all_three and confluence >= 90:
        return "all timeframes aligned"
    if at_least_two_active and confluence >= 70:
        return "strong confluence"
    if at_least_two_active and confluence >= 50:
        return "moderate confluence"

    if len(available_tfs) == 1:
        return "weak / single timeframe"
    if len(available_tfs) == 2:
        return "weak / incomplete timeframes"
    return "weak confluence"


def score_confluence(
    ticker: str,
    provider: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> dict[str, Any]:
    """
    Fetch all three timeframes and compute a weighted confluence score.

    Returns a dict with individual scores, confluence score, tier label,
    active/available/missing timeframe metadata, and combined reasons sorted
    by timeframe. Missing timeframes contribute zero to the score and are
    recorded in ``errors`` so callers can see why they did not contribute.
    """
    available: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    fetchers: dict[str, tuple[Any, str]] = {
        "intraday": (intraday.score, "intraday"),
        "short": (short_term.score, "short"),
        "long": (long_term.score, "long"),
    }

    if settings is None:
        settings = load_runtime_settings()

    for tf in _TIME_FRAME_ORDER:
        scorer, tf_key = fetchers[tf]
        try:
            df = fetch(ticker, tf_key, provider=provider, settings=settings)
            if len(df) < 30:
                errors[tf] = "insufficient data"
                continue
            available[tf] = scorer(df)
        except Exception as e:
            errors[tf] = str(e)

    coverage = _coverage_fields(available, errors)

    if not available:
        return {
            "ticker": ticker,
            "confluence_score": 0,
            "tier": "no data",
            "active_timeframes": [],
            "scores": {},
            "reasons": {},
            "last_close": None,
            "errors": errors,
            **coverage,
        }

    confluence = _compute_confluence(available)
    active_tfs = _active_timeframes(available)
    tier = _select_tier(confluence, coverage["available_timeframes"], active_tfs)

    return {
        "ticker": ticker,
        "confluence_score": confluence,
        "tier": tier,
        "active_timeframes": active_tfs,
        "scores": {tf: available[tf]["score"] for tf in _TIME_FRAME_ORDER if tf in available},
        "reasons": {tf: available[tf]["reasons"] for tf in _TIME_FRAME_ORDER if tf in available},
        "last_close": next(iter(available.values()))["last_close"],
        "errors": errors,
        **coverage,
    }


def run_confluence_screen(
    tickers: list[str],
    min_confluence: int = 50,
    provider: str | None = None,
    exclude_earnings_within: int | None = None,
    earnings_source: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """
    Run confluence scoring across a watchlist.
    Returns a DataFrame ranked by confluence score.

    `exclude_earnings_within`: if set, drop tickers with earnings within N days.
    Result rows always include `days_until_earnings` (None if unknown).
    `earnings_source` is passed to `days_until_earnings` and defaults to Yahoo.
    """
    if settings is None:
        settings = load_runtime_settings()
    filter_enabled = exclude_earnings_within is not None and exclude_earnings_within > 0
    rows = []
    for ticker in tickers:
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source, settings=settings)
            if filter_enabled:
                if days_to_er is None:
                    print(
                        f"[skip] {ticker}: earnings date unknown/unavailable; cannot evaluate exclusion window"
                    )
                    continue
                if 0 <= days_to_er <= exclude_earnings_within:
                    print(f"[skip] {ticker}: earnings in {days_to_er}d")
                    continue

            result = score_confluence(ticker, provider=provider, settings=settings)
            if result["confluence_score"] >= min_confluence:
                rows.append(
                    {
                        "ticker": result["ticker"],
                        "confluence_score": result["confluence_score"],
                        "tier": result["tier"],
                        "active_timeframes": ", ".join(result["active_timeframes"]),
                        "timeframe_coverage": result["timeframe_coverage"],
                        "available_timeframes": ", ".join(result["available_timeframes"]),
                        "missing_timeframes": ", ".join(result["missing_timeframes"]),
                        "score_intraday": result["scores"].get("intraday", "-"),
                        "score_short": result["scores"].get("short", "-"),
                        "score_long": result["scores"].get("long", "-"),
                        "days_until_earnings": days_to_er,
                        "last_close": result.get("last_close"),
                    }
                )
        except Exception as e:
            print(f"[skip] {ticker}: {e}")

    columns = [
        "ticker",
        "confluence_score",
        "tier",
        "active_timeframes",
        "timeframe_coverage",
        "available_timeframes",
        "missing_timeframes",
        "score_intraday",
        "score_short",
        "score_long",
        "days_until_earnings",
        "last_close",
    ]
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("confluence_score", ascending=False)
        .reset_index(drop=True)
    )
