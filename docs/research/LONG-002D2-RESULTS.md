# LONG-002D2: Incremental Ranking Value of Relative Volume Beyond Frozen VAM5 — Empirical Results

- **Task ID:** `LONG-002D2-INCREMENTAL-RERANK-001`
- **Execution Run ID:** `2026-09-28-143047`
- **Execution Date:** 2026-09-28
- **Preregistration Spec SHA-256:** `db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8` (`docs/research/specs/LONG-002D2-v1.json`)
- **Preregistration Commit SHA:** `494caa8df3e60bae15e5015ad98a42a13eb109f3`
- **Spec Immutability:** Verified; `git diff 494caa8df3e60bae15e5015ad98a42a13eb109f3..HEAD -- docs/research/specs/LONG-002D2-v1.json` is clean.
- **Stage C Input Dataset:** Run ID `2026-09-27-161243` (code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`)
- **Stage D1 Input Dataset:** Run ID `2026-09-28-003539` (spec SHA `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381`)
- **Branch:** `antigravity/long-002d2-incremental-rerank`
- **Primary Candidate Disposition:** `NOT_SUPPORTED`
- **Status:** Execution Completed & Verified; Ready for Gary/ChatGPT Post-Run Review

---

## 1. Executive Summary & Boundaries

This document reports the empirical findings of **LONG-002D2**, a controlled, coverage-matched development-only reranking experiment testing whether `relative_volume_20` adds incremental top-of-list predictive ranking value beyond the frozen Stage C baseline comparator `volatility_aware_momentum_5` (VAM5) for the retained primary endpoint: **clean +10% within 10 trading sessions**.

### Key Empirical Finding
- **Primary Candidate (`relative_volume_20`) Disposition: `NOT_SUPPORTED`**
  Reranking the frozen VAM5 top-quartile candidate pool by `relative_volume_20` resulted in a statistically significant **reduction** in precision compared to selecting the exact same number of securities by frozen VAM5 rank alone:
  - **Candidate Precision:** **12.4321%** (9,499 clean events / 76,407 selected observations)
  - **Matched VAM5 Baseline Precision:** **15.3533%** (11,731 clean events / 76,407 selected observations)
  - **Absolute Precision Delta:** **-2.9212 percentage points** (**-2.92 pp**, precision ratio **0.8097**)
  - **Incremental Clean Events:** **-2,232 clean events** at identical coverage ($K(date)$ matched daily)
  - **21-Session Block Bootstrap 95% CI:** `[-0.0352, -0.0235]` (Upper bound $\le 0.0$)
  - **42-Session Block Bootstrap 95% CI:** `[-0.0352, -0.0239]` (Median: `-0.0291`)
  - **Annual Stability:** **0 out of 5 development years** exhibited positive delta (negative delta in 2016, 2017, 2018, 2019, and 2020).
  - Under the preregistered decision rules, because the 21-session block bootstrap 95% CI upper bound is $\le 0$ and the pooled delta is negative with $\le 2$ positive years, the empirical status is conclusively **`NOT_SUPPORTED`**.

- **Secondary Challenger (`sma20_slope_5`) Disposition: `descriptive_underperformance`**
  Reranking by the 5-day slope of the 20-day SMA also underperformed matched VAM5:
  - **Challenger Precision:** **11.9950%** (9,165 clean events / 76,407 selected observations)
  - **Absolute Precision Delta:** **-3.3583 percentage points** (**-3.36 pp**, precision ratio **0.7813**)
  - **21-Session Block Bootstrap 95% CI:** `[-0.0415, -0.0258]`
  - **Annual Stability:** **0 out of 5 development years** positive.
  - Per preregistration, this challenger is purely descriptive and did not alter the primary relative-volume status.

### Research Scope & Governance Quarantines
- **Controlled Coverage-Matched Reranking Only:** On each date, the candidate and matched baseline selected exactly $K(date)$ securities ($K(date) = \text{count of frozen VAM5 top-10 observations}$).
- **No Model Fitting or Parameter Tuning:** No coefficients, weights, thresholds, lookback horizons, or feature combinations were fitted or optimized.
- **Development Split Only:** All analyses were strictly confined to the development split (`2016-01-01` to `2020-12-31`) at the `20:30` ET snapshot (982 trading sessions, 758,731 observations).
- **Strict Data Quarantines:** Validation (`2021–2022`), holdout (`2023–2025`), and shadow (`2026+`) splits remained completely unopened, unaccessed, and quarantined. Zero rows loaded.
- **Zero Live Network Calls:** Zero provider or network calls were made. 100% of data was loaded from verified local Parquet artifacts.
- **Production Status:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.

---

## 2. Upstream Input Integrity & Cryptographic Audit

All input datasets were verified byte-for-byte against the locked preregistered checksums before execution:

| Dataset Artifact | Relative Path | Rows | SHA-256 Digest | Status |
|---|---|---:|---|:---:|
| D1 Feature Table | `data/research/long_002d1/feature_table.parquet` | 758,731 | `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` | **VERIFIED MATCH** |
| Stage C Baseline Outputs | `data/research/long_002c/baseline_comparator_outputs.parquet` | 758,731 | `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` | **VERIFIED MATCH** |
| D2 Preregistration Spec | `docs/research/specs/LONG-002D2-v1.json` | — | `db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8` | **LOCKED & VERIFIED** |

### Integrity & Contract Gate Audit
- **Feature Table Rows:** Exactly 758,731.
- **Joined Dataset Rows:** Exactly 758,731 (1:1 inner join on `immutable_security_id`, `as_of_date`, `cutoff_time`).
- **Join Key Uniqueness:** Verified unique on both sides; zero duplicates.
- **Cutoff Time:** 100% of observations evaluated at `20:30` ET. Zero morning (09:00) observations.
- **Date Boundary Enforcement:** Earliest date `2016-12-30`, latest date `2020-11-23` (all within development window `[2016-01-01, 2020-12-31]`). Zero validation, holdout, or shadow rows loaded.
- **Outcome Labels:** 100% non-null boolean values in `clean_target_reached`.
- **Top-25 Pool Invariant:** On 100% of evaluation dates, candidate pool size exceeded $K(date)$; 100% of candidate picks were drawn strictly from the frozen VAM5 top-quartile pool.
- **Daily Coverage Matching:** On 100% of 982 dates, `candidate_selected_count == matched_vam5_selected_count == K(date)`.

---

## 3. Primary Candidate Results: `relative_volume_20`

- **Hypothesized Direction:** HIGHER (stocks with higher volume relative to prior 20-session median selected first).
- **Candidate Pool:** Securities with frozen VAM5 `top_25_flag == True` on each date.
- **Selection Count:** Exactly $K(date)$ securities on each date (identical to matched VAM5).

### Pooled Performance Comparison

| Metric | Official Full-Dev VAM5 Reference | Matched VAM5 Comparator | Candidate Reranker (`relative_volume_20`) | Delta / Ratio |
|---|:---:|:---:|:---:|:---:|
| **Population Observations** | 758,731 | 758,731 | 758,731 | — |
| **Common Clean Events** | 67,257 (8.8644%) | 67,257 (8.8644%) | 67,257 (8.8644%) | — |
| **Selected Observations** | 76,407 (Top 10%) | 76,407 | 76,407 | **Equal Coverage (100.0%)** |
| **Selected Clean Events** | 11,731 | 11,731 | 9,499 | **-2,232 events** |
| **Precision (Clean Rate)** | 15.3533% | 15.3533% | 12.4321% | **-2.9212 pp** |
| **Lift over Base Rate** | 1.7320x | 1.7320x | 1.4025x | **0.8097x ratio** |
| **Selection Overlap** | — | — | 34,399 / 76,407 | **45.02% overlap** |

*Note: Because candidate coverage within the frozen VAM5 top-25 pool is 100.0%, the candidate-specific matched VAM5 comparator is identical to the official full-development VAM5 top-10 reference.*

### Annual Performance Breakdown

| Year | Eval Sessions | Selected Obs ($K$) | Matched VAM5 Clean | Matched VAM5 Precision | Candidate Clean | Candidate Precision | Absolute Delta | Precision Ratio | Positive Delta? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| **2016** | 1 | 54 | 5 | 9.2593% | 3 | 5.5556% | **-3.7037 pp** | 0.6000 | No |
| **2017** | 251 | 14,885 | 1,267 | 8.5119% | 957 | 6.4293% | **-2.0826 pp** | 0.7553 | No |
| **2018** | 251 | 21,250 | 2,669 | 12.5600% | 2,019 | 9.5012% | **-3.0588 pp** | 0.7565 | No |
| **2019** | 252 | 21,848 | 3,090 | 14.1432% | 2,353 | 10.7699% | **-3.3733 pp** | 0.7615 | No |
| **2020** | 227 | 18,370 | 4,700 | 25.5852% | 4,167 | 22.6837% | **-2.9015 pp** | 0.8866 | No |
| **Total** | **982** | **76,407** | **11,731** | **15.3533%** | **9,499** | **12.4321%** | **-2.9212 pp** | **0.8097** | **0 / 5 Years** |

### Paired Fixed Calendar-Block Bootstrap Results

Paired resamples were generated using non-overlapping calendar blocks with fixed seed `20260928` across 1,000 replicates. On each replicate, candidate precision and matched VAM5 precision were evaluated on the exact same date blocks:

| Block Size | Description | Mean Delta | Median Delta | Std Error | 2.5th Percentile | 97.5th Percentile | 95% Confidence Interval |
|---|---|---:|---:|---:|---:|---:|:---:|
| **21 Sessions** | Primary Block Size | -2.9247 pp | -2.9284 pp | 0.3097 pp | -3.5191 pp | -2.3472 pp | **[-0.0352, -0.0235]** |
| **42 Sessions** | Robustness Block Size | -2.9109 pp | -2.9104 pp | 0.2915 pp | -3.5169 pp | -2.3853 pp | **[-0.0352, -0.0239]** |

The upper bound of the 95% confidence interval is strictly negative (`-2.35 pp`), proving that the observed underperformance is robust to calendar clustering and not an artifact of block size.

---

## 4. Secondary Challenger Results: `sma20_slope_5`

- **Hypothesized Direction:** HIGHER.
- **Context:** In D1, `sma20_slope_5` showed a strong univariate lift (1.2238x) but was heavily collinear with 20-day return ($\rho \approx +0.9190$). Evaluated here as a secondary descriptive comparator under identical reranking rules.

### Pooled Performance Comparison

| Metric | Matched VAM5 Comparator | Challenger Reranker (`sma20_slope_5`) | Delta / Ratio |
|---|:---:|:---:|:---:|
| **Selected Observations** | 76,407 | 76,407 | **Equal Coverage** |
| **Selected Clean Events** | 11,731 | 9,165 | **-2,566 events** |
| **Precision (Clean Rate)** | 15.3533% | 11.9950% | **-3.3583 pp** |
| **Precision Ratio** | 1.0000 | 0.7813 | **0.7813x ratio** |
| **Selection Overlap** | — | 34,326 / 76,407 | **44.93% overlap** |

### Annual Performance Breakdown

| Year | Eval Sessions | Selected Obs ($K$) | Matched VAM5 Precision | Challenger Precision | Absolute Delta | Precision Ratio | Positive Delta? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| **2016** | 1 | 54 | 9.2593% | 3.7037% | **-5.5556 pp** | 0.4000 | No |
| **2017** | 251 | 14,885 | 8.5119% | 5.6433% | **-2.8687 pp** | 0.6630 | No |
| **2018** | 251 | 21,250 | 12.5600% | 9.7553% | **-2.8047 pp** | 0.7767 | No |
| **2019** | 252 | 21,848 | 14.1432% | 9.1221% | **-5.0211 pp** | 0.6450 | No |
| **2020** | 227 | 18,370 | 25.5852% | 23.1737% | **-2.4115 pp** | 0.9057 | No |
| **Total** | **982** | **76,407** | **15.3533%** | **11.9950%** | **-3.3583 pp** | **0.7813** | **0 / 5 Years** |

### Paired Fixed Calendar-Block Bootstrap Results

| Block Size | Mean Delta | Median Delta | Std Error | 2.5th Percentile | 97.5th Percentile | 95% Confidence Interval |
|---|---:|---:|---:|---:|---:|:---:|
| **21 Sessions** | -3.3560 pp | -3.3638 pp | 0.4125 pp | -4.1502 pp | -2.5791 pp | **[-0.0415, -0.0258]** |
| **42 Sessions** | -3.3399 pp | -3.3324 pp | 0.4082 pp | -4.1296 pp | -2.5297 pp | **[-0.0413, -0.0253]** |

Like relative volume, `sma20_slope_5` underperformed matched VAM5 across all 5 development years, with an upper 95% CI bound of `-2.58 pp`.

---

## 5. Descriptive SPY Market-Regime Diagnostics

Unique development dates (982 sessions) were partitioned into three fixed bins based on cross-sectional rank of 20-session SPY return (matching D1 date-ranking semantics):
- **Lower Regime:** Bottom 30% of dates (294 dates, percentile $\le 30.0$)
- **Middle Regime:** Middle 40% of dates (393 dates, $30.0 < \text{percentile} < 70.0$)
- **Upper Regime:** Top 30% of dates (295 dates, percentile $\ge 70.0$)

*Governance Reminder: These diagnostics are strictly descriptive. They did not filter securities, did not alter candidate selection, did not alter candidate direction, and did not affect the primary D2 status.*

### Primary Candidate (`relative_volume_20`) by Regime

| Regime | Dates | Selected Obs ($K$) | Matched VAM5 Precision | Candidate Precision | Absolute Delta | Precision Ratio |
|---|---:|---:|---:|---:|---:|---:|
| **Lower Regime** (SPY bottom 30%) | 294 | 23,404 | 18.4840% | 15.7452% | **-2.7388 pp** | 0.8518 |
| **Middle Regime** (SPY mid 40%) | 393 | 28,750 | 11.6591% | 8.6748% | **-2.9843 pp** | 0.7440 |
| **Upper Regime** (SPY top 30%) | 295 | 24,253 | 16.7113% | 13.6890% | **-3.0223 pp** | 0.8191 |

### Secondary Challenger (`sma20_slope_5`) by Regime

| Regime | Dates | Selected Obs ($K$) | Matched VAM5 Precision | Candidate Precision | Absolute Delta | Precision Ratio |
|---|---:|---:|---:|---:|---:|---:|
| **Lower Regime** (SPY bottom 30%) | 294 | 23,404 | 18.4840% | 15.0444% | **-3.4396 pp** | 0.8139 |
| **Middle Regime** (SPY mid 40%) | 393 | 28,750 | 11.6591% | 8.2922% | **-3.3670 pp** | 0.7112 |
| **Upper Regime** (SPY top 30%) | 295 | 24,253 | 16.7113% | 13.4416% | **-3.2697 pp** | 0.8043 |

**Key Diagnostic Insight:** The negative delta of both candidate rerankers relative to frozen VAM5 is remarkably uniform across all three market regimes (consistently between `-2.7 pp` and `-3.4 pp`). The performance degradation is not confined to bear, chop, or bull environments.

---

## 6. Interpretation & Research Takeaways

1. **Univariate Association Does Not Imply Incremental Conditional Value:**
   In D1, `relative_volume_20` exhibited a positive univariate association (1.1307x top-decile lift, 4/5 positive years). However, when used to rerank stocks that are *already* in the top quartile of the volatility-aware momentum composite (`volatility_aware_momentum_5`), selecting highest-relative-volume stocks displaces higher-ranked VAM5 stocks that have substantially higher clean-event rates.
2. **Dilution of Momentum / ATR Signal:**
   Frozen VAM5 selects names with the highest combined 5-day momentum and ATR movement capacity. In the top quartile, selecting by `relative_volume_20` favors stocks experiencing volume spikes that may correspond to gap openings, late-stage churn, or distribution, rather than clean follow-through.
3. **Collinear Trend Features Suffer the Same Fate:**
   `sma20_slope_5` exhibited the exact same degradation (-3.36 pp delta, 0/5 years positive). Selecting the steepest 20-day SMA slope from the top-quartile pool replaces top-10 VAM5 names with extended or late-stage trends that fail to cleanly expand an additional +10% over the next 10 sessions.
4. **Research Quarantine Integrity:**
   All findings are based solely on development split observations (`2016-01-01` to `2020-12-31`). No validation or holdout data was accessed.

---

## 7. Artifact Catalog & Cryptographic Integrity

All committed summary artifacts have been generated in `docs/research/artifacts/LONG-002D2/2026-09-28-143047/`:

| Artifact File | Byte Size | SHA-256 Digest | Description |
|---|---:|---|---|
| `execution_metadata.json` | 1,375 | `382d3bec1fb5b9cb01e5192fdcab53ae77e6bb5687d3f6bc335e7c2ec7e25f3f` | Run metadata, timing, authorization, and denominators |
| `input_integrity.json` | 877 | `df4c76fabdcd51ca421194477a2d78d63074c27fa58e1fbf6a266d0a469e55ce` | Verified input file hashes and quarantine audit |
| `rerank_summary.json` | 5,363 | `3b8dfe7ceb9a15cca310e10aae13148f8848a9161ad44918fd8b02b67f8c2b92` | Full pooled and annual reranking metrics for both candidates |
| `bootstrap_summary.json` | 1,328 | `8425b222d653359051d701d95ecb621b809c286690435dfd03eef857c329b227` | Paired calendar-block bootstrap distributions (21 and 42 sessions) |
| `regime_diagnostic_summary.json` | 3,518 | `7c27447b6db142b63d41666bffaed4f83e5317cf9ffd002451682d6a12df5bdf` | SPY return regime breakdown across Lower, Middle, and Upper bins |
| `checksums.sha256` | 454 | — | Manifest of SHA-256 digests for all summary JSON artifacts |

---

## 8. Next Steps & Stop Condition

- **Primary Relative-Volume Decision:** Conclusively **`NOT_SUPPORTED`** for incremental top-of-list reranking beyond frozen VAM5.
- **Strategy & Model Impact:** `relative_volume_20` will NOT be carried forward as a top-of-list reranker for the VAM5 candidate pool.
- **Quarantine Preservation:** Validation (2021–2022) and holdout (2023–2025) splits remain unopened.
- **Production Preservation:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.
- **Stop Condition:** Gary Yang and ChatGPT will review these empirical findings. No subsequent phase (`LONG-002E`, model fitting, or validation access) is authorized.
