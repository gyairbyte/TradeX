# LONG-002C-EXECUTION-REPORT — Development Dataset, Outcome Census, Master Episodes, and Frozen Baselines

- **Task ID:** `LONG-002C-EXEC-001`
- **Execution Run ID:** `2026-09-27-161243`
- **Status:** `completed` / `valid_development_evidence`
- **Classification:** `official_development_census`
- **Valid Research Evidence:** `true` (development split census only)
- **Production Promotion Eligible:** `false` (`APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved)
- **Code HEAD SHA:** `d6a300e556c690c83ff8b9265833667c02dc94ec`
- **Authorized Discovery Manifest SHA-256:** `d1bf16d6b475c93b5c47e81a47af5597fd514432880107030040a81fd61e9947`
- **Authorized Frozen Pre-Run Manifest SHA-256:** `5bb2f90a2a3e572e8be1d2b8b13fbb207d7bb9d459e096f19e177f9250cfdb37`
- **Authorized Frozen Eligible Candidates:** `1,291`

---

## 1. Executive Summary

This execution report documents the official Stage C development-only outcome census and frozen baseline evaluation for `LONG-002C-EXEC-001` (Run ID: `2026-09-27-161243`), executed on branch `antigravity/long-002c-exec-001` (PR #85) at code HEAD `d6a300e556c690c83ff8b9265833667c02dc94ec`.

The empirical run was executed following the approved performance enhancements (PERF-001, PERF-002, PERF-003) and passing the pre-launch memory-capacity gate (realistic working set projection 21.84 GB <= 24.89 GB 80% RAM ceiling; actual peak working set during evaluation 16.74 GB).

### Key Empirical Findings:
1. **Universe & Decision Observations:**
   - 1,291 point-in-time discovery candidates ingested from `discovery_manifest.json`.
   - 2,815,600 total decision observations constructed across 20:30 post-close primary and 09:00 pre-market reevaluation.
   - 758,731 raw outcome-eligible observations evaluated for the 20:30 primary census (758,735 for 09:00 diagnostic).
2. **Primary Outcome Census (20:30 Primary Population):**
   - **Primary Endpoint (+10%/10 sessions):** 67,257 clean target reached events (**8.8644% prevalence**, denominator 758,731).
   - **Fallback Endpoint (+10%/21 sessions):** 135,603 clean target reached events (**17.8723% prevalence**, denominator 758,731).
   - Stationary 21-session block bootstrap 95% confidence interval for primary clean +10%/10d is **[6.7194%, 11.0772%]**, far exceeding the 2.0% statistical floor.
3. **Master Opportunity Episodes:**
   - **16,139** independent non-recursive master opportunity episodes clustered on the 20:30 primary census.
   - **1,205** distinct immutable securities represented (out of 1,291 universe candidates).
   - Effective Number of Securities ($N_{\text{eff}}$): **901.15**.
   - Herfindahl-Hirschman Index ($\text{HHI}$): **0.00111** (demonstrating extreme cross-sectional diversification, well below 0.15).
4. **Frozen Baseline Comparators:**
   - 13 simple comparators evaluated on common observations ($N = 758,731$) against universe base rate (8.8644%).
   - **Empirical Winner Selected:** `volatility_aware_momentum_5` achieved **1.7320x Top-10 Decile Lift** (15.3533% clean rate) and **1.4314x Top-25 Lift**, outperforming all simple momentum, SPY-relative, and legacy comparators.
   - **Legacy TradeX Scorer Evaluation:** Produced **0.9151x Top-10 Lift** (8.1118% clean rate, below universe base rate), failing to exhibit positive predictive power and confirming the necessity of modern baseline comparators.
5. **Endpoint Feasibility:**
   - Formally designated `pending_gary_chatgpt_review`. Both primary (+10%/10d) and fallback (+10%/21d) endpoints exhibit massive statistical sample sizes and power.
6. **Strict Governance & Quarantine:**
   - Validation split (2021–2022), Holdout split (2023–2025), and Shadow split (2026+) remain **strictly unread, unqueried, and quarantined**.
   - Zero live network requests occurred (100% provider cache hits).
   - Production promotion remains unauthorized (`APPROVED_PRODUCTION_STRATEGIES == ()`).

---

## 2. Upstream Specification & Split Verification

Before ingestion, the Stage C pre-launch assertions verified:
1. Current Git HEAD matches authorized code head `d6a300e556c690c83ff8b9265833667c02dc94ec`.
2. Working tree is clean.
3. Candidates manifest SHA-256 matches authorized discovery digest `d1bf16d6b475c93b5c47e81a47af5597fd514432880107030040a81fd61e9947`.
4. Frozen pre-run manifest SHA-256 matches authorized frozen digest `5bb2f90a2a3e572e8be1d2b8b13fbb207d7bb9d459e096f19e177f9250cfdb37`.
5. Frozen manifest recorded Git SHA matches current HEAD.
6. Frozen eligible count is exactly 1,291.
7. Candidate set has zero duplicate immutable security IDs.

### Split Boundary Enforcements:
- **Warmup Split:** `2015-01-01` to `2015-12-31` (used exclusively for indicator stabilization: 60-session momentum, 14-session Wilder ATR, 20-session dollar volume medians).
- **Development Split:** `2016-01-01` to `2020-12-31` (1,259 trading sessions on the XNYS calendar).
- **Split Boundary Purging:** 6,271 observations per cutoff (12,542 total) whose forward 26-session outcome evaluation window extended past `2020-12-31` were marked `split_boundary_purged=True` and excluded from outcome evaluation to eliminate forward-split leakage.
- **Future Splits:** `2021-01-01` through present remained completely unread.

---

## 3. Data Providers, Provenance, and Integrity

All provider data was consumed strictly from local persistent cache (`data/cache/long_002c/`):
- **Alpaca SIP Fallback Daily Bars:** 100% cache hits. Zero live network requests.
- **Massive Reference Splits & Dividends:** 100% cache hits. Zero live network requests.
- **SEC EDGAR Submissions & Company Facts:** 100% cache hits. Zero live network requests.
- **Provider Request Audit:**
  - Total network requests during build: **0**
  - Retries: **0**
  - Rate-limit 429s: **0**
  - Server 5xxs: **0**
- **Data Quality & Completeness:**
  - Security count audited: 1,291
  - Average completeness: **86.61%** across all securities and historical trading sessions
  - Zero duplicate timestamps, zero malformed OHLCV rows

---

## 4. Observation Funnel & Dual Reporting

### Primary 20:30 Population Observation Funnel

| Funnel Stage | Count | Percentage of Total Obs | Description |
|---|---|---|---|
| **Total Decision Observations** | **1,407,800** | 100.0% | 1,291 securities $\times$ 1,259 sessions (less pre-listing) |
| Universe Eligible | 784,299 | 55.71% | Met price >= \$5, 20d dollar vol >= \$20M, 60d >= \$10M, mcap >= \$3B |
| Data Complete | 1,118,155 | 79.43% | Passed session data quality and forward analytical window checks |
| **Raw Outcome Eligible** | **758,731** | **53.90%** | Both universe eligible and data complete (excluding boundary purged) |
| Earnings Schedule Known | 0 | 0.00% | No historical known-at-time earnings schedule exists for 2016–2020 |
| Earnings Schedule Unknown | 1,407,800 | 100.0% | Option 2 fail-closed handling applied |
| **Actionable Eligible** | **0** | **0.00%** | Fail-closed under Option 2 (`unavailable_earnings_unknown`) |

### Reevaluation 09:00 Pre-Market Diagnostic Funnel

| Funnel Stage | Count | Percentage of Total Obs |
|---|---|---|
| Total Decision Observations | 1,407,800 | 100.0% |
| Universe Eligible | 783,260 | 55.64% |
| Data Complete | 1,119,178 | 79.50% |
| Raw Outcome Eligible | 758,735 | 53.90% |
| Earnings Schedule Known / Actionable | 0 | 0.00% |

---

## 5. Outcome Census: The 3x3 Target/Horizon Matrix

A total of **13,657,194 outcome label records** were evaluated across non-purged raw outcome eligible observations.

### Primary 20:30 Population Outcome Census ($N = 758,731$)

| Cell Identifier | Return Target | Horizon (Sessions) | Evaluated Obs | Clean Target Events | Clean Target Rate (%) | Gross Target Events | Gross Target Rate (%) | Near Misses (0.8–1.0x) | Partial Moves (0.5–0.8x) | Adverse Excursions | Sustained Targets |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `+10%_5d` | +10% | 5 | 758,731 | 29,529 | **3.8919%** | 33,495 | 4.4146% | 22,004 | 81,634 | 129,183 | 28,545 |
| **`+10%_10d` (Primary)** | **+10%** | **10** | **758,731** | **67,257** | **8.8644%** | **80,129** | **10.5609%** | **41,964** | **126,251** | **225,042** | **66,364** |
| **`+10%_21d` (Fallback)** | **+10%** | **21** | **758,731** | **135,603** | **17.8723%** | **173,532** | **22.8713%** | **66,002** | **151,084** | **338,225** | **140,473** |
| `+20%_5d` | +20% | 5 | 758,731 | 4,979 | **0.6562%** | 5,377 | 0.7087% | 4,873 | 23,245 | 129,183 | 4,840 |
| `+20%_10d` | +20% | 10 | 758,731 | 13,659 | **1.8002%** | 15,423 | 2.0327% | 12,366 | 52,340 | 225,042 | 13,064 |
| `+20%_21d` | +20% | 21 | 758,731 | 34,423 | **4.5369%** | 42,666 | 5.6233% | 28,566 | 102,300 | 338,225 | 37,351 |
| `+30%_5d` | +30% | 5 | 758,731 | 1,410 | **0.1858%** | 1,480 | 0.1951% | 1,602 | 9,194 | 129,183 | 1,347 |
| `+30%_10d` | +30% | 10 | 758,731 | 3,973 | **0.5236%** | 4,362 | 0.5749% | 4,676 | 23,582 | 225,042 | 3,640 |
| `+30%_21d` | +30% | 21 | 758,731 | 11,991 | **1.5804%** | 14,381 | 1.8954% | 12,476 | 54,762 | 338,225 | 12,794 |

### Diagnostic 09:00 Pre-Market Reevaluation Census ($N = 758,735$)

| Cell Identifier | Return Target | Horizon (Sessions) | Evaluated Obs | Clean Target Events | Clean Target Rate (%) | Gross Target Events | Gross Target Rate (%) |
|---|---|---|---|---|---|---|---|
| `+10%_5d` | +10% | 5 | 758,735 | 29,529 | 3.8919% | 33,495 | 4.4146% |
| `+10%_10d` | +10% | 10 | 758,735 | 67,259 | 8.8646% | 80,131 | 10.5611% |
| `+10%_21d` | +10% | 21 | 758,735 | 135,603 | 17.8722% | 173,534 | 22.8715% |
| `+20%_5d` | +20% | 5 | 758,735 | 4,979 | 0.6562% | 5,377 | 0.7087% |
| `+20%_10d` | +20% | 10 | 758,735 | 13,661 | 1.8005% | 15,425 | 2.0330% |
| `+20%_21d` | +20% | 21 | 758,735 | 34,424 | 4.5370% | 42,667 | 5.6234% |
| `+30%_5d` | +30% | 5 | 758,735 | 1,410 | 0.1858% | 1,480 | 0.1951% |
| `+30%_10d` | +30% | 10 | 758,735 | 3,972 | 0.5235% | 4,361 | 0.5748% |
| `+30%_21d` | +30% | 21 | 758,735 | 11,991 | 1.5804% | 14,381 | 1.8954% |

**Cross-Cutoff Stability:** The primary clean +10%/10d rate at 20:30 (8.8644%) and 09:00 (8.8646%) differ by less than 0.0002 percentage points, demonstrating remarkable temporal consistency across overnight and pre-market information flows.

---

## 6. Master Opportunity Episodes

Clustered strictly on the 20:30 primary census:
- **Total Master Episodes:** **16,139**
- **Unique Anchor Securities:** **1,205** (93.3% of universe candidates)
- **Effective Number of Securities ($N_{\text{eff}}$):** **901.15**
- **Herfindahl-Hirschman Index ($\text{HHI}$):** **0.00111** (indicating negligible security concentration, far below the 0.15 threshold)
- **Average Constituent Observations per Episode:** **41.99**
- **Constituent Memberships Mapped:** **677,736**

### Annual Distribution of Master Episodes

| Calendar Year | Episode Count | Fraction of Total (%) |
|---|---|---|
| 2016 | 67 | 0.42% |
| 2017 | 2,159 | 13.38% |
| 2018 | 3,982 | 24.67% |
| 2019 | 3,957 | 24.52% |
| 2020 | 5,974 | 37.02% |
| **Total** | **16,139** | **100.0%** |

### Maximum Target Tier Reached Within Episodes

| Max Tier Reached | Episode Count | Fraction of Total (%) |
|---|---|---|
| +10% Tier | 14,413 | 89.31% |
| +20% Tier | 1,145 | 7.09% |
| +30% Tier | 581 | 3.60% |

---

## 7. Dependence-Aware Block Resampling

To account for cross-sectional and temporal clustering, stationary block bootstrap resampling (1,000 iterations each) was conducted on the 20:30 primary census:

### Primary 21-Session Block Resampling ($K = 21$, 60 blocks)

| Outcome Metric | Mean Prevalence | Std Error | 2.5% CI Quantile | Median | 97.5% CI Quantile |
|---|---|---|---|---|---|
| **Clean +10%/10d (Primary)** | **0.088270** | **0.011306** | **0.067194** | **0.087727** | **0.110772** |
| Clean +10%/21d (Fallback) | 0.178214 | 0.014815 | 0.150285 | 0.177942 | 0.208134 |
| Gross +10%/10d | 0.105395 | 0.016800 | 0.075818 | 0.104257 | 0.140137 |
| Gross +10%/21d | 0.228157 | 0.023288 | 0.183513 | 0.227397 | 0.274103 |

### Robustness 42-Session Block Resampling ($K = 42$, 30 blocks)

| Outcome Metric | Mean Prevalence | Std Error | 2.5% CI Quantile | Median | 97.5% CI Quantile |
|---|---|---|---|---|---|
| **Clean +10%/10d (Primary)** | **0.087956** | **0.013769** | **0.063729** | **0.086926** | **0.117146** |
| Clean +10%/21d (Fallback) | 0.177919 | 0.015591 | 0.149873 | 0.177216 | 0.210625 |
| Gross +10%/10d | 0.104789 | 0.020710 | 0.069286 | 0.102815 | 0.150864 |
| Gross +10%/21d | 0.227386 | 0.028111 | 0.176597 | 0.226293 | 0.287567 |

---

## 8. Frozen Baseline Comparators Analysis on Common Observations

All baseline comparators were evaluated across **758,731 common observations** against the universe base rate (8.8644%):

| Comparator ID | Family | Lookback | Top-10 Clean Count | Top-10 Clean Rate (%) | Top-10 Decile Lift | Top-25 Decile Lift | Selection Disposition |
|---|---|---|---|---|---|---|---|
| **`volatility_aware_momentum_5`** | **volatility_aware_momentum** | **5** | **11,731** | **15.3533%** | **1.7320x** | **1.4314x** | **EMPERICALLY SELECTED WINNER (FROZEN)** |
| `volatility_aware_momentum_10` | volatility_aware_momentum | 10 | 11,616 | 15.2028% | 1.7150x | 1.4293x | Candidate |
| `volatility_aware_momentum_60` | volatility_aware_momentum | 60 | 11,512 | 15.0667% | 1.6997x | 1.4010x | Candidate |
| `volatility_aware_momentum_20` | volatility_aware_momentum | 20 | 11,431 | 14.9607% | 1.6877x | 1.4116x | Candidate |
| `simple_momentum_60` | simple_momentum | 60 | 8,491 | 11.1129% | 1.2536x | 1.0158x | Candidate |
| `spy_relative_60` | spy_relative | 60 | 8,491 | 11.1129% | 1.2536x | 1.0158x | Candidate |
| `simple_momentum_5` | simple_momentum | 5 | 8,430 | 11.0330% | 1.2446x | 1.0432x | Candidate |
| `spy_relative_5` | spy_relative | 5 | 8,430 | 11.0330% | 1.2446x | 1.0432x | Candidate |
| `simple_momentum_10` | simple_momentum | 10 | 8,420 | 11.0199% | 1.2432x | 1.0532x | Candidate |
| `spy_relative_10` | spy_relative | 10 | 8,420 | 11.0199% | 1.2432x | 1.0532x | Candidate |
| `simple_momentum_20` | simple_momentum | 20 | 8,210 | 10.7451% | 1.2122x | 1.0239x | Candidate |
| `spy_relative_20` | spy_relative | 20 | 8,210 | 10.7451% | 1.2122x | 1.0239x | Candidate |
| `universe_base_rate` | universe_base_rate | 0 | 67,257 | 8.8644% | 1.0000x | 1.0000x | Null Benchmark |
| `legacy_tradex_scorer` | legacy_tradex_scorer | 999 | 6,198 | 8.1118% | **0.9151x** | **0.9003x** | **INELIGIBLE (Negative Predictive Lift)** |

### Baseline Selection Analysis:
1. **Strongest Simple Baseline Winner:**
   `volatility_aware_momentum_5` (5-session return normalized by 14-session ATR percentage) achieved the highest Top-10 predictive lift (**1.7320x** over universe base rate). It is formally frozen as the benchmark comparator for all subsequent research phases.
2. **Deficiency of Legacy TradeX Scorer:**
   The legacy TradeX scorer produced a top-decile clean rate of 8.1118%, which is **lower than the baseline random universe rate of 8.8644%** (lift 0.9151x). Filtering by high legacy TradeX scores historically resulted in adverse selection for large multi-week breakout moves.

---

## 9. Endpoint Feasibility Disposition

- **Disposition:** `pending_gary_chatgpt_review`
- **Primary Endpoint (+10%/10 sessions):**
  - Observed clean target events: **67,257**
  - Prevalence: **8.8644%**
  - 21-session block bootstrap 95% CI: **[6.7194%, 11.0772%]**
  - Statistical sufficiency: Confirmed. The empirical prevalence exceeds the 2.0% feasibility floor by more than 4x.
- **Fallback Endpoint (+10%/21 sessions):**
  - Observed clean target events: **135,603**
  - Prevalence: **17.8723%**
  - 21-session block bootstrap 95% CI: **[15.0285%, 20.8134%]**
  - Statistical sufficiency: Confirmed.
- **Recommendation:** Both endpoints are statistically robust and highly populated. Final selection between primary (+10%/10d) and fallback (+10%/21d) is reserved for Gary and ChatGPT review.

---

## 10. Proposed Validation Evidence Gates (Development-Only; For Review; Not Locked)

The following empirical evidence gates are proposed based on the development split census (scaling ratio: 2 years validation / 5 years development = 0.40):

| Proposed Evidence Gate | Development Value | Scaling Formula | Proposed Validation Gate | Status |
|---|---|---|---|---|
| Master Opportunity Episodes | 16,139 | $\times 0.40 \times 0.75$ | **$\ge$ 4,841** | Proposed for review |
| Clean Target Events (+10%/10d) | 67,257 | $\times 0.40 \times 0.75$ | **$\ge$ 20,177** | Proposed for review |
| Effective Securities ($N_{\text{eff}}$) | 901.15 | $\times 0.35$ cross-sectional floor | **$\ge$ 315.4** | Proposed for review |
| Actionable Observations | 0 | Option 2 historical unknown | **None (N/A)** | Known limitation |
| Clustering Session Fraction Ceiling | 0.85 | Max fraction in top 15% sessions | **$\le$ 0.85** | Proposed for review |

*Note: In accordance with research governance, these gates are proposed recommendations derived from development data for Gary and ChatGPT review and are NOT permanently locked.*

---

## 11. Exclusions & Data Limitations Audit

Total observation exclusions: **3,684,007**
- **Data Quality (1,517,288 total):**
  - `data_quality_consecutive_missing_exceeded`: 497,291
  - `data_quality_missing_sessions_exceeded`: 494,685
  - `data_quality_completeness_below_99`: 494,685
  - `forward_analytical_data_incomplete`: 30,627
- **Liquidity (712,632 total):**
  - `dollar_volume_20d_below_20m`: 570,089
  - `dollar_volume_60d_below_10m`: 142,543
- **Market Cap (688,786 total):**
  - `market_cap_valid_below_3b`: 639,782
  - `market_cap_unavailable_at_cutoff`: 47,861
  - `market_cap_non_positive_as_traded_close`: 1,143
- **Trading History (649,373 total):**
  - `unverified_history_truncated`: 487,998
  - `insufficient_trading_history`: 161,375
- **Price (103,278 total):**
  - `price_below_5`: 103,278
- **Split Boundary Purged (12,542 total):**
  - `split_boundary_purged`: 12,542
- **Corporate Action (108 total):**
  - `special_distribution_unresolved`: 108

---

## 12. Storage Artifacts & Checksums

### External Row-Level Parquet Datasets (`data/research/long_002c/` — Gitignored)

| Parquet File Name | Schema Name | Row Count | Byte Count | SHA-256 Digest |
|---|---|---|---|---|
| `decision_observations.parquet` | `decision_observations` | 2,815,600 | 40,622,094 | `722bee866cabb697931dfb96abaf7f9250f1cd1240b405d2e308af0b6bbb48af` |
| `data_eligibility.parquet` | `data_eligibility` | 2,815,600 | 21,858,159 | `16147606e629daf02e54db4b6b0127ede04aeb45608f27900a92f73805baa4d9` |
| `security_classification_status.parquet` | `security_classification_status` | 2,815,600 | 3,087,801 | `65adc6170f2095371f3842153256b96c16042b88c6716d78c329f45ffb8d4d6d` |
| `earnings_schedule_status.parquet` | `earnings_schedule_status` | 2,815,600 | 3,062,791 | `439b85a5c5c2ed618585007fe6e62ef213eb2600bb47ba222f35ff338557d05b` |
| `outcome_matrix.parquet` | `outcome_label_records` | 13,657,194 | 283,336,113 | `b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3` |
| `master_episodes.parquet` | `master_opportunity_episodes` | 16,139 | 502,442 | `1fe5b36f98919465007a720908c626203e5272b054a4ef76be772db279b3cc98` |
| `constituent_memberships.parquet` | `episode_membership` | 677,736 | 624,457 | `53a8adc92f1210ef3a1b6d10c9eedd1f360dad2760897f97b5d293f473734b11` |
| `baseline_comparator_outputs.parquet` | `baseline_comparator_outputs` | 21,244,524 | 190,588,243 | `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` |
| `data_quality_coverage.parquet` | `data_quality_coverage` | 1,291 | 24,845 | `265973b7e88ce98f65c492836fd8a4949d72c5de7e28fc4e62442bc01993e9bb` |
| `provenance_records.parquet` | `provenance_provider_records` | 8,211 | 1,225,777 | `4ff93f7008310df2e115937ed6acbc2d435f58f06130a369f4b5b72615f4554f` |
| `exclusions.parquet` | `exclusions_and_reason_codes` | 3,684,007 | 5,967,704 | `9624d11dd191d967d6a3160e2f877d02027d744dcd5b2d46a6b638837ba97da8` |

### Committed Summary Manifest (`docs/research/artifacts/LONG-002C/2026-09-27-161243/`)

| File Name | SHA-256 Digest |
|---|---|
| `baseline_census_summary.json` | `0ac79deec3598f163ad72565333c43634e95ec76c670a71a8fdec39a4f7c3ff7` |
| `data_quality_report.json` | `5115680805d7172531559997d9a5961f6bcf9d442e6317d8803ef232c9c0f144` |
| `dataset_manifest.json` | `d4eed62d204c6a9955bc7f1ae347ec41f22e0f7f9b438df64569c731949fabaf` |
| `endpoint_feasibility_report.json` | `1b63a13d80138dba0d8d1a021e79abffb062698d53a70ef2a50b5f8a0acce0a6` |
| `exclusion_summary.json` | `69f42dac1e62281c13ce35df0700f02aa70b1a33233192c4bc79aef18fd24984` |
| `execution_metadata.json` | `18d518cf00d8ec88b8305309801fe9ee41ff39b172fbcc1cf5e0b50384e1a460` |
| `master_episodes_summary.json` | `7ebf45cae230bdf85e96a027895dfa8a00e96689f4bc3123b3206f14a82bc000` |
| `outcome_census_summary.json` | `3ccfc1e9e3e6f08130fb7d94eb56a8fe2e40ce2456665f1ab5b94c4a262bf76a` |
| `provenance_summary.json` | `813c36a4fff4498d14fd9ffa6b5e585409ffde8768ef0ef74614ac2743709f0b` |
| `checksums.sha256` | Formally locked checksum index |

---

## 13. Verification Commands & Status

Both official verification commands passed with exit code 0:
1. **Artifact Verification:**
   ```bash
   uv run python -m tradex.research.long_002c.cli verify
   ```
   *Result:* All 9 summary JSON artifacts successfully verified against `checksums.sha256`.
2. **Offline Parquet Evaluation:**
   ```bash
   uv run python -m tradex.research.long_002c.cli evaluate
   ```
   *Result:* Verified identical counts (2,815,600 observations, 13,657,194 outcomes, 16,139 episodes, 21,244,524 baselines, 134,516 primary clean +10/10 events across cutoffs, 271,206 fallback clean +10/21 events).
3. **Automated Test Suite:**
   ```bash
   uv run pytest tests/research/long_002c tests/research/long_002c_design -q
   ```
   *Result:* 154 passed in 22.75s.
4. **Code Quality:**
   ```bash
   uv run ruff check tests scripts tradex/research/long_002c
   ```
   *Result:* All checks passed. Working tree clean.

---

## 14. Governance Constraints & Next Steps

1. **Research-Only Scope:**
   `LONG-002C-EXEC-001` is strictly an offline research milestone. It does not authorize or perform any production code changes, scoring changes, or strategy registrations (`APPROVED_PRODUCTION_STRATEGIES == ()`).
2. **Strict Quarantine Maintained:**
   Validation split (2021–2022) and Holdout split (2023–2025) remain unopened and strictly quarantined.
3. **No Strategy Promotion:**
   No trading strategy or model is promoted to production.
4. **Next Step:**
   STOP and present this comprehensive evidence report for Gary and ChatGPT review. Progression to subsequent research or gate locking requires explicit user authorization.
