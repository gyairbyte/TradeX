"""
Pre-market gap scanner.

Runs before market open (typically 7–9:30am ET) and identifies stocks
that have gapped significantly from their previous close based on
pre-market trading data.

Gap logic:
  - Fetches the previous session's closing price (last daily bar)
  - Fetches the latest pre-market quote (1m bars for today's pre-market session)
  - Computes gap % = (pre_market_last - prev_close) / prev_close * 100
  - Classifies direction, magnitude, and flags potential fill vs continuation

Gap tiers:
  Massive  : abs(gap) >= 8%  — earnings, major news, M&A
  Large    : abs(gap) >= 4%  — sector move, analyst action
  Moderate : abs(gap) >= 2%  — normal pre-market activity worth watching
  Small    : abs(gap) < 2%   — noise, filtered out by default

Data source: yfinance pre-market data (free, ~15min delayed).
For real-time pre-market quotes, use Alpaca or Polygon.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import yfinance as yf


GAP_TIERS = {
    "massive":  8.0,
    "large":    4.0,
    "moderate": 2.0,
}

DEFAULT_MIN_GAP = 2.0  # % — filter out noise below this


def _get_prev_close(ticker: str) -> float | None:
    """Fetch the most recent regular-session closing price."""
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        return float(df["close"].iloc[-1])
    except Exception:
        return None


def _get_premarket_price(ticker: str) -> float | None:
    """
    Fetch the latest pre-market price using 1-minute bars for today.
    yfinance returns pre/post market data when prePost=True.
    Returns None if no pre-market activity found.
    """
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="1d", interval="1m", prepost=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        now_utc = datetime.now(timezone.utc)
        # Pre-market is before 9:30am ET (13:30 UTC)
        # Filter to bars before market open
        df.index = pd.to_datetime(df.index, utc=True)
        premarket = df[df.index.hour < 13]  # before 1pm UTC ≈ 9am ET
        if premarket.empty:
            return None
        return float(premarket["close"].iloc[-1])
    except Exception:
        return None


def _classify_gap(gap_pct: float) -> tuple[str, str]:
    """Returns (tier, direction) for a given gap percentage."""
    direction = "up" if gap_pct > 0 else "down"
    abs_gap = abs(gap_pct)
    if abs_gap >= GAP_TIERS["massive"]:
        tier = "massive"
    elif abs_gap >= GAP_TIERS["large"]:
        tier = "large"
    elif abs_gap >= GAP_TIERS["moderate"]:
        tier = "moderate"
    else:
        tier = "small"
    return tier, direction


def _gap_note(gap_pct: float, tier: str, direction: str) -> str:
    """Plain-English context for the gap."""
    if tier == "massive":
        return f"Massive {direction} gap — likely earnings, M&A, or major news. High volatility expected at open."
    if tier == "large" and direction == "up":
        return "Large gap up — watch for opening drive continuation vs. fade back into gap."
    if tier == "large" and direction == "down":
        return "Large gap down — watch for gap fill attempt or continuation of selling pressure."
    if direction == "up":
        return "Moderate gap up — bullish pre-market sentiment. Monitor volume at open."
    return "Moderate gap down — bearish pre-market. Watch for stabilization or further decline."


def scan_gaps(
    tickers: list[str],
    min_gap_pct: float = DEFAULT_MIN_GAP,
) -> pd.DataFrame:
    """
    Scan a watchlist for pre-market gaps above the threshold.

    Returns a DataFrame sorted by absolute gap size, largest first.
    Best run between 7am–9:25am ET before market open.
    """
    rows = []
    for ticker in tickers:
        prev_close = _get_prev_close(ticker)
        if prev_close is None or prev_close == 0:
            continue

        pre_price = _get_premarket_price(ticker)
        if pre_price is None:
            continue

        gap_pct = (pre_price - prev_close) / prev_close * 100
        if abs(gap_pct) < min_gap_pct:
            continue

        tier, direction = _classify_gap(gap_pct)
        rows.append({
            "ticker":      ticker,
            "prev_close":  round(prev_close, 2),
            "pre_market":  round(pre_price, 2),
            "gap_pct":     round(gap_pct, 2),
            "direction":   direction,
            "tier":        tier,
            "note":        _gap_note(gap_pct, tier, direction),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["abs_gap"] = df["gap_pct"].abs()
    return df.sort_values("abs_gap", ascending=False).drop(columns="abs_gap").reset_index(drop=True)


def run_gap_alerts(tickers: list[str], min_gap_pct: float = 4.0) -> pd.DataFrame:
    """
    Scan gaps and fire alerts for large/massive ones.
    Intended to be called by the watcher at ~8am ET.
    """
    from tradex.alerts.notifier import alert_gap
    gaps = scan_gaps(tickers, min_gap_pct=min_gap_pct)
    for _, row in gaps.iterrows():
        if row["tier"] in ("large", "massive"):
            alert_gap(
                ticker=row["ticker"],
                gap_pct=row["gap_pct"],
                direction=row["direction"],
                prev_close=row["prev_close"],
                pre_market=row["pre_market"],
            )
    return gaps
