# TradeX Recommended Roadmap

This roadmap divides the audit recommendations into small, reviewable projects. Each project addresses one coherent objective and can be delivered as a standalone pull request. The order is chosen to maximize safety: correctness and data integrity come before new features or backtesting.

---

## Project 1: Correctness and data integrity

**Objective:** Fix the confirmed bugs that make the signal journal, confluence, and watcher unreliable.

**Reason:** Without correct data, no downstream feature can be trusted.

**Files likely affected:**
- `tradex/tracker/confluence.py` (empty DataFrame, missing-timeframe handling)
- `tradex/tracker/outcome_tracker.py` (MultiIndex columns, early resolution)
- `tradex/tracker/watcher.py` (provider propagation, market-hours check optional)
- `tradex/signals/*.py` (none for correctness, but tests needed)

**Risks:** Low. These are isolated bug fixes with no UI redesign.

**Acceptance criteria:**
- `run_confluence_screen([])` returns an empty DataFrame without raising.
- `_fetch_close_after` resolves an intraday outcome as soon as 1 trading day has passed.
- `_fetch_close_after` handles MultiIndex columns from yfinance.
- `run_once` passes `provider` to `screener_run` and `_check_alerts` propagates it.

**Tests required:**
- `tests/tracker/test_confluence.py`
- `tests/tracker/test_outcome_tracker.py`
- `tests/tracker/test_watcher.py`

---

## Project 2: Test coverage and CI

**Objective:** Add a `tests/` tree, fixtures, and a GitHub Actions workflow.

**Reason:** All future work depends on being able to make changes safely.

**Files likely affected:**
- `tests/**/*.py`
- `.github/workflows/ci.yml`
- `pyproject.toml` (add `pytest` and dev deps if not present)

**Risks:** Low. Adds files; does not change behavior.

**Acceptance criteria:**
- `pytest` passes in CI.
- `ruff check .` passes in CI.
- Provider-contract test exists with a mocked Yahoo/Alpaca response.

**Tests required:**
- `tests/data/test_fetcher.py`
- `tests/signals/test_indicators.py`
- `tests/conftest.py` with isolated DB fixtures

---

## Project 3: Signal-history redesign

**Objective:** Record every scan observation (or at least every ticker scanned) with a session/trading-date concept so the coil detector can see deterioration and count distinct days.

**Reason:** The coil detector and signal journal depend on accurate history.

**Files likely affected:**
- `tradex/tracker/store.py` (schema, `record_signals`)
- `tradex/tracker/analyzer.py` (coil logic)
- `tradex/screener/engine.py` (return errors/summary)
- `tradex/tracker/watcher.py` (pass `tickers_scanned`)

**Risks:** Medium. Schema change requires migration or user guidance.

**Acceptance criteria:**
- `signal_history` or a new `scan_observations` table records one row per scanned ticker per session.
- Coil detector counts distinct trading sessions, not raw scan rows.
- Existing `~/.tradex/signals.db` is either versioned or the migration is documented.

**Tests required:**
- `tests/tracker/test_store.py`
- `tests/tracker/test_analyzer.py`

---

## Project 4: Scheduler and alert reliability

**Objective:** Add timezone-aware scheduling, market-hours checks, and alert deduplication/cooldown.

**Reason:** Prevents false/spam alerts and ensures scans run at appropriate times.

**Files likely affected:**
- `tradex/tracker/watcher.py`
- `tradex/alerts/notifier.py`
- New `tradex/market_hours.py` and `tradex/alert_state.py` modules

**Risks:** Medium. New modules but behavior changes only when watcher is running.

**Acceptance criteria:**
- Watcher can be configured to skip scans outside US equity market hours.
- Scheduled jobs run at the intended US/Eastern time regardless of host timezone.
- The same coil does not alert more than once per configured cooldown window.

**Tests required:**
- `tests/tracker/test_watcher.py`
- `tests/alerts/test_notifier.py`

---

## Project 5: Backtesting foundation

**Objective:** Build a minimal, point-in-time backtesting harness that can evaluate a single signal with explicit entry, stop, target, and costs.

**Reason:** Needed to validate any trading feature before trusting it.

**Files likely affected:**
- New `tradex/backtest/` package
- `tradex/signals/*.py` (ensure scorers are pure functions)
- `tradex/screener/engine.py` (optional: make signal generation callable from backtest)

**Risks:** Medium. This is new functionality, but isolated from live paths.

**Acceptance criteria:**
- A `Backtest` class can run a signal over a historical universe.
- Outputs include win rate, expectancy, Sharpe, and max drawdown.
- Supports at least equal-weight position sizing and ATR-based stops.

**Tests required:**
- `tests/backtest/test_backtest.py`

---

## Project 6: Intraday strategy improvements

**Objective:** Redesign the intraday scorer around a specific, testable setup with VWAP, time-of-day, and liquidity context.

**Reason:** The current intraday score is too generic to be actionable.

**Files likely affected:**
- `tradex/signals/intraday.py`
- `tradex/signals/indicators.py` (add VWAP, anchored VWAP)
- `tradex/data/fetcher.py` (may need intraday volume profile)
- `tradex/ui/dashboard.py` intraday help text

**Risks:** Medium to high. Changes trading logic; must be validated with backtests.

**Acceptance criteria:**
- Intraday scorer has a documented setup hypothesis.
- New indicators are unit tested.
- Backtest shows the redesigned score outperforms the current score on a hold-out period.

**Tests required:**
- `tests/signals/test_intraday.py`
- `tests/backtest/test_intraday_strategy.py`

---

## Project 7: Short-term and long-term improvements

**Objective:** Add market regime, sector relative strength, and explicit entry/exit rules to the short-term scorer; redesign or deprioritize the long-term scorer.

**Reason:** Short-term is the most defensible timeframe; long-term needs either a clear purpose or removal.

**Files likely affected:**
- `tradex/signals/short_term.py`
- `tradex/signals/long_term.py`
- New `tradex/market_context.py`
- `tradex/data/fetcher.py` (fetch SPY/QQQ/sector data)

**Risks:** Medium. Requires careful lookahead controls.

**Acceptance criteria:**
- Short-term score includes a market-regime filter.
- Relative-strength vs. SPY is available as an input.
- Long-term either has a validated trend-following hypothesis or is removed from the default dashboard.

**Tests required:**
- `tests/signals/test_short_term.py`
- `tests/signals/test_long_term.py`

---

## Project 8: Remove or simplify low-value features

**Objective:** Decide the fate of options flow, pre-market gap scanner, and pattern matcher based on available data quality and validation results.

**Reason:** These features add UI and code complexity but may not improve decisions.

**Files likely affected:**
- `tradex/options/flow.py`
- `tradex/premarket/gap_scanner.py`
- `tradex/patterns/*`
- `tradex/ui/dashboard.py`

**Risks:** Low for quarantine; high for removal if users rely on them.

**Acceptance criteria:**
- Options flow is either gated behind a paid-data check or moved to `research/`.
- Pre-market gap scanner is clearly labeled as context-only and disabled outside pre-market hours unless explicitly enabled.
- Pattern matcher is moved to an "Experiments" tab until validated.

**Tests required:**
- `tests/options/test_flow_degradation.py`
- `tests/patterns/test_pattern_experimental.py`

---

## Project 9: UI and observability improvements

**Objective:** Split `ui/dashboard.py` into smaller components, add scan-status/error display, and improve logging.

**Reason:** A 1,721-line UI file is a maintainability and review bottleneck.

**Files likely affected:**
- `tradex/ui/dashboard.py` (shrink to a router)
- New `tradex/ui/tabs/*.py`
- `tradex/ui/components/*.py`
- `tradex/logging_config.py`

**Risks:** Medium. Refactor only; no trading-logic changes.

**Acceptance criteria:**
- No single UI file exceeds 300 lines of logic.
- Dashboard shows a summary of scan failures vs. zero-signal results.
- `print` statements in production modules are replaced with `logging` calls.

**Tests required:**
- UI tests are optional; focus on component unit tests if possible.

---

## Recommended order of execution

1. Project 1 — Correctness and data integrity
2. Project 2 — Test coverage and CI
3. Project 4 — Scheduler and alert reliability
4. Project 3 — Signal-history redesign
5. Project 5 — Backtesting foundation
6. Project 7 — Short-term and long-term improvements
7. Project 6 — Intraday strategy improvements
8. Project 8 — Remove or simplify low-value features
9. Project 9 — UI and observability improvements

This order ensures that the data layer is correct, tests are in place, and the signal journal can collect reliable history before any trading logic is redesigned or validated.
