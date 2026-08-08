"""Research-only Alpaca multi-symbol bars client for the INTRA-001B dataset build."""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _headers(api_key: str, secret_key: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
    }


def _token_hash(token: str | None) -> str:
    raw = "null" if token is None else str(token)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _token_sequence_hash(token_hashes: list[str]) -> str:
    return hashlib.sha256("".join(token_hashes).encode("utf-8")).hexdigest()


def _safe_error_class(status: int) -> str:
    if status == 429:
        return "http_429"
    if status >= 500:
        return f"http_{status}"
    if status == 400:
        return "http_400"
    if status == 401:
        return "http_401"
    if status == 403:
        return "http_403"
    if status != 200:
        return f"http_{status}"
    return "none"


def _retry_after_seconds(response: requests.Response, default: float) -> float:
    retry = response.headers.get("Retry-After") or response.headers.get("x-ratelimit-reset")
    if retry is None:
        return default
    try:
        value = float(retry)
        if value > 1_000_000_000:
            return max(0.0, value - time.time())
        return min(value, 30.0)
    except (TypeError, ValueError):
        return default


class DatasetAlpacaClient:
    """Minimal read-only client for Alpaca multi-symbol historical bars."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        market_data_host: str = "https://data.alpaca.markets",
        request_delay_seconds: float = 0.5,
        max_retries: int = 1,
        request_func: Callable[..., requests.Response] | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise OSError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured")
        self.api_key = api_key
        self.secret_key = secret_key
        self.market_data_host = market_data_host.rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.request_func = request_func or requests.get

    def _get(
        self,
        url: str,
        params: dict[str, Any],
        sleeper: Callable[[float], None] | None = None,
    ) -> tuple[requests.Response, float | None, int]:
        sleeper = sleeper or time.sleep
        retry_after: float | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.request_func(url, params=params, headers=_headers(self.api_key, self.secret_key), timeout=30)
            except (requests.Timeout, requests.ConnectionError):
                if attempt < self.max_retries:
                    sleeper(self.request_delay_seconds)
                    continue
                raise
            status = resp.status_code
            if (status == 429 or status >= 500) and attempt < self.max_retries:
                retry_after = _retry_after_seconds(resp, self.request_delay_seconds)
                sleeper(retry_after)
                continue
            sleeper(self.request_delay_seconds)
            return resp, retry_after, attempt + 1
        return resp, retry_after, attempt + 1  # type: ignore[possibly-undefined]

    def _normalize_bars(
        self,
        bars: list[dict[str, Any]],
    ) -> pd.DataFrame:
        if not bars:
            return pd.DataFrame(
                columns=_OHLCV_COLUMNS,
                index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
            )
        df = pd.DataFrame(bars)
        if "t" not in df.columns:
            return pd.DataFrame(
                columns=_OHLCV_COLUMNS,
                index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
            )
        df = df.rename(columns={"t": "datetime", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
        df = df.dropna(subset=["datetime"])
        df = df.set_index("datetime").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        for col in _OHLCV_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[_OHLCV_COLUMNS]
        for col in _OHLCV_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=_OHLCV_COLUMNS)

    def get_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
        *,
        feed: str,
        timeframe: str,
        adjustment: str,
        asof: str | None = None,
        sort: str = "asc",
        limit: int = 10000,
        sleeper: Callable[[float], None] | None = None,
    ) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
        """Fetch multi-symbol bars, returning per-symbol DataFrames and pagination metadata.

        Pagination metadata contains ``page_count``, ``next_page_token_present``,
        ``pagination_complete``, ``repeated_page_token``, ``pagination_cycle_detected``,
        per-page bar counts, and token hashes.
        """
        url = f"{self.market_data_host}/v2/stocks/bars"
        params: dict[str, Any] = {
            "symbols": ",".join(s.upper() for s in symbols),
            "timeframe": timeframe,
            "start": start_utc.isoformat().replace("+00:00", "Z"),
            "end": end_utc.isoformat().replace("+00:00", "Z"),
            "feed": feed,
            "adjustment": adjustment,
            "sort": sort,
            "limit": limit,
        }
        if asof:
            params["asof"] = asof

        all_bars: dict[str, list[dict[str, Any]]] = {s.upper(): [] for s in symbols}
        page_count = 0
        next_page_token_present = False
        seen_tokens: set[str] = set()
        repeated_page_token = False
        pagination_cycle_detected = False
        last_status = 0
        retry_after: float | None = None
        safe_error = "none"
        page_token: str | None = None
        page_bar_counts: list[int] = []
        token_hashes: list[str] = []

        while True:
            if page_token:
                params["page_token"] = page_token
            elif "page_token" in params:
                del params["page_token"]

            token_hashes.append(_token_hash(page_token))

            try:
                resp, retry_after, _ = self._get(url, params, sleeper=sleeper)
            except (requests.Timeout, requests.ConnectionError):
                return {s: pd.DataFrame() for s in symbols}, {
                    "page_count": page_count,
                    "next_page_token_present": next_page_token_present,
                    "pagination_complete": False,
                    "repeated_page_token": repeated_page_token,
                    "pagination_cycle_detected": pagination_cycle_detected,
                    "retry_after_seconds": None,
                    "safe_error_classification": "network_error",
                    "page_bar_counts": page_bar_counts,
                    "token_hashes": token_hashes,
                    "token_sequence_sha256": _token_sequence_hash(token_hashes),
                    "http_status": 0,
                }

            page_count += 1
            last_status = resp.status_code
            if last_status != 200:
                safe_error = _safe_error_class(last_status)
                try:
                    error_body = resp.text
                except Exception:  # noqa: BLE001
                    error_body = ""
                return {s: pd.DataFrame() for s in symbols}, {
                    "page_count": page_count,
                    "next_page_token_present": next_page_token_present,
                    "pagination_complete": False,
                    "repeated_page_token": repeated_page_token,
                    "pagination_cycle_detected": pagination_cycle_detected,
                    "retry_after_seconds": retry_after,
                    "safe_error_classification": safe_error,
                    "page_bar_counts": page_bar_counts,
                    "token_hashes": token_hashes,
                    "token_sequence_sha256": _token_sequence_hash(token_hashes),
                    "http_status": last_status,
                    "error_body": error_body[:500],
                }

            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                safe_error = "invalid_response"
                break

            if not isinstance(data, dict):
                safe_error = "invalid_response"
                break

            bars_by_symbol = data.get("bars", {})
            if not isinstance(bars_by_symbol, dict):
                safe_error = "invalid_response"
                break

            page_total = 0
            for sym in symbols:
                upper = sym.upper()
                bars = bars_by_symbol.get(upper, [])
                if not isinstance(bars, list):
                    bars = []
                all_bars[upper].extend(bars)
                page_total += len(bars)
            page_bar_counts.append(page_total)

            token = data.get("next_page_token")
            if token:
                next_page_token_present = True
                if token in seen_tokens:
                    repeated_page_token = True
                    pagination_cycle_detected = True
                    safe_error = "pagination_cycle"
                    break
                seen_tokens.add(token)
                page_token = token
                continue
            token_hashes.append(_token_hash(None))
            break

        dfs: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            dfs[sym.upper()] = self._normalize_bars(all_bars.get(sym.upper(), []))

        return dfs, {
            "page_count": page_count,
            "next_page_token_present": next_page_token_present,
            "pagination_complete": last_status == 200 and not repeated_page_token and safe_error != "invalid_response",
            "repeated_page_token": repeated_page_token,
            "pagination_cycle_detected": pagination_cycle_detected,
            "retry_after_seconds": retry_after,
            "safe_error_classification": safe_error,
            "page_bar_counts": page_bar_counts,
            "token_hashes": token_hashes,
            "token_sequence_sha256": _token_sequence_hash(token_hashes),
            "http_status": last_status,
        }
