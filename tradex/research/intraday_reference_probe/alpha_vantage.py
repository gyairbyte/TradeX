"""Alpha Vantage LISTING_STATUS reference probe client."""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from .models import PITObservation, ProviderCandidateResult

_BASE_URL = "https://www.alphavantage.co/query"
_MIN_INTERVAL_SECONDS = 12.1  # free-tier limit: 5 calls per minute
_EXPECTED_COLUMNS = {"symbol", "name", "exchange", "assetType", "ipoDate", "delistingDate", "status"}


class AlphaVantageReferenceClient:
    """Minimal reference client for Alpha Vantage LISTING_STATUS."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Alpha Vantage API key is required")
        self._last_request_time: float = 0.0

    def _url(self, pit_date: str, state: str) -> str:
        params = {
            "function": "LISTING_STATUS",
            "apikey": self.api_key,
            "date": pit_date,
            "state": state,
        }
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        return f"{_BASE_URL}?{query}"

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)

    def _fetch_once(self, url: str) -> tuple[bytes, int | None, str | None]:
        self._wait_for_rate_limit()
        try:
            self._last_request_time = time.monotonic()
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read(), response.getcode(), None
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return body, exc.code, str(exc)
        except Exception as exc:  # noqa: BLE001
            return b"", None, str(exc)

    def _fetch_with_retry(self, url: str) -> tuple[bytes, int | None, str | None]:
        body, status, error = self._fetch_once(url)
        if error and status in (429, 503):
            # Free tier rate limit or temporary unavailability; wait and retry once.
            time.sleep(60)
            body, status, error = self._fetch_once(url)
        return body, status, error

    def fetch_listing(self, pit_date: str, state: str) -> tuple[list[dict[str, Any]], PITObservation]:
        """Fetch one LISTING_STATUS CSV snapshot and parse it."""
        url = self._url(pit_date, state)
        start = datetime.now(UTC)
        body, status, error = self._fetch_with_retry(url)
        elapsed = (datetime.now(UTC) - start).total_seconds()

        if error and status != 200:
            return [], PITObservation(
                provider="alpha_vantage",
                pit_date=pit_date,
                state=state,
                requested_at=start.isoformat(timespec="microseconds"),
                elapsed_seconds=elapsed,
                row_count=0,
                column_headers=(),
                raw_sha256="",
                http_status=status,
                error=error,
            )

        try:
            text = body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return [], PITObservation(
                provider="alpha_vantage",
                pit_date=pit_date,
                state=state,
                requested_at=start.isoformat(timespec="microseconds"),
                elapsed_seconds=elapsed,
                row_count=0,
                column_headers=(),
                raw_sha256="",
                http_status=status,
                error=f"decode error: {exc}",
            )

        # Alpha Vantage may return an error JSON instead of CSV.
        if text.strip().startswith("{"):
            try:
                info = json.loads(text)
                error = info.get("Information", info.get("Error Message", text[:200]))
            except json.JSONDecodeError:
                error = text[:200]
            return [], PITObservation(
                provider="alpha_vantage",
                pit_date=pit_date,
                state=state,
                requested_at=start.isoformat(timespec="microseconds"),
                elapsed_seconds=elapsed,
                row_count=0,
                column_headers=(),
                raw_sha256="",
                http_status=status,
                error=f"provider message: {error}",
            )

        reader = csv.DictReader(io.StringIO(text))
        rows = [row for row in reader if any(v.strip() for v in row.values())]
        headers = tuple(reader.fieldnames or ())
        from .models import hash_bytes

        raw_sha = hash_bytes(body)
        obs = PITObservation(
            provider="alpha_vantage",
            pit_date=pit_date,
            state=state,
            requested_at=start.isoformat(timespec="microseconds"),
            elapsed_seconds=elapsed,
            row_count=len(rows),
            column_headers=headers,
            raw_sha256=raw_sha,
            http_status=status,
        )
        return rows, obs

    def probe_provider(
        self,
        pit_dates: tuple[str, ...],
        states: tuple[str, ...] = ("active", "delisted"),
    ) -> ProviderCandidateResult:
        """Probe all PIT dates and states, including a single repeatability check per date/state."""
        observations: list[PITObservation] = []
        security_type_counts: dict[str, int] = {}
        exchange_counts: dict[str, int] = {}
        errors: list[str] = []

        for pit_date in pit_dates:
            for state in states:
                rows, obs = self.fetch_listing(pit_date, state)
                if obs.error:
                    errors.append(f"{pit_date}/{state}: {obs.error}")
                else:
                    for row in rows:
                        asset = row.get("assetType", "").strip()
                        if asset:
                            security_type_counts[asset] = security_type_counts.get(asset, 0) + 1
                        exchange = row.get("exchange", "").strip()
                        if exchange:
                            exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
                    # Repeat once for reproducibility.
                    time.sleep(_MIN_INTERVAL_SECONDS)
                    _repeat_rows, repeat_obs = self.fetch_listing(pit_date, state)
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
                        errors.append(f"{pit_date}/{state} repeat: {repeat_obs.error}")
                time.sleep(_MIN_INTERVAL_SECONDS)

        return ProviderCandidateResult(
            provider="alpha_vantage",
            target_entitlement="free LISTING_STATUS",
            probe_version=1,
            observations=tuple(observations),
            capability_rows=(),
            security_type_counts=security_type_counts,
            exchange_counts=exchange_counts,
            primary_exchange_field="exchange",
            security_type_field="assetType",
            delisting_date_field="delistingDate",
            listing_date_field="ipoDate",
            error="; ".join(errors) if errors else None,
        )
