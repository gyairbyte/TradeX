"""Typed exceptions for provider transport, rate limit, pagination, and response failures."""
from __future__ import annotations

from typing import Any


class ProviderDataUnavailable(Exception):
    """Base exception for provider data unavailability or failure."""

    def __init__(
        self,
        message: str,
        symbol: str | None = None,
        failure_type: str = "provider_data_unavailable",
        status_code: int | None = None,
        page: int = 1,
        retry_count: int = 0,
        provenance_records: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.symbol = symbol
        self.failure_type = failure_type
        self.status_code = status_code
        self.page = page
        self.retry_count = retry_count
        self.provenance_records = provenance_records or []


class ProviderRequestFailed(ProviderDataUnavailable):
    """Transport exception, connection error, timeout, or HTTP 5xx with exhausted retries."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_type", "provider_request_failed")
        super().__init__(message, **kwargs)


class ProviderRateLimitedUnresolved(ProviderDataUnavailable):
    """HTTP 429 rate limit that remains unresolved after retry policy was exhausted."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_type", "provider_rate_limited_unresolved")
        kwargs.setdefault("status_code", 429)
        super().__init__(message, **kwargs)


class ProviderPaginationIncomplete(ProviderDataUnavailable):
    """Page 1 or subsequent page succeeded, but later page failed before normal pagination exhaustion."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_type", "provider_pagination_incomplete")
        super().__init__(message, **kwargs)


class MalformedProviderResponse(ProviderDataUnavailable):
    """Provider response body was not valid JSON or had an unexpected payload structure."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_type", "malformed_provider_response")
        super().__init__(message, **kwargs)
