"""Auditable research provider clients for LONG-002C.

Integrates Alpaca (daily bars fallback), Massive (reference / corporate actions), and SEC EDGAR (fundamentals/shares).
All clients record provenance, enforce budgets, and never log secrets.
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

import requests

from tradex.config import load_runtime_settings
from tradex.research.long_002c.models import ProvenanceProviderRecord


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class BudgetError(RuntimeError):
    """Raised when the network budget is exhausted."""


class RequestBudget:
    """Shared budget counter for provider network requests."""

    def __init__(self, max_requests: int = 50000) -> None:
        self.max_requests = max_requests
        self.used = 0
        self.started_at = time.monotonic()

    def charge(self, n: int = 1) -> None:
        if self.used + n > self.max_requests:
            raise BudgetError(f"Request budget exhausted: {self.used + n}/{self.max_requests}")
        self.used += n

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


class AlpacaDailyClient:
    """Daily market data client using Alpaca REST API."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        budget: RequestBudget | None = None,
        request_func: Callable[..., requests.Response] | None = None,
        request_delay_seconds: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        if not api_key or not secret_key:
            raise ValueError("Alpaca API key and secret key are required")
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

    def fetch_daily_bars(
        self,
        symbol: str,
        start_utc: str,
        end_utc: str,
        *,
        feed: str = "sip",
        adjustment: str = "raw",
    ) -> tuple[list[dict[str, Any]], list[ProvenanceProviderRecord]]:
        """Fetch daily bars for symbol between start_utc and end_utc, paginating if needed."""
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
        provenance_records: list[ProvenanceProviderRecord] = []
        page = 0

        while page < 50:
            page += 1
            self.budget.charge(1)
            req_time = _now_utc()
            req_fp = _json_hash({"url": url, "params": params, "feed": feed, "adjustment": adjustment})

            attempt = 0
            resp: requests.Response | None = None
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    resp = self._request_func(
                        url,
                        params=params,
                        headers=self._headers(),
                        timeout=30,
                    )
                except Exception as exc:  # noqa: BLE001
                    if attempt > self.max_retries:
                        provenance_records.append(
                            ProvenanceProviderRecord(
                                record_id=f"prov_{req_fp[:16]}_{page}",
                                data_family="daily_market_data",
                                provider_name="alpaca",
                                provider_role="fallback",
                                endpoint_url_pattern="/v2/stocks/{symbol}/bars",
                                retrieval_timestamp_utc=req_time,
                                request_fingerprint_sha256=req_fp,
                                response_sha256=hashlib.sha256(str(exc).encode()).hexdigest(),
                            )
                        )
                        return all_bars, provenance_records
                    time.sleep(self.request_delay_seconds)
                    continue

                if (resp.status_code == 429 or resp.status_code >= 500) and attempt <= self.max_retries:
                    time.sleep(self.request_delay_seconds * 2)
                    continue
                break

            if resp is None or resp.status_code != 200:
                resp_hash = hashlib.sha256(resp.content if resp else b"").hexdigest()
                provenance_records.append(
                    ProvenanceProviderRecord(
                        record_id=f"prov_{req_fp[:16]}_{page}",
                        data_family="daily_market_data",
                        provider_name="alpaca",
                        provider_role="fallback",
                        endpoint_url_pattern="/v2/stocks/{symbol}/bars",
                        retrieval_timestamp_utc=req_time,
                        request_fingerprint_sha256=req_fp,
                        response_sha256=resp_hash,
                    )
                )
                break

            resp_hash = hashlib.sha256(resp.content).hexdigest()
            provenance_records.append(
                ProvenanceProviderRecord(
                    record_id=f"prov_{req_fp[:16]}_{page}",
                    data_family="daily_market_data",
                    provider_name="alpaca",
                    provider_role="fallback",
                    endpoint_url_pattern="/v2/stocks/{symbol}/bars",
                    retrieval_timestamp_utc=req_time,
                    request_fingerprint_sha256=req_fp,
                    response_sha256=resp_hash,
                )
            )

            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                break

            bars = data.get("bars", []) if isinstance(data, dict) else []
            if isinstance(bars, dict):
                bars = bars.get(symbol.upper(), [])
            all_bars.extend(bars)

            next_token = data.get("next_page_token") if isinstance(data, dict) else None
            if not next_token:
                break
            params["page_token"] = next_token

        return all_bars, provenance_records


class MassiveRefClient:
    """Security master, corporate actions, and financial reference client."""

    _BASE_URL = "https://api.massive.com"
    _MIN_INTERVAL_SECONDS = 12.1

    def __init__(
        self,
        api_key: str,
        budget: RequestBudget | None = None,
        request_func: Callable[[str], bytes] | None = None,
        min_interval_seconds: float | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Massive API key is required")
        self.api_key = api_key.strip()
        self.budget = budget or RequestBudget()
        self._last_request_time: float = 0.0
        self._request_func = request_func
        self._min_interval_seconds = (
            min_interval_seconds if min_interval_seconds is not None else self._MIN_INTERVAL_SECONDS
        )

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
            return b"", None, str(exc)

    def _fetch_json(self, url: str) -> tuple[dict[str, Any] | None, int | None, str | None, str]:
        self.budget.charge(1)
        body, status, error = self._fetch_once(url)
        body_hash = hashlib.sha256(body).hexdigest()
        if error:
            return None, status, error, body_hash
        try:
            return json.loads(body.decode("utf-8")), status, None, body_hash
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, status, f"JSON decode error: {exc}", body_hash

    def _url(self, path: str, params: dict[str, Any]) -> str:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        sep = "&" if query else ""
        return f"{self._BASE_URL}{path}?{query}{sep}apiKey={self.api_key}"

    def fetch_reference_snapshot(
        self,
        pit_date: str,
        active: bool = True,
        safety_max_pages: int = 15,
    ) -> tuple[list[dict[str, Any]], list[ProvenanceProviderRecord]]:
        """Fetch active or inactive ticker reference snapshot."""
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
        provenance: list[ProvenanceProviderRecord] = []
        next_url: str | None = None
        page = 0

        while page < safety_max_pages:
            page += 1
            if next_url:
                url = next_url if "apiKey=" in next_url else f"{next_url}&apiKey={self.api_key}"
            else:
                url = self._url("/v3/reference/tickers", base_params)

            req_time = _now_utc()
            req_fp = _json_hash({"url": url.split("&apiKey=")[0]})
            data, _status, error, resp_hash = self._fetch_json(url)

            provenance.append(
                ProvenanceProviderRecord(
                    record_id=f"prov_massive_tickers_{pit_date}_{page}",
                    data_family="security_master",
                    provider_name="massive",
                    provider_role="primary",
                    endpoint_url_pattern="/v3/reference/tickers",
                    retrieval_timestamp_utc=req_time,
                    request_fingerprint_sha256=req_fp,
                    response_sha256=resp_hash,
                )
            )

            if error or not isinstance(data, dict):
                break

            results = data.get("results", [])
            all_results.extend(results)
            raw_next = data.get("next_url")
            next_url = raw_next if isinstance(raw_next, str) else None
            if not next_url:
                break

        return all_results, provenance

    def fetch_corporate_actions(
        self, ticker: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[ProvenanceProviderRecord]]:
        """Fetch split and dividend events for ticker."""
        provenance: list[ProvenanceProviderRecord] = []

        # Splits
        split_url = self._url("/v3/reference/splits", {"ticker": ticker.upper(), "limit": 1000})
        req_time = _now_utc()
        data, _status, error, resp_hash = self._fetch_json(split_url)
        splits = data.get("results", []) if isinstance(data, dict) and not error else []
        provenance.append(
            ProvenanceProviderRecord(
                record_id=f"prov_split_{ticker.upper()}",
                data_family="corporate_actions",
                provider_name="massive",
                provider_role="primary",
                endpoint_url_pattern="/v3/reference/splits",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash({"ticker": ticker.upper(), "event": "split"}),
                response_sha256=resp_hash,
            )
        )

        # Dividends
        div_url = self._url("/v3/reference/dividends", {"ticker": ticker.upper(), "limit": 1000})
        req_time = _now_utc()
        data, _status, error, resp_hash = self._fetch_json(div_url)
        dividends = data.get("results", []) if isinstance(data, dict) and not error else []
        provenance.append(
            ProvenanceProviderRecord(
                record_id=f"prov_div_{ticker.upper()}",
                data_family="corporate_actions",
                provider_name="massive",
                provider_role="primary",
                endpoint_url_pattern="/v3/reference/dividends",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash({"ticker": ticker.upper(), "event": "dividend"}),
                response_sha256=resp_hash,
            )
        )

        return splits, dividends, provenance


class EdgarClient:
    """Minimal SEC EDGAR submissions and facts client."""

    _BASE = "https://data.sec.gov"
    _USER_AGENT = "TradeX Research (research@gyairbyte.com)"

    def __init__(
        self,
        budget: RequestBudget | None = None,
        request_func: Callable[[str], bytes] | None = None,
    ) -> None:
        self.budget = budget or RequestBudget()
        self._request_func = request_func

    def _fetch_json(self, url: str) -> tuple[dict[str, Any], str]:
        self.budget.charge(1)
        if self._request_func:
            try:
                res = self._request_func(url)
            except Exception:  # noqa: BLE001
                return {}, ""
            body = res[0] if isinstance(res, tuple) else res
            h = hashlib.sha256(body).hexdigest()
            return json.loads(body.decode("utf-8")), h

        req = urllib.request.Request(url, headers={"User-Agent": self._USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8")), hashlib.sha256(body).hexdigest()
        except Exception:  # noqa: BLE001
            return {}, ""

    def fetch_submissions(self, cik: str) -> tuple[dict[str, Any], list[ProvenanceProviderRecord]]:
        padded = cik.zfill(10)
        url = f"{self._BASE}/submissions/CIK{padded}.json"
        req_time = _now_utc()
        data, h = self._fetch_json(url)
        prov = [
            ProvenanceProviderRecord(
                record_id=f"prov_edgar_sub_{padded}",
                data_family="issuer_fundamentals",
                provider_name="sec_edgar",
                provider_role="primary",
                endpoint_url_pattern="/submissions/CIK{cik}.json",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash({"cik": padded}),
                response_sha256=h,
            )
        ]
        return data, prov


def resolve_credentials() -> dict[str, str | None]:
    """Load runtime provider credentials safely without printing values."""
    settings = load_runtime_settings()
    return {
        "massive_api_key": settings.data.massive_api_key,
        "alpaca_api_key": settings.data.alpaca_api_key,
        "alpaca_secret_key": settings.data.alpaca_secret_key,
    }
