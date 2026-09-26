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

* **Split Period:** `2025-01-02` through `2025-06-30` (124 regular sessions)
* **Disposition:** **`rejected`**
* **Disposition Step:** `step_3_directional_hypothesis_failure`
* **Disposition Reason:** Directional failure: primary mean net return (-5.45 bps) <= 0, mean baseline uplift (-1.50 bps) <= 0, positive ticker breadth (6.67%) < 60.0%

### Core Development Metrics

| Metric | Value |
|---|---|
| **Eligible Minute Count** | 1,317,083 |
| **Event Count** | 2,046 |
| **Represented Tickers** | 30 |
| **Maximum Single-Ticker Concentration** | 5.08% (BA: 104 events) |
| **Overlapping Event Count & Rate** | 1,816 events (88.76% overlapping) |
| **Mean Gross Forward Return (1m)** | -0.000145 (-1.45 bps) |
| **Mean Gross Forward Return (2m)** | -0.000164 (-1.64 bps) |
| **Mean Gross Forward Return (5m)** | -0.000282 (-2.82 bps) |
| **Median Gross Forward Return (1m)** | -0.000078 (-0.78 bps) |
| **Mean Net Return @ 0 bps/side** | -0.000145 (-1.45 bps) |
| **Mean Net Return @ 2 bps/side (Primary)** | -0.000545 (-5.45 bps) |
| **Mean Net Return @ 5 bps/side (Stressed)** | -0.001145 (-11.45 bps) |
| **Median Net Return @ 2 bps/side** | -0.000478 (-4.78 bps) |
| **Win Rate (1m gross)** | 47.31% |
| **Win Rate (2m gross)** | 48.09% |
| **Win Rate (5m gross)** | 48.09% |
| **Matched Baseline Mean Return** | -0.000395 (-3.95 bps) |
| **Matched Baseline Median Return** | -0.000399 (-3.99 bps) |
| **Event-minus-Baseline Uplift (Mean)** | -0.000150 (-1.50 bps) |
| **Event-minus-Baseline Uplift (Median)** | +0.000321 (+3.21 bps) |
| **Represented Tickers with Positive Net Mean** | 2 of 30 (6.67%; only CRM and UNH positive) |
| **Primary Net Return 95% Clustered CI** | [-0.000718, -0.000376] (-7.18 bps to -3.76 bps; computable) |
| **Baseline Uplift 95% Clustered CI** | [-0.000325, +0.000017] (-3.25 bps to +0.17 bps; computable) |
| **Excluded Ticker-Sessions (Data Quality)** | 108 of 3,720 (2.90% <= 5.0% limit) |

---

## 4. Validation Split (Formal Gating Gate)

Validation was executed once under the exact frozen evaluator (`1b96751c0c62043bd3cd2af0b702c7757842eb7d`) and verified freeze record (`freeze.json`).

* **Split Period:** `2025-07-01` through `2025-09-30` (63 regular sessions)
* **Disposition:** **`inconclusive`**
* **Disposition Step:** `step_2_evidence_sufficiency`
* **Disposition Reason:** Evidence sufficiency gate failure: split_excluded_sessions_7.83%_above_5.0%

### Five Locked Validation Gates

| Gate | Criterion | Threshold | Result | Details |
|---|---|---|---|---|
| **1. Sample Gate** | Eligible event count and breadth | $\ge 300\text{ events}$ across $\ge 15\text{ tickers}$ | **PASS** | 899 events across 30 represented tickers |
| **2. Concentration Gate** | Maximum single-ticker contribution | No single ticker $> 15.0\%$ of validation events | **PASS** | Maximum contribution: 5.01% (45 events, BA) |
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
| **Maximum Single-Ticker Concentration** | 5.01% (BA: 45 events) |
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
| **Excluded Ticker-Sessions (Data Quality)** | 148 of 1,890 (7.83% $> 5.0\%$ limit) |

---

## 5. Holdout Partition Decision

Under Section 14 of the locked study protocol:
* Conditional holdout acquisition and evaluation require validation to earn the disposition **`supported`**.
* Validation earned the disposition **`inconclusive`** (failing the data-quality sufficiency gate, primary net return gate, baseline bootstrap gate, and breadth gate).

**Decision:**
* **Holdout status:** `unread_not_acquired`
* Holdout data (`2025-10-01` through `2025-12-31`) **remained unread and was not acquired because validation did not earn supported.**
* Zero provider calls were made for the October–December 2025 period.
* The holdout partition directory (`holdout/`) does not exist and was never created or populated.

---

## 6. Research Conclusion

1. **No Edge Found After Friction:** In the development partition (January–June 2025), extreme 1-minute drops continued downward on average (mean 1-minute gross return of -1.45 bps, net -5.45 bps at 2 bps/side friction), performing worse than matched non-event baselines (uplift of -1.50 bps). Only 6.67% of tickers exhibited positive net returns.
2. **Gross Bounces Do Not Clear Execution Costs:** In the validation partition (July–September 2025), a slight gross positive reversal occurred on average (+1.50 bps gross), but this was completely consumed by realistic execution friction (-2.50 bps net at 2 bps/side). Only 26.67% of tickers exhibited positive net returns.
3. **Data Quality Sufficiency Limit:** The validation split experienced a 7.83% session exclusion rate (above the 5.0% threshold), primarily driven by missing bars in single-ticker sessions.
4. **Overall Empirical Finding:** The empirical data does not support the hypothesis that extreme completed 1-minute negative returns in Dow 30 equities provide an exploitable positive bounce after realistic execution friction.
5. **No Parameter Fishing or Retesting:** In strict adherence to scientific integrity principles, no parameters, thresholds, horizons, costs, or data filters were adjusted after observing development or validation outcomes.

---

## 7. Production Boundary Invariant

* **Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains preserved.
* **No Trading Behavior Changes:** No production signals, scores, indicators, weights, thresholds, rankings, eligibility, alerts, or dashboard displays have been modified.
* **Zero Production Promotion:** This research study authorizes zero promotion or operational deployment. Any future strategy proposal or promotion requires a separate, independently pre-registered research plan and explicit approval from Gary Yang.
