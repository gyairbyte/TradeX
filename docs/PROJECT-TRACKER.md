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
- **Status:** Completed
- **Resolved by:** `devin/fix-confluence-missing-timeframe`
- **Problem statement:** Confluence renormalizes weights over available timeframes and can report `"all timeframes aligned"` when only one timeframe is present.
- **Recommended action:** Use fixed-denominator weights (intraday 30%, short 40%, long 30%) so missing timeframes contribute zero. Add explicit coverage metadata (`available_timeframes`, `missing_timeframes`, `timeframe_coverage`, `complete_timeframe_coverage`). Only award `all timeframes aligned` when 3/3 timeframes contributed, all three are active (score ≥ 50), and the confluence score is at least 90.
- **Reason:** The label implies multi-timeframe agreement, which is not true when data is missing.
- **Dependencies:** None
- **Files likely affected:** `tradex/tracker/confluence.py`, `tradex/ui/dashboard.py`, `tests/tracker/test_confluence.py`, `README.md`, `SETUP.md`
- **Testing requirements:** Unit tests for fixed-weight scoring across all missing-timeframe combinations, tier classification, coverage metadata, stable no-data schema, and `run_confluence_screen` threshold behavior.
- **Acceptance criteria:** Confluence score and tier accurately reflect which timeframes contributed; the former strict `COR-006` xfail in `tests/tracker/test_confluence.py` is now a passing regression; no `COR-006` xfail remains.
- **Intended pull request:** `devin/fix-confluence-missing-timeframe`
- **Affects trading behavior:** Yes (confluence output changes)
- **Next recommended PR:** `devin/reevaluate-scores-with-validated-data`

### ALERT-001: Add alert deduplication and cooldown

- **ID:** ALERT-001
- **Title:** Add alert deduplication and cooldown
- **Category:** Alerts
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/add-alert-cooldown`
- **Problem statement:** The watcher fires alerts on every scan cycle for every ticker above threshold, with no persistence or cooldown.
- **Recommended action:** Introduce an alert state store keyed by `(ticker, alert_type, timeframe)` and enforce a configurable cooldown (e.g., 1 hour for coils).
- **Reason:** Prevents alert spam and respects user attention.
- **Dependencies:** None
- **Files likely affected:** `tradex/alerts/notifier.py`, `tradex/tracker/watcher.py`, new `tradex/alerts/policy.py`, `tradex/alerts/models.py`, `tradex/alerts/store.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** Unit tests mocking `send_alert`; verify it is only called once per cooldown window; verify persistence across restarts, atomic claims, and dashboard display.
- **Acceptance criteria:** Repeated checks for the same alert identity produce only one Discord/email message per cooldown window; state persists across watcher restarts; manual test alerts bypass cooldown.
- **Intended pull request:** `devin/add-alert-cooldown`
- **Affects trading behavior:** Yes — production trading-alert delivery cadence changes; signals, scores, thresholds, rankings, and eligibility remain unchanged. Implementation authorized by Gary; final merge requires Gary’s explicit approval.
- **Next recommended PR:** `devin/refactor-dashboard-boundaries` (UI-001)

### TEST-001: Complete test foundation and fixtures

- **ID:** TEST-001
- **Title:** Complete test foundation and fixtures
- **Category:** Testing
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/close-test-001-tracker`
- **Problem statement:** The task began with one passing test and seven strict `xfail`s tied to COR/DATA/COIL items. The repository now has broad deterministic unit, integration, provider-contract, persistence, research, and UI coverage.
- **Recommended action:** Close TEST-001 and keep the tracker aligned with the actual remaining work; no further production or test source changes are required.
- **Reason:** Tests are a prerequisite for safely fixing correctness and redesigning trading logic.
- **Dependencies:** None
- **Files likely affected:** `docs/PROJECT-TRACKER.md`
- **Testing requirements:** `uv run pytest tests -q` passes locally and in CI; focused provider, config, tracker, and UI suites pass.
- **Acceptance criteria:** `pytest` passes locally and in CI; provider-contract coverage exists for TEST-001's scope; DB tests use temp files, isolated `TradeXSettings`, or redirected environment paths; no active `xfail` remains; CI enforces `ruff check tests scripts` and the complete test suite; the isolated full suite does not create or modify real `~/.tradex/` files.
- **Current verified result:** `1229 passed` in ~2 minutes with `5` pre-existing `datetime.utcnow()` deprecation warnings; `0` xfailed, `0` xpassed, `0` skipped.
- **Active xfails:** `0`.
- **Provider-contract coverage:** Complete for TEST-001's scope (provider resolution and normalization, retry/fallback policy, canonical OHLCV schema, empty/malformed/missing-credential handling, Schwab contract tests, provenance, and no live API calls in CI).
- **Intended pull request:** `devin/close-test-001-tracker`
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
- **Next recommended PR:** `devin/reevaluate-scores-with-validated-data` (VAL-002)

### VAL-002: Reproducible short-term score validation study

- **ID:** VAL-002
- **Title:** Reproducible short-term score validation study
- **Category:** Backtesting
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `devin/reevaluate-scores-with-validated-data`
- **Problem statement:** There is no structured, reproducible way to evaluate whether the current `short_term` score is calibrated to future returns, and no separation between an event study and the executable backtest engine.
- **Recommended action:** Add `tradex/research/score_validation` with a versioned offline dataset manifest, SHA-256 verification, point-in-time score generation, 1/3/5-bar forward-return event studies, temporal splits, score-bucket/threshold/component aggregation, per-ticker/pooled summaries, transaction-cost sensitivity, and deterministic JSON/CSV/Markdown reports.
- **Reason:** Needed before changing any production score, weights, or thresholds.
- **Dependencies:** VAL-001
- **Files affected:** `tradex/signals/short_term.py`, `tradex/research/score_validation/*.py`, `tests/research/score_validation/*.py`, `README.md`, `SETUP.md`, `.agents/skills/tradex-local-testing/SKILL.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Credential-free, network-free, deterministic tests covering manifest validation, snapshot mocking, point-in-time events, temporal splits, aggregations, report output, CLI help, and rerun determinism.
- **Acceptance criteria:**
  - `python -m tradex.research.score_validation evaluate --manifest ...` runs offline with a fresh `ShortWeights()` and produces deterministic outputs.
  - Event returns are not presented as portfolio/account returns or proof of a tradable strategy.
  - A valid outcome is `insufficient evidence to change the production score`; the study does not force a recommendation.
- **Intended pull request:** `devin/reevaluate-scores-with-validated-data`
- **Affects trading behavior:** No
- **Next recommended PR:** `devin/long-002a-locked-research-contract` — `SHORT-001` is complete and `INTRA-001` is complete and inconclusive; the active research program is now `LONG-002`.

### LONG-002: Long-only rapid-upside opportunity research program

- **ID:** LONG-002
- **Title:** Long-only rapid-upside opportunity research program
- **Category:** Long-term trading
- **Priority:** High
- **Status:** In progress
- **Completed phase:** `LONG-002A` — locked research/discovery contract (merged in PR #48)
- **Completed phase:** `LONG-002B` — core data feasibility and point-in-time dataset contract (merged in PR #49)
- **Current phase:** `LONG-002B-AMEND-001` — blocked data-family resolution (security identity/lifecycle/exclusion classification and earnings-event timing)
- **Research contract:** `docs/research/LONG-002.md`
- **Locked machine-readable specification:** `docs/research/specs/LONG-002-v1.json`
- **Objective:** Research an explainable, long-only rapid-upside opportunity system for U.S.-listed mid-, large-, and mega-cap common stocks, estimating the probability and capturable potential of clean +10%, +20%, and +30% moves over 5, 10, and 21 trading sessions from an executable entry.
- **Classification:** Research-only
- **Production promotion:** Unauthorized (`production_promotion_eligible=false`); historical holdout support (`LONG-002I`) authorizes only `LONG-002J` prospective shadow, and a `prospectively_supported` shadow authorizes only consideration of a separate Gary-approved production decision-support PR
- **Historical periods:** Warm-up 2015, development 2016-2020, validation 2021-2022, untouched holdout 2023-2025, shadow/replay 2026+
- **Official snapshots:** 20:30 and 09:00 America/New_York on XNYS calendar
- **Display caps:** Enter Now 7, Armed 12, Qualified Waitlist 12, default focus list 31
- **Model search budget:** 48 material configurations across three allowed families
- **Trigger/M1/M2 budgets:** 12 / 8 / 8 material configurations
- **Provider search budget:** One preferred provider plus at most two named fallbacks per data family
- **Deferred decisions:** Final feature set, weights, thresholds, stop/target parameters, provider choices, recommendation-episode lifecycle, and production behavior are explicitly deferred to later phases.
- **Problem statement:** A dedicated rapid-upside research program is needed that is distinct from LONG-001 and INTRA-001, with a locked contract before any provider investigation or outcome analysis.
- **B-phase results:** `docs/research/LONG-002B-DATA-FEASIBILITY.md`
- **B-phase probe spec:** `docs/research/specs/LONG-002B-probe-v1.json` (SHA-256: `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98`)
- **B-phase data contract:** `docs/research/specs/LONG-002B-data-contract-v1.json` (SHA-256: `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a`)
- **B-phase safe artifact bundle:** `docs/research/artifacts/LONG-002B/2026-08-13-044204/`
- **B-phase overall disposition:** `not_supported`
- **Per-family dispositions:**
  - Daily market data: `supported_with_documented_limitations` (Alpaca fallback after Massive/Polygon `v2/aggs` 403 entitlement; 1259 bars from 2016-01-04 through 2020-12-31; complete 2020 XNYS completeness; explicit `raw` and `split` policies; Massive corporate-action provenance)
  - Security master & corporate actions: `not_supported` (Massive per-ticker PIT rows returned, but one PIT row per symbol does not demonstrate active/inactive lifecycle coverage and `type` values `CS`/`INDEX` do not defensibly identify the locked excluded security types; split/dividend event endpoints returned events)
  - Issuer fundamentals & shares: `supported_with_documented_limitations` (SEC EDGAR primary; CIK identity resolved for AAPL/GOOGL/FDX; filing acceptance-time control linked to the selected shares fact; PIT market-cap pathway demonstrated for AAPL with shares outstanding period end 2020-10-16, filed 2020-10-30, acceptance 2020-10-29, paired with the 2020-12-31 close)
  - Earnings event timing: `not_supported` (no live provider calls; preregistered candidates remain unverified; no historical known-at-time schedule source identified within bounded budget)
- **Provider call budget:** 41 of 120 HTTP requests used; 0 retries; 1 provider switch (Massive/Polygon daily bars → Alpaca fallback)
- **Recommended action:** A Gary-approved amendment must identify and verify a historical earnings-calendar source or formally adopt the `unknown` earnings treatment before `LONG-002C` full dataset construction. No production behavior is authorized.
- **Testing requirements:** `tests/research/long_002_data_feasibility/test_spec.py`; `tests/research/long_002_data_feasibility/test_probe.py`; `tests/research/long_002_data_feasibility/test_amendment_001.py`; `uv run ruff`; `uv run pytest`; `git diff --check`.
- **Acceptance criteria:** Bounded provider probes produce auditable dispositions for each core data family; `LONG-002B-AMEND-001` resolves the minimum-contract gating for security identity/lifecycle/exclusion classification with deterministic tests; no full historical dataset is built; no validation/holdout outcomes are accessed; no production behavior changes.
- **Intended pull request:** `devin/long-002b-amend-001-blocker-resolution` (draft)
- **Affects trading behavior:** No — research-only amendment; no production scorer, score, weight, threshold, ranking, eligibility, confluence, alert, or dashboard trading logic changes.
- **Amendment results:** `docs/research/LONG-002B-AMEND-001.md`
- **Amendment probe spec:** `docs/research/specs/LONG-002B-AMEND-001-probe-v1.json`
- **Amendment safe artifact bundle:** `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647/`
- **Amendment overall disposition:** `not_supported` (security identity and earnings-event timing both remain blocked; `LONG-002C` is not authorized)
- **Amendment per-family dispositions:**
  - Security identity, lifecycle, and exclusion classification: `not_supported` (Massive partial; every `(symbol, as_of_date)` PIT row is classified independently; unresolved historical rows with generic or missing `type` codes and no corroborating name/SIC signal fail closed to `unknown`; later/current rows are never backfilled as historical fact; PFF classified as `ETF`, SPY as `ETF`, IGR as `closed_end_fund`, IPOD as `pre_merger_spac`)
  - Earnings-event timing: `not_supported` (no preregistered endpoint returned a historical known-at-time earnings schedule; `vX/reference/financials` provides XBRL filing/period dates only; `sec_edgar` and `yahoo_earnings_calendar` fallbacks were not exercised and are recorded as `unverified` with `request_count=0`; fail-closed `unknown` treatment is explicitly not adopted)
- **Amendment provider calls:** 64 of 120 HTTP requests; 0 retries; 0 provider switches; ~12.5 minutes runtime
- **Current phase:** `LONG-002B-DEC-001` — blocker disposition decision packet (pending Gary decision; research-governance only)
- **Decision packet:** `docs/research/LONG-002B-DEC-001.md`
- **Decision payload (machine-readable):** `docs/research/specs/LONG-002B-DEC-001.json`
- **Decision status:** `pending_gary_decision`
- **Recommended option (advisory):** Option 2 — adopt an explicit fail-closed `unknown` policy subject to a separate Gary/ChatGPT approval and a separate `LONG-002C` design PR
- **Next phase:** A Gary-approved amendment or fail-closed unknown policy must resolve the two blockers before `LONG-002C` full dataset construction is authorized.

### DAYTRADE-001: Future real-time day-trading decision-support program

- **ID:** DAYTRADE-001
- **Title:** Future real-time day-trading decision-support program
- **Category:** Intraday trading
- **Priority:** High
- **Status:** Deferred
- **Description:** A separate future real-time day-trading decision-support program based on Gary's actual 3-year daily, 133-tick, 1-minute, and 50-tick workflow.
- **Note:** Not equivalent to INTRA-001; not assumed to be VWAP-based.
- **Sequencing:** After LONG-002 unless Gary explicitly reprioritizes.
- **Affects trading behavior:** No
- **Do not start DAYTRADE-001 work in this PR.**

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
- **Files likely affected:** `tradex/market/hours.py`, `tradex/market/__init__.py`, `tradex/tracker/watcher.py`, `tradex/premarket/gap_scanner.py`, `README.md`, `SETUP.md`, `docs/PROJECT-TRACKER.md`
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
- **Status:** Completed — Not supported (v2 ingestion remediation succeeded; 23 malformed rows dropped, 45-symbol panel preserved; no candidate policy passed the predefined development/validation criteria; `production_promotion_eligible=false`)
- **Resolved by:** `devin/improve-short-term-context`
- **Disposition reviewed by:** `devin/short-001-disposition`
- **V1 real-data study branch:** `devin/short-001-real-data-study`
- **V1 real-data report:** `docs/research/SHORT-001-SCHWAB-STUDY.md`
- **V2 remediation branch:** `devin/short-001-data-ingestion`
- **V2 real-data report:** `docs/research/SHORT-001-SCHWAB-STUDY-V2.md`
- **Safe artifacts:** `docs/research/artifacts/SHORT-001/2026-08-01-5ae8a420/` (v1, preserved unchanged); `docs/research/artifacts/SHORT-001/2026-08-07-e5b64b56/` (v2)
- **Problem statement:** The short-term score does not account for whether the broad market or sector is trending.
- **Recommended action:** The v2 ingestion remediation and rerun are complete. The data-quality issue was resolved by dropping 23 malformed rows and producing deterministic audit evidence. The unchanged candidate-selection gate produced no qualifying policy, so SHORT-001 is closed as Completed — Not supported and no production integration is warranted. The next research priority is now `LONG-002` (locked rapid-upside long opportunity program); the `INTRA-001B` through `INTRA-001D` work is complete and inconclusive.
- **Next recommended PR:** `devin/long-002a-locked-research-contract` — `INTRA-001B` through `INTRA-001D` are complete and inconclusive; the active research program is now `LONG-002`.
- **Reason:** Buying pullbacks in a bear market or weak sector is a different proposition than in a strong bull market.
- **Dependencies:** VAL-001 (backtesting harness), VAL-002 (score validation study)
- **Files affected:** `tradex/market/__init__.py`, `tradex/market/context.py`, `tradex/market/models.py`, `tradex/signals/short_term.py`, `tradex/screener/engine.py`, `tradex/research/short_context/*`, `tests/market/test_context.py`, `tests/research/short_context/*`, `README.md`, `SETUP.md`, `.agents/skills/tradex-local-testing/SKILL.md`, `docs/PROJECT-TRACKER.md`, `docs/research/SHORT-001.md`
- **Testing requirements:** Unit tests for context computation, eligibility, spec validation, event generation, candidate selection, paired backtests, report generation, and CLI help; synthetic end-to-end workflow; focused and full pytest suites.
- **Acceptance criteria:**
  - `short_term.score` accepts optional `context` and `context_policy` kwargs, preserves the existing numeric `score` as `base_score`, and adds `context_eligible`, `context_status`, `context_reasons`, and `market_context`.
  - `tradex/research/short_context` produces `study.json`, `context_events.csv`, `candidate_comparison.csv`, `candidate_selection.json`, `holdout_evaluation.csv`, `paired_backtests.csv`, `ticker_comparison.csv`, `data_quality.csv`, `report.md`, `manifest.lock.json`, and `context_spec.lock.json`.
  - Candidate selection uses only `development` + `validation`; `holdout` does not influence any decision.
  - Both the event-study and paired-backtest promotion gates must pass before production exposure.
  - On synthetic data the gate did not pass, so the candidate policy was not exposed and production behavior remains unchanged.
  - A manifest-locked v2 real-data study exists at `docs/research/artifacts/SHORT-001/2026-08-07-e5b64b56/`; no candidate policy passed the predefined gates, so production promotion remains blocked.
- **Intended pull request:** `devin/improve-short-term-context`
- **Affects trading behavior:** No; the production screener does not expose context filtering. Research output is promotion-gated, and a candidate policy is only integrated after both holdout gates pass.

### INTRA-001: Redesign intraday scorer around a specific setup

- **ID:** INTRA-001
- **Title:** Redesign intraday scorer around a specific setup
- **Category:** Intraday trading
- **Priority:** Medium
- **Status:** `INTRA-001D` complete on `devin/intra-001-d-locked-study` after final review fixes — runtime spec/amendment hashes are now enforced against the actual files the CLI loads, the holdout ledger uses an exclusive `fcntl` advisory lock held through parsing (with `started` tombstone and retry refusal), and safe-bundle output is deterministic for a fixed `--generated-at` by canonicalizing `runtime_seconds`, `freeze_verification_seconds`, and `freeze.frozen_at`; the obsolete `2026-08-10-040552/` and `2026-08-10-131410/` bundles were removed so only the final canonical bundle remains; the locked `INTRA-001B-DATASET-V1` snapshot was integrity-verified and development/validation were rerun from a clean freeze with no live provider calls; the study returned `inconclusive`; holdout was correctly not parsed; `production_promotion_eligible=false`; no production behavior changed
- **Research specification:** `docs/research/INTRA-001-SPEC.md`
- **Locked machine-readable strategy spec:** `docs/research/specs/INTRA-001-v1.json` (SHA-256 unchanged)
- **Data-sufficiency amendment v3:** `docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json` and `docs/research/INTRA-001-DATA-SUFFICIENCY-AMENDMENT-V3.md`
- **Locked 2025 dataset plan:** `docs/research/specs/INTRA-001B-dataset-v1.json`
- **2025 dataset plan 1Day amendment rationale:** `docs/research/INTRA-001B-DATASET-V1-1DAY-AMENDMENT.md`
- **Reference probe v4 safe artifacts:** `docs/research/artifacts/INTRA-001B-REFERENCE-V4/2026-08-08-062051/`
- **Reference probe v4 decision:** `docs/research/INTRA-001B-REFERENCE-V4.md`
- **Reference probe v4 outcome:** `unsupported` — Massive/Polygon completed full pagination, taxonomy, and repeatability, but failed the mandatory `otc_exclusion` and `duplicate_symbol_behavior_and_resolution` gates
- **INTRA-001B branch:** `devin/intra-001b-one-year-snapshot`
- **INTRA-001B pre-registration / 1Day amendment commit:** `60e46e25b38e9e7ef9316bf49bb0a51cf092121c`
- **INTRA-001B live run head:** `ee4b7b897f3768f6fa6608c2fdba28384b9a5d91` (original download head; no new provider calls on recompute)
- **INTRA-001B bundle generation head:** `ccb5e604d8497c1cbec230bc146c12019d3d0bae` (fourth-round validation/finalize code commit)
- **INTRA-001B original safe artifacts (preserved):** `docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-08-200945/`
- **INTRA-001B first-corrected safe artifacts (preserved):** `docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-08-211737/`
- **INTRA-001B second-corrected safe artifacts (preserved):** `docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-08-225153/`
- **INTRA-001B third-corrected safe artifacts (preserved):** `docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-09-011333/`
- **INTRA-001B fourth-corrected safe artifacts:** `docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-09-014844/`
- **INTRA-001B dataset disposition:** `inconclusive` — pre-normalization duplicate/malformed metrics unavailable, so the 1% duplicate threshold is unverified; missing-bar and zero-volume thresholds are otherwise clean except for six BKNG symbol-month breaches (Jan 23.2372%, Feb 13.4451%, Mar 12.1326%, Apr 9.9124%, Jul 29.4559%, Nov 11.6059%, all > the locked 5% per-symbol maximum); no provider/provenance/pagination/silent-substitution/manifest failures
- **INTRA-001C branch:** `devin/intra-001c-research-engine` (current head is the branch tip)
- **INTRA-001C implementation doc:** `docs/research/INTRA-001C-IMPLEMENTATION.md`
- **INTRA-001C engine package:** `tradex/research/intraday_engine/`
- **INTRA-001C tests:** `tests/research/intraday_engine/`
- **INTRA-001C status:** Synthetic engine complete and merged; `run_study` uses genuine end-to-end synthetic `TickerInput` fixtures (candidate, Baseline A, Baseline B, execution, aggregation, gates, and JSON-safe serialization) with exact dispositions/statuses for supported, not_supported, and rejected paths; no monkeypatched strategy evaluators; no real-data or provider calls; no production behavior changed
- **INTRA-001B monthly stock counts:** 50 selected stocks per month, 12 months
- **INTRA-001B fixed ETF stratum:** 13 ETFs per month
- **INTRA-001B unique selected symbols:** 97 distinct stocks + 13 ETFs
- **INTRA-001B coverage:** `2025-01-02` through `2025-12-31` with 20-session warm-up before each month
- **INTRA-001B Massive HTTP requests:** 440 (12 active + 12 inactive PIT snapshots, 0 errors, 0 `429`s)
- **INTRA-001B Alpaca HTTP requests:** 1,885 aggregate observed during original download; per-phase logical/page/attempt/429/error counters are unavailable for the recomputed bundle and modeled as `null`
- **INTRA-001B actual runtime:** historical runtime unavailable for the recomputed bundle; original download was under 60 minutes
- **INTRA-001B local storage:** ~270 MB
- **Ranking formula:** `session_dollar_volume = Alpaca SIP 1Day close * Alpaca SIP 1Day volume`; median over prior 20 complete XNYS sessions; 1Day volume accepted as a total-liquidity proxy that includes pre/post-market activity
- **Holdout protection:** OHLCV bars downloaded and validated; no VWAP, signals, entries, exits, returns, metrics, or holdout-performance inspected for real data; synthetic engine does not access the locked INTRA-001B real-data directory
- **INTRA-001C holdout protection:** Engine operates on purely synthetic tickers (`SYNTH-STK-*`, `SYNTH-ETF-*`) and writes only to a user-supplied output directory; it never downloads, reads, or evaluates real symbols
- **INTRA-001D branch:** `devin/intra-001-d-locked-study` (live PR head is the branch tip; see the PR description for the exact SHA)
- **INTRA-001D safe artifact bundle generation commit:** `0eeaab5`
- **INTRA-001D starting main SHA:** `a7249f2f1ebf5230947c6fa601cbb1634365f25e`
- **INTRA-001D evaluation-code freeze SHA:** `ed1739a50ce738c7620ea083e9d6fd77c4a6915f` (clean tracked commit used to run development/validation; distinct from the live PR head and bundle generation commit)
- **INTRA-001D safe artifacts:** `docs/research/artifacts/INTRA-001D/2026-08-10-151816/` (generated from freeze `ed1739a50ce738c7620ea083e9d6fd77c4a6915f` with `--generated-at 2026-08-10T15:20:00+00:00`)
- **INTRA-001D development outcome:** `inconclusive` — candidate executed trades=232, below the locked `executed_candidate_trades_min=300`; ETF stratum trades=32, below 75; four BKNG symbol-months exceed the 5% per-symbol missing-bar threshold (Jan 23.2372%, Feb 13.4451%, Mar 12.1326%, Apr 9.9124%); all 378 symbol-months have `pre_normalization_metrics_unavailable`, keeping split disposition `inconclusive` while still allowing diagnostic trade/sample metrics
- **INTRA-001D validation outcome:** `inconclusive` — candidate executed trades=103, below 300; represented ETFs=7, below 8; stock stratum trades=95, below 100; ETF stratum trades=8, below 75; one BKNG month (Jul, 29.4559%) exceeds the 5% per-symbol missing-bar threshold; all 189 symbol-months have `pre_normalization_metrics_unavailable`
- **INTRA-001D holdout access status:** Not parsed — validation disposition was not `supported`; all 189 holdout symbol-month files received hash-only integrity checks (`access_count=189`) and zero holdout Parquet parses occurred (`parse_count=0`); the persistent ledger is now at a canonical location keyed by `dataset_id` only, stores the frozen `evaluation_code_sha`, `spec_sha256`, `amendment_sha256`, and `dataset_plan_sha256`, and blocks `started`/`completed`/`not_run` reruns and any identity mismatch; the public `--holdout-ledger-dir` option was removed so the ledger cannot be bypassed by changing output directory
- **INTRA-001D final disposition:** `inconclusive`; `production_promotion_eligible=false`; 6 of 756 symbol-months (0.7937%) are data-quality rejected for `missing_bar_rate`, all BKNG (Jan 23.2372%, Feb 13.4451%, Mar 12.1326%, Apr 9.9124% in development, Jul 29.4559% in validation, Nov 11.6059% in holdout); the remaining 750 symbol-months are unverified due to unavailable pre-normalization duplicate/malformed metrics and cannot be counted as clean, forcing the honest `inconclusive` classification
- **INTRA-001D production-promotion eligible:** `false`
- **INTRA-001D dataset:** `INTRA-001B-DATASET-V1` private snapshot at `~/.tradex/research/INTRA-001B-DATASET-V1/` (not committed)
- **INTRA-001D provider calls:** 0
- **Problem statement:** The intraday score is a loose bundle of indicators without VWAP, time-of-day, or liquidity context.
- **Recommended action:** `INTRA-001D` is complete and inconclusive; the holdout was not parsed and no production promotion is warranted. No further work on this hypothesis is authorized without a new Gary-approved plan.

- **Reason:** A generic score is not actionable for intraday trading. The concrete open-drive VWAP pullback setup and its two baselines are pre-registered before any code changes.
- **Dependencies:** VAL-001
- **Files likely affected:** `docs/research/INTRA-001-SPEC.md`, `docs/research/specs/INTRA-001-v1.json`, `docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json`, `docs/research/INTRA-001-DATA-SUFFICIENCY-AMENDMENT-V3.md`, `docs/research/specs/INTRA-001B-dataset-v1.json`, `docs/research/INTRA-001B-DATASET-V1-1DAY-AMENDMENT.md`, `tradex/research/intraday_dataset/`, `tradex/research/intraday_engine/`, `tradex/research/intraday_study/`, `docs/research/INTRA-001C-IMPLEMENTATION.md`, `docs/research/INTRA-001D-IMPLEMENTATION.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** JSON schema validation; focused dataset tests; full test suite; documentation/search audit; artifact checksum verification; secret/path/token/cursor scan.
- **Acceptance criteria:** 12 monthly PIT universes built, 13-ETF stratum preserved, Alpaca SIP 5Min OHLCV manifest locked, data-quality gates evaluated and reported under the locked disposition hierarchy, safe artifact bundle produced, `INTRA-001-v1.json` / amendment v3 / frozen V4 artifacts unchanged; `INTRA-001C` engine implemented with locked session/VWAP/opening-drive/reclaim/entry/exit/cost semantics, Baseline A calling fresh `IntradayWeights()`, Baseline B simple VWAP reclaim, synthetic-only `synthetic=true` artifacts, no real-data/provider access, no production behavior change; `INTRA-001D` adapter implemented, real-data development/validation/holdout run under frozen evaluation code, holdout parsed only if validation `supported`, final disposition and `production_promotion_eligible` recorded.
- **Intended pull request:** `devin/intra-001d-locked-study` (completed and merged; no further work on this hypothesis without a new Gary-approved plan)
- **Affects trading behavior:** No — `INTRA-001C` is research-only and `INTRA-001D` is a separately approved real-data study; no production code, scores, weights, thresholds, rankings, or eligibility changed.
- **This PR changes no trading behavior.**

### PATTERN-001: Validate pattern matcher before dashboard promotion

- **ID:** PATTERN-001
- **Title:** Validate pattern matcher before dashboard promotion
- **Category:** Backtesting
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/validate-pattern-matcher`
- **Real Schwab study result:** The locked PATTERN-001 Schwab study completed with run-up `rejected`, decline `rejected`, and `production_promotion_eligible=false`. Sanitized safe-handoff artifacts are at `docs/research/artifacts/PATTERN-001/2026-08-03-9ea40e85/`.
- **Problem statement:** Pattern matcher uses Pearson correlation vs. a fingerprint but has not been validated for predictive value.
- **Recommended action:** Run an out-of-sample backtest; if it fails to add value, move pattern match to a research/experiment tab.
- **Reason:** Correlation to a historical average is not a trade signal without empirical support.
- **Dependencies:** VAL-001
- **Files likely affected:** `tradex/patterns/matcher.py`, `tradex/ui/dashboard.py`, `tradex/tracker/watcher.py`, `tradex/research/pattern_validation/`
- **Testing requirements:** Out-of-sample backtest on a point-in-time universe with delisted-bias controls; production quarantine tests; artifact determinism tests.
- **Acceptance criteria:** Pattern-match alerts are removed from the watcher; the dashboard tab is relabeled as experimental research with a prominent warning; the matcher output uses neutral wording; a locked `tradex/research/pattern_validation` package produces deterministic artifacts and never reads/writes `~/.tradex/fingerprints.db`.
- **Intended pull request:** `devin/validate-pattern-matcher`
- **Affects trading behavior:** Yes — the watcher no longer calls `run_match_screen()` or `alert_pattern_match()`; dashboard tab and matcher wording are relabeled as experimental research. No pattern similarity is added to scores, rankings, eligibility, or confluence.
- **Next recommended PR:** `devin/centralize-config` (ARCH-001)

### OPT-001: Gate options flow behind real data source

- **ID:** OPT-001
- **Title:** Gate options flow behind real data source
- **Category:** Cleanup
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/gate-options-flow`
- **Problem statement:** Without Unusual Whales credentials, options flow degraded to delayed yfinance chain data that is not transaction-level "flow." Tradier and Yahoo supply chain snapshots, not true flow.
- **Recommended action:** Add capability-aware source resolution that distinguishes `true_flow` (Unusual Whales, when configured) from `chain_snapshot` (Tradier or Yahoo). Disable the true-flow scan when no true-flow source is configured and clearly label chain activity as non-directional snapshot data.
- **Reason:** Prevents users from making decisions on data that has been mislabeled as unusual options flow or directional signal.
- **Dependencies:** None
- **Files likely affected:** `tradex/options/models.py`, `tradex/options/flow.py`, `tradex/ui/dashboard.py`, `README.md`, `SETUP.md`, `.env.example`, `CLAUDE.md`
- **Testing requirements:** Unit tests for typed models, source resolution, true-flow reports, chain reports, put/call balance, provider error handling, and dashboard helpers. Credential-free and network-free.
- **Acceptance criteria:** True-flow scans only run when Unusual Whales is configured; chain scans use Tradier or Yahoo; no result is labeled as true flow from a snapshot source; put/call volume balance is explicitly non-directional; the dashboard tab is renamed to "Options Activity" and shows source/data-kind warnings.
- **Intended pull request:** `devin/gate-options-flow`
- **Affects trading behavior:** Yes — production options-feature eligibility and interpretation change: users without Unusual Whales can no longer run a true options-flow scan, and chain volume/OI is no longer presented as unusual/directional flow. Final merge requires Gary's explicit approval.
- **Next recommended PR:** `devin/refactor-dashboard-boundaries` (UI-001)

### UI-001: Split `dashboard.py` into tab and component modules

- **ID:** UI-001
- **Title:** Split dashboard.py into tab and component modules
- **Category:** User interface
- **Priority:** Medium
- **Status:** Completed
- **Phase 1 (done):** Extracted `Signal Journal` and `Weights` into `tradex/ui/tabs/signal_journal.py` and `tradex/ui/tabs/weights.py` on branch `devin/ui-001-phase-1` through PR #28.
- **Phase 2 (done):** Extracted `Alerts` and `Help` into `tradex/ui/tabs/alerts.py` and `tradex/ui/tabs/help.py` on branch `devin/ui-001-phase-2` through PR #30.
- **Phase 3 (done):** Extracted `Coil Detector` and `Confluence` into `tradex/ui/tabs/coil_detector.py` and `tradex/ui/tabs/confluence.py` on branch `devin/ui-001-phase-3` through PR #31.
- **Phase 4 (done):** Extracted `Scanner` into `tradex/ui/tabs/scanner.py` on branch `devin/ui-001-phase-4` through PR #32.
- **Phase 5 (done):** Extracted `Pattern Similarity — Experimental Research` into `tradex/ui/tabs/pattern_similarity.py` on branch `devin/ui-001-phase-5` through PR #33.
- **Phase 6 (done):** Extracted `Pre-Market` into `tradex/ui/tabs/premarket.py` and `Options Activity` into `tradex/ui/tabs/options_activity.py` on branch `devin/ui-001-phase-6` through PR #34.
- **Problem statement:** `tradex/ui/dashboard.py` was 2,378 lines and imported every backend module. After Phase 6 it is 444 lines; `tradex/ui/tabs/premarket.py` is 260 lines and `tradex/ui/tabs/options_activity.py` is 262 lines. All ten tabs are now routed through `tradex/ui/tabs/` modules; no tabs remain inline in `dashboard.py`.
- **Recommended action:** No further UI-001 phases required. Future UI work should use `tradex/ui/tabs/<name>.py` and keep `dashboard.py` as the router.
- **Reason:** Improves reviewability and makes the UI testable.
- **Dependencies:** TEST-001
- **Files likely affected:** `tradex/ui/dashboard.py`, `tradex/ui/tabs/__init__.py`, `tradex/ui/tabs/signal_journal.py`, `tradex/ui/tabs/weights.py`, `tradex/ui/tabs/alerts.py`, `tradex/ui/tabs/help.py`, `tradex/ui/tabs/coil_detector.py`, `tradex/ui/tabs/confluence.py`, `tradex/ui/tabs/scanner.py`, `tradex/ui/tabs/pattern_similarity.py`, `tradex/ui/tabs/premarket.py`, `tradex/ui/tabs/options_activity.py`, `tests/ui/test_signal_journal_tab.py`, `tests/ui/test_weights_tab.py`, `tests/ui/test_alerts_tab.py`, `tests/ui/test_help_tab.py`, `tests/ui/test_coil_detector_tab.py`, `tests/ui/test_confluence_tab.py`, `tests/ui/test_scanner_tab.py`, `tests/ui/test_pattern_similarity_tab.py`, `tests/ui/test_premarket_tab.py`, `tests/ui/test_options_activity_tab.py`
- **Testing requirements:** Component unit tests for each extracted tab module; smoke test that the dashboard module loads and routes correctly.
- **Acceptance criteria:** `dashboard.py` remains the canonical Streamlit entrypoint; all ten tabs still render with unchanged labels, order, and behavior; no import-time side effects from tab modules; no trading logic changed. No tabs remain inline in `dashboard.py`.
- **Intended pull request:** `devin/ui-001-phase-6` (PR #34)
- **Remaining inline tabs:** None.
- **Affects trading behavior:** No

### ARCH-001: Centralize configuration and remove import-time env loading

- **ID:** ARCH-001
- **Title:** Centralize configuration and remove import-time env loading
- **Category:** Architecture
- **Priority:** Medium
- **Status:** Completed
- **Resolved by:** `devin/centralize-config`
- **Problem statement:** Several modules call `load_dotenv()` and read `os.getenv` at import time, making tests dependent on the environment and causing global state to leak between unit tests.
- **Recommended action:** Add a typed `tradex.config` module with `TradeXSettings`, expose `settings_from_mapping` (pure) and `load_runtime_settings` (call-time `.env`/env loader), and thread explicit `settings` objects through providers, options, alerts, persistence, and the dashboard.
- **Reason:** Makes the codebase import-safe, testable, and avoids accidental coupling to a specific `.env` at import time.
- **Dependencies:** None
- **Files likely affected:** `tradex/config.py`, `tradex/data/fetcher.py`, `tradex/options/flow.py`, `tradex/alerts/notifier.py`, `tradex/alerts/policy.py`, `tradex/tracker/store.py`, `tradex/tracker/watcher.py`, `tradex/tracker/analyzer.py`, `tradex/tracker/outcome_tracker.py`, `tradex/watchlists/store.py`, `tradex/patterns/fingerprint.py`, `tradex/earnings/calendar.py`, `tradex/signals/weights.py`, `tradex/ui/dashboard.py`
- **Testing requirements:** AST import-safety tests; settings-isolation matrix; A→B→A persistence isolation for signals, watchlists, fingerprints, and earnings cache; mocked Schwab client-cache isolation; runtime loader precedence/parser/path/no-side-effect tests.
- **Acceptance criteria:** No `load_dotenv`, `os.getenv`, `os.environ`, `Path.home()`, or module-scope path expansion in `tradex/` except in `tradex/config.py`. All public entry points accept an explicit `settings: TradeXSettings | None` and fall back to `load_runtime_settings()` at call time. PR remains draft/unmerged for ChatGPT final review.
- **Intended pull request:** `devin/centralize-config`
- **Affects trading behavior:** No

---

## Low priority

### DOC-001: Close LONG-001 and restore documentation and tracker consistency

- **ID:** DOC-001
- **Title:** Close LONG-001 and restore documentation and tracker consistency
- **Category:** Documentation
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `devin/close-long-001-docs` (PR #27)
- **Problem statement:** After LONG-001 merged, `docs/PROJECT-TRACKER.md` still listed it as `In Progress` and recommended the already-completed `devin/evaluate-long-term-score` branch as the next PR. `README.md`, `CLAUDE.md`, and `SETUP.md` contained stale references: missing LONG-001 result, inconsistent dashboard tab names/order, a "Next Features to Build" list with already-delivered capabilities, and language in `SETUP.md` implying pattern similarity generated automatic alerts.
- **Recommended action:** Mark LONG-001 completed with its `inconclusive` result and `production_promotion_eligible=false`; set the tracker’s next-recommended engineering task to UI-001; synchronize `README.md`, `CLAUDE.md`, and `SETUP.md` with the current dashboard tab names, research packages, automatic-alert categories, and LONG-001 status.
- **Reason:** Canonical sources of truth must agree before starting UI-001.
- **Dependencies:** LONG-001
- **Files likely affected:** `README.md`, `CLAUDE.md`, `SETUP.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** `git diff --check`; `uv run ruff check tests scripts`; targeted `rg` searches; `uv run pytest tests -q`.
- **Acceptance criteria:** LONG-001 is marked completed; the tracker no longer recommends the completed LONG-001 branch; UI-001 is listed as the next engineering task; README/CLAUDE/SETUP agree on tab names, pattern-similarity research-only status, automatic-alert categories, and LONG-001 result.
- **Affects trading behavior:** No

### DOC-002: Establish canonical AI-development and research-governance documentation

- **ID:** DOC-002
- **Title:** Establish canonical AI-development and research-governance documentation
- **Category:** Documentation
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `devin/add-ai-development-governance`
- **Problem statement:** TradeX lacked canonical shared documentation defining the ChatGPT–Devin–Codex workflow and minimum trading-research standards. The project tracker also lived under a review-specific directory rather than the canonical documentation root.
- **Recommended action:** Create `docs/AI-DEVELOPMENT-WORKFLOW.md` and `docs/RESEARCH-PROTOCOL.md`; move the existing project tracker out of `docs/devin-review/` to `docs/PROJECT-TRACKER.md`; update all repository references; add navigation from a top-level project document.
- **Reason:** Provides a single, discoverable source of truth for AI-agent assignments and research safeguards.
- **Dependencies:** None
- **Files likely affected:** `docs/AI-DEVELOPMENT-WORKFLOW.md`, `docs/RESEARCH-PROTOCOL.md`, `docs/PROJECT-TRACKER.md`, `docs/devin-review/REPOSITORY-ORGANIZATION.md`, `docs/devin-review/DEVELOPMENT-WORKFLOW.md`, `CLAUDE.md`
- **Testing requirements:** Doc review checklist; `git diff --check`; `rg` for obsolete tracker references.
- **Acceptance criteria:** Canonical docs exist; tracker moved with history preserved; no active references to the old tracker path; top-level document points AI agents and contributors to the canonical docs.
- **Intended pull request:** `devin/add-ai-development-governance`
- **Affects trading behavior:** No

### LONG-001: Evaluate long-term scorer against 40-week MA (research-only)

- **ID:** LONG-001
- **Title:** Evaluate long-term scorer against 40-week MA (research-only)
- **Category:** Long-term trading
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `devin/evaluate-long-term-score` (PR #26)
- **Result:** `inconclusive`
- **Production promotion:** Not eligible (`production_promotion_eligible=false`)
- **Trading behavior:** Unchanged
- **Artifact location:** `docs/research/artifacts/LONG-001/2026-08-04-fc015c8f13e1/`
- **Problem statement:** The long-term score is a weekly-bar version of the short-term score and lacks fundamental or relative-strength context.
- **Recommended action:** Run a locked, point-in-time research study comparing the current production `long_term.score` to a simple 40-week moving-average baseline. Do not redesign production scoring or the dashboard until a follow-up promotion assignment is explicitly approved.
- **Reason:** A "long-term" screen should not simply be a slower momentum score.
- **Dependencies:** VAL-001
- **Files likely affected:** `tradex/research/long_term_evaluation/`, `tests/research/test_long_term_evaluation.py`, `docs/research/artifacts/LONG-001/`
- **Testing requirements:** Locked, point-in-time, split-respecting, provider-aware research study comparing `long_term.score` to a 40-week MA baseline; deterministic credential-free unit tests.
- **Acceptance criteria:** Research study concludes `supports_further_research`, `reject_or_deprioritize`, or `inconclusive` based on validation and holdout performance; no production scorer or dashboard changes made.
- **Affects trading behavior:** No

### GAP-001: Improve pre-market gap scanner

- **ID:** GAP-001
- **Title:** Improve pre-market gap scanner
- **Category:** Intraday trading
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `devin/improve-gap-scanner`
- **Problem statement:** The gap scanner used delayed yfinance pre-market bars and did not filter by liquidity, spread, or catalyst.
- **Recommended action:** Refactor into `tradex/premarket/` with typed `GapScanConfig`, `PremarketSnapshot`, `DailyLiquidityBaseline`, `SpreadSnapshot`, and `GapCatalystContext` models; add liquidity/spread/catalyst filters (all opt-in); link to earnings/news context; restrict to pre-market hours unless explicitly enabled; expose `scan_gaps_with_report` public API and CLI; update dashboard and watcher to use structured reports.
- **Reason:** Gaps without liquidity or catalyst context are not tradable; structured reports make scan quality visible and testable.
- **Dependencies:** COR-005
- **Files likely affected:** `tradex/premarket/{config,models,sources,catalysts,gap_scanner,cli,__main__}.py`, `tradex/ui/dashboard.py`, `tradex/tracker/watcher.py`, `tests/premarket/`, `README.md`, `SETUP.md`
- **Testing requirements:** Unit tests with mocked pre-market data covering configuration validation, source filtering, liquidity baselines, spread semantics, catalyst context, `scan_gaps_with_report` orchestration, CLI help, and no network on weekends/holidays.
- **Acceptance criteria:** `scan_gaps_with_report` returns a typed `GapScanReport` with counts, observations, and results; all new filters are opt-in; default behavior and alert thresholds unchanged; spread never inferred from candle range; no live API calls in tests.
- **Intended pull request:** `devin/improve-gap-scanner`
- **Affects trading behavior:** Yes — opt-in eligibility/filter change explicitly approved by Gary (filters are opt-in; default gap scanner behavior, gap tiers, and alert thresholds are preserved)

### DEC-001: Adopt Architectural Decision Records

- **ID:** DEC-001
- **Title:** Adopt Architectural Decision Records
- **Category:** Documentation
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `devin/add-initial-adrs`
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
| High | 17 | LONG-002: Long-only rapid-upside opportunity research program |
| Medium | 12 | SHORT-001: Add market regime and relative strength to short-term scorer |
| Low | 5 | DOC-001: Close LONG-001 and restore documentation and tracker consistency |

## Summary by status

| Status | Count |
|---|---|
| Completed | 32 |
| Deferred | 1 |
| Proposed | 0 |
| In progress | 1 |
| Blocked | 0 |

The original engineering-foundation and UI-refactor backlog is substantially complete. `SHORT-001` is closed as Completed — Not supported. `INTRA-001B` produced a locked 2025 dataset manifest and safe artifacts with the 1Day-ranking amendment accepted. `INTRA-001C` is complete and accepted: the synthetic intraday engine and its tests produce deterministic `synthetic=true`, `evidence_eligible=false` artifacts and do not access real data or production behavior. `INTRA-001D` is complete: the locked real-data study ran on `INTRA-001B-DATASET-V1` with frozen evaluation code, produced real diagnostic trade/sample metrics, and returned `inconclusive`; the holdout was not parsed. No further work on the `INTRA-001` hypothesis is authorized without a new Gary-approved plan. `LONG-002A` is now the active research contract: a locked, research-only rapid-upside opportunity program distinct from `LONG-001` and `INTRA-001`. `DAYTRADE-001` is a future, deferred real-time day-trading program sequenced after `LONG-002` unless Gary explicitly reprioritizes.

**Remaining non-completed items:**
1. **LONG-002** — `LONG-002A` locked research contract (in progress on `devin/long-002a-locked-research-contract`).
2. **DAYTRADE-001** — Future real-time day-trading decision-support program (deferred until after `LONG-002`).

**Recommended next work order:**
1. **LONG-002A** — Review and accept the locked `LONG-002` research contract.
2. **LONG-002B** — Core data feasibility and point-in-time dataset contract, only after `LONG-002A` acceptance.
3. **Separate Gary-approved production PR** — Only if a future research phase (e.g., `LONG-002I`) passes validation and holdout and the methodology remains valid. No production promotion is currently warranted.

**Recommended next pull request order:**
1. `devin/long-002a-locked-research-contract` — `LONG-002A` locked research/discovery contract.

