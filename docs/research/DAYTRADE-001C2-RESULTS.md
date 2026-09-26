# DAYTRADE-001C2 — Real-Data Reversal Study Execution Results

This document records the empirical results of the bounded real-data execution of the locked `DAYTRADE-001B` 1-minute extreme downside reversal study.

* **Task ID:** `DAYTRADE-001C2`
* **Classification:** Research-only real-data execution (zero production impact)
* **Execution Date:** 2026-09-26
* **Evaluator Base Commit SHA:** `1b96751c0c62043bd3cd2af0b702c7757842eb7d` (merge commit of PR #88 / `DAYTRADE-001C1`)
* **Canonical Specification:** `docs/research/specs/DAYTRADE-001B-v1.json`
* **Locked Spec SHA-256:** `0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620`
* **Evidence Confidence Cap:** `limited_but_usable_evidence`
* **Production Promotion Eligible:** `False`
* **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 1. Study Identity and Contract

| Dimension | Specification Value |
|---|---|
| **Task ID** | `DAYTRADE-001C2` |
| **Evaluator Code SHA** | `1b96751c0c62043bd3cd2af0b702c7757842eb7d` (clean frozen evaluator) |
| **Locked Spec SHA-256** | `0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620` |
| **Market Data Provider** | Alpaca Market Data API (`alpaca`) |
| **Market Data Feed** | `sip` (Securities Information Processor consolidated tape, no fallback) |
| **Timeframe & Adjustment** | `1Min`, split-adjusted only (`split`), cash dividends excluded |
| **Exchange Calendar** | `XNYS` regular trading sessions (09:30–16:00 ET; early closes excluded) |
| **Timezone** | `America/New_York` |
| **Universe** | Fixed 30-symbol Dow Jones Industrial Average research universe (`tradex.watchlists.presets.DOW30`) |
| **Study Dates** | Warm-up: `2024-12-02` through `2025-01-01`<br>Development: `2025-01-02` through `2025-06-30`<br>Validation: `2025-07-01` through `2025-09-30`<br>Holdout (conditional): `2025-10-01` through `2025-12-31` |
| **Evidence Confidence Cap** | `limited_but_usable_evidence` (retrospective May 2026 Dow snapshot applied to 2025 data) |
| **Production Promotion** | Ineligible (`production_promotion_eligible = false`) |

---

## 2. Dataset Evidence & Provenance

The preholdout dataset partition (warm-up, development, validation through September 30, 2025) was acquired exactly once using the frozen `build-dataset` command against Alpaca SIP.

* **Private Dataset Root:** `~/.tradex/research/daytrade_001b_c2_v1/` (external to all TradeX repositories and worktrees; raw/normalized OHLCV files are strictly private and excluded from Git).
* **Pre-Holdout Manifest Path:** `preholdout/manifest.lock.json`
* **Pre-Holdout Manifest SHA-256:** `80bd6b0e9b89e1b8cf578625c795aeec2730f3e9e31de0a01de8075e8f165884`
* **Logical Provider Requests:** `300` (10 monthly chunks across 30 symbols)
* **HTTP Pages Retrieved:** `394` (average ~1.3 pages per monthly chunk; all chunks well within the 100-page limit)
* **HTTP Retries:** `0`
* **HTTP Errors / Safe Errors:** `0`
* **Malformed Timestamps:** `0`
* **Pagination Complete:** `True`
* **Represented Universe Symbols:** `30` of 30 locked symbols (`MMM`, `AXP`, `AMGN`, `AMZN`, `AAPL`, `BA`, `CAT`, `CVX`, `CSCO`, `KO`, `DIS`, `GS`, `HD`, `HON`, `IBM`, `JNJ`, `JPM`, `MCD`, `MRK`, `MSFT`, `NKE`, `NVDA`, `PG`, `CRM`, `SHW`, `TRV`, `UNH`, `V`, `VZ`, `WMT`).
* **Source Bar Files:** Exactly 30 CSV files in `bars/` with verified individual SHA-256 digests.
* **Survivorship Limitation:** The 30-symbol constituent panel reflects a May 2026 Dow snapshot applied retrospectively to 2024–2025 market data. Even if all statistical gates had passed, the evidence confidence rating remains strictly capped at `limited_but_usable_evidence`.

---

## 3. Development Split (Diagnostic Only)

Development was executed once using the frozen evaluator and freeze state. Development is non-gating and diagnostic only; it caused zero parameter, threshold, code, or methodology modifications.

* **Split Period:** `2025-01-02` through `2025-06-30` (122 regular sessions)
* **Disposition:** **`rejected`**
* **Disposition Step:** `step_3_directional_hypothesis_failure`
* **Disposition Reason:** Directional hypothesis failure: primary_mean_net_-0.000545_le_0; mean_uplift_-0.000150_le_0; ticker_breadth_6.7%_below_60.0%

### Core Development Metrics

| Metric | Value |
|---|---|
| **Eligible Minute Count** | 1,317,083 |
| **Event Count** | 2,046 |
| **Represented Tickers** | 30 |
| **Maximum Single-Ticker Concentration** | 5.08% (V: 104 events; 5.083088954056696%) |
| **Overlapping Event Count & Rate** | 1,816 events (88.76% overlapping) |
| **Mean Gross Forward Return (1m)** | -0.000145 (-1.45 bps) |
| **Mean Gross Forward Return (2m)** | -0.000313 (-3.13 bps) |
| **Mean Gross Forward Return (5m)** | -0.000364 (-3.64 bps) |
| **Median Gross Forward Return (1m)** | -0.000093 (-0.93 bps) |
| **Mean Net Return @ 0 bps/side** | -0.000145 (-1.45 bps) |
| **Mean Net Return @ 2 bps/side (Primary)** | -0.000545 (-5.45 bps) |
| **Mean Net Return @ 5 bps/side (Stressed)** | -0.001145 (-11.45 bps) |
| **Median Net Return @ 2 bps/side** | -0.000493 (-4.93 bps) |
| **Win Rate (1m gross)** | 47.31% |
| **Win Rate (2m gross)** | 47.36% |
| **Win Rate (5m gross)** | 49.44% |
| **Matched Baseline Mean Return** | -0.000395 (-3.95 bps) |
| **Matched Baseline Median Return** | -0.000393 (-3.93 bps) |
| **Event-minus-Baseline Uplift (Mean)** | -0.000150 (-1.50 bps) |
| **Event-minus-Baseline Uplift (Median)** | -0.000138 (-1.38 bps) |
| **Represented Tickers with Positive Net Mean** | 2 of 30 (6.67%; only AAPL and NKE positive) |
| **Primary Net Return 95% Clustered CI** | [-0.000718, -0.000376] (-7.18 bps to -3.76 bps; computable) |
| **Baseline Uplift 95% Clustered CI** | [-0.000325, +0.000017] (-3.25 bps to +0.17 bps; computable) |
| **Excluded Ticker-Sessions (Data Quality)** | 166 of 3,660 (4.54% <= 5.0% limit; exact: 4.53551912568306%) |

### Development Data-Quality Diagnostic

For completeness, development's canonical data-quality evidence is:
* **Total regular trading sessions:** 122
* **Total ticker-sessions:** 3,660 (122 sessions x 30 tickers)
* **Excluded ticker-sessions:** 166
* **Exclusion rate:** 4.53551912568306% (Gate: **PASS** because 4.54% <= 5.0%)
* **Exclusions by ticker:**
  * `TRV`: 82 / 122 sessions excluded
  * `SHW`: 71 / 122 sessions excluded
  * `GS`: 5 / 122 sessions excluded
  * `AMGN`: 4 / 122 sessions excluded
  * `CAT`: 2 / 122 sessions excluded
  * `AXP`: 1 / 122 sessions excluded
  * `HON`: 1 / 122 sessions excluded
* **Missing bar criterion:** All 166 exclusions were due to the locked missing-bar criterion (`missing_rate > 5.0%`).
* **Concentration:** `TRV` and `SHW` account for 153 of 166 exclusions (92.17%).
* **Integrity:** Duplicates contributed no material exclusions; malformed timestamps = 0; provider retrieval errors = 0; pagination completed successfully.
* **Characterization:** Strictly characterized as ticker-concentrated missing-minute coverage without claiming unevidenced causal mechanisms.

---

## 4. Validation Split (Formal Gating Gate)

Validation was executed once under the exact frozen evaluator (`1b96751c0c62043bd3cd2af0b702c7757842eb7d`) and verified freeze record (`freeze.json`).

* **Split Period:** `2025-07-01` through `2025-09-30` (63 regular sessions)
* **Disposition:** **`inconclusive`**
* **Disposition Step:** `step_2_evidence_sufficiency`
* **Disposition Reason:** Evidence sufficiency gate failure: split_excluded_sessions_7.83%_above_5.0%

### Locked Validation and Data-Quality Gate Evaluations

| Gate | Criterion | Threshold | Result | Details |
|---|---|---|---|---|
| **1. Sample Gate** | Eligible event count and breadth | $\ge 300\text{ events}$ across $\ge 15\text{ tickers}$ | **PASS** | 899 events across 30 represented tickers |
| **2. Concentration Gate** | Maximum single-ticker contribution | No single ticker $> 15.0\%$ of validation events | **PASS** | Maximum contribution: 5.01% (45 events, DIS) |
| **3. Data-Quality Gate** | Ticker-session exclusion rate | $\le 5.0\%$ excluded sessions in split | **FAIL** | 148 of 1,890 sessions excluded (7.83% $> 5.0\%$) |
| **4. Primary Net-Effect Gate** | Mean 1m net return @ 2 bps/side | Mean $> 0$ **and** 95% Clustered CI lower bound $> 0$ | **FAIL** | Mean: -0.000250 (-2.50 bps); CI: `non_computable` (replicate 202 empty baseline for TRV 09:33) |
| **5. Baseline-Uplift Gate** | Mean 1m event-minus-baseline return | Mean $> 0$ **and** 95% Clustered CI lower bound $> 0$ | **FAIL** | Mean: +0.000156 (+1.56 bps); CI: `non_computable` (replicate 202 empty baseline) |
| **6. Ticker Breadth Gate** | Cross-sectional consistency | $\ge 60.0\%$ tickers with positive mean net return | **FAIL** | 8 of 30 tickers positive (26.67% $< 60.0\%$) |

### Core Validation Metrics

| Metric | Value |
|---|---|
| **Eligible Minute Count** | 664,350 |
| **Event Count** | 899 |
| **Represented Tickers** | 30 |
| **Maximum Single-Ticker Concentration** | 5.01% (DIS: 45 events; 5.005561735261402%) |
| **Overlapping Event Count & Rate** | 749 events (83.31% overlapping) |
| **Mean Gross Forward Return (1m)** | +0.000150 (+1.50 bps) |
| **Mean Gross Forward Return (2m)** | +0.000404 (+4.04 bps) |
| **Mean Gross Forward Return (5m)** | +0.000347 (+3.47 bps) |
| **Median Gross Forward Return (1m)** | +0.000134 (+1.34 bps) |
| **Mean Net Return @ 0 bps/side** | +0.000150 (+1.50 bps) |
| **Mean Net Return @ 2 bps/side (Primary)** | -0.000250 (-2.50 bps) |
| **Mean Net Return @ 5 bps/side (Stressed)** | -0.000850 (-8.50 bps) |
| **Median Net Return @ 2 bps/side** | -0.000266 (-2.66 bps) |
| **Win Rate (1m gross)** | 53.28% |
| **Win Rate (2m gross)** | 56.73% |
| **Win Rate (5m gross)** | 54.39% |
| **Matched Baseline Mean Return** | -0.000405 (-4.05 bps) |
| **Matched Baseline Median Return** | -0.000397 (-3.97 bps) |
| **Event-minus-Baseline Uplift (Mean)** | +0.000156 (+1.56 bps) |
| **Event-minus-Baseline Uplift (Median)** | +0.000131 (+1.31 bps) |
| **Represented Tickers with Positive Net Mean** | 8 of 30 (26.67%: CRM, CSCO, HON, IBM, MRK, NKE, PG, UNH) |
| **Primary Net Return 95% Clustered CI** | `non_computable` (`replicate_202_empty_baseline_for_TRV_09:33`) |
| **Baseline Uplift 95% Clustered CI** | `non_computable` (`replicate_202_empty_baseline_for_TRV_09:33`) |
| **Excluded Ticker-Sessions (Data Quality)** | 148 of 1,890 (7.83% $> 5.0\%$ limit; exact: 7.830687830687831%) |

### Validation Data-Quality Diagnostic

For auditability, the canonical validation data-quality diagnostic is:
* **Total regular trading sessions:** 63
* **Total ticker-sessions:** 1,890 (63 sessions x 30 tickers)
* **Excluded ticker-sessions:** 148
* **Exclusion rate:** 7.830687830687831% (Gate: **FAIL** because 7.83% > 5.0%)
* **Exclusions by ticker:**
  * `TRV`: 53 / 63 sessions excluded
  * `GS`: 32 / 63 sessions excluded
  * `SHW`: 29 / 63 sessions excluded
  * `AMGN`: 26 / 63 sessions excluded
  * `MMM`: 4 / 63 sessions excluded
  * `CAT`: 3 / 63 sessions excluded
  * `AXP`: 1 / 63 sessions excluded
* **Missing bar criterion:** All 148 exclusions were due to the locked missing-bar criterion (`missing_rate > 5.0%`).
* **Concentration:** The four largest contributors (`TRV` + `GS` + `SHW` + `AMGN`) account for 140 of the 148 exclusions (94.59%).
* **Integrity:** Duplicates contributed no material exclusions; malformed timestamps = 0; provider retrieval errors = 0; pagination completed successfully.
* **Characterization:** Strictly characterized as `ticker-concentrated missing-minute coverage`. In accordance with scientific governance, no causal reason (such as low liquidity, provider defect, provider outage, or exchange issue) is claimed without a separately authorized investigation.
* **Formal disposition impact:** This diagnostic details coverage distribution but does not alter the formal locked disposition of `inconclusive`.

---

## 5. Holdout Partition Decision

Under Section 14 of the locked study protocol:
* Conditional holdout acquisition and evaluation require validation to earn the disposition **`supported`**.
* Validation earned the formal disposition **`inconclusive`** (failing the data-quality sufficiency gate at Step 2; eligible observations also failed the primary net return gate, baseline bootstrap gate, and breadth gate).

**Decision:**
* **Holdout status:** `unread_not_acquired`
* Holdout data (`2025-10-01` through `2025-12-31`) **remained unread and was not acquired because validation did not earn supported.**
* Zero provider calls were made for the October–December 2025 period.
* The holdout partition directory (`holdout/`) does not exist and was never created or populated.

---

## 6. Research Conclusion

1. **Formal Study Conclusion:** Development rejected the hypothesis under the locked gates. Validation did not establish support and formally resolved to **`inconclusive`** because the preregistered data-quality sufficiency gate failed (`148 / 1,890 = 7.830687830687831% > 5.0%`). Within the eligible validation observations, the primary 1-minute mean return was negative after the locked 2 bps/side friction and ticker breadth was below the preregistered requirement, but the formal validation conclusion remains strictly **`inconclusive`**. Holdout therefore remained unread and unacquired (`holdout_status = unread_not_acquired`).
2. **Development Split Finding (Diagnostic):** In the development partition (January–June 2025; 122 regular sessions), extreme 1-minute drops continued downward on average (mean 1-minute gross return of -1.45 bps, net -5.45 bps at 2 bps/side friction), performing worse than matched non-event baselines (uplift of -1.50 bps). Only 2 of 30 tickers (6.67%: AAPL and NKE) exhibited positive net returns. Development formally rejected the directional hypothesis at `step_3_directional_hypothesis_failure`.
3. **Validation Descriptive Observations:** In the validation partition (July–September 2025; 63 regular sessions), descriptive observation of eligible events showed a slight gross positive bounce on average (+1.50 bps gross), but this was consumed by realistic execution friction (mean net return of -2.50 bps at 2 bps/side). Only 8 of 30 tickers (26.67%: CRM, CSCO, HON, IBM, MRK, NKE, PG, UNH) exhibited positive net returns. However, because validation failed the Step 2 data-quality sufficiency gate, these descriptive observations do not override or alter the formal `inconclusive` disposition precedence.
4. **Data-Quality Boundary:** Data-quality session exclusions in validation (7.83%) exceeded the preregistered 5.0% tolerance, driven primarily by ticker-concentrated missing-minute coverage across four tickers (TRV, GS, SHW, AMGN accounting for 140 of 148 exclusions).
5. **No Parameter Fishing or Retesting:** In strict adherence to scientific integrity principles, no parameters, thresholds, horizons, costs, or data filters were adjusted after observing development or validation outcomes.

---

## 7. Production Boundary Invariant

* **Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains preserved.
* **No Trading Behavior Changes:** No production signals, scores, indicators, weights, thresholds, rankings, eligibility, alerts, or dashboard displays have been modified.
* **Zero Production Promotion:** This research study authorizes zero promotion or operational deployment. Any future strategy proposal or promotion requires a separate, independently pre-registered research plan and explicit approval from Gary Yang.
