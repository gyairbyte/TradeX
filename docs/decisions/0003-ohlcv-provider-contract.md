# ADR-0003: OHLCV Provider Contract and Error Taxonomy

## Status

Accepted

## Date

2026-08-01

## Context

`tradex/data/fetcher.py` supports Yahoo, Alpaca, IBKR, and Schwab for OHLCV data. Signal code is provider-agnostic. The contract must describe only guarantees enforced across providers, while preserving explicit provider-specific limitations.

## Decision

All provider implementations return a pandas `DataFrame` with lowercase `open`, `high`, `low`, `close`, `volume` columns. MultiIndex columns are flattened and lowercased. Rows containing any missing OHLCV field are dropped by default.

Provider-specific index/timestamp guarantees differ:

- **Schwab**: `_normalize_schwab_candles` enforces a sorted, timezone-aware UTC `DatetimeIndex` named `datetime`, removes duplicate timestamps, and returns an empty DataFrame with the same canonical columns and UTC index when candles are empty.
- **Yahoo**: `normalize_yahoo_columns` flattens and lowercases columns and drops null rows. It does not independently enforce a named, timezone-aware, ascending UTC index across all possible yfinance outputs.
- **Alpaca**: converts bars to lowercase OHLCV columns, drops null rows, and converts a MultiIndex index by dropping the symbol level.
- **IBKR**: converts `ib_insync` bar output to lowercase columns and drops null rows; the `date` index is converted with `pd.to_datetime`.

Therefore, the universal cross-provider contract is: lowercase OHLCV columns and rows with any missing OHLCV field dropped (the provider adapters call `dropna()` or otherwise exclude rows missing required values; Schwab date-history normalization drops rows with null OHLCV by default). Schwab additionally guarantees sorted, de-duplicated, UTC-indexed output. Providers may differ in timestamp conventions, adjustment policies, coverage, freshness, and feeds; callers must not assume these are uniform.

Supported canonical providers: `yahoo`, `alpaca`, `ibkr`, `schwab`. Provider selection precedence: explicit `provider` argument > `settings.data.data_provider` > runtime `DATA_PROVIDER` env var > `yahoo` default (`DEFAULT_PROVIDER`).

Unknown provider names and unsupported `timeframe` strings are rejected with `ValueError` at the `resolve_provider`/`fetch` boundary before any provider implementation runs.

Error taxonomy (all subclasses of `ProviderError`):

- `ProviderTransientError`: retryable network/connection timeouts.
- `ProviderAuthenticationError`: missing credentials/tokens or auth failure.
- `ProviderConfigurationError`: missing packages, unsafe local settings.
- `ProviderCapabilityError`: unsupported provider capability in a specialized adapter.
- `ProviderDataUnavailableError`: empty or unusable symbol/date data.
- `ProviderResponseError`: malformed non-retryable response.

Retries are disabled by default (`OHLCV_MAX_RETRIES` defaults to 0), capped at 3 extra attempts, and applied only to `ProviderTransientError`.

Fallback is disabled unless configured via `OHLCV_FALLBACK_ORDER` or the `fallback_order` argument. `FetchPolicy.build` normalizes the fallback order and removes the primary provider. `fetch_multi_report` operates at whole-scan level: if the primary provider produces zero usable data for all fetch-eligible tickers, the next fallback provider is tried. Fallback stops at the first provider that returns any usable data. `FetchReport.failures` maps the tickers that still failed after the last attempted provider; these are not mixed from later providers once a fallback provider has produced usable data. `ScanReport` exposes the same information as `fetch_failures`.

Provenance: `FetchReport` records `requested_provider`, `actual_provider`, `fallback_used`, and `providers_attempted`.

## Consequences

- Signal code can rely on lowercase OHLCV columns.
- Callers can distinguish data failure from zero-signal scans.
- Explicit fallback prevents silent provider switches.
- Provider-specific differences in adjustment, timestamps, and coverage are documented rather than hidden.
- Schwab is the only provider with deterministic, credential-free tests enforcing the full UTC-index contract (`tests/data/test_schwab_provider.py`).

## Rejected alternatives

- Enforcing full UTC index normalization on all providers at this layer: rejected because Yahoo, Alpaca, and IBKR clients return heterogeneous index types and the current code does not normalize them. Schwab is the only provider with explicit normalization tests.
- Silent Yahoo fallback: rejected in favor of explicit `OHLCV_FALLBACK_ORDER`.
- Mixing successful tickers from multiple fallback providers: rejected because `fetch_multi_report` stops at the first provider with any usable data to keep provenance unambiguous.

## References

- `tradex/data/fetcher.py` (`_fetch_yahoo`, `_fetch_alpaca`, `_fetch_ibkr`, `_fetch_schwab`, `normalize_yahoo_columns`, `_normalize_schwab_candles`, `fetch_multi_report`, `FetchReport`, `FetchPolicy`, `resolve_provider`)
- `tests/data/test_fetcher.py`
- `tests/data/test_fetcher_policy.py`
- `tests/data/test_schwab_provider.py`
- `docs/PROJECT-TRACKER.md` (PROVIDER-004, PROVIDER-005)

## Supersession

None.
