"""Options flow scanner.

Detects unusual options activity that often precedes large price moves.
Institutional traders frequently telegraph their positioning through the
options market 1–3 days before a move shows up in price/volume.

What we look for:
  - Large single-order call/put sweeps (market orders that sweep multiple exchanges)
  - Out-of-the-money options with high volume vs open interest (OI) ratio
  - Volume spikes: options volume >> 20-day average options volume
  - Unusual put/call ratio skew (heavy call buying = bullish, heavy puts = bearish)

Data source policy:
  Options data is independent of the OHLCV provider. Use ``source`` to choose:
    - ``auto``          : documented priority (Unusual Whales → Tradier → Yahoo)
    - ``unusual_whales``: Unusual Whales API only (requires UNUSUAL_WHALES_API_KEY)
    - ``tradier``       : Tradier API only (requires TRADIER_API_KEY)
    - ``yahoo``         : yfinance options chains only

  When a specific source is selected, the scanner does NOT fall back to another
  source. Missing credentials for an explicitly selected paid source produce a
  clear ProviderCapabilityError / structured unavailable result.

  The default source is controlled by ``OPTIONS_DATA_SOURCE``; if unset, it is
  ``auto``. ``DATA_PROVIDER`` is never used for options data.
"""
from __future__ import annotations

import os
from datetime import datetime, date, timedelta

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

from tradex.data.fetcher import ProviderCapabilityError

load_dotenv()

UNUSUAL_WHALES_KEY = os.getenv("UNUSUAL_WHALES_API_KEY", "")
TRADIER_KEY        = os.getenv("TRADIER_API_KEY", "")

OPTIONS_DATA_SOURCE = os.getenv("OPTIONS_DATA_SOURCE", "auto").lower().strip()

_OPTIONS_SOURCES = {"auto", "unusual_whales", "tradier", "yahoo"}

# Volume/OI ratio above this = unusual activity worth flagging
VOL_OI_THRESHOLD = 3.0
# Options volume vs 20-day avg above this = volume spike
VOL_SPIKE_THRESHOLD = 2.5

_FLOW_COLUMNS = [
    "ticker", "source", "type", "side", "strike", "expiry", "premium",
    "volume", "open_interest", "vol_oi_ratio", "is_sweep", "sentiment",
    "timestamp", "last", "bid", "ask",
]


def _resolve_options_source(source: str | None) -> str:
    """Return a validated options source string."""
    s = (source or OPTIONS_DATA_SOURCE).lower().strip()
    if s not in _OPTIONS_SOURCES:
        raise ProviderCapabilityError(
            f"Unknown options source '{source}'; supported: {', '.join(sorted(_OPTIONS_SOURCES))}"
        )
    return s


def _empty_flow(ticker: str, source: str) -> pd.DataFrame:
    """Return an empty flow DataFrame that still carries the requested source."""
    df = pd.DataFrame(columns=_FLOW_COLUMNS)
    df["ticker"] = pd.Series(dtype="object")
    df["source"] = pd.Series(dtype="object")
    if not df.empty:
        df["ticker"] = ticker
        df["source"] = source
    return df


# ── Unusual Whales ────────────────────────────────────────────────────────────
def _fetch_unusual_whales_flow(ticker: str, limit: int = 20) -> list[dict]:
    """
    Fetch recent options flow for a ticker from Unusual Whales.
    Returns list of flow records, newest first.
    Docs: https://unusualwhales.com/api
    """
    if not UNUSUAL_WHALES_KEY:
        return []
    try:
        url = f"https://api.unusualwhales.com/api/stock/{ticker}/options-flow"
        headers = {"Authorization": f"Bearer {UNUSUAL_WHALES_KEY}"}
        resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        return data
    except Exception:
        return []


def _parse_whales_flow(records: list[dict], ticker: str) -> pd.DataFrame:
    if not records:
        return _empty_flow(ticker, "unusual_whales")
    rows = []
    for r in records:
        rows.append({
            "ticker":      ticker,
            "source":      "unusual_whales",
            "type":        r.get("put_call", "").upper(),       # CALL / PUT
            "side":        r.get("side", ""),                   # ask / bid (sweep indicator)
            "strike":      r.get("strike_price"),
            "expiry":      r.get("expiry_date"),
            "premium":     r.get("premium"),                    # total $ value
            "volume":      r.get("volume"),
            "open_interest": r.get("open_interest"),
            "vol_oi_ratio": round(
                r.get("volume", 0) / max(r.get("open_interest", 1), 1), 2
            ),
            "is_sweep":    r.get("is_sweep", False),
            "sentiment":   r.get("sentiment", ""),
            "timestamp":   r.get("created_at", ""),
            "last":        None,
            "bid":         None,
            "ask":         None,
        })
    return pd.DataFrame(rows)


# ── Tradier ───────────────────────────────────────────────────────────────────
def _fetch_tradier_chain(ticker: str) -> pd.DataFrame:
    """
    Fetch options chain from Tradier for the nearest expiry.
    Free with a Tradier brokerage account.
    Docs: https://documentation.tradier.com/brokerage-api/markets/get-options-chains
    """
    if not TRADIER_KEY:
        return _empty_flow(ticker, "tradier")
    try:
        # Get nearest expiration
        exp_url = "https://api.tradier.com/v1/markets/options/expirations"
        headers = {
            "Authorization": f"Bearer {TRADIER_KEY}",
            "Accept": "application/json",
        }
        exp_resp = requests.get(exp_url, headers=headers,
                                params={"symbol": ticker, "includeAllRoots": True}, timeout=10)
        if exp_resp.status_code != 200:
            return _empty_flow(ticker, "tradier")
        expirations = exp_resp.json().get("expirations", {}).get("date", [])
        if not expirations:
            return _empty_flow(ticker, "tradier")
        nearest_exp = expirations[0] if isinstance(expirations, list) else expirations

        # Get chain for that expiry
        chain_url = "https://api.tradier.com/v1/markets/options/chains"
        chain_resp = requests.get(chain_url, headers=headers,
                                  params={"symbol": ticker, "expiration": nearest_exp,
                                          "greeks": False}, timeout=10)
        if chain_resp.status_code != 200:
            return _empty_flow(ticker, "tradier")
        options = chain_resp.json().get("options", {}).get("option", [])
        if not options:
            return _empty_flow(ticker, "tradier")

        df = pd.DataFrame(options)
        df["ticker"] = ticker
        df["source"] = "tradier"
        df["vol_oi_ratio"] = (df["volume"] / df["open_interest"].clip(lower=1)).round(2)
        df["is_sweep"] = False
        df["sentiment"] = ""
        df["timestamp"] = ""
        df["premium"] = None
        return df[["ticker", "source", "option_type", "strike", "expiration_date",
                   "premium", "volume", "open_interest", "vol_oi_ratio", "is_sweep",
                   "sentiment", "timestamp", "last", "bid", "ask"]].rename(
            columns={"option_type": "type", "expiration_date": "expiry"}
        )
    except Exception:
        return _empty_flow(ticker, "tradier")


# ── yfinance ──────────────────────────────────────────────────────────────────
def _fetch_yf_chain(ticker: str) -> pd.DataFrame:
    """
    yfinance options chain — free but delayed, no sweep/flow data.
    Good for vol/OI ratio anomalies on the nearest expiry.
    """
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            return _empty_flow(ticker, "yahoo")
        expiry = exps[0]
        chain = tk.option_chain(expiry)  # nearest expiry
        calls = chain.calls.copy()
        calls["type"] = "CALL"
        puts  = chain.puts.copy()
        puts["type"]  = "PUT"
        df = pd.concat([calls, puts], ignore_index=True)
        df["ticker"] = ticker
        df["source"] = "yahoo"
        df["expiry"] = expiry
        df["vol_oi_ratio"] = (df["volume"].fillna(0) / df["openInterest"].clip(lower=1)).round(2)
        df["is_sweep"] = False
        df["sentiment"] = ""
        df["timestamp"] = ""
        df["premium"] = None
        df["side"] = ""
        df["last"] = df["lastPrice"]
        return df[["ticker", "source", "type", "side", "strike",
                   "expiry", "premium", "volume", "openInterest",
                   "vol_oi_ratio", "is_sweep", "sentiment", "timestamp",
                   "last", "bid", "ask"]].rename(
            columns={"openInterest": "open_interest"}
        )
    except Exception:
        return _empty_flow(ticker, "yahoo")


# ── public API ────────────────────────────────────────────────────────────────
def get_flow(ticker: str, source: str | None = None) -> pd.DataFrame:
    """
    Get options flow / chain data for ``ticker`` from an explicit source.

    Args:
        source: ``auto`` | ``unusual_whales`` | ``tradier`` | ``yahoo``.
                Defaults to ``OPTIONS_DATA_SOURCE`` or ``auto``.

    ``auto`` follows the documented priority: Unusual Whales (if configured),
    then Tradier (if configured), then yfinance.

    An explicit paid source does not fall back when credentials are missing or
    the request fails. Missing credentials raise ProviderCapabilityError so the
    caller can surface a clear message instead of silently switching sources.
    """
    src = _resolve_options_source(source)

    if src == "unusual_whales":
        if not UNUSUAL_WHALES_KEY:
            raise ProviderCapabilityError(
                "Unusual Whales source selected but UNUSUAL_WHALES_API_KEY is not configured"
            )
        records = _fetch_unusual_whales_flow(ticker)
        return _parse_whales_flow(records, ticker)

    if src == "tradier":
        if not TRADIER_KEY:
            raise ProviderCapabilityError(
                "Tradier source selected but TRADIER_API_KEY is not configured"
            )
        return _fetch_tradier_chain(ticker)

    if src == "yahoo":
        return _fetch_yf_chain(ticker)

    if src == "auto":
        if UNUSUAL_WHALES_KEY:
            records = _fetch_unusual_whales_flow(ticker)
            df = _parse_whales_flow(records, ticker)
            if not df.empty:
                return df

        if TRADIER_KEY:
            df = _fetch_tradier_chain(ticker)
            if not df.empty:
                return df

        return _fetch_yf_chain(ticker)

    # Should be unreachable due to _resolve_options_source validation.
    raise ProviderCapabilityError(f"Unsupported options source '{src}'")


def scan_unusual_flow(
    tickers: list[str],
    min_vol_oi: float = VOL_OI_THRESHOLD,
    source: str | None = None,
) -> pd.DataFrame:
    """
    Scan a watchlist for unusual options activity.
    Returns contracts where volume/OI ratio exceeds threshold, ranked by ratio.

    ``source`` is passed to ``get_flow`` for every ticker.
    """
    all_rows = []
    for ticker in tickers:
        try:
            df = get_flow(ticker, source=source)
            if df.empty:
                continue
            unusual = df[df["vol_oi_ratio"] >= min_vol_oi].copy()
            if not unusual.empty:
                all_rows.append(unusual)
        except ProviderCapabilityError as e:
            # Surface a clear source/capability error without falling back.
            print(f"[options] {ticker}: {e}")
        except Exception as e:
            print(f"[options] {ticker}: {e}")

    if not all_rows:
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)
    return combined.sort_values("vol_oi_ratio", ascending=False).reset_index(drop=True)


def get_put_call_sentiment(ticker: str, source: str | None = None) -> dict:
    """
    Compute put/call ratio and overall options sentiment for a ticker.
    >1.0 ratio = more puts = bearish, <0.7 = more calls = bullish.

    ``source`` is passed to ``get_flow``. If the source is unavailable or
    credentials are missing, a structured unavailable result is returned.
    """
    try:
        df = get_flow(ticker, source=source)
    except ProviderCapabilityError as e:
        return {
            "ticker": ticker,
            "put_call_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "sentiment": "unavailable",
            "data_source": _resolve_options_source(source),
            "error": str(e),
        }

    if df.empty:
        return {
            "ticker": ticker,
            "put_call_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "sentiment": "unknown",
            "data_source": _resolve_options_source(source),
        }

    call_vol = df[df["type"].str.upper() == "CALL"]["volume"].sum()
    put_vol  = df[df["type"].str.upper() == "PUT"]["volume"].sum()

    if call_vol == 0:
        ratio = float("inf")
    else:
        ratio = round(put_vol / call_vol, 2)

    if ratio < 0.7:
        sentiment = "bullish"
    elif ratio > 1.2:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "ticker":          ticker,
        "put_call_ratio":  ratio,
        "call_volume":     int(call_vol),
        "put_volume":      int(put_vol),
        "sentiment":       sentiment,
        "data_source":     df["source"].iloc[0] if "source" in df.columns else "unknown",
    }
