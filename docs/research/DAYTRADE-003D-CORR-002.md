# DAYTRADE-003D-CORR-002
# Sparse-Bar Correction and Final January 2 Data Pilot

## 1. Task Identity & Context

- **Task ID:** `DAYTRADE-003D-CORR-002`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Classification:** Research methodology and evaluator-compatibility correction, followed by one bounded real-data feasibility pilot.
- **Parent Task:** `DAYTRADE-003D-CORR-001` (PR #109)
- **Parent Authoritative Disposition:** `INVALID_CORRECTED_PROBE_IMPLEMENTATION`
- **Parent Defect Identified:** Conflation of absent Alpaca SIP minute bars (legitimate lack of trades) with missing provider data, which incorrectly depressed Stage-A coverage to 6.82%.
- **Expected Starting Main Commit:** `b109c462ec7389d71843470eedf9c612fc43cb04` (verified on `origin/main`).

---

## 2. Upstream Specification & Amendment Hashes

All historical specifications are immutable and verified via SHA-256:

| Document | Path | SHA-256 Hash |
| :--- | :--- | :--- |
| **DAYTRADE-003B Spec** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` |
| **DAYTRADE-003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` |
| **Historical DAYTRADE-003D Spec** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` |
| **DAYTRADE-003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` |
| **DAYTRADE-003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` |

---

## 3. Approved Research Methodology Amendments & Architectural Principles

This amendment addresses the root causes of prior pilot failures while preserving the underlying published Stocks-in-Play 5-minute ORB strategy (Zarattini et al., 2024).

### Architectural Principles

- **Principle A (Work with real-world data availability):** Ordinary missing historical intervals or legitimate no-trade intervals must not invalidate an otherwise representative study. Provider data failures (HTTP errors, pagination failure, truncated responses, malformed records) must be strictly distinguished from legitimate no-trade / no-setup market conditions.
- **Principle B (Candidate preservation):** The externally supported ORB strategy remains a permanent research candidate regardless of independent evaluation outcomes.

### Scope A: Sparse-Bar Opening Range Semantics
- In Alpaca SIP feeds, 1-minute bars are only emitted when qualifying trades occur.
- Any valid subset of 1 to 5 minute bars in the 09:30–09:34 ET window constructs a valid opening range:
  - `Open` = first available bar open
  - `High` = max high across available bars
  - `Low` = min low across available bars
  - `Close` = last available bar close
  - `Volume` = sum volume across available bars
- If zero bars exist across the entire 5-minute window on session $D$, the symbol had no opening prints and is classified as `NO_OPENING_PRINT_NO_SETUP` (a valid resolved non-setup outcome, not missing data).
- Corrupt, non-finite, out-of-order, or duplicate minute timestamps fail closed.

### Scope B: Baseline Relative Volume Denominator Semantics
- For each of the 14 prior sessions, opening-range volume is aggregated from available sparse bars.
- If all 14 prior sessions traded zero volume, mean prior volume is $0.0$, making RV uncomputable. This yields a valid resolved outcome: `UNRANKABLE_ZERO_RV_BASELINE`.
- A genuinely missing trading session (provider error, unmapped response) fails closed as `PROVIDER_DATA_FAILURE`.

### Scope C: Evaluator Compatibility & Sparse-Bar Price-Path Execution
- In Stage B (09:35–15:59 ET), sparse minute bars represent intervals with no qualifying trades.
- Fills are never fabricated:
  - Pending stop orders remain pending across missing minutes.
  - Open positions remain open across missing minutes; protective stops trigger only on actual reported trades touching the stop price.
  - A missing 15:59 ET EOD liquidation bar for an active position fails closed as `non_computable`.

### Scope D: Inexpensive Screening Operational Query Ordering
- Pre-filtering reduces provider network calls by ~88%:
  1. Broad daily screening (ADV14 $\ge 1\text{M}$, ATR14 $> \$0.50$) on Dec 2023 D-1 history reduces ~8,000 listed symbols down to ~600–1,000 daily-base-qualified symbols.
  2. Current opening range (09:30–09:34) and price filtering (`or_open > $5.00`) further reduces candidate symbols.
  3. Prior 14 OR sessions are queried only for daily-base-qualified symbols with current OR open $> \$5.00$.

### Scope E: Reformulated 95% Candidate-Screening Coverage Gate
- The formal 95% gate applies strictly to **candidate-screening completeness among daily-base-qualified symbols**:
  $$\text{screening\_completeness} = \frac{\text{validly\_determined\_count}}{\text{daily\_base\_qualified\_count}} \ge 0.95$$
- Validly determined classifications include:
  - `ELIGIBLE`
  - `PRICE_REJECTED`
  - `UNRANKABLE_ZERO_RV_BASELINE`
  - `RV_REJECTED`
  - `NO_OPENING_PRINT_NO_SETUP`
- Provider HTTP failures, truncated pagination, and corrupt data count against completeness.

---

## 4. Operational Safety Bounds & Governance

- **Runaway HTTP Page Ceiling:** `5,000 pages`.
- **Runaway Private Storage Bound:** `2 GB` (`2,147,483,648 bytes`).
- **Batch Size:** `100 symbols`.
- **Single-Session Authorization:** Pilot date is strictly `2024-01-02`.
- **Strict Quarantine:** Validation (2025) and Holdout (2026) partitions remain unopened.
- **No Simulation / PnL:** No simulated trades, PnL, win-rate, or Sharpe ratio calculation.
- **Production Isolation:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified.
- **Private Raw Storage:** Raw provider data and ticker lists remain isolated in private storage (`C:/Users/Gary/.tradex/research/daytrade_003d_corr_002/`).

---

## 5. Governed Pilot Dispositions

1. `FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD`
2. `BLOCKED_REFERENCE_OR_PROVIDER_ACCESS`
3. `BLOCKED_PROVIDER_DATA_INTEGRITY`
4. `BLOCKED_CANDIDATE_SCREENING_COVERAGE`
5. `BLOCKED_STAGE_B_PRICE_PATH`
6. `INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE`
7. `INVALID_CORR_002_IMPLEMENTATION`
