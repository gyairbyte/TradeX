"""Massive / Polygon reference tickers probe client."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from .models import PITObservation, ProviderCandidateResult

_BASE_URL = "https://api.polygon.io"
_RATE_LIMIT_SECONDS = 0.2


class MassiveReferenceClient:
    """Minimal reference client for Polygon/Massive v3 reference tickers."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Massive/Polygon API key is required")
        self.base_url = (base_url or _BASE_URL).rstrip("/")

    def _url(self, path: str, params: dict[str, Any]) -> str:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        sep = "&" if query else ""
        return f"{self.base_url}{path}?{query}{sep}apiKey={self.api_key}"

    def _fetch_once(self, url: str) -> tuple[bytes, int | None, str | None]:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read(), response.getcode(), None
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return body, exc.code, str(exc)
        except Exception as exc:  # noqa: BLE001
            return b"", None, str(exc)

    def _fetch_json(self, url: str) -> tuple[dict[str, Any] | None, int | None, str | None]:
        body, status, error = self._fetch_once(url)
        if error:
            return None, status, error
        try:
            return json.loads(body.decode("utf-8")), status, None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, status, f"JSON decode error: {exc}"

    def _paginated_results(
        self,
        path: str,
        base_params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], PITObservation]:
        """Paginate through a Polygon v3 endpoint and return merged results."""
        start = datetime.now(UTC)
        all_results: list[dict[str, Any]] = []
        pages = 0
        cursor: str | None = None
        while True:
            params = dict(base_params)
            if cursor:
                params["cursor"] = cursor
            url = self._url(path, params)
            data, status, error = self._fetch_json(url)
            elapsed = (datetime.now(UTC) - start).total_seconds()
            if error:
                return all_results, PITObservation(
                    provider="massive",
                    pit_date=str(base_params.get("date", "")),
                    state=str(base_params.get("active", "")),
                    requested_at=start.isoformat(timespec="microseconds"),
                    elapsed_seconds=elapsed,
                    row_count=len(all_results),
                    column_headers=(),
                    raw_sha256="",
                    http_status=status,
                    error=error,
                )
            results = data.get("results", []) if isinstance(data, dict) else []
            all_results.extend(results)
            pages += 1
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                break
            time.sleep(_RATE_LIMIT_SECONDS)
            if pages > 500:
                break

        from .models import hash_bytes

        body_bytes = json.dumps(all_results, sort_keys=True, ensure_ascii=True).encode("utf-8")
        obs = PITObservation(
            provider="massive",
            pit_date=str(base_params.get("date", "")),
            state=str(base_params.get("active", "")),
            requested_at=start.isoformat(timespec="microseconds"),
            elapsed_seconds=elapsed,
            row_count=len(all_results),
            column_headers=(),
            raw_sha256=hash_bytes(body_bytes),
            http_status=status,
        )
        return all_results, obs

    def fetch_tickers(
        self, pit_date: str, active: bool
    ) -> tuple[list[dict[str, Any]], PITObservation]:
        params = {
            "market": "stocks",
            "locale": "us",
            "date": pit_date,
            "active": "true" if active else "false",
            "limit": 1000,
            "sort": "ticker",
            "order": "asc",
        }
        return self._paginated_results("/v3/reference/tickers", params)

    def fetch_ticker_types(self) -> tuple[list[dict[str, Any]], str | None]:
        params = {"asset_class": "stocks", "locale": "us"}
        url = self._url("/v3/reference/tickers/types", params)
        data, _status, error = self._fetch_json(url)
        if error:
            return [], error
        return data.get("results", []) if isinstance(data, dict) else [], None

    def probe_provider(
        self,
        pit_dates: tuple[str, ...],
        states: tuple[bool, ...] = (True, False),
    ) -> ProviderCandidateResult:
        observations: list[PITObservation] = []
        security_type_counts: dict[str, int] = {}
        exchange_counts: dict[str, int] = {}
        errors: list[str] = []

        for pit_date in pit_dates:
            for active in states:
                state_label = "active" if active else "inactive"
                rows, obs = self.fetch_tickers(pit_date, active)
                if obs.error:
                    errors.append(f"{pit_date}/{state_label}: {obs.error}")
                else:
                    for row in rows:
                        ttype = row.get("type", "").strip()
                        if ttype:
                            security_type_counts[ttype] = security_type_counts.get(ttype, 0) + 1
                        exchange = row.get("primary_exchange", "").strip()
                        if exchange:
                            exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
                    # Repeat once for reproducibility.
                    time.sleep(_RATE_LIMIT_SECONDS)
                    _repeat_rows, repeat_obs = self.fetch_tickers(pit_date, active)
                    repeat_obs = PITObservation(
                        provider=repeat_obs.provider,
                        pit_date=repeat_obs.pit_date,
                        state=repeat_obs.state,
                        requested_at=repeat_obs.requested_at,
                        elapsed_seconds=repeat_obs.elapsed_seconds,
                        row_count=repeat_obs.row_count,
                        column_headers=repeat_obs.column_headers,
                        raw_sha256=repeat_obs.raw_sha256,
                        repeat_sha256=obs.raw_sha256,
                        repeat_match=(repeat_obs.raw_sha256 == obs.raw_sha256),
                        repeat_seconds=repeat_obs.elapsed_seconds,
                        http_status=repeat_obs.http_status,
                        error=repeat_obs.error,
                    )
                    observations.append(repeat_obs)
                    if repeat_obs.error:
                        errors.append(f"{pit_date}/{state_label} repeat: {repeat_obs.error}")
                time.sleep(_RATE_LIMIT_SECONDS)

        return ProviderCandidateResult(
            provider="massive",
            target_entitlement="current Gary entitlement",
            probe_version=1,
            observations=tuple(observations),
            capability_rows=(),
            security_type_counts=security_type_counts,
            exchange_counts=exchange_counts,
            primary_exchange_field="primary_exchange",
            security_type_field="type",
            delisting_date_field="delisting_utc",
            listing_date_field=None,
            error="; ".join(errors) if errors else None,
        )
