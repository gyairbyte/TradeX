# DAYTRADE-003G: Manual Market Preparation & Cached ORB Scanning

**Task ID:** `DAYTRADE-003G-MANUAL-PREP-CACHE`  
**GitHub Issue:** [#120](https://github.com/gyairbyte/TradeX/issues/120)  
**Classification:** Research-Only Market Observation & Performance Optimization  
**Branch:** `antigravity/daytrade-003g-manual-prep-cache`  
**Base Commit:** `c833698ba504f21e38b1cf8afd5e0da5597af775` (PR #119 merge commit on `origin/main`)  
**Strategy Authority:** Zarattini, Barbon, Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market* (Swiss Finance Institute RP 24-98 / SSRN 4729284)

---

## 1. Executive Summary & Objective

In DAYTRADE-003F, TradeX introduced a market-wide Opening Range Breakout (ORB) opportunity scanner that discovers and ranks the Top 20 Stocks in Play across the entire active U.S. equity universe. However, an on-demand scan across ~8,000 equities required 230 batched provider API calls (80 calls for 15 daily bars $D-15 \dots D-1$, 10 calls for session $D$ opening range bars, and 140 calls for 14-session prior opening-range volume baselines). Under Alpaca rate limits, this historical data acquisition required 70 to 120+ seconds during the time-sensitive post-opening window (09:35 ET).

**DAYTRADE-003G** optimizes this workflow by cleanly separating **historical data preparation** from the **post-opening opportunity scan**:

1. **Pre-Market Manual Preparation (e.g., 8:00 AM ET):**
   - The user opens TradeX, navigates to **Research Lab → ORB Candidate Preview → Market-Wide Live Discovery**, selects the provider and feed (SIP or IEX), and clicks **Prepare Market**.
   - TradeX discovers the active equity universe (~8,000 tickers), retrieves exactly 15 completed daily bars through $D-1$, computes ADV14 and Wilder ATR14, applies the preliminary liquidity/volatility filters ($\text{ADV14} \ge 1,000,000$, $\text{ATR14} > \$0.50$), retrieves the prior 14 completed sessions' opening-range volume baselines for daily-qualified symbols, validates all inputs, and persists an atomic, validated snapshot to user-local storage (`~/.tradex/orb_prep/`).
   - The user may safely close TradeX. The application does not need to remain running.

2. **Post-Opening Opportunity Scan (at or after 09:35 AM ET):**
   - The user reopens TradeX, returns to the scanner, and clicks **Scan Market**.
   - TradeX automatically validates and loads the prepared snapshot from disk, eliminating historical data retrieval.
   - It executes **zero historical daily-bar provider calls** and **zero prior-opening-volume provider calls**, retrieving only today's completed 09:30–09:34 ET 1-minute bars for the ~950 pre-qualified symbols.
   - It applies session $D$ opening price eligibility ($\text{Open} > \$5.00$), evaluates opening ranges and RV14, and deterministically ranks the Top 20 candidates.
   - Execution time is reduced by up to ~90%, while preserving exact numerical and ranking parity with the cold path.

3. **Fallback & Robustness:**
   - If no valid preparation exists, or if the artifact is stale, corrupt, or feed-mismatched, TradeX gracefully falls back to the slower cold scan path with an explicit notice, ensuring no silent degradation or data corruption.

---

## 2. Architecture & Design

### 2.1 Separation of Responsibilities

```
Pre-Market (e.g. 08:00 ET)                  Post-Opening (>= 09:35 ET)
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│     User clicks Prepare Market  │         │      User clicks Scan Market    │
└────────────────┬────────────────┘         └────────────────┬────────────────┘
                 │                                           │
                 ▼                                           ▼
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│       prepare_market(...)       │         │       run_market_scan(...)      │
├─────────────────────────────────┤         ├─────────────────────────────────┤
│ • Discover universe (~8,000)    │         │ • Inspect local cache status    │
│ • Fetch 15 daily bars (D-15..D-1│         │ • If valid preparation found:   │
│ • Calc ADV14 & Wilder ATR14     │         │   - Load cached universe/metrics│
│ • Filter ADV >= 1M & ATR > $0.50│         │   - 0 historical daily calls    │
│ • Fetch prior 14 OR volumes     │         │   - 0 prior OR volume calls     │
│ • Audit exclusions & coverage   │         │   - Fetch session D 1-min bars  │
│ • Save atomic local snapshot    │         │   - Apply Open > $5.00 & RV14   │
└────────────────┬────────────────┘         │   - Rank Top 20 candidates      │
                 │                          │ • Else: Fallback to cold scan   │
                 ▼                          └─────────────────────────────────┘
┌─────────────────────────────────┐
│  ~/.tradex/orb_prep/            │
│  orb_prep_<session>_<prov>_<fd> │
└─────────────────────────────────┘
```

### 2.2 Reusable Preparation Service (`tradex/research/daytrade_orb/preparation.py`)

The preparation service provides clean, decoupled primitives:

- **`prepare_market(...)`**: Orchestrates discovery, daily bar retrieval ($D-15 \dots D-1$), ADV14/ATR14 evaluation, preliminary liquidity filtering, prior 14-session opening-range volume collection, and persistence.
- **`save_prepared_snapshot(...)`**: Serializes and writes the preparation artifact to disk using atomic temporary file creation (`.tmp_<uuid>`) and atomic replacement (`os.replace`).
- **`load_prepared_snapshot(...)`**: Deserializes and validates a saved snapshot.
- **`validate_prepared_snapshot(...)`**: Performs multi-point verification against the target session, provider, feed, lookback calendar, payload integrity hash, and schema version.
- **`inspect_cache_status(...)`**: Non-intrusively checks local disk for valid preparation without making network calls.

### 2.3 Persistent Local Cache Specification

- **Location:** `PathSettings.orb_cache_dir` defaulting to `~/.tradex/orb_prep/` (configurable via `TRADEX_ORB_CACHE_DIR`). Outside git tracking.
- **Naming Convention:** `orb_prep_{session_date}_{provider}_{feed}.json` (e.g. `orb_prep_2026-10-22_alpaca_sip.json`).
- **Atomic Write Strategy:**
  1. Writes JSON payload to `orb_prep_{session_date}_{provider}_{feed}.json.tmp_{uuid}`.
  2. Flushes and syncs file buffers to physical disk.
  3. Uses `os.replace` to atomically swap the temporary file over the target destination.
  4. Guarantees that application termination or process kill during preparation cannot leave a corrupted cache file.
- **Integrity Checksum:** Computes a SHA-256 digest of the canonical snapshot payload and embeds it in `integrity_hash`. Upon loading, recomputes the SHA-256 digest and rejects tampered or truncated files.
- **Credential & Secret Isolation:** The snapshot strictly records tickers, metrics, volumes, exclusions, and timestamps. Zero API keys, OAuth tokens, account IDs, or environment secrets are persisted.

---

## 3. Scanner Integration & Parity Verification

### 3.1 Warm Scan Execution Path

The `run_market_scan(...)` entrypoint was extended with `use_cache: bool = True` and optional `prepared_snapshot` / `cache_dir`:

1. **Cache Loading & Validation:** When `use_cache=True`, the scanner checks for an existing preparation artifact matching the current session date, provider, and feed.
2. **Provider Call Elimination:**
   - **0 daily bar calls:** The historical daily bars ($D-15 \dots D-1$), ADV14, Wilder ATR14, and daily technical exclusions are loaded directly from the prepared snapshot.
   - **0 prior opening volume calls:** The exact 14-session opening-range volume baselines for daily-qualified symbols are loaded directly from the prepared snapshot.
3. **Session D Execution:**
   - Retrieves only session $D$ 09:30–09:34 ET 1-minute bars for the daily-qualified symbols.
   - Evaluates regular-session opening print eligibility: $\text{Open} > \$5.00$.
   - Computes opening range (High, Low, Open, Close, Volume), setup direction (LONG, SHORT, DOJI), and Relative Volume ($\text{RV14}$).
   - Filters $\text{RV14} \ge 1.0$ and ranks the Top 20 Candidates using the locked Zarattini et al. ranking algorithm.
4. **Deterministic Equivalence:**
   - An automated test (`test_warm_scan_matches_cold_scan_exact_parity`) executes both the cold scan path and the warmed scan path on the identical populated 33-symbol fixture and verifies exact, 100% field-for-field parity across all candidate setups, rankings, directions, breakout levels, stop offsets, RV14 values, and exclusions.

### 3.2 Cache Fallback Invariant

If the cache file is absent, stale (different session date), mismatched (different feed or provider), corrupted (bad JSON or SHA-256 mismatch), or truncated, the scanner automatically falls back to the full cold scan workflow and appends an explicit audit warning:
> *"No prepared market snapshot found; executing cold scan."*

---

## 4. UI Enhancements in Research Lab

The **Research Lab → ORB Candidate Preview → Market-Wide Live Discovery** tab was enhanced with:

1. **Market Preparation Card:**
   - **Target Session Date:** Displays target regular XNYS session date.
   - **Prep Status:** Displays `NOT_PREPARED`, `PREPARING`, `READY`, `PARTIAL`, `FAILED`, or `STALE`.
   - **Prepared At:** ET timestamp of preparation completion.
   - **Eligible / Discovered:** Pre-screened candidates passing ADV14/ATR14 vs total discovered universe (e.g. `950 / 8,124`).
2. **Action Buttons:**
   - **🛠️ Prepare Market:** Executes pre-market universe discovery, daily metrics calculation, prior volume baseline retrieval, and cache persistence.
   - **🔍 Scan Market:** Executes post-opening candidate evaluation and ranking (warmed if preparation exists; cold otherwise).
3. **Scan Execution Badge & Timing Banner:**
   - **⚡ Warmed Scan Badge:** `⚡ Warmed Scan (Zero Historical Provider Calls): Loaded valid preparation snapshot from HH:MM:SS ET. Retrieved session D opening range (X securities evaluated).`
   - **🐢 Cold Scan Banner:** `🐢 Cold Scan (Live Historical Acquisition): [reason]. Retrieved full historical daily bars and prior 14-session opening-range volume baselines.`
   - **Scan Path Metric:** Explicitly indicates `⚡ Warmed (Cache)` or `🐢 Cold (Live)`.

---

## 5. Market Calendar, Lookbacks & Edge Case Defenses

1. **Exact 15 Daily Sessions ($D-15 \dots D-1$):**
   - Welles Wilder 14-period ATR requires 15 completed daily bars ($D-15 \dots D-1$) to compute the initial 14-period True Range baseline and the 15th smoothed step.
2. **Exact 14 Opening-Range Volume Sessions ($D-14 \dots D-1$):**
   - RV14 requires the exact prior 14 completed XNYS regular trading sessions.
3. **Calendar Awareness:**
   - Non-trading days (weekends, NYSE holidays) are detected via `is_trading_day(...)`. Attempting preparation on a non-trading day fails closed with `PreparationStatus.FAILED` ("Session YYYY-MM-DD is not an active regular XNYS trading session").
   - Early market closures (e.g., 13:00 ET on post-Thanksgiving or Christmas Eve) are detected via `is_early_close(...)` and excluded from regular lookback sets to prevent distorted volume baselines.
4. **Session D Price Filter Deferred:**
   - The $\$5.00$ minimum price requirement is strictly deferred to session $D$'s 09:30 ET opening print. It is **not** evaluated during pre-market preparation, preserving eligibility for stocks that gap up above $\$5.00$ at the open.
5. **Partial Market Coverage & Provisional Status:**
   - If provider rate limits or network issues cause partial symbol coverage during preparation, the snapshot records `PreparationStatus.PARTIAL`. When scanned, candidates are marked as provisional.
6. **IEX Feed Disclosure:**
   - Free-tier IEX preparation and scans always record and display the provisional coverage warning: *"IEX feed reflects ~2% tape volume; rankings are provisional."*

---

## 6. Governance & Explicit Exclusions

In accordance with TradeX architecture and DAYTRADE-003G constraints:

- **Manual Trigger Only:** No Windows Task Scheduler, cron jobs, background threads, or automatic 8:00 AM daemons were added. Gary explicitly chose manual preparation.
- **Production Isolation:** Strategy registry remains strictly unpromoted:
  ```python
  APPROVED_PRODUCTION_STRATEGIES == ()
  ```
- **Zero Strategy Mutation:** No weights, thresholds, formulas, or ranking criteria were altered.
- **Zero Secrets in Persistence:** Cache files contain only public market data and computed metrics.
- **No Order Routing or Live Broker Interactions:** Workflow remains strictly read-only and exploratory inside Research Lab.

---

## 7. Verification Results

| Test Suite | Tests Passed | Status | Coverage Focus |
|---|:---:|:---:|---|
| `tests/research/daytrade_orb/test_preparation.py` | 10 | **PASS** | Calendar lookbacks, Wilder ATR14, non-trading day rejection, atomic replacement, corrupt checksum rejection, stale feed rejection, zero secrets |
| `tests/research/daytrade_orb/test_warm_scan.py` | 6 | **PASS** | Zero historical provider calls during warm scan, exact warm/cold parity, Doji invariant preservation, fallback on missing/corrupt/incompatible cache |
| `tests/research/daytrade_orb/test_scanner.py` | 19 | **PASS** | Market scan execution, stage transitions, exclusions, Doji no-order invariant, time gating |
| `tests/ui/test_orb_scanner_ui.py` | 10 | **PASS** | UI buttons, preparation progress container, cache status cards (Ready, Stale), warm scan badge, zero provider calls before click |
| `tests/research/daytrade_orb/` (Full Suite) | 284 | **PASS** | Comprehensive research regression suite |
| `ruff check tests scripts` | All checks passed | **PASS** | Clean lint and style compliance |
