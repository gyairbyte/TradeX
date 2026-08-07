"""Research-only direct REST client for Alpaca Market Data and Trading endpoints.

This module intentionally avoids the ``alpaca-py`` SDK so the probe has explicit
control over every query parameter, pagination token, and HTTP status code.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

from tradex.config import TradeXSettings, load_runtime_settings

logger = logging.getLogger(__name__)

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _token_hash(token: str | None) -> str:
    """Return a short, safe SHA-256 digest of a pagination token (or a null token)."""
    raw = "null" if token is None else str(token)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _token_sequence_hash(token_hashes: list[str]) -> str:
    """Return a SHA-256 digest of the ordered page-token hash sequence."""
    return hashlib.sha256("".join(token_hashes).encode("utf-8")).hexdigest()


def _alpaca_paper_host_from_key(api_key: str) -> str:
    """Best-guess trading host from key prefix; falls back to paper first if unknown."""
    if api_key.startswith("AK"):
        return "https://api.alpaca.markets"
    # Paper keys typically start with PK; treat unknown keys as paper to avoid live side effects.
    return "https://paper-api.alpaca.markets"


def _headers(api_key: str, secret_key: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
    }


def _now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _normalize_alpaca_bars(bars: list[dict]) -> pd.DataFrame:
    """Convert Alpaca ``bars`` records to a canonical, sorted, UTC-indexed DataFrame."""
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

    # Alpaca records use t/o/h/l/c/v plus optional n/vw.
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


def _extract_bars(data: Any, symbol: str) -> list[dict]:
    """Return the raw bars list from an Alpaca bars response payload."""
    if not isinstance(data, dict):
        return []
    bars = data.get("bars", [])
    if isinstance(bars, list):
        return bars
    if isinstance(bars, dict):
        return bars.get(symbol.upper(), []) if symbol else []
    return []


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
        # Header may be seconds-until-retry or an absolute epoch.
        value = float(retry)
        if value > 1_000_000_000:  # Looks like an epoch timestamp.
            return max(0.0, value - time.time())
        return min(value, 30.0)
    except (TypeError, ValueError):
        return default


class AlpacaRestClient:
    """Minimal read-only REST client for Alpaca research probes."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        market_data_host: str = "https://data.alpaca.markets",
        trading_host: str | None = None,
        request_delay_seconds: float = 0.5,
        max_retries: int = 1,
        request_func: Callable[..., requests.Response] | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise OSError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured")
        self.api_key = api_key
        self.secret_key = secret_key
        self.market_data_host = market_data_host.rstrip("/")
        self.trading_host = (trading_host or _alpaca_paper_host_from_key(api_key)).rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.request_func = request_func or requests.get

    def _get(
        self,
        url: str,
        params: dict[str, Any],
        sleeper: Callable[[float], None] | None = None,
        retry_hosts: list[str] | None = None,
    ) -> tuple[requests.Response, float | None, int, list[str]]:
        """Execute a GET with 429/5xx retries and optional host fallback for 401s.

        Returns (response, retry_after_seconds, attempt_count, hosts_tried).
        """
        sleeper = sleeper or time.sleep
        hosts = retry_hosts or [url]
        tried: list[str] = []
        retry_after: float | None = None
        for attempt in range(self.max_retries + 1):
            for host in hosts:
                final_url = url if host == url else host
                tried.append(final_url)
                try:
                    resp = self.request_func(final_url, params=params, headers=_headers(self.api_key, self.secret_key), timeout=30)
                except (requests.Timeout, requests.ConnectionError):
                    if attempt < self.max_retries:
                        retry_after = self.request_delay_seconds
                        sleeper(retry_after)
                        continue
                    raise

                status = resp.status_code
                if status == 429 or status >= 500:
                    if attempt < self.max_retries:
                        retry_after = _retry_after_seconds(resp, self.request_delay_seconds)
                        sleeper(retry_after)
                        continue
                elif status == 401 and len(hosts) > 1 and host != hosts[-1]:
                    # Try next host (paper/live) for 401 before giving up.
                    continue

                # Delay between sequential calls (but not between retries of the same call).
                if host == hosts[-1]:
                    sleeper(self.request_delay_seconds)
                return resp, retry_after, attempt + 1, tried
        # Exhausted retries; return last response if available.
        return resp, retry_after, attempt + 1, tried

    def get_bars(
        self,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        feed: str,
        timeframe: str,
        adjustment: str,
        asof: str,
        sort: str,
        limit: int,
        sleeper: Callable[[float], None] | None = None,
    ) -> tuple[int, list[dict], dict[str, Any]]:
        """Return (http_status, bars, pagination_metadata) following all pages.

        Bars are returned as raw Alpaca records (``t``, ``o``, ``h``, ``l``,
        ``c``, ``v``).  Pagination metadata contains ``page_count``,
        ``next_page_token_present``, ``pagination_complete``,
        ``repeated_page_token``, ``pagination_cycle_detected``,
        per-page bar counts, and token hashes (never raw tokens).
        """
        url = f"{self.market_data_host}/v2/stocks/{symbol.upper()}/bars"
        params: dict[str, Any] = {
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

        all_bars: list[dict] = []
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
                resp, retry_after, _, _ = self._get(url, params, sleeper=sleeper)
            except (requests.Timeout, requests.ConnectionError):
                return 0, all_bars, {
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
                }

            page_count += 1
            last_status = resp.status_code
            if last_status != 200:
                safe_error = _safe_error_class(last_status)
                break

            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                safe_error = "invalid_response"
                break

            bars = _extract_bars(data, symbol)
            page_bar_counts.append(len(bars))
            all_bars.extend(bars)

            token = data.get("next_page_token") if isinstance(data, dict) else None
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

        return last_status, all_bars, {
            "page_count": page_count,
            "next_page_token_present": next_page_token_present,
            "pagination_complete": last_status == 200 and not repeated_page_token,
            "repeated_page_token": repeated_page_token,
            "pagination_cycle_detected": pagination_cycle_detected,
            "retry_after_seconds": retry_after,
            "safe_error_classification": safe_error,
            "page_bar_counts": page_bar_counts,
            "token_hashes": token_hashes,
            "token_sequence_sha256": _token_sequence_hash(token_hashes),
        }

    def _trading_get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
        """Call a Trading API endpoint, trying paper then live host on 401."""
        hosts = [self.trading_host]
        other = "https://api.alpaca.markets" if self.trading_host.startswith("https://paper-api") else "https://paper-api.alpaca.markets"
        hosts.append(other)

        url = f"{hosts[0]}{path}"
        resp, _, _, _ = self._get(url, params or {}, retry_hosts=[url, f"{hosts[1]}{path}"])
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {}
        return status, data

    def get_assets(self, status: str = "active", asset_class: str = "us_equity") -> tuple[int, Any]:
        """Return (status, assets list or error object)."""
        return self._trading_get("/v2/assets", {"status": status, "asset_class": asset_class})

    def get_corporate_actions(
        self,
        symbols: list[str],
        start: str,
        end: str,
        *,
        data_quality: str = "complete",
        limit: int = 1000,
    ) -> tuple[int, Any]:
        """Return (status, corporate actions payload or error object)."""
        url = f"{self.market_data_host}/v1/corporate-actions"
        params: dict[str, Any] = {
            "symbols": ",".join(s.upper() for s in symbols),
            "start": start,
            "end": end,
            "data_quality": data_quality,
            "limit": limit,
        }
        try:
            resp, _, _, _ = self._get(url, params)
        except (requests.Timeout, requests.ConnectionError):
            return 0, {}
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {}
        return status, data


def make_alpaca_client(
    settings: TradeXSettings | None = None,
    request_func: Callable[..., requests.Response] | None = None,
) -> AlpacaRestClient:
    """Build an AlpacaRestClient from typed TradeXSettings."""
    settings = settings or load_runtime_settings()
    api_key = (settings.data.alpaca_api_key or "").strip()
    secret_key = (settings.data.alpaca_secret_key or "").strip()
    return AlpacaRestClient(api_key, secret_key, request_func=request_func)
