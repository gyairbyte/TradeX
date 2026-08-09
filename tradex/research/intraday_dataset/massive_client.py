"""Massive/Polygon reference-client wrapper for the dataset build."""
from __future__ import annotations

from typing import Any

from ..intraday_reference_probe.massive import MassiveReferenceClient as _MassiveClient
from .models import PaginationPage, PITObservation, ReferenceSnapshot, json_hash


class MassiveDatasetClient:
    """Thin wrapper around the proven Massive v3 reference client."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Massive/Polygon API key is required")
        self._client = _MassiveClient(api_key.strip(), base_url=base_url)

    def fetch_taxonomy(self) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """Return code->category mapping and taxonomy rows."""
        ticker_types, error = self._client.fetch_ticker_types()
        if error:
            raise RuntimeError(f"Massive ticker types endpoint failed: {error}")
        mapping, _stock_allowlist, rows = self._client.build_taxonomy_mapping(ticker_types)
        return mapping, list(rows)

    def fetch_reference_snapshot(
        self,
        pit_date: str,
        active: bool,
        *,
        safety_max_pages: int = 50,
    ) -> ReferenceSnapshot:
        """Fetch one completely paginated Massive active or inactive PIT snapshot."""
        rows, pages, obs = self._client.fetch_tickers(
            pit_date,
            active,
            safety_max_pages=safety_max_pages,
        )

        # Convert sibling-module PITObservation into our models.PITObservation.
        our_obs = PITObservation(
            provider=obs.provider,
            pit_date=obs.pit_date,
            state=obs.state,
            requested_at=obs.requested_at,
            elapsed_seconds=obs.elapsed_seconds,
            row_count=obs.row_count,
            raw_sha256=obs.raw_sha256,
            http_status=obs.http_status,
            error=obs.error,
            page_count=obs.page_count,
            first_page_count=obs.first_page_count,
            last_page_count=obs.last_page_count,
            provider_reported_count=obs.provider_reported_count,
            pagination_complete=obs.pagination_complete,
            max_pages_reached=obs.max_pages_reached,
            repeated_cursor_detected=obs.repeated_cursor_detected,
            cycle_detected=obs.cycle_detected,
            unexpected_next_url=obs.unexpected_next_url,
            full_snapshot_sha256=obs.full_snapshot_sha256,
            canonical_ticker_count=obs.canonical_ticker_count,
            blank_ticker_count=obs.blank_ticker_count,
            duplicate_ticker_count=obs.duplicate_ticker_count,
            unresolved_duplicate_count=obs.unresolved_duplicate_count,
        )

        duplicate_details = []
        _blank, _duplicate_count, _unresolved, details = self._client._audit_duplicates(
            rows, pit_date, our_obs.state
        )
        for d in details:
            duplicate_details.append({
                "ticker": d["ticker"],
                "pit_date": d["pit_date"],
                "state": d["state"],
                "occurrences": d["occurrences"],
                "resolvable": d["resolvable"],
            })

        canonical = self._client._canonicalize_rows(rows)
        canonical_sha256 = json_hash(canonical)

        return ReferenceSnapshot(
            pit_date=pit_date,
            state=our_obs.state,
            rows=rows,
            observations=[our_obs],
            pages=[
                PaginationPage(
                    provider=p.provider,
                    pit_date=p.pit_date,
                    state=p.state,
                    page_number=p.page_number,
                    row_count=p.row_count,
                    page_sha256=p.page_sha256,
                    next_url_present=p.next_url_present,
                    next_cursor_sha256=p.next_cursor_sha256,
                    http_status=p.http_status,
                    error=p.error,
                )
                for p in pages
            ],
            raw_sha256=our_obs.raw_sha256,
            canonical_sha256=canonical_sha256,
            duplicate_details=duplicate_details,
        )
