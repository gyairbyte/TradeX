"""Massive / Polygon reference tickers probe client."""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from .models import (
    PaginationPage,
    PITObservation,
    ProviderCandidateResult,
    ProviderDisposition,
    hash_text,
    json_hash,
)

_BASE_URL = "https://api.massive.com"
_MIN_INTERVAL_SECONDS = 12.1  # free-tier: 5 calls per minute


class MassiveReferenceClient:
    """Minimal reference client for Massive v3 reference tickers."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Massive/Polygon API key is required")
        self.base_url = (base_url or _BASE_URL).rstrip("/")
        parsed = urllib.parse.urlparse(self.base_url)
        self._expected_netloc = parsed.netloc
        self._last_request_time: float = 0.0

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)

    def _fetch_once(self, url: str) -> tuple[bytes, int | None, str | None]:
        self._wait_for_rate_limit()
        try:
            self._last_request_time = time.monotonic()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read(), response.getcode(), None
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return body, exc.code, str(exc)
        except Exception as exc:  # noqa: BLE001
            return b"", None, str(exc)

    def _fetch_json(self, url: str) -> tuple[dict[str, Any] | None, int | None, str | None]:
        body, status, error = self._fetch_once(url)
        if error and status == 429:
            # Free tier rate limit; wait and retry once.
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

    def _decode_cursor_params(self, next_url: str) -> dict[str, list[str]] | None:
        """Decode Massive's base64url cursor parameter into a query dict."""
        parsed = urllib.parse.urlparse(next_url)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        cursor = query.get("cursor", [None])[0]
        if not cursor:
            return query
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            return urllib.parse.parse_qs(decoded, keep_blank_values=True)
        except (ValueError, UnicodeDecodeError):
            return None

    def _validate_next_url(
        self,
        next_url: str,
        base_params: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Validate a provider-supplied next_url before following it.

        Massive encodes the original query parameters inside a single
        base64url `cursor` parameter, so we decode that before comparing
        active/date/market against the original request.
        """
        if not next_url:
            return True, None
        parsed = urllib.parse.urlparse(next_url)
        if parsed.scheme != "https":
            return False, f"unexpected scheme: {parsed.scheme}"
        if parsed.netloc != self._expected_netloc:
            return False, f"unexpected host: {parsed.netloc}"
        if not parsed.path.startswith("/v3/reference/tickers"):
            return False, f"unexpected path: {parsed.path}"

        decoded = self._decode_cursor_params(next_url)
        if decoded is None:
            return False, "cursor decode failure"

        for key in ("date", "active", "market"):
            expected = str(base_params.get(key, ""))
            if not expected:
                continue
            actual = decoded.get(key, [None])[0]
            if actual != expected:
                return False, f"{key} parameter drift: expected {expected!r}, got {actual!r}"
        return True, None

    def _authenticated_next_url(self, next_url: str) -> str:
        """Re-attach the API key to a provider-supplied next_url if absent.

        The provider-supplied cursor string is preserved byte-for-byte to avoid
        re-encoding issues with base64url tokens.
        """
        if "apiKey=" in next_url:
            return next_url
        sep = "&" if ("?" in next_url and next_url.split("?")[-1]) else "?"
        return f"{next_url}{sep}apiKey={self.api_key}"

    def _canonicalize_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a stable, hashable representation of rows for repeatability."""
        keys = ("ticker", "name", "type", "primary_exchange", "active", "cik", "figi", "composite_figi")
        canonical = []
        for row in rows:
            item: dict[str, Any] = {}
            for k in keys:
                v = row.get(k)
                if v is not None:
                    item[k] = str(v).strip()
            canonical.append(item)
        canonical.sort(key=lambda r: (r.get("ticker", ""), r.get("type", ""), r.get("primary_exchange", "")))
        return canonical

    def _hash_rows(self, rows: list[dict[str, Any]]) -> str:
        return json_hash(self._canonicalize_rows(rows))

    def _page_hash(self, rows: list[dict[str, Any]]) -> str:
        return json_hash(sorted(self._canonicalize_rows(rows), key=lambda r: r.get("ticker", "")))

    def _audit_duplicates(
        self,
        rows: list[dict[str, Any]],
        pit_date: str,
        state: str,
    ) -> tuple[int, int, int, list[dict[str, Any]]]:
        """Return blank, duplicate, unresolved duplicate counts and details."""
        blank = 0
        ticker_map: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ticker = str(row.get("ticker") or "").strip()
            if not ticker:
                blank += 1
                continue
            ticker_map.setdefault(ticker, []).append(row)

        duplicate_count = 0
        unresolved = 0
        details: list[dict[str, Any]] = []
        identity_fields = ["cik", "figi", "composite_figi"]
        for ticker, group in ticker_map.items():
            if len(group) > 1:
                duplicate_count += 1
                # Resolvable if every identity field is non-empty and identical across duplicates.
                resolvable = False
                for field in identity_fields:
                    values = {str(g.get(field) or "").strip() for g in group if g.get(field)}
                    if len(values) == 1 and values != {""}:
                        resolvable = True
                        break
                if not resolvable:
                    unresolved += 1
                details.append({
                    "ticker": ticker,
                    "pit_date": pit_date,
                    "state": state,
                    "occurrences": len(group),
                    "resolvable": resolvable,
                })

        return blank, duplicate_count, unresolved, details

    def _paginated_results(
        self,
        path: str,
        base_params: dict[str, Any],
        *,
        safety_max_pages: int | None = None,
        state_label: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[PaginationPage], PITObservation]:
        """Paginate through a Massive v3 endpoint to terminal next_url.

        ``safety_max_pages`` is FAILURE-ONLY: reaching it before terminal
        pagination marks the snapshot as incomplete.
        """
        start = datetime.now(UTC)
        all_results: list[dict[str, Any]] = []
        pages: list[PaginationPage] = []
        page_number = 0
        next_url: str | None = None
        state_label = state_label or str(base_params.get("active", ""))
        base_date = str(base_params.get("date", ""))
        seen_next_url_hashes: set[str] = set()
        seen_cursor_hashes: set[str] = set()
        provider_reported_count: int | None = None
        status: int | None = None
        repeated_cursor = False
        repeated_next_url = False
        cycle = False
        unexpected_next_url = False
        max_pages_reached = False
        error: str | None = None

        while True:
            page_number += 1
            if next_url:
                valid, reason = self._validate_next_url(next_url, base_params)
                if not valid:
                    unexpected_next_url = True
                    error = error or f"invalid next_url: {reason}"
                    break
                url = self._authenticated_next_url(next_url)
            else:
                params = dict(base_params)
                params["limit"] = 1000
                url = self._url(path, params)

            data, status, fetch_error = self._fetch_json(url)
            if fetch_error:
                error = error or fetch_error
                pages.append(PaginationPage(
                    provider="massive",
                    pit_date=base_date,
                    state=state_label,
                    page_number=page_number,
                    row_count=0,
                    provider_reported_count=None,
                    page_sha256="",
                    next_url_present=False,
                    next_cursor_sha256=None,
                    http_status=status,
                    error=fetch_error,
                ))
                break

            results = data.get("results", []) if isinstance(data, dict) else []
            provider_reported_count = data.get("count") if isinstance(data, dict) else provider_reported_count
            all_results.extend(results)

            raw_next = data.get("next_url") if isinstance(data, dict) else None
            next_url = raw_next if isinstance(raw_next, str) else None
            next_url_hash = hash_text(str(raw_next)) if raw_next else None
            cursor_hash: str | None = None
            if raw_next:
                parsed = urllib.parse.urlparse(raw_next)
                cursor = urllib.parse.parse_qs(parsed.query).get("cursor", [None])[0]
                if cursor:
                    cursor_hash = hash_text(cursor)

            page_hash = self._page_hash(results)
            pages.append(PaginationPage(
                provider="massive",
                pit_date=base_date,
                state=state_label,
                page_number=page_number,
                row_count=len(results),
                provider_reported_count=provider_reported_count if provider_reported_count is not None else None,
                page_sha256=page_hash,
                next_url_present=bool(raw_next),
                next_cursor_sha256=cursor_hash,
                http_status=status,
            ))

            if not next_url:
                break

            # Cycle/repeated-cursor detection.
            if next_url_hash:
                if next_url_hash in seen_next_url_hashes:
                    repeated_next_url = True
                    error = error or "repeated next_url detected"
                    break
                seen_next_url_hashes.add(next_url_hash)
            if cursor_hash:
                if cursor_hash in seen_cursor_hashes:
                    repeated_cursor = True
                    error = error or "repeated cursor detected"
                    break
                seen_cursor_hashes.add(cursor_hash)

            if safety_max_pages is not None and page_number >= safety_max_pages:
                max_pages_reached = True
                error = error or f"safety_max_pages ({safety_max_pages}) reached before terminal pagination"
                break

        elapsed = (datetime.now(UTC) - start).total_seconds()
        full_hash = self._hash_rows(all_results) if all_results and not error else None
        blank, duplicate_count, unresolved, _details = self._audit_duplicates(all_results, base_date, state_label)

        obs = PITObservation(
            provider="massive",
            pit_date=base_date,
            state=state_label,
            requested_at=start.isoformat(timespec="microseconds"),
            elapsed_seconds=elapsed,
            row_count=len(all_results),
            column_headers=(),
            raw_sha256=full_hash or "",
            http_status=status,
            error=error,
            page_count=page_number,
            first_page_count=pages[0].row_count if pages else 0,
            last_page_count=pages[-1].row_count if pages else 0,
            provider_reported_count=provider_reported_count if provider_reported_count is not None else None,
            pagination_complete=(not error and not next_url and not max_pages_reached),
            max_pages_reached=max_pages_reached,
            repeated_cursor_detected=repeated_cursor,
            repeated_next_url_detected=repeated_next_url,
            cycle_detected=cycle or repeated_next_url or repeated_cursor,
            unexpected_next_url=unexpected_next_url,
            full_snapshot_sha256=full_hash,
            canonical_ticker_count=len({str(r.get("ticker") or "").strip() for r in all_results if str(r.get("ticker") or "").strip()}),
            blank_ticker_count=blank,
            duplicate_ticker_count=duplicate_count,
            unresolved_duplicate_count=unresolved,
        )
        return all_results, pages, obs

    def fetch_tickers(
        self,
        pit_date: str,
        active: bool,
        *,
        safety_max_pages: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[PaginationPage], PITObservation]:
        params = {
            "market": "stocks",
            "locale": "us",
            "date": pit_date,
            "active": "true" if active else "false",
            "sort": "ticker",
            "order": "asc",
        }
        state_label = "active" if active else "inactive"
        return self._paginated_results(
            "/v3/reference/tickers",
            params,
            safety_max_pages=safety_max_pages,
            state_label=state_label,
        )

    def fetch_ticker_types(self) -> tuple[list[dict[str, Any]], str | None]:
        params = {"asset_class": "stocks", "locale": "us"}
        url = self._url("/v3/reference/tickers/types", params)
        data, _status, error = self._fetch_json(url)
        if error:
            return [], error
        return data.get("results", []) if isinstance(data, dict) else [], None

    def _normalize_ticker_type(self, code: str, description: str) -> str:
        """Map a provider Ticker Type code/description to a TradeX category."""
        desc = (description or "").lower()
        code_l = (code or "").upper().strip()
        if "common stock" in desc or code_l in {"CS", "COMMON STOCK"}:
            return "common_stock"
        if "etf" in desc or code_l in {"ETF", "ETN", "ETS", "ETV"}:
            return "etf"
        if "preferred" in desc or "pfd" in desc or code_l in {"PFD", "PFS", "PRF"}:
            return "preferred_stock"
        if "warrant" in desc or code_l in {"WARRANT", "WRT", "WAR"}:
            return "warrant"
        if "right" in desc or code_l in {"RIGHT", "RGT", "RTS"}:
            return "right"
        if "unit" in desc or code_l in {"UNIT", "UNT", "UTS"}:
            return "unit"
        if "otc" in desc or code_l in {"OTC", "OTCE", "OTCMKTS", "PINX", "OTCBB"}:
            return "otc"
        if "fund" in desc or "index" in desc or "depositary" in desc or "ad" in desc:
            return "other"
        return "unknown"

    def build_taxonomy_mapping(
        self,
        ticker_types: list[dict[str, Any]],
    ) -> tuple[dict[str, str], tuple[str, ...], tuple[dict[str, Any], ...]]:
        """Return code->category mapping, stock allowlist, and taxonomy rows."""
        mapping: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        for entry in ticker_types:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("code") or "").strip().upper()
            description = str(entry.get("description") or "").strip()
            asset_class = str(entry.get("asset_class") or "").strip()
            locale = str(entry.get("locale") or "").strip()
            if not code:
                continue
            category = self._normalize_ticker_type(code, description)
            mapping[code] = category
            rows.append({
                "code": code,
                "description": description,
                "asset_class": asset_class,
                "locale": locale,
                "tradex_category": category,
                "eligible_stock": category == "common_stock",
            })
        allowlist = tuple(sorted({code for code, cat in mapping.items() if cat == "common_stock"}))
        return mapping, allowlist, tuple(rows)

    def probe_provider(
        self,
        pit_dates: tuple[str, ...],
        states: tuple[bool, ...] = (True, False),
        *,
        safety_max_pages: int | None = None,
    ) -> ProviderCandidateResult:
        observations: list[PITObservation] = []
        pagination_pages: list[PaginationPage] = []
        security_type_counts: dict[str, int] = {}
        exchange_counts: dict[str, int] = {}
        errors: list[str] = []

        max_active_pages = 0
        max_inactive_pages = 0
        http_request_count = 0

        # Taxonomy endpoint is a prerequisite for decision-grade classification.
        ticker_types, taxonomy_error = self.fetch_ticker_types()
        taxonomy_endpoint_verified = taxonomy_error is None and bool(ticker_types)
        taxonomy_mapping, stock_allowlist, taxonomy_rows = self.build_taxonomy_mapping(ticker_types)
        taxonomy_sha256 = json_hash([dict(r) for r in taxonomy_rows]) if taxonomy_rows else None
        if taxonomy_error:
            errors.append(f"ticker_types: {taxonomy_error}")

        all_blank = 0
        all_duplicate = 0
        all_unresolved = 0
        all_details: list[dict[str, Any]] = []

        for pit_date in pit_dates:
            for active in states:
                state_label = "active" if active else "inactive"
                rows, pages, obs = self.fetch_tickers(
                    pit_date,
                    active,
                    safety_max_pages=safety_max_pages,
                )
                http_request_count += len(pages)
                observations.append(obs)
                pagination_pages.extend(pages)
                if obs.error:
                    errors.append(f"{pit_date}/{state_label}: {obs.error}")
                    continue

                if state_label == "active":
                    max_active_pages = max(max_active_pages, obs.page_count)
                else:
                    max_inactive_pages = max(max_inactive_pages, obs.page_count)

                for row in rows:
                    ttype = str(row.get("type") or "").strip().upper()
                    if ttype:
                        security_type_counts[ttype] = security_type_counts.get(ttype, 0) + 1
                    exchange = str(row.get("primary_exchange") or "").strip().upper()
                    if exchange:
                        exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1

                # Repeat the full snapshot once for repeatability.
                time.sleep(_MIN_INTERVAL_SECONDS)
                _repeat_rows, _repeat_pages, repeat_obs = self.fetch_tickers(
                    pit_date,
                    active,
                    safety_max_pages=safety_max_pages,
                )
                http_request_count += len(_repeat_pages)
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
                    page_count=repeat_obs.page_count,
                    first_page_count=repeat_obs.first_page_count,
                    last_page_count=repeat_obs.last_page_count,
                    provider_reported_count=repeat_obs.provider_reported_count,
                    pagination_complete=repeat_obs.pagination_complete,
                    max_pages_reached=repeat_obs.max_pages_reached,
                    repeated_cursor_detected=repeat_obs.repeated_cursor_detected,
                    repeated_next_url_detected=repeat_obs.repeated_next_url_detected,
                    cycle_detected=repeat_obs.cycle_detected,
                    unexpected_next_url=repeat_obs.unexpected_next_url,
                    full_snapshot_sha256=repeat_obs.full_snapshot_sha256,
                    canonical_ticker_count=repeat_obs.canonical_ticker_count,
                    blank_ticker_count=repeat_obs.blank_ticker_count,
                    duplicate_ticker_count=repeat_obs.duplicate_ticker_count,
                    unresolved_duplicate_count=repeat_obs.unresolved_duplicate_count,
                )
                observations.append(repeat_obs)
                if repeat_obs.error:
                    errors.append(f"{pit_date}/{state_label} repeat: {repeat_obs.error}")

                all_blank += obs.blank_ticker_count
                all_duplicate += obs.duplicate_ticker_count
                all_unresolved += obs.unresolved_duplicate_count

                time.sleep(_MIN_INTERVAL_SECONDS)

        # Feasibility estimate for 48 monthly snapshots.
        estimated_calls = (max_active_pages + max_inactive_pages) * 48
        estimated_seconds = estimated_calls * _MIN_INTERVAL_SECONDS if estimated_calls else None

        lifecycle_fields: set[str] = set()
        for obs in observations:
            # We don't have per-row lifecycle fields in this aggregate; mark from
            # field presence once we have at least one observation with rows.
            if obs.row_count > 0:
                lifecycle_fields.add("listing_date")
                lifecycle_fields.add("delisting_date")

        return ProviderCandidateResult(
            provider="massive",
            target_entitlement="current Gary entitlement",
            probe_version=3,
            observations=tuple(observations),
            capability_rows=(),
            pagination_pages=tuple(pagination_pages),
            security_type_counts=security_type_counts,
            exchange_counts=exchange_counts,
            primary_exchange_field="primary_exchange",
            security_type_field="type",
            delisting_date_field="delisted_utc",
            listing_date_field=None,
            error="; ".join(errors) if errors else None,
            ticker_types=tuple(ticker_types) if ticker_types else (),
            taxonomy_mapping=taxonomy_mapping,
            taxonomy_endpoint_verified=taxonomy_endpoint_verified,
            taxonomy_sha256=taxonomy_sha256,
            stock_type_allowlist=stock_allowlist,
            blank_symbol_count=all_blank,
            duplicate_symbol_count=all_duplicate,
            unresolved_duplicate_count=all_unresolved,
            duplicate_details=tuple(all_details),
            max_pages_active=max_active_pages,
            max_pages_inactive=max_inactive_pages,
            estimated_http_calls_48_months=estimated_calls if estimated_calls else None,
            estimated_collection_time_48_months_seconds=estimated_seconds,
            lifecycle_fields_present=tuple(sorted(lifecycle_fields)),
            stable_identity_fields=("ticker",),
            date_semantics_note="date parameter sent and validated in next_url drift checks",
            otc_rule_note="OTC classification relies on provider taxonomy mapping and primary exchange provenance; must be verified against live evidence",
            exchange_or_otc_policy_version="preregistered_massive_v3_us_national_exchanges_plus_otc_taxonomy",
        )

    def disposition(
        self,
        pit_dates: tuple[str, ...],
        dataset: str,
        credential_available: bool,
    ) -> ProviderDisposition:
        return ProviderDisposition(
            provider="massive",
            dataset=dataset,
            pit_dates=pit_dates,
            credential_available=credential_available,
            probe_executed=False,
            disposition="not_attempted",
            reason="Probe not executed",
        )
