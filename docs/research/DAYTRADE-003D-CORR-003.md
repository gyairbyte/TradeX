# DAYTRADE-003D-CORR-003
# ORB Provider Integrity, Offline Replay, and Stage-B Validation

## 1. Executive Summary & Authoritative Disposition

- **Task ID:** `DAYTRADE-003D-CORR-003`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Pilot Date:** `2024-01-02`
- **Execution PR:** #113
- **Branch:** `antigravity/daytrade-003d-corr-003-jan02-pilot-authorization`
- **Pre-Live Frozen Implementation SHA ($F$):** `cf554598bc486b73d646a593bb4174c02f6121c1`
- **Authorization Commit SHA ($A$):** `66474a28489e3567b248e068a755b75ff3c0eb69` (Gary Yang explicit approval on 2026-10-13)
- **Authoritative Empirical Disposition:** `**INVALID_CORR_003_IMPLEMENTATION**` (preregistered taxonomy status)
- **Audit Disposition Rationale:**
  The approved one-shot historical feasibility pilot was launched exactly once on 2026-10-13 (`uv run python scripts/research/daytrade_003d_corr_003_pilot.py pilot --pre-live-sha cf554598bc486b73d646a593bb4174c02f6121c1 --batch-size 100 --authorize-live`).
  Phase 1 (Massive PIT reference snapshot: 11,109 rows, 7,987 canonical symbols) and Phase 2 (Alpaca broad daily Dec 2023 history: 80 batches across 7,985 valid symbols, 7,558 daily computable, 959 daily-base-qualified) completed successfully with all 80 daily batches verified as valid provider payloads.
  At Phase 3, the frozen CLI runner crashed on the first batch with an unhandled exception: `TypeError: 'module' object is not callable` at line 538 of `scripts/research/daytrade_003d_corr_003_pilot.py` (`allowed_time_window=(time(9, 30), time(9, 34))`) because top-level `import time` shadowed `datetime.time`.
  Execution was interrupted before opening range minute bars, prior 14-session baseline observations, Top-20 ranking, or Stage-B minute bars could be acquired, and before a cryptographic manifest could be created.
  Under Gary Yang's authorization contract (`max_executions: 1`, `automatic_retry_after_partial_attempt_authorized: false`) and strict research protocol rules (no rerun after interruption, no post-freeze code changes), execution was terminated and partial artifacts were preserved intact.
  Independent offline replay against the private output directory failed closed as designed due to the missing manifest.
  This disposition reflects an implementation bug in the frozen live runner harness, **NOT** provider failure, data unavailability, or strategy invalidation.
- **Permanent Research Candidate Retention (Principle B):** Under Principle B, the published Stocks-in-Play 5-minute Opening Range Breakout strategy (Zarattini et al., 2024) remains a **permanent externally supported research candidate** regardless of independent evaluation outcomes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Execution Wall-Clock Runtime:** ~219.78 seconds (interrupted during Phase 3).
- **Total Private Raw Storage:** `88,609,308 bytes` (~88.6 MB, Bound: `2,147,483,648 bytes`).
- **Total Provider HTTP Pages:** `92` (12 Massive + 80 Alpaca, Ceiling: `5,000`).

---

## 2. Methodology & Upstream Specification Hashes

All seven upstream and environment specifications were verified via SHA-256 before live access:

| Document | Path | SHA-256 Hash | Status |
| :--- | :--- | :--- | :--- |
| **003B Specification** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` | Immutable Verified |
| **003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` | Immutable Verified |
| **003D Data Feasibility** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` | Immutable Verified |
| **003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` | Immutable Verified |
| **003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` | Immutable Verified |
| **003D-CORR-003 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-v1.json` | `2f86d1231f55180b8fe4f65832cde8783e7c6058788a1e98130353b5822a1cdb` | Locked Preregistered |
| **003D-CORR-003 Environment Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-ENVIRONMENT.json` | `09d2edda68d9940a175d2333613e80defb8e5a3d0275c8b9554e48dd9947a58f` | Locked Preregistered |

---

## 3. Preserved Empirical Pilot Evidence (2024-01-02 Execution)

### Phase 1: Massive PIT Target Universe (2024-01-02)
- **Raw Massive Snapshot Rows:** `11,109` across `12` pages (raw artifact SHA-256: `ebb74dab83cfdbbf875016d8b2f7a50d0970f2a7c1ec17250927daaf6ab0ad42`).
- **Target Exchange Scope:** `('XNYS', 'XNAS')`.
- **Canonical Target Universe Count:** `7,987` (`4,981` `XNAS`, `3,008` `XNYS`).
- **Target Universe Cryptographic Hash:** `383a66f1c7100922d38638f24e4a23724bbc29b77cafc51990dab6ccda117f20`.
- **Fail-Closed Canonical Duplicates:** Exactly `2` ambiguous duplicate identities resolved fail-closed as `AMBIGUOUS_IDENTITY`.
- **Valid Query Target Symbols:** `7,985`.

### Phase 2: Inexpensive Broad Daily Availability (Dec 2023 D-1 Lookback)
- **Broad PIT Universe Symbols:** `7,987`.
- **Daily Indicator Computable Symbols:** `7,558` (`94.63%` broad daily data availability).
- **Missing Daily Data Count:** `429`.
- **Daily-Base-Qualified Pool:** `959` symbols met ADV14 $\ge 1\text{M}$ shares and ATR14 $> \$0.50$.
- **Alpaca Daily Batches:** `80` batches of up to 100 symbols across 7,985 valid symbols.
- **Alpaca Daily Pages:** `80` HTTP pages fetched, `0` retries, `0` 429s.
- **Provider Payload Integrity:** All `80` batches validated with `integrity_status: VALID` under raw-to-aggregated bar parity and payload schema checks.
- **Raw Daily Artifact:** `alpaca_daily_dec2023.json` (`84,409,548 bytes`, SHA-256: `8a5612d7beac2e10fa7f1f99c0addcd0186718def9e85821b11a7656c1afd4e6`).

### Phase 3: Opening Range & Relative Volume Screening (Scope E Gate)
- **Screening Denominator (Daily-Base-Qualified Pool):** `959` symbols.
- **Execution Status:** **INTERRUPTED BEFORE DATA ACQUISITION**.
- **Root Cause:** Script crashed at line 538 of `scripts/research/daytrade_003d_corr_003_pilot.py` (`allowed_time_window=(time(9, 30), time(9, 34))`) with `TypeError: 'module' object is not callable` caused by `import time` shadowing `datetime.time`.
- **Validly Determined Symbols:** Uncomputed due to runner interruption.
- **Eligible Candidates:** Uncomputed.
- **Candidate Screening Completeness:** Uncomputed.

### Phase 4: Top-20 Selection Evidence
- **Execution Status:** **NOT REACHED** (blocked by Phase 3 interruption).
- **Top-20 Candidates Selected:** `0`.
- **Selection Hash:** None.

### Phase 5: Stage-B Price Path Audit (09:35–15:59 ET)
- **Execution Status:** **NOT REACHED** (0 provider calls made).
- **Stage-B Usability Status:** `UNUSABLE` (not acquired).

### Phase 6: Checksum Manifest
- **Execution Status:** **NOT CREATED** (runner terminated before manifest generation).
- **Manifest Hash:** None.

---

## 4. Material Review Findings & Independent Audit Analysis

### Finding 1: Top-Level Module Shadowing in Live Runner Script
In `scripts/research/daytrade_003d_corr_003_pilot.py`:
- Line 14 imports the standard library module: `import time`.
- Line 538 (Phase 3 current OR validation), line 667 (Phase 3 prior OR validation), and line 842 (Phase 5 Stage-B validation) attempt to call `time(9, 30)` and `time(15, 59)`, expecting the `time` class from the `datetime` module.
- Calling `time(9, 30)` on the module object raised `TypeError: 'module' object is not callable`.
- Phase 2 avoided this crash because it passed `expected_start=datetime(...)` rather than `allowed_time_window=(time(...), time(...))`.
- Consequently, Phase 1 and Phase 2 completed perfectly, and the crash occurred at the very first call to `validate_provider_batch_response` in Phase 3.

### Finding 2: Unit-Test Blindspot at Script Boundary
- The test suite in `tests/research/daytrade_orb/test_corr_003_integrity_replay.py` contained 98 deterministic tests covering all library validation functions in `tradex/research/daytrade_orb/corr_003_pilot.py`.
- In `test_corr_003_integrity_replay.py`, callers used `from datetime import time`, so library calls succeeded in tests.
- However, the top-level CLI script `scripts/research/daytrade_003d_corr_003_pilot.py`'s `run_corr_003_live_pilot` function was never executed in a dry-run or mock-provider integration test.
- This left an untested name-collision defect in the CLI script that escaped pre-live freeze review.

### Finding 3: Strict One-Shot Guard and No-Rerun Governance Compliance
- The runner wrote the durable atomic run lock `.pilot_run_lock_2024-01-02.json` at run startup (12:06 PM EDT).
- Gary Yang's authorization record explicitly mandates:
  - `"max_executions": 1`
  - `"automatic_retry_after_partial_attempt_authorized": false`
- The research protocol strictly mandates:
  - "No rerun after interruption"
  - "No code modifications after frozen implementation"
- The one-shot guard `check_one_shot_pilot_guard` in `corr_003_pilot.py` detects partial artifacts in the directory and correctly refuses any further runs.
- Modifying `scripts/research/daytrade_003d_corr_003_pilot.py` would violate the pre-live code freeze ($F = cf554598bc486b73d646a593bb4174c02f6121c1$).
- Therefore, the execution was properly halted and preserved without retrying.

### Finding 4: Independent Offline Replay Failure
- Running `uv run python scripts/research/daytrade_003d_corr_003_pilot.py replay` against `C:\Users\Gary\.tradex\research\daytrade_003d_corr_003`:
  ```text
  ================================================================================
  STARTING OFFLINE REPLAY: DAYTRADE-003D-CORR-003 (2024-01-02)
  Input Directory: C:\Users\Gary\.tradex\research\daytrade_003d_corr_003
  ================================================================================
  [REPLAY FAILED] Replay manifest verification failed closed: ['Missing manifest file: C:\\Users\\Gary\\.tradex\\research\\daytrade_003d_corr_003\\manifest_2024-01-02.json']
  ```
- The replay engine strictly refused to process unmanifested partial artifacts without credentials or network calls, confirming that the fail-closed manifest verification works as designed.

### Finding 5: Subprocess Preflight Test Omitted `--output-dir` Isolation
- In `tests/research/daytrade_orb/test_corr_003_integrity_replay.py:test_live_pilot_preflight_rejects_missing_uv_lock`, the test invoked `scripts/research/daytrade_003d_corr_003_pilot.py pilot` in a subprocess with `--repo-root str(tmp_path)` but omitted `--output-dir str(tmp_path / "private_output")`.
- When run prior to live execution, `DEFAULT_PRIVATE_ROOT` was clean so the test passed.
- However, once the live pilot executed and deposited `.pilot_run_lock_2024-01-02.json` into `DEFAULT_PRIVATE_ROOT`, running `test_live_pilot_preflight_rejects_missing_uv_lock` without an isolated `--output-dir` triggered `check_one_shot_pilot_guard` on `DEFAULT_PRIVATE_ROOT` before reaching `check_runtime_environment_freeze`.
- Future correction (`DAYTRADE-003D-CORR-004`) must pass an isolated `--output-dir` in `test_live_pilot_preflight_rejects_missing_uv_lock`.

---

## 5. Preserved Private Raw Artifacts & Hashes

All private artifacts acquired during the single pilot run are preserved in `C:\Users\Gary\.tradex\research\daytrade_003d_corr_003`:

| File Name | Size (Bytes) | SHA-256 Checksum | Description |
| :--- | :--- | :--- | :--- |
| `.pilot_run_lock_2024-01-02.json` | 225 | `f0f2057a72c23fe24fee53f3c27515ed19080d4cad5781d13526018e7bff1413` | Durable atomic pilot run-start lock marker |
| `massive_reference_2024-01-02.json` | 4,104,222 | `ebb74dab83cfdbbf875016d8b2f7a50d0970f2a7c1ec17250927daaf6ab0ad42` | Raw Massive reference snapshot (11,109 rows) |
| `universe_2024-01-02.json` | 95,313 | `d15f15cc4c6e8b54e726fade35637326b3bcd9b3a490b0785e7ad6920d9c4c3c` | Filtered target universe (7,987 symbols) |
| `alpaca_daily_dec2023.json` | 84,409,548 | `8a5612d7beac2e10fa7f1f99c0addcd0186718def9e85821b11a7656c1afd4e6` | Raw Alpaca daily bars (80 batches, 80 pages) |

---

## 6. Provider Resource Consumption & Provenance

- **Alpaca Total Logical Calls:** `80` (Phase 2 daily bars only).
- **Alpaca Total HTTP Pages:** `80`.
- **Alpaca Retries / 429s:** `0`.
- **Massive HTTP Pages:** `12`.
- **Total Provider HTTP Pages:** `92` (Ceiling limit: `5,000`).
- **Total Elapsed Runtime:** `219.78 seconds`.
- **Storage Consumption:** `88,609,308 bytes` (~88.6 MB, Bound: `2,147,483,648 bytes`).

---

## 7. Governance & Production Safeguards

- **Strategy Simulation / Backtest:** Strictly forbidden and not executed. Zero trade simulations, orders, fills, PnL, win rates, or Sharpe ratios were calculated.
- **Full-Year 2024 Acquisition:** Quarantined and not executed.
- **2025 Validation / 2026 Holdout Partitions:** Strictly unopened and quarantined.
- **External Strategy Retention Principle:** Under Principle B, the Stocks-in-Play 5-minute ORB strategy remains an authorized permanent external research candidate regardless of TradeX independent evaluation outcomes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly verified.

---

## 8. Recommended Next Steps

1. **Acknowledge Implementation Defect:** Formally record the `INVALID_CORR_003_IMPLEMENTATION` disposition for task `DAYTRADE-003D-CORR-003`.
2. **Narrow Correction Task (`DAYTRADE-003D-CORR-004`):**
   - Correct the `time` import collision in `scripts/research/daytrade_003d_corr_003_pilot.py` by using `from datetime import time as dt_time`.
   - Add a mocked integration test executing `run_corr_003_live_pilot` through all 5 phases with synthetic provider clients to prevent script-boundary regressions.
   - Establish a new pre-live frozen commit SHA ($F$).
   - Obtain separate Gary Yang authorization ($A$) before any subsequent one-shot historical feasibility pilot run.
