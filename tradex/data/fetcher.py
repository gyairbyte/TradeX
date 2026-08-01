"""
OHLCV data fetcher supporting four providers:
  - yahoo   : free, no setup, 15-min delayed intraday (default)
  - alpaca  : free real-time US stocks (requires ALPACA_API_KEY + ALPACA_SECRET_KEY in .env)
  - ibkr    : real-time global markets (requires running TWS/IB Gateway locally)
  - schwab  : Charles Schwab API — replaced TD Ameritrade in Sept 2024
              (requires Schwab brokerage account + OAuth app at developer.schwab.com)

Set the provider via the DATA_PROVIDER env var or pass it explicitly to fetch().
"""
import json
import os
import threading
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# ── timeframe presets ────────────────────────────────────────────────────────
# Each provider maps these to its own param names internally.
TIMEFRAMES = {
    "intraday": {"period": "5d",  "interval": "5m"},
    "short":    {"period": "60d", "interval": "1d"},
    "long":     {"period": "2y",  "interval": "1wk"},
}

DEFAULT_PROVIDER = os.getenv("DATA_PROVIDER", "yahoo")


def normalize_yahoo_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance MultiIndex columns and normalize names to lowercase.

    yfinance >= 0.2.x can return either single-level columns ("Open", "Close",
    ...) or a MultiIndex whose first level is the field name and whose second
    level is the ticker symbol. This helper produces a single-level lowercase
    column index regardless of the input shape.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return df


# ── Yahoo Finance ─────────────────────────────────────────────────────────────
def _fetch_yahoo(ticker: str, timeframe: str) -> pd.DataFrame:
    tf = TIMEFRAMES[timeframe]
    df = yf.download(
        ticker,
        period=tf["period"],
        interval=tf["interval"],
        progress=False,
        auto_adjust=True,
    )
    return normalize_yahoo_columns(df).dropna()


# ── Alpaca ────────────────────────────────────────────────────────────────────
# Requires: pip install alpaca-py
# Env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY
# Free tier gives real-time IEX feed; paid gives SIP (full NBBO).
_ALPACA_INTERVAL_MAP = {
    "intraday": "5Min",
    "short":    "1Day",
    "long":     "1Week",
}
_ALPACA_LIMIT_MAP = {
    "intraday": 1000,   # ~5 trading days of 5m bars
    "short":    60,
    "long":     104,    # 2 years of weekly bars
}

def _fetch_alpaca(ticker: str, timeframe: str) -> pd.DataFrame:
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    except ImportError:
        raise ImportError("Install alpaca-py: pip install alpaca-py")

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise EnvironmentError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    client = StockHistoricalDataClient(api_key, secret_key)

    tf_str = _ALPACA_INTERVAL_MAP[timeframe]
    tf_map = {
        "5Min":  TimeFrame(5, TimeFrameUnit.Minute),
        "1Day":  TimeFrame(1, TimeFrameUnit.Day),
        "1Week": TimeFrame(1, TimeFrameUnit.Week),
    }

    from datetime import datetime, timedelta
    lookback_days = {"intraday": 7, "short": 90, "long": 730}
    start = datetime.now() - timedelta(days=lookback_days[timeframe])

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=tf_map[tf_str],
        start=start,
        limit=_ALPACA_LIMIT_MAP[timeframe],
    )
    bars = client.get_stock_bars(request).df

    # Alpaca returns a MultiIndex (symbol, timestamp) — drop symbol level
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker, level="symbol")

    bars.index.name = "datetime"
    bars = bars.rename(columns={"open": "open", "high": "high", "low": "low",
                                 "close": "close", "volume": "volume"})
    return bars[["open", "high", "low", "close", "volume"]].dropna()


# ── Interactive Brokers ───────────────────────────────────────────────────────
# Requires: pip install ib_insync  AND  TWS or IB Gateway running locally
# TWS/Gateway must have API connections enabled (Edit > Global Config > API > Enable)
# Default connection: host=127.0.0.1, port=7497 (paper) or 7496 (live)
_IBKR_DURATION_MAP = {
    "intraday": ("5 D", "5 mins"),
    "short":    ("60 D", "1 day"),
    "long":     ("2 Y",  "1 week"),
}

def _fetch_ibkr(ticker: str, timeframe: str) -> pd.DataFrame:
    try:
        from ib_insync import IB, Stock, util
    except ImportError:
        raise ImportError("Install ib_insync: pip install ib_insync")

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "7497"))   # 7497 = paper, 7496 = live
    client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        contract = Stock(ticker, "SMART", "USD")
        duration, bar_size = _IBKR_DURATION_MAP[timeframe]
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        df = util.df(bars).set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={"open": "open", "high": "high", "low": "low",
                                  "close": "close", "volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]].dropna()
    finally:
        ib.disconnect()


# ── Charles Schwab (replaced TD Ameritrade Sept 2024) ────────────────────────
# Requires: pip install schwab-py
# Setup:
#   1. Create a Schwab brokerage account at schwab.com
#   2. Register an app at developer.schwab.com — get SCHWAB_APP_KEY + SCHWAB_APP_SECRET
#   3. Run scripts/schwab_oauth.py once to generate the OAuth token file at
#      SCHWAB_TOKEN_PATH (default: ~/.tradex_schwab_token.json). After that,
#      this fetcher just reads the token; schwab-py refreshes it automatically.
# Note: TD Ameritrade API (tda-api library) is fully dead — do not use it.
from datetime import datetime, timedelta, timezone

def _repo_root() -> Path | None:
    """Return the repository root if this file is inside a git checkout, else None."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").is_dir():
            return parent
    return None


def _assert_token_path_outside_repo(token_path: str) -> None:
    """Refuse to read or write a Schwab token file that lives inside the repo."""
    repo_root = _repo_root()
    if repo_root is None:
        return
    resolved = Path(token_path).expanduser().resolve()
    try:
        if resolved.is_relative_to(repo_root):
            raise ValueError(
                f"Schwab token path must not be inside the repository: {resolved}\n"
                f"Set SCHWAB_TOKEN_PATH to a location outside {repo_root}, "
                "e.g. ~/.tradex_schwab_token.json"
            )
    except ValueError:
        raise


# Map each timeframe to (client method name, lookback timedelta).
# Lookbacks roughly match what other providers return for the same timeframe.
_SCHWAB_TIMEFRAMES = {
    "intraday": ("get_price_history_every_five_minutes", timedelta(days=5)),
    "short":    ("get_price_history_every_day",          timedelta(days=120)),
    "long":     ("get_price_history_every_week",         timedelta(days=730)),
}

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


# Cache the authenticated client across calls — fetching a watchlist would
# otherwise reload + decrypt the token file once per ticker.
_SCHWAB_CLIENT = None
_SCHWAB_LOCK = threading.Lock()


def _normalize_schwab_candles(candles: list[dict]) -> pd.DataFrame:
    """Convert Schwab price-history candles into the canonical OHLCV DataFrame.

    Schwab candle JSON contains: open, high, low, close, volume, datetime (epoch ms).
    Returns a sorted, de-duplicated, UTC timezone-aware DataFrame with columns
    open, high, low, close, volume. Rows with missing or invalid OHLCV data are
    dropped. Duplicate timestamps keep the last occurrence.
    """
    if not candles:
        return pd.DataFrame(
            columns=_OHLCV_COLUMNS,
            index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
        )

    df = pd.DataFrame(candles)
    df.columns = [c.lower() for c in df.columns]

    if "datetime" not in df.columns:
        return pd.DataFrame(
            columns=_OHLCV_COLUMNS,
            index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
        )

    # Coerce epoch-ms timestamps; invalid values become NaT and are dropped.
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True, errors="coerce")
    df = df.dropna(subset=["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in _OHLCV_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_OHLCV_COLUMNS]

    for col in _OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows that are missing any OHLCV field. Volume of 0 is valid; NaN is not.
    return df.dropna(subset=_OHLCV_COLUMNS)


def _fetch_schwab(ticker: str, timeframe: str) -> pd.DataFrame:
    """Fetch canonical OHLCV data from the Schwab Market Data API.

    Raises:
        ImportError:            schwab-py is not installed.
        EnvironmentError:       SCHWAB_APP_KEY or SCHWAB_APP_SECRET missing.
        FileNotFoundError:      The OAuth token file does not exist.
        ValueError:             The token path is inside the repo or timeframe unsupported.
        RuntimeError:            The Schwab API request failed.
        ValueError:             The response was not valid JSON.
    """
    try:
        from schwab.auth import client_from_token_file
    except ImportError as e:
        raise ImportError(
            "Install schwab-py to use the Schwab provider: "
            "uv pip install -e \".[schwab]\""
        ) from e

    app_key = os.getenv("SCHWAB_APP_KEY", "").strip()
    app_secret = os.getenv("SCHWAB_APP_SECRET", "").strip()
    token_path = os.path.expanduser(
        os.getenv("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json")
    )

    if not app_key or not app_secret:
        raise EnvironmentError("SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in .env")

    _assert_token_path_outside_repo(token_path)

    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"Schwab OAuth token not found at {token_path}. "
            "Run `python scripts/schwab_oauth.py` once to generate it."
        )

    global _SCHWAB_CLIENT
    with _SCHWAB_LOCK:
        if _SCHWAB_CLIENT is None:
            _SCHWAB_CLIENT = client_from_token_file(
                token_path=token_path,
                api_key=app_key,
                app_secret=app_secret,
            )

    client = _SCHWAB_CLIENT

    if timeframe not in _SCHWAB_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe for schwab: {timeframe}")
    method_name, lookback = _SCHWAB_TIMEFRAMES[timeframe]

    end = datetime.now(timezone.utc)
    start = end - lookback

    resp = getattr(client, method_name)(
        ticker,
        start_datetime=start,
        end_datetime=end,
        need_extended_hours_data=False,
    )

    try:
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"Schwab price-history request failed for {ticker} ({timeframe}): {e}"
        ) from e

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Schwab returned non-JSON price-history response for {ticker}: {e}"
        ) from e

    candles = data.get("candles", []) if isinstance(data, dict) else []
    return _normalize_schwab_candles(candles)


# ── Public API ────────────────────────────────────────────────────────────────
_PROVIDERS = {
    "yahoo":  _fetch_yahoo,
    "alpaca": _fetch_alpaca,
    "ibkr":   _fetch_ibkr,
    "schwab": _fetch_schwab,
}


def fetch(ticker: str, timeframe: str, provider: str | None = None) -> pd.DataFrame:
    """
    Fetch OHLCV data for a ticker.

    Args:
        ticker:    e.g. "NVDA"
        timeframe: "intraday" | "short" | "long"
        provider:  "yahoo" | "alpaca" | "ibkr" | "schwab" (defaults to DATA_PROVIDER env var, then "yahoo")
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {list(TIMEFRAMES)}")

    p = (provider or DEFAULT_PROVIDER).lower()
    if p not in _PROVIDERS:
        raise ValueError(f"provider must be one of {list(_PROVIDERS)}")

    return _PROVIDERS[p](ticker, timeframe)


def fetch_multi(tickers: list[str], timeframe: str, provider: str | None = None) -> dict[str, pd.DataFrame]:
    """Fetch data for multiple tickers; skips any that fail."""
    result = {}
    for t in tickers:
        try:
            result[t] = fetch(t, timeframe, provider=provider)
        except Exception as e:
            print(f"[skip] {t}: {e}")
    return result
