# DAYTRADE-003D-CORR-002
# Sparse-Bar Correction and Final January 2 Data Pilot

## 1. Executive Summary & Authoritative Disposition

- **Task ID:** `DAYTRADE-003D-CORR-002`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Pilot Date:** `2024-01-02`
- **Starting Main SHA:** `b109c462ec7389d71843470eedf9c612fc43cb04`
- **Pre-Live Frozen Implementation SHA:** `d4c999dca88085cccb6d88455b13b25fbf76e9e6`
- **Initial Frozen-Run Emitted Claim:** `FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD` (preserved as historical execution output)
- **Authoritative Independent Audit Disposition:** `**INVALID_CORR_002_IMPLEMENTATION**` (preregistered taxonomy status)
- **Audit Disposition Rationale:** Deficiencies in automated Stage-B price-path validation, absence of persistent private OHLCV replay artifacts, and incomplete live validation of provider payload integrity. This reflects implementation and audit limitations, **NOT** proof of provider failure or invalidation of the underlying strategy.
- **Permanent Research Candidate Retention (Principle B):** The published Stocks-in-Play 5-minute Opening Range Breakout strategy (Zarattini et al., 2024) remains a permanent externally supported research candidate regardless of independent evaluation outcomes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.
- **Execution Wall-Clock Runtime:** `357.44 seconds`
- **Total Private Raw Storage:** `4,368,413 bytes` (Ceiling: `2,147,483,648 bytes`)

---

## 2. Methodology & Upstream Specification Hashes

All historical specifications are immutable and verified via SHA-256:

| Document | Path | SHA-256 Hash | Status |
| :--- | :--- | :--- | :--- |
| **003B Specification** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` | Immutable Verified |
| **003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` | Immutable Verified |
| **003D Data Feasibility** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` | Immutable Verified |
| **003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` | Immutable Verified |
| **003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` | Locked Preregistered |

---

## 3. Preserved Empirical Pilot Evidence (2024-01-02 Execution)

### Phase 1: Massive PIT Target Universe (2024-01-02)
- **Raw Massive Snapshot Rows:** `11,109` across `12` pages (SHA-256: `a3131c477d4af0b464410bc1bef369bf87d6a2830b7a72284cdd3f0667a786a7`).
- **Target Exchange Scope:** `('XNYS', 'XNAS')`.
- **Canonical Target Universe Count:** `7,987` (`4,981` `XNAS`, `3,008` `XNYS`).
- **Target Universe Cryptographic Hash:** `383a66f1c7100922d38638f24e4a23724bbc29b77cafc51990dab6ccda117f20`.
- **Fail-Closed Canonical Duplicates:** Exactly `2` ambiguous duplicate identities resolved fail-closed as `AMBIGUOUS_IDENTITY`.
- **Valid Query Target Symbols:** `7,985`.

### Phase 2: Inexpensive Broad Daily Availability (Dec 2023 D-1 Lookback)
- **Broad PIT Universe Symbols:** `7,987`.
- **Daily Indicator Computable Symbols:** `7,558` (94.63% broad daily data availability).
- **Missing Daily Data Count:** `429`.
- **Daily-Base-Qualified Pool:** `959` symbols met ADV14 $\ge 1\text{M}$ and ATR14 $> \$0.50$.

### Phase 3: Candidate Screening Completeness (Scope E Gate)
- **Screening Denominator (Daily-Base-Qualified Pool):** `959` symbols.
- **Validly Determined Symbols (Frozen Output):** `959` (reported 100.00% completeness vs 95.0% threshold).
- **Classification Breakdown (Frozen Output):**
  - `ELIGIBLE`: `253` symbols
  - `RV_REJECTED` (RV < 1.0): `678` symbols
  - `PRICE_REJECTED` (Open $\le \$5.00$): `28` symbols
  - `NO_OPENING_PRINT_NO_SETUP`: `0` symbols
  - `UNRANKABLE_ZERO_RV_BASELINE`: `0` symbols
  - `PROVIDER_DATA_FAILURE`: `0` symbols
- *Audit Status:* **Not independently validated as a rigorous data-quality conclusion** (see Section 4).

### Phase 4: Frozen Top-20 Selection Evidence
- **Eligible Candidates:** `253` symbols passed all 4 technical screens (Price $> \$5$, ADV14 $\ge 1\text{M}$, ATR14 $> \$0.50$, RV $\ge 1.0$).
- **Top-20 Selected Count:** Exactly `20` non-doji symbols selected by Relative Volume descending (ticker ascending tie-breaker).
- **Doji Count (No-Order):** `0`.
- **Selection Cryptographic Hash:** `080a444e0fc371969d8ba228b0eb0ad9d4fe89958c88778901cc11498a69e82e`.

### Phase 5: Stage-B Price Path Audit (09:35–15:59 ET)
- **Selected Symbols Queried:** `20` symbols.
- **Total Expected Minute Intervals:** `7,700` ($20 \times 385$).
- **Total Actual Provider Bars Received:** `7,447`.
- **Total Absent Minute Slots:** `253` absent minute intervals.
- **Missing 15:59 EOD Liquidation Bars Reported:** `0`.
- **Stage-B Price Path Status (Frozen Output):** `USABLE`.
- *Audit Status:* **Not independently validated as a complete data-quality conclusion**; the absent-minute count of 253 is not proven to represent verified absence of qualifying trades (see Section 4).

---

## 4. Material Review Findings & Independent Audit Analysis

Independent code and evidence audit identified three material methodological gaps, one documentation typo, and an external CI environment failure:

### Finding 1: Stage-B Usability Logic Unproven
In [`tradex/research/daytrade_orb/corr_002_pilot.py`](file:///tradex/research/daytrade_orb/corr_002_pilot.py), `audit_stage_b_price_path` sets `is_usable = failures == 0` without independently evaluating that:
- The required 15:59 ET EOD liquidation bar exists and is non-zero for all open positions.
- Bars are strictly within regular market hours (09:35–15:59 ET) with no out-of-session prints.
- No duplicate timestamps or inverted high/low price bounds exist in the returned series.
- Bar symbol identities match requested query keys.

Although the frozen runner reported `0` missing 15:59 bars, the audit logic itself does not enforce these requirements before declaring usability.

### Finding 2: Replayable Private Alpaca Data Missing
The pilot runner persisted the Massive reference snapshot (`massive_reference_2024-01-02.json`) and the Top-20 selection record, but did **not** persist:
- Raw Dec 2023 daily bars across the 7,985 queried symbols.
- Raw 14-session prior opening-range minute bars for the 931 screened symbols.
- Raw 09:30–09:34 ET opening-range bars for session $D$.
- Raw 09:35–15:59 ET Stage-B minute bars for the 20 selected symbols.

Consequently, the reported `4,368,413 bytes` private storage does not contain the complete OHLCV evidence required to replay eligibility, ranking, and path execution offline without making fresh provider calls.

### Finding 3: Provider-Integrity versus No-Print Gaps Not Fully Verified
The runner does not comprehensively inspect provider payloads for malformed timestamps, unexpected symbol identities, truncated batches, or HTTP anomalies before treating missing minutes as legitimate no-print sparse intervals. Thus, the observed 100.00% screening completeness and `USABLE` Stage-B classifications are **frozen run outputs, not independently validated data-quality conclusions**. The 253 absent minutes cannot yet be formally certified as verified absence of qualifying trades.

### Finding 4: Candidate Count Clarification
The preliminary report conflated candidate counts. The empirical execution produced **253 eligible candidates**, from which the top **20 candidates** were selected by relative volume for Stage B.

### Finding 5: Exact-Head CI Failure (External Toolchain Drift)
GitHub Actions workflow run `38179981673` (job `114590294666`) on PR #110 failed at the scoped lint check (`uv run ruff check tests scripts`) before tests could run. The CI environment installed unpinned Ruff **0.17.0** (whereas the prior passing PR #109 used Ruff **0.16.10**). Ruff 0.17.0 introduced new default checks that flagged 31 `RUF100` (unused `noqa` directive) warnings across unchanged historical test files. This failure represents external CI toolchain dependency drift, not a defect or regression in TradeX research code. Per governance rules, no mass-edits to historical tests or dependency files are permitted on this post-live-frozen research PR.

---

## 5. Provider Resource Consumption & Provenance

- **Alpaca Total Logical Calls:** `231`
- **Alpaca Total HTTP Pages:** `231`
- **Alpaca Retries / 429s:** `0`
- **Massive HTTP Pages:** `12`
- **Total Provider HTTP Pages:** `243` (Ceiling limit: `5,000`)
- **Total Elapsed Runtime:** `357.44 seconds`
- **Storage Consumption:** `4,368,413 bytes` (~4.17 MB, Bound: `2,147,483,648 bytes`)

---

## 6. Governance & Production Safeguards

- **Strategy Simulation / Backtest:** Strictly forbidden and not executed. Zero trade simulations, orders, fills, PnL, win rates, or Sharpe ratios were calculated.
- **Full-Year 2024 Acquisition:** Quarantined and not executed.
- **2025 Validation / 2026 Holdout Partitions:** Strictly unopened and quarantined.
- **Candidate Retention Principle:** Under Principle B, the Stocks-in-Play 5-minute ORB strategy remains an authorized permanent external research candidate regardless of independent evaluation outcomes.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly verified empty.

---

## 7. Roadmap & Recommended Next Work Order

To maintain strict boundary hygiene and resolve these findings cleanly, work is divided into two separate, future bounded PRs. Neither is executed in PR #110:

1. **Future PR A (Development Tooling):** Minimal CI Ruff version stabilization from `main` (pinning Ruff tooling to restore clean CI across unchanged historical files without touching research logic).
2. **Future PR B (Research Methodology & Replay Correction):** Focused provider-integrity validation and full private raw OHLCV replay persistence with ONE controlled January 2, 2024 verification before any full-year 2024 development dataset construction is authorized. (No generalized data platform).
