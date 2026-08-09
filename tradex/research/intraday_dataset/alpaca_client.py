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


def _count_429_and_error(statuses: list[int]) -> tuple[int, int]:
    """Return (http_429_count, http_error_count) from per-attempt statuses."""
    http_429s = sum(1 for s in statuses if s == 429)
    http_errors = sum(1 for s in statuses if s != 200)
    return http_429s, http_errors


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
        if request_func:
            self.request_func = request_func
        else:
            self._session = requests.Session()
            self.request_func = self._session.get

    def _get(
        self,
        url: str,
        params: dict[str, Any],
        sleeper: Callable[[float], None] | None = None,
    ) -> tuple[requests.Response, float | None, int, list[int]]:
        """Execute one HTTP page fetch, retrying on 429/5xx. Returns response, retry-after, attempt count, statuses."""
        sleeper = sleeper or time.sleep
        retry_after: float | None = None
        statuses: list[int] = []
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.request_func(url, params=params, headers=_headers(self.api_key, self.secret_key), timeout=30)
            except (requests.Timeout, requests.ConnectionError):
                if attempt < self.max_retries:
                    sleeper(self.request_delay_seconds)
                    continue
                raise
            status = resp.status_code
            statuses.append(status)
            if (status == 429 or status >= 500) and attempt < self.max_retries:
                retry_after = _retry_after_seconds(resp, self.request_delay_seconds)
                sleeper(retry_after)
                continue
            sleeper(self.request_delay_seconds)
            return resp, retry_after, attempt + 1, statuses
        return resp, retry_after, attempt + 1, statuses  # type: ignore[possibly-undefined]

    def _normalize_bars(
        self,
        bars: list[dict[str, Any]],
    ) -> tuple[pd.DataFrame, int]:
        """Convert provider bars to a numeric UTC DataFrame and count malformed timestamps.

        Rows with missing or unparseable timestamps are counted and dropped so
        callers can fail closed; callers are responsible for counting duplicate
        and malformed OHLCV rows and then deduplicating/dropping before storage.
        """
        empty = pd.DataFrame(
            columns=_OHLCV_COLUMNS,
            index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
        )
        if not bars:
            return empty, 0
        df = pd.DataFrame(bars)
        if "t" not in df.columns:
            # Every row is missing its timestamp; count them and fail closed.
            return empty, len(df)
        df = df.rename(columns={"t": "datetime", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
        malformed_timestamp_count = int(df["datetime"].isna().sum())
        df = df.dropna(subset=["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in _OHLCV_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[_OHLCV_COLUMNS]
        for col in _OHLCV_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df, malformed_timestamp_count

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
        response_symbols: set[str] = set()
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

        http_attempts = 0
        http_429s = 0
        http_errors = 0
        while True:
            if page_token:
                params["page_token"] = page_token
            elif "page_token" in params:
                del params["page_token"]

            token_hashes.append(_token_hash(page_token))

            try:
                resp, retry_after, attempts, statuses = self._get(url, params, sleeper=sleeper)
                http_attempts += attempts
                r429, rerr = _count_429_and_error(statuses)
                http_429s += r429
                http_errors += rerr
            except (requests.Timeout, requests.ConnectionError):
                return {s: pd.DataFrame() for s in symbols}, {
                    "page_count": page_count,
                    "logical_calls": 1,
                    "http_pages": page_count,
                    "http_attempts": http_attempts,
                    "http_429s": http_429s,
                    "http_errors": http_errors,
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
                    "response_symbols": sorted(response_symbols),
                    "malformed_timestamp_counts": {s.upper(): 0 for s in symbols},
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
                    "logical_calls": 1,
                    "http_pages": page_count,
                    "http_attempts": http_attempts,
                    "http_429s": http_429s,
                    "http_errors": http_errors,
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
                    "response_symbols": sorted(response_symbols),
                    "malformed_timestamp_counts": {s.upper(): 0 for s in symbols},
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

            # Symbol identity: accumulate every symbol that appears on any page.
            # A requested symbol missing from all pages is returned as an empty
            # DataFrame; an unexpected key is ignored for the requested set.
            response_symbols.update(str(s).upper() for s in bars_by_symbol)

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
        malformed_timestamp_counts: dict[str, int] = {}
        for sym in symbols:
            sym_upper = sym.upper()
            df, malformed_ts_count = self._normalize_bars(all_bars.get(sym_upper, []))
            dfs[sym_upper] = df
            malformed_timestamp_counts[sym_upper] = malformed_ts_count

        return dfs, {
            "page_count": page_count,
            "logical_calls": 1,
            "http_pages": page_count,
            "malformed_timestamp_counts": malformed_timestamp_counts,
            "http_attempts": http_attempts,
            "http_429s": http_429s,
            "http_errors": http_errors,
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
            "response_symbols": sorted(response_symbols),
        }
