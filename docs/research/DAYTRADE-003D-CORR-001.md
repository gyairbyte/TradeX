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

---

## 7. Post-Live Empirical Evidence & Semantic Audit Correction

### A. Execution & Valid Live Evidence Preserved
The bounded single-session (2024-01-02) pilot executed exactly once from pre-live frozen commit `052360e439a96649eea13091e6d92ffa9623601c` obeying all freeze and governance rules. Valid empirical findings preserved:
- **Massive PIT 2024-01-02 Reference Snapshot:** 12 pages, 11,109 raw rows (SHA-256 `a3131c477d4af0b464410bc1bef369bf87d6a2830b7a72284cdd3f0667a786a7`), 7,989 target rows (4,981 `XNAS`, 3,008 `XNYS`).
- **Canonical Target Universe:** 7,987 symbols (SHA-256 `383a66f1c7100922d38638f24e4a23724bbc29b77cafc51990dab6ccda117f20`).
- **Fail-Closed Canonical Duplicates:** Exactly 2 ambiguous duplicate identities identified and classified fail-closed as `AMBIGUOUS_IDENTITY` (neither dropped nor arbitrarily deduplicated). Valid target symbols queried: 7,985.
- **Alpaca 100-Symbol Capability Test:** HTTP 200, 97 symbols returned with valid bar data.
- **Stage-A Acquisition Operationally Completed:** 80 batches of 100 symbols querying 20 daily bars (Dec 2023), 14 prior OR sessions, and Jan 2 OR (1,281 calls, 1,281 pages, 0 retries, 0 429s/errors).
- **Resource Consumption:** 1,293 total HTTP pages (< 5,000 limit), 103,310 bytes private storage (< 2 GB limit), 463.65s runtime.
- **Execution Boundaries Preserved:** Zero Stage-B calls requested/executed; zero strategy evaluation, backtest, trade simulation, or PnL executed (`strategy_evaluator_executed = false`); validation (2025) and holdout (2026) remain strictly unopened and quarantined; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.

### B. Material Provider-Semantics Defect (Sparse Alpaca Bars)
Independent post-live review identified a material provider-semantics defect in how the frozen implementation interpreted absent Alpaca stock minute bars:
1. **Alpaca Stock Bar Semantics:** Alpaca's stock market-data documentation states that a stock bar is not generated when there are no qualifying trades in the bar interval. Therefore, absence of a 1-minute bar does **NOT** necessarily mean missing provider data.
2. **ORB Source Definition:** The Zarattini et al. (2024) Relative Volume formula defines RV as first-five-minute traded volume today divided by average first-five-minute traded volume over the prior 14 trading days. A no-trade interval contributes zero traded volume.
3. **Conflation Defect:** The frozen implementation incorrectly required an opening-range observation for every one of the prior 14 sessions and classified absent minute bars as `MISSING_PRIOR_OR_DATA`. The frozen probe conflated `NO_TRADES_IN_INTERVAL` with `MISSING_DATA`.
4. **Correction of 7,008 Classification:** 7,008 symbols were classified `MISSING_PRIOR_OR_DATA` by the frozen implementation, but that classification is **not reliable as a provider gap count** because no-trade minute intervals were treated as missing observations.
5. **Coverage Result Invalidation:** The observed Stage-A coverage of 6.8236% (545/7,987 computable) is **`NOT_VALID_AS_TRUE_DATA_COVERAGE_ESTIMATE`**.
6. **Authoritative Final Disposition:**
   $$\text{Authoritative Disposition} = \mathbf{INVALID\_CORRECTED\_PROBE\_IMPLEMENTATION}$$

### C. 95% Coverage Policy Status
The approved practical coverage policy (data availability is part of reality; small unavailable portions do not invalidate an otherwise representative study) remains active. However, the 95.0% gate was **NOT validly evaluated** by this frozen pilot because its numerator was corrupted by the sparse-bar interpretation defect. The next corrected pilot must calculate coverage using corrected provider semantics. Only after that result should TradeX decide whether the 95% threshold itself needs reconsideration; do not tune the threshold based on the invalid 6.82% result.

### D. Recommended Next Correction: DAYTRADE-003D-CORR-002
1. **Correct Opening-Volume Semantics:** For a successfully completed Alpaca SIP request covering a known mapped symbol and opening window, a missing 1-minute bar within the 09:30–09:34 interval means zero qualifying traded volume for that minute. Do NOT fabricate OHLC. For prior RV volume: sum volumes of bars that exist in the 5-minute window; if no bars exist in the full window: opening-range volume = 0. For current opening range: aggregate OHLC from actual qualifying trades/bars occurring anywhere in the 5-minute window; if zero bars exist across the entire window: no valid current opening range, symbol cannot generate a setup that session.
2. **Flexible 5-Minute Range:** Do not require exactly five 1-minute bars merely to compute a 5-minute opening range.
3. **Preserve True Provider Failures Separately:** Request failure, pagination failure, malformed data, unmapped symbol, or actual incomplete response must NOT be converted to zero.
4. **Cheap Point-in-Time Pre-Filtering:** Apply cheap PIT eligibility checks (daily ADV14, ATR14) before unnecessary OR-history work wherever it does not change the locked strategy. Obtain/process current opening range and prior RV data only for symbols that pass daily eligibility.
5. **Preserve Locked Strategy:** Do not change price threshold ($> \$5$), ADV threshold ($\ge 1\text{M}$), ATR threshold ($> \$0.50$), RV threshold ($\ge 1.0$), Top 20 ranking, entry logic, stop logic, or cost assumptions.
6. **Rerun Only Bounded Jan-2 Pilot:** Rerun only the Jan-2 bounded pilot after code/spec/test freeze. No full-year build yet.
