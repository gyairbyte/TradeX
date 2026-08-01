"""
Runs all three signal scorers across a watchlist and returns ranked results.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import pandas as pd
from tradex.data.fetcher import fetch, resolve_provider
from tradex.signals import intraday, short_term, long_term
from tradex.earnings import days_until_earnings


SIGNAL_MAP = {
    "intraday": (intraday.score, "intraday"),
    "short":    (short_term.score, "short"),
    "long":     (long_term.score, "long"),
}

# Concurrent workers for the per-ticker scan loop. Schwab handles this fine;
# yfinance is more rate-limit-prone so we keep it moderate.
DEFAULT_WORKERS = 12


def run(
    tickers: list[str],
    timeframe: str = "intraday",
    min_score: int = 40,
    exclude_earnings_within: int | None = None,
    max_workers: int = DEFAULT_WORKERS,
    progress: Callable[[int, int], None] | None = None,
    provider: str | None = None,
    earnings_source: str | None = None,
) -> pd.DataFrame:
    """
    `exclude_earnings_within`: if set, drop tickers with earnings within N days.
    Result rows always include `days_until_earnings` (None if unknown/unavailable).
    `progress(done, total)` is called once per completed ticker if provided —
    useful for driving a Streamlit progress bar on long scans.
    `provider` is passed through to the central fetcher; when None, fetcher falls
    back to `DATA_PROVIDER` env var and then `yahoo`.
    `earnings_source` is passed to `days_until_earnings` and defaults to Yahoo.
    """
    scorer, tf_key = SIGNAL_MAP[timeframe]
    effective_provider = resolve_provider(provider)

    def _score_one(ticker: str) -> dict | None:
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source)
            if (
                exclude_earnings_within is not None
                and days_to_er is not None
                and 0 <= days_to_er <= exclude_earnings_within
            ):
                return None

            df = fetch(ticker, tf_key, provider=provider)
            if len(df) < 30:
                return None
            result = scorer(df)
            if result["score"] < min_score:
                return None
            return {
                "ticker": ticker,
                "score": result["score"],
                "last_close": result["last_close"],
                "volume_ratio": round(result["volume_ratio"], 2),
                "rsi": round(result["rsi"], 1),
                "days_until_earnings": days_to_er,
                "reasons": " | ".join(result["reasons"]),
                "provider": effective_provider,
            }
        except Exception as e:
            print(f"[skip] {ticker}: {e}")
            return None

    rows: list[dict] = []
    total = len(tickers)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_score_one, t): t for t in tickers}
        for fut in as_completed(futures):
            row = fut.result()
            if row is not None:
                rows.append(row)
            done += 1
            if progress is not None:
                progress(done, total)

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
