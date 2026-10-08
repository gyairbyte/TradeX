# DAYTRADE-003D: Stocks-in-Play ORB Real-Data Feasibility & Acquisition Probe

## 1. Document & Task Metadata

- **Task ID:** `DAYTRADE-003D-ORB-DATA-FEASIBILITY-001`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Classification:** Research-only real-data feasibility and bounded acquisition probe
- **Base / Starting Main SHA:** `faec0b096bd8fe7b1f7761557a1f74fbdac41ba1`
- **Pre-Live Code Freeze Commit:** `2d756c266cf50082e48ca5fc341f4e83c93a5644`
- **Live-Evidence Documentation Commit:** `f0b9fda2cff90ab9cd7bd9049019b4357a3d9a3f`
- **Locked DAYTRADE-003B Spec:** `docs/research/specs/DAYTRADE-003B-ORB-v1.json` (SHA-256: `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`)
- **Locked DAYTRADE-003C Resolution Spec:** `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` (SHA-256: `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`)
- **Machine-Readable Specification:** `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` (SHA-256: `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c`)
- **Authoritative Final Disposition:** `INVALID_PROBE_IMPLEMENTATION_DEFECT`
- **Observed Stop Condition:** `BLOCKED_RESOURCE_BOUND_UNDER_FROZEN_BATCH100_PLAN`

---

## 2. Research Protocol & Governance Boundaries

This assignment is strictly bounded to data feasibility and acquisition validation.

- **Real provider calls:** AUTHORIZED ONLY within the exact bounds of this probe.
- **Private local research data:** AUTHORIZED ONLY within the exact bounds of this probe.
- **Full 2024 development dataset construction:** NOT AUTHORIZED.
- **Strategy backtest / evaluator execution:** NOT AUTHORIZED.
- **Development performance evaluation:** NOT AUTHORIZED.
- **Validation partition (2025):** NOT AUTHORIZED / UNOPENED.
- **Holdout partition (2026):** STRICTLY QUARANTINED AND UNOPENED.
- **Production trading behavior:** NO CHANGE. `APPROVED_PRODUCTION_STRATEGIES == ()`.

The sole question for DAYTRADE-003D is:
> *Can the currently available Massive/Polygon + Alpaca SIP provider path construct the data required by the locked DAYTRADE-003B/003C contracts truthfully enough to proceed with the 2024 development dataset?*

---

## 3. Fixed Probe Dates

All dates are locked prospectively and verified as full regular XNYS sessions (opens 09:30 ET, closes 16:00 ET, `is_early_close == False`):

1. **`2024-01-02`** (Session 1 of 2024 — End-to-end Stage A + Stage B pilot date)
2. **`2024-06-03`** (Mid-year reference-only snapshot)
3. **`2024-12-02`** (Late-year reference-only snapshot)

For all three dates, a complete historical active U.S. stock-market point-in-time reference snapshot is acquired from Massive (`/v3/reference/tickers`) to audit historical date sensitivity, pagination, symbol identity, and universe drift. Intraday bars are acquired ONLY for `2024-01-02`.

---

## 4. Exchange Mapping Policy

DAYTRADE-003C specifies point-in-time U.S. equity-market records whose primary exchange is **NYSE or Nasdaq**.
Massive / Polygon exposes ISO 10383 Market Identifier Codes (MIC):
- **NYSE:** `XNYS`
- **Nasdaq:** `XNAS`

Non-target exchanges (such as `ARCX` NYSE Arca, `XASE` NYSE American, `BATS` Cboe BZX, `XBOS` Nasdaq BX, and OTC/empty) are excluded from the target candidate universe.
No artificial security-type exclusions (e.g. against ETFs or warrants) are applied; provider `type` values are preserved for auditability.

---

## 5. Lean Two-Stage Acquisition Architecture & Strict No-Lookahead

1. **Stage A (09:30-09:34 ET candidate construction):**
   - Raw daily OHLCV from Alpaca SIP (`timeframe=1Day`, `adjustment=raw`, `asof=2024-01-02`) covering the 20 completed regular XNYS trading sessions in December 2023 (2023-12-01 through 2023-12-29). Target session 2024-01-02 is strictly excluded from ADV14 and ATR14 lookbacks.
   - Raw 1-minute bars from Alpaca SIP (`timeframe=1Min`, `adjustment=raw`) for 09:30..09:34 ET across the 14 prior completed XNYS sessions (2023-12-11 through 2023-12-29) for Relative Volume denominator baseline.
   - Raw 1-minute bars for 2024-01-02 09:30..09:34 ET for current opening range.
   - 100% candidate-pool computability gate: every active target-universe member must have computable indicators. Insufficient history due to IPO listing age is surfaced and classified explicitly.

2. **Strict No-Lookahead Freezing:**
   - Candidate ranking (RV desc, ticker asc) and Top-20 selection occurs strictly prior to requesting any post-09:35 market data.
   - The Top-20 selection artifact is serialized and hashed (`top_20_selection_artifact_hash`) before Stage-B acquisition begins.

3. **Stage B (09:35-15:59 ET trade path):**
   - Raw 1-minute SIP bars (`timeframe=1Min`, `adjustment=raw`) for the selected Top-20 symbols only.
   - Complete 385-minute path audited. Zero strategy backtesting or PnL evaluation executed.

---

## 6. Private Output Root & Artifact Safety

- **Private Output Root:** `C:\Users\Gary\.tradex\research\daytrade_003d_orb_probe`
  Contains raw bar files, full ticker rosters, and the complete private manifest `manifest.json`.
- **Public Repository Artifacts:** `docs/research/artifacts/DAYTRADE-003D/`
  Contains ONLY safe aggregates:
  - `probe_summary.json`
  - `resource_estimate.json`
  - `provider_evidence.json`
  Zero OHLC prices, zero ticker symbol lists, and zero credentials are committed.

---

## 7. Disposition Precedence Hierarchy

1. `FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD`
2. `BLOCKED_MASSIVE_ENTITLEMENT`
3. `BLOCKED_ALPACA_SIP_ENTITLEMENT`
4. `BLOCKED_REFERENCE_EXCHANGE_MAPPING`
5. `BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS`
6. `BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY`
7. `BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS`
8. `BLOCKED_STAGE_A_DATA_COMPLETENESS`
9. `BLOCKED_STAGE_B_PATH_COMPLETENESS`
10. `BLOCKED_RESOURCE_BOUND`
11. `INVALID_PROBE_IMPLEMENTATION_DEFECT`
12. `INVALID_PROVIDER_RESPONSE_INTEGRITY`

---

## 8. Preserved Valid Provider Capabilities Evidence

The live probe obtained valuable, verifiable empirical findings that remain valid:

### Massive PIT Reference Snapshot Audit
- **Endpoint:** `/v3/reference/tickers` (`active=true`, `limit=1000`)
- **Observed Snapshots:**
  - `2024-01-02`: 11,109 rows, 12 pages, terminal pagination reached | SHA-256 `a3131c477d4af0b464410bc1bef369bf87d6a2830b7a72284cdd3f0667a786a7`
  - `2024-06-03`: 11,014 rows, 12 pages, terminal pagination reached | SHA-256 `8fcd08e763bc568049dd43b5fcf93d9fb3f3b1cb7c3ec770edcbf0cda6dfa962`
  - `2024-12-02`: 11,095 rows, 12 pages, terminal pagination reached | SHA-256 `590c76310a2a871031ec8722b1d4f5a6a582b5cc7fb0ab8e33375c43d198fc07`
- **Date Sensitivity Proven:** Row counts and canonical digests differ across dates, confirming historical PIT snapshot sensitivity.
- **Exchange Code Mapping Verified:**
  - Primary target exchanges: `XNYS` (3,008 symbols) + `XNAS` (4,981 symbols) = **7,987 symbols** for `2024-01-02`.
  - Excluded exchanges: `ARCX` (2,102), `BATS` (670), `XASE` (348).

### Alpaca Market Data Entitlement Audit
- **Endpoint:** `/v2/stocks/bars`
- **Feed:** SIP (entitled)
- **Adjustment Mode:** `raw` (verified)
- **SPY Smoke Probe:**
  - Daily bars (2023-12-01 to 2024-01-02): 20 bars returned, HTTP 200.
  - Opening range 1-minute bars (2024-01-02 09:30-09:34 ET): 5 bars returned, HTTP 200.
- **`asof` Evidence Boundary:** The `asof=2024-01-02` parameter was accepted by the provider in the bounded smoke test. Cross-provider historical symbol identity remains untested because Stage A did not execute.

---

## 9. Post-Live Audit Review & Discovered Implementation Defects

Independent review following the live probe identified four material implementation and planning defects that require classification under `INVALID_PROBE_IMPLEMENTATION_DEFECT` rather than a provider-intrinsic failure:

### 1. Batch-Size / Resource-Bound Planning Defect
- The pre-live implementation locked `batch_size = 100`.
- For the measured 7,987 symbol universe, this produced:
  - 80 daily requests + 1,200 opening-range requests (15 sessions × 80 batches) + 1 Stage-B probe + 36 Massive pages = **1,317 planned pages**.
- However, the 1,000-page failure is an artifact of the arbitrary batch size, not an intrinsic provider limit:
  - Under the identical planner assumptions, `ceil(7,987 / 134) = 60 batches`:
    - 60 daily + (60 × 15) opening-range + 1 Stage-B + 36 Massive = **997 planned pages** (below the 1,000-page limit).
- The probe did NOT demonstrate that the data architecture exceeds the pilot limit, only that the frozen batch-size-100 plan exceeded it.

### 2. Full-Year Storage Extrapolation Defect
- The artifact reported ~190,849,785 rows but only 25,689,579 bytes (~25.7 MB) of storage.
- These numbers are internally inconsistent: the frozen planner assumes ~200 bytes per stored bar row, which implies:
  - $190,849,785 \times 200 = 38,169,957,000\text{ bytes}$ (~38.2 GB decimal / ~35.6 GiB).
- The 25.7 MB estimate occurred because `compute_full_year_estimate()` multiplied pre-acquisition pilot directory size (~103 KB) by 249 sessions because Stage A never ran.
- `extrapolated_storage_bytes = 25,689,579` is therefore **INVALID_NOT_DECISION_GRADE**. The 38.2 GB figure serves only as an internal consistency check, not a formal forecast.

### 3. Full-Year Call/Page Extrapolation Defect
- The full-year projection reported ~318,720 Alpaca calls and ~318,969 total pages.
- This was produced by naively multiplying the single-session Stage-A plan by 249 sessions, redundantly reacquiring the 20 prior daily sessions and 14 opening-range sessions every day.
- A production dataset builder must reuse already-acquired historical observations across adjacent sessions.
- These figures represent a **NAIVE_NO_REUSE_EXTRAPOLATION** and are marked `INVALID_REQUIRES_CORRECTED_ACQUISITION_PLAN`.

### 4. Canonical Duplicate Identity Defect
- Safe artifacts reported `duplicate_ticker_count = 2` while `unresolved_duplicate_count = 0`.
- Audit of `filter_target_universe()` shows it silently retained the first row for duplicate canonical tickers and hard-coded `unresolved_duplicate_count = 0`.
- This does not prove that the target PIT universe is identity-clean.
- Status is recorded as `canonical_duplicate_count = 2`, `canonical_duplicate_resolution_status = "UNRESOLVED_BY_FROZEN_PROBE"`.

---

## 10. Authoritative Final Disposition

Pursuant to Section 15 (*Real-Data Integrity Rule After First Access*):
> *If an implementation defect is discovered after live provider access, the task must stop and be classified as `INVALID_PROBE_IMPLEMENTATION_DEFECT`.*

- **Authoritative Final Disposition:** **`INVALID_PROBE_IMPLEMENTATION_DEFECT`**
- **Observed Stop Condition:** **`BLOCKED_RESOURCE_BOUND_UNDER_FROZEN_BATCH100_PLAN`**
- **Stage A Executed:** No (`stage_a_candidate_pool = null`)
- **Top-20 Selection Executed:** No (`stage_a_selection = null`)
- **Stage B Executed:** No (`stage_b_path = null`)
- **Strategy Backtest / Evaluator Executed:** No
- **Validation (2025) Status:** Unopened
- **Holdout (2026) Status:** Quarantined & unopened
- **Production Status:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 11. Recommended Next Task: `DAYTRADE-003D-CORR-001A`

A separately authorized correction task (`DAYTRADE-003D-CORR-001A`) is required before any subsequent live provider access.

### Correction Scope:
1. **Offline Acquisition Planning:** Preregister an optimized multi-symbol batching plan (e.g. `batch_size >= 134`) within provider request constraints.
2. **Fail-Closed Duplicate Identity:** Fail closed on unresolved canonical duplicate identity during universe filtering before Stage-A acquisition.
3. **Validated Deduplicated Resource Model:** Construct a valid, deduplicated full-year acquisition model that accounts for historical lookback observation reuse across adjacent trading sessions.
4. **Validated Storage Model:** Construct a verified row-count and byte-size storage projection grounded in actual schema definitions.

### Governance Guardrail:
- **NO strategy-universe narrowing is authorized.**
- Do NOT implement or recommend market-cap filters, index filters, security-type filters, or smaller exchange subsets as workarounds.
- The evidence-backed research strategy universe (broad NYSE/Nasdaq PIT stock-market universe without artificial exclusions) remains strictly unchanged.
