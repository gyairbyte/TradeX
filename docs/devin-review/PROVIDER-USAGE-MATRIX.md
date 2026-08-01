# Provider-Usage Matrix

This matrix inventories which TradeX features touch market-data sources, which abstraction they use, and how source selection works.

## Capability classification

| Capability | Central contract | Specialized source | Notes |
|---|---|---|---|
| Canonical OHLCV (intraday / short / long) | `tradex.data.fetcher.fetch(ticker, timeframe, provider=None)` | n/a | `DATA_PROVIDER` default; explicit `provider` overrides. |
| Date-ranged daily OHLCV | `tradex.data.history.fetch_daily_history(ticker, start, end, provider=None)` | n/a | Used by pattern mining and outcome tracker. `DATA_PROVIDER` default; explicit `provider` overrides. Yahoo and Schwab supported; Alpaca/IBKR raise `ProviderCapabilityError`. |
| Extended-hours / pre-market quote | `tradex.premarket.gap_scanner.get_premarket_price(ticker, provider=None)` | n/a | Currently only Yahoo. Schwab/other raise `ProviderCapabilityError`. |
| Options chain / flow | `tradex.options.flow.get_flow(ticker, source=None)` | `OPTIONS_DATA_SOURCE` env var, `source` argument | Allowed: `auto`, `unusual_whales`, `tradier`, `yahoo`. Explicit paid sources do not fall back. |
| Earnings calendar | `tradex.earnings.calendar.get_next_earnings(ticker, source=None)` | `EARNINGS_DATA_SOURCE` env var, `source` argument | Only Yahoo supported; other sources raise `ProviderCapabilityError`. Cached 24h. |
| Fundamental / market-cap ranking | `tradex.watchlists.refresh.fetch_market_caps(tickers, source=None)` | `MARKET_CAP_DATA_SOURCE` env var | Yahoo supported; Schwab supported only if configured. Used for S&P 100 refresh. |
| Index / constituent reference | `tradex.watchlists.refresh` Wikipedia helpers | n/a | S&P 500 / Dow / NDX / Russell 1000 constituents scraped from Wikipedia. Not a market-data provider. |

## Feature matrix

| Feature | File(s) | OHLCV/data source | Uses central `fetch()`? | Uses `history.fetch_daily_history()`? | Can use Schwab now? | Source controls |
|---|---|---|---|---|---|---|
| Main screener | `tradex/screener/engine.py` | `fetch(ticker, tf_key, provider=provider)` | Yes | No | Yes | `DATA_PROVIDER` / explicit `provider` |
| Intraday scoring | `tradex/signals/intraday.py` | `fetch()` via screener | Yes | No | Yes, via propagated provider | n/a |
| Short-term scoring | `tradex/signals/short_term.py` | `fetch()` via screener | Yes | No | Yes, via propagated provider | n/a |
| Long-term scoring | `tradex/signals/long_term.py` | `fetch()` via screener | Yes | No | Yes, via propagated provider | n/a |
| Confluence | `tradex/tracker/confluence.py` | `fetch(..., provider=provider)` | Yes | No | Yes | `DATA_PROVIDER` / explicit `provider` |
| Pattern matching | `tradex/patterns/matcher.py` | `fetch(..., provider=provider)` | Yes | No | Yes | `DATA_PROVIDER` / explicit `provider` |
| Pattern mining | `tradex/patterns/miner.py`, `tradex/patterns/fingerprint.py` | `fetch_daily_history(ticker, ..., provider=provider)` | No | Yes | Yes | `DATA_PROVIDER` / explicit `provider`; fingerprint cache keyed by `source` |
| Outcome tracker | `tradex/tracker/outcome_tracker.py` | `fetch_daily_history(ticker, ..., provider=provider)` | No | Yes | Yes | `DATA_PROVIDER` / explicit `provider`; timing fixed in COR-003 |
| Pre-market scanner | `tradex/premarket/gap_scanner.py` | Previous close via `fetch_daily_history`; pre-market quote via `get_premarket_price` | No | Yes (previous close only) | Previous close yes; pre-market quote no | `DATA_PROVIDER` / explicit `provider`; unsupported pre-market quote raises `ProviderCapabilityError` |
| Options flow | `tradex/options/flow.py` | Unusual Whales / Tradier / Yahoo options chains | No | No | No | `OPTIONS_DATA_SOURCE` env var or `source` argument |
| Earnings | `tradex/earnings/calendar.py` | Yahoo earnings dates | No | No | No | `EARNINGS_DATA_SOURCE` env var or `source` argument |
| Signal journal | `tradex/ui/dashboard.py` (read-only DB view) | SQLite signal history | N/A | N/A | N/A | Displays `signal_provider` and `outcome_provider`; filters/ metrics respect selected timeframe |
| Dashboard charts | `tradex/ui/dashboard.py` | `fetch(selected, tf, provider=provider)` | Yes | No | Yes | Sidebar OHLCV provider selector; drill-down uses saved scan provider |
| Watchlist refresh | `tradex/watchlists/refresh.py` | Wikipedia for constituents; Schwab for liquidity filter (optional); `fetch_market_caps` for S&P 100 ranking | No | No | Liquidity filter and market-cap source if configured | `MARKET_CAP_DATA_SOURCE` env var or `market_cap_source` argument |
| Scheduled watcher | `tradex/tracker/watcher.py` | Calls `screener_run()`, `run_confluence_screen()`, `run_outcome_pass()`, `run_gap_alerts()` with provider | Yes for scanner/confluence; `fetch_daily_history` for outcomes/pre-market | Yes | Yes for OHLCV; pre-market still Yahoo-only | `--provider` CLI flag, `DATA_PROVIDER`; persisted to `signal_history.provider` and `scan_runs.provider` |

## Key takeaways

1. `DATA_PROVIDER` and the explicit `provider` argument now control **only** central OHLCV (`fetch`) and date-ranged daily history (`fetch_daily_history`).
2. Specialized data sources (options, earnings, market-cap ranking) have their own explicit `source` arguments and environment variables:
   - `OPTIONS_DATA_SOURCE` — options flow (`auto`, `unusual_whales`, `tradier`, `yahoo`)
   - `EARNINGS_DATA_SOURCE` — earnings calendar (currently `yahoo` only)
   - `MARKET_CAP_DATA_SOURCE` — S&P 100 market-cap ranking (`yahoo`, `schwab`)
3. No feature silently falls back to Yahoo when an unsupported provider is selected. Unsupported combinations raise `ProviderCapabilityError`.
4. Fingerprint cache includes a `source` column so Yahoo-built and Schwab-built fingerprints do not mix.
5. Index constituents remain explicitly sourced from Wikipedia and are not routed through any market-data provider.
6. Signal and outcome provenance is stored in `signal_history` (`provider`, `outcome_provider`) and `scan_runs` (`provider`). Pre-PROVIDER-004 rows are labeled `unknown` and are not backfilled as Yahoo.
