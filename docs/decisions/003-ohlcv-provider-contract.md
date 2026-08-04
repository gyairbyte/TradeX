# ADR 003: OHLCV Provider Contract and Error Handling

## Status

Accepted

## Context

TradeX supports multiple OHLCV sources (Yahoo, Alpaca, IBKR, Schwab). Signal code must work with any provider, and callers must understand when data is missing, stale, or from an unexpected source.

## Decision

All provider implementations return the same canonical DataFrame:

- Columns: `open`, `high`, `low`, `close`, `volume` (lowercase).
- Index: timezone-aware `datetime` named `datetime`, sorted ascending.
- MultiIndex columns are flattened and lowercased before returning.
- Rows with any missing OHLCV field are dropped by default.
- Empty DataFrames carry the canonical columns and a UTC `DatetimeIndex`.

Supported canonical providers are `yahoo`, `alpaca`, `ibkr`, and `schwab`. Provider selection follows explicit argument > `DATA_PROVIDER` setting > `yahoo` default.

Error classification:

- `ProviderTransientError` for retryable network issues.
- `ProviderAuthenticationError` for missing credentials or tokens.
- `ProviderConfigurationError` for missing packages or unsafe local settings.
- `ProviderCapabilityError` for unsupported capabilities or data sources.
- `ProviderDataUnavailableError` for empty or unusable symbol/date data.
- `ProviderResponseError` for malformed non-retryable responses.

Retries are disabled by default and capped at 3 extra attempts. Fallback is disabled unless explicitly configured via `OHLCV_FALLBACK_ORDER` or the `fallback_order` argument; fallback operates at whole-scan level and stops at the first provider that returns any usable data.

## Consequences

- Signal code is provider-agnostic.
- Callers can distinguish data failure from zero-signal scans.
- Explicit fallback configuration prevents silent provider switches.
- Schwab replaces the deprecated TD Ameritrade API.
