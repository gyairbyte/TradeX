# R7-PIT-OPERATIONS: Deterministic PIT Operations Runner

> **MVP-ARCH-001-R7-PIT-001C1** — Gary-approved 2026-09-02

---

## Purpose

This document describes the operational layer added in `MVP-ARCH-001-R7-PIT-001C1`. It operationalizes the already-merged prospective PIT foundations (001A earnings, 001B reference) without installing an OS scheduler.

**What C1 adds:**
- Versioned, immutable `PITUniverseManifest` contract (JSON file)
- `run_pit_slot`: deterministic runner for both families (earnings → reference, same universe)
- Universe drift guard (fail-closed on hash mismatch)
- Family failure isolation (reference runs even if earnings fails)
- `get_pit_slot_health`: fully read-only health inspection
- `estimate_capacity`: pacing-floor math, no network
- CLI: `validate-universe`, `run-slot`, `health` subcommands

**What C1 does NOT do:**
- Install an OS scheduler (no schtasks, cron, systemd, launchd, GitHub Actions scheduling)
- Select or activate a production universe
- Perform automatic watchlist/preset/scanner universe resolution
- Modify the active schema (remains v7)
- Promote any strategy (`APPROVED_PRODUCTION_STRATEGIES == ()`)

---

## Universe Manifest Contract

The manifest is a JSON file with the following schema (contract_version=1):

```json
{
  "contract_version": 1,
  "universe_id": "my-universe",
  "universe_version": "v1",
  "effective_from": "2026-01-01",
  "symbols": ["AAPL", "MSFT", "NVDA"],
  "description": "Optional human-readable description."
}
```

### Fields

| Field | Type | Required | Constraints |
|---|---|---|---|
| `contract_version` | integer | Yes | Must be `1` |
| `universe_id` | string | Yes | `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` |
| `universe_version` | string | Yes | Non-empty |
| `effective_from` | string | Yes | ISO date `YYYY-MM-DD` |
| `symbols` | array of strings | Yes | Non-empty; normalized (trimmed, uppercased, sorted, deduplicated) at load time |
| `description` | string | No | Excluded from manifest_hash |

### Manifest Hash

The `manifest_hash` is a SHA-256 hash of the **material fields** (deterministically serialized):
- `contract_version`, `effective_from`, `symbols`, `universe_id`, `universe_version`

Non-material fields (`description`, file path, file mtime) are excluded.

### Universe Hash

The `universe_hash` is a SHA-256 hash of the comma-joined sorted normalized symbols. This is the same hash used by the earnings and reference capture services, guaranteeing the same-universe-across-families invariant.

---

## Trading-Day Policy

The `run_pit_slot` and `get_pit_slot_health` functions apply the following policy:

| Condition | Result |
|---|---|
| `is_trading_day(current_ny_date) == False` | `not_due` — zero writes, zero provider calls |
| `current_utc < scheduled_for` | `not_due` — zero writes, zero provider calls |
| `current_ny_date < manifest.effective_from` | `failed` — manifest is future-dated |
| Universe hash conflict with existing runs | `failed` — zero provider calls, zero new writes |
| Both families complete with SUCCEEDED status | `succeeded` |
| One family fails, other succeeds | `degraded` |
| Both families fail | `failed` |

**Scheduled slot times** (America/New_York):
- `morning`: 09:00 ET
- `evening`: 20:30 ET

---

## Universe Drift Guard

Before any provider call or DB write, `run_pit_slot` inspects all existing runs for `(capture_date, slot)`:

- If any existing run has a different `universe_hash` → raises `PITOperationalUniverseConflictError` (caught and returned as `failed` result)
- Zero new provider calls or writes are performed on conflict
- Changing the operational universe for a date/slot requires an explicit future operational decision

---

## Family Failure Isolation

```
Earnings capture (family 1)
  └── Exception → captured, error_detail set, continue to reference
Reference capture (family 2)
  └── Always attempted regardless of earnings outcome
```

This ensures a reference capture failure never prevents earnings from completing and vice versa.

---

## Capacity Estimation

`estimate_capacity(manifest)` computes deterministic pacing-floor math:

| Field | Formula |
|---|---|
| `symbol_count` | N |
| `minimum_reference_requests` | N (one active lookup per symbol) |
| `maximum_reference_requests` | 2N (active + inactive fallback per symbol) |
| `minimum_pacing_floor_seconds` | max(N - 1, 0) × `DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS` |
| `maximum_pacing_floor_seconds` | max(2N - 1, 0) × `DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS` |

**Current `DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS` = 12.1 s** (~5 requests/minute free-tier pacing).

Because the rate limiter enforces a minimum delay *between* requests rather than before the first request, the pure pacing floor for $R$ requests is $\max(R - 1, 0) \times \text{interval}$.

These are floor estimates only. Actual completion time excludes provider/network latency, retries, process startup, SQLite overhead, and other delays.


---

## Health States

| Status | Meaning |
|---|---|
| `not_due` | Non-trading day OR current time before slot time |
| `healthy` | Both families have ≥1 terminal SUCCEEDED run with matching universe hash |
| `degraded` | Both families have terminal evidence but not both succeeded |
| `missing` | Slot is due but one or both families have zero runs |
| `incomplete` | At least one run is still in STARTED state |
| `universe_conflict` | At least one run has a different universe_hash than the manifest |

---

## CLI Reference

```
python -m tradex.pit.ops <subcommand> [options]
```

### `validate-universe`

Validate a manifest JSON file and report capacity. No network calls. No DB writes.

```bash
python -m tradex.pit.ops validate-universe --universe-file path/to/universe.json
```

**Exit codes:** 0 = valid, 1 = invalid

### `run-slot`

Run deterministic PIT slot capture for both earnings and reference families.

```bash
python -m tradex.pit.ops run-slot \
  --slot evening \
  --universe-file path/to/universe.json \
  [--db-path path/to/signals.db]
```

**Exit codes:** 0 = succeeded/not_due, 2 = degraded, 1 = failed

### `health`

Read-only PIT slot health inspection. No provider calls. No DB writes.

```bash
python -m tradex.pit.ops health \
  --universe-file path/to/universe.json \
  [--date 2026-01-02] \
  [--slot morning|evening] \
  [--db-path path/to/signals.db]
```

**Exit codes:** 0 = healthy/not_due, 2 = degraded/missing/incomplete, 1 = universe_conflict/error

---

## C1/C2 Boundary

**C1 (this task):**
- Implements the manifest contract and operational layer infrastructure
- No active production universe is selected
- CLI tools are available but require an explicit `--universe-file` argument

**C2 (unauthorized, separate Gary approval required):**
- OS scheduler installation (schtasks, cron, systemd, etc.)
- Active production universe selection
- Automatic invocation without explicit manifest path

---

---

## Schema & Contract Evolution

### Schema Version
- **Schema v8**: Introduced in `MVP-ARCH-001-R7-PIT-STATUS-IMPL-A` via an atomic 14-step table rebuild.
- Prior Schema v7 data is fully preserved with exact row count verification across all 4 PIT tables.
- Rebuild execution sequence strictly adheres to:
  1. Open dedicated connection to database
  2. `PRAGMA foreign_keys = OFF` executed strictly *before* `BEGIN TRANSACTION`
  3. Verify `PRAGMA user_version == 7`
  4. Query source row counts across all 4 PIT tables
  5. Create temporary `_v8` tables (`pit_capture_runs_v8`, `pit_earnings_snapshots_v8`, `pit_reference_capture_runs_v8`, `pit_reference_snapshots_v8`)
  6. Copy source data verbatim with Schema v8 column backfills
  7. Verify destination row counts equal source row counts
  8. Drop old tables
  9. Rename `_v8` tables to canonical table names
  10. Recreate indexes
  11. `PRAGMA foreign_key_check` asserting zero violations
  12. `PRAGMA user_version = 8`
  13. `COMMIT`
  14. `PRAGMA foreign_keys = ON`, close connection

### Manifest Contract v2 Primitives
- **Contract Version 2**: Requires the normative per-symbol `applicability` mapping where each symbol declares both `earnings` and `reference` families:
  ```json
  {
    "contract_version": 2,
    "universe_id": "candidate-c",
    "universe_version": "v1",
    "effective_from": "2026-09-01",
    "symbols": ["AAPL", "MSFT", "SPY"],
    "description": "Example manifest with per-symbol applicability",
    "applicability": {
      "AAPL": {
        "earnings": "required",
        "reference": "required"
      },
      "MSFT": {
        "earnings": "required",
        "reference": "required"
      },
      "SPY": {
        "earnings": "not_applicable",
        "reference": "required"
      }
    }
  }
  ```
- **Deep Immutability**: `PITUniverseManifest.applicability` enforces recursive immutability using `types.MappingProxyType` for both outer and inner mappings, preventing in-memory mutations post-construction.
- **Material Hashing**: For contract v2 manifests, `manifest_hash` commits to normalized, sorted per-symbol applicability declarations, while `universe_hash` remains strictly the SHA-256 of the symbol list.
- **PR-A Transition Guard**: Before PR B, `run_pit_slot` rejected contract-v2 execution. PR B supersedes that temporary guard and explicitly dispatches v1 or v2 runtime execution according to the supplied manifest contract version.
- **Default Capture Contract**: `PIT_CAPTURE_WRITE_CONTRACT_VERSION = 1` is retained as the legacy/default direct-write contract version, while runner-driven v2 execution explicitly passes `contract_version=2` when a v2 manifest is supplied.
- **Truthful Provenance**: `NOT_APPLICABLE` earnings records persist `observation_origin = 'manifest'`, `applicability_source = 'manifest'`, `provider = NULL`, `provider_call_attempted = 0`, with no fictitious timestamps or provider names.
- `APPROVED_PRODUCTION_STRATEGIES == ()` (unchanged).

### Manifest Contract v2 Runtime Execution & Two-Dimensional Status Semantics (PR B)

Introduced in `MVP-ARCH-001-R7-PIT-STATUS-IMPL-B` on branch `antigravity/mvp-arch-001-r7-pit-status-impl-b`:

1. **Two-Dimensional Status Semantics**:
   - **Operational Health** (`operational_status` / `overall_status`): Tracks capture execution success, scheduling/drift compliance, and process/system failures. Evaluates to `healthy` (exit 0), `degraded` (exit 2), `failed` (exit 1), or `not_due` (exit 0).
   - **Evidence Completeness** (`evidence_completeness` read model): Measures factual market evidence depth across applicable symbols. Categorized into discrete tiers:
     - `complete`: 100% of applicable symbols have known observations (`known_n == applicable_n`). If all symbols are declared `not_applicable`, tier is `complete` and ratio is `1.0`.
     - `partial`: At least one known fact exists, but not all applicable symbols are known (`0 < known_n < applicable_n`).
     - `sparse`: Applicable symbols exist, but zero known facts were obtained (`applicable_n > 0` and `known_n == 0`).
   - **Slot-Level Aggregation Invariant**: The overall slot tier requires all expected families to be `complete` for the slot to be `complete`. If any family is `sparse`, the overall tier is `sparse`, even if pooled completion ratio is high. Pooled ratio is informational only and never masks a sparse family tier.

2. **Multi-Attempt & Retry Reconciliation**:
   - When multiple capture attempts exist for a `(capture_date, slot)`:
     - **Operational Health**: Evaluates the latest terminal attempt (`SUCCEEDED`, `PARTIAL`, `FAILED`). A successful retry supersedes an earlier failed attempt; however, **any matching STARTED run keeps operational health DEGRADED** (`run_in_progress`). A newer terminal retry may supply the evidence-completeness attempt, but does not erase the STARTED operational-health condition. Conversely, if a later retry fails, the slot is evaluated as degraded/failed to truthfully reflect current operational reality.
     - **Evidence Completeness**: Selected from the attempt with maximal evidence across matching runs (`max(matching_runs, key=lambda r: (r.requested_at, r.capture_run_id))`), ensuring completeness reflects the best factual evidence available.

3. **Massive Reference 404 & Exception Handling**:
   - HTTP 404 from Massive/Polygon reference endpoint indicates an endpoint or query error (`MassiveResponseError`), caught per-symbol and recorded truthfully as `ReferenceObservationStatus.ERROR`, incrementing `error_n`. It contributes to `PARTIAL` or `FAILED` terminal run status.
   - This is strictly distinguished from a clean absence (HTTP 200 active with 0 results + HTTP 200 inactive with 0 results), which produces `ReferenceObservationStatus.UNAVAILABLE` and `error_n = 0` (`SUCCEEDED`).
   - Exceptions in the per-symbol loop are caught, sanitized against secrets (`apiKey=[REDACTED]`), and recorded truthfully with request start and end timestamps.

4. **Schema-v8 Limitation around Fatal DB Failures**:
   - Under Schema v8, if SQLite or I/O encounters a fatal failure during runner execution after a run record is created, the active runner catches the failure and returns `operational_status = FAILED` (exit 1).
   - The surviving DB row remains stranded in `STARTED` state with `completed_at = NULL`.
   - Subsequent offline health inspection evaluates any stranded `STARTED` run as `DEGRADED` (`run_in_progress`), because Schema v8 lacks a supervisor/daemon or timeout state machine to transition stranded runs.

5. **Manifest-only Earnings Applicability**:
   - If an equity is declared `not_applicable` in the manifest applicability mapping, the runner skips provider calls entirely (0 calls, `provider = NULL`, `provider_call_attempted = 0`, `observation_origin = 'manifest'`, `applicability_source = 'manifest'`, `not_applicable_n` incremented).
   - No heuristic inference (e.g. ticker name pattern matching) is performed.
   - Reference capture remains universal (`reference: required` for 100% of symbols).

6. **Exact Backward Compatibility with Contract v1**:
   - Manifest v1 executions continue to run with exact legacy keyword signatures, strict all-known operational health rules, and legacy JSON serialization shapes without v2 `evidence_completeness` fields.

---

## Production Operational Universe & Scheduling (PR C)

### 1. Selected Operational Universe (Candidate C)
- **Universe ID:** `candidate-dow30-sector-etfs`
- **Universe Version:** `2026-09-21-v1`
- **Effective From:** `2026-09-21`
- **Canonical Manifest Path:** `docs/product/manifests/pit-universe-2026-09-21-v1.json`
- **Contract Version:** 2
- **Total Symbols:** 45 (30 corporate equities, 15 broad-market / sector ETFs)
- **Applicability:**
  - **Earnings:** 30 corporate equities `required`; 15 ETFs (`DIA`, `IWM`, `QQQ`, `SPY`, `XLB`, `XLC`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLRE`, `XLU`, `XLV`, `XLY`) `not_applicable`.
  - **Reference:** All 45 symbols `required`.
- **Hashes:**
  - `universe_hash`: `83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29`
  - `manifest_hash`: `4eee8a5da39c74db499b6f644f6891d61f6a30b0f98d95b53445b12929c9dedb`

### 2. Intended Operational Schedule
- **Morning Slot:** 09:00 America/New_York (morning / pre-market decision capture)
- **Evening Slot:** 20:30 America/New_York (post-market capture)
- **Windows Timezone Requirement:** `Eastern Standard Time` (handles New York DST transitions).
- **Missed Slot Policy:** No automatic catch-up (`StartWhenAvailable = false`). Missed executions remain visible in health audit.

### 3. Windows Scheduler Management Commands
Script: `scripts/manage_pit_scheduler.ps1`
Dedicated Task Scheduler Path: `\TradeX\`
Ownership Marker: `Managed by scripts/manage_pit_scheduler.ps1`

- **Safe Configuration Validation (Non-mutating):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/manage_pit_scheduler.ps1 -Action Validate
  ```
  Validates host timezone, project root, `uv` presence, and canonical manifest without modifying OS tasks.

- **Status Inspection:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/manage_pit_scheduler.ps1 -Action Status
  ```
  Inspects whether `TradeX PIT Morning` and `TradeX PIT Evening` tasks are registered in the owned `\TradeX\` path.

- **Future Installation (Explicit Gary Action Post-Merge):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/manage_pit_scheduler.ps1 -Action Install
  ```
  Registers the two scheduled tasks in `\TradeX\`. Requires ownership validation, refuses unsafe overwrite (no `-Force`), and performs atomic rollback on failure. (Do not execute until authorized post-merge).

- **Removal / Rollback:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/manage_pit_scheduler.ps1 -Action Remove
  ```
  Safely unregisters the two TradeX scheduled tasks only after verifying the `\TradeX\` path and ownership marker. Refuses removal on conflict.

### 4. Direct Operations Runner & Health Commands
- **Manual Slot Execution:**
  ```bash
  uv run python -m tradex.pit.ops run-slot \
    --slot morning \
    --universe-file docs/product/manifests/pit-universe-2026-09-21-v1.json
  ```
  ```bash
  uv run python -m tradex.pit.ops run-slot \
    --slot evening \
    --universe-file docs/product/manifests/pit-universe-2026-09-21-v1.json
  ```

- **Health Inspection:**
  ```bash
  uv run python -m tradex.pit.ops health \
    --universe-file docs/product/manifests/pit-universe-2026-09-21-v1.json
  ```

### 5. Exit Code Semantics (Contract v2 / PR-B)
- **`run-slot`**:
  - `0 = succeeded or not_due`
  - `2 = degraded (STARTED / PARTIAL behavior)`
  - `1 = failed`
    - either required family terminally FAILED
    - missing family/run
    - universe or manifest conflict
    - fatal/database failure
    - total required-provider failure
- **`health` (Contract v2)**:
  - `0 = healthy or not_due`
  - `2 = degraded`
    - `run_in_progress`
    - `partial_evidence`
  - `1 = failed`
    - `missing_due_family`
    - `universe_conflict`
    - `manifest_conflict`
    - `capture_failed`
    - internal/fatal health failure

*(Note: Legacy Contract-v1 enum values `missing` and `incomplete` returning exit 2 remain strictly for v1 manifest compatibility; under Contract v2, missing due families and failures truthfully return exit 1).*

### 6. Operational Notes & Limitations
- **Credentials:** Credentials (`MASSIVE_API_KEY`, etc.) remain in local `.env` or system environment; never embedded in scheduler commands or repository files.
- **Stranded-STARTED Limitation:** If an unexpected process termination occurs during a run, the record remains in `STARTED` state and offline health reports `degraded` (`run_in_progress`). A subsequent successful retry provides evidence completeness but keeps operational health degraded until reconciled.
- **Strategy Independence:** Production strategy registry remains empty (`APPROVED_PRODUCTION_STRATEGIES == ()`). Point-in-time capture is data infrastructure only.

### 7. Current Activation State

Scheduler activation status:
```text
ACTIVATED_WITH_LOGON_REQUIREMENT
```

- **Activated:** `2026-09-19`
- **TaskPath:** `\TradeX\`
- **Morning:** `09:00 ET` (`TradeX PIT Morning`)
- **Evening:** `20:30 ET` (`TradeX PIT Evening`)
- **Working directory:** `C:\Users\Gary\Projects\TradeX`
- **PIT DB:** `C:\Users\Gary\.tradex\signals.db`
- **Task Principal:** `UserId = Gary`, `LogonType = Interactive`, `RunLevel = Limited`

#### Operational Limitations
- Gary must remain signed into Windows (`LogonType = Interactive`).
- Locking the workstation is acceptable; scheduled tasks will run while locked.
- Signing out prevents execution (`can_run_while_signed_out = false`).
- Machine must be awake (`machine_must_be_awake = true`).
- `StartWhenAvailable = false`, therefore missed captures intentionally do not run late.

*(Note: First scheduled captures have **not yet been observed**; they remain pending for the 2026-09-21 morning and evening slots).*
