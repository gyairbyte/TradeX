"""Date-ranged daily OHLCV history abstraction.

This is separate from the central timeframe-based fetcher because some consumers
need an explicit calendar-date window rather than a named preset (intraday/short/long).

Supported providers:
  - yahoo   : free, no setup
  - schwab  : Schwab Market Data API (requires schwab-py and OAuth token)

Alpaca and IBKR are not yet supported for explicit date-ranged daily history; they
raise ProviderCapabilityError so callers do not silently fall back to Yahoo.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timezone

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import (
    DEFAULT_PROVIDER,
    ProviderCapabilityError,
    _OHLCV_COLUMNS,
    _get_schwab_client,
    _normalize_schwab_candles,
    normalize_yahoo_columns,
)


_HISTORY_PROVIDERS = {"yahoo", "schwab"}


def _resolve_history_provider(provider: str | None) -> str:
    p = (provider or DEFAULT_PROVIDER).lower()
    if p not in {"yahoo", "schwab", "alpaca", "ibkr"}:
        raise ValueError(f"provider must be one of yahoo, schwab, alpaca, ibkr; got {p}")
    if p not in _HISTORY_PROVIDERS:
        raise ProviderCapabilityError(
            f"Provider '{p}' does not support date-ranged daily OHLCV history"
        )
    return p


def _as_date(d: date | datetime) -> date:
    return d.date() if isinstance(d, datetime) else d


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        columns=_OHLCV_COLUMNS,
        index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
    )


def _canonicalize_history(df: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted, de-duplicated, UTC-indexed DataFrame with canonical columns."""
    if df.empty:
        return _empty_history()

    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "datetime"

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in _OHLCV_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_OHLCV_COLUMNS]
    for col in _OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows that have no OHLCV data at all, but keep rows where only the
    # close is missing so downstream callers (e.g. outcome tracker) can count
    # the session and fall back to the next valid close.
    return df.dropna(how="all")


def _fetch_yahoo_daily(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch daily bars from Yahoo Finance for an inclusive start/end range.

    yfinance's ``end`` argument is exclusive, so we pass ``end_date + 1 day``
    to include the requested end date.
    """
    end_exclusive = end_date + pd.Timedelta(days=1)
    df = yf.download(
        ticker,
        start=start_date.isoformat(),
        end=end_exclusive.isoformat(),
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        return _empty_history()
    df = normalize_yahoo_columns(df)
    return _canonicalize_history(df)


def _fetch_schwab_daily(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch daily bars from Schwab for the requested inclusive date range."""
    client = _get_schwab_client()

    start_dt = datetime.combine(start_date, time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time(23, 59, 59), tzinfo=timezone.utc)

    resp = client.get_price_history_every_day(
        ticker,
        start_datetime=start_dt,
        end_datetime=end_dt,
        need_extended_hours_data=False,
    )

    status = getattr(resp, "status_code", "unknown")
    try:
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        raise RuntimeError(
            f"Schwab daily history request failed for {ticker} "
            f"(HTTP {status})."
        ) from None

    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise ValueError(f"Schwab returned non-JSON daily history for {ticker}") from None

    candles = data.get("candles", []) if isinstance(data, dict) else []
    return _normalize_schwab_candles(candles)


def fetch_daily_history(
    ticker: str,
    start: date | datetime,
    end: date | datetime,
    provider: str | None = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV bars for ``ticker`` from ``start`` through ``end`` (inclusive).

    Args:
        ticker: Ticker symbol.
        start: First calendar date to include.
        end: Last calendar date to include.
        provider: "yahoo", "schwab", or None to use ``DATA_PROVIDER``/``yahoo``.

    Returns:
        Canonical DataFrame with columns ``open``, ``high``, ``low``, ``close``,
        ``volume`` and a UTC ``datetime`` index.

    Raises:
        ValueError: For an invalid provider name.
        ProviderCapabilityError: For providers that do not support this call.
        RuntimeError: For a failed provider request.
    """
    start_date = _as_date(start)
    end_date = _as_date(end)

    if end_date < start_date:
        return _empty_history()

    p = _resolve_history_provider(provider)
    if p == "yahoo":
        return _fetch_yahoo_daily(ticker, start_date, end_date)
    if p == "schwab":
        return _fetch_schwab_daily(ticker, start_date, end_date)
    # Should be unreachable because _resolve_history_provider raises.
    raise ProviderCapabilityError(
        f"Provider '{p}' does not support date-ranged daily OHLCV history"
    )
