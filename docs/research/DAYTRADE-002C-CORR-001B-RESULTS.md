# DAYTRADE-002C-CORR-001B — Corrected Preholdout Development & Validation Re-execution Results

> [!IMPORTANT]
> **Executive Summary & Research-Validity Classification**
>
> * **Execution Validity:** **`VALID`**
> * **Execution Identity:** Corrected empirical re-execution under task `DAYTRADE-002C-CORR-001B`
> * **Gary Authorization:** Explicitly authorized on 2026-10-05
> * **Historical Execution Distinction:**
>   * **ORIGINAL DAYTRADE-002C (2026-10-04, PR #94):** **`INVALID`** — evaluator integration defect (`quality.py:audit_ticker_session` omitted `bar_start` timestamp resolution, causing 100% session row exclusions). Produced **zero valid strategy evidence**.
>   * **DAYTRADE-002C-CORR-001A (PR #96):** Evaluator timestamp-schema integration defect corrected and merged to `main` at commit `770a1a66382351dd63b9245c50bed0c1d92f3ca1`. Zero real-data access; zero re-execution.
>   * **DAYTRADE-002C-CORR-001B (This Task):** Corrected empirical execution reusing the exact existing preholdout dataset bytes. Zero new provider calls. Zero reacquisition. Development executed exactly once. Validation executed exactly once.
> * **Development Disposition (Diagnostic Only):** **`REJECTED`** (`step_3_directional_hypothesis_failure` — mean net return @ 2 bps $\le 0$ at $-0.95$ bps, breadth $53.33\% < 60.0\%$)
> * **Validation Disposition (Preregistered):** **`INCONCLUSIVE`** (`step_4_statistical_uncertainty` — primary net return 95% clustered confidence interval lower bound $\le 0$ at $-2.02$ bps)
> * **Holdout Status:** **`unread_not_acquired`** (holdout strictly unread, unacquired, unparsed, and unevaluated; zero provider calls)
> * **Production Promotion:** Ineligible (`production_promotion_eligible = false`; `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved)

* **Task ID:** `DAYTRADE-002C-CORR-001B`
* **Title:** Corrected DAYTRADE-002 preholdout development and validation re-execution
* **Classification:** Research-only corrected empirical execution (zero production impact)
* **Execution Date:** 2026-10-05
* **Evaluator Base Commit SHA:** `770a1a66382351dd63b9245c50bed0c1d92f3ca1` (merge commit of PR #96 / `DAYTRADE-002C-CORR-001A`)
* **Canonical Specification:** `docs/research/specs/DAYTRADE-002A-v1.json`
* **Locked Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Preholdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Execution Plan SHA-256:** `e0022b3f40c3d9e23cc014380d3c4cd5c8005bc3943744df1c809f5c9bac4c2a`
* **Development Bundle SHA-256:** `c756f5d7efa4d63cdc8f5574623667432507a239d8397da2099b4bea79287da8`
* **Validation Bundle SHA-256:** `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`
* **Evidence Confidence Cap:** `limited_but_usable_evidence`
* **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 1. Study Identity and Execution Lineage

| Dimension | Specification & Execution Value |
|---|---|
| **Task ID** | `DAYTRADE-002C-CORR-001B` |
| **Gary Authorization** | EXPLICITLY AUTHORIZED on 2026-10-05 |
| **Execution Validity** | `VALID` |
| **Evaluator Code SHA** | `770a1a66382351dd63b9245c50bed0c1d92f3ca1` (clean frozen evaluator from PR #96) |
| **Locked Spec SHA-256** | `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127` |
| **Preholdout Manifest SHA-256** | `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb` |
| **Execution Plan SHA-256** | `e0022b3f40c3d9e23cc014380d3c4cd5c8005bc3943744df1c809f5c9bac4c2a` |
| **Freeze File** | `~/.tradex/research/daytrade_002c_corr_001b_v1/freeze/freeze.json` |
| **Market Data Provider** | Alpaca Market Data API (`alpaca`) via Alpaca SIP |
| **Provider Calls for CORR-001B** | **`0`** (zero new market data requests; exact existing bytes reused) |
| **Timeframe & Adjustment** | `1Min`, split-adjusted only (`split`), cash dividends excluded |
| **Exchange Calendar** | `XNYS` regular trading sessions (09:30–16:00 ET; early closes excluded) |
| **Timezone** | `America/New_York` |
| **Universe** | Fixed 15-ETF panel: `XLK`, `XLV`, `XLF`, `XLY`, `XLP`, `XLE`, `XLI`, `XLB`, `XLU`, `XLRE`, `XLC`, `SPY`, `QQQ`, `IWM`, `DIA` |
| **Dataset Partitions** | Context Anchor: `2025-12-31`<br>Warm-up: `2026-01-02` through `2026-01-30`<br>Development: `2026-02-02` through `2026-04-30`<br>Validation: `2026-05-01` through `2026-06-30`<br>Holdout (quarantined): `2026-07-01` through `2026-08-31` |
| **Private Dataset Root** | `~/.tradex/research/daytrade_002_v1/preholdout` (reused byte-for-byte; uncommitted) |
| **External Run Root** | `~/.tradex/research/daytrade_002c_corr_001b_v1/` |
| **Committed Safe Artifacts** | `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/` |
| **Holdout Status** | `unread_not_acquired` (zero provider calls; holdout strictly unread and unacquired) |
| **Production Promotion** | Ineligible (`production_promotion_eligible = false`) |

---

## 2. Dataset Verification & Reused Provenance

Before executing development or validation, the preholdout dataset partition was verified using the authoritative repository validator (`DaytradeDatasetManifest.from_dict` and `verify_dataset_manifest`):

* **Dataset Reacquisition Authorized:** `false`
* **Additional Provider Calls:** `0`
* **Preholdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb` (verified)
* **All 15 Source Bar File Checksums Verified Against Manifest:**
  * `bars/XLK.csv`: `16cde6316e82fb233ac84cc4c2d3dadb159a8c9b24d8b923718e3c294040601c`
  * `bars/XLV.csv`: `0848560d3b67e46354bd78789db3ae68b3c20bdce4e2d5708bf18da6656a84b5`
  * `bars/XLF.csv`: `87a6b8efcae214103465edad22cff28e142f4eafeec1ec9c38a078cf314ae0ee`
  * `bars/XLY.csv`: `e4daaa9f6041bba49751639fc0af551786b86270b629a8bc208c3205e004c86d`
  * `bars/XLP.csv`: `8d6a58b33d6dee0f113d0d9ce94bc63a5b133025d33b52a7759b3356cbaaa199`
  * `bars/XLE.csv`: `1634947222e1c14d66bdc61fc7a716a1d916556ee269b03752ef1ddfecc583e2`
  * `bars/XLI.csv`: `6f7d560e7087fb160a3b7596d90e86072e2b8ebfc285b405b6137bb1e9bb8700`
  * `bars/XLB.csv`: `ec05784b30aee9b4a1601c10c7e019ba86bb38e6ccb47f3af749193f9a9bc493`
  * `bars/XLU.csv`: `83ae5d609ef3acc9ec32048c8a023676d06999e2c7b99a306da424f968302624`
  * `bars/XLRE.csv`: `b3abd58e931b547376c160dfeb88580f8dadba68d5ef7def102ee634e75acd24`
  * `bars/XLC.csv`: `db4742679cf27d0b2210498343aebcbcb6bbd4bb8d90db2dc75182a6f1f5541c`
  * `bars/SPY.csv`: `bee62d98a76a6e73fad75bdfb83d8bfc4ec2d54465c3de8ea4626b09dcb30c9b`
  * `bars/QQQ.csv`: `44e6523fe8c07b69b736496a99d0e9386ac87f447605fd41becc50d65568e667`
  * `bars/IWM.csv`: `7393d59c10811bdbe7a94ab8fee8066a3ef1f8b95c5d0896309f7cad9997539d`
  * `bars/DIA.csv`: `286cb40f7a8473786ae1e45f84b2d7b49c4857ec9e968118760208caa8b5fe22`
* **Zero Unmanifested Bar Files:** Confirmed.
* **Inherited Acquisition Provenance:** 105 provider calls, 149 pages, 44 retries, 0 429s, 0 errors, 0 provider malformed timestamps.

---

## 3. Development Split Empirical Results (Diagnostic Only)

Development was executed exactly once using the frozen corrected evaluator. Pursuant to protocol, development results are diagnostic only and were not used to optimize or tune parameters.

* **Split Period:** `2026-02-02` through `2026-04-30` (62 regular trading sessions)
* **Expected Ticker-Sessions:** 930 (62 trading dates $\times$ 15 ETFs)
* **Eligible Ticker-Sessions:** 930 (100.00%)
* **Excluded Ticker-Sessions:** 0 (0.00% exclusion rate $\le 5.0\%$ gate)
* **Malformed Timestamps:** 0
* **Malformed OHLCV Rows:** 0
* **Missing Bars Across All Sessions:** 61 (0 session exclusions; all well within the 19 missing bars pass threshold)
* **Duplicate Bars Across All Sessions:** 0
* **Evaluator Disposition:** **`REJECTED`**
* **Disposition Step:** `step_3_directional_hypothesis_failure`
* **Disposition Reason:** `mean_net_return_le_zero (-9.471154340871249e-05); breadth_gate_failed (53.33% < 60.0%)`

### Development Gate Results

| Gate | Status | Threshold / Requirement | Realized Value |
|---|---|---|---|
| **1. Sample Gate** | **PASS** | $\ge 75$ events, $\ge 10$ ETFs, $\ge 20$ dates | 206 events, 15 ETFs, 47 dates |
| **2. Concentration Gate** | **PASS** | Max single ETF $\le 15.0\%$ | 7.77% (XLI, 16/206 events) |
| **3. Data Quality Gate** | **PASS** | Split exclusion rate $\le 5.0\%$ | 0.00% (0 / 930 sessions) |
| **4. Primary Net-Effect Gate** | **FAIL** | Mean net return @ 2 bps $> 0$ & 95% CI lower $> 0$ | Mean: $-0.95$ bps; 95% CI: $[-7.56\text{ bps}, +5.55\text{ bps}]$ |
| **5. Baseline-Uplift Gate** | **FAIL** | Mean uplift $> 0$ & 95% CI lower $> 0$ | Mean: $+3.85$ bps; 95% CI lower: $-3.35$ bps ($\le 0$) |
| **6. Cross-ETF Breadth Gate** | **FAIL** | Positively performing ETFs $\ge 60.0\%$ | 53.33% (8 of 15 ETFs positive) |

> [!NOTE]
> While development mean uplift is positive (+3.85 bps), the 95% session-date clustered confidence interval lower bound is $\le 0$ ($-3.35$ bps; CI $[-3.35\text{ bps}, +10.56\text{ bps}]$), so the full locked baseline-uplift gate failed (`baseline_uplift_gate.passed = false` in authoritative development `study.json`). This did NOT alter the formal development disposition: `REJECTED` (`step_3_directional_hypothesis_failure`), because Step 3 was already triggered by mean primary net return $\le 0$ ($-0.95$ bps) and cross-ETF breadth $< 60.0\%$ (53.33%).

### Development Core Metrics

| Metric | Development Value |
|---|---|
| **Expected Target Ticker-Sessions** | 930 |
| **Eligible Ticker-Sessions** | 930 |
| **Excluded Ticker-Sessions** | 0 (0.00%) |
| **Event Count** | 206 |
| **Represented ETFs** | 15 |
| **Event Session Count (Dates)** | 47 |
| **Long Event Count** | 111 (53.88%) |
| **Short Event Count** | 95 (46.12%) |
| **Maximum Single-ETF Concentration** | 7.77% (XLI, 16 events) |
| **Multi-Signal Session Count & Rate** | 36 sessions (76.60% of event sessions) |
| **Mean Gross Signed Return (30m)** | +3.05 bps (+0.000305) |
| **Median Gross Signed Return (30m)** | +3.91 bps (+0.000391) |
| **Gross Win Rate (30m)** | 56.80% (117 / 206) |
| **Mean Net Return @ 0 bps** | +3.05 bps (+0.000305) |
| **Median Net Return @ 0 bps** | +3.91 bps (+0.000391) |
| **Mean Net Return @ 2 bps/side (Primary)** | $-0.95$ bps ($-0.000095$) |
| **Median Net Return @ 2 bps/side** | $-0.09$ bps ($-0.000009$) |
| **Mean Net Return @ 5 bps/side** | $-6.95$ bps ($-0.000695$) |
| **Median Net Return @ 5 bps/side** | $-6.09$ bps ($-0.000609$) |
| **Matched Non-Event Baseline Mean** | $-4.80$ bps ($-0.000480$) |
| **Matched Non-Event Baseline Median** | $-3.97$ bps ($-0.000397$) |
| **Event-minus-Baseline Uplift (Mean)** | $+3.85$ bps (+0.000385) |
| **Event-minus-Baseline Uplift (Median)** | $+4.42$ bps (+0.000442) |
| **Primary Net Return 95% Clustered CI** | $[-7.56\text{ bps}, +5.55\text{ bps}]$ (`computable`) |
| **Baseline Uplift 95% Clustered CI** | $[-3.35\text{ bps}, +10.56\text{ bps}]$ (`computable`) |
| **Positive Ticker Breadth** | 53.33% (8 / 15 ETFs positive) |

### Development Subgroup Breakdown

* **Direction Diagnostics:**
  * LONG (111 events): Mean net return @ 2 bps: $-1.17$ bps; Mean uplift: $+2.07$ bps; Gross win rate: 60.36%
  * SHORT (95 events): Mean net return @ 2 bps: $-0.68$ bps; Mean uplift: $+5.93$ bps; Gross win rate: 52.63%
* **Monthly Breakdown:**
  * 2026-02 (69 events): Mean net return @ 2 bps: $-4.68$ bps
  * 2026-03 (83 events): Mean net return @ 2 bps: $-3.41$ bps
  * 2026-04 (54 events): Mean net return @ 2 bps: $+7.61$ bps
* **Per-ETF Results (Net Mean @ 2 bps, Gross Win Rate, Event Count):**
  * `DIA`: $-0.49$ bps | 50.00% | 14 events
  * `IWM`: $+5.58$ bps | 66.67% | 12 events
  * `QQQ`: $+3.17$ bps | 58.33% | 12 events
  * `SPY`: $+0.23$ bps | 64.29% | 14 events
  * `XLB`: $+2.12$ bps | 71.43% | 14 events
  * `XLC`: $-9.59$ bps | 30.77% | 13 events
  * `XLE`: $+2.40$ bps | 64.29% | 14 events
  * `XLF`: $-1.71$ bps | 45.45% | 11 events
  * `XLI`: $-3.64$ bps | 56.25% | 16 events
  * `XLK`: $+0.83$ bps | 69.23% | 13 events
  * `XLP`: $-1.45$ bps | 46.67% | 15 events
  * `XLRE`: $-1.40$ bps | 71.43% | 14 events
  * `XLU`: $+1.38$ bps | 57.14% | 14 events
  * `XLV`: $+1.30$ bps | 66.67% | 15 events
  * `XLY`: $-11.08$ bps | 33.33% | 15 events

---

## 4. Validation Split Empirical Results (Formal Preregistered Evaluation)

Validation was executed exactly once immediately after development with zero code, parameter, or configuration changes.

* **Split Period:** `2026-05-01` through `2026-06-30` (41 regular trading sessions)
* **Expected Ticker-Sessions:** 615 (41 trading dates $\times$ 15 ETFs)
* **Eligible Ticker-Sessions:** 615 (100.00%)
* **Excluded Ticker-Sessions:** 0 (0.00% exclusion rate $\le 5.0\%$ gate)
* **Malformed Timestamps:** 0
* **Malformed OHLCV Rows:** 0
* **Missing Bars Across All Sessions:** 75 (0 session exclusions)
* **Duplicate Bars Across All Sessions:** 0
* **Evaluator Disposition:** **`INCONCLUSIVE`**
* **Disposition Step:** `step_4_statistical_uncertainty`
* **Disposition Reason:** `primary_ci_lower_le_zero (-0.00020152034006772274)`

### Validation Gate Results

| Gate | Status | Threshold / Requirement | Realized Value | Analysis |
|---|---|---|---|---|
| **1. Sample Gate** | **PASS** | $\ge 75$ events, $\ge 10$ ETFs, $\ge 20$ dates | 153 events, 15 ETFs, 36 dates | Ample sample size |
| **2. Concentration Gate** | **PASS** | Max single ETF $\le 15.0\%$ | 7.84% (IWM, QQQ, XLK, XLP: 12/153) | Well below ceiling |
| **3. Data Quality Gate** | **PASS** | Split exclusion rate $\le 5.0\%$ | 0.00% (0 / 615 sessions) | Perfect realizable sessions |
| **4. Primary Net-Effect Gate** | **FAIL** | Mean net return @ 2 bps $> 0$ & 95% CI lower $> 0$ | Mean: $+3.46$ bps ($> 0$); 95% CI lower: $-2.02$ bps ($\le 0$) | Mean is positive, but statistical uncertainty gate fails |
| **5. Baseline-Uplift Gate** | **PASS** | Mean uplift $> 0$ & 95% CI lower $> 0$ | Mean: $+6.44$ bps ($> 0$); 95% CI lower: $+0.44$ bps ($> 0$) | Significant positive uplift over matched non-events |
| **6. Cross-ETF Breadth Gate** | **PASS** | Positively performing ETFs $\ge 60.0\%$ | 66.67% (10 of 15 ETFs positive) | Passes 60% breadth threshold |

### Validation Core Metrics

| Metric | Validation Value |
|---|---|
| **Expected Target Ticker-Sessions** | 615 |
| **Eligible Ticker-Sessions** | 615 |
| **Excluded Ticker-Sessions** | 0 (0.00%) |
| **Event Count** | 153 |
| **Represented ETFs** | 15 |
| **Event Session Count (Dates)** | 36 |
| **Long Event Count** | 91 (59.48%) |
| **Short Event Count** | 62 (40.52%) |
| **Maximum Single-ETF Concentration** | 7.84% (12 events each in IWM, QQQ, XLK, XLP) |
| **Multi-Signal Session Count & Rate** | 33 sessions (91.67% of event sessions) |
| **Mean Gross Signed Return (30m)** | +7.46 bps (+0.000746) |
| **Median Gross Signed Return (30m)** | +9.00 bps (+0.000900) |
| **Gross Win Rate (30m)** | 67.97% (104 / 153) |
| **Mean Net Return @ 0 bps** | +7.46 bps (+0.000746) |
| **Median Net Return @ 0 bps** | +9.00 bps (+0.000900) |
| **Mean Net Return @ 2 bps/side (Primary)** | +3.46 bps (+0.000346) |
| **Median Net Return @ 2 bps/side** | +5.00 bps (+0.000500) |
| **Mean Net Return @ 5 bps/side** | $-2.54$ bps ($-0.000254$) |
| **Median Net Return @ 5 bps/side** | $-0.997$ bps ($-0.000100$) |
| **Matched Non-Event Baseline Mean** | $-2.98$ bps ($-0.000298$) |
| **Matched Non-Event Baseline Median** | $-3.77$ bps ($-0.000377$) |
| **Event-minus-Baseline Uplift (Mean)** | $+6.44$ bps (+0.000644) |
| **Event-minus-Baseline Uplift (Median)** | $+6.58$ bps (+0.000658) |
| **Primary Net Return 95% Clustered CI** | $[-2.02\text{ bps}, +8.56\text{ bps}]$ (`computable`) |
| **Baseline Uplift 95% Clustered CI** | $[+0.44\text{ bps}, +12.14\text{ bps}]$ (`computable`) |
| **Positive Ticker Breadth** | 66.67% (10 / 15 ETFs positive) |

### Validation Subgroup Breakdown

* **Direction Diagnostics:**
  * LONG (91 events): Mean net return @ 2 bps: $-0.84$ bps; Mean uplift: $+2.87$ bps; Gross win rate: 59.34%
  * SHORT (62 events): Mean net return @ 2 bps: $+9.77$ bps; Mean uplift: $+11.70$ bps; Gross win rate: 80.65%
* **Monthly Breakdown:**
  * 2026-05 (74 events): Mean net return @ 2 bps: $-0.36$ bps
  * 2026-06 (79 events): Mean net return @ 2 bps: $+7.04$ bps
* **Per-ETF Results (Net Mean @ 2 bps, Gross Win Rate, Event Count):**
  * `DIA`: $-6.31$ bps | 33.33% | 9 events
  * `IWM`: $+3.93$ bps | 75.00% | 12 events
  * `QQQ`: $+10.18$ bps | 83.33% | 12 events
  * `SPY`: $+3.67$ bps | 81.82% | 11 events
  * `XLB`: $-2.71$ bps | 54.55% | 11 events
  * `XLC`: $+4.99$ bps | 90.00% | 10 events
  * `XLE`: $+0.61$ bps | 55.56% | 9 events
  * `XLF`: $-7.17$ bps | 55.56% | 9 events
  * `XLI`: $+2.40$ bps | 66.67% | 9 events
  * `XLK`: $+14.81$ bps | 75.00% | 12 events
  * `XLP`: $-3.28$ bps | 50.00% | 12 events
  * `XLRE`: $+15.97$ bps | 90.91% | 11 events
  * `XLU`: $+12.78$ bps | 85.71% | 7 events
  * `XLV`: $-0.94$ bps | 50.00% | 10 events
  * `XLY`: $+0.008$ bps | 66.67% | 9 events

---

## 5. Formal Research Interpretation

Under the locked 5-step disposition precedence hierarchy:

* **Step 1 (Invalidity):** Execution is valid (no calculation-, timestamp-, split-, or dataset-integrity defect was identified. One non-calculation artifact metadata-label defect is documented separately in Section 8).
* **Step 2 (Evidence Sufficiency):** All sufficiency gates pass (153 events $\ge 75$, 15 ETFs $\ge 10$, 36 dates $\ge 20$, 7.84% concentration $\le 15\%$, 0.0% DQ exclusions $\le 5\%$).
* **Step 3 (Directional Hypothesis Failure):** All directional gates pass (mean primary net return $+3.46$ bps $> 0$; mean uplift $+6.44$ bps $> 0$; positive ETF breadth $66.67\% \ge 60\%$).
* **Step 4 (Statistical Uncertainty):**
  * Event-minus-baseline uplift 95% clustered confidence interval is strictly positive: $[+0.44\text{ bps}, +12.14\text{ bps}]$.
  * However, the **primary net return 95% clustered confidence interval includes zero**: $[-2.02\text{ bps}, +8.56\text{ bps}]$.
  * Because the lower bound of the primary CI is $\le 0$, Gate 4 (`primary_net_effect_gate`) fails under Step 4.
* **Formal Disposition:** **`INCONCLUSIVE`** (`step_4_statistical_uncertainty`).

### Governing Research Conclusion

The empirical evidence from the preregistered validation partition demonstrates:
1. **Positive Gross Edge & Breadth:** The early-to-late momentum signal produced positive gross returns (+7.46 bps, 67.97% win rate), positive net returns after 2 bps/side friction (+3.46 bps), and positive net performance across 10 of 15 ETFs (66.67% breadth).
2. **Statistically Significant Uplift:** Relative to direction-matched non-event baselines, the signal demonstrated a statistically significant uplift (+6.44 bps, 95% CI $[+0.44\text{ bps}, +12.14\text{ bps}]$).
3. **Primary Net Statistical Uncertainty:** Because the 95% session-date clustered confidence interval for the primary net return crosses zero ($-2.02$ bps lower bound), the strict preregistered criterion for statistical certainty is not satisfied.
4. **Governing Status:** Under the locked research protocol, the hypothesis is classified as **`INCONCLUSIVE`** due to statistical uncertainty. It is **not supported** and **not rejected**.

---

## 6. Holdout Partition Quarantine

* **Status:** **`unread_not_acquired`**
* **Holdout Market Data:**
  * **NOT ACQUIRED**
  * **NOT READ**
  * **NOT PARSED**
  * **NOT EVALUATED**
* **Zero Provider Calls:** Exactly 0 provider calls were made for July or August 2026.
* **Governance Invariant:** Because validation did not earn `supported` (disposition is `inconclusive`), holdout access is strictly prohibited. The holdout partition remains completely sealed, unread, and unacquired.

---

## 7. Artifact Bundle Lineage & Checksums

The full evaluator bundles were copied from the external `$RUN_ROOT` to the repository under [`docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/`](artifacts/DAYTRADE-002C-CORR-001B-v1/):

* **Execution Plan:** `$RUN_ROOT/execution-plan.json` (SHA-256: `e0022b3f40c3d9e23cc014380d3c4cd5c8005bc3943744df1c809f5c9bac4c2a`)
* **Development Bundle Checksum:** `checksums.sha256` (SHA-256: `c756f5d7efa4d63cdc8f5574623667432507a239d8397da2099b4bea79287da8`)
* **Validation Bundle Checksum:** `checksums.sha256` (SHA-256: `b28a43ad3c775afe999ad67516948a57d24bb57d9e3cabc8d1d2a25b8e9a3805`)
* **Evidence Index:** `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/evidence-index.json`

### Validation Bundle Artifact Checksums

```text
72d54e48227b7fbf1dd0ba6da9e17b3bc3ff6c4004944ec1c6d32eb7a13bfd3f  baseline_summary.csv
ec05c4860b73b22cf4b6e5108f2bf52c2fe45c99d2551bfefeaec797669bb37d  bootstrap.json
6f49488e09f5a9cf2996e382d6342898b846e42bca7e8c37d800958fa1c47942  data_quality.csv
e47854eb1308ea225bf9c9a5fb181ceb7ce761823eb9dcf2634d0b0051e73f27  direction.csv
265c7112028fa5d2c88fbf386c91a7e289bfdd140882e569992c90bc8e5cfc9b  events.csv
a40498bfe1be44e1379eb43fc80d60d2bbf441fb742fc7d6ccb236102aa64f26  freeze.json
8f53812897a69f693b90b60d0480555e72211246c7452659351efa0ce4159e70  manifest.lock.json
2ff7e4eb1bc1f0ae0924967a544c278912d8a570081d451cb0cb630fa986b627  metrics.json
87c4769062ec1725b86ea7641f39f21d3a660a5df636eb01c2cb1a3962b7858c  monthly.csv
dfc3d4ee78906be753d0473e6d8a221f52da3f67232231e3427ec689a7fb3ee1  per_etf.csv
681f2fcb9f5f001097fa21360098dfcf5cf36605be533f81e3a2468305c4f2bb  report.md
4aa4d852bb071e6268f776269eb87ca43b0ba10cbe7e6fbcba86c47cbbe8c8cb  spec.lock.json
28bc325c3fe5d63f03b879aeb6990eb91708892f39281a8b9e672ce346795f9d  study.json
```

---

## 8. Known Non-Calculation Artifact Metadata Defect

During independent post-execution review of PR #98, one non-calculation artifact metadata defect was identified in the emitted artifact bundles:

* **Emitted Value:** `provider_provenance_summary.status = "synthetic_fixtures_only"` in `development/metrics.json` and `validation/metrics.json`.
* **Root Cause:** A hardcoded label string in legacy evaluator code (`tradex/research/daytrade_momentum/metrics.py`) carried over from early offline testing and was frozen into the evaluator before execution.
* **Authoritative Lineage Verification:**
  * Both development and validation executions operated strictly on real preholdout Alpaca SIP market data.
  * Verified dataset manifest SHA-256: `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`.
  * Preserved runtime provenance in `study.json.provenance`:
    * `feed`: `"sip"`
    * `provider`: `"alpaca"`
    * `evaluator_code_sha`: `"770a1a66382351dd63b9245c50bed0c1d92f3ca1"`
    * `run_id`: `"daytrade_002c_corr_001b_reexecution"`
  * Authoritative `manifest.lock.json` and `freeze.json` record the exact verified preholdout files.
* **Impact Assessment:**
  * **Calculation Impact:** NONE. Return, uplift, bootstrap CI, and event detection calculations are completely independent of this label.
  * **Dataset Integrity Impact:** NONE. Reused exact preholdout bytes matching the verified manifest.
  * **Disposition Impact:** NONE. Development disposition (`REJECTED`) and validation disposition (`INCONCLUSIVE`) are unchanged.
  * **Rerun Requirement:** NONE. Rerunning development or validation is prohibited and scientifically unjustified.
* **Remediation & Governance Tracking:**
  * Emitted artifact bundles (`metrics.json`) remain immutable audit records and are not rewritten.
  * Disclosed in `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/evidence-index.json` under `artifact_metadata_defects`.
  * Future evaluator code maintenance should correct the hardcoded label string prior to any subsequent authorized empirical study.

---

## 9. Research Limitations & Governance Invariants

1. **Evidence Confidence Cap:** Formally capped at `limited_but_usable_evidence` under the locked specification.
2. **Frozen Universe:** Evaluated exclusively on the locked 15-ETF universe (`XLK`, `XLV`, `XLF`, `XLY`, `XLP`, `XLE`, `XLI`, `XLB`, `XLU`, `XLRE`, `XLC`, `SPY`, `QQQ`, `IWM`, `DIA`).
3. **Single Regime Window:** Evaluated only across the February–June 2026 market window; no multi-year replication.
4. **Post-Hoc Conception Boundary:** DAYTRADE-002 was conceived after DAYTRADE-001 results were known; no 2025 observations count as confirmatory evidence.
5. **Fixed Cost Model:** Primary returns assume fixed 2 bps/side friction. Higher friction (5 bps/side) yields negative net returns ($-2.54$ bps in validation).
6. **No Durable Alpha Claim:** The validation result is `inconclusive`; no claim of durable alpha or production viability is made.
7. **Production Promotion Ineligible:** `production_promotion_eligible = false`. Live trading, automated order placement, and live alert delivery remain strictly unauthorized.
8. **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.
