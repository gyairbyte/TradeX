# Provider-Usage Matrix

This matrix inventories which TradeX features touch market-data sources, whether they go through the central `tradex.data.fetcher` abstraction, and whether they can already use the Schwab provider.

| Feature | File(s) | Current data source | Uses central `fetch()`? | Can use Schwab now? | Required change |
|---|---|---|---|---|---|
| Main screener | `tradex/screener/engine.py` | `fetch(ticker, tf_key, provider=provider)` | Yes | Yes | Propagate `provider` from `run()` to `fetch()` — done in `devin/fix-provider-propagation` |
| Intraday scoring | `tradex/signals/intraday.py` (called by screener) | `fetch()` via screener | Yes | Yes, via propagated provider | None (uses screener's `provider`) |
| Short-term scoring | `tradex/signals/short_term.py` (called by screener) | `fetch()` via screener | Yes | Yes, via propagated provider | None (uses screener's `provider`) |
| Long-term scoring | `tradex/signals/long_term.py` (called by screener) | `fetch()` via screener | Yes | Yes, via propagated provider | None (uses screener's `provider`) |
| Confluence | `tradex/tracker/confluence.py` | `fetch(..., provider=provider)` | Yes | Yes, when called with `provider='schwab'` | `run_confluence_screen()` already accepts `provider`; watcher/dashboard now pass it |
| Pattern matching | `tradex/patterns/matcher.py` | `fetch(..., provider=provider)` | Yes | Yes | No file change needed; `match_ticker()` and `run_match_screen()` already accept `provider` and watcher/dashboard now pass it |
| Pattern mining | `tradex/patterns/miner.py` | `yfinance` directly (3 years daily) | No | No | Route historical 3-year daily mining through a provider or add a dedicated Schwab daily-history call with a longer lookback |
| Pre-market scanner | `tradex/premarket/gap_scanner.py` | `yfinance` directly (`yf.download` + `yf.Ticker.history`) | No | No | Add a provider-based pre/regular-hours quote path or Schwab `get_quotes` support |
| Options flow | `tradex/options/flow.py` | Unusual Whales / Tradier / `yfinance` fallback (`yf.Ticker`) | No (not OHLCV) | No | Schwab options-chain endpoint integration; not an OHLCV provider contract |
| Earnings | `tradex/earnings/calendar.py` | `yfinance` directly (`yf.Ticker`) | No | No | Keep Yahoo or add an alternate fundamental/calendar source; not available through Schwab market-data OHLCV |
| Outcome tracker | `tradex/tracker/outcome_tracker.py` | `yfinance` directly (`yf.download`) | No | No | Replace `_fetch_close_after` with `fetch(ticker, 'short', provider=...)` or a provider-aware close lookup. Deferred to COR-003 |
| Signal journal | `tradex/ui/dashboard.py` (read-only view of DB) | SQLite signal history | N/A | N/A | None; presentation only |
| Dashboard charts | `tradex/ui/dashboard.py` | `fetch(selected, tf, provider=provider)` | Yes | Yes | Provider selector added; selected provider passed to `fetch()` for drill-down charts |
| Scheduled watcher | `tradex/tracker/watcher.py` | Calls `screener_run()`, `run_confluence_screen()`, and `run_match_screen()` with `provider` | Yes | Yes | `run_once()` and `_check_alerts()` now forward `provider`; CLI `--provider` accepts the four supported values |
| Watchlist refresh | `tradex/watchlists/refresh.py` | Wikipedia for index constituents; Schwab for liquidity filter (optional); `yfinance` for market-cap ranking | Partial | Liquidity filter yes; market-cap ranking no | Route `_fetch_market_caps` through a provider-agnostic fundamental source or accept Schwab fundamental data |
| Alerts | `tradex/alerts/notifier.py` | Consumes coil/confluence/pattern match results | N/A | Indirectly | No direct data fetch; provider propagation fixes the upstream modules |

## Key takeaways

1. `confluence.py`, `patterns/matcher.py`, and the screener/engine now honor an explicit `provider` argument and route through `fetch()`.
2. `tracker/watcher.py` and `ui/dashboard.py` now pass `provider` into all supported OHLCV workflows.
3. Non-OHLCV or specialized data consumers (`patterns/miner.py`, `premarket/gap_scanner.py`, `options/flow.py`, `earnings/calendar.py`, `watchlists/refresh.py`, `outcome_tracker.py`) still bypass the OHLCV fetcher and will be addressed in later PRs.
4. `outcome_tracker.py` is intentionally deferred to `devin/fix-outcome-timing` (COR-003) because it involves timing/eligibility logic, not just propagation.
