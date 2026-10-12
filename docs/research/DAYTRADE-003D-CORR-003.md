# DAYTRADE-003D-CORR-003
# ORB Provider Integrity, Offline Replay, and Stage-B Validation

## 1. Executive Summary & Authoritative Disposition

- **Task ID:** `DAYTRADE-003D-CORR-003`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Pilot Date:** `2024-01-02`
- **Base Commit:** `4b1d7084d5d8c91ef10fffbc1f7169de43bfcd0a` (merged PR #110)
- **Proposed Branch:** `antigravity/daytrade-003d-corr-003-integrity-replay`
- **Classification:** Research-only methodology and data-integrity correction. No production trading changes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Permanent Research Candidate Retention (Principle B):** The published Stocks-in-Play 5-minute Opening Range Breakout strategy (Zarattini et al., 2024) remains a permanent externally supported research candidate.
- **Historical Disposition Invariance:** Preserves the frozen January 2, 2024 pilot results and authoritative `INVALID_CORR_002_IMPLEMENTATION` disposition.
- **Live Execution Gate Status:** **STRICTLY LOCKED**. No live provider calls or live pilot reruns are executed. Delivering draft PR with verified synthetic tests and deterministic offline replay, stopping at the live execution gate pending Gary Yang's explicit authorization.

---

## 2. Correction of the Three Material CORR-002 Deficiencies

This methodology correction directly addresses and resolves the three independently confirmed deficiencies identified during the review of DAYTRADE-003D-CORR-002:

### Correction 1: Provider Payload Integrity Validation
- **Deficiency in CORR-002:** Missing provider records or empty responses were treated as legitimate sparse minutes without validating that the provider payload succeeded, completed pagination, and returned valid bar structures.
- **Resolution in CORR-003:** Added [`validate_provider_batch_response`](file:///tradex/research/daytrade_orb/corr_003_pilot.py):
  - Validates HTTP 200 status code; any non-200 payload fails closed.
  - Enforces `pagination_complete == True`; truncated pagination fails closed.
  - Verifies symbol identities in response match requested query keys; unexpected symbols fail closed.
  - Validates timestamp parsing and strictly enforces session window constraints (e.g., 09:30–09:34 ET for Opening Range, 09:35–15:59 ET for Stage B); out-of-session prints fail closed.
  - Detects duplicate timestamps within any symbol's series and fails closed.
  - Enforces OHLCV invariants: `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`, `low >= 0`, `volume >= 0`, all values finite and non-NaN.
  - Distinguishes verified empty responses (zero trades during interval, legitimate `NO_OPENING_PRINT_NO_SETUP`) from failed/corrupt responses (`PROVIDER_DATA_FAILURE`). Failed requests are **never** converted into zero-volume bars.

### Correction 2: Private Raw OHLCV Persistence & Deterministic Offline Replay
- **Deficiency in CORR-002:** The runner did not persist the raw Alpaca OHLCV payloads for daily bars, prior opening ranges, session opening ranges, or Stage-B minutes, preventing offline replication.
- **Resolution in CORR-003:**
  - Implemented complete private raw persistence schema via [`persist_raw_stage_artifact`](file:///tradex/research/daytrade_orb/corr_003_pilot.py) and [`create_and_save_manifest`](file:///tradex/research/daytrade_orb/corr_003_pilot.py).
  - Persists full batch provenance: HTTP status, pagination metadata, page count, pagination token sequence hashes, and raw bars by symbol.
  - Generates a cryptographic manifest (`manifest_<date>.json`) recording artifact filenames, SHA-256 hashes, byte sizes, and record counts.
  - Implemented [`replay_corr_003_pilot`](file:///tradex/research/daytrade_orb/corr_003_pilot.py) and `daytrade_003d_corr_003_pilot.py replay`:
    - Operates with **zero network access** and **zero provider credentials**.
    - Verifies all 6 upstream specification hashes before execution.
    - Verifies manifest checksums; fails closed on missing, extra, or modified files.
    - Deterministically reproduces universe filtering, daily screening, opening range evaluation, Top-20 ranking, and Stage-B usability.

### Correction 3: Stage-B Usability Invariants & 15:59 ET Liquidation Bar Coverage
- **Deficiency in CORR-002:** Stage-B audit marked paths `USABLE` solely based on zero provider failures, without checking bar invariants or enforcing 15:59 ET liquidation coverage.
- **Resolution in CORR-003:** Implemented [`audit_stage_b_price_path_corr_003`](file:///tradex/research/daytrade_orb/corr_003_pilot.py):
  - Strictly requires the presence of a valid 15:59 ET EOD liquidation bar for every selected actionable symbol (`missing_eod_bar_symbols_count == 0`).
  - Verifies zero provider failures and zero bar integrity failures (`provider_failure_count == 0`, `integrity_failure_count == 0`).
  - Correctly accounts for legitimate sparse trading minutes (intervals where no trades occurred) without fabricating synthetic prints or misclassifying provider failures.
  - Requires actionable symbols to evaluate; an empty selection pool fails closed as unusable.

---

## 3. Preregistered Specifications & Upstream Hashes

All six specifications are verified via SHA-256:

| Specification Document | Path | SHA-256 Hash | Status |
| :--- | :--- | :--- | :--- |
| **003B Specification** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` | Immutable Verified |
| **003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` | Immutable Verified |
| **003D Data Feasibility** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` | Immutable Verified |
| **003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` | Immutable Verified |
| **003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` | Immutable Verified |
| **003D-CORR-003 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-v1.json` | `2f86d1231f55180b8fe4f65832cde8783e7c6058788a1e98130353b5822a1cdb` | Locked Preregistered |

---

## 4. Architecture & Implementation Summary

### 4.1 Python Modules & Scripts
- [`tradex/research/intraday_dataset/alpaca_client.py`](file:///tradex/research/intraday_dataset/alpaca_client.py):
  - Added backward-compatible opt-in kwargs `include_raw_bars: bool = False, include_raw_pages: bool = False` to `get_stock_bars_multi_chunked` to retain raw provider response payloads for persistence.
- [`tradex/research/daytrade_orb/corr_003_pilot.py`](file:///tradex/research/daytrade_orb/corr_003_pilot.py):
  - Primary module housing provider integrity validation, Stage-B auditing, persistence/manifest management, prospective disposition determination, and the deterministic offline replay engine.
- [`scripts/research/daytrade_003d_corr_003_pilot.py`](file:///scripts/research/daytrade_003d_corr_003_pilot.py):
  - Dual CLI runner:
    - `replay`: fully offline deterministic replay subcommand.
    - `pilot`: bounded live pilot execution subcommand gated behind explicit authorization (`--authorize-live`) and pre-live commit SHA verification (`--pre-live-sha`).
- [`tests/research/daytrade_orb/test_corr_003_integrity_replay.py`](file:///tests/research/daytrade_orb/test_corr_003_integrity_replay.py):
  - Comprehensive test suite covering 23 unit and synthetic verification cases.

### 4.2 Replay Persistence Schema
Artifacts stored under private storage directory:
1. `massive_reference_<date>.json`: Universe snapshot rows from Massive Reference API.
2. `alpaca_daily_dec2023.json`: Raw daily bar batches across canonical target universe.
3. `alpaca_current_or_<date>.json`: Raw 09:30–09:34 ET minute bar batches for target date.
4. `alpaca_prior_or_14sessions_<date>.json`: Raw 14-session prior opening range batches.
5. `top_20_selection_<date>.json`: Top-20 ranking and order intent records.
6. `alpaca_stage_b_<date>.json`: Raw 09:35–15:59 ET minute bar batches for actionable symbols.
7. `manifest_<date>.json`: Cryptographic manifest binding all artifacts by SHA-256 and byte size.

---

## 5. Verification Results

### 5.1 Test Suite Execution
- **CORR-003 Synthetic & Offline Tests:** 23 passed in 0.28s ([`tests/research/daytrade_orb/test_corr_003_integrity_replay.py`](file:///tests/research/daytrade_orb/test_corr_003_integrity_replay.py)).
  - Upstream spec hash verification: PASSED
  - Strategy registry empty invariant: PASSED
  - HTTP error, truncated pagination, unexpected symbol, malformed timestamp, duplicate timestamp, out-of-session bar, invalid OHLCV detection: PASSED
  - Distinction between provider failure and verified completed no-print: PASSED
  - Stage-B usability with valid sparse minutes and 15:59 liquidation bar: PASSED
  - Stage-B unfitness on missing 15:59 bar, provider failure, duplicates, out-of-session bars: PASSED
  - Complete deterministic offline fixture replay: PASSED
  - Missing artifact, tampered artifact, missing manifest, tampered manifest fail-closed: PASSED
- **Full ORB Test Suite:** 142 passed in 2.08s ([`tests/research/daytrade_orb/`](file:///tests/research/daytrade_orb/)).
- **Linter Check:** `uv run ruff check tests scripts` passed cleanly with 0 errors.

### 5.2 Execution Gate Verification
- Attempting to run `python scripts/research/daytrade_003d_corr_003_pilot.py pilot` without `--authorize-live` immediately halts with exit code 1:
  ```text
  [FATAL] Live execution gate active: Gary Yang has not authorized live provider calls.
  Deliver draft PR with passing offline replay tests and stop at execution gate.
  ```

---

## 6. Governance Safeguards & Boundaries

- **Strategy Invariance:** Zero strategy modifications, parameter changes, indicator alterations, or portfolio rule adjustments.
- **Production Isolation:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Simulation Invariance:** Zero backtesting, trade simulation, order fills, PnL calculations, or win-rate analyses performed.
- **Historical Immutability:** Specs `DAYTRADE-003B-ORB-v1.json`, `DAYTRADE-003C-ORB-RESOLUTION-v1.json`, `DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json`, `DAYTRADE-003D-CORR-001-v1.json`, and `DAYTRADE-003D-CORR-002-v1.json` are byte-for-byte unchanged.
- **Live Execution Gate:** Strictly locked. Live provider execution requires explicit written authorization from Gary Yang following independent review of the draft PR.
