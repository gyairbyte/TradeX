"""Production-facing point-in-time Massive/Polygon reference adapter (MVP-ARCH-001-R7-PIT-001B).

Provides narrow, typed, safe point-in-time security/reference data retrieval from Massive/Polygon
v3 reference ticker endpoints. Supports exact-ticker matching, active->inactive fallback, request ID
provenance, injectable transport/sleep for deterministic testing, bounded rate-limiting, and strict secret scrubbing.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from tradex.pit.models import (
    ReferenceObservationStatus,
    _parse_iso_utc,
    audit_missing_reference_fields,
    build_ambiguous_reference_fact_payload,
    build_error_reference_fact_payload,
    build_known_reference_fact_payload,
    build_unavailable_reference_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


class MassiveReferenceError(Exception):
    """Base exception for Massive reference adapter failures."""

    def __init__(self, message: str, *, request_ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.request_ids = request_ids


class MassiveAuthError(MassiveReferenceError):
    """Raised on missing credentials or authentication failure (e.g. 401)."""


class MassiveEntitlementError(MassiveReferenceError):
    """Raised when access is denied due to plan entitlements (e.g. 403)."""


class MassiveRateLimitError(MassiveReferenceError):
    """Raised when rate limits are exceeded (HTTP 429)."""


class MassiveTransientError(MassiveReferenceError):
    """Raised for retryable network/server failures (5xx, timeouts)."""


class MassiveResponseError(MassiveReferenceError):
    """Raised when the provider response is malformed or unparseable."""


def sanitize_text(text: str, secret: str | None = None) -> str:
    """Scrub secret keys, URLs containing apiKey, and private path patterns from error strings."""
    if not text:
        return ""
    cleaned = str(text)
    if secret and secret.strip():
        cleaned = cleaned.replace(secret.strip(), "[REDACTED]")
    # Scrub apiKey query parameter patterns: apiKey=...
    cleaned = re.sub(r"apiKey=[^&\s'\"<>]+", "apiKey=[REDACTED]", cleaned, flags=re.IGNORECASE)
    # Scrub absolute file paths that contain user private paths
    cleaned = re.sub(r"[A-Za-z]:\\[^:\n\r]*private[^\s'\"<>]*", "[REDACTED_PATH]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"/Users/[^/\s'\"<>]+/private[^\s'\"<>]*", "[REDACTED_PATH]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"/home/[^/\s'\"<>]+/private[^\s'\"<>]*", "[REDACTED_PATH]", cleaned, flags=re.IGNORECASE)
    return cleaned


@dataclass(frozen=True, slots=True)
class MassiveObservationResult:
    """Typed result of a prospective reference lookup for a single symbol."""

    observation_status: ReferenceObservationStatus
    symbol: str
    query_date: date
    request_ids: tuple[str, ...]
    provider_ticker: str | None
    provider_name: str | None
    provider_market: str | None
    provider_locale: str | None
    provider_active: bool | None
    provider_type_code: str | None
    provider_primary_exchange: str | None
    provider_cik: str | None
    provider_composite_figi: str | None
    provider_share_class_figi: str | None
    provider_last_updated_at: datetime | None
    provider_delisted_at: str | None
    missing_fields: tuple[str, ...]
    fact_hash: str
    fact_json: str
    error_category: str | None
    error_message: str | None


class MassiveReferenceClient:
    """Production client for Massive/Polygon prospective reference/security lookups.

    Implements local bounded rate-limiting (pacing) between outgoing requests.
    """

    DEFAULT_BASE_URL: str = "https://api.massive.com"
    DEFAULT_MIN_INTERVAL_SECONDS: float = 12.1  # ~5 requests/minute free-tier pacing

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        settings: TradeXSettings | None = None,
        min_interval_seconds: float | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        request_func: Callable[[str, dict[str, str]], tuple[bytes, int, dict[str, str]]] | None = None,
    ) -> None:
        resolved_key: str | None = None
        if api_key is not None and api_key.strip():
            resolved_key = api_key.strip()
        elif settings is not None and settings.data.massive_api_key:
            resolved_key = settings.data.massive_api_key.strip()

        self._api_key = resolved_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.min_interval_seconds = (
            min_interval_seconds
            if min_interval_seconds is not None
            else self.DEFAULT_MIN_INTERVAL_SECONDS
        )
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
        self._request_func = request_func
        self._last_request_time: float = 0.0

    def _pace(self) -> None:
        """Enforce rate-limiting interval between outgoing provider HTTP calls."""
        if self.min_interval_seconds <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval_seconds:
            sleep_duration = self.min_interval_seconds - elapsed
            self._sleep_fn(sleep_duration)
        self._last_request_time = time.monotonic()

    def _http_get(self, url: str) -> tuple[dict[str, Any], int, list[str]]:
        """Perform a single sanitized HTTP GET request with bounded pacing and request ID extraction."""
        if not self._api_key:
            raise MassiveAuthError("Massive/Polygon API key is required but not configured.")

        # Pace request
        self._pace()

        headers = {"Accept": "application/json", "User-Agent": "TradeX/1.0"}
        request_ids: list[str] = []

        if self._request_func is not None:
            try:
                body_bytes, status_code, resp_headers = self._request_func(url, headers)
            except Exception as exc:
                clean_err = sanitize_text(str(exc), self._api_key)
                raise MassiveTransientError(f"HTTP transport failed: {clean_err}") from exc
        else:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status_code = resp.getcode()
                    body_bytes = resp.read()
                    resp_headers = {k: v for k, v in resp.headers.items()}
            except urllib.error.HTTPError as exc:
                status_code = exc.code
                body_bytes = exc.read() if hasattr(exc, "read") else b""
                resp_headers = {k: v for k, v in exc.headers.items()} if hasattr(exc, "headers") else {}
            except urllib.error.URLError as exc:
                clean_err = sanitize_text(str(exc), self._api_key)
                raise MassiveTransientError(f"Network error: {clean_err}") from exc
            except Exception as exc:
                clean_err = sanitize_text(str(exc), self._api_key)
                raise MassiveTransientError(f"Unexpected request error: {clean_err}") from exc

        # Extract request ID from response headers if present
        header_req_id = resp_headers.get("X-Request-Id") or resp_headers.get("x-request-id")
        if header_req_id and isinstance(header_req_id, str) and header_req_id.strip():
            request_ids.append(header_req_id.strip())

        # Attempt to decode JSON body to extract body request_id even on error status
        parsed: Any = None
        if body_bytes:
            try:
                parsed = json.loads(body_bytes.decode("utf-8"))
                if isinstance(parsed, dict):
                    body_req_id = parsed.get("request_id")
                    if (
                        body_req_id
                        and isinstance(body_req_id, str)
                        and body_req_id.strip()
                        and body_req_id.strip() not in request_ids
                    ):
                        request_ids.append(body_req_id.strip())
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                pass

        # Check status codes
        if status_code == 401:
            raise MassiveAuthError(
                "Massive/Polygon authentication failed: invalid or unauthorized API key (HTTP 401).",
                request_ids=tuple(request_ids),
            )
        if status_code == 403:
            raise MassiveEntitlementError(
                "Massive/Polygon entitlement denied for endpoint (HTTP 403).",
                request_ids=tuple(request_ids),
            )
        if status_code == 429:
            retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
            msg = (
                f"Massive/Polygon rate limit exceeded (HTTP 429). Retry-After: {retry_after}"
                if retry_after
                else "Massive/Polygon rate limit exceeded (HTTP 429)."
            )
            raise MassiveRateLimitError(msg, request_ids=tuple(request_ids))
        if status_code >= 500:
            raise MassiveTransientError(
                f"Massive/Polygon server error (HTTP {status_code}).",
                request_ids=tuple(request_ids),
            )
        if status_code == 404:
            raise MassiveResponseError(
                "Massive/Polygon reference endpoint returned HTTP 404 Not Found.",
                request_ids=tuple(request_ids),
            )
        if status_code != 200:
            raise MassiveResponseError(
                f"Unexpected HTTP status {status_code} from Massive/Polygon.",
                request_ids=tuple(request_ids),
            )

        if not isinstance(parsed, dict):
            if body_bytes:
                clean_err = sanitize_text("Response body is not a JSON object", self._api_key)
                raise MassiveResponseError(
                    f"Malformed JSON response from Massive/Polygon: {clean_err}",
                    request_ids=tuple(request_ids),
                )
            parsed = {}

        return parsed, status_code, request_ids

    def _query_reference_tickers(
        self,
        symbol: str,
        pit_date: date,
        active: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Query /v3/reference/tickers for a specific symbol, date, and active flag."""
        params = {
            "ticker": symbol,
            "date": pit_date.isoformat(),
            "active": "true" if active else "false",
            "limit": 10,
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.base_url}/v3/reference/tickers?{query_str}&apiKey={self._api_key}"
        data, _status, req_ids = self._http_get(url)

        if "results" not in data or not isinstance(data.get("results"), list):
            raise MassiveResponseError(
                "Massive/Polygon response is missing valid 'results' list.",
                request_ids=tuple(req_ids),
            )

        results = data["results"]
        exact_matches: list[dict[str, Any]] = []
        for r in results:
            if not isinstance(r, dict):
                raise MassiveResponseError(
                    "Massive/Polygon result item is not a JSON object.",
                    request_ids=tuple(req_ids),
                )
            raw_ticker = r.get("ticker")
            if raw_ticker is not None and not isinstance(raw_ticker, str):
                raise MassiveResponseError(
                    f"Malformed 'ticker' field type ({type(raw_ticker).__name__}) in provider result item.",
                    request_ids=tuple(req_ids),
                )
            if isinstance(raw_ticker, str) and raw_ticker.strip().upper() == symbol:
                exact_matches.append(r)

        return exact_matches, req_ids

    def fetch_ticker_reference(
        self,
        symbol: str,
        capture_date: date,
    ) -> MassiveObservationResult:
        """Perform prospective two-stage reference lookup for symbol as of capture_date."""
        cleaned_symbol = symbol.strip().upper()
        if not cleaned_symbol:
            raise ValueError("Symbol must be a non-empty string.")

        all_request_ids: list[str] = []

        try:
            active_results, req_ids1 = self._query_reference_tickers(
                cleaned_symbol,
                capture_date,
                active=True,
            )
            all_request_ids.extend(req_ids1)

            if len(active_results) == 1:
                rec = active_results[0]
                return self._build_known_result(cleaned_symbol, capture_date, tuple(all_request_ids), rec)

            if len(active_results) > 1:
                return self._build_ambiguous_result(cleaned_symbol, capture_date, tuple(all_request_ids), active_results)

            # Active returned 0 results: perform inactive fallback
            inactive_results, req_ids2 = self._query_reference_tickers(
                cleaned_symbol,
                capture_date,
                active=False,
            )
            for rid in req_ids2:
                if rid not in all_request_ids:
                    all_request_ids.append(rid)

            if len(inactive_results) == 1:
                rec = inactive_results[0]
                return self._build_known_result(cleaned_symbol, capture_date, tuple(all_request_ids), rec)

            if len(inactive_results) > 1:
                return self._build_ambiguous_result(cleaned_symbol, capture_date, tuple(all_request_ids), inactive_results)

            # Both returned 0 results -> unavailable
            return self._build_unavailable_result(cleaned_symbol, capture_date, tuple(all_request_ids))

        except MassiveReferenceError as exc:
            error_cat = type(exc).__name__
            clean_msg = sanitize_text(str(exc), self._api_key)
            combined_req_ids = list(all_request_ids)
            for rid in exc.request_ids:
                if rid not in combined_req_ids:
                    combined_req_ids.append(rid)
            return self._build_error_result(cleaned_symbol, capture_date, tuple(combined_req_ids), error_cat, clean_msg)
        except Exception as exc:  # noqa: BLE001
            error_cat = type(exc).__name__
            clean_msg = sanitize_text(str(exc), self._api_key)
            return self._build_error_result(cleaned_symbol, capture_date, tuple(all_request_ids), error_cat, clean_msg)

    def _build_known_result(
        self,
        symbol: str,
        query_date: date,
        request_ids: tuple[str, ...],
        record: dict[str, Any],
    ) -> MassiveObservationResult:
        """Construct a known observation result from a single provider record."""
        # Safe-normalize and validate contract fields
        active = record.get("active")
        if active is not None and not isinstance(active, bool):
            raise MassiveResponseError(
                f"Malformed 'active' field type ({type(active).__name__}) in provider record.",
                request_ids=request_ids,
            )

        for f in (
            "ticker",
            "name",
            "market",
            "locale",
            "primary_exchange",
            "cik",
            "composite_figi",
            "share_class_figi",
            "delisted_utc",
        ):
            val = record.get(f)
            if val is not None and not isinstance(val, str):
                raise MassiveResponseError(
                    f"Malformed field type for '{f}' ({type(val).__name__}) in provider record.",
                    request_ids=request_ids,
                )

        type_code = record.get("type")
        if type_code is not None and not isinstance(type_code, str):
            raise MassiveResponseError(
                f"Malformed field type for 'type' ({type(type_code).__name__}) in provider record.",
                request_ids=request_ids,
            )

        last_updated_raw = record.get("last_updated_utc")
        if last_updated_raw is not None and not isinstance(last_updated_raw, str):
            raise MassiveResponseError(
                f"Malformed field type for 'last_updated_utc' ({type(last_updated_raw).__name__}) in provider record.",
                request_ids=request_ids,
            )

        last_updated_dt = _parse_iso_utc(last_updated_raw)
        last_updated_iso = last_updated_dt.isoformat() if last_updated_dt else None

        raw_ticker = record.get("ticker")
        ticker = raw_ticker.strip() if isinstance(raw_ticker, str) and raw_ticker.strip() else symbol
        name = record.get("name")
        market = record.get("market")
        locale = record.get("locale")
        primary_exchange = record.get("primary_exchange")
        cik = record.get("cik")
        composite_figi = record.get("composite_figi")
        share_class_figi = record.get("share_class_figi")
        delisted_utc = record.get("delisted_utc")

        missing_fields = audit_missing_reference_fields(record)

        fact_payload = build_known_reference_fact_payload(
            active=active,
            cik=cik,
            composite_figi=composite_figi,
            delisted_utc=delisted_utc,
            last_updated_utc=last_updated_iso,
            locale=locale,
            market=market,
            name=name,
            primary_exchange=primary_exchange,
            share_class_figi=share_class_figi,
            ticker=ticker,
            type_code=type_code,
        )
        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)

        return MassiveObservationResult(
            observation_status=ReferenceObservationStatus.KNOWN,
            symbol=symbol,
            query_date=query_date,
            request_ids=request_ids,
            provider_ticker=ticker,
            provider_name=name,
            provider_market=market,
            provider_locale=locale,
            provider_active=active,
            provider_type_code=type_code,
            provider_primary_exchange=primary_exchange,
            provider_cik=cik,
            provider_composite_figi=composite_figi,
            provider_share_class_figi=share_class_figi,
            provider_last_updated_at=last_updated_dt,
            provider_delisted_at=delisted_utc,
            missing_fields=missing_fields,
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
        )

    def _build_unavailable_result(
        self,
        symbol: str,
        query_date: date,
        request_ids: tuple[str, ...],
    ) -> MassiveObservationResult:
        """Construct an unavailable observation result when zero records match."""
        error_cat = "MassiveDataUnavailableError"
        error_msg = f"No Massive/Polygon reference record found for symbol {symbol} on {query_date.isoformat()}."
        fact_payload = build_unavailable_reference_fact_payload(
            ticker=symbol,
            error_category=error_cat,
            error_message=error_msg,
        )
        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)

        return MassiveObservationResult(
            observation_status=ReferenceObservationStatus.UNAVAILABLE,
            symbol=symbol,
            query_date=query_date,
            request_ids=request_ids,
            provider_ticker=None,
            provider_name=None,
            provider_market=None,
            provider_locale=None,
            provider_active=None,
            provider_type_code=None,
            provider_primary_exchange=None,
            provider_cik=None,
            provider_composite_figi=None,
            provider_share_class_figi=None,
            provider_last_updated_at=None,
            provider_delisted_at=None,
            missing_fields=(),
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=error_cat,
            error_message=error_msg,
        )

    def _build_ambiguous_result(
        self,
        symbol: str,
        query_date: date,
        request_ids: tuple[str, ...],
        candidates: Sequence[dict[str, Any]],
    ) -> MassiveObservationResult:
        """Construct an ambiguous observation result when multiple records match."""
        error_cat = "MassiveAmbiguousIdentityError"
        error_msg = (
            f"Multiple ({len(candidates)}) Massive/Polygon reference records matched exact ticker "
            f"{symbol} on {query_date.isoformat()}."
        )
        try:
            fact_payload = build_ambiguous_reference_fact_payload(
                ticker=symbol,
                candidates=candidates,
            )
        except (TypeError, ValueError) as exc:
            clean_err = sanitize_text(str(exc), self._api_key)
            raise MassiveResponseError(
                f"Malformed candidate record in ambiguous reference results for {symbol}: {clean_err}",
                request_ids=request_ids,
            ) from exc

        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)

        return MassiveObservationResult(
            observation_status=ReferenceObservationStatus.AMBIGUOUS,
            symbol=symbol,
            query_date=query_date,
            request_ids=request_ids,
            provider_ticker=None,
            provider_name=None,
            provider_market=None,
            provider_locale=None,
            provider_active=None,
            provider_type_code=None,
            provider_primary_exchange=None,
            provider_cik=None,
            provider_composite_figi=None,
            provider_share_class_figi=None,
            provider_last_updated_at=None,
            provider_delisted_at=None,
            missing_fields=(),
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=error_cat,
            error_message=error_msg,
        )

    def _build_error_result(
        self,
        symbol: str,
        query_date: date,
        request_ids: tuple[str, ...],
        error_category: str,
        error_message: str,
    ) -> MassiveObservationResult:
        """Construct an error observation result upon provider / network / auth failure."""
        fact_payload = build_error_reference_fact_payload(
            ticker=symbol,
            error_category=error_category,
            error_message=error_message,
        )
        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)

        return MassiveObservationResult(
            observation_status=ReferenceObservationStatus.ERROR,
            symbol=symbol,
            query_date=query_date,
            request_ids=request_ids,
            provider_ticker=None,
            provider_name=None,
            provider_market=None,
            provider_locale=None,
            provider_active=None,
            provider_type_code=None,
            provider_primary_exchange=None,
            provider_cik=None,
            provider_composite_figi=None,
            provider_share_class_figi=None,
            provider_last_updated_at=None,
            provider_delisted_at=None,
            missing_fields=(),
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=error_category,
            error_message=error_message,
        )
