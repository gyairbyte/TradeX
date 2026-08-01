"""Pre-market gap scanner.

Runs before market open (typically 7–9:30am ET) and identifies stocks
that have gapped significantly from their previous close based on
pre-market trading data.

Gap logic:
  - Fetches the previous session's closing price (last daily bar) using the
    date-ranged daily-history abstraction.
  - Fetches the latest pre-market quote via the appropriate source interface.
  - Computes gap % = (pre_market_last - prev_close) / prev_close * 100
  - Classifies direction, magnitude, and flags potential fill vs continuation

Gap tiers:
  Massive  : abs(gap) >= 8%  — earnings, major news, M&A
  Large    : abs(gap) >= 4%  — sector move, analyst action
  Moderate : abs(gap) >= 2%  — normal pre-market activity worth watching
  Small    : abs(gap) < 2%   — noise, filtered out by default

Data source policy:
  - Previous close follows the selected OHLCV provider through the daily-history
    abstraction (Yahoo, Schwab).
  - Extended-hours/pre-market quotes are currently only supported for Yahoo.
    Schwab and other providers raise ProviderCapabilityError rather than silently
    falling back to Yahoo.
  - Broad market-hours / exchange-calendar approximation remains under COR-005.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import DEFAULT_PROVIDER, ProviderCapabilityError
from tradex.data.history import fetch_daily_history


GAP_TIERS = {
    "massive":  8.0,
    "large":    4.0,
    "moderate": 2.0,
}

DEFAULT_MIN_GAP = 2.0  # % — filter out noise below this


def _get_prev_close(ticker: str, provider: str | None = None) -> float | None:
    """Fetch the most recent regular-session closing price from the selected provider."""
    try:
        end = date.today()
        start = end - pd.Timedelta(days=7)
        df = fetch_daily_history(ticker, start, end, provider=provider)
        if df.empty:
            return None
        return float(df["close"].iloc[-1])
    except ProviderCapabilityError:
        raise
    except Exception:
        return None


def get_premarket_price(ticker: str, provider: str | None = None) -> float | None:
    """Fetch the latest pre-market/extended-hours price.

    Yahoo uses 1-minute bars with pre/post-market data enabled and returns the
    last bar before 9:30am ET (13:30 UTC). Other providers raise a clear
    capability error rather than silently falling back to Yahoo.
    """
    p = (provider or DEFAULT_PROVIDER).lower()
    if p != "yahoo":
        raise ProviderCapabilityError(
            f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
        )

    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="1d", interval="1m", prepost=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df.index = pd.to_datetime(df.index, utc=True)
        # Approximate pre-market before 9:30am ET (13:30 UTC).
        # Full exchange-calendar handling belongs under COR-005.
        premarket = df[df.index.hour < 13]
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
    provider: str | None = None,
) -> pd.DataFrame:
    """Scan a watchlist for pre-market gaps above the threshold.

    ``provider`` is passed to the daily-history abstraction for the previous
    close and to the pre-market quote source. When None, ``DATA_PROVIDER`` is
    used.

    Returns a DataFrame sorted by absolute gap size, largest first.
    Best run between 7am–9:25am ET before market open.
    """
    rows = []
    for ticker in tickers:
        try:
            prev_close = _get_prev_close(ticker, provider=provider)
            if prev_close is None or prev_close == 0:
                continue

            pre_price = get_premarket_price(ticker, provider=provider)
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
        except ProviderCapabilityError:
            raise
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["abs_gap"] = df["gap_pct"].abs()
    return df.sort_values("abs_gap", ascending=False).drop(columns="abs_gap").reset_index(drop=True)


def run_gap_alerts(
    tickers: list[str],
    min_gap_pct: float = 4.0,
    provider: str | None = None,
) -> pd.DataFrame:
    """Scan gaps and fire alerts for large/massive ones.

    Intended to be called by the watcher at ~8am ET. Provider errors are
    surfaced safely so the watcher loop is not silently broken.
    """
    from tradex.alerts.notifier import alert_gap

    try:
        gaps = scan_gaps(tickers, min_gap_pct=min_gap_pct, provider=provider)
    except ProviderCapabilityError as e:
        print(f"[gap alert] {e}")
        return pd.DataFrame()

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
