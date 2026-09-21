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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from tradex.config import load_runtime_settings
from tradex.research.long_002c.cache import ResponseCache, sanitize_url
from tradex.research.long_002c.models import ProvenanceProviderRecord


@dataclass(frozen=True)
class SnapshotPaginationMeta:
    """Detailed pagination and completeness audit metadata for a reference snapshot."""

    pit_date: str
    active: bool
    pages_fetched: int
    records_per_page: list[int]
    total_records: int
    pagination_exhausted_normally: bool
    safety_max_pages_hit: bool
    first_ticker: str | None
    last_ticker: str | None
    response_hashes: list[str]
    is_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "pit_date": self.pit_date,
            "active": self.active,
            "pages_fetched": self.pages_fetched,
            "records_per_page": self.records_per_page,
            "total_records": self.total_records,
            "pagination_exhausted_normally": self.pagination_exhausted_normally,
            "safety_max_pages_hit": self.safety_max_pages_hit,
            "first_ticker": self.first_ticker,
            "last_ticker": self.last_ticker,
            "response_hashes": self.response_hashes,
            "is_complete": self.is_complete,
        }


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
        cache: ResponseCache | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise ValueError("Alpaca API key and secret key are required")
        self.api_key = api_key
        self.secret_key = secret_key
        self.budget = budget or RequestBudget()
        self._request_func = request_func or requests.get
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.cache = cache
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
            req_time = _now_utc()
            req_fp = _json_hash({"url": url, "params": params, "feed": feed, "adjustment": adjustment})

            if self.cache:
                cached_data, cached_sha, cached_ts = self.cache.get_json(url, req_fp)
                if cached_data is not None and isinstance(cached_data, dict):
                    provenance_records.append(
                        ProvenanceProviderRecord(
                            record_id=f"prov_{req_fp[:16]}_{page}",
                            data_family="daily_market_data",
                            provider_name="alpaca",
                            provider_role="fallback",
                            endpoint_url_pattern="/v2/stocks/{symbol}/bars",
                            retrieval_timestamp_utc=cached_ts or req_time,
                            request_fingerprint_sha256=req_fp,
                            response_sha256=cached_sha or "",
                        )
                    )
                    bars = cached_data.get("bars", [])
                    if isinstance(bars, dict):
                        bars = bars.get(symbol.upper(), [])
                    all_bars.extend(bars)
                    next_token = cached_data.get("next_page_token")
                    if not next_token:
                        break
                    params["page_token"] = next_token
                    continue

            self.budget.charge(1)

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
            if self.cache:
                self.cache.set(
                    url,
                    req_fp,
                    resp.content,
                    endpoint_pattern="/v2/stocks/{symbol}/bars",
                    retrieval_timestamp_utc=req_time,
                )

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
        cache: ResponseCache | None = None,
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
        self.cache = cache
        self.network_requests_count = 0
        self.cache_hits_count = 0
        self.retries_count = 0
        self.rate_limit_429_count = 0

    def _fetch_once(self, url: str, max_retries: int = 3) -> tuple[bytes, int | None, str | None]:
        for attempt in range(max_retries + 1):
            if attempt > 0:
                self.retries_count += 1
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._min_interval_seconds:
                time.sleep(self._min_interval_seconds - elapsed)
            self._last_request_time = time.monotonic()

            if self._request_func:
                self.network_requests_count += 1
                return self._request_func(url), 200, None

            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            try:
                self.network_requests_count += 1
                with urllib.request.urlopen(req, timeout=120) as response:
                    return response.read(), response.getcode(), None
            except urllib.error.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                if exc.code == 429:
                    self.rate_limit_429_count += 1
                    if attempt < max_retries:
                        time.sleep(15.0 * (attempt + 1))
                        continue
                return body, exc.code, str(exc)
            except urllib.error.URLError as exc:
                if attempt < max_retries:
                    time.sleep(2.0)
                    continue
                return b"", None, str(exc)
        return b"", None, "Max retries exceeded"

    def _fetch_json(
        self,
        url: str,
        endpoint_pattern: str | None = None,
        req_fp_obj: Any = None,
    ) -> tuple[dict[str, Any] | None, int | None, str | None, str, str]:
        sanitized = sanitize_url(url)
        req_fp = _json_hash(req_fp_obj if req_fp_obj is not None else {"url": sanitized})
        req_time = _now_utc()

        if self.cache:
            cached_data, cached_sha, cached_ts = self.cache.get_json(sanitized, req_fp)
            if cached_data is not None and isinstance(cached_data, dict):
                self.cache_hits_count += 1
                return cached_data, 200, None, cached_sha or "", cached_ts or req_time

        self.budget.charge(1)
        body, status, error = self._fetch_once(url)
        body_hash = hashlib.sha256(body).hexdigest()
        if error:
            return None, status, error, body_hash, req_time
        try:
            parsed = json.loads(body.decode("utf-8"))
            if self.cache and isinstance(parsed, dict) and status == 200:
                self.cache.set(
                    sanitized,
                    req_fp,
                    body,
                    endpoint_pattern=endpoint_pattern,
                    retrieval_timestamp_utc=req_time,
                )
            return parsed, status, None, body_hash, req_time
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, status, f"JSON decode error: {exc}", body_hash, req_time

    def _url(self, path: str, params: dict[str, Any]) -> str:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        sep = "&" if query else ""
        return f"{self._BASE_URL}{path}?{query}{sep}apiKey={self.api_key}"

    def fetch_reference_snapshot(
        self,
        pit_date: str,
        active: bool = True,
        safety_max_pages: int = 50,
    ) -> tuple[list[dict[str, Any]], list[ProvenanceProviderRecord], SnapshotPaginationMeta]:
        """Fetch active or inactive ticker reference snapshot, paginating until exhausted."""
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
        records_per_page: list[int] = []
        response_hashes: list[str] = []
        next_url: str | None = None
        page = 0
        exhausted = False
        hit_max = False

        while page < safety_max_pages:
            page += 1
            if next_url:
                url = next_url if "apiKey=" in next_url else f"{next_url}&apiKey={self.api_key}"
            else:
                url = self._url("/v3/reference/tickers", base_params)

            data, _status, error, resp_hash, req_time = self._fetch_json(
                url,
                endpoint_pattern="/v3/reference/tickers",
                req_fp_obj={"endpoint": "tickers", "date": pit_date, "active": active, "page": page},
            )

            provenance.append(
                ProvenanceProviderRecord(
                    record_id=f"prov_massive_tickers_{pit_date}_{page}",
                    data_family="security_master",
                    provider_name="massive",
                    provider_role="primary",
                    endpoint_url_pattern="/v3/reference/tickers",
                    retrieval_timestamp_utc=req_time,
                    request_fingerprint_sha256=_json_hash({"endpoint": "tickers", "date": pit_date, "active": active, "page": page}),
                    response_sha256=resp_hash,
                )
            )
            response_hashes.append(resp_hash)

            if error:
                raise RuntimeError(
                    f"Massive reference snapshot failed for {pit_date} (active={active}, page={page}): {error}"
                )
            if not isinstance(data, dict):
                break

            results = data.get("results", [])
            records_per_page.append(len(results))
            all_results.extend(results)

            raw_next = data.get("next_url")
            next_url = raw_next if isinstance(raw_next, str) and raw_next.strip() else None
            if not next_url:
                exhausted = True
                break

        if not exhausted and page >= safety_max_pages and next_url:
            hit_max = True

        first_sym = all_results[0].get("ticker") if all_results else None
        last_sym = all_results[-1].get("ticker") if all_results else None

        meta = SnapshotPaginationMeta(
            pit_date=pit_date,
            active=active,
            pages_fetched=page,
            records_per_page=records_per_page,
            total_records=len(all_results),
            pagination_exhausted_normally=exhausted,
            safety_max_pages_hit=hit_max,
            first_ticker=first_sym,
            last_ticker=last_sym,
            response_hashes=response_hashes,
            is_complete=(exhausted and not hit_max),
        )

        return all_results, provenance, meta

    def fetch_ticker_reference(
        self,
        ticker: str,
        pit_date: str | None = None,
        active: bool | None = None,
    ) -> tuple[list[dict[str, Any]], list[ProvenanceProviderRecord]]:
        """Fetch reference records for a specific ticker symbol, optionally bounded by PIT date and active status."""
        params: dict[str, Any] = {"ticker": ticker.upper()}
        if pit_date:
            params["date"] = pit_date
        if active is not None:
            params["active"] = "true" if active else "false"

        url = self._url("/v3/reference/tickers", params)
        fp_obj = {"endpoint": "tickers", "ticker": ticker.upper(), "date": pit_date, "active": active}
        data, _status, _error, resp_hash, req_time = self._fetch_json(
            url,
            endpoint_pattern="/v3/reference/tickers",
            req_fp_obj=fp_obj,
        )
        provenance = [
            ProvenanceProviderRecord(
                record_id=f"prov_ref_{resp_hash[:16]}",
                data_family="security_reference",
                provider_name="massive",
                provider_role="primary",
                endpoint_url_pattern="/v3/reference/tickers",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash(fp_obj),
                response_sha256=resp_hash,
            )
        ]
        results = data.get("results", []) if isinstance(data, dict) else []
        return results, provenance

    def fetch_corporate_actions(
        self, ticker: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[ProvenanceProviderRecord]]:
        """Fetch split and dividend events for ticker."""
        provenance: list[ProvenanceProviderRecord] = []

        # Splits
        split_url = self._url("/v3/reference/splits", {"ticker": ticker.upper(), "limit": 1000})
        split_fp = {"ticker": ticker.upper(), "event": "split"}
        data, _status, error, resp_hash, req_time = self._fetch_json(
            split_url,
            endpoint_pattern="/v3/reference/splits",
            req_fp_obj=split_fp,
        )
        splits = data.get("results", []) if isinstance(data, dict) and not error else []
        provenance.append(
            ProvenanceProviderRecord(
                record_id=f"prov_split_{ticker.upper()}",
                data_family="corporate_actions",
                provider_name="massive",
                provider_role="primary",
                endpoint_url_pattern="/v3/reference/splits",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash(split_fp),
                response_sha256=resp_hash,
            )
        )

        # Dividends
        div_url = self._url("/v3/reference/dividends", {"ticker": ticker.upper(), "limit": 1000})
        div_fp = {"ticker": ticker.upper(), "event": "dividend"}
        data, _status, error, resp_hash, req_time = self._fetch_json(
            div_url,
            endpoint_pattern="/v3/reference/dividends",
            req_fp_obj=div_fp,
        )
        dividends = data.get("results", []) if isinstance(data, dict) and not error else []
        provenance.append(
            ProvenanceProviderRecord(
                record_id=f"prov_div_{ticker.upper()}",
                data_family="corporate_actions",
                provider_name="massive",
                provider_role="primary",
                endpoint_url_pattern="/v3/reference/dividends",
                retrieval_timestamp_utc=req_time,
                request_fingerprint_sha256=_json_hash(div_fp),
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
        cache: ResponseCache | None = None,
    ) -> None:
        self.budget = budget or RequestBudget()
        self._request_func = request_func
        self.cache = cache

    def _fetch_json(
        self,
        url: str,
        endpoint_pattern: str | None = None,
        req_fp_obj: Any = None,
    ) -> tuple[dict[str, Any], str, str]:
        sanitized = sanitize_url(url)
        req_fp = _json_hash(req_fp_obj if req_fp_obj is not None else {"url": sanitized})
        req_time = _now_utc()

        if self.cache:
            cached_data, cached_sha, cached_ts = self.cache.get_json(sanitized, req_fp)
            if cached_data is not None and isinstance(cached_data, dict):
                return cached_data, cached_sha or "", cached_ts or req_time

        self.budget.charge(1)
        if self._request_func:
            try:
                res = self._request_func(url)
            except Exception:  # noqa: BLE001
                return {}, "", req_time
            body = res[0] if isinstance(res, tuple) else res
            h = hashlib.sha256(body).hexdigest()
            try:
                parsed = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                return {}, h, req_time
            if self.cache and isinstance(parsed, dict):
                self.cache.set(
                    sanitized,
                    req_fp,
                    body,
                    endpoint_pattern=endpoint_pattern,
                    retrieval_timestamp_utc=req_time,
                )
            return parsed, h, req_time

        req = urllib.request.Request(url, headers={"User-Agent": self._USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                h = hashlib.sha256(body).hexdigest()
                parsed = json.loads(body.decode("utf-8"))
                if self.cache and isinstance(parsed, dict):
                    self.cache.set(
                        sanitized,
                        req_fp,
                        body,
                        endpoint_pattern=endpoint_pattern,
                        retrieval_timestamp_utc=req_time,
                    )
                return parsed, h, req_time
        except Exception:  # noqa: BLE001
            return {}, "", req_time

    def fetch_submissions(self, cik: str) -> tuple[dict[str, Any], list[ProvenanceProviderRecord]]:
        padded = cik.zfill(10)
        url = f"{self._BASE}/submissions/CIK{padded}.json"
        req_fp = _json_hash({"cik": padded, "endpoint": "submissions"})
        data, h, retrieval_ts = self._fetch_json(
            url,
            endpoint_pattern="/submissions/CIK{cik}.json",
            req_fp_obj={"cik": padded, "endpoint": "submissions"},
        )
        prov = [
            ProvenanceProviderRecord(
                record_id=f"prov_edgar_sub_{padded}",
                data_family="issuer_fundamentals",
                provider_name="sec_edgar",
                provider_role="primary",
                endpoint_url_pattern="/submissions/CIK{cik}.json",
                retrieval_timestamp_utc=retrieval_ts,
                request_fingerprint_sha256=req_fp,
                response_sha256=h,
            )
        ]
        return data, prov

    def fetch_company_facts(self, cik: str) -> tuple[dict[str, Any], list[ProvenanceProviderRecord]]:
        padded = cik.zfill(10)
        url = f"{self._BASE}/api/xbrl/companyfacts/CIK{padded}.json"
        req_fp = _json_hash({"cik": padded, "endpoint": "companyfacts"})
        data, h, retrieval_ts = self._fetch_json(
            url,
            endpoint_pattern="/api/xbrl/companyfacts/CIK{cik}.json",
            req_fp_obj={"cik": padded, "endpoint": "companyfacts"},
        )
        prov = [
            ProvenanceProviderRecord(
                record_id=f"prov_edgar_facts_{padded}",
                data_family="issuer_fundamentals",
                provider_name="sec_edgar",
                provider_role="primary",
                endpoint_url_pattern="/api/xbrl/companyfacts/CIK{cik}.json",
                retrieval_timestamp_utc=retrieval_ts,
                request_fingerprint_sha256=req_fp,
                response_sha256=h,
            )
        ]
        return data, prov

    @staticmethod
    def get_accession_acceptance_map(submissions: dict[str, Any]) -> dict[str, str]:
        """Extract accessionNumber -> acceptanceDateTime mapping from SEC submissions JSON."""
        acc_map: dict[str, str] = {}
        if not submissions or not isinstance(submissions, dict):
            return acc_map
        recent = submissions.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return acc_map
        accessions = recent.get("accessionNumber", [])
        acceptance_times = recent.get("acceptanceDateTime", [])
        if isinstance(accessions, list) and isinstance(acceptance_times, list):
            for accn, dt in zip(accessions, acceptance_times):
                if accn and dt:
                    acc_map[str(accn)] = str(dt)
        return acc_map

    @staticmethod
    def get_former_names_history(submissions: dict[str, Any]) -> list[dict[str, str]]:
        """Extract former names and effective date ranges from SEC submissions JSON."""
        if not submissions or not isinstance(submissions, dict):
            return []
        raw_names = submissions.get("formerNames", [])
        history: list[dict[str, str]] = []
        if isinstance(raw_names, list):
            for item in raw_names:
                if isinstance(item, dict) and item.get("name"):
                    from_dt = str(item.get("from") or "")[:10]
                    to_dt = str(item.get("to") or "")[:10]
                    history.append({
                        "name": str(item.get("name")),
                        "from": from_dt,
                        "to": to_dt,
                    })
        return history


def resolve_credentials() -> dict[str, str | None]:
    """Load runtime provider credentials safely without printing values."""
    settings = load_runtime_settings()
    return {
        "massive_api_key": settings.data.massive_api_key,
        "alpaca_api_key": settings.data.alpaca_api_key,
        "alpaca_secret_key": settings.data.alpaca_secret_key,
    }
