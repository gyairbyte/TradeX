# R7 PIT Operational Universe Selection & Verification (MVP-ARCH-001-R7-PIT-STATUS-IMPL-C)

## 1. Executive Summary & Authorization

Gary Yang explicitly approved the selection of **Candidate C — `candidate-dow30-sector-etfs`** on **2026-09-18** as TradeX's initial operational point-in-time (PIT) universe.

Candidate B (`candidate-dow30`) is formally recorded as `not_selected`.

This document records the repository implementation of PR C's operational universe package:
- Canonical Manifest Contract v2 operational universe creation under `docs/product/manifests/pit-universe-2026-09-21-v1.json`;
- Deterministic Windows scheduler management script `scripts/manage_pit_scheduler.ps1`;
- Operational documentation updates in `docs/product/R7-PIT-OPERATIONS.md`;
- Governance and project tracker updates.

### Authorization Boundaries
> [!IMPORTANT]
> - **Operational universe selected:** `true`
> - **Scheduler assets authorized:** `true`
> - **Scheduler installed:** `false`
> - **Scheduler enabled:** `false`
> - **Live provider calls performed in this PR:** `false`
> - **Approved production strategies:** `APPROVED_PRODUCTION_STRATEGIES == ()` (empty)
> - **Live scheduler installation/enabling:** Requires a separate explicit Gary action after PR review and merge.

The selected universe is strictly an **operational data-capture universe** and does **not** constitute an approved trading strategy, ranking rule, or strategy promotion.

---

## 2. Canonical Universe Specification

- **Universe ID:** `candidate-dow30-sector-etfs`
- **Universe Version:** `2026-09-21-v1`
- **Effective Date:** `2026-09-21` (first intended trading date post-selection)
- **Canonical Manifest Path:** `docs/product/manifests/pit-universe-2026-09-21-v1.json`
- **Contract Version:** `2`
- **Symbol Count:** 45 total (30 corporate equities, 15 broad-market / sector ETFs)

### Constituent Breakdown & Applicability
- **Corporate Equities (30 symbols):**
  `AAPL`, `AMGN`, `AMZN`, `AXP`, `BA`, `CAT`, `CRM`, `CSCO`, `CVX`, `DIS`, `GS`, `HD`, `HON`, `IBM`, `JNJ`, `JPM`, `KO`, `MCD`, `MMM`, `MRK`, `MSFT`, `NKE`, `NVDA`, `PG`, `SHW`, `TRV`, `UNH`, `V`, `VZ`, `WMT`
  - `earnings`: `"required"`
  - `reference`: `"required"`
- **ETFs (15 symbols):**
  `DIA`, `IWM`, `QQQ`, `SPY`, `XLB`, `XLC`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLRE`, `XLU`, `XLV`, `XLY`
  - `earnings`: `"not_applicable"`
  - `reference`: `"required"`

Applicability is fully materialized per symbol in the manifest. No symbol-name heuristics, provider-derived applicability, or runtime inference are used.

### Cryptographic Hashes
- **Universe Hash (`universe_hash`):**
  ```text
  83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29
  ```
  (Identical to the frozen Candidate C research artifact hash from `MVP-ARCH-001-R7-PIT-001C2-READINESS-A`.)
- **Manifest Hash (`manifest_hash`):**
  ```text
  4eee8a5da39c74db499b6f644f6891d61f6a30b0f98d95b53445b12929c9dedb
  ```
  (Computed deterministically over Contract v2 material fields including sorted per-symbol applicability.)

---

## 3. Capacity Verification

Capacity estimation under Massive free-tier rate limiting (`DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS = 12.1`):

| Metric | Value |
|---|---|
| Symbol Count ($N$) | 45 |
| Minimum Reference Requests ($N$) | 45 |
| Maximum Reference Requests ($2N$) | 90 |
| Minimum Reference Pacing Floor | 532.4 seconds (~8.87 minutes) |
| Maximum Reference Pacing Floor | 1076.9 seconds (~17.95 minutes) |

---

## 4. Windows Scheduler Management Asset

Implemented in `scripts/manage_pit_scheduler.ps1`:
- **Scheduled Jobs:**
  - `TradeX PIT Morning`: 09:00 America/New_York (market open context)
  - `TradeX PIT Evening`: 20:30 America/New_York (post-market close context)
- **Execution Target:** `uv run python -m tradex.pit.ops run-slot --slot <morning|evening> --universe-file docs/product/manifests/pit-universe-2026-09-21-v1.json`
- **Actions:**
  - `Validate`: Safe, non-mutating check of host timezone (`Eastern Standard Time`), project root, `uv` executable, and manifest validity.
  - `Status`: Inspects registration and state of the two tasks via `Get-ScheduledTask`.
  - `Install`: Registers the two tasks (requires human execution post-merge; not executed in this PR).
  - `Remove`: Safely removes the two registered TradeX tasks without affecting unrelated tasks.
- **Fail-Closed Timezone Check:** Fails if host timezone is not `Eastern Standard Time` to ensure 09:00 and 20:30 correspond exactly to America/New_York with proper DST handling.

---

## 5. Decision Record & Invariants

```json
{
  "task_id": "MVP-ARCH-001-R7-PIT-STATUS-IMPL-C",
  "decision_status": "gary_approved",
  "approved_by": "Gary Yang",
  "approved_on": "2026-09-18",
  "selected_candidate": "C",
  "selected_universe": "candidate-dow30-sector-etfs",
  "selected_universe_version": "2026-09-21-v1",
  "effective_from": "2026-09-21",
  "candidate_b_status": "not_selected",
  "candidate_c_status": "selected",
  "operational_universe_selected": true,
  "scheduler_assets_authorized": true,
  "scheduler_installed": false,
  "scheduler_enabled": false,
  "live_provider_calls_performed": false,
  "schema_version": 8,
  "approved_production_strategies": []
}
```
