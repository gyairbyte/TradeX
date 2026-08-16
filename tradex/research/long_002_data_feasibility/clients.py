"""Research-only provider clients for LONG-002B.

Each client returns safe, provenance-rich dictionaries and never logs secrets.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

from tradex.config import load_runtime_settings


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class BudgetError(RuntimeError):
    """Raised when the hard network budget is exhausted."""


class Long002ClientError(RuntimeError):
    """Base for provider capability/response errors in LONG-002B."""


class Long002ProviderTransientError(Long002ClientError):
    """Retryable network/connection errors."""


class Long002ProviderAuthError(Long002ClientError):
    """Missing credentials or authentication failure."""


class Long002ProviderEntitlementError(Long002ClientError):
    """Provider access denied because of plan/entitlement."""


class Long002ProviderResponseError(Long002ClientError):
    """Malformed or unexpected non-retryable response."""


class Long002ProviderUnsupportedError(Long002ClientError):
    """Requested capability not supported by this provider/client."""


class RequestBudget:
    """Shared mutable budget tracker."""

    def __init__(self, max_requests: int = 120) -> None:
        self.max_requests = max_requests
        self.used = 0
        self.started_at = time.monotonic()

    def charge(self, n: int = 1) -> None:
        if self.used + n > self.max_requests:
            raise BudgetError(f"Budget exhausted: {self.used + n}/{self.max_requests}")
        self.used += n

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


class Long002MassiveClient:
    """Research-only wrapper around Massive/Polygon v3 reference endpoints."""

    _BASE_URL = "https://api.massive.com"
    _MIN_INTERVAL_SECONDS = 12.1  # free-tier 5 calls per minute

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        budget: RequestBudget | None = None,
        request_func: Callable[[str], bytes] | None = None,
        min_interval_seconds: float | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise Long002ProviderAuthError("Massive/Polygon API key is required")
        self.api_key = api_key.strip()
        self.base_url = (base_url or self._BASE_URL).rstrip("/")
        self.budget = budget or RequestBudget()
        self._last_request_time: float = 0.0
        self._request_func = request_func
        self._min_interval_seconds = min_interval_seconds if min_interval_seconds is not None else self._MIN_INTERVAL_SECONDS

    def _fetch_once(self, url: str) -> tuple[bytes, int | None, str | None]:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)
        self._last_request_time = time.monotonic()
        if self._request_func:
            return self._request_func(url), 200, None
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read(), response.getcode(), None
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return body, exc.code, str(exc)
        except urllib.error.URLError as exc:
            raise Long002ProviderTransientError(str(exc)) from exc

    def _fetch_json(self, url: str) -> tuple[dict[str, Any] | None, int | None, str | None]:
        body, status, error = self._fetch_once(url)
        if error and status == 429:
            time.sleep(60)
            body, status, error = self._fetch_once(url)
        if error:
            return None, status, error
        try:
            return json.loads(body.decode("utf-8")), status, None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, status, f"JSON decode error: {exc}"

    def _url(self, path: str, params: dict[str, Any]) -> str:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        sep = "&" if query else ""
        return f"{self.base_url}{path}?{query}{sep}apiKey={self.api_key}"

    def fetch_reference_snapshot(
        self,
        pit_date: str,
        active: bool,
        safety_max_pages: int = 50,
    ) -> dict[str, Any]:
        """Fetch one completely paginated active/inactive ticker snapshot."""
        self.budget.charge(1)
        base_params = {
            "market": "stocks",
            "locale": "us",
            "date": pit_date,
            "active": "true" if active else "false",
            "sort": "ticker",
            "order": "asc",
            "limit": 1000,
        }
        all_results: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        next_url: str | None = None
        page = 0
        while True:
            page += 1
            if next_url:
                url = next_url if "apiKey=" in next_url else f"{next_url}&apiKey={self.api_key}"
            else:
                url = self._url("/v3/reference/tickers", base_params)
            if page > 1:
                self.budget.charge(1)
            data, status, error = self._fetch_json(url)
            if error:
                return {
                    "provider": "massive",
                    "pit_date": pit_date,
                    "active": active,
                    "status": status,
                    "error": error,
                    "row_count": 0,
                    "page_count": page,
                    "pagination_complete": False,
                    "rows": [],
                    "pages": pages,
                }
            results = data.get("results", []) if isinstance(data, dict) else []
            raw_next = data.get("next_url") if isinstance(data, dict) else None
            next_url = raw_next if isinstance(raw_next, str) else None
            page_hash = _json_hash(results)
            all_results.extend(results)
            pages.append({
                "page": page,
                "row_count": len(results),
                "page_sha256": page_hash,
                "next_url_present": bool(next_url),
                "http_status": status,
            })
            if not next_url:
                break
            if page >= safety_max_pages:
                return {
                    "provider": "massive",
                    "pit_date": pit_date,
                    "active": active,
                    "status": status,
                    "error": f"safety_max_pages ({safety_max_pages}) reached",
                    "row_count": len(all_results),
                    "page_count": page,
                    "pagination_complete": False,
                    "rows": all_results,
                    "pages": pages,
                }

        full_hash = _json_hash(all_results) if all_results else ""
        return {
            "provider": "massive",
            "pit_date": pit_date,
            "active": active,
            "status": 200,
            "error": None,
            "row_count": len(all_results),
            "page_count": page,
            "pagination_complete": True,
            "rows": all_results,
            "pages": pages,
            "snapshot_sha256": full_hash,
        }

    def fetch_ticker_detail(
        self,
        ticker: str,
        pit_date: str,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """Fetch a single ticker's PIT identity record."""
        self.budget.charge(1)
        params: dict[str, Any] = {
            "ticker": ticker,
            "date": pit_date,
            "market": "stocks",
            "locale": "us",
            "limit": 10,
            "sort": "ticker",
            "order": "asc",
        }
        if active is not None:
            params["active"] = "true" if active else "false"
        url = self._url("/v3/reference/tickers", params)
        data, status, error = self._fetch_json(url)
        if error:
            return {
                "provider": "massive",
                "ticker": ticker,
                "pit_date": pit_date,
                "status": status,
                "error": error,
                "row": None,
                "type": None,
                "primary_exchange": None,
                "cik": None,
            }
        results = data.get("results", []) if isinstance(data, dict) else []
        row = results[0] if results else None
        return {
            "provider": "massive",
            "ticker": ticker,
            "pit_date": pit_date,
            "status": status,
            "error": None,
            "row": row,
            "type": row.get("type") if row else None,
            "primary_exchange": row.get("primary_exchange") if row else None,
            "cik": row.get("cik") if row else None,
        }

    def fetch_daily_bars(
        self,
        ticker: str,
        start: str,
        end: str,
        *,
        adjusted: bool = False,
    ) -> dict[str, Any]:
        """Attempt Polygon/Massive daily aggregate bars for a single ticker."""
        self.budget.charge(1)
        path = f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}"
        params: dict[str, Any] = {"adjusted": "true" if adjusted else "false"}
        url = self._url(path, params)
        data, status, error = self._fetch_json(url)
        if error:
            return {
                "provider": "massive/polygon",
                "ticker": ticker,
                "start": start,
                "end": end,
                "status": status,
                "error": error,
                "bars": [],
                "results_count": 0,
                "pagination_complete": False,
                "adjusted": adjusted,
            }
        results = data.get("results", []) if isinstance(data, dict) else []
        bars: list[dict[str, Any]] = []
        for r in results:
            if not all(isinstance(r.get(k), (int, float)) for k in ("o", "h", "l", "c", "v")):
                return {
                    "provider": "massive/polygon",
                    "ticker": ticker,
                    "start": start,
                    "end": end,
                    "status": status,
                    "error": "invalid_bar_fields",
                    "bars": [],
                    "results_count": 0,
                    "pagination_complete": False,
                    "adjusted": adjusted,
                }
            ts = r.get("t")
            if isinstance(ts, int):
                ts_dt = datetime.fromtimestamp(ts / 1000.0, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            else:
                ts_dt = str(ts)
            bars.append({
                "t": ts_dt,
                "o": r.get("o"),
                "h": r.get("h"),
                "l": r.get("l"),
                "c": r.get("c"),
                "v": r.get("v"),
                "vw": r.get("vw"),
                "n": r.get("n"),
            })
        return {
            "provider": "massive/polygon",
            "ticker": ticker,
            "start": start,
            "end": end,
            "status": status,
            "error": None,
            "bars": bars,
            "results_count": len(bars),
            "pagination_complete": True,
            "adjusted": adjusted,
        }

    def fetch_splits(self, ticker: str) -> dict[str, Any]:
        """Fetch split events for a single ticker."""
        self.budget.charge(1)
        url = self._url("/v3/reference/splits", {"ticker": ticker, "limit": 1000})
        data, status, error = self._fetch_json(url)
        results = data.get("results", []) if isinstance(data, dict) and not error else []
        return {
            "provider": "massive",
            "ticker": ticker,
            "event_type": "split",
            "status": status,
            "error": error,
            "events": results,
            "event_count": len(results),
        }

    def fetch_dividends(self, ticker: str) -> dict[str, Any]:
        """Fetch dividend events for a single ticker."""
        self.budget.charge(1)
        url = self._url("/v3/reference/dividends", {"ticker": ticker, "limit": 1000})
        data, status, error = self._fetch_json(url)
        results = data.get("results", []) if isinstance(data, dict) and not error else []
        return {
            "provider": "massive",
            "ticker": ticker,
            "event_type": "dividend",
            "status": status,
            "error": error,
            "events": results,
            "event_count": len(results),
        }

    def fetch_corporate_actions(self, ticker: str) -> dict[str, Any]:
        """Fetch both split and dividend events for a single ticker."""
        splits = self.fetch_splits(ticker)
        dividends = self.fetch_dividends(ticker)
        return {
            "provider": "massive",
            "ticker": ticker,
            "splits": splits,
            "dividends": dividends,
            "status": 200 if splits["status"] == 200 and dividends["status"] == 200 else (splits["status"] or dividends["status"]),
            "error": splits.get("error") or dividends.get("error"),
        }


class Long002AlpacaClient:
    """Research-only daily-bars client built on the existing Alpaca REST pattern."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        budget: RequestBudget | None = None,
        request_func: Callable[..., requests.Response] | None = None,
        request_delay_seconds: float = 0.5,
        max_retries: int = 1,
    ) -> None:
        if not api_key or not secret_key:
            raise Long002ProviderAuthError("Alpaca API key and secret key are required")
        self.api_key = api_key
        self.secret_key = secret_key
        self.budget = budget or RequestBudget()
        self._request_func = request_func or requests.get
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.host = "https://data.alpaca.markets"

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Accept": "application/json",
        }

    def _error_class(self, status: int) -> str:
        if status == 429:
            return "http_429"
        if status >= 500:
            return f"http_{status}"
        if status == 401:
            return "http_401"
        if status == 403:
            return "http_403"
        if status == 400:
            return "http_400"
        if status != 200:
            return f"http_{status}"
        return "none"

    def _get(self, url: str, params: dict[str, Any]) -> tuple[requests.Response, int]:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                resp = self._request_func(url, params=params, headers=self._headers(), timeout=30)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if attempt > self.max_retries:
                    raise Long002ProviderTransientError(str(exc)) from exc
                time.sleep(self.request_delay_seconds)
                continue
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt <= self.max_retries:
                time.sleep(self.request_delay_seconds)
                continue
            return resp, attempt
        raise Long002ProviderTransientError(str(last_exc)) from last_exc

    def fetch_daily_bars(
        self,
        symbol: str,
        start_utc: str,
        end_utc: str,
        *,
        feed: str = "sip",
        adjustment: str = "raw",
    ) -> dict[str, Any]:
        """Fetch daily bars for a symbol and provenance summary, with pagination."""
        url = f"{self.host}/v2/stocks/{symbol.upper()}/bars"
        params: dict[str, Any] = {
            "timeframe": "1Day",
            "start": start_utc,
            "end": end_utc,
            "feed": feed,
            "adjustment": adjustment,
            "sort": "asc",
            "limit": 10000,
        }
        all_bars: list[dict[str, Any]] = []
        page = 0
        pagination_complete = False
        total_attempts = 0
        status: int | None = None
        safe_error = "none"
        while page < 50:
            page += 1
            self.budget.charge(1)
            try:
                resp, attempts = self._get(url, params)
            except Long002ProviderTransientError as exc:
                return {
                    "provider": "alpaca",
                    "symbol": symbol,
                    "http_status": None,
                    "error_classification": "network_error",
                    "retry_count": total_attempts,
                    "bars": [],
                    "bar_count": 0,
                    "page_count": page,
                    "pagination_complete": False,
                    "feed": feed,
                    "adjustment": adjustment,
                    "error": str(exc),
                }
            status = resp.status_code
            safe_error = self._error_class(status)
            total_attempts += attempts
            if status != 200:
                return {
                    "provider": "alpaca",
                    "symbol": symbol,
                    "http_status": status,
                    "error_classification": safe_error,
                    "retry_count": total_attempts - 1,
                    "bars": [],
                    "bar_count": 0,
                    "page_count": page,
                    "pagination_complete": False,
                    "feed": feed,
                    "adjustment": adjustment,
                    "error": safe_error,
                }
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return {
                    "provider": "alpaca",
                    "symbol": symbol,
                    "http_status": status,
                    "error_classification": "invalid_response",
                    "retry_count": total_attempts - 1,
                    "bars": [],
                    "bar_count": 0,
                    "page_count": page,
                    "pagination_complete": False,
                    "feed": feed,
                    "adjustment": adjustment,
                    "error": "invalid_response",
                }
            bars = data.get("bars", []) if isinstance(data, dict) else []
            if isinstance(bars, dict):
                bars = bars.get(symbol.upper(), [])
            all_bars.extend(bars)
            next_token = data.get("next_page_token") if isinstance(data, dict) else None
            if not next_token:
                pagination_complete = True
                break
            params["page_token"] = next_token
        return {
            "provider": "alpaca",
            "symbol": symbol,
            "http_status": status,
            "error_classification": safe_error,
            "retry_count": total_attempts - page if total_attempts >= page else 0,
            "bars": all_bars,
            "bar_count": len(all_bars),
            "page_count": page,
            "pagination_complete": pagination_complete,
            "feed": feed,
            "adjustment": adjustment,
        }

    def to_dataframe(self, bars: list[dict[str, Any]]) -> pd.DataFrame:
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(bars)
        df = df.rename(columns={"t": "datetime", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
        df = df.dropna(subset=["datetime"]).set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna()


class Long002EdgarClient:
    """Minimal SEC EDGAR submissions/facts client with no API key."""

    _BASE = "https://data.sec.gov"
    _USER_AGENT = "TradeX Research (research@gyairbyte.com)"

    def __init__(
        self,
        budget: RequestBudget | None = None,
        request_func: Callable[[str], bytes] | None = None,
    ) -> None:
        self.budget = budget or RequestBudget()
        self._request_func = request_func

    def _fetch_json(self, url: str) -> dict[str, Any]:
        self.budget.charge(1)
        if self._request_func:
            try:
                result = self._request_func(url)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return {}
                raise Long002ProviderResponseError(f"EDGAR HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise Long002ProviderTransientError(str(exc)) from exc
            body = result[0] if isinstance(result, tuple) else result
            return json.loads(body.decode("utf-8"))
        req = urllib.request.Request(url, headers={"User-Agent": self._USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {}
            raise Long002ProviderResponseError(f"EDGAR HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise Long002ProviderTransientError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise Long002ProviderResponseError(f"EDGAR JSON decode error: {exc}") from exc

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        padded = cik.zfill(10)
        url = f"{self._BASE}/submissions/CIK{padded}.json"
        return self._fetch_json(url)

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        padded = cik.zfill(10)
        url = f"{self._BASE}/api/xbrl/companyfacts/CIK{padded}.json"
        return self._fetch_json(url)


def resolve_credentials() -> dict[str, str | None]:
    """Load provider credentials from runtime settings without exposing them."""
    settings = load_runtime_settings()
    return {
        "massive_api_key": settings.data.massive_api_key,
        "alpaca_api_key": settings.data.alpaca_api_key,
        "alpaca_secret_key": settings.data.alpaca_secret_key,
    }
