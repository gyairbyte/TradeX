"""
Runs all three signal scorers across a watchlist and returns ranked results.
"""
import pandas as pd
from tradex.data.fetcher import fetch
from tradex.signals import intraday, short_term, long_term


SIGNAL_MAP = {
    "intraday": (intraday.score, "intraday"),
    "short":    (short_term.score, "short"),
    "long":     (long_term.score, "long"),
}


def run(tickers: list[str], timeframe: str = "intraday", min_score: int = 40) -> pd.DataFrame:
    scorer, tf_key = SIGNAL_MAP[timeframe]
    rows = []

    for ticker in tickers:
        try:
            df = fetch(ticker, tf_key)
            if len(df) < 30:
                continue
            result = scorer(df)
            if result["score"] >= min_score:
                rows.append({
                    "ticker": ticker,
                    "score": result["score"],
                    "last_close": result["last_close"],
                    "volume_ratio": round(result["volume_ratio"], 2),
                    "rsi": round(result["rsi"], 1),
                    "reasons": " | ".join(result["reasons"]),
                })
        except Exception as e:
            print(f"[skip] {ticker}: {e}")

    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
