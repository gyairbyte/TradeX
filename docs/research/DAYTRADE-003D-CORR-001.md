# DAYTRADE-003D-CORR-001
# Practical Missing-Data Policy & Corrected Jan-2 End-to-End Data Pilot

## 1. Task Identity & Context

- **Task ID:** `DAYTRADE-003D-CORR-001`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Classification:** Research methodology amendment & bounded real-data feasibility pilot
- **Parent Task:** `DAYTRADE-003D-ORB-DATA-FEASIBILITY-001` (PR #108)
- **Parent Authoritative Disposition:** `INVALID_PROBE_IMPLEMENTATION_DEFECT`
- **Parent Observed Stop Condition:** `BLOCKED_RESOURCE_BOUND_UNDER_FROZEN_BATCH100_PLAN`
- **Starting Main Commit:** `625e67b14ad0ebfb2d4ccba315d55897980f7a33`

---

## 2. Upstream Specification & Amendment Hashes

| Document | Path | SHA-256 Hash |
| :--- | :--- | :--- |
| **DAYTRADE-003B Spec** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` |
| **DAYTRADE-003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` |
| **Historical DAYTRADE-003D Spec** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` |
| **DAYTRADE-003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` |

---

## 3. Approved Research Methodology Amendment: Data Availability Is Part of Reality

This methodology amendment supersedes **ONLY** the prior DAYTRADE-003C rule that one missing Stage-A symbol invalidates the entire session.

The underlying DAYTRADE-003B ORB strategy parameters do **NOT** change.

### A. Stage-A Coverage Gate (95.0%)
For each regular trading session $D$:
1. Begin with the complete point-in-time Massive target universe:
   - `active = true`
   - `market = stocks`
   - `primary_exchange in ('XNYS', 'XNAS')`
2. Define:
   $$\text{stage\_a\_coverage} = \frac{\text{computable\_stage\_a\_symbols}}{\text{canonical\_target\_universe\_symbols}}$$
3. Lock minimum coverage threshold at **95.0%**.
   - If $\text{stage\_a\_coverage} \ge 95.0\%$: The session is sufficiently representative for research, and ranking continues using the computable universe.
   - If $\text{stage\_a\_coverage} < 95.0\%$: The session is marked `DATA_COVERAGE_INSUFFICIENT` (`BLOCKED_STAGE_A_COVERAGE`), and no Stage-B data are requested.
4. The 95% threshold is a **prospective data-quality rule**, NOT a new trading filter. It reflects the practical reality of historical market data.

### B. Unavailable-Symbol Handling
If a symbol cannot be computed due to:
- `AMBIGUOUS_IDENTITY` (conflicting duplicate records)
- `INSUFFICIENT_HISTORY` (recent listing / IPO with fewer than 15 historical sessions)
- `CROSS_PROVIDER_UNMAPPED` (symbol not returned by Alpaca SIP)
- `MISSING_DAILY_DATA` (ADV14 or ATR14 not computable)
- `MISSING_PRIOR_OR_DATA` (fewer than 14 prior opening-range observations)
- `MISSING_CURRENT_OR_DATA` (missing session $D$ 09:30..09:34 opening range)
- `MALFORMED_DATA` (inverted bounds, negative prices/volume)

Then:
- Mark the symbol `STAGE_A_UNAVAILABLE` with its exact reason.
- Exclude the symbol from candidate ranking.
- Count the symbol in the coverage denominator ($\text{canonical\_target\_universe\_symbols}$).
- **Strict Prohibitions:** Do not invent data, fill missing bars, search further backward, use current membership lists, use future price behavior, or replace symbols based on outcome. The missingness decision is strictly independent of future returns.

### C. Fail-Closed Duplicate Canonical Symbols
- Canonical ticker format: `ticker.strip().upper()`.
- If the same canonical ticker appears more than once:
  - Do **NOT** silently keep the first row.
  - If rows can be proven identical using provider identity metadata (identical exchange, type, active status, and matching non-empty strong identity such as FIGI or CIK): collapse deterministically to 1 row.
  - Otherwise: mark the canonical symbol `AMBIGUOUS_IDENTITY`, exclude from Stage A, and count against the 95% coverage denominator.
  - Do NOT fail the entire universe for isolated ambiguous duplicates.
  - Do NOT publish ambiguous ticker names.
  - Do NOT create ticker-remapping heuristics.

### D. Missing IPO / Short-History Securities
- Securities listed fewer than the required lookback sessions are classified as `INSUFFICIENT_HISTORY`.
- Excluded from Stage-A ranking. Counts against coverage denominator.
- Does not invalidate the session if overall coverage $\ge 95.0\%$.
- No artificial IPO filter is introduced.

### E. Stage-B Missing Data Policy
- Complete 09:35 through 15:59 ET 1-minute data are strictly required for selected non-doji symbols.
- If required Stage-B data are missing: `BLOCKED_STAGE_B_COVERAGE`.
- Do NOT replace missing selected symbols with rank 21.
- Do NOT interpolate or fabricate intraday bars.

---

## 4. Operational Safety Bounds & Batching

- **Runaway HTTP Page Ceiling:** `5,000 pages` (replaces the self-imposed 1,000-page limit from PR #108).
- **Runaway Private Storage Bound:** `2 GB` (`2,147,483,648 bytes`).
- **Batch Size:** Simple deterministic batch size of `100 symbols`.
- **Pre-Acquisition Capability Verification:** Execute ONE small 100-symbol batch request before broad acquisition. If rejected: `BLOCKED_PROVIDER_BATCH_CAPABILITY`.

---

## 5. Governed Pilot Dispositions

The pilot terminates in one of seven preregistered dispositions:
1. `FEASIBLE_FOR_2024_DEVELOPMENT_DATASET`
2. `BLOCKED_MASSIVE_REFERENCE`
3. `BLOCKED_PROVIDER_BATCH_CAPABILITY`
4. `BLOCKED_ALPACA_SIP`
5. `BLOCKED_STAGE_A_COVERAGE`
6. `BLOCKED_STAGE_B_COVERAGE`
7. `INVALID_CORRECTED_PROBE_IMPLEMENTATION`

---

## 6. Strict Governance & Scope Hygiene

- **Strategy Simulation / Backtest:** Strictly forbidden. No simulated trades, entries, stops, PnL, win rates, or Sharpe ratios are computed.
- **Full-Year Acquisition:** Strictly forbidden in this pilot task.
- **Partitions:** Validation (2025) and Holdout (2026) partitions remain unopened and quarantined.
- **Production Status:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified.
- **Artifact Quarantine:** Raw provider payloads and ticker symbols remain in private storage (`C:/Users/Gary/.tradex/research/daytrade_003d_corr_001/`). Committed public artifacts contain only safe aggregates and hashes.
