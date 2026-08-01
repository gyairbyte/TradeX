# Provider-Propagation Gaps (COR-004 / PROVIDER-002 / PROVIDER-003)

## Status after `devin/provider-agnostic-consumers`

The explicit `provider` argument is now propagated through the supported OHLCV workflows, and each specialized market-data consumer has an explicit source policy.

### `tradex/data/fetcher.py`

- Added `ProviderCapabilityError` for unsupported provider/capability combinations.
- Added `_get_schwab_client()` helper so the daily-history abstraction can reuse the same safe Schwab authentication logic without inlining token handling.

### `tradex/data/history.py`

- New `fetch_daily_history(ticker, start, end, provider=None)` abstraction for date-ranged daily OHLCV.
- Provider resolution: explicit argument → `DATA_PROVIDER` → `yahoo`.
- Yahoo implementation uses `yf.download` with inclusive start/end semantics and normalizes columns.
- Schwab implementation uses `get_price_history_every_day` with `start_datetime` / `end_datetime`.
- Alpaca and IBKR raise `ProviderCapabilityError`.

### `tradex/tracker/outcome_tracker.py`

- `_fetch_close_after(..., provider=None)` uses `fetch_daily_history()`.
- All COR-003 timing behavior preserved (signal date excluded, `days_forward` counts trading-session rows, bounded +7 calendar-day buffer, NaN close fallback).
- `run_outcome_pass(..., provider=None)` propagates provider from the watcher/dashboard.

### `tradex/patterns/miner.py` and `tradex/patterns/fingerprint.py`

- `_fetch_history()` and `mine_events()` accept `provider` and use `fetch_daily_history()`.
- `run_full_build()` resolves the provider early and passes `source=resolved_provider` to `build_fingerprint()`.
- Fingerprint cache includes a `source` column and unique index so Yahoo and Schwab fingerprints cannot mix.
- `match_ticker()` loads the fingerprint for the same `source` as the live-data provider.

### `tradex/premarket/gap_scanner.py`

- Previous close now comes from `fetch_daily_history()` (provider-aware).
- `get_premarket_price(ticker, provider=None)` is the explicit pre-market/extended-hours quote interface.
- Currently only Yahoo supports pre-market quotes; other providers raise `ProviderCapabilityError`.
- `scan_gaps()` and `run_gap_alerts()` accept and propagate `provider`.

### `tradex/options/flow.py`

- `get_flow(ticker, source=None)` with explicit source values: `auto`, `unusual_whales`, `tradier`, `yahoo`.
- `OPTIONS_DATA_SOURCE` env var sets the default.
- `auto` follows documented priority (Unusual Whales → Tradier → Yahoo); explicit paid sources do not fall back.
- Missing credentials for an explicit paid source raise `ProviderCapabilityError`.
- `scan_unusual_flow()` and `get_put_call_sentiment()` accept and propagate `source`.

### `tradex/earnings/calendar.py`

- `get_next_earnings(ticker, source=None)` and `days_until_earnings()` accept an explicit source.
- `EARNINGS_DATA_SOURCE` env var sets the default.
- Only `yahoo` is supported; other sources raise `ProviderCapabilityError`.
- 24-hour SQLite cache now includes `source`.

### `tradex/watchlists/refresh.py`

- `fetch_market_caps(tickers, source=None)` separates market-cap fetching with explicit source (`yahoo` or `schwab`).
- `MARKET_CAP_DATA_SOURCE` env var sets the default.
- `refresh_all(top_n_per_sector, market_cap_source=None)` accepts `market_cap_source`.
- `RefreshResult` exposes `constituent_source` (`wikipedia`) and `market_cap_source`.
- Schwab liquidity filter remains optional and safe (no credentials exposure).

### `tradex/ui/dashboard.py`

- The global provider selector is now labeled **"OHLCV provider"**.
- Added independent source selectors: **Options source**, **Earnings source**, **Market-cap source**.
- All relevant call sites pass `provider`/`source`/`market_cap_source` to their consumers.
- Help text clarifies that selecting Schwab does not change options or earnings data.

### `tradex/screener/engine.py` and `tradex/tracker/confluence.py`

- `run()` and `run_confluence_screen()` now accept an optional `earnings_source` argument and pass it to `days_until_earnings()` so earnings filtering remains explicitly Yahoo-sourced independently of `DATA_PROVIDER`.

### Provider provenance (PROVIDER-004)

- `tradex/data/fetcher.py` exposes `resolve_provider()` as the single canonical OHLCV provider resolver.
- `signal_history` now has `provider` (signal OHLCV source) and `outcome_provider` (outcome OHLCV source).
- `scan_runs` now has `provider`.
- Existing databases are migrated safely; pre-PROVIDER-004 rows are labeled `unknown` and are not backfilled as Yahoo.
- `record_signals()` rejects mixed-provider result frames and explicit/DataFrame provider mismatches.
- `mark_outcome()` writes `outcome_provider` only when a valid close is resolved.
- `run_outcome_pass()` resolves the outcome provider once and passes it to `fetch_daily_history()`.
- `get_signal_journal()` exposes `signal_provider` and `outcome_provider`.
- The dashboard Scanner shows the **OHLCV Provider** column, drill-down charts use the saved scan provider, and the Signal Journal displays **Signal Provider** and **Outcome Provider** with a mismatch warning.

## Remaining intentionally deferred work

| ID | Work | Status |
|---|---|---|
| PROVIDER-004 | Persist provider/source provenance in `signal_history`, `scan_runs`, and outcomes | Completed |
| PROVIDER-005 | Define broad provider failure/fallback policy (retries, explicit fallback chains, UI error surfacing) | Proposed |
| COR-005 | Add market-hours / exchange-calendar handling for pre-market and watcher scheduling | Proposed |

## Key takeaway

Explicit provider selection reaches every OHLCV and date-ranged daily-history consumer. Specialized data sources (options, earnings, market-cap ranking) have their own explicit source controls and never silently inherit `DATA_PROVIDER` or fall back to Yahoo.
