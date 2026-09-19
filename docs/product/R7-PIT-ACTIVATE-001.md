# Candidate C PIT Scheduler Operational Activation (MVP-ARCH-001-R7-PIT-ACTIVATE-001)

## 1. Purpose & Activation Summary

This document formally records the operational activation of TradeX's Candidate C Point-in-Time (PIT) scheduler on Windows Task Scheduler following the review and merge of PR C (`MVP-ARCH-001-R7-PIT-STATUS-IMPL-C`, PR #81).

- **Task ID:** `MVP-ARCH-001-R7-PIT-ACTIVATE-001`
- **Activation Status:** `ACTIVATED_WITH_LOGON_REQUIREMENT`
- **Activation Date:** `2026-09-19`
- **Activated By:** Gary Yang
- **Source Main Commit SHA:** `e2f1e37a27e751fc9116c2893e226c83af025cb0`
- **Canonical Repository Root:** `C:\Users\Gary\Projects\TradeX`
- **Canonical Branch:** `main` (clean working tree post-activation)

> [!IMPORTANT]
> The scheduler being active does not constitute a trading-strategy promotion and does not alter signals, scores, weights, thresholds, rankings, or eligibility.
>
> The next operational gate is **first scheduled capture verification**, not additional R7 implementation.

---

## 2. Selected Operational Universe (Candidate C)

- **Universe ID:** `candidate-dow30-sector-etfs`
- **Universe Version:** `2026-09-21-v1`
- **Contract Version:** `2`
- **Total Symbol Count:** 45 (30 corporate equities, 15 broad-market / sector ETFs)
- **Applicability Breakdown:**
  - Corporate Equities (30 symbols): `earnings = required`, `reference = required`
    - `AAPL`, `AMGN`, `AMZN`, `AXP`, `BA`, `CAT`, `CRM`, `CSCO`, `CVX`, `DIS`, `GS`, `HD`, `HON`, `IBM`, `JNJ`, `JPM`, `KO`, `MCD`, `MMM`, `MRK`, `MSFT`, `NKE`, `NVDA`, `PG`, `SHW`, `TRV`, `UNH`, `V`, `VZ`, `WMT`
  - ETFs (15 symbols): `earnings = not_applicable`, `reference = required`
    - `DIA`, `IWM`, `QQQ`, `SPY`, `XLB`, `XLC`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLRE`, `XLU`, `XLV`, `XLY`
  - Total Reference Required: 45 symbols
- **Universe Hash (`universe_hash`):**
  ```text
  83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29
  ```
- **Manifest Hash (`manifest_hash`):**
  ```text
  4eee8a5da39c74db499b6f644f6891d61f6a30b0f98d95b53445b12929c9dedb
  ```

---

## 3. Installed Scheduler Configuration

The scheduler was installed on the canonical workstation using `scripts/manage_pit_scheduler.ps1 -Action Install`:

- **Task Scheduler Path:** `\TradeX\`
- **Ownership Marker:** `Managed by scripts/manage_pit_scheduler.ps1`
- **Installed Tasks:**
  - `TradeX PIT Morning`: `09:00 America/New_York` (morning pre-market context capture)
  - `TradeX PIT Evening`: `20:30 America/New_York` (post-market close context capture)
- **Task State:** `Ready` / `Enabled`
- **Canonical Working Directory:** `C:\Users\Gary\Projects\TradeX`
- **Persistent Database Path:** `C:\Users\Gary\.tradex\signals.db`
- **Execution Limits:** `execution_time_limit = PT1H`, `multiple_instances = IgnoreNew`
- **Catch-up Setting:** `StartWhenAvailable = false` (missed slots intentionally do not run late)
- **Credential Gate:** Confirmed successful (`MASSIVE_API_KEY` resolved by TradeX runtime settings from supported local configuration)

---

## 4. Operational Invariants & Limitations

- **Interactive Logon Limitation:**
  - Task Principal: `UserId = Gary`, `LogonType = Interactive`, `RunLevel = Limited`
  - The scheduled tasks **can run while the workstation is locked** (`can_run_while_workstation_locked = true`).
  - The scheduled tasks **cannot run while Gary is signed out of Windows** (`can_run_while_signed_out = false`).
- **Machine Awake Requirement:**
  - The workstation must remain powered on and awake (`machine_must_be_awake = true`). Scheduled tasks do not wake a sleeping system.
- **Activation Safety Audit:**
  - `manual_PIT_execution_performed = false`: No manual capture was triggered during activation.
  - `provider_calls_during_activation = false`: Zero live market data or provider API calls occurred during activation.
  - `repository_files_modified_during_activation = false`: No repository files were modified on `main` during activation.
  - `scheduler_manually_altered_outside_management_script = false`: Scheduler configuration was registered exclusively through `manage_pit_scheduler.ps1`.
- **First Due Captures (Pending Observation):**
  - First scheduled captures have **not yet been observed**.
  - First expected due trading-day captures:
    - `2026-09-21 09:00 ET`
    - `2026-09-21 20:30 ET`

---

## 5. Next Operational Gate

The next operational step is **`MVP-ARCH-001-R7-PIT-ACTIVATE-001-VERIFY`**:
- Observe and verify the first naturally scheduled Candidate C PIT captures after the 2026-09-21 morning and evening slots.
- No further R7 implementation work is authorized or required.
- Production strategy registry remains empty (`APPROVED_PRODUCTION_STRATEGIES == ()`).
- `LONG-002C` remains paused.
- `R8` remains unauthorized.
- `DAYTRADE-001` remains deferred.
