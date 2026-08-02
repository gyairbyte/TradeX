# TradeX Project Tracker

This is the master backlog for recommendations from the Devin review. Items are grouped by priority (High, Medium, Low) and then by category. Update this tracker as work is accepted, started, blocked, completed, or rejected.

---

## Legend

| Field | Meaning |
|---|---|
| **ID** | Unique short identifier. |
| **Category** | One of: Architecture, Correctness, Data integrity, Intraday trading, Short-term trading, Long-term trading, Backtesting, Testing, Scheduling, Alerts, User interface, Documentation, Cleanup, Security. |
| **Priority** | High / Medium / Low based on risk to correctness or trading decisions. |
| **Status** | Proposed / Accepted / In progress / Blocked / Completed / Rejected / Deferred. |
| **Affects trading behavior** | Yes if the change changes how signals, scores, or coils are produced; No for tests, docs, or internal refactoring. |

---

## High priority

### DATA-001: Redesign signal history to record all scan observations

- **ID:** DATA-001
- **Title:** Redesign signal history to record all scan observations
- **Category:** Data integrity
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/redesign-signal-history`
- **Problem statement:** The store only records signals that pass `min_score`. A stock whose score deteriorates disappears from history, so the coil detector cannot see fading setups, and the signal journal is incomplete.
- **Recommended action:** Add a `scan_observations` table (or widen `signal_history`) to record one row per ticker per scan session, including failures to pass `min_score`. Add a `session_id`/`trading_date` concept.
- **Reason:** Correct downstream analysis (coils, journal, outcome) depends on an accurate, complete history.
- **Dependencies:** None
- **Files likely affected:** `tradex/tracker/store.py`, `tradex/screener/engine.py`, `tradex/tracker/watcher.py`, `tradex/tracker/analyzer.py`
- **Testing requirements:** Unit and DB tests; verify all scanned tickers are recorded; verify schema migration/versioning.
- **Acceptance criteria:** `store.record_scan` accepts `(session, tickers_scanned, results)` and writes both audit and observations. Coil detector can identify fading setups.
- **Intended pull request:** `devin/redesign-signal-history`
- **Affects trading behavior:** Yes (coil detection and journal data improve)

### COIL-001: Count distinct trading sessions, not scan executions

- **ID:** COIL-001
- **Title:** Count distinct trading sessions, not scan executions
- **Category:** Data integrity
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/redesign-signal-history`
- **Problem statement:** The coil detector uses `COUNT(*)` on `signal_history` rows. If the watcher runs multiple times per day, the same trading day contributes multiple appearances.
- **Recommended action:** Group coil appearances by `session_id` or `trading_date` once signal history records sessions.
- **Reason:** A coil is a multi-day market phenomenon, not a function of scan frequency.
- **Dependencies:** DATA-001
- **Files likely affected:** `tradex/tracker/analyzer.py`, `tradex/tracker/store.py`
- **Testing requirements:** DB test with three scans in one day; verify `appearances` = 1.
- **Acceptance criteria:** Coil `appearances` reflects distinct trading sessions, not scan rows.
- **Intended pull request:** `devin/redesign-signal-history`
- **Affects trading behavior:** Yes

### COIL-002: Remove scan-frequency bias from coil strength

- **ID:** COIL-002
- **Title:** Remove scan-frequency bias from coil strength
- **Category:** Correctness
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/redesign-signal-history`
- **Problem statement:** `coil_strength` includes `appearances * 5`, so running the watcher more often mechanically increases strength.
- **Recommended action:** Replace the linear appearances term with a capped fraction of recent sessions, or remove it and rely on score/trend.
- **Reason:** Coil strength must be independent of how often the user runs the watcher.
- **Dependencies:** DATA-001, COIL-001
- **Files likely affected:** `tradex/tracker/analyzer.py`
- **Testing requirements:** Unit test with two different scan frequencies producing the same market history.
- **Acceptance criteria:** Coil strength is invariant to scan frequency for the same set of sessions.
- **Intended pull request:** `devin/fix-coil-frequency-bias`
- **Affects trading behavior:** Yes

### COR-001: Fix empty confluence result crash

- **ID:** COR-001
- **Title:** Fix empty confluence result crash
- **Category:** Correctness
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/fix-confluence-empty-result`
- **Problem statement:** `run_confluence_screen` raised `KeyError: 'confluence_score'` when no tickers met the threshold because it sorted a column-less DataFrame.
- **Recommended action:** Build the result DataFrame with explicit columns when `rows` is empty.
- **Reason:** A zero-result scan is normal and must not crash the dashboard.
- **Dependencies:** None
- **Files likely affected:** `tradex/tracker/confluence.py`
- **Testing requirements:** Unit test with `run_confluence_screen([], min_confluence=50)` and mocked tickers that do not reach the threshold.
- **Acceptance criteria:** Empty confluence input returns an empty DataFrame with the expected columns.
- **Intended pull request:** `devin/fix-confluence-empty-result`
- **Affects trading behavior:** No

### COR-002: Fix outcome tracker MultiIndex column crash

- **ID:** COR-002
- **Title:** Fix outcome tracker MultiIndex column crash
- **Category:** Correctness
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/fix-outcome-multiindex`
- **Problem statement:** `outcome_tracker._fetch_close_after` did `float(df["Close"].iloc[...])` without normalizing MultiIndex columns, causing `TypeError`.
- **Recommended action:** Apply the same normalization used in `data/fetcher.py` and use `df["close"].iloc[...]`.
- **Reason:** yfinance can return MultiIndex columns; outcome fetching must be robust.
- **Dependencies:** None
- **Files likely affected:** `tradex/tracker/outcome_tracker.py`, `tradex/data/fetcher.py`
- **Testing requirements:** Unit test with mocked yfinance responses covering single-level and MultiIndex columns, empty responses, missing close columns, and NaN close values.
- **Acceptance criteria:** `_fetch_close_after` returns the correct close for both single-level and MultiIndex responses and returns `None` for empty or unusable data.
- **Intended pull request:** `devin/fix-outcome-multiindex`
- **Affects trading behavior:** No

### COR-003: Fix outcome tracker waiting too long to resolve

- **ID:** COR-003
- **Title:** Fix outcome tracker waiting too long to resolve
- **Category:** Correctness
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/fix-outcome-timing`
- **Problem statement:** `_fetch_close_after` computed `end = after_date + days_forward + 7` and returned `None` until that full buffer date had passed, delaying resolution by ~7 extra calendar days even when the required trading-session close was already available.
- **Recommended action:** Resolve as soon as at least `days_forward` trading sessions after the signal are available in historical data; keep the +7 calendar-day buffer only as a maximum search window for weekends/holidays.
- **Reason:** The signal journal is only useful if outcomes are recorded close to the intended holding period.
- **Dependencies:** None
- **Files affected:** `tradex/tracker/outcome_tracker.py`
- **Testing:** Credential-free mocked tests cover 1-day/3-day/5-day resolution, weekend handling, holiday gaps, future/unavailable data, request boundaries, MultiIndex/single-level columns, and NaN close fallback.
- **Acceptance criteria:** An intraday signal resolves after 1 trading session, a short signal after 3, a long signal after 5; the function does not refuse to fetch solely because the maximum buffer end is in the future.
- **Deferred:** Making the outcome tracker provider-agnostic is still under PROVIDER-003 and not completed by this fix.
- **Intended pull request:** `devin/fix-outcome-timing`
- **Affects trading behavior:** No

### COR-006: Fix confluence "all timeframes aligned" mislabel

- **ID:** COR-006
- **Title:** Fix confluence "all timeframes aligned" mislabel
- **Category:** Correctness
- **Priority:** High
- **Status:** Proposed
- **Problem statement:** Confluence renormalizes weights over available timeframes and can report `"all timeframes aligned"` when only one timeframe is present.
- **Recommended action:** Require all three timeframes for a confluence score, or add a missing-timeframe penalty. Never report "all timeframes aligned" unless all three timeframes contributed.
- **Reason:** The label implies multi-timeframe agreement, which is not true when data is missing.
- **Dependencies:** None
- **Files likely affected:** `tradex/tracker/confluence.py`
- **Testing requirements:** Unit test with only intraday data available; verify tier does not claim alignment.
- **Acceptance criteria:** Confluence score and tier accurately reflect which timeframes contributed.
- **Intended pull request:** `devin/fix-confluence-missing-timeframe`
- **Affects trading behavior:** Yes (confluence output changes)

### ALERT-001: Add alert deduplication and cooldown

- **ID:** ALERT-001
- **Title:** Add alert deduplication and cooldown
- **Category:** Alerts
- **Priority:** High
- **Status:** Proposed
- **Problem statement:** The watcher fires alerts on every scan cycle for every ticker above threshold, with no persistence or cooldown.
- **Recommended action:** Introduce an alert state store keyed by `(ticker, alert_type, timeframe)` and enforce a configurable cooldown (e.g., 1 hour for coils).
- **Reason:** Prevents alert spam and respects user attention.
- **Dependencies:** None
- **Files likely affected:** `tradex/alerts/notifier.py`, `tradex/tracker/watcher.py`, new `tradex/alerts/policy.py`
- **Testing requirements:** Unit tests mocking `send_alert`; verify it is only called once per cooldown window.
- **Acceptance criteria:** Repeated checks for the same coil produce only one Discord/email message per cooldown window.
- **Intended pull request:** `devin/add-alert-cooldown`
- **Affects trading behavior:** No

### TEST-001: Complete test foundation and fixtures

- **ID:** TEST-001
- **Title:** Complete test foundation and fixtures
- **Category:** Testing
- **Priority:** High
- **Status:** In progress
- **Problem statement:** The initial local and CI test foundation is now established (`1` passing test, `7` strict `xfail`s tied to COR/DATA/COIL items, GitHub Actions running `ruff check tests` and `pytest tests -q`). Provider-contract tests and broader unit/integration coverage remain to be added.
- **Recommended action:** Add provider-contract tests for each data provider, expand unit/integration tests, and document how to run the suite. Ensure every existing `xfail` test references a specific tracker/correctness item and uses `strict=True`.
- **Reason:** Tests are a prerequisite for safely fixing correctness and redesigning trading logic.
- **Dependencies:** None
- **Files likely affected:** `tests/conftest.py`, `tests/**/*.py`
- **Testing requirements:** Local `pytest` passes; all `xfail` tests are tracked against COR/DATA/COIL IDs and use `strict=True`.
- **Acceptance criteria:** `pytest` passes locally and in CI; a provider-contract test exists; DB tests use temp files; no `xfail` test can XPASS for an unrelated reason.
- **Intended pull request:** `devin/add-ci`
- **Affects trading behavior:** No

### TEST-002: Add CI workflow

- **ID:** TEST-002
- **Title:** Add CI workflow
- **Category:** Testing
- **Priority:** High
- **Status:** Completed
- **Problem statement:** No automated CI means tests and lint are not enforced on PRs.
- **Recommended action:** Add `.github/workflows/ci.yml` that installs dependencies with `uv sync --extra dev`, runs `ruff check tests`, and runs `pytest tests -q`. Add `mypy` only after it is added as a dependency, configured, and an agreed baseline is established.
- **Reason:** Prevents regressions and ensures a consistent review process.
- **Dependencies:** TEST-001
- **Files likely affected:** `.github/workflows/ci.yml`
- **Testing requirements:** N/A
- **Acceptance criteria:** CI runs on PRs and pushes to `main`, fails on test or lint failure, and unexpected `XPASS` from `strict=True` xfails fails the build.
- **Intended pull request:** `devin/add-ci`
- **Affects trading behavior:** No

### PROVIDER-001: Validate and harden Schwab market-data provider

- **ID:** PROVIDER-001
- **Title:** Validate and harden Schwab market-data provider
- **Category:** Data provider
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/validate-schwab-provider`
- **Problem statement:** The existing Schwab provider was untested against the installed `schwab-py` version, had no canonical OHLCV contract enforcement, and lacked credential-free tests.
- **Recommended action:** Verify `schwab-py==1.5.1` compatibility, normalize Schwab candles into the canonical OHLCV DataFrame, add deterministic mocked contract tests, tighten OAuth/token safety, and add a read-only local smoke test.
- **Reason:** Schwab is the intended primary local market-data source for TradeX.
- **Dependencies:** TEST-001
- **Files likely affected:** `tradex/data/fetcher.py`, `scripts/schwab_oauth.py`, `scripts/schwab_smoke_test.py`, `.env.example`, `.gitignore`, `tests/data/test_schwab_provider.py`
- **Testing requirements:** Credential-free mocked tests covering intraday, daily, weekly, empty/malformed responses, missing credentials, client caching, and thread-safe usage. Local smoke test requires the user's own token.
- **Acceptance criteria:** `pytest tests -q` passes; `ruff check tests scripts` passes; CI runs with `--extra schwab`; no account or order endpoint is used.
- **Intended pull request:** `devin/validate-schwab-provider`
- **Affects trading behavior:** No

### PROVIDER-002: Fix provider propagation

- **ID:** PROVIDER-002
- **Title:** Fix provider propagation
- **Category:** Data provider
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/fix-provider-propagation`
- **Problem statement:** `screener/engine.run`, `tracker/watcher.run_once`, and `ui/dashboard.py` accepted or exposed `provider` but did not thread it through to `fetch()`. `outcome_tracker` and non-OHLCV consumers (earnings, options, pre-market quotes, market-cap ranking, pattern mining) bypass the OHLCV provider abstraction by design and were out of scope for this fix.
- **Recommended action:** Pass `provider` through every supported central-OHLCV `fetch()` call: screener `_score_one`, watcher `screener_run`/confluence/pattern calls, and dashboard `run()`/`fetch()`/`run_confluence_screen()`/`run_match_screen()`/`match_ticker()` calls.
- **Reason:** Users must be able to switch providers explicitly or via `DATA_PROVIDER` without silent fallback for all OHLCV workflows that already go through `fetch()`.
- **Dependencies:** PROVIDER-001
- **Files affected:** `tradex/screener/engine.py`, `tradex/tracker/watcher.py`, `tradex/ui/dashboard.py`
- **Testing:** Unit tests patch `fetch` and assert the expected `provider` is passed; tests for `run_confluence_screen` and `run_match_screen` provider propagation.
- **Acceptance criteria:** `python -m tradex.tracker.watcher --provider schwab` causes all central-OHLCV fetches to use Schwab; dashboard provider selector works.
- **Deferred to later PRs:** `outcome_tracker` provider routing remains under COR-003; pattern-mining, pre-market gap, options, watchlist market-cap, and earnings consumers are covered by PROVIDER-003.
- **Affects trading behavior:** No

### PROVIDER-003: Make remaining market-data consumers provider-agnostic

- **ID:** PROVIDER-003
- **Title:** Make remaining market-data consumers source-aware
- **Category:** Data provider
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/provider-agnostic-consumers`
- **Problem statement:** Pattern mining, pre-market gap scanner, options flow, earnings, and watchlist market-cap ranking still called Yahoo or other sources directly with no provider alternative.
- **Recommended action:** Move each non-OHLCV or specialized data need behind a small abstraction or clearly document that it is a specialized source. Add `tradex/data/history.py` for date-ranged daily OHLCV (used by outcome tracker and pattern mining) and `ProviderCapabilityError` for unsupported combinations. Add explicit source parameters/options for options, earnings, and market-cap ranking. Update dashboard selector labels and help text to show which source drives each feature.
- **Reason:** Provider independence means market-data consumers must be explicit about source and not silently fall back to Yahoo. `DATA_PROVIDER` should only control compatible OHLCV workflows.
- **Dependencies:** PROVIDER-002, COR-003
- **Files affected:** `tradex/data/fetcher.py` (shared Schwab helper, `ProviderCapabilityError`), `tradex/data/history.py` (new daily-history abstraction), `tradex/patterns/miner.py`, `tradex/patterns/fingerprint.py`, `tradex/tracker/outcome_tracker.py`, `tradex/tracker/watcher.py`, `tradex/premarket/gap_scanner.py`, `tradex/options/flow.py`, `tradex/earnings/calendar.py`, `tradex/watchlists/refresh.py`, `tradex/ui/dashboard.py`, `tradex/screener/engine.py`, `tradex/tracker/confluence.py`
- **Testing:** Credential-free mocked tests for `fetch_daily_history` (Yahoo + Schwab), outcome-tracker provider propagation, pattern-mining provider/source propagation, pre-market source separation, options source policy, earnings source policy, watchlist refresh market-cap source, and gap-scanner provider propagation.
- **Acceptance criteria:** No remaining feature module calls Yahoo directly except inside approved source adapters. `DATA_PROVIDER=schwab` does not silently relabel options, earnings, or market-cap data as Schwab. Unsupported provider/capability combinations raise `ProviderCapabilityError`. Existing `51 passed, 3 xfailed` baseline remains green.
- **Intended pull request:** `devin/provider-agnostic-consumers`
- **Affects trading behavior:** No

### PROVIDER-004: Add provider provenance

- **ID:** PROVIDER-004
- **Title:** Add provider provenance
- **Category:** Data provider
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/add-provider-provenance`
- **Problem statement:** Signal history, outcomes, and scans did not record which OHLCV provider produced the prices used for signals and outcomes.
- **Recommended action:** Add a canonical `resolve_provider()` helper in `tradex/data/fetcher.py`. Thread the resolved provider through `screener/engine.py` results and persist `provider` on `signal_history` and `scan_runs`. Add `outcome_provider` to `signal_history` and write it only when an outcome resolves successfully. Migrate existing databases safely, labeling pre-existing rows as `unknown`. Expose `signal_provider` and `outcome_provider` in the signal journal and dashboard.
- **Reason:** Provider data quality differs (delayed, real-time, adjusted); provenance is required for backtesting and for identifying data-source bugs. Outcomes may legitimately be fetched with a different provider than the original signal.
- **Dependencies:** PROVIDER-002, PROVIDER-003
- **Files affected:** `tradex/data/fetcher.py`, `tradex/data/history.py`, `tradex/screener/engine.py`, `tradex/tracker/store.py`, `tradex/tracker/outcome_tracker.py`, `tradex/tracker/watcher.py`, `tradex/ui/dashboard.py`
- **Testing:** Credential-free mocked/DB tests for `resolve_provider`, screener result provenance, SQLite schema migration, signal and scan-run persistence, outcome-provider persistence, watcher provenance, and journal column exposure.
- **Acceptance criteria:** Every recorded signal stores the provider used for its OHLCV data. Successful outcomes store `outcome_provider` separately and leave `signal_history.provider` unchanged. Pre-migration rows are `unknown`. No trading logic changed.
- **Intended pull request:** `devin/add-provider-provenance`
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/provider-failure-policy` (PROVIDER-005)

### PROVIDER-005: Define provider failure and fallback policy

- **ID:** PROVIDER-005
- **Title:** Define provider failure and fallback policy
- **Category:** Data provider
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/provider-failure-policy`
- **Problem statement:** There is no explicit policy for what happens when a provider fails or when a requested symbol is unavailable. The current `fetch_multi` silently skips failures and the engine shows "No opportunities" rather than distinguishing data failure from zero signals.
- **Recommended action:** Document and implement a failure/fallback policy: per-symbol retries, explicit fallback order, clear error surfacing, and no silent fallback to Yahoo when `DATA_PROVIDER` is set to another provider.
- **Reason:** Trading decisions depend on knowing whether data is missing, stale, or from an unexpected source.
- **Dependencies:** PROVIDER-003, PROVIDER-004
- **Files likely affected:** `tradex/data/fetcher.py`, `tradex/screener/engine.py`, `tradex/ui/dashboard.py`, `tradex/tracker/watcher.py`
- **Testing requirements:** Unit tests for provider error classification, retry behavior, policy parsing, batch fetch reporting, screener report, fallback behavior, watcher and dashboard helpers.
- **Acceptance criteria:**
  - Provider errors are classified as retryable (`ProviderTransientError`) or non-retryable (configuration, authentication, capability, data unavailable, response) and never expose credentials or raw response bodies.
  - Retries are disabled by default (`max_retries=0`); retries are capped at 3 and use deterministic injectable backoff.
  - Fallback is disabled unless explicitly configured via `OHLCV_FALLBACK_ORDER` or the `fallback_order` argument.
  - Fallback operates at whole-scan level: only tried when the current provider produces zero usable OHLCV data for all symbols that reached the fetch stage, and the chain stops at the first provider with any usable data.
  - Partial provider success keeps successful results, reports failed symbols, and does not create a mixed-provider scan.
  - `fetch_multi` returns a `FetchReport` with per-ticker failures, attempt counts, requested/actual provider, fallback flag, and providers attempted.
  - `engine.run_with_report()` returns a `ScanReport` with results, requested/actual provider, fallback flag, failure details, and totals (requested, fetched, scored, signals, below threshold, insufficient data, earnings excluded).
  - The dashboard Scanner tab distinguishes valid zero-signal scans, complete provider failures, partial failures, and fallback use.
  - The watcher logs requested/retry/fallback/actual provider, signal counts, and failure counts.
  - No Yahoo fallback is inserted automatically.
- **Intended pull request:** `devin/provider-failure-policy`
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/add-market-hours` (COR-005)

### VAL-001: Build a backtesting harness

- **ID:** VAL-001
- **Title:** Build a backtesting harness
- **Category:** Backtesting
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/add-backtest-engine`
- **Problem statement:** There is no way to validate whether any signal has a tradable edge.
- **Recommended action:** Create `tradex/backtest/` with point-in-time data, explicit entry/stop/target/costs, and metrics (win rate, expectancy, Sharpe, drawdown).
- **Reason:** Needed to validate every trading feature before trusting it.
- **Dependencies:** TEST-001
- **Files affected:** `tradex/backtest/models.py`, `tradex/backtest/validation.py`, `tradex/backtest/engine.py`, `tradex/backtest/metrics.py`, `tradex/backtest/io.py`, `tradex/backtest/cli.py`, `tests/backtest/*.py`
- **Testing requirements:** Unit tests with deterministic synthetic data; test against a known benchmark; credential-free CLI and provider-mock tests.
- **Acceptance criteria:** A point-in-time backtest can be run for the short-term scorer via `python -m tradex.backtest --csv ...` and produces a deterministic JSON/report with no `NaN` or `inf` values.
- **Intended pull request:** `devin/add-backtest-engine`
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/fix-confluence-missing-timeframe` (COR-006)

---

## Medium priority

### COR-004: Fix watcher provider argument propagation

- **ID:** COR-004
- **Title:** Fix watcher provider argument propagation
- **Category:** Correctness
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/fix-provider-propagation` (merged with PROVIDER-002)
- **Problem statement:** `run_once` accepted a `provider` argument but did not pass it to `screener_run` or `run_confluence_screen`. See also PROVIDER-002.
- **Recommended action:** Thread `provider` through all fetch calls in `run_once` and `_check_alerts`.
- **Reason:** Users who set `--provider alpaca` or `--provider schwab` silently got the default Yahoo provider.
- **Dependencies:** None
- **Files affected:** `tradex/tracker/watcher.py`
- **Testing:** Unit tests patch `screener_run`, `run_confluence_screen`, and `run_match_screen`; assert `provider` is forwarded.
- **Acceptance criteria:** `python -m tradex.tracker.watcher --provider alpaca` causes `fetch` to be called with `provider='alpaca'`.
- **Affects trading behavior:** No

### COR-005: Add market-hours and timezone handling

- **ID:** COR-005
- **Title:** Add market-hours and timezone handling
- **Category:** Scheduling
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/add-market-hours`
- **Problem statement:** The watcher ran at any time and `schedule` job times were interpreted in host-local time, so scans fired outside US equity hours and daily jobs drifted with DST.
- **Recommended action:** Add `tradex/market/hours.py` with NYSE/XNYS market-open checks and schedule in the `America/New_York` timezone.
- **Reason:** Avoids wasted scans, stale data, and alerts at wrong times.
- **Dependencies:** None
- **Files likely affected:** `tradex/market/hours.py`, `tradex/market/__init__.py`, `tradex/tracker/watcher.py`, `tradex/premarket/gap_scanner.py`, `README.md`, `SETUP.md`, `docs/devin-review/PROJECT-TRACKER.md`
- **Testing requirements:** Unit tests for open/close/early-close/holiday/DST boundaries, naive-datetime rejection, timezone conversion, watcher gating, daily-job registration in `America/New_York`, pre-market filtering, and previous-close date handling.
- **Acceptance criteria:**
  - `tradex/market/hours.py` exposes `MarketSession`, `MarketStatus`, `get_market_session`, `is_regular_market_open`, `market_status`, `previous_trading_session`, `next_trading_session` against the XNYS calendar in `America/New_York`.
  - Watcher `run_once` accepts `market_hours_only` (default `False`) and skips scans before open, after close, on weekends, and on NYSE holidays.
  - CLI adds `--market-hours-only` and startup log shows gating status.
  - Daily pre-market job registered at `08:00 America/New_York`; daily outcome pass at `16:30 America/New_York`.
  - Trading-day guards wrap scheduled pre-market and outcome jobs so they skip non-session dates without fake persistence.
  - Pre-market filtering in `gap_scanner.py` uses `04:00 America/New_York` through (but not including) the actual regular-session open and excludes prior-day after-hours, regular-session, and post-market bars.
  - `_get_prev_close()` uses the centralized calendar, accepts injectable `as_of`, and selects the most recent completed NYSE session before the intended session.
- **Intended pull request:** `devin/add-market-hours`
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/redesign-signal-history` (DATA-001)

### COR-012: Fix scan audit to record tickers scanned vs. found

- **ID:** COR-012
- **Title:** Fix scan audit to record tickers scanned vs. found
- **Category:** Data integrity
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/fix-scan-audit`
- **Problem statement:** `scan_runs` recorded `tickers_n = hits_n = len(results)`, so it could not distinguish how many tickers were requested, how many were observed, how many qualified as signals, or whether a scan failed entirely. Legacy `scan_runs` rows also lacked any link to canonical `scan_sessions`.
- **Recommended action:** Bump the SQLite schema to version 3, extend `scan_runs` with `session_id`, `status`, `requested_provider`, `actual_provider`, `counts_complete`, and `source`; migrate legacy rows honestly (`counts_complete=0`, `status='unknown'`, `source='legacy'`); write one native `scan_runs` audit row for every `scan_sessions` row in the same transaction; update `record_scan()` and `record_signals()` to supply accurate counts; and improve `get_recent_scan_runs()` to expose the new columns and a `complete_only` filter.
- **Reason:** Audit data is needed to detect provider failures, understand coverage, and support downstream dashboards/journals without relying on `signal_history` for counts.
- **Dependencies:** DATA-001
- **Files likely affected:** `tradex/tracker/store.py`, `tradex/tracker/watcher.py`, `tradex/ui/dashboard.py`, `tests/tracker/test_scan_audit.py`, `tests/tracker/test_watcher.py`, `tests/ui/test_dashboard.py`
- **Testing requirements:** DB tests for schema v3, native persistence, transaction rollback on audit/observation failure, migration/backfill of legacy rows, compatibility wrapper semantics, query API ordering and `complete_only`, and watcher/dashboard integration.
- **Acceptance criteria:**
  - `scan_sessions` remains the canonical source of truth.
  - `record_scan()` writes exactly one `scan_runs` row per native scan with `tickers_n = report.total_requested`, `hits_n = signals_n`, `status` derived from observations, `source='native'`, `counts_complete=1`, and `session_id` populated.
  - `record_signals()` backward-compatible 3-arg calls still work; explicit `tickers_scanned` sets complete counts; omitted `tickers_scanned` writes `counts_complete=0` and `tickers_n=NULL`.
  - Legacy databases are migrated to v3, preserving legacy row IDs and marking unmatched rows `source='legacy'`/`counts_complete=0`/`status='unknown'`.
  - `get_recent_scan_runs()` returns stable empty-schema, new columns, `hit_rate_pct`, and supports `complete_only`.
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/fix-confluence-missing-timeframe` (COR-006)

### COR-013: Distinguish provider failures from zero results

- **ID:** COR-013
- **Title:** Distinguish provider failures from zero results
- **Category:** Correctness
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/provider-failure-policy` (same PR as PROVIDER-005)
- **Problem statement:** When all fetches fail, the engine returns an empty DataFrame and the dashboard says "No opportunities."
- **Recommended action:** Return a structured `ScanReport` from `engine.run_with_report()` and display it in the dashboard and watcher.
- **Reason:** Users need to know when data is broken, not just when no signals fired.
- **Dependencies:** None
- **Files likely affected:** `tradex/screener/engine.py`, `tradex/ui/dashboard.py`, `tradex/tracker/watcher.py`
- **Testing requirements:** Regression test where all fetches fail: zero signals, visible failures, selected provider present, distinguishable from a valid zero-signal scan.
- **Acceptance criteria:**
  - `tests/screener/test_engine.py::test_engine_reports_provider_failures` is a passing regression against `run_with_report`.
  - The dashboard Scanner tab shows `st.error` for complete provider failure and `st.warning` for partial failure.
  - The watcher prints an error summary when all providers fail instead of only "No signals above threshold."
  - A valid zero-signal scan continues to show the existing no-opportunities message.
- **Intended pull request:** `devin/provider-failure-policy`
- **Affects trading behavior:** No

### SHORT-001: Add market regime and relative strength to short-term scorer

- **ID:** SHORT-001
- **Title:** Add market regime and relative strength to short-term scorer
- **Category:** Short-term trading
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** The short-term score does not account for whether SPY/QQQ or the sector is trending.
- **Recommended action:** Add inputs for SPY trend and sector relative strength; either as filters or as score modifiers.
- **Reason:** Buying pullbacks in a bear market or weak sector is a different proposition than in a strong bull market.
- **Dependencies:** VAL-001 (backtesting harness)
- **Files likely affected:** `tradex/signals/short_term.py`, `tradex/data/fetcher.py`, new `tradex/market/context.py`
- **Testing requirements:** Backtest comparing current score vs. regime-aware score on hold-out data.
- **Acceptance criteria:** Regime-aware score has higher net expectancy in backtest.
- **Intended pull request:** `devin/improve-short-term-context`
- **Affects trading behavior:** Yes

### INTRA-001: Redesign intraday scorer around a specific setup

- **ID:** INTRA-001
- **Title:** Redesign intraday scorer around a specific setup
- **Category:** Intraday trading
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** The intraday score is a loose bundle of indicators without VWAP, time-of-day, or liquidity context.
- **Recommended action:** Define a concrete setup (e.g., "VWAP-based open-drive pullback") and rebuild the scorer around it.
- **Reason:** A generic score is not actionable for intraday trading.
- **Dependencies:** VAL-001
- **Files likely affected:** `tradex/signals/intraday.py`, `tradex/signals/indicators.py`, `tradex/data/fetcher.py`
- **Testing requirements:** Backtest; unit tests for VWAP/time-of-day indicators.
- **Acceptance criteria:** New score outperforms the current score on a hold-out period with explicit entry/exit rules.
- **Intended pull request:** `devin/redesign-intraday-score`
- **Affects trading behavior:** Yes

### PATTERN-001: Validate pattern matcher before dashboard promotion

- **ID:** PATTERN-001
- **Title:** Validate pattern matcher before dashboard promotion
- **Category:** Backtesting
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** Pattern matcher uses Pearson correlation vs. a fingerprint but has not been validated for predictive value.
- **Recommended action:** Run an out-of-sample backtest; if it fails to add value, move pattern match to a research/experiment tab.
- **Reason:** Correlation to a historical average is not a trade signal without empirical support.
- **Dependencies:** VAL-001
- **Files likely affected:** `tradex/patterns/matcher.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** Out-of-sample backtest on a point-in-time universe with delisted-bias controls.
- **Acceptance criteria:** Pattern-match-based trades have statistically significant positive expectancy, or the feature is quarantined.
- **Intended pull request:** `devin/validate-pattern-matcher`
- **Affects trading behavior:** Possibly Yes

### OPT-001: Gate options flow behind real data source

- **ID:** OPT-001
- **Title:** Gate options flow behind real data source
- **Category:** Cleanup
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** Without Unusual Whales/Tradier credentials, options flow degrades to delayed yfinance chain data that is not "flow."
- **Recommended action:** Show a warning and disable "unusual activity" scanning unless a real flow provider is configured; or move the feature to `research/`.
- **Reason:** Prevents users from making decisions on misleading data.
- **Dependencies:** None
- **Files likely affected:** `tradex/options/flow.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** Unit test verifying degraded state is detected.
- **Acceptance criteria:** Options flow tab clearly states data source limitations and does not present chain volume as flow.
- **Intended pull request:** `devin/gate-options-flow`
- **Affects trading behavior:** Yes

### UI-001: Split `dashboard.py` into tab and component modules

- **ID:** UI-001
- **Title:** Split dashboard.py into tab and component modules
- **Category:** User interface
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** `tradex/ui/dashboard.py` is 1,721 lines and imports every backend module.
- **Recommended action:** Move each tab into `tradex/ui/tabs/` and reusable widgets into `tradex/ui/components/`; keep `dashboard.py` as a router.
- **Reason:** Improves reviewability and makes the UI testable.
- **Dependencies:** TEST-001
- **Files likely affected:** `tradex/ui/dashboard.py`, new `tradex/ui/tabs/*.py`, new `tradex/ui/components/*.py`
- **Testing requirements:** Component unit tests; smoke test that the dashboard module loads.
- **Acceptance criteria:** No single UI file exceeds ~300 lines of logic; dashboard still renders all tabs.
- **Intended pull request:** `devin/refactor-dashboard-boundaries`
- **Affects trading behavior:** No

### ARCH-001: Centralize configuration and remove import-time env loading

- **ID:** ARCH-001
- **Title:** Centralize configuration and remove import-time env loading
- **Category:** Architecture
- **Priority:** Medium
- **Status:** Proposed
- **Problem statement:** Several modules call `load_dotenv()` and read `os.getenv` at import time, making tests dependent on the environment.
- **Recommended action:** Add a typed `tradex.config` module and pass settings explicitly.
- **Reason:** Makes the codebase testable and avoids accidental coupling to a specific `.env` at import time.
- **Dependencies:** None
- **Files likely affected:** `tradex/data/fetcher.py`, `tradex/options/flow.py`, `tradex/alerts/notifier.py`, new `tradex/config.py`
- **Testing requirements:** Unit tests verify behavior changes when config changes.
- **Acceptance criteria:** No `os.getenv` at module level except in `config.py`.
- **Intended pull request:** `devin/centralize-config`
- **Affects trading behavior:** No

---

## Low priority

### DOC-001: Fix documentation drift

- **ID:** DOC-001
- **Title:** Fix documentation drift
- **Category:** Documentation
- **Priority:** Low
- **Status:** Proposed
- **Problem statement:** `README.md` and `CLAUDE.md` disagree on tabs/completed features; `SETUP.md` has a wrong Discord env variable name.
- **Recommended action:** Sync docs; fix env variable; establish one canonical source per topic.
- **Reason:** New users and future agents should not get conflicting instructions.
- **Dependencies:** None
- **Files likely affected:** `README.md`, `CLAUDE.md`, `SETUP.md`
- **Testing requirements:** Doc review checklist.
- **Acceptance criteria:** Tab counts and feature statuses are consistent; `SETUP.md` uses `ALERT_DISCORD_TOKEN`.
- **Intended pull request:** `devin/fix-doc-drift`
- **Affects trading behavior:** No

### LONG-001: Redesign or deprioritize long-term scorer

- **ID:** LONG-001
- **Title:** Redesign or deprioritize long-term scorer
- **Category:** Long-term trading
- **Priority:** Low
- **Status:** Proposed
- **Problem statement:** The long-term score is a weekly-bar version of the short-term score and lacks fundamental or relative-strength context.
- **Recommended action:** Either define a clear long-term trend-following setup (price > 40-week MA, relative strength, sector) or remove the long-term tab.
- **Reason:** A "long-term" screen should not simply be a slower momentum score.
- **Dependencies:** VAL-001
- **Files likely affected:** `tradex/signals/long_term.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** Backtest comparing long-term score to a simple 40-week MA rule.
- **Acceptance criteria:** Long-term score adds value beyond the simple benchmark, or is deprioritized.
- **Intended pull request:** `devin/improve-long-term-score`
- **Affects trading behavior:** Yes

### GAP-001: Improve pre-market gap scanner

- **ID:** GAP-001
- **Title:** Improve pre-market gap scanner
- **Category:** Intraday trading
- **Priority:** Low
- **Status:** Proposed
- **Problem statement:** The gap scanner uses delayed yfinance pre-market bars and does not filter by liquidity, spread, or catalyst.
- **Recommended action:** Add liquidity/spread filters; link to earnings/news context; restrict to pre-market hours unless explicitly enabled.
- **Reason:** Gaps without liquidity or catalyst context are not tradable.
- **Dependencies:** COR-005
- **Files likely affected:** `tradex/premarket/gap_scanner.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** Unit tests with mocked pre-market data.
- **Acceptance criteria:** Scanner shows liquidity metrics and catalyst context.
- **Intended pull request:** `devin/improve-gap-scanner`
- **Affects trading behavior:** Yes

### DEC-001: Adopt Architectural Decision Records

- **ID:** DEC-001
- **Title:** Adopt Architectural Decision Records
- **Category:** Documentation
- **Priority:** Low
- **Status:** Proposed
- **Problem statement:** Major decisions (what is a coil, confluence weights, provider contract) are not recorded.
- **Recommended action:** Create `docs/decisions/` and seed it with ADRs for the most important current decisions.
- **Reason:** Future developers and agents need to understand why key choices were made.
- **Dependencies:** None
- **Files likely affected:** `docs/decisions/*.md`
- **Testing requirements:** N/A
- **Acceptance criteria:** ADRs exist for coil definition, confluence requirements, provider contract, and market timezone.
- **Intended pull request:** `devin/add-initial-adrs`
- **Affects trading behavior:** No

---

## Summary by priority

| Priority | Count | Representative first item |
|---|---|---|
| High | 16 | DATA-001: Redesign signal history to record all scan observations |
| Medium | 8 | SHORT-001: Add market regime and relative strength to short-term scorer |
| Low | 5 | DOC-001: Fix documentation drift |

**Recommended next pull request order:**
1. `devin/redesign-signal-history` (DATA-001, COIL-001, COIL-002).
2. `devin/fix-scan-audit` (COR-012).
3. `devin/add-backtest-engine` (VAL-001).
4. `devin/fix-confluence-missing-timeframe` (COR-006).
5. `devin/reevaluate-scores-with-validated-data` (new, after backtesting).
6. `devin/improve-gap-scanner` (INTRA-002, after COR-005 and DATA-001).

