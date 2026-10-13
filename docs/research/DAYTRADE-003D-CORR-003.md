# DAYTRADE-003D-CORR-003
# ORB Provider Integrity, Offline Replay, and Stage-B Validation

## 1. Executive Summary & Authoritative Disposition

- **Task ID:** `DAYTRADE-003D-CORR-003`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Pilot Date:** `2024-01-02`
- **Base Commit:** `4b1d7084d5d8c91ef10fffbc1f7169de43bfcd0a` (merged PR #110)
- **Proposed Branch:** `antigravity/daytrade-003d-corr-003-integrity-replay`
- **Pre-Live Implementation Freeze Provenance:**
  - Initial candidate freeze: `124206b73bc3ccb5783c422439bedb7bd5c1c0f8`
  - Interim heads: `640608cce14d12189bbf3760c924a15d9e1df635` (module-scope import safety fix), `7a20805d87201224f6f99ca56d521463fcf837eb` (first review resolution).
  - Prospective Pre-Live Freeze ($F$): Established on the final audited implementation commit of this PR, prior to Gary Yang's separate authorization commit ($A$).
- **Classification:** Research-only methodology and data-integrity correction. No production trading changes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Permanent Research Candidate Retention (Principle B):** The published Stocks-in-Play 5-minute Opening Range Breakout strategy (Zarattini et al., 2024) remains a permanent externally supported research candidate.
- **Historical Disposition Invariance:** Preserves the frozen January 2, 2024 pilot results and authoritative `INVALID_CORR_002_IMPLEMENTATION` disposition.
- **Live Execution Gate Status:** **STRICTLY LOCKED**. No live provider calls or live pilot reruns are executed. Delivering draft PR with verified synthetic tests and deterministic offline replay, stopping at the live execution gate pending Gary Yang's explicit authorization.

---

## 2. Material Deficiencies & Bounded Resolutions

This methodology correction addresses and resolves the material deficiencies identified in DAYTRADE-003D-CORR-002 and the subsequent independent reviews on PR #112:

### Blocker 1: Satisfiable Two-Commit Freeze & Authorization Contract
- **Deficiency:** Requiring `git HEAD == expected_sha` in the freeze check while also requiring a committed authorization record embedded with that same SHA created an unsatisfiable circular dependency, because committing the authorization record necessarily changes `HEAD`.
- **Resolution:** Implemented a satisfiable two-commit workflow in [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py):
  1. **Audited Freeze Commit $F$ (`expected_sha`):** Immutable code, test, and specification freeze.
  2. **Authorization Commit $A$:** Separate commit added only after explicit approval by Gary Yang, containing the tracked authorization file [`docs/research/authorizations/DAYTRADE-003D-CORR-003-AUTHORIZATION.json`](../../docs/research/authorizations/DAYTRADE-003D-CORR-003-AUTHORIZATION.json) with `frozen_implementation_sha == F`.
  3. **Ancestry & Drift Invariant:** `check_pre_live_code_freeze` verifies that $F$ is an ancestor of `HEAD` ($A$) via `git merge-base --is-ancestor`, enforces zero file modifications in `tradex/`, `scripts/`, `tests/`, and `docs/research/specs/` between $F$ and $A$, and requires a completely clean working tree at $A$.
  4. **Authorization Record Validation:** `check_pilot_authorization` verifies JSON schema, task ID, pilot date, freeze SHA match, run scope `ONE_SHOT_PILOT_JAN_2_2024`, and ensures the authorization record is tracked and unmodified in git.

### Blocker 2: Raw Provider Payload Integrity & Concatenation Parity
- **Deficiency:** Provider payloads were insufficiently checked. In `DatasetAlpacaClient`, a `bars` dictionary containing a null or non-list symbol entry could be silently converted to `[]` and marked completed. In `validate_provider_batch_response`, raw-page member shapes were not checked and raw page bars were not verified to match aggregated `bars_by_symbol`.
- **Resolution:**
  - In [`alpaca_client.py`](../../tradex/research/intraday_dataset/alpaca_client.py): strictly validates that `data["bars"]` is a dictionary, every symbol entry is a list of bar dictionaries, and immediately halts pagination with `safe_error = "malformed_page_payload"` and `pagination_complete = False` on schema violations. Preserves legitimate empty completed responses (`{"bars": {}}` or `{"bars": {"AAPL": []}}`) as valid with `safe_error = "none"`.
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `validate_provider_batch_response` validates raw page schema (valid dict with `bars` dictionary mapping symbols to lists of dicts), concatenates all raw-page symbol bars, and enforces strict exact equality between raw-page bars and aggregated `bars_by_symbol`. Fails closed with `PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD` on any disparity.

### Blocker 3: Actual Request Provenance & Stage-Specific PIT Parameters
- **Deficiency:** `_verify_request_params_consistency` only checked `symbols` if it was a Python list, allowing contradictory comma-separated string parameters (e.g., `"symbols": "AAA,ROGUE"` as produced by real `get_bars()`) to bypass validation. Stage-specific PIT query parameters and token sequence hashes were not fully verified in replay.
- **Resolution:**
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `_verify_request_params_consistency` handles both comma-separated strings and lists, enforcing exact symbol set parity against `symbols_requested`.
  - Enforces stage-specific expected parameters in replay:
    - Phase 2 Daily: `timeframe="1Day"`, `feed="sip"`, `adjustment="raw"`, `asof="2024-01-02"`, `start="2023-12-01T00:00:00Z"`, `end="2023-12-29T23:59:00Z"`.
    - Phase 3 Current OR: `timeframe="1Min"`, `feed="sip"`, `adjustment="raw"`, `asof="2024-01-02"`, `start="2024-01-02T14:30:00Z"`, `end="2024-01-02T14:34:59Z"`.
    - Phase 3 Prior OR: `timeframe="1Min"`, `feed="sip"`, `adjustment="raw"`, `asof="2024-01-02"`, matching session window for each of the 14 lookback dates.
    - Phase 5 Stage B: `timeframe="1Min"`, `feed="sip"`, `adjustment="raw"`, `asof="2024-01-02"`, `start="2024-01-02T14:35:00Z"`, `end="2024-01-02T20:59:59Z"`.
  - Enforces `token_sequence_sha256` matching the SHA-256 hash of concatenated `token_hashes`.

### Blocker 4: Prospective Resource Ceilings & True One-Shot Safeguards
- **Deficiency:** Resource checks ran only after entire phases, meaning a batch-size of 1 could exceed the 5,000-page limit during Phase 2 before any check. `get_bars()` did not cap per-call pagination to remaining budget. The one-shot guard only checked for `manifest_<date>.json`, allowing interrupted runs with partial artifacts to be restarted and overwrite evidence.
- **Resolution:**
  - In [`scripts/research/daytrade_003d_corr_003_pilot.py`](../../scripts/research/daytrade_003d_corr_003_pilot.py):
    - Prospective Page Check: Before each `alpaca_client.get_bars(...)` call, calculates `remaining_pages = MAX_PILOT_PAGES_LIMIT - total_pages_used` and passes `max_pages=min(100, remaining_pages)`. Halts immediately if budget would be exceeded.
    - Prospective Storage Check: Before writing any artifact, verifies `current_storage_bytes + len(bytes_to_write) <= MAX_PILOT_STORAGE_BYTES_LIMIT`.
    - Durable Run Marker: Writes `.pilot_run_lock_<date>.json` immediately upon startup.
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `check_one_shot_pilot_guard` fails closed if `manifest_<date>.json` exists, if `.pilot_run_lock_<date>.json` exists, or if any `.json` artifacts already exist in the output directory, ensuring partial run evidence is preserved and cannot be overwritten.

### Third Independent Review Deficiencies & Resolutions

#### Finding 1: Durable Run Lock Marker in Replay & Storage Layout
- **Deficiency:** The live runner created `.pilot_run_lock_2024-01-02.json` but omitted it from manifest `artifacts_info`. Replay verification strictly failed closed on unlisted extra files (`Unlisted extra file`), causing any valid live producer run to fail replay.
- **Resolution:**
  - In [`scripts/research/daytrade_003d_corr_003_pilot.py`](../../scripts/research/daytrade_003d_corr_003_pilot.py): includes `.pilot_run_lock_2024-01-02.json` in `artifacts_info` before writing `manifest_2024-01-02.json`.
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `verify_replay_manifest` verifies lock marker SHA-256 and byte size against the manifest, validates its schema and fields via `validate_run_lock_marker`, and accepts manifested lock markers. Rejects unlisted or tampered locks.

#### Finding 2: Atomic One-Shot Lock Acquisition
- **Deficiency:** Running `check_one_shot_pilot_guard` followed non-atomically by `write_bytes` permitted concurrent processes to race and overwrite locks and artifacts.
- **Resolution:**
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `acquire_atomic_pilot_run_lock` uses atomic exclusive file creation (`open(..., 'xb')` / `O_CREAT | O_EXCL`). Fails closed on collision with `RuntimeError` while preserving existing markers and partial evidence intact. Tested via multi-threaded concurrent race simulation.

#### Finding 3: Deliberate Post-Freeze Allowlist
- **Deficiency:** Narrow denylist permitted drift in dependency files (`pyproject.toml`, `uv.lock`), workflows, or configuration between freeze commit $F$ and authorization commit $A$.
- **Resolution:**
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): replaced denylist with `is_allowed_post_freeze_drift`. Strictly restricts post-freeze drift to the approved Gary Yang authorization record and explicitly non-executable documentation (`.md`, `.txt`, `.rst` under `docs/` and root docs). Fails closed on tracked drift to executable code, dependencies (`pyproject.toml`, `uv.lock`), workflows, or configuration.

#### Finding 4: Assert Completed Raw-Page Evidence Presence & Coherence
- **Deficiency:** Completed HTTP 200 requests with `raw_pages=[]` could pass validation if aggregate bars were empty, risking accepting invented no-print evidence without raw provider proof.
- **Resolution:**
  - In [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py): `validate_provider_batch_response` with `require_raw_pages=True` requires non-empty `raw_pages` for completed HTTP 200 responses, verifies `len(raw_pages) == page_count`, enforces per-page `http_status == 200`, and verifies terminal pagination tokens are fully consumed. Preserves legitimately completed empty pages (`{"bars": {}}` or `{"bars": {"AAPL": []}}`).

### Fourth Independent Review Deficiencies & Resolutions

#### Finding: Runtime Dependency and Environment Reproducibility Gate
- **Deficiency:** While repository code files were cryptographically locked at freeze commit $F$, `uv.lock` is uncommitted in `.gitignore`. A modified or re-resolved `uv.lock` or mutated runtime package environment on the execution host could execute the live pilot under different dependency versions than those frozen and tested, bypassing Git-based freeze checks unnoticed.
- **Resolution (Option B Implemented):**
  - **Preregistered Environment Specification:** Authored immutable specification [`docs/research/specs/DAYTRADE-003D-CORR-003-ENVIRONMENT.json`](../../docs/research/specs/DAYTRADE-003D-CORR-003-ENVIRONMENT.json) with cryptographic hash `1a76b92f9667bb8503517687aae2b2356ba9c0124a7ff735adccff42ba666a80`. It records:
    - Python major/minor version (`3.11`).
    - The audited SHA-256 hash of repository `uv.lock` (`ec533f6e15ca61c360f936083079a9fb21407a0ef082a01e04f799687e95b01f`).
    - 19 pinned core runtime packages (`pandas==3.0.6`, `numpy==2.4.6`, `exchange-calendars==4.13.2`, `pytz==2026.5`, `ta==0.11.0`, etc.).
    - 3 pinned live provider packages (`alpaca-py==0.44.0`, `pydantic==2.14.1`, `pydantic-core==2.50.1`).
  - **Hard Execution Gate (`check_runtime_environment_freeze`):** Added to [`corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py). Before loading credentials or invoking provider endpoints, it enforces:
    1. Spec file existence and SHA-256 match against `LOCKED_003D_CORR_003_ENV_SPEC_SHA256`.
    2. Exact Python 3.11 runtime version.
    3. Direct on-disk SHA-256 verification of `uv.lock` against the frozen hash (failing closed even though `uv.lock` is ignored by Git).
    4. Exact package versions via `importlib.metadata.version()`.
  - **Pre-Live Freeze Integration:** Integrated into `check_pre_live_code_freeze` and registered in `verify_upstream_spec_hashes`.
  - **CLI Environment Inspection:** Added `check-env` subcommand in [`scripts/research/daytrade_003d_corr_003_pilot.py`](../../scripts/research/daytrade_003d_corr_003_pilot.py) (`python scripts/research/daytrade_003d_corr_003_pilot.py check-env --require-live-providers`).

---

## 3. Preregistered Specifications & Upstream Hashes

All seven specifications are verified via SHA-256:

| Specification Document | Path | SHA-256 Hash | Status |
| :--- | :--- | :--- | :--- |
| **003B Specification** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` | Immutable Verified |
| **003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` | Immutable Verified |
| **003D Data Feasibility** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` | Immutable Verified |
| **003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` | Immutable Verified |
| **003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` | Immutable Verified |
| **003D-CORR-003 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-v1.json` | `2f86d1231f55180b8fe4f65832cde8783e7c6058788a1e98130353b5822a1cdb` | Locked Preregistered |
| **003D-CORR-003 Environment Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-ENVIRONMENT.json` | `1a76b92f9667bb8503517687aae2b2356ba9c0124a7ff735adccff42ba666a80` | Locked Preregistered |

---

## 4. Architecture & Implementation Summary

### 4.1 Python Modules & Scripts
- [`tradex/research/intraday_dataset/alpaca_client.py`](../../tradex/research/intraday_dataset/alpaca_client.py):
  - Validates `data["bars"]` structure and symbol bar lists; breaks on malformed pages with `safe_error = "malformed_page_payload"`.
  - Supports `max_pages` ceiling, pagination cycle detection, and token preservation.
  - Backward-compatible kwargs `include_raw_bars: bool = False, include_raw_pages: bool = False`.
- [`tradex/research/daytrade_orb/corr_003_pilot.py`](../../tradex/research/daytrade_orb/corr_003_pilot.py):
  - Implements provider integrity checking, raw-page parity validation, Stage-B auditing, two-commit freeze/authorization checking, prospective one-shot guards, offline replay engine, and runtime environment verification.
- [`scripts/research/daytrade_003d_corr_003_pilot.py`](../../scripts/research/daytrade_003d_corr_003_pilot.py):
  - Multi-command CLI runner:
    - `replay`: fully offline deterministic replay subcommand.
    - `pilot`: bounded live pilot execution subcommand gated behind explicit authorization (`--authorize-live`) and pre-live commit SHA verification (`--pre-live-sha`).
    - `check-env`: inspects runtime environment and verifies against frozen specification without making network calls.
- [`tests/research/daytrade_orb/test_corr_003_integrity_replay.py`](../../tests/research/daytrade_orb/test_corr_003_integrity_replay.py):
  - Comprehensive suite of 91 deterministic tests covering all unit, synthetic, and integration paths without network access.

### 4.2 Replay Persistence Schema
Artifacts stored under private storage directory:
1. `massive_reference_<date>.json`: Universe snapshot rows from Massive Reference API.
2. `universe_<date>.json`: Filtered target universe classification summary.
3. `alpaca_daily_dec2023.json`: Raw daily bar batches across canonical target universe.
4. `alpaca_current_or_<date>.json`: Raw 09:30–09:34 ET minute bar batches for target date.
5. `alpaca_prior_or_14sessions_<date>.json`: Raw 14-session prior opening range batches.
6. `top_20_selection_<date>.json`: Top-20 ranking and candidate selection records.
7. `alpaca_stage_b_<date>.json`: Raw 09:35–15:59 ET minute bar batches for actionable symbols.
8. `manifest_<date>.json`: Cryptographic manifest binding all artifacts by SHA-256 and byte size.

---

## 5. Verification Results

### 5.1 Test Suite Execution
- **CORR-003 Synthetic & Offline Tests:** 91 passed ([`tests/research/daytrade_orb/test_corr_003_integrity_replay.py`](../../tests/research/daytrade_orb/test_corr_003_integrity_replay.py)).
  - Upstream spec hash verification: PASSED
  - Strategy registry empty invariant: PASSED
  - HTTP error, truncated pagination, unexpected symbol, malformed timestamp, duplicate timestamp, out-of-session bar, invalid OHLCV detection: PASSED
  - Client multi-page pagination advance, max pages hard-stop token preservation, and cycle detection: PASSED
  - Distinction between provider failure and verified completed no-print: PASSED
  - Stage-B usability with valid sparse minutes and 15:59 liquidation bar: PASSED
  - Stage-B unfitness on missing 15:59 bar, provider failure, duplicates, out-of-session bars: PASSED
  - Complete deterministic offline fixture replay: PASSED
  - Missing artifact, tampered artifact, missing manifest, tampered manifest fail-closed: PASSED
  - Strict manifest schema, unlisted extra file rejection, invalid size/hash rejection: PASSED
  - Daily provider failure propagation to `BLOCKED_PROVIDER_DATA_INTEGRITY`: PASSED
  - Two-commit freeze/authorization workflow, code drift detection, non-ancestor detection, dirty worktree rejection: PASSED
  - Raw payload schema validation, null/non-list bars rejection, raw-to-aggregated parity enforcement: PASSED
  - Realistic string-valued symbols verification, feed/timeframe/asof/window verification, token sequence hash parity: PASSED
  - End-to-end mocked acquisition-to-replay integration: PASSED
  - Durable run marker lock guard, partial artifact restart rejection, prospective resource limit enforcement: PASSED
  - Durable run lock marker manifest verification and unlisted/corrupted marker rejection: PASSED
  - Atomic one-shot lock acquisition and concurrent race collision rejection: PASSED
  - Deliberate post-freeze allowlist enforcement (rejecting pyproject.toml, uv.lock, workflows): PASSED
  - Completed raw-page presence & coherence (rejecting empty raw pages, page count mismatch, non-200, unconsumed pagination tokens): PASSED
  - Full live producer layout to offline replay end-to-end integration: PASSED
  - Runtime environment freeze specification matching active Python 3.11 and package versions: PASSED
  - Pre-live execution gate rejecting modified/re-resolved ignored uv.lock on disk: PASSED
  - Runtime environment freeze rejecting package version mismatch, missing package, or Python version mismatch: PASSED
  - Clean Git F->A path with frozen environment and Gary authorization passes all guards: PASSED
  - CLI check-env subcommand clean verification: PASSED
- **Full ORB Test Suite:** 210 passed ([`tests/research/daytrade_orb/`](../../tests/research/daytrade_orb/)).
- **Shared Intraday Dataset Test Suite:** 43 passed ([`tests/research/intraday_dataset/`](../../tests/research/intraday_dataset/)).
- **Import Safety Verification:** 14 passed in 14.29s ([`tests/config/test_import_safety.py`](../../tests/config/test_import_safety.py)).
- **Linter Check:** `uv run ruff check` passed cleanly with 0 errors across all modified and test files.

### 5.2 Execution Gate Verification
- Attempting to run `python scripts/research/daytrade_003d_corr_003_pilot.py pilot` without `--authorize-live` immediately halts with exit code 1:
  ```text
  [FATAL] Live execution gate active: Gary Yang has not granted live pilot authorization.
  Deliver draft PR with passing offline replay tests and stop at execution gate.
  ```

---

## 6. Governance Safeguards & Boundaries

- **Strategy Invariance:** Zero strategy modifications, parameter changes, indicator alterations, or portfolio rule adjustments.
- **Production Isolation:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Simulation Invariance:** Zero backtesting, trade simulation, order fills, PnL calculations, or win-rate analyses performed.
- **Historical Immutability:** Specs `DAYTRADE-003B-ORB-v1.json`, `DAYTRADE-003C-ORB-RESOLUTION-v1.json`, `DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json`, `DAYTRADE-003D-CORR-001-v1.json`, and `DAYTRADE-003D-CORR-002-v1.json` are byte-for-byte unchanged.
- **Live Execution Gate:** Strictly locked. Live provider execution requires explicit written authorization from Gary Yang following independent review of the draft PR.
