# Provider-Propagation Gaps (COR-004 / PROVIDER-002)

## Independent verification

The explicit `provider` argument is introduced in several public APIs but is not consistently threaded through to `tradex.data.fetcher.fetch()`. The following call sites were verified on this branch:

### `tradex/tracker/watcher.py`

- `run_once(tickers, timeframe, min_score, provider=...)` accepts `provider` but calls:
  - `screener_run(tickers, timeframe=timeframe, min_score=min_score)` — `provider` is **not** passed.
  - `_check_alerts(tickers, timeframe)` — `provider` is **not** passed.
- `start_loop(...)` correctly passes `provider` to `run_once()`.
- `_check_alerts()` calls `run_confluence_screen(tickers)` and `run_match_screen(...)` without `provider`.

### `tradex/screener/engine.py`

- `run(..., provider=...)` accepts `provider` but `_score_one()` calls `fetch(ticker, tf_key)` — `provider` is **not** passed.

### `tradex/ui/dashboard.py`

- The dashboard has no provider selector and calls `run(watchlist, ...)` and `fetch(selected, tf)` without an explicit `provider`. It relies entirely on the `DATA_PROVIDER` environment variable.

### `tradex/tracker/outcome_tracker.py`

- `_fetch_close_after()` uses `yfinance` directly (`yf.download`) and has no `provider` parameter at all.

## Impact

- Setting `DATA_PROVIDER=schwab` in `.env` is the only way to make the screener, watcher, and dashboard use Schwab, because any explicit `provider` argument is silently ignored.
- Features that do not go through `fetch()` (pre-market gap scanner, options flow, earnings, pattern mining, outcome tracker) cannot use Schwab regardless of the environment setting.

## Recommended follow-up

Branch: `devin/fix-provider-propagation`

Scope (do not mix with this Schwab-validation PR):

1. `tradex/screener/engine.py` — thread `provider` through `run()` and into `fetch(ticker, tf_key, provider=provider)`.
2. `tradex/tracker/watcher.py` — pass `provider` to `screener_run()` and `_check_alerts()`; pass `provider` to `run_confluence_screen()` and `run_match_screen()` inside `_check_alerts()`.
3. `tradex/ui/dashboard.py` — either add a provider selector or read `DATA_PROVIDER` and pass it to all `run()` / `fetch()` / `run_confluence_screen()` / `run_match_screen()` calls.
4. `tradex/tracker/outcome_tracker.py` — rewrite `_fetch_close_after` to call `fetch(ticker, 'short', provider=...)` so outcomes resolve through the configured provider.

## Explicitly deferred

- Pattern miner (`tradex/patterns/miner.py`) needs 3 years of daily data. Schwab's current mapped `short` lookback is 120 days of daily candles. A longer daily-history call or a new `long_daily` timeframe would be needed; this is out of scope for the provider-propagation fix.
- Non-OHLCV sources (options chains, earnings dates, market-cap ranking, pre-market quotes) bypass the provider contract by design and require their own integrations.
