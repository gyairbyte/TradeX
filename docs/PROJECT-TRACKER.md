# TradeX Project Tracker

This is the master backlog for TradeX engineering and research tasks, originating from the initial repository review. Items are grouped by priority (High, Medium, Low) and then by category. Update this tracker as work is accepted, started, blocked, completed, or rejected.

> **Implementation-Agent Governance Note:** Prospective implementation and build work is executed by **Antigravity** under the ChatGPT–Antigravity–Codex workflow (see [`docs/AI-DEVELOPMENT-WORKFLOW.md`](AI-DEVELOPMENT-WORKFLOW.md)) using `antigravity/` branch naming. Historical references to `devin/...` branches, PRs, and completion records are intentionally preserved throughout this tracker to maintain an accurate historical record of previously completed work.

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
- **Next recommended PR:** `devin/mvp-arch-001-consolidation-decision` — `LONG-002A`, `LONG-002B`, and `LONG-002B-AMEND-002` are completed; `LONG-002C` design is authorized by PR #52 but paused by Gary while `MVP-ARCH-001` is completed.

### LONG-002: Long-only rapid-upside opportunity research program

- **ID:** LONG-002
- **Title:** Long-only rapid-upside opportunity research program
- **Category:** Long-term trading
- **Priority:** High
- **Status:** Completed — background research
- **Governance Note:** The prior research roadmap is no longer the active MVP implementation path. LONG-MVP-001 and LONG-MVP-002 supersede it for product implementation. All historical phase records, frozen artifacts, and diagnostic evidence are preserved as completed background research.
- **Completed phase:** `LONG-002A` — locked research/discovery contract (merged in PR #48)
- **Completed phase:** `LONG-002B` — core data feasibility and point-in-time dataset contract (merged in PR #49)
- **Completed phase:** `LONG-002B-AMEND-002` — Gary-approved selection of Option 2 fail-closed unknown policy (merged in PR #52)
- **Completed phase:** `LONG-002C-DESIGN-001` — outcome census, master episodes, endpoint feasibility, and baseline design specification (merged in PR #84 at commit `61d392c1ca7222f15954cb684d54d6fcc39b4181`)
- **Completed phase:** `LONG-002C-EXEC-001` — Build Development Dataset, Outcome Census, Episodes, and Frozen Baselines (PR #85, valid official development run `2026-09-27-161243`, execution code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`; approved as valid development evidence; preregistered PRIMARY endpoint retained: clean +10% / 10 sessions; strongest development baseline frozen: `volatility_aware_momentum_5`; validation and holdout remain unopened/unauthorized; shadow untouched; production promotion unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`)
- **Completed phase:** `LONG-002D1` — Core Technical & Market-Context KPI Census (PR #92; official corrected run `2026-09-28-003539`, spec SHA-256 `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381`; `atr_pct_14` strongest univariate association 2.2816x lift; `relative_volume_20` showed 1.1307x lift with low ATR/momentum correlation; candidate features set to `review_pending`)
- **Completed phase:** `LONG-002D2` — Incremental Ranking Value of Relative Volume Beyond Frozen VAM5 (`LONG-002D2-INCREMENTAL-RERANK-001`; authorized by Gary Yang on 2026-09-28; dedicated preregistration commit `494caa8df3e60bae15e5015ad98a42a13eb109f3`, spec SHA-256 `db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8`; initial run `2026-09-28-143047` was superseded under `LONG-002D2-CORR-001` due to unrecorded execution code provenance; official corrected run `2026-10-04-002604` (committed execution code SHA `e494f12dfa526a62e5014572d335510099a3a024`); primary candidate `relative_volume_20` disposition: `NOT_SUPPORTED`, candidate precision 12.4321% vs matched VAM5 15.3533%, absolute delta -2.9212 pp, 21-session block bootstrap 95% CI [-0.0352, -0.0235], annual stability 0/5 years positive; secondary challenger `sma20_slope_5` underperformed with 11.9950% precision, delta -3.3583 pp, 21-session 95% CI [-0.0415, -0.0258]; descriptive SPY return regimes confirmed uniform negative delta across lower, middle, and upper market environments; validation, holdout, and shadow remain strictly quarantined; production promotion unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`)
- **Completed phase:** `LONG-002D3A` — Blinded Review Tooling, Pilot Freeze, and Main-Study Contract Foundation (`LONG-002D3A-BLINDED-REVIEW-PILOT-001`, updated under `LONG-002D3A-CORR-001`; authorized by Gary Yang on 2026-10-03, CORR-001 authorized 2026-10-04; dedicated preregistration commit `a6345f97330358b1dfbbdf7c11e6aba9f10e2c87`, spec SHA-256 `7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427`; correction contract spec `docs/research/specs/LONG-002D3A-CORR-001.json`, SHA-256 `f0c239ab934cb7435ed914a33e1224b490974218016b442cba4793a7a8f87cfe`; D3A tooling completed; human pilot review WAIVED BY GARY / NOT EXECUTED; 24 pilot labels: none; 240-case main human study: not generated and waived for current quantitative path; no human-label evidence used; external answer key remains unrevealed and quarantined; D3A tooling preserved for potential future reactivation under separate authorization; validation/holdout access unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`)
- **Completed phase:** `LONG-002D3B` — Quantitative-Only Research Amendment, Final Feature Registry Freeze, and Recommendation-Episode Evaluation Contract (`LONG-002D3B-QUANTITATIVE-FREEZE-001`; authorized by Gary Yang on 2026-10-05; formal research contract amendment `LONG-002D-AMEND-001` waives discretionary human blinded chart review and records 0 human labels collected; final quantitative feature registry frozen in `docs/research/artifacts/LONG-002D3B/feature_registry.json` across all 15 D1 features; Stage C baseline `volatility_aware_momentum_5` remains frozen without retuning; D2 negative findings preserved with `relative_volume_20` and `sma20_slope_5` prohibited as standalone rankers; post-hoc deep pullback finding excluded from E absent separate preregistration; recommendation-episode evaluation contract frozen in `docs/research/artifacts/LONG-002D3B/recommendation_episode_contract.json` with 21-session cap and anti-double-count reset rule to prevent persistent daily signal inflation; no new empirical study; readiness disposition `ready_for_long_002e_authorization` with `long_002e_authorized: false`; validation, holdout, and shadow splits remain strictly unopened and quarantined; LONG-002E model fitting remains unauthorized pending separate Gary authorization; production promotion unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`)
- **Completed phase:** `LONG-002E1` — Preregistered Round-1 Candidate Search (`LONG-002E1-ROUND1-CANDIDATE-SEARCH-001`, updated under `LONG-002E1-CORR-001`; authorized by Gary Yang on 2026-10-05; preregistration commit `49103f84ffbf7cd7b60216c2866ad103282bae58`, spec SHA-256 `d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0`; correction spec SHA-256 `6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96`; official corrected run `LONG-002E1-20261006_152832`; 36 material configurations evaluated across 3 families on 2018–2020 development data [730 sessions, 610,648 rows]; all 12 rank models `round1_not_supported`; all 12 logistic and 12 GBDT models `round1_inconclusive` achieving 2 of 3 positive years; overall disposition `no_round2_candidate_supported`; 0 candidates eligible for Round 2; Round 2 unauthorized; search budget: 36 consumed, 12 unused of 48)
- **Completed phase:** `LONG-002E2` — Development-Only Logistic Regime/Stability Diagnostic and Round-2 Research Decision Gate (`LONG-002E2-LOGISTIC-STABILITY-DIAGNOSTIC-001`, updated under correction contract `LONG-002E2-CORR-001`; authorized by Gary Yang on 2026-10-06; dedicated preregistration commit `90f3b3daa8c6ac234da724e8ad1ce2ec629a1bc7`, spec SHA-256 `cec5105883198cbd856c763cd39993fa1e2f72960fd7c4c5bb17dbfd2a0f9519`; correction contract `docs/research/specs/LONG-002E2-CORR-001-v1.json`, SHA-256 `4e57fb503d99bab5e02a90461eb2da6ce32825f065075c85587e8fec225c74a0` correcting representative model hyperparameter metadata from erroneous C=300.0 to canonical C=3.0 matching canonical E1 `configuration_registry.json` without empirical rerun; official execution code SHA `bbb9b136c54cde87de143e9ea7b033e4ed21bbdb`; official run ID `LONG-002E2-20261006_183219`; investigated representative configuration `LOGIT_S4_C300` [reproduced P@10 26.8109%, +2.7216 pp vs matched VAM5; 2018 delta +3.9841 pp, 2019 delta +5.0000 pp, 2020 delta -1.4520 pp exact match to 6 decimal places] and confirmed all 12 tested E1 logistic configurations exhibited the same annual sign pattern [2018+, 2019+, 2020-], therefore the 2020 reversal was not unique to `LOGIT_S4_C300` within the tested Round-1 logistic grid; 2020 net hit loss is -31 hits; Rule A Calendar Localization FAILED [dominant quarter 2020Q1 loss share 37.50% < 60% threshold, remaining 3 quarters delta -13 hits]; Rule B Market-Context Localization FAILED [dominant SPY regime UPPER loss share 83.87% >= 60%, but remaining 2 regimes delta -5 hits violating >= 0 threshold]; diagnostic disposition: `no_bounded_regime_hypothesis_supported`; recommended next action: `close_initial_long_002e_search_preserve_unused_budget`; search budget strictly preserved at 36 consumed / 12 unused of 48; Round 2 unauthorized [`round2_authorized: false`]; validation, holdout, and shadow remain strictly unopened and quarantined; zero live network or provider calls; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved)
- **Research contract:** `docs/research/LONG-002.md`
- **Locked machine-readable specification:** `docs/research/specs/LONG-002-v1.json`
- **Design specification:** `docs/research/LONG-002C-DESIGN.md`
- **Design specification (machine-readable):** `docs/research/specs/LONG-002C-design-v1.json`
- **Execution report:** `docs/research/LONG-002C-EXECUTION-REPORT.md`
- **Committed summary artifacts:** `docs/research/artifacts/LONG-002C/2026-09-27-161243/` (official approved development run); `docs/research/artifacts/LONG-002C/2026-09-21-043414/` (historical preliminary debugging run; `invalid_evidence`)
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
- **Recommended action:** Gary Yang and ChatGPT approved the `LONG-002C-EXEC-001` Stage C empirical execution on 2026-09-27 as valid development evidence on official run `2026-09-27-161243` (execution code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`). Review decisions: retain the preregistered PRIMARY endpoint (clean +10% / 10 sessions, `primary_retained`; fallback not invoked); freeze `volatility_aware_momentum_5` as the strongest development baseline comparator for future LONG-002 research (does not authorize production use or establish out-of-sample predictive validity); record proposed validation evidence-sufficiency gates as approved research gates for future use. The prior preliminary run `2026-09-21-043414` remains preserved as historical/debug evidence only (`invalid_evidence`). Next step: STOP; progression to subsequent research phase `LONG-002D` requires explicit Gary Yang / ChatGPT authorization; validation and holdout splits remain strictly unopened and quarantined; shadow remains untouched; production promotion remains unauthorized (`APPROVED_PRODUCTION_STRATEGIES == ()`).
- **Testing requirements:** `tests/research/long_002c/`; `tests/research/long_002c_design/`; `tests/research/test_long_002_spec.py`; `uv run ruff check tradex/research/long_002c tests/research/long_002c`; `git diff --check`.
- **Acceptance criteria:** PIT universe-construction preflight implemented; identity, market-cap, IPO, price-series, and baseline bugs resolved; regression test suite passing; external row-level Parquet datasets saved to gitignored `data/research/long_002c/`; summary JSON artifacts and checksums committed to `docs/research/artifacts/LONG-002C/2026-09-27-161243/`; validation/holdout untouched; PR #85 remains draft and unmerged.
- **Intended pull request:** `antigravity/long-002c-exec-001` (draft PR #85)
- **Affects trading behavior:** No — research-only execution; no production scorer, score, weight, threshold, ranking, eligibility, confluence, alert, or dashboard trading logic changes.
- **Historical note:** `LONG-002B-AMEND-001` results are preserved as historical artifacts and are superseded by the later `LONG-002B-AMEND-002` Option 2 decision.
- **Amendment results:** `docs/research/LONG-002B-AMEND-001.md`
- **Amendment probe spec:** `docs/research/specs/LONG-002B-AMEND-001-probe-v1.json`
- **Amendment safe artifact bundle:** `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647/`
- **Amendment overall disposition:** `not_supported` (security identity and earnings-event timing both remain blocked; `LONG-002C` is not authorized)
- **Amendment per-family dispositions:**
  - Security identity, lifecycle, and exclusion classification: `not_supported` (Massive partial; every `(symbol, as_of_date)` PIT row is classified independently; unresolved historical rows with generic or missing `type` codes and no corroborating name/SIC signal fail closed to `unknown`; later/current rows are never backfilled as historical fact; PFF classified as `ETF`, SPY as `ETF`, IGR as `closed_end_fund`, IPOD as `pre_merger_spac`)
  - Earnings-event timing: `not_supported` (no preregistered endpoint returned a historical known-at-time earnings schedule; `vX/reference/financials` provides XBRL filing/period dates only; `sec_edgar` and `yahoo_earnings_calendar` fallbacks were not exercised and are recorded as `unverified` with `request_count=0`; fail-closed `unknown` treatment is explicitly not adopted)
- **Amendment provider calls:** 64 of 120 HTTP requests; 0 retries; 0 provider switches; ~12.5 minutes runtime
- **Completed phase:** `LONG-002B-AMEND-002` — Gary-approved selection of Option 2 (fail-closed unknown policy) and contract amendment before `LONG-002C` design PR
- **Selection amendment:** `docs/research/LONG-002B-AMEND-002.md`
- **Selection payload (machine-readable):** `docs/research/specs/LONG-002B-DEC-001.json` and `docs/research/specs/LONG-002B-AMEND-002.json`
- **Decision status:** `gary_approved` (selected Option 2)
- **Completed design phase:** `LONG-002C-DESIGN-001` (merged in PR #84 at commit `61d392c1ca7222f15954cb684d54d6fcc39b4181`)
- **Completed execution phase:** `LONG-002C-EXEC-001` (PR #85; official development run `2026-09-27-161243`, code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`; approved as valid development evidence; preliminary run `2026-09-21-043414` noted as historical/debug evidence only)
- **LONG-002C dataset construction authorized:** `true` (authorized by Gary on 2026-09-21; empirical execution completed 2026-09-27)
- **LONG-002C execution disposition:** `valid_development_evidence` / `primary_retained` (clean +10% / 10 sessions retained; development baseline `volatility_aware_momentum_5` frozen)
- **Validation/holdout data access authorized:** `false` (remains strictly quarantined)
- **Production promotion eligible:** `false` (`APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved)
- **Next phase:** The prior research roadmap is no longer the active MVP implementation path. LONG-MVP-001 and LONG-MVP-002 supersede it for product implementation.

### LONG-MVP-001: Define the Production-Target Long Opportunity Strategy v1 Contract

- **ID:** LONG-MVP-001
- **Title:** Define the Production-Target Long Opportunity Strategy v1 Contract
- **Category:** Long-term trading
- **Priority:** High
- **Status:** Completed when merged
- **Classification:** Production-target design
- **Resolved by:** `antigravity/long-mvp-001-strategy-contract`
- **Problem statement:** TradeX lacked a clear, implementable, and production-target long opportunity strategy contract. Legacy long scoring used a 5-indicator weekly heuristic with user-tunable weights, while the LONG-002 research program became too research-process-heavy for immediate MVP production delivery.
- **Recommended action:** Define ONE explainable, deterministic MVP long-side strategy contract across three established market archetypes (`momentum_continuation`, `trend_pullback`, `breakout_expansion`) over a 5–21 session holding horizon using daily OHLCV bars; specify the 100-point opportunity scoring formula, eligibility floor, execution states (`ENTER NOW`, `ARMED`, `QUALIFIED WAITLIST`), trigger/invalidation contracts, display caps, and PR 2 implementation impact map in `docs/product/LONG-MVP-001.md`.
- **Reason:** Establishes the authoritative product and engineering foundation for end-to-end implementation in PR 2 without black-box ML or further research delays.
- **Dependencies:** None
- **Files affected:** `docs/product/LONG-MVP-001.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Offline documentation and contract verification; `git diff --check`; standard CI suite.
- **Acceptance criteria:** All 24 acceptance criteria satisfied; exact 100-point score; three archetypes locked; daily 5–21 session horizon defined; PR 2 implementation map complete; `APPROVED_PRODUCTION_STRATEGIES` remains empty; zero production behavior changes.
- **Intended pull request:** `antigravity/long-mvp-001-strategy-contract`
- **Affects trading behavior:** No

### LONG-MVP-002: Implement Production-Target Long Opportunity Strategy v1 End-to-End

- **ID:** LONG-MVP-002
- **Title:** Implement Production-Target Long Opportunity Strategy v1 End-to-End
- **Category:** Long-term trading
- **Priority:** High
- **Status:** Completed — pending review/merge
- **Classification:** Production trading-logic implementation
- **Resolved by:** `antigravity/long-mvp-002-strategy-impl`
- **Problem statement:** TradeX still runs the legacy weekly 5-indicator heuristic for long scans. The new explainable three-archetype daily strategy defined in LONG-MVP-001 must be implemented end-to-end to deliver the long-side opportunity engine in production.
- **Recommended action:** Implement the daily long data fetcher preset, indicators in `tradex/signals/indicators.py`, the LONG MVP v1 scoring engine in `tradex/signals/long_term.py`, detach long scoring from user-tunable `LongWeights`, extend the screener observation schema in `tradex/screener/engine.py`, and update UI surfaces in `tradex/ui/`.
- **Reason:** Replaces legacy weekly scoring with an explainable, deterministic, multi-archetype daily swing engine.
- **Dependencies:** LONG-MVP-001
- **Files likely affected:** `tradex/data/fetcher.py`, `tradex/signals/indicators.py`, `tradex/signals/long_term.py`, `tradex/signals/weights.py`, `tradex/screener/engine.py`, `tradex/tracker/watcher.py`, `tradex/tracker/confluence.py`, `tradex/ui/dashboard.py`, `tradex/ui/tabs/scanner.py`, `tradex/ui/tabs/weights.py`, tests.
- **Testing requirements:** Comprehensive unit and integration test suites covering all 3 archetypes, eligibility floor, state assignments, confluence compatibility, and UI rendering.
- **Acceptance criteria:** Daily long scans return qualified candidates with `primary_setup`, `state`, `trigger`, `invalidation`, `component_scores`; deterministic tie-breaking verified; detached from user weights; Gary's explicit approval required before merge.
- **Intended pull request:** `antigravity/long-mvp-002-strategy-impl`
- **Affects trading behavior:** Yes
- **Gary approval required before merge:** Yes

### MVP-ARCH-001: TradeX product consolidation decision packet

- **ID:** MVP-ARCH-001
- **Title:** TradeX provider, strategy, and dashboard consolidation plan
- **Category:** Architecture / Product
- **Priority:** High
- **Status:** Completed — Gary approved (design-only)
- **Branch:** `devin/mvp-arch-001-consolidation-decision`
- **Problem statement:** TradeX has a strong modular foundation but presents as a collection of scanners, context tools, and research pipelines; a single understandable daily decision workflow for Gary is needed before any further research-to-production promotion.
- **Recommended action:** The design-only product-architecture direction has been approved by Gary Yang on 2026-08-19. Each consolidation rollout step now requires separate Gary approval before implementation. No implementation, provider call, dashboard change, alert change, database migration, `LONG-002C` dataset construction, or production behavior change is authorized by this approval.
- **Reason:** Without explicit consolidation, the product risks surfacing unvalidated heuristics as actionable signals.
- **Dependencies:** `LONG-002B-AMEND-002` (merged PR #52)
- **Files affected:** `docs/product/MVP-ARCH-001.md`, `docs/product/MVP-ARCH-001.json`, `tests/product/test_mvp_arch_001.py`, `README.md`, `CLAUDE.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Deterministic `tests/product/test_mvp_arch_001.py`; scoped lint; `git diff --check`; full `pytest`; GitHub CI.
- **Acceptance criteria:** Packet is human-readable, machine-readable, fully auditable, makes no implementation/provider/dashboard/alert/schema/data changes, records Gary's design-only approval, and keeps all rollout implementation steps pending separate Gary approval.
- **Intended pull request:** `devin/mvp-arch-001-consolidation-decision`
- **Affects trading behavior:** No
- **Authorization status:** `gary_approved` (design-only); `production_promotion_eligible`: `false`
- **Rollout Step 1 (MVP-ARCH-001-R1):** Gary Yang approved rollout step 1 on 2026-08-21 for truthful UI/help labeling and evidence-state notices only (implemented in PR #57).
- **Rollout Step 2 (MVP-ARCH-001-R2):** Gary Yang approved rollout step 2 on 2026-08-21 for provider lifecycle and configuration simplification only (implemented and merged in PR #58).
- **Rollout Step 3 (MVP-ARCH-001-R3):** Gary Yang separately approved rollout step 3 on 2026-08-22 for navigation consolidation only (implemented and merged in PR #59).
- **Rollout Step 5A (MVP-ARCH-001-R5A):** MVP-ARCH-001-R5A was separately Gary-approved on 2026-08-23 for candidate snapshot domain contract and schema v4 persistence primitives only and implemented by PR #61.
- **Rollout Step 5B (MVP-ARCH-001-R5B):** MVP-ARCH-001-R5B was separately Gary-approved on 2026-08-23 and implemented by PR #62 for prospective scorable-observation aggregation and descriptive exploratory CandidateDossier persistence only.
- **Rollout Step 5C (MVP-ARCH-001-R5C):** MVP-ARCH-001-R5C was separately Gary-approved on 2026-08-23 and implemented by PR #63 for truthful read-only Today landing surface, in-place Candidate Detail drill-down, and snapshot history query layer only (Steps 6–8 remain pending separate Gary approval; no production strategy was promoted; no actionable candidate states were created; no candidate persistence writes were performed; no provider calls were added; schema remains v4; LONG-002C remains paused; completion of R5C does not automatically authorize the next implementation PR).
- **Rollout Step 6 Readiness A (MVP-ARCH-001-R6-READINESS-A):** Normative executable Journal data, lifecycle, and persistence contract defined in `docs/product/MVP-ARCH-001-R6-DATA-CONTRACT.md` (implemented and merged via PR #64; design-only; schema remains v4; strategy promotion unauthorized).
- **Rollout Step 6 Implementation A (MVP-ARCH-001-R6-IMPL-A):** Gary Yang approved rollout step 6 implementation slice A on 2026-08-28 for executable Journal persistence, lifecycle service, outcome calculations, and Schema v5 migration only (implemented and merged via PR #67 commit `b8c80941c41545ef72830a53de2f087107564c7b`).
- **Rollout Step 6 Implementation B (MVP-ARCH-001-R6-IMPL-B):** Gary Yang explicitly approved rollout step 6 implementation slice B on 2026-08-29 for executable Journal read-only UI projection, domain read models (`tradex/journal/queries.py`), top-level Tab 5 Journal integration, and relocation of legacy scanner telemetry under Research Lab (merged via PR #68, merge commit `2605645aaba77a80ff9907d434d851ee8e6d1564`; schema remained v5; `APPROVED_PRODUCTION_STRATEGIES == ()`).
- **Rollout Step 7 PIT Capture Foundation (MVP-ARCH-001-R7-PIT-001A):** Gary Yang explicitly approved rollout step 7 implementation slice A on 2026-08-29 for prospective earnings point-in-time capture foundation (`tradex/pit/`, models, store, earnings capture bypassing 24-hour cache, one-shot CLI, and additive Schema v6 migration) only. Merged on `main` via PR #69; Schema v6 introduced by this step.
- **Rollout Step 7 PIT Capture Foundation (MVP-ARCH-001-R7-PIT-001B):** Gary Yang explicitly approved R7-PIT-001B for prospective Massive/Polygon security/reference-data capture foundation (Massive adapter, reference capture service, reference store tables, reference capture CLI, and additive Schema v7 migration). Merged on `main` via PR #70 at commit `6047691549315936d679c845abb61fd727a241fa`; Schema v7 is the active schema version; `APPROVED_PRODUCTION_STRATEGIES == ()`; LONG-002C remains paused; R8 remains unauthorized; DAYTRADE-001 remains deferred.
- **Rollout Step 7 PIT Operations Runner (MVP-ARCH-001-R7-PIT-001C1):** Gary Yang explicitly approved (Gary-approved 2026-09-02) R7-PIT-001C1 for the deterministic PIT operations runner, versioned universe manifest, and capture health layer. Implementation record: PR #71 (merged at commit `e111c04107b929b0b2ae8896755d57ec9b114f95`). Deliverables: `tradex/pit/ops.py` (PITUniverseManifest, load_universe_manifest, estimate_capacity, run_pit_slot, get_pit_slot_health, CLI), `list_earnings_capture_runs`/`list_reference_capture_runs` read-only store APIs, `DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS` module-level constant, new test files, `docs/product/R7-PIT-OPERATIONS.md`. Schema remains v7. NO OS scheduler; NO active universe selected; NO strategy promotion; `APPROVED_PRODUCTION_STRATEGIES == ()`; C2 (scheduler installation + universe selection) remains unauthorized; R8 remains unauthorized; DAYTRADE-001 remains deferred.
- **Rollout Step 7 PIT Universe Capacity & C2 Readiness (MVP-ARCH-001-R7-PIT-001C2-READINESS-A):** Gary Yang explicitly authorized R7-PIT-001C2-READINESS-A for research/design-readiness evaluation of initial prospective PIT universe capacity under Massive free-tier pacing. Five frozen candidate manifests derived from committed presets at `e111c04107b929b0b2ae8896755d57ec9b114f95` (`SECTOR_ETFS`, `DOW30`, `DOW30 + SECTOR_ETFS`, `SP100`, `SP100 + SECTOR_ETFS`) with `effective_from = "2099-01-01"`; decision packet `docs/product/artifacts/r7-pit-c2-readiness-a/decision.json` and report `docs/product/R7-PIT-C2-READINESS-A.md` completed. Capacity analysis is complete, but operational activation is blocked pending resolution of the C1 all-known capture-success criterion (`operational_readiness_status: "blocked_pending_capture_status_compatibility_decision"`). Merged on `main` via PR #73 at commit `93d2174fed72f325e4ea87199c2aac9045998cbb`. Active universe remains unselected (`selected_universe = null`); active universe authorization is `false`; C2 implementation remains unauthorized; scheduler remains unauthorized; R7 remains incomplete; Schema remains v7; `APPROVED_PRODUCTION_STRATEGIES == ()`; LONG-002C remains paused; R8 remains unauthorized; DAYTRADE-001 remains deferred.
- **Rollout Step 7 PIT Observation Completeness & Health Semantics (MVP-ARCH-001-R7-PIT-STATUS-DEC-001):** Gary Yang authorized R7-PIT-STATUS-DEC-001 as design-only to resolve the capture-status ambiguity exposed by READINESS-A before universe selection or C2 scheduler activation. Gary Yang approved the architectural direction (Option 2 + Option 3: orthogonal operational health & evidence completeness, with applicability-aware semantics) on 2026-09-09 in the ChatGPT workflow (`MVP-ARCH-001-R7-PIT-STATUS-DEC-001-APPROVAL`). Recorded in `docs/product/R7-PIT-STATUS-DEC-001.md`, `docs/product/artifacts/r7-pit-status-dec-001/decision.json`, and `docs/product/artifacts/r7-pit-status-dec-001/approval.json` (`selected_status_policy: "option_2_plus_3"`). Approval is for architecture direction only; does not authorize production status semantics implementation. Current C1 all-known health semantics remain the active production behavior; operational activation remains blocked; active universe remains unselected (`selected_universe = null`); production status semantics remain unchanged; Schema remains v7; schema migration unauthorized; provider study unauthorized; C2 implementation unauthorized; scheduler unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`; R7 remains incomplete; LONG-002C remains paused; R8 unauthorized; DAYTRADE-001 deferred.
- **Rollout Step 7 PIT Earnings Provider / Provenance Hardening (MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001):** Gary Yang explicitly approved MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001 on 2026-09-09 to harden the Yahoo/yfinance earnings lookup path so TradeX prospectively distinguishes technical provider failures from clean no-usable-upcoming-date results without collapsing them into generic unavailable errors. Implementation record: branch `antigravity/mvp-arch-001-r7-pit-status-harden-001`. Introduced single-inheritance typed exceptions (`EarningsProviderLookupError`, `EarningsProviderResponseError`), deterministic strategy precedence (valid date -> response error -> technical error -> unavailable), sanitized error payloads in SQLite and domain models, preserved Schema v7 and contract version 1 with zero DB migrations, and left strict all-known C1 operational run and slot health semantics in `tradex/pit/ops.py` completely unchanged. Live-provider empirical study, candidate universe activation (Candidate B/C), C2 scheduler installation, and production strategy promotion remain unauthorized pending separate Gary authorization; Schema remains v7; `APPROVED_PRODUCTION_STRATEGIES == ()`; R7 remains incomplete; LONG-002C remains paused; R8 remains unauthorized; DAYTRADE-001 remains deferred.
- **Rollout Step 7 PIT Provider Compatibility Study (MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001):** Gary Yang explicitly authorized `MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001` on 2026-09-10 to execute a bounded live provider-compatibility study across Candidates B and C to determine mapping and fallback behavior for the approved option_2_plus_3 semantics. (1) A historical missing-credential preflight run on 2026-09-11 verified the safety abort mechanism and blocked execution with zero live provider calls (`incomplete_environment_or_provider_block`). (2) On 2026-09-17, following credential configuration, the authorized single live run was executed cleanly from protocol commit `5731baacf73197a15eb9c72c1d6eb2e16a09962b` across all 45 Candidate C symbols (45/45 Yahoo attempted yielding 30 KNOWN equities and 15 CLEAN_NO_USABLE_UPCOMING_DATE ETFs; 45/45 Massive attempted yielding 45 KNOWN with 30 `CS` and 15 `ETF` provider type codes, and zero provider errors, aborts, or market-date rollovers; final disposition `completed_evidence_sufficient_for_next_decision`). The empirical study is Completed and provides sufficient evidence for subsequent architecture decisions. Active universe remains unselected (`selected_universe = null`); Option 2+3 production semantics remain unauthorized and not implemented; Schema remains v7 and contract remains v1; C2 implementation remains unauthorized; scheduler remains unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`; R7 remains incomplete; LONG-002C remains paused; R8 remains unauthorized; DAYTRADE-001 remains deferred.
- **Rollout Step 7 PIT Status & Applicability Implementation Readiness (MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001):** Produced the final, implementation-ready normative design contract and machine-readable artifact for TradeX's Gary-approved Option 2 + Option 3 point-in-time architecture following completion of the empirical Yahoo/Massive provider study (`MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001`). Implementation record: branch `antigravity/mvp-arch-001-r7-pit-status-impl-readiness-001`. Deliverables: `docs/product/R7-PIT-STATUS-IMPL-READINESS-001.md`, `docs/product/artifacts/r7-pit-status-impl-readiness-001/decision.json`, and focused product contract tests in `tests/product/test_r7_pit_status_impl_readiness_001.py`. Locks manifest contract v2, versioned manifest hashing (v1 exact preservation, v2 applicability hashing), Schema v8 constraints across all 4 PIT tables, version-aware nullable manifest_hash (NULL for v1 rows, NOT NULL for v2 rows), truthful provenance without fictitious provider names or zero-duration timestamps, deterministic operational health truth table (no undefined hung timeouts; STARTED runs mapped to DEGRADED), deterministic count-based evidence completeness (no arbitrary 50% threshold; slot-level aggregation requiring all expected families COMPLETE, SPARSE if any family has applicable facts but zero known, pooled ratio informational only), skip-provider-call behavior for NOT_APPLICABLE, and 14-step SQLite table rebuild procedure inside a single atomic transaction. Future implementation decomposed into Implementation PR A (primitives & Schema v8), PR B (two-dimensional operational/read model semantics & CLI), and PR C (universe selection & C2 activation). Design-only / implementation-readiness only: zero changes under `tradex/`, zero schema migrations executed, zero provider calls made, Candidate B and C remain unselected (`selected_universe = null`), C2 implementation remains unauthorized, scheduler remains unauthorized, `APPROVED_PRODUCTION_STRATEGIES == ()`, and R7 remains incomplete.
- `long_002b_amend_002_completed`: `true`
- `long_002c_design_authorized_by_pr52`: `true`
- `long_002c_currently_paused_by_gary`: `true`
- `long_002c_dataset_construction_authorized`: `false`
- `long_002c_work_authorized_by_mvp_arch_001`: `false`


### DAYTRADE-001: Future real-time day-trading decision-support program

- **ID:** DAYTRADE-001
- **Title:** Future real-time day-trading decision-support program
- **Category:** Intraday trading
- **Priority:** High
- **Status:** Deferred
- **Description:** A separate real-time day-trading decision-support program based on Gary's actual 3-year daily, 133-tick, 1-minute, and 50-tick workflow.
- **Note:** Explicitly separate from INTRA-001; not assumed to be VWAP-based; no production promotion eligible. DAYTRADE-001 remains closed as recorded research evidence with zero production promotion (development rejected, validation inconclusive, holdout unread and unacquired); strategy registry remains empty (`APPROVED_PRODUCTION_STRATEGIES == ()`).
- **Slice DAYTRADE-001A (Research MVP Foundation):** Completed on branch `antigravity/daytrade-001a-mvp-skeleton` (merged via PR #86). Research contract locked in `docs/research/DAYTRADE-001A.md`. Core multi-resolution data container and point-in-time access semantics implemented in `tradex/research/daytrade_mvp/`. Evaluator enforces strict point-in-time materialization (zero future-bar leakage) and fail-closed resolution validation. Architectural smoke setup `SYNTH-DAYTRADE-001` proves 4-tier multi-resolution evaluation on deterministic synthetic fixtures with zero provider calls. No real strategy hypothesis approved; no provider study authorized; `APPROVED_PRODUCTION_STRATEGIES == ()` preserved; zero interaction with parallel LONG-002 Stage C execution.
- **Slice DAYTRADE-001B (Locked Reversal Study Specification):** Preregistered locked study specification in `docs/research/specs/DAYTRADE-001B-v1.json` and human-readable contract in `docs/research/DAYTRADE-001B.md`. Zero provider calls. Tested 1-minute downside reversal hypothesis on Dow 30 universe across 2025.
- **Slice DAYTRADE-001C1 (Locked Reversal Study Engine & Data Pipeline Foundation):** Implemented on branch `antigravity/daytrade-001c1-reversal-engine` in dedicated package `tradex/research/daytrade_reversal/` and merged on `main` via PR #88 at commit `1b96751c0c62043bd3cd2af0b702c7757842eb7d`. Implements locked spec hash verification (`load_and_verify_spec`), XNYS regular session normalization (390 bars, early close exclusion), per-ticker-session quality audit (missing > 5%, duplicate > 1%, malformed), rolling 20-valid-prior-session threshold (`numpy.quantile(q=0.001, method="linear")`), point-in-time execution at open[t+1], 1m/2m/5m horizon outcome returns, execution friction (0/2/5 bps), matched baseline pool (arithmetic mean of qualifying non-events), canonical 5-minute forward window overlapping event classification, deterministic joint cluster bootstrap (2,000 resamples, seed 20260925), 5-step disposition precedence hierarchy, evaluation code freeze (`freeze.py`), dataset manifest contract with safety bounds (`dataset.py`), strict holdout protection guard (`study.py`), and CLI. Tested across 30 deterministic synthetic fixture scenarios with 0 real market-data provider calls; no development, validation, or holdout study executed; no real market data inspected; no tick-resolution work authorized; no production promotion authorized; `APPROVED_PRODUCTION_STRATEGIES == ()` preserved.
- **Slice DAYTRADE-001C2 (Bounded Real-Data Reversal Study Execution):** Executed on branch `antigravity/daytrade-001c2-real-study` using the exact approved frozen evaluator SHA `1b96751c0c62043bd3cd2af0b702c7757842eb7d` and locked spec SHA `0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620`. Acquired pre-holdout partition (warm-up, development, validation through 2025-09-30) from Alpaca SIP into private external dataset root (preholdout manifest SHA `80bd6b0e9b89e1b8cf578625c795aeec2730f3e9e31de0a01de8075e8f165884`; 300 requests, 394 pages, 0 retries). Evaluated development split once (`rejected`: mean net 1m return -5.45 bps, mean baseline uplift -1.50 bps, positive ticker breadth 6.67%). Evaluated validation split once (`inconclusive`: data quality exclusion rate 7.83% > 5.0% threshold, mean net 1m return -2.50 bps, replicate 202 empty baseline for TRV 09:33 non-computable CI, positive ticker breadth 26.67%). Because validation was not `supported`, holdout remained unread and was not acquired (`holdout_status = unread_not_acquired`, 0 provider calls for Q4 2025). Safe artifact bundle committed to `docs/research/artifacts/DAYTRADE-001C2-v1/` with verified checksums. Maximum evidence confidence capped at `limited_but_usable_evidence`. Zero production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()`.
- **Slice DAYTRADE-002A (Early-to-Late Intraday Momentum Specification & Preregistration):** Completed on branch `antigravity/daytrade-002a-intraday-momentum-spec` and merged to `main` via PR #90 at commit `74ee008f451d430ec3332587a39b0869534be8e4`. Machine-readable specification locked in `docs/research/specs/DAYTRADE-002A-v1.json` (SHA-256: `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`) and documented in `docs/research/DAYTRADE-002A.md`. Conceived as a distinct hypothesis after DAYTRADE-001 results were known; no 2025 observations count as confirmatory evidence. Tests 15 liquid sector/market ETFs across fresh 2026 data. DAYTRADE-002A makes zero provider calls, zero real-data queries, zero real-data inspection, zero backtest execution, and zero production changes. Verified by deterministic, credential-free unit tests in `tests/research/daytrade_002a/test_spec.py`.
- **Slice DAYTRADE-002B (Locked Early-to-Late Momentum Evaluator & Pipeline Foundation):** Implemented on branch `antigravity/daytrade-002b-momentum-engine` in dedicated package `tradex/research/daytrade_momentum/` and merged to `main` via PR #91 at commit `774b37efe883233d0c3f2a888e37aebf0851d347`. Implements locked spec hash verification (`verify_spec`), XNYS regular session normalization (390 bars, 09:30-15:59, early close exclusion), per-ticker-session quality audit (missing rate > 5.0%, duplicate rate > 1.0%, malformed row discard, missing session representation), split-level DQ gate (≤ 5.0% excluded sessions across 15 × expected sessions), first-half-hour return calculation (relative to usable 15:59 close from immediately preceding regular session, disentangled from threshold history), rolling 20-valid-prior-session threshold (`numpy.quantile(q=0.80, method="linear")`), LONG/SHORT event and non-event classification, 15:30 open to 15:59 close gross returns (direction-signed, with algebraic equivalence check), friction modeling (0/2/5 bps/side), direction-matched baseline pool indexing by `(ticker, split, direction)`, reference return, baseline uplift, non-computable handling (never substitute zero), deterministic session-date clustered bootstrap (2,000 resamples, seed 20260926, 95% percentile CI, simultaneous baseline recomputation, metric-specific non-computability for primary CI vs uplift CI), all 6 validation gates with exact 5-step disposition precedence hierarchy (`step_1_invalidity` -> `invalid`, `step_2_evidence_sufficiency` -> `inconclusive`, `step_3_directional_hypothesis_failure` -> `rejected`, `step_4_statistical_uncertainty` -> `inconclusive`, `step_5_support` -> `supported`), evaluation code freeze (`freeze.py`), dataset manifest contract with safety bounds (`dataset.py`, `--execute-provider` guard, dry-run mode, private external storage root enforcement), complete holdout security guard (`study.py`) enforcing all 23 explicit governance/integrity/provenance checks prior to any loader or provider invocation, deterministic safe artifact writer (`artifacts.py`, 14 standard artifacts), and CLI (`cli.py`, commands `verify-spec`, `freeze`, `evaluate`, `build-dataset`). Verified across 123 deterministic synthetic unit and e2e integration tests in `tests/research/daytrade_momentum/` with 0 real market-data provider calls; all 8 merge-blocking issues and 4 approved clarifications resolved; no development, validation, or holdout study executed; no real market data queried or inspected; no parameter or hypothesis changes; no production promotion authorized; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
- **Slice DAYTRADE-002C (Bounded Real Preholdout Acquisition & Momentum Study Execution):** Authorized and executed on dedicated branch `antigravity/daytrade-002c-real-study` using the exact approved frozen evaluator SHA `774b37efe883233d0c3f2a888e37aebf0851d347` (PR #91 merge commit) and locked spec SHA-256 `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`. Real preholdout acquisition completed successfully from Alpaca SIP into private external dataset root (preholdout manifest SHA-256: `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`; 105 provider calls, 149 pages, 149 attempts, 44 retries, 0 429s, 0 errors, 0 provider malformed timestamps; 15 source files in `bars/` matching manifest digests). Frozen evaluator execution attempted exactly once. Execution is **INVALID** due to a deterministic evaluator implementation defect: `quality.py:audit_ticker_session` looked only for `datetime`, `timestamp`, and `t` while `write_normalized_bars_csv` serialized the locked schema column `bar_start`, causing fail-closed exclusion of 100% of session bars. The raw evaluator mechanically returned `step_2_evidence_sufficiency` inconclusive because all observations were excluded; **no valid development or validation strategy-performance evidence was produced**. Pursuant to Section 15 (*Real-Data Integrity Rule After First Access*), no code modifications or reruns were performed after real-data access; zero evaluator code changes made. Holdout remained unread and unacquired (`holdout_status = unread_not_acquired`; 0 provider calls for July/August 2026). Safe artifact bundle committed to `docs/research/artifacts/DAYTRADE-002C-v1/` with verified checksums as audit evidence of the failed execution and merged into `main` via PR #94 at commit `70d41000bb8ce17e3fca2300ac3dc8e25df5f186`. A separately authorized correction task approved by Gary Yang is required before any corrected re-execution; zero production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()`.
- **Slice DAYTRADE-002C-CORR-001A (Timestamp-Schema Integration Fix & Corrected Re-execution Readiness):** PR #94 / DAYTRADE-002C was merged to `main` at commit `70d41000bb8ce17e3fca2300ac3dc8e25df5f186` as INVALID execution audit evidence due to the confirmed `bar_start` timestamp-schema integration defect in `quality.py:audit_ticker_session`. Implemented on branch `antigravity/daytrade-002c-corr-001a-timestamp-schema` to correct only the evaluator integration defect by implementing an explicit deterministic timestamp resolver adhering to locked candidate precedence (`dt_parsed` -> `bar_start` -> `datetime` -> `timestamp` -> `t`), fail-closed malformed timestamp checking, and rejection of unknown timestamp columns. Proven by end-to-end writer->reader->auditor regression and unit tests in `tests/research/daytrade_momentum/test_quality.py` (all 12 pass). Zero real-data access; zero provider calls; zero re-execution of development or validation; holdout remains strictly `unread_not_acquired`; merged to `main` via PR #96 at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`; production promotion remains false; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
- **Slice DAYTRADE-002C-CORR-001B (Corrected Preholdout Re-execution After Timestamp-Schema Fix):** Explicitly authorized by Gary on 2026-10-05 to execute the corrected DAYTRADE-002 preholdout development and validation re-execution against the frozen evaluator base `770a1a66382351dd63b9245c50bed0c1d92f3ca1` and locked spec SHA-256 `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`. Reused the exact existing preholdout dataset bytes (`~/.tradex/research/daytrade_002_v1/preholdout/`, manifest SHA-256 `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`; all 15 source files verified); zero dataset reacquisition; zero new provider calls. Evaluator frozen (`freeze.json`) at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1` with clean worktree. Development executed exactly once with disposition `rejected` (`step_3_directional_hypothesis_failure`, mean net return @ 2 bps $-0.95$ bps, breadth 53.33% < 60.0%, baseline uplift CI lower bound $-3.35$ bps $\le 0$). Continued to validation as preregistered. Validation executed exactly once with disposition `inconclusive` (`step_4_statistical_uncertainty`, primary net return 95% clustered CI $[-2.02\text{ bps}, +8.56\text{ bps}]$, lower bound $\le 0$; uplift 95% CI $[+0.44\text{ bps}, +12.14\text{ bps}]$; breadth 66.67% $\ge 60\%$). Because validation was not `supported`, holdout was strictly not accessed and remains unacquired (`holdout_status = unread_not_acquired`; 0 provider calls for July/August 2026). Validation bundle SHA-256 is `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`. Complete safe artifact bundles and results recorded in `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/` and `docs/research/DAYTRADE-002C-CORR-001B-RESULTS.md`. Emitted `metrics.provider_provenance_summary.status` contains a known non-calculation metadata defect (`synthetic_fixtures_only`) originating from frozen legacy evaluator code; authoritative Alpaca SIP provenance is verified via `manifest.lock.json` and `study.json.provenance` with zero calculation, dataset, or disposition impact. Zero production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()`.
- **Slice DAYTRADE-002C-CORR-002 (Provider-Provenance Summary Metadata Fix):** Implemented on branch `antigravity/daytrade-002c-corr-002-provenance-metadata` and merged to `main` via PR #99 at commit `bf8539f`. Corrected only the non-calculation evaluator provider-provenance summary metadata defect in `tradex/research/daytrade_momentum/study.py` for future executions; synthetic fixtures remain labeled `synthetic_fixtures_only`; manifest-backed evaluations derive provenance summary from verified manifest. Historical CORR-001B artifacts remain unchanged; zero empirical reruns; zero real-data access; zero provider calls; holdout strictly `unread_not_acquired`; DAYTRADE-002 validation remains INCONCLUSIVE; no production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
- **Slice DAYTRADE-003A (Re-anchor to Original Multi-Resolution Thesis):** Task `DAYTRADE-003A-ORIGINAL-THESIS-REANCHOR-001`. Gary Yang explicitly selected Path B to return TradeX DAYTRADE research to the original multi-resolution decision-support thesis (`DAILY` -> `133-tick` -> `1-minute` -> `50-tick` -> execution lifecycle) rather than continuing isolated 1-minute anomaly research as the primary roadmap. DAYTRADE-001 and DAYTRADE-002 preserved as component research; in-memory DAYTRADE-001A foundation inventoried and verified; comprehensive gap matrix committed in `docs/research/artifacts/DAYTRADE-003A/original_thesis_gap_matrix.json`; human-readable decision document committed in `docs/research/DAYTRADE-003A-ORIGINAL-THESIS-REANCHOR.md`; all 10 canonical governance/architecture questions answered; no strategy logic added; no empirical execution; no provider calls; no private data access; no holdout access; no production behavior changes; merged to `main` via PR #102 at base commit `b15015cb46adf5ceca707589455fc12fbca64c63`; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
- **Slice DAYTRADE-003B (Preregister Evidence-Backed Stocks-in-Play 5-Minute ORB Strategy):** Task `DAYTRADE-003B-ORB-PREREG-001`. Gary Yang explicitly approved pursuing the evidence-backed 5-minute Opening Range Breakout on Stocks in Play strategy candidate (based primarily on Zarattini, Barbon, Aziz 2024, Swiss Finance Institute Research Paper No. 24-98 / SSRN 4729284) rather than building generalized 50/133-tick infrastructure first. The previously proposed DAYTRADE-003B tick-provider feasibility study is SUPERSEDED and not authorized. Machine-readable specification locked in `docs/research/specs/DAYTRADE-003B-ORB-v1.json` (SHA-256: `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`) and human-readable contract documented in `docs/research/DAYTRADE-003B-ORB.md`. Locks source parameters without optimization: 5-minute opening range (09:30-09:35 ET), direction via OR close vs open (bullish long at OR_high, bearish short at OR_low, doji no order), opening price > $5, ADV14 >= 1M shares, ATR14 > $0.50, Relative Volume >= 1.0 vs 14-session baseline (session D excluded), Top 20 Stocks in Play with deterministic tie-break (RV desc, ticker asc), protective stop 0.10 * ATR14, EOD exit (no overnight hold, no profit target). Temporal partitions: Warmup Dec 2023, Development 2024 (sanity checks only; no tuning), Validation 2025, Untouched Holdout Jan-Sep 2026 (quarantined; accessible only if Validation == SUPPORTED). Disposition taxonomy prospectively includes PROMISING_NOT_CONFIRMED. Friction scenarios: Scenario A (source $0.0035/share), Scenario B (TradeX primary $0.0035/share + 2 bps/side), Scenario C (stress $0.0035/share + 5 bps/side). Execution model locks conservative gap-through, same-bar worst case, and immediate stop activation. Source audit table and 10 unresolved source ambiguities documented with resolution requirements. Verified by deterministic, credential-free unit tests in `tests/research/daytrade_003b/test_spec.py`. Zero tick infrastructure required; zero evaluator implementation; zero market data acquired; zero provider calls; zero private data access; zero empirical execution; zero holdout access; zero production changes; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
- **Sequencing:** DAYTRADE-001 remains closed as recorded research evidence with no promotion (reversal candidate development rejected, validation inconclusive, holdout unread/not acquired). DAYTRADE-002A specification/preregistration merged to `main` via PR #90. DAYTRADE-002B evaluator & pipeline foundation merged to `main` via PR #91. DAYTRADE-002C real preholdout acquisition succeeded but study execution was **INVALID** due to the evaluator timestamp-schema defect (raw evaluator step_2 inconclusive; zero valid strategy evidence produced; merged via PR #94 as invalid audit evidence). DAYTRADE-002C-CORR-001A corrected only the evaluator timestamp-schema integration defect (merged via PR #96 at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`). DAYTRADE-002C-CORR-001B executed corrected development (`rejected`) and validation (`inconclusive` due to primary CI crossing zero); holdout strictly unread and unacquired (`unread_not_acquired`); non-calculation metadata defect in `metrics.json` disclosed with zero calculation impact. DAYTRADE-002C-CORR-002 corrected evaluator provider-provenance summary metadata in `study.py` (merged via PR #99). DAYTRADE-003A re-anchored roadmap to original multi-resolution thesis (merged via PR #102). DAYTRADE-003B preregistered evidence-backed Stocks-in-Play 5-minute ORB strategy (spec SHA-256 `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`). Strategy registry remains strictly empty (`APPROVED_PRODUCTION_STRATEGIES == ()`); zero production promotion.
- **Affects trading behavior:** No

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
- **Recommended action:** The v2 ingestion remediation and rerun are complete. The data-quality issue was resolved by dropping 23 malformed rows and producing deterministic audit evidence. The unchanged candidate-selection gate produced no qualifying policy, so SHORT-001 is closed as Completed — Not supported and no production integration is warranted. `LONG-002A`, `LONG-002B`, and `LONG-002B-AMEND-002` are completed; `LONG-002C` design is authorized by PR #52 but paused by Gary while `MVP-ARCH-001` is completed; the `INTRA-001B` through `INTRA-001D` work is complete and inconclusive.
- **Next recommended PR:** `devin/mvp-arch-001-consolidation-decision` — `INTRA-001B` through `INTRA-001D` are complete and inconclusive; `LONG-002A`, `LONG-002B`, and `LONG-002B-AMEND-002` are completed; `LONG-002C` design is authorized by PR #52 but paused by Gary while `MVP-ARCH-001` is completed.
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

### DOC-003: Transition TradeX implementation-agent governance from Devin to Antigravity

- **ID:** DOC-003
- **Title:** Transition TradeX implementation-agent governance from Devin to Antigravity
- **Category:** Documentation
- **Priority:** Low
- **Status:** Completed
- **Resolved by:** `antigravity/doc-003-agent-governance-transition`
- **Problem statement:** TradeX transitioned from Devin to Antigravity for repository-level implementation work, but canonical development governance still described Devin as the primary builder and framed workflows and assignments in Devin-specific terms.
- **Recommended action:** Update canonical AI development workflow documentation, CLAUDE.md, and project tracker so Antigravity is the default prospective builder under the ChatGPT–Antigravity–Codex workflow; document Antigravity workspace and `antigravity/` branch conventions without hardcoding Gemini model versions; preserve Gary, ChatGPT, and Codex roles; preserve all research safeguards and production-trading boundaries; preserve historical Devin records; explicitly affirm that no product/research implementation is authorized.
- **Reason:** Aligns canonical repository governance with the active operating model while preserving historical integrity and product boundaries.
- **Dependencies:** DOC-002
- **Files likely affected:** `docs/AI-DEVELOPMENT-WORKFLOW.md`, `CLAUDE.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** `git diff --check`; `uv run ruff check tests scripts`; `uv run pytest tests/product/test_mvp_arch_001.py`; audit of remaining Devin references.
- **Acceptance criteria:** Canonical prospective workflow identifies Antigravity as default builder; ChatGPT/Gary/Codex roles preserved; workspace and branch conventions documented; no Gemini version hardcoding; historical Devin references preserved; no production or research code changes; no MVP-ARCH-001 or LONG-002C authorization change; tracker summary tables match entries.
- **Intended pull request:** `antigravity/doc-003-agent-governance-transition`
- **Affects trading behavior:** No — documentation and governance transition only; does not authorize product implementation.

---

##### MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001: R7 PIT Live Provider Compatibility Study

- **ID:** MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001
- **Title:** R7 PIT Live Provider Compatibility Study
- **Category:** Infrastructure / Architecture
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-arch-001-r7-pit-provider-study-001`
- **Problem statement:** TradeX needed to empirically measure how the current production provider adapters behave on the frozen Candidate B / Candidate C symbol set after HARDEN-001.
- **Recommended action:** Execute a single, bounded live-provider compatibility study on the 45-symbol Candidate C.
- **Reason:** To provide real-world evidence for the Gary-approved Option 2 + 3 status semantics and universe selection.
- **Dependencies:** MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001
- **Files likely affected:** `scripts/research/r7_pit_provider_study.py`, `tests/research/test_r7_pit_provider_study.py`, `docs/product/R7-PIT-PROVIDER-STUDY-001.md`, `docs/product/artifacts/r7-pit-provider-study-001/study_spec.json`, `docs/product/artifacts/r7-pit-provider-study-001/results.json`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Offline mocked tests that prove no live calls happen without explicit arguments, classification logic is deterministic, massive auth/entitlement errors block execution.
- **Acceptance criteria:** Protocol committed before execution; strict one-pass constraint; no production code changes; no database changes; no automatic universe recommendation; disposition adheres to preregistered rules.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-provider-study-001`
- **Affects trading behavior:** No

##### MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001: R7 PIT Status & Applicability Implementation Readiness

- **ID:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001
- **Title:** R7 PIT Status & Applicability Implementation Readiness
- **Category:** Architecture / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-arch-001-r7-pit-status-impl-readiness-001`
- **Problem statement:** Following the empirical Yahoo/Massive provider study (`MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001`), TradeX needed an exact, implementation-ready normative specification and machine-readable contract for Option 2 + 3 status semantics before implementing Schema v8 or C2 universe selection.
- **Recommended action:** Produce normative readiness specification `docs/product/R7-PIT-STATUS-IMPL-READINESS-001.md`, machine-readable contract `docs/product/artifacts/r7-pit-status-impl-readiness-001/decision.json`, and product contract tests locking manifest v2, Schema v8 constraints, version-aware nullable manifest_hash (NULL for v1 rows, NOT NULL for v2 rows), truthful provenance without fictitious provider names or zero-duration timestamps, count-based completeness without arbitrary thresholds, deterministic operational health, and bounded PR A/B/C decomposition.
- **Reason:** To prevent ambiguous requirements or unprincipled schema evolution, lock exact mathematical contracts, protect historical Schema v7 evidence, and enable bounded implementation PRs.
- **Dependencies:** MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001
- **Files likely affected:** `docs/product/R7-PIT-STATUS-IMPL-READINESS-001.md`, `docs/product/artifacts/r7-pit-status-impl-readiness-001/decision.json`, `tests/product/test_r7_pit_status_impl_readiness_001.py`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Offline product contract tests verifying governance invariants, manifest v2 specs, versioned hashing, Schema v8 table constraints, truthful provenance, count-based completeness, operational health truth table, and PR decomposition.
- **Acceptance criteria:** Implementation-ready contract with zero material TBDs; no hard-coded ticker lists; historical v7 evidence protected with zero reinterpretation; manifest_hash NULL for v1 rows; reference kept universally required; count-based completeness without arbitrary percentage thresholds; zero `tradex/` changes; all tests pass; PR remains Draft and unmerged.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-status-impl-readiness-001`
- **Affects trading behavior:** No

##### MVP-ARCH-001-R7-PIT-STATUS-IMPL-A: Versioned Applicability & Persistence Primitives

- **ID:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-A
- **Title:** Implementation PR A — Versioned Applicability & Persistence Primitives
- **Category:** Architecture / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-arch-001-r7-pit-status-impl-a`
- **Problem statement:** TradeX required foundational primitives for Manifest Contract v2, domain models supporting v1 & v2, Schema v8 atomic 14-step rebuild, v2 request fingerprinting, truthful manifest-origin `NOT_APPLICABLE` persistence, and defensive backward compatibility with Schema v7 while pinning runtime capture execution to v1.
- **Recommended action:** Implement Manifest Contract v2 schema validation and versioned hashing; add `ObservationStatus.NOT_APPLICABLE` and fact payload builder; compute request fingerprints using `contract_version` and `manifest_hash`; execute atomic 14-step rebuild for Schema v8 with `PRAGMA foreign_keys = OFF` before `BEGIN TRANSACTION`; add defensive row mappers and store functions supporting `not_applicable_n` and v2 columns; pin write execution to `PIT_CAPTURE_WRITE_CONTRACT_VERSION = 1`; block premature v2 runtime capture until PR B.
- **Reason:** To establish the production-capable persistence and domain foundation for versioned manifest applicability and truthful persistence before wiring runtime capture execution in PR B.
- **Dependencies:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001
- **Files likely affected:** `tradex/pit/models.py`, `tradex/pit/ops.py`, `tradex/pit/store.py`, `tradex/tracker/store.py`, `tradex/pit/earnings.py`, `tradex/pit/reference.py`, `tests/pit/`, `tests/tracker/`, `docs/PROJECT-TRACKER.md`, `docs/product/R7-PIT-OPERATIONS.md`
- **Testing requirements:** Unit tests for v1 and v2 models, fingerprint hashing, manifest validation, 14-step rebuild, foreign key ordering and checks, atomic rollback on count mismatch or failure, idempotency, check constraints, and 100% pass across pit and tracker suites.
- **Acceptance criteria:** Manifest Contract v2 primitives complete; Schema v8 rebuild works atomically; prior v7 data preserved with exact counts; truthful provenance enforced; runtime capture pinned to v1; premature v2 runtime blocked; PR remains Draft and unmerged.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-status-impl-a`
- **Affects trading behavior:** No

##### MVP-ARCH-001-R7-PIT-STATUS-IMPL-B: Runtime Capture & Health Execution

- **ID:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-B
- **Title:** Implementation PR B — Runtime Capture & Health Execution
- **Category:** Architecture / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-arch-001-r7-pit-status-impl-b` (merged in PR #80 at commit `618f91bfe2e9dc75b5d911f837b37cda5f38ff2f`)
- **Problem statement:** Following completion of PR A's persistence and domain primitives, TradeX required wiring runtime capture and health execution for Contract v2 manifests with two-dimensional status semantics (operational health vs. independent evidence completeness), multi-attempt reconciliation, manifest-only earnings applicability with provider call skipping, per-symbol reference exception sanitization, and deterministic CLI exit codes (0/2/1).
- **Recommended action:** Extend `run_pit_slot` to dispatch contract v2 executions when a v2 manifest is supplied; enforce manifest-only provider call skipping for `not_applicable` earnings; execute reference lookups universally with per-symbol exception handling and truthful observation persistence; compute discrete evidence completeness tiers (`complete`, `partial`, `sparse`) preserving integer arithmetic and the invariant that pooled ratio never masks a sparse family; reconcile multi-attempt slot history; bifurcate CLI JSON serialization preserving exact v1 shapes for v1 manifests; maintain Schema v8 constraints and 100% backward compatibility for contract v1.
- **Reason:** To operationalize the Gary-approved Option 2 + Option 3 point-in-time architecture with clean separation between operational infrastructure health and empirical market data completeness before operational universe selection in PR C.
- **Dependencies:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-A
- **Files likely affected:** `tradex/pit/models.py`, `tradex/pit/earnings.py`, `tradex/pit/reference.py`, `tradex/pit/ops.py`, `tests/pit/`, `docs/PROJECT-TRACKER.md`, `docs/product/R7-PIT-OPERATIONS.md`
- **Testing requirements:** Offline, credential-free unit and CLI tests verifying preflight guards, manifest-only skipping, lifecycle statuses, independent evidence completeness math/tiers, multi-attempt reconciliation, drift fail-closed behavior, reference exception handling, fatal SQLite write handling, and CLI exit codes (0/2/1) across v1 and v2.
- **Acceptance criteria:** Contract v2 runtime capture and health execution complete; two-dimensional semantics operational; exact v1 compatibility preserved; all new and existing tests pass; PR #80 merged at commit `618f91bfe2e9dc75b5d911f837b37cda5f38ff2f`.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-status-impl-b`
- **Affects trading behavior:** No

##### MVP-ARCH-001-R7-PIT-STATUS-IMPL-C: Operational Universe Selection & Verification

- **ID:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-C
- **Title:** Implementation PR C — Operational Universe Selection & Verification
- **Category:** Architecture / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-arch-001-r7-pit-status-impl-c` (merged in PR #81 at commit `e2f1e37a27e751fc9116c2893e226c83af025cb0`)
- **Problem statement:** Following completion and merge of PR B (`MVP-ARCH-001-R7-PIT-STATUS-IMPL-B`, PR #80), TradeX required establishing the Gary-approved canonical operational Manifest Contract v2 package, deterministic scheduler management assets, and operations documentation.
- **Gary Authorization:** Gary Yang explicitly approved Candidate C (`candidate-dow30-sector-etfs`) on 2026-09-18 as TradeX's initial operational PIT universe. Candidate B (`candidate-dow30`) is recorded as `not_selected`.
- **Recommended action:** Materialize the canonical operational manifest `docs/product/manifests/pit-universe-2026-09-21-v1.json` with contract_version 2, effective_from 2026-09-21, 45 symbols (30 equities earnings required, 15 ETFs earnings not_applicable, 45 reference required); verify exact hashes; implement bounded PowerShell scheduler management script `scripts/manage_pit_scheduler.ps1` with Validate/Status/Install/Remove actions; fail closed on non-Eastern timezone; document operational and health inspection procedures in `docs/product/R7-PIT-OPERATIONS.md`; maintain Schema v8 and empty strategy registry.
- **Reason:** Formalizes the Gary-approved Candidate C operational universe and establishes deterministic, auditable Windows scheduler management assets for future activation.
- **Dependencies:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-B
- **Files likely affected:** `docs/product/manifests/pit-universe-2026-09-21-v1.json`, `docs/product/artifacts/r7-pit-status-impl-c/decision.json`, `docs/product/R7-PIT-STATUS-IMPL-C.md`, `scripts/manage_pit_scheduler.ps1`, `docs/product/R7-PIT-OPERATIONS.md`, `tests/product/test_r7_pit_status_impl_c.py`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Offline tests verifying manifest loading, exact symbol counts, exact universe hash (`83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29`), computed manifest hash (`4eee8a5da39c74db499b6f644f6891d61f6a30b0f98d95b53445b12929c9dedb`), applicability breakdown (30 corporate equities required, 15 ETFs not_applicable, 45 reference required), decision artifact alignment, non-mutating PowerShell scheduler validation, and `APPROVED_PRODUCTION_STRATEGIES == ()`.
- **Acceptance criteria:** Canonical manifest loads as Contract v2; exact Candidate C universe hash matches; decision artifact recorded; PowerShell scheduler management asset created with non-mutating Validate path; Schema remains v8; PR #81 merged at commit `e2f1e37a27e751fc9116c2893e226c83af025cb0`.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-status-impl-c`
- **Affects trading behavior:** No — operational data-capture configuration only; no trading strategies, scores, weights, thresholds, rankings, or eligibility changed.

##### MVP-ARCH-001-R7-PIT-ACTIVATE-001: Candidate C PIT Scheduler Operational Activation

- **ID:** MVP-ARCH-001-R7-PIT-ACTIVATE-001
- **Title:** Candidate C PIT Scheduler Operational Activation
- **Category:** Architecture / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Activation disposition:** ACTIVATED_WITH_LOGON_REQUIREMENT
- **Activated on:** 2026-09-19
- **Resolved by:** Operational activation on canonical checkout `C:\Users\Gary\Projects\TradeX` on `main` at commit `e2f1e37a27e751fc9116c2893e226c83af025cb0`; governance closeout recorded by `antigravity/mvp-arch-001-r7-pit-activate-001-closeout`
- **Problem statement:** Following completion and merge of PR C (`MVP-ARCH-001-R7-PIT-STATUS-IMPL-C`, PR #81), TradeX required explicit operational activation of the Candidate C PIT scheduler on Windows Task Scheduler to initiate scheduled point-in-time data captures starting on trading day 2026-09-21.
- **Operational State & Boundaries:** Gary Yang executed `manage_pit_scheduler.ps1 -Action Install` on 2026-09-19 from canonical checkout `C:\Users\Gary\Projects\TradeX`. Both `TradeX PIT Morning` (09:00 ET) and `TradeX PIT Evening` (20:30 ET) are installed and enabled under Task Scheduler path `\TradeX\`, targeting canonical checkout `C:\Users\Gary\Projects\TradeX` and persistent DB `C:\Users\Gary\.tradex\signals.db`. Task principal is `UserId = Gary`, `LogonType = Interactive`, `RunLevel = Limited`. Operational consequence: task can run while workstation is locked, but cannot run while Gary is signed out (`can_run_while_signed_out = false`); machine must be awake (`machine_must_be_awake = true`). `StartWhenAvailable = false` ensures missed captures intentionally do not run late. Zero manual PIT executions were performed during activation (`manual_PIT_execution_performed = false`); zero provider calls were made during activation (`provider_calls_during_activation = false`); no repository files were modified during activation; scheduler was not manually altered outside `manage_pit_scheduler.ps1`. First naturally scheduled capture remains pending (first due 2026-09-21 morning slot). Production strategy registry remains strictly empty (`APPROVED_PRODUCTION_STRATEGIES == ()`).
- **Dependencies:** MVP-ARCH-001-R7-PIT-STATUS-IMPL-C
- **Files likely affected:** `docs/product/artifacts/r7-pit-activate-001/activation.json`, `docs/product/R7-PIT-ACTIVATE-001.md`, `docs/product/R7-PIT-OPERATIONS.md`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Machine-readable artifact `docs/product/artifacts/r7-pit-activate-001/activation.json` validation via `python -m json.tool`; governance consistency via `tests/product/test_mvp_arch_001.py`; git diff check.
- **Acceptance criteria:** Candidate C scheduler installed and enabled in Windows Task Scheduler; machine-readable activation artifact committed and valid; human-readable activation document recorded; operations doc updated with current activation state; project tracker updated; zero production code or strategy changes; first scheduled captures remain pending.
- **Intended pull request:** `antigravity/mvp-arch-001-r7-pit-activate-001-closeout`
- **Affects trading behavior:** No — operational data-capture activation only; does not alter signals, scores, weights, thresholds, rankings, or eligibility; no strategy promoted.

##### MVP-UX-DESKTOP-001: Windows Desktop Start and Stop Launchers

- **ID:** MVP-UX-DESKTOP-001
- **Title:** Windows Desktop Start and Stop Launchers
- **Category:** User interface / Infrastructure
- **Priority:** High
- **Status:** Completed
- **Resolved by:** `antigravity/mvp-ux-desktop-001-windows-launchers`
- **Problem statement:** TradeX was launchable via `launchers\windows\TradeX.bat`, but required manual shortcut creation, lacked a supported one-click Stop action, did not track runtime PID metadata, and naively assumed any process listening on port 8501 was TradeX.
- **Recommended action:** Implement defense-in-depth process identity verification anchored to canonical `tradex\ui\dashboard.py`; persist runtime PID metadata in `%USERPROFILE%\.tradex\dashboard.pid`; implement `TradeX-Stop.ps1` and `TradeX-Stop.bat` to cleanly terminate the TradeX process tree without terminating unrelated applications on port 8501; implement automated shortcut installer `install_desktop_shortcuts.ps1`; extend `make_icon.py` with cross-platform font discovery and generate red stop-themed icon assets (`TradeX-Stop.ico` and `tradex_stop_icon.png`); add targeted tests.
- **Reason:** Provides a reliable, professional Windows desktop Start/Stop experience for Gary while guaranteeing that unrelated applications on port 8501 are never terminated or conflated with TradeX.
- **Dependencies:** None
- **Files affected:** `launchers/make_icon.py`, `launchers/windows/TradeX.ps1`, `launchers/windows/TradeX-Stop.ps1`, `launchers/windows/TradeX-Stop.bat`, `launchers/windows/install_desktop_shortcuts.ps1`, `launchers/README.md`, `SETUP.md`, `tests/launchers/test_windows_launchers.py`, `docs/PROJECT-TRACKER.md`
- **Testing requirements:** Offline, credential-free unit tests verifying icon assets, batch/PowerShell syntax, CRLF line endings, shortcut installer properties, and process identity safety invariants.
- **Acceptance criteria:** Start and Stop desktop shortcuts installed; defense-in-depth process verification prevents touching unrelated processes; port release confirmed; runtime PID tracked; targeted tests pass; documentation updated.
- **Intended pull request:** `antigravity/mvp-ux-desktop-001-windows-launchers`
- **Affects trading behavior:** No — operational desktop tooling only; no trading strategies, scores, weights, thresholds, rankings, or eligibility changed.

---

## Summary by priority

| Priority | Count | Representative first item |
|---|---|---|
| High | 27 | LONG-002: Rapid-upside long opportunity research program |
| Medium | 12 | SHORT-001: Add market regime and relative strength to short-term scorer |
| Low | 6 | DOC-001: Close LONG-001 and restore documentation and tracker consistency |

## Summary by status

| Status | Count |
|---|---|
| Completed | 44 |
| Deferred | 1 |
| Proposed | 0 |
| In progress | 0 |
| Blocked | 0 |

The original engineering-foundation and UI-refactor backlog is substantially complete. `SHORT-001` is closed as Completed - Not supported. `INTRA-001B` through `INTRA-001D` are complete and `INTRA-001` returned `inconclusive` without parsing the holdout; no further work on the `INTRA-001` hypothesis is authorized without a new Gary-approved plan. `LONG-002A` and `LONG-002B` are completed. `LONG-002B-AMEND-002` is completed and merged through PR #52. `LONG-002C-DESIGN-001` was merged in PR #84 at commit `61d392c1ca7222f15954cb684d54d6fcc39b4181`. Gary Yang explicitly authorized `LONG-002C-EXEC-001` execution and historical development dataset construction on 2026-09-21. `LONG-002C-EXEC-001` empirical execution was completed and approved on 2026-09-27 as valid development evidence on official run `2026-09-27-161243` (code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`) and merged into main via PR #85 at base commit `17a59e942c17c52ceaaabc0e7ed5ec430492dc95`; preregistered PRIMARY endpoint retained (clean +10% / 10 sessions, `primary_retained`; fallback not invoked); `volatility_aware_momentum_5` frozen as strongest development baseline comparator; `LONG-002D1` (Core Technical and Market-Context KPI Census) was preregistered at commit `c36ec7f818b2c45ceb084964177db5984269d71c` (spec SHA-256 `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381`); initial run `2026-09-27-223646` was superseded under `LONG-002D1-CORR-001` due to non-study candidate loading and unmatched provenance; official corrected run `2026-09-28-003539` was successfully executed on branch `antigravity/long-002d1-core-kpi-census` with 100% empirical equivalence, 0 cache misses, 0 live network attempts, 0 outbound HTTP calls, and 100% (2,797/2,797) Stage C provenance match; all 15 features evaluated on N=758,731 20:30 development observations across 1,271 study securities; `atr_pct_14` demonstrated strongest univariate lift (2.2816x, 5/5 years stable); `proximity_high20` showed an inverse proximity-to-high / pullback association (Decile 1 pullbacks have 1.6448x lift vs Decile 10 near highs 0.7307x; post-hoc exploratory dip evidence requiring separate preregistration); moving average features showed 1.20x-1.22x lift across 4-5 years; volume features showed 1.13x lift for relative volume; 0 pairs exceeded the mechanical |rho| >= 0.95 redundancy threshold, though return_20 <-> sma20_slope_5 reached rho = +0.9190 reflecting substantial shared information; frozen VAM5 baseline preserved (1.7320x lift); candidate features initialized to `review_pending` pending Gary/ChatGPT post-run carry-forward review; `LONG-002D2` (Incremental Ranking Value of Relative Volume Beyond Frozen VAM5, task `LONG-002D2-INCREMENTAL-RERANK-001`) was authorized by Gary Yang on 2026-09-28; dedicated preregistration commit `494caa8df3e60bae15e5015ad98a42a13eb109f3` (spec SHA-256 `db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8`); initial run `2026-09-28-143047` was superseded under `LONG-002D2-CORR-001` due to unrecorded execution code provenance; official corrected run `2026-10-04-002604` (committed execution code SHA `e494f12dfa526a62e5014572d335510099a3a024`) was successfully executed on branch `antigravity/long-002d2-incremental-rerank` with 100% empirical equivalence across 982 development dates (758,731 observations) and 100% daily coverage matching; primary candidate `relative_volume_20` disposition: `NOT_SUPPORTED` (candidate precision 12.4321% vs matched VAM5 15.3533%, absolute delta -2.9212 pp, 21-session block bootstrap 95% CI [-0.0352, -0.0235], annual stability 0/5 years positive); secondary challenger `sma20_slope_5` underperformed with 11.9950% precision, delta -3.3583 pp, 21-session 95% CI [-0.0415, -0.0258]; descriptive SPY return regimes confirmed uniform negative delta across lower, middle, and upper market environments; validation, holdout, and shadow remain strictly quarantined; production promotion unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()`. `MVP-ARCH-001` is completed and Gary-approved as the design-only product-architecture direction; R1, R2, and R3 are completed and merged; R4 was separately Gary-approved and implemented by PR #60; R5A was separately Gary-approved on 2026-08-23 for candidate snapshot domain contract and schema v4 persistence primitives only and implemented by PR #61; R5B was separately Gary-approved on 2026-08-23 and implemented by PR #62 for prospective scorable-observation aggregation and CandidateDossier persistence; R5C is separately Gary-approved on 2026-08-23 and implemented by PR #63 for truthful read-only Today and Candidate Detail workflow; R6-READINESS-A is merged via PR #64; R6-READINESS-B is merged via PR #65; R6-IMPL-0 is merged via PR #66 (merge commit `4d06920244755445b4ceb445f65907df0d61a3dc`); R6-IMPL-A was merged via PR #67 commit `b8c80941c41545ef72830a53de2f087107564c7b` (Schema v5 migration, persistence primitives, lifecycle service, outcome calculations); R6-IMPL-B was merged via PR #68 commit `2605645aaba77a80ff9907d434d851ee8e6d1564` (executable Journal read-only UI projection, domain read models, top-level Tab 5 Journal integration, and legacy telemetry relocation); R7-PIT-001A was merged via commit `f37f42169edf09c959d95fc73375f975c3216351` (prospective earnings PIT capture foundation, schema v6); R7-PIT-001B was merged via PR #70 commit `6047691549315936d679c845abb61fd727a241fa` (prospective security/reference point-in-time capture, schema v7); R7-PIT-001C1 was merged via PR #71 commit `e111c04107b929b0b2ae8896755d57ec9b114f95` (deterministic PIT operations runner, versioned universe manifest, capture health, and capacity estimation); R7-PIT-001C2-READINESS-A was merged via PR #73 commit `93d2174fed72f325e4ea87199c2aac9045998cbb` (candidate universe capacity analysis complete; operational activation blocked pending status semantics decision); R7-PIT-STATUS-DEC-001 architecture direction (Option 2 + Option 3) is Gary-approved (`gary_approved`, `selected_status_policy = "option_2_plus_3"`); MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001 is completed on branch `antigravity/mvp-arch-001-r7-pit-status-harden-001` (earnings provider failure/provenance hardening, typed single-inheritance exceptions, deterministic precedence, sanitized payloads, Schema v7 and contract v1 preserved, strict all-known C1 ops health preserved); MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001 is Completed on branch `antigravity/mvp-arch-001-r7-pit-provider-study-001` with study disposition `completed_evidence_sufficient_for_next_decision`; MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001 is Completed on branch `antigravity/mvp-arch-001-r7-pit-status-impl-readiness-001` (normative readiness specification locked in `docs/product/R7-PIT-STATUS-IMPL-READINESS-001.md` and machine-readable contract `docs/product/artifacts/r7-pit-status-impl-readiness-001/decision.json`); MVP-ARCH-001-R7-PIT-STATUS-IMPL-A is Completed and merged in PR #79 (Manifest Contract v2 primitives, domain models, Schema v8 atomic 14-step rebuild, v2 request fingerprinting, truthful NOT_APPLICABLE persistence, runtime capture pinned to v1); MVP-ARCH-001-R7-PIT-STATUS-IMPL-B is Completed and merged in PR #80 at commit `618f91bfe2e9dc75b5d911f837b37cda5f38ff2f` (Manifest Contract v2 runtime capture and health execution, two-dimensional status semantics with discrete evidence completeness read models, multi-attempt reconciliation, manifest-only provider call skipping for NOT_APPLICABLE earnings, reference universal lookup with per-symbol exception sanitization, Schema-v8 fatal DB failure limitation surfacing, and 0/2/1 CLI exit codes); Candidate C (`candidate-dow30-sector-etfs`) was selected by Gary on 2026-09-18 as TradeX's initial operational PIT universe; Candidate B (`candidate-dow30`) is not selected; MVP-ARCH-001-R7-PIT-STATUS-IMPL-C is Completed and merged in PR #81 at commit `e2f1e37a27e751fc9116c2893e226c83af025cb0`; Candidate C PIT scheduler was operationally activated on 2026-09-19 under `MVP-ARCH-001-R7-PIT-ACTIVATE-001` with disposition `ACTIVATED_WITH_LOGON_REQUIREMENT` (morning 09:00 ET and evening 20:30 ET jobs installed and enabled in Task Scheduler path `\TradeX\`, Interactive logon, machine must be awake, no manual capture executed during activation, first scheduled capture due 2026-09-21 and remains pending); MVP-UX-DESKTOP-001 is Completed on branch `antigravity/mvp-ux-desktop-001-windows-launchers` (Windows Desktop Start and Stop launchers, automated shortcut installer, defense-in-depth process identity verification, PID tracking, and red stop-themed icon assets); Schema remains v8; `APPROVED_PRODUCTION_STRATEGIES == ()`; no production strategy was promoted; validation/holdout access unauthorized; R8 remains unauthorized; DAYTRADE-001 remains deferred (DAYTRADE-001A completed, DAYTRADE-001B specification locked, DAYTRADE-001C1 merged via PR #88, DAYTRADE-001C2 real study completed with validation `inconclusive` and holdout `unread_not_acquired`; no production promotion is authorized; `APPROVED_PRODUCTION_STRATEGIES == ()` preserved); DAYTRADE-002A specification is locked and merged via PR #90 (`docs/research/specs/DAYTRADE-002A-v1.json`, SHA-256 `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`); DAYTRADE-002B locked evaluator and data pipeline foundation is merged to `main` via PR #91 at commit `774b37efe883233d0c3f2a888e37aebf0851d347`; DAYTRADE-002C bounded real preholdout acquisition succeeded from Alpaca SIP into private root (manifest SHA-256 `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`, 105 provider calls, 149 pages, 44 retries, 0 429s, 0 errors, 0 provider malformed timestamps), but study execution was **INVALID** due to a deterministic evaluator timestamp-schema defect in `quality.py:audit_ticker_session` (omitted `bar_start`, causing 100% session row exclusion; raw evaluator mechanically emitted step_2 inconclusive; no valid development or validation strategy-performance evidence produced; zero evaluator code changes after real-data access; holdout strictly `unread_not_acquired`; safe artifact bundle committed to `docs/research/artifacts/DAYTRADE-002C-v1/` as audit evidence of failed execution; PR #94 merged to `main` at commit `70d41000bb8ce17e3fca2300ac3dc8e25df5f186` as INVALID execution audit evidence; task `DAYTRADE-002C-CORR-001A` corrected only the evaluator timestamp-schema integration defect via deterministic resolver obeying candidate precedence `dt_parsed` -> `bar_start` -> `datetime` -> `timestamp` -> `t`; merged to `main` via PR #96 at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`); task `DAYTRADE-002C-CORR-001B` explicitly authorized by Gary on 2026-10-05 and executed corrected preholdout study reusing existing dataset bytes; zero reacquisition; zero provider calls; development executed once (`rejected`: `step_3_directional_hypothesis_failure`); validation executed once (`inconclusive`: `step_4_statistical_uncertainty`, primary net return 95% CI lower $\le 0$ at $-2.02$ bps); validation bundle SHA-256 `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`; non-calculation metadata defect in `metrics.json` documented with zero calculation/disposition impact; holdout strictly `unread_not_acquired`; production promotion unauthorized; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved; task `DAYTRADE-002C-CORR-002` corrected only the non-calculation evaluator provider-provenance summary metadata defect in `study.py` for future executions; synthetic injected fixtures remain labeled `synthetic_fixtures_only`; manifest-backed evaluations derive provenance summary from verified manifest; historical CORR-001B artifacts remain unchanged; zero empirical reruns; zero real-data access; zero provider calls; holdout strictly `unread_not_acquired`; DAYTRADE-002 validation remains INCONCLUSIVE; no production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved; task `TEST-004` corrected the stale LONG-002D3B historical DAYTRADE-isolation test in `tests/research/test_long_002d3b_contract.py:test_45_no_daytrade_files_changed` to evaluate the immutable PR #97 commit range (`770a1a6...c8fcef5`) rather than HEAD, preventing false CI failures on future unrelated DAYTRADE work; historical PR #97 scope remains verified; no research logic changed; no empirical results changed; no production behavior changed; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved). The prior LONG-002 research program (A through E2) has concluded and is preserved as completed background research; the active implementation roadmap is LONG-MVP-001 (strategy contract) -> LONG-MVP-002 (implementation end-to-end, completed on branch `antigravity/long-mvp-002-strategy-impl`).

**Remaining non-completed items:**
1. **LONG-MVP-002 review/merge** — Review and merge PR 2 (`antigravity/long-mvp-002-strategy-impl`), implementing Production-Target Long Opportunity Strategy v1 End-to-End (`tradex/data/fetcher.py`, `tradex/signals/indicators.py`, `tradex/signals/long_term.py`, `tradex/signals/weights.py`, `tradex/screener/engine.py`, `tradex/tracker/watcher.py`, `tradex/tracker/confluence.py`, UI, and tests; requires explicit Gary Yang approval before merge).
2. **MVP-ARCH-001-R7-PIT-ACTIVATE-001-VERIFY** — First Scheduled Candidate C PIT Capture Verification (Future operational verification after the 2026-09-21 morning and evening slots; first capture has not yet been observed; no implementation changes in TradeX).
3. **DAYTRADE-001** — Future real-time day-trading decision-support program (`DAYTRADE-001A` research foundation completed; `DAYTRADE-001B` research specification locked; `DAYTRADE-001C1` merged via PR #88; `DAYTRADE-001C2` real study completed with validation `inconclusive` and holdout `unread_not_acquired`; production promotion unauthorized).
4. **DAYTRADE-002** — Early-to-late intraday ETF momentum research program (`DAYTRADE-002A` specification locked; `DAYTRADE-002B` evaluator merged via PR #91; PR #94 / `DAYTRADE-002C` merged at commit `70d41000bb8ce17e3fca2300ac3dc8e25df5f186` as INVALID execution audit evidence; `DAYTRADE-002C-CORR-001A` timestamp-schema fix merged via PR #96 at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`; `DAYTRADE-002C-CORR-001B` corrected preholdout study executed reusing existing dataset bytes; zero reacquisition; zero provider calls; development executed once (`rejected`); validation executed once (`inconclusive` due to primary net return 95% CI crossing zero); validation bundle SHA-256 `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`; non-calculation metadata defect in `metrics.json` documented with zero calculation impact; holdout strictly `unread_not_acquired`; task `DAYTRADE-002C-CORR-002` corrected only the non-calculation evaluator provider-provenance summary metadata defect in `study.py` for future executions; synthetic injected fixtures remain labeled `synthetic_fixtures_only`; manifest-backed evaluations derive provenance summary from verified manifest; historical CORR-001B artifacts remain unchanged; zero empirical reruns; zero real-data access; zero provider calls; holdout strictly `unread_not_acquired`; DAYTRADE-002 validation remains INCONCLUSIVE; no production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved).
5. **DAYTRADE-003** — DAYTRADE-003A (roadmap re-anchor) is completed and merged (PR #102). Earlier proposed DAYTRADE-003B tick-provider feasibility study is SUPERSEDED and not authorized. Gary explicitly selected the evidence-backed Stocks-in-Play 5-minute ORB strategy (Zarattini, Barbon, Aziz 2024 [SSRN 4729284]). PR #104 / `DAYTRADE-003B` preregistration is merged to `main` at commit `61639a49c50da9fe626754bbc0980070dbaf8a3c` (locked spec SHA-256 `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` remains unchanged). Task `DAYTRADE-003C-ORB-EVALUATOR-001` completed additive resolution specification (`docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json`, SHA-256 `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`) and report `docs/research/DAYTRADE-003C-ORB-EVALUATOR.md`; locked Relative Volume source-fidelity correction to immediately preceding 14 completed regular trading sessions (no eligible-session searching); resolved ATR to Wilder ATR14; resolved sizing to source-linked 1%-risk / 4x leverage framework with deterministic portfolio gross leverage ceiling; resolved v1 commission to $0.0035/share without broker ticket minimums; locked raw daily + raw intraday price basis; locked broad PIT NYSE/Nasdaq stock-market universe without artificial security-type exclusions; excluded exchange early-close sessions; locked lean two-stage acquisition architecture; implemented deterministic research-only evaluator in `tradex/research/daytrade_orb/` with 56 passing synthetic tests; zero real-data acquisition; zero provider API calls; zero empirical backtests; zero holdout access; no production behavior change; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved; recommended next bounded task is data feasibility/acquisition tooling only, subject to review (not authorized automatically).

**Recommended next work order:**
1. **LONG-MVP-002 review and merge** — Review and merge PR 2 (`antigravity/long-mvp-002-strategy-impl`), implementing the production-target long opportunity strategy v1 end-to-end according to the LONG-MVP-001 contract (fetcher daily preset, indicators, scoring, screener, watcher, confluence, UI, tests), requiring explicit Gary Yang approval prior to merge.
2. **MVP-ARCH-001-R7-PIT-ACTIVATE-001-VERIFY** — Verify the first naturally scheduled Candidate C PIT captures after the 2026-09-21 morning (09:00 ET) and evening (20:30 ET) slots. This is a future verification task only; do not implement in this PR.
3. **DAYTRADE-001** — `DAYTRADE-001A` foundation completed; `DAYTRADE-001B` specification locked; `DAYTRADE-001C1` merged; `DAYTRADE-001C2` real study completed (validation `inconclusive`, holdout `unread_not_acquired`); production promotion unauthorized.
4. **DAYTRADE-002** — `DAYTRADE-002A` specification locked; `DAYTRADE-002B` evaluator merged via PR #91; PR #94 / `DAYTRADE-002C` merged at commit `70d41000bb8ce17e3fca2300ac3dc8e25df5f186` as INVALID execution audit evidence; `DAYTRADE-002C-CORR-001A` timestamp-schema fix merged via PR #96 at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`; `DAYTRADE-002C-CORR-001B` corrected preholdout study completed (development `rejected`, validation `inconclusive`, validation bundle SHA-256 `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`, zero reacquisition, zero provider calls, non-calculation metadata defect in `metrics.json` documented with zero calculation impact, holdout strictly `unread_not_acquired`); `DAYTRADE-002C-CORR-002` evaluator provider-provenance metadata fix completed in `study.py` (synthetic injected fixtures remain labeled `synthetic_fixtures_only`; manifest-backed evaluations derive provenance summary from verified manifest; historical CORR-001B artifacts remain unchanged; zero empirical reruns; zero real-data access; zero provider calls; holdout strictly `unread_not_acquired`; DAYTRADE-002 validation remains INCONCLUSIVE; no production promotion; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved).
5. **DAYTRADE-003** — Gary selected evidence-backed Stocks-in-Play 5-minute ORB; DAYTRADE-003A merged via PR #102; DAYTRADE-003B merged via PR #104 (spec SHA-256 `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`); DAYTRADE-003C completed and merged via PR #106 (resolution spec SHA-256 `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`); Relative Volume corrected to previous 14 completed regular sessions; Wilder ATR14 locked; 1% risk / 4x portfolio leverage sizing locked; commission minimum resolved without ticket minimums; raw daily + raw intraday price basis locked; broad PIT NYSE/Nasdaq universe locked; synthetic evaluator and dataset contract implemented; zero real-data acquisition; zero provider calls; zero empirical backtests; zero holdout access; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved; recommended next task is bounded data feasibility/acquisition tooling only, subject to review.

**Recommended next pull request order:**
1. **PR 2: `antigravity/long-mvp-002-strategy-impl` (LONG-MVP-002)** — Implement production long strategy v1 according to the LONG-MVP-001 contract (completed — pending review/merge; requires explicit Gary Yang approval before merge).
2. **MVP-ARCH-001-R7-PIT-ACTIVATE-001-VERIFY** — Operational verification only.
3. **DAYTRADE-003 bounded data feasibility/acquisition tooling** — Subject to Gary Yang review and authorization.
