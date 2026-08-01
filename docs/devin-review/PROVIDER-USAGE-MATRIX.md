# Provider-Usage Matrix

This matrix inventories which TradeX features touch market-data sources, whether they go through the central `tradex.data.fetcher` abstraction, and whether they can already use the Schwab provider.

| Feature | File(s) | Current data source | Uses central `fetch()`? | Can use Schwab now? | Required change |
|---|---|---|---|---|---|
| Main screener | `tradex/screener/engine.py` | `fetch()` — but ignores `provider` arg | Partial (hard-coded default) | Only if `DATA_PROVIDER=schwab` | Pass `provider` through `run()` to `fetch(ticker, tf_key, provider=provider)` |
| Intraday scoring | `tradex/signals/intraday.py` (called by screener) | `fetch()` via screener | Partial | Only via default provider | Same as main screener |
| Short-term scoring | `tradex/signals/short_term.py` (called by screener) | `fetch()` via screener | Partial | Only via default provider | Same as main screener |
| Long-term scoring | `tradex/signals/long_term.py` (called by screener) | `fetch()` via screener | Partial | Only via default provider | Same as main screener |
| Confluence | `tradex/tracker/confluence.py` | `fetch(..., provider=provider)` | Yes | Yes, when called with `provider='schwab'` | `tradex/tracker/watcher.py` calls `run_confluence_screen(tickers)` without `provider`; propagate `provider` |
| Pattern matching | `tradex/patterns/matcher.py` | `fetch(..., provider=provider)` | Yes | Yes | None for live matching; `patterns/miner.py` fingerprint mining still uses yfinance directly |
| Pattern mining | `tradex/patterns/miner.py` | `yfinance` directly (3 years daily) | No | No | Route historical 3-year daily mining through a provider or add a dedicated Schwab daily-history call with a longer lookback |
| Pre-market scanner | `tradex/premarket/gap_scanner.py` | `yfinance` directly (`yf.download` + `yf.Ticker.history`) | No | No | Add a provider-based pre/regular-hours quote path or Schwab `get_quotes` support |
| Options flow | `tradex/options/flow.py` | Unusual Whales / Tradier / `yfinance` fallback (`yf.Ticker`) | No (not OHLCV) | No | Schwab options-chain endpoint integration; not an OHLCV provider contract |
| Earnings | `tradex/earnings/calendar.py` | `yfinance` directly (`yf.Ticker`) | No | No | Keep Yahoo or add an alternate fundamental/calendar source; not available through Schwab market-data OHLCV |
| Outcome tracker | `tradex/tracker/outcome_tracker.py` | `yfinance` directly (`yf.download`) | No | No | Replace `_fetch_close_after` with `fetch(ticker, 'short', provider=...)` or a provider-aware close lookup |
| Signal journal | `tradex/ui/dashboard.py` (read-only view of DB) | SQLite signal history | N/A | N/A | None; presentation only |
| Dashboard charts | `tradex/ui/dashboard.py` | `fetch(selected, tf)` — no provider arg | Partial (uses `DATA_PROVIDER` default only) | Only via `DATA_PROVIDER=schwab` | Add a provider selector in the UI or read `DATA_PROVIDER` and pass it explicitly |
| Scheduled watcher | `tradex/tracker/watcher.py` | Calls `screener_run()` and `run_confluence_screen()` without `provider`; `_check_alerts` never receives `provider` | Partial | Only via `DATA_PROVIDER=schwab` | Pass `provider` into `screener_run()`, `run_confluence_screen()`, and `run_match_screen()` in `_check_alerts` |
| Watchlist refresh | `tradex/watchlists/refresh.py` | Wikipedia for index constituents; Schwab for liquidity filter (optional); `yfinance` for market-cap ranking | Partial | Liquidity filter yes; market-cap ranking no | Route `_fetch_market_caps` through a provider-agnostic fundamental source or accept Schwab fundamental data |
| Alerts | `tradex/alerts/notifier.py` | Consumes coil/confluence/pattern match results | N/A | Indirectly | No direct data fetch; provider propagation fixes the upstream modules |

## Key takeaways

1. Only `confluence.py` and `patterns/matcher.py` already honor an explicit `provider` argument and route through `fetch()`.
2. `screener/engine.py` and `tracker/watcher.py` define a `provider` parameter in their public API but drop it before reaching `fetch()`. This is the primary provider-propagation gap (COR-004 / PROVIDER-002).
3. Modules that need non-OHLCV data (options, earnings, market cap, pre-market quotes) bypass the OHLCV fetcher by design. Making them provider-agnostic is a separate, later project.
4. `outcome_tracker.py` fetches daily closing prices for signal outcomes — it is a good next candidate for a provider-agnostic rewrite after propagation is fixed.
