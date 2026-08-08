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

from .models import PITObservation, ProviderCandidateResult, ProviderDisposition, hash_bytes

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

    def _canonicalize_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keys = ("symbol", "name", "exchange", "assetType", "ipoDate", "delistingDate", "status")
        canonical = []
        for row in rows:
            item: dict[str, Any] = {}
            for k in keys:
                v = row.get(k)
                if v is not None:
                    item[k] = str(v).strip()
            canonical.append(item)
        canonical.sort(key=lambda r: (r.get("symbol", ""), r.get("exchange", ""), r.get("assetType", "")))
        return canonical

    def _hash_rows(self, rows: list[dict[str, Any]]) -> str:
        encoded = json.dumps(self._canonicalize_rows(rows), sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hash_bytes(encoded)

    def _audit_duplicates(
        self,
        rows: list[dict[str, Any]],
        pit_date: str,
        state: str,
    ) -> tuple[int, int, int, list[dict[str, Any]]]:
        blank = 0
        symbol_map: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                blank += 1
                continue
            symbol_map.setdefault(symbol, []).append(row)

        duplicate_count = 0
        unresolved = 0
        details: list[dict[str, Any]] = []
        for symbol, group in symbol_map.items():
            if len(group) > 1:
                duplicate_count += 1
                # Resolvable only if every non-empty identity field is identical.
                resolvable = False
                for field in ("exchange", "assetType", "ipoDate"):
                    values = {str(g.get(field) or "").strip() for g in group if g.get(field)}
                    if len(values) == 1 and values != {""}:
                        resolvable = True
                        break
                if not resolvable:
                    unresolved += 1
                details.append({
                    "ticker": symbol,
                    "pit_date": pit_date,
                    "state": state,
                    "occurrences": len(group),
                    "resolvable": resolvable,
                })

        return blank, duplicate_count, unresolved, details

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
        headers = tuple(reader.fieldnames or ())
        missing = _EXPECTED_COLUMNS - set(headers)
        if missing:
            error = f"missing required columns: {sorted(missing)}"
            return [], PITObservation(
                provider="alpha_vantage",
                pit_date=pit_date,
                state=state,
                requested_at=start.isoformat(timespec="microseconds"),
                elapsed_seconds=elapsed,
                row_count=0,
                column_headers=headers,
                raw_sha256="",
                http_status=status,
                error=error,
            )

        rows = [row for row in reader if any(v.strip() for v in row.values())]
        raw_sha = self._hash_rows(rows)
        blank, duplicate_count, unresolved, _ = self._audit_duplicates(rows, pit_date, state)
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
            page_count=1,
            first_page_count=len(rows),
            last_page_count=len(rows),
            pagination_complete=True,
            full_snapshot_sha256=raw_sha,
            canonical_ticker_count=len({str(r.get("symbol") or "").strip() for r in rows if str(r.get("symbol") or "").strip()}),
            blank_ticker_count=blank,
            duplicate_ticker_count=duplicate_count,
            unresolved_duplicate_count=unresolved,
        )
        return rows, obs

    def probe_provider(
        self,
        pit_dates: tuple[str, ...],
        states: tuple[str, ...] = ("active", "delisted"),
        *,
        probe_version: int = 3,
    ) -> ProviderCandidateResult:
        """Probe all PIT dates and states, including a single repeatability check per date/state."""
        observations: list[PITObservation] = []
        security_type_counts: dict[str, int] = {}
        exchange_counts: dict[str, int] = {}
        errors: list[str] = []
        all_blank = 0
        all_duplicate = 0
        all_unresolved = 0
        any_lifecycle = False

        for pit_date in pit_dates:
            for state in states:
                rows, obs = self.fetch_listing(pit_date, state)
                if obs.error:
                    errors.append(f"{pit_date}/{state}: {obs.error}")
                    continue
                for row in rows:
                    asset = row.get("assetType", "").strip()
                    if asset:
                        security_type_counts[asset] = security_type_counts.get(asset, 0) + 1
                    exchange = row.get("exchange", "").strip()
                    if exchange:
                        exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
                    if row.get("ipoDate") or row.get("delistingDate"):
                        any_lifecycle = True

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
                    repeat_match=(repeat_obs.raw_sha256 == obs.raw_sha256 and repeat_obs.raw_sha256 is not None),
                    repeat_seconds=repeat_obs.elapsed_seconds,
                    http_status=repeat_obs.http_status,
                    error=repeat_obs.error,
                    page_count=1,
                    first_page_count=repeat_obs.row_count,
                    last_page_count=repeat_obs.row_count,
                    pagination_complete=True,
                    full_snapshot_sha256=repeat_obs.raw_sha256,
                    canonical_ticker_count=repeat_obs.canonical_ticker_count,
                    blank_ticker_count=repeat_obs.blank_ticker_count,
                    duplicate_ticker_count=repeat_obs.duplicate_ticker_count,
                    unresolved_duplicate_count=repeat_obs.unresolved_duplicate_count,
                )
                observations.append(repeat_obs)
                if repeat_obs.error:
                    errors.append(f"{pit_date}/{state} repeat: {repeat_obs.error}")
                else:
                    all_blank += repeat_obs.blank_ticker_count
                    all_duplicate += repeat_obs.duplicate_ticker_count
                    all_unresolved += repeat_obs.unresolved_duplicate_count
                time.sleep(_MIN_INTERVAL_SECONDS)

        return ProviderCandidateResult(
            provider="alpha_vantage",
            target_entitlement="free LISTING_STATUS",
            probe_version=probe_version,
            observations=tuple(observations),
            capability_rows=(),
            security_type_counts=security_type_counts,
            exchange_counts=exchange_counts,
            primary_exchange_field="exchange",
            security_type_field="assetType",
            delisting_date_field="delistingDate",
            listing_date_field="ipoDate",
            error="; ".join(errors) if errors else None,
            ticker_types=(),
            taxonomy_mapping={},
            taxonomy_endpoint_verified=False,
            taxonomy_sha256=None,
            stock_type_allowlist=(),
            blank_symbol_count=all_blank,
            duplicate_symbol_count=all_duplicate,
            unresolved_duplicate_count=all_unresolved,
            max_pages_active=1,
            max_pages_inactive=1,
            estimated_http_calls_48_months=len(pit_dates) * len(states) * 48,
            estimated_collection_time_48_months_seconds=len(pit_dates) * len(states) * 48 * _MIN_INTERVAL_SECONDS,
            lifecycle_fields_present=("ipoDate", "delistingDate") if any_lifecycle else (),
            full_snapshot_repeat_match=all(
                obs.repeat_match for obs in observations if obs.repeat_match is not None
            ) if observations else False,
            stable_identity_fields=("symbol",),
            date_semantics_note="date and state parameters sent per official LISTING_STATUS contract; response must be historical as-of date",
            otc_rule_note="assetType must explicitly identify OTC or exchange field must distinguish OTC venues; unmapped assetType is ineligible",
            exchange_or_otc_policy_version="preregistered_alpha_vantage_listing_status_asset_type_and_exchange",
        )

    def disposition(
        self,
        pit_dates: tuple[str, ...],
        dataset: str,
        credential_available: bool,
    ) -> ProviderDisposition:
        return ProviderDisposition(
            provider="alpha_vantage",
            dataset=dataset,
            pit_dates=pit_dates,
            credential_available=credential_available,
            probe_executed=False,
            disposition="not_attempted",
            reason="Probe not executed",
        )
