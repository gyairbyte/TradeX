# Provider-Propagation Gaps (COR-004 / PROVIDER-002)

## Status after `devin/fix-provider-propagation`

The explicit `provider` argument is now propagated through the supported OHLCV workflows.

### `tradex/screener/engine.py`

- `run(..., provider=...)` accepts `provider` and passes it to `fetch(ticker, tf_key, provider=provider)` inside `_score_one()`.
- Concurrent worker calls all receive the same requested provider.

### `tradex/tracker/watcher.py`

- `run_once(..., provider=...)` passes `provider` to `screener_run()` and `_check_alerts()`.
- `_check_alerts(tickers, timeframe, provider=...)` passes `provider` to `run_confluence_screen()` and `run_match_screen()`.
- `start_loop(..., provider=...)` continues passing `provider` into scheduled `run_once` calls.
- The CLI `--provider` argument accepts `yahoo`, `schwab`, `alpaca`, or `ibkr`.

### `tradex/tracker/confluence.py`

- `run_confluence_screen(..., provider=...)` and `score_confluence(..., provider=...)` already forwarded `provider` to `fetch()`.
- `score_confluence()` was not changed; it simply received `provider` from the watcher and dashboard.

### `tradex/patterns/matcher.py` (not modified)

- `match_ticker(..., provider=...)` and `run_match_screen(..., provider=...)` already accepted `provider` and routed it to `fetch()`.
- This PR did not modify `matcher.py`; the watcher and dashboard now pass `provider` into those existing provider-aware interfaces.
- Pattern *mining* (`tradex/patterns/miner.py`) still uses `yfinance` directly for multi-year daily history and is covered by PROVIDER-003.

### `tradex/ui/dashboard.py`

- A "Data provider" selector was added to the sidebar with options `yahoo`, `schwab`, `alpaca`, and `ibkr`.
- The default selection reflects the `DATA_PROVIDER` environment variable or `yahoo`.
- The selected provider is passed to `run()`, `fetch()`, `run_confluence_screen()`, `run_match_screen()`, and `match_ticker()`.
- The current provider is displayed near the scan controls.
- Provider selection does **not** affect features that bypass the OHLCV fetcher (earnings, options, preset refresh, market-cap ranking, outcome tracker); those are documented as unchanged.

### `tradex/tracker/outcome_tracker.py`

- `_fetch_close_after()` still uses `yfinance` directly (`yf.download`) and has no `provider` parameter.
- Routing this through the central fetcher is intentionally deferred to `devin/fix-outcome-timing` (COR-003), because it involves changing the outcome eligibility/timing logic, not just propagation.

## Remaining gaps

| Module | Gap | Covered by |
|---|---|---|
| `tradex/tracker/outcome_tracker.py` | `_fetch_close_after` bypasses `fetch()` | COR-003 / `devin/fix-outcome-timing` |
| `tradex/patterns/miner.py` | Multi-year daily fingerprint mining uses `yfinance` directly | PROVIDER-003 |
| `tradex/premarket/gap_scanner.py` | Pre-market quotes use `yfinance` directly | PROVIDER-003 |
| `tradex/options/flow.py` | Options-chain data is not OHLCV | PROVIDER-003 |
| `tradex/earnings/calendar.py` | Earnings dates use `yfinance` directly | PROVIDER-003 |
| `tradex/watchlists/refresh.py` | Market-cap ranking uses `yfinance` directly | PROVIDER-003 |

## Key takeaway

Explicit provider selection now reaches every central-OHLCV consumer that already supported it. Non-OHLCV or specialized data consumers remain direct-Yahoo/direct-source and will be addressed in `devin/provider-agnostic-consumers` (PROVIDER-003) and `devin/fix-outcome-timing` (COR-003) as separate, reviewable PRs.
