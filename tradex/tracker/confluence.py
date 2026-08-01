"""
Cross-timeframe confluence scoring.

Runs all three scorers on a single ticker simultaneously and returns a
combined confluence score. A stock scoring well across multiple timeframes
is a much higher conviction setup than one that only looks good on one.

Confluence tiers:
  90+  : All three timeframes aligned — rare, very high conviction
  70+  : Two timeframes strongly aligned
  50+  : One strong + one moderate signal
  <50  : Single-timeframe only, treat with caution
"""
import pandas as pd
from tradex.data.fetcher import fetch
from tradex.signals import intraday, short_term, long_term
from tradex.earnings import days_until_earnings


# Weight by timeframe — intraday gets less weight alone since it's noisier
_WEIGHTS = {
    "intraday": 0.30,
    "short":    0.40,
    "long":     0.30,
}


def score_confluence(ticker: str, provider: str | None = None) -> dict:
    """
    Fetch all three timeframes and compute a weighted confluence score.

    Returns a dict with individual scores, confluence score, tier label,
    and combined reasons sorted by timeframe.
    """
    results = {}
    errors = {}

    fetchers = {
        "intraday": (fetch, "intraday", intraday.score),
        "short":    (fetch, "short",    short_term.score),
        "long":     (fetch, "long",     long_term.score),
    }

    for tf, (fetch_fn, tf_key, scorer) in fetchers.items():
        try:
            df = fetch_fn(ticker, tf_key, provider=provider)
            if len(df) < 30:
                errors[tf] = "insufficient data"
                continue
            results[tf] = scorer(df)
        except Exception as e:
            errors[tf] = str(e)

    if not results:
        return {"ticker": ticker, "confluence_score": 0, "tier": "no data", "error": errors}

    # Weighted confluence score across available timeframes
    weight_sum = sum(_WEIGHTS[tf] for tf in results)
    confluence = sum(
        results[tf]["score"] * (_WEIGHTS[tf] / weight_sum)
        for tf in results
    )
    confluence = round(confluence)

    tier = (
        "all timeframes aligned" if confluence >= 90 else
        "strong confluence"      if confluence >= 70 else
        "moderate confluence"    if confluence >= 50 else
        "weak / single timeframe"
    )

    # How many timeframes scored above 50 (meaningful signal threshold)
    active_tfs = [tf for tf in results if results[tf]["score"] >= 50]

    return {
        "ticker":           ticker,
        "confluence_score": confluence,
        "tier":             tier,
        "active_timeframes": active_tfs,
        "scores": {
            tf: results[tf]["score"] for tf in results
        },
        "reasons": {
            tf: results[tf]["reasons"] for tf in results
        },
        "last_close": next(iter(results.values()))["last_close"],
        "errors":     errors,
    }


def run_confluence_screen(
    tickers: list[str],
    min_confluence: int = 50,
    provider: str | None = None,
    exclude_earnings_within: int | None = None,
    earnings_source: str | None = None,
) -> pd.DataFrame:
    """
    Run confluence scoring across a watchlist.
    Returns a DataFrame ranked by confluence score.

    `exclude_earnings_within`: if set, drop tickers with earnings within N days.
    Result rows always include `days_until_earnings` (None if unknown).
    `earnings_source` is passed to `days_until_earnings` and defaults to Yahoo.
    """
    rows = []
    for ticker in tickers:
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source)
            if (
                exclude_earnings_within is not None
                and days_to_er is not None
                and 0 <= days_to_er <= exclude_earnings_within
            ):
                print(f"[skip] {ticker}: earnings in {days_to_er}d")
                continue

            result = score_confluence(ticker, provider=provider)
            if result["confluence_score"] >= min_confluence:
                rows.append({
                    "ticker":              result["ticker"],
                    "confluence_score":    result["confluence_score"],
                    "tier":                result["tier"],
                    "active_timeframes":   ", ".join(result.get("active_timeframes", [])),
                    "score_intraday":      result["scores"].get("intraday", "-"),
                    "score_short":         result["scores"].get("short", "-"),
                    "score_long":          result["scores"].get("long", "-"),
                    "days_until_earnings": days_to_er,
                    "last_close":          result.get("last_close"),
                })
        except Exception as e:
            print(f"[skip] {ticker}: {e}")

    columns = [
        "ticker",
        "confluence_score",
        "tier",
        "active_timeframes",
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
