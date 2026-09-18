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
- **Fail-Closed Execution Guard**: `run_pit_slot` checks `contract_version != 1` immediately at entry before any trading-day, slot-time, or effective-from gates, failing closed with zero provider calls and zero DB writes until PR B.
- **Cross-Version Conflict Guard**: `(capture_date, slot)` runs cannot mix contract v1 and v2.
- **Runtime Capture Pinning**: Write execution is pinned to `PIT_CAPTURE_WRITE_CONTRACT_VERSION = 1` until PR B. Premature v2 runtime capture attempts fail closed.
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
     - **Operational Health**: Evaluates the latest terminal attempt (`SUCCEEDED`, `PARTIAL`, `FAILED`). A successful retry supersedes an earlier failed or in-progress attempt. Conversely, if a later retry fails, the slot is evaluated as degraded/failed to truthfully reflect current operational reality.
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
