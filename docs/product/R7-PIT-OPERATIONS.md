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

## Schema Invariant

- Schema version: `v7` (unchanged by C1)
- No new tables, no migrations
- `APPROVED_PRODUCTION_STRATEGIES == ()` (unchanged)
