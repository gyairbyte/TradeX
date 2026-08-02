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

from datetime import UTC, date, datetime, time, timezone

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import DEFAULT_PROVIDER, ProviderCapabilityError
from tradex.data.history import fetch_daily_history
from tradex.market import (
    MARKET_TIMEZONE,
    get_market_session,
    is_trading_day,
    next_trading_session,
    normalize_market_datetime,
    previous_trading_session,
)


GAP_TIERS = {
    "massive":  8.0,
    "large":    4.0,
    "moderate": 2.0,
}

DEFAULT_MIN_GAP = 2.0  # % — filter out noise below this


def _get_prev_close(
    ticker: str,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> float | None:
    """Fetch the most recent regular-session closing price before ``as_of``.

    The previous session is resolved through the NYSE calendar so weekends,
    holidays, and early closes are handled correctly regardless of the host
    timezone.
    """
    as_of = as_of or datetime.now(UTC)
    # ``normalize_market_datetime`` raises ValueError for naive datetimes before
    # any provider call or broad exception handler can swallow it.
    ny_as_of = normalize_market_datetime(as_of)
    try:
        current_day = next_trading_session(ny_as_of).session_date
        prev = previous_trading_session(current_day)
        df = fetch_daily_history(
            ticker,
            prev.session_date,
            prev.session_date,
            provider=provider,
        )
        if df.empty or "close" not in df.columns:
            return None
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        # Daily history bars represent a session date by their UTC calendar date.
        mask = idx.date == prev.session_date
        closes = df.loc[mask, "close"].dropna()
        if closes.empty:
            return None
        return float(closes.iloc[-1])
    except ProviderCapabilityError:
        raise
    except Exception:
        return None


def get_premarket_price(
    ticker: str,
    provider: str | None = None,
    as_of: datetime | None = None,
) -> float | None:
    """Fetch the latest pre-market/extended-hours price before the session open.

    Uses the NYSE calendar to identify the intended session date, then selects
    1-minute Yahoo bars from 04:00 AM ET through (but not including) the actual
    regular-session open on that date. Bars from the previous day's after-hours,
    regular-session, or post-market periods are excluded, as are bars after ``as_of``.
    """
    as_of = as_of or datetime.now(UTC)
    # ``normalize_market_datetime`` raises ValueError for naive datetimes.
    ny_as_of = normalize_market_datetime(as_of)

    p = (provider or DEFAULT_PROVIDER).lower()
    if p != "yahoo":
        raise ProviderCapabilityError(
            f"Provider '{p}' does not yet support pre-market/extended-hours quotes"
        )

    session_date = ny_as_of.date()
    if not is_trading_day(session_date):
        return None

    session = get_market_session(session_date)
    if session is None:
        return None

    premarket_start = datetime.combine(
        session_date, time(4, 0), tzinfo=MARKET_TIMEZONE
    )

    # The pre-market window ends at the earlier of ``as_of`` and the regular open.
    window_end = min(ny_as_of, session.opens_at)
    if window_end <= premarket_start:
        return None

    try:
        tk = yf.Ticker(ticker)
        # Request enough 1-minute history to cover a weekend gap.
        df = tk.history(period="5d", interval="1m", prepost=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df.index = pd.to_datetime(df.index, utc=True)
        ny_index = df.index.tz_convert(MARKET_TIMEZONE)
        mask = (
            (ny_index.date == session_date)
            & (ny_index >= premarket_start)
            & (ny_index < session.opens_at)
            & (ny_index <= ny_as_of)
        )
        premarket = df.loc[mask]
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
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Scan a watchlist for pre-market gaps above the threshold.

    ``provider`` is passed to the daily-history abstraction for the previous
    close and to the pre-market quote source. When None, ``DATA_PROVIDER`` is
    used. ``as_of`` defaults to the current UTC time and anchors the calendar
    calculations to the intended NYSE session date.

    Returns a DataFrame sorted by absolute gap size, largest first.
    Best run between 7am–9:25am ET before market open.
    """
    rows = []
    for ticker in tickers:
        try:
            prev_close = _get_prev_close(ticker, provider=provider, as_of=as_of)
            if prev_close is None or prev_close == 0:
                continue

            pre_price = get_premarket_price(ticker, provider=provider, as_of=as_of)
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
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Scan gaps and fire alerts for large/massive ones.

    Intended to be called by the watcher at ~8am ET. Provider errors are
    surfaced safely so the watcher loop is not silently broken.
    """
    from tradex.alerts.notifier import alert_gap

    try:
        gaps = scan_gaps(tickers, min_gap_pct=min_gap_pct, provider=provider, as_of=as_of)
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
