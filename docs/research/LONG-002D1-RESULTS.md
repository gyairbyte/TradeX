# LONG-002D1: Core Technical and Market-Context KPI Census — Empirical Results

- **Task ID:** `LONG-002D1-CORE-KPI-CENSUS`
- **Execution Run ID:** `2026-09-28-003539` (Official Corrected Run)
- **Superseded Run ID:** `2026-09-27-223646` (Superseded: execution/audit defect; 100% empirical equivalence confirmed)
- **Execution Date:** 2026-09-28
- **Preregistration Spec SHA-256:** `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381` (`docs/research/specs/LONG-002D1-v1.json`)
- **Stage C Input Dataset:** Run ID `2026-09-27-161243` (code SHA `d6a300e556c690c83ff8b9265833667c02dc94ec`)
- **Branch:** `antigravity/long-002d1-core-kpi-census`
- **Status:** Execution Completed & Verified; Ready for Gary/ChatGPT Post-Run Review

---

## 1. Executive Summary & Boundaries

This document reports the empirical results of **LONG-002D1**, the first slice of `LONG-002D`: a development-only, point-in-time-safe descriptive core technical and market-context feature census for the retained LONG-002 primary endpoint.

### Primary Scope & Quarantine Boundaries
- **Descriptive KPI Discovery Only:** This study evaluates univariate predictive association, distribution coverage, annual stability across development years, and redundancy. **No predictive models were fit, no multi-feature scores were optimized, and no trading strategies were promoted.**
- **Development Split Only:** All analyses were strictly confined to the development split (2016-01-01 to 2020-12-31) at the 20:30 ET snapshot.
- **Strict Data Quarantines:** Validation (2021–2022), holdout (2023–2025), and shadow (2026+) remain completely unopened, unaccessed, and strictly quarantined.
- **Zero Live Network Requests & Audit Truthfulness:** Alpaca client ran with `allow_live=False` and fail-closed assertion. 100% of candidate bars (1,271 study securities) and SPY closes were served strictly from the audited read-only provider cache (2,797 cache hits, 0 misses, 0 live attempts, 0 outbound HTTP). 100% (2,797 / 2,797) of consumed payloads matched Stage C Alpaca provenance records (`provenance_records.parquet`).
- **Production Status:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.

---

## 2. Population & Dataset Denominators

- **Universe:** 1,271 active securities with valid observations in the Stage C 20:30 ET population across 1,259 SPY market sessions.
- **Primary Population:** Exactly **758,731** observations (`raw_outcome_eligible == True` and `split_boundary_purged == False`).
- **Primary Endpoint:** Clean +10% within 10 trading sessions (`target_pct == 10.0`, `horizon_sessions == 10`).
- **Clean Events Count:** Exactly **67,257** events.
- **Common Base Rate:** **8.8644%** ($67,257 / 758,731$).

---

## 3. Comprehensive Feature Census Results

Stock-level features were ranked cross-sectionally within each 20:30 `as_of_date` on non-null observations with deterministic tie-breaking. Percentile ranks were mapped to 10 deciles (Decile 10 = favorable $\ge 90.0$, Top Quartile = favorable $\ge 75.0$). `spy_return_20` was evaluated as a date-level market-regime diagnostic.

| Feature ID | Role | Status | Hypoth. Dir | Usable Obs | Cov % | Fav Decile Clean Rate | Fav Decile Lift | Top Quartile Clean Rate | Top Quartile Lift | 21-Session Block Bootstrap 95% CI | 42-Session Block Bootstrap 95% CI | Annual Stability (+ lift yrs) |
|---|---|---|:---:|---:|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| `return_5` | reference | `reference` | NONE | 758,731 | 100.0% | 11.03% | **1.2446x** | 9.94% | 1.1213x | [1.13, 1.38] | [1.13, 1.40] | 5/5 |
| `return_20` | reference | `reference` | NONE | 758,731 | 100.0% | 10.75% | **1.2122x** | 9.77% | 1.1022x | [1.11, 1.33] | [1.11, 1.34] | 5/5 |
| `return_60` | reference | `reference` | NONE | 758,731 | 100.0% | 11.11% | **1.2536x** | 9.94% | 1.1213x | [1.08, 1.44] | [1.10, 1.45] | 5/5 |
| `atr_pct_14` | reference | `reference` | NONE | 758,731 | 100.0% | 20.22% | **2.2816x** | 16.92% | 1.9088x | [1.94, 2.70] | [1.90, 2.84] | 5/5 |
| `close_vs_sma20` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 10.71% | **1.2083x** | 9.69% | 1.0931x | [1.10, 1.34] | [1.10, 1.35] | 4/5 |
| `close_vs_sma60` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 10.61% | **1.1967x** | 9.80% | 1.1055x | [1.07, 1.33] | [1.08, 1.36] | 4/5 |
| `sma20_slope_5` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 10.85% | **1.2238x** | 9.76% | 1.1010x | [1.11, 1.34] | [1.12, 1.35] | 5/5 |
| `proximity_high20` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 6.48% | **0.7307x** | 6.84% | 0.7716x | [0.65, 0.80] | [0.64, 0.80] | 0/5 |
| `proximity_high60` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 6.10% | **0.6886x** | 6.47% | 0.7300x | [0.59, 0.78] | [0.57, 0.78] | 0/5 |
| `true_range_compression_5_20` | candidate | `review_pending` | LOWER | 758,731 | 100.0% | 8.94% | **1.0087x** | 8.87% | 1.0006x | [0.96, 1.06] | [0.97, 1.05] | 2/5 |
| `relative_volume_20` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 10.02% | **1.1307x** | 9.47% | 1.0683x | [1.07, 1.20] | [1.08, 1.21] | 4/5 |
| `dollar_volume_trend_20_60` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 8.88% | **1.0022x** | 8.94% | 1.0085x | [0.91, 1.10] | [0.93, 1.08] | 3/5 |
| `up_volume_share_20` | candidate | `review_pending` | HIGHER | 758,731 | 100.0% | 7.84% | **0.8842x** | 8.08% | 0.9115x | [0.81, 0.96] | [0.80, 0.96] | 0/5 |
| `spy_return_20` | diagnostic | `review_pending` | HIGHER | 758,731 | 100.0% | 13.72% | **1.5473x** | 10.27% | 1.1585x | [0.90, 2.18] | [0.87, 2.14] | 1/5 |
| `stock_minus_spy_20` | reference | `reference` | NONE | 758,731 | 100.0% | 10.75% | **1.2122x** | 9.77% | 1.1022x | [1.11, 1.33] | [1.11, 1.34] | 5/5 |

---

## 4. Key Empirical Findings

### 1. `atr_pct_14` Showed the Strongest Univariate Development Association
- `atr_pct_14` (normalized Wilder ATR-14) showed the strongest univariate development association among the evaluated reference and candidate features: **2.2816x** favorable decile lift (Clean Rate: **20.22%** vs base rate 8.86%), with a 21-session block bootstrap 95% CI of `[1.94, 2.70]` and positive descriptive lift in **5 out of 5 development years**.
- The decile progression is strictly monotonic across all 10 deciles (Decile 1: 2.40% clean rate, 0.27x lift $\to$ Decile 10: 20.24% clean rate, 2.28x lift).
- Notably, univariate `atr_pct_14` alone achieved higher top-decile lift (2.2816x) than the composite multi-factor Stage C baseline comparator `volatility_aware_momentum_5` (1.7320x), confirming that baseline volatility capacity is an essential conditioning factor for clean rapid upside.

### 2. Verification of Locked Ranking Semantics (Clarification 1)
- `stock_minus_spy_20` produced identical cross-sectional decile assignments, clean event counts, clean rates (10.75%), favorable lifts (1.2122x), and bootstrap confidence intervals as `return_20`.
- This confirms the mathematical identity: for any date $t$, $\text{rank}_i(r_{i,t} - r_{\text{SPY},t}) \equiv \text{rank}_i(r_{i,t})$ on identical non-null universes within each same-date cross-section.

### 3. Moving Average & Trend Features Show Moderate, Stable Lift
- `sma20_slope_5` (5-day slope of 20-day SMA): **1.2238x** lift, CI `[1.11, 1.34]`, 5/5 years positive lift.
- `close_vs_sma20` (distance above 20-day SMA): **1.2083x** lift, CI `[1.10, 1.34]`, 4/5 years positive lift.
- `close_vs_sma60` (distance above 60-day SMA): **1.1967x** lift, CI `[1.07, 1.33]`, 4/5 years positive lift.
- All three moving average trend indicators display positive descriptive lift in 4/5 or 5/5 development years (no stationarity or out-of-sample claims are made).

### 4. Proximity to Highs: Contradicted Preregistered Direction (Post-Hoc Exploratory Dip Evidence)
- Both `proximity_high20` and `proximity_high60` directly contradicted the preregistered HIGHER breakout hypothesis:
  - Favorable Decile 10 (stocks nearest to rolling highs under preregistered HIGHER direction) yielded only a **6.48% clean rate** (**0.7307x lift**, 0/5 years favorable).
  - Conversely, Decile 1 (stocks most deeply pulled back from highs, mean $-14.26\%$) achieved a **14.58% clean rate** (**1.6448x lift**).
  - **Preregistration Discipline Note:** This observed pullback association is post-hoc exploratory evidence of dip-buying behavior. Because the preregistered direction was HIGHER, this feature direction must NOT be post-hoc inverted or automatically converted into an active model feature. Any dip-buying formulation must be separately preregistered in a subsequent specification before inclusion in predictive pipelines.

### 5. Volume Features
- `relative_volume_20` (volume vs prior 20-session median) showed modest, statistically distinct positive lift: **1.1307x** lift (Clean Rate: 10.02%), CI `[1.07, 1.20]`, 4/5 years favorable.
- `dollar_volume_trend_20_60` was effectively neutral (**1.0022x** lift, CI `[0.91, 1.10]`, 3/5 years favorable).
- `up_volume_share_20` showed an inverse development association (**0.8842x** lift, CI `[0.81, 0.96]`, 0/5 years favorable). The underlying market mechanism for this inverse relationship remains unproven and should not be attributed to specific causal hypotheses (e.g. buyer exhaustion) without independent verification.

### 6. Compression Features
- `true_range_compression_5_20` showed negligible univariate lift (**1.0087x** lift, CI `[0.96, 1.06]`, 2/5 years favorable), indicating that rolling true range compression alone does not provide a directional edge for rapid clean expansion without secondary conditioning.

### 7. Market Regime Diagnostic (`spy_return_20`)
- `spy_return_20` (deciles formed over unique market dates) showed a 13.72% clean rate on favorable dates (1.5473x lift). However, its 21-session block bootstrap CI spans `[0.90, 2.18]` and annual stability is only `1/5` years due to macro date clustering (2020 post-crash bounce dominated favorable decile dates). As preregistered, it serves as a date-level macro diagnostic, and its lift is not directly comparable to cross-sectional stock-ranking lifts.

---

## 5. Pairwise Redundancy & Correlation Analysis

Pairwise Spearman rank correlations were computed on the common non-null sample across all 758,731 observations:
- **High-Redundancy Pairs ($|\rho| \ge 0.95$):** **0 pairs** exceeded the threshold.
- No candidate features were flagged as `high_redundancy_candidate`.
- Notable pairwise correlation clusters:
  - `close_vs_sma20` $\leftrightarrow$ `proximity_high20`: $\rho = +0.8286$
  - `close_vs_sma20` $\leftrightarrow$ `return_20`: $\rho = +0.8228$
  - `close_vs_sma60` $\leftrightarrow$ `return_60`: $\rho = +0.8218$
  - `close_vs_sma60` $\leftrightarrow$ `sma20_slope_5`: $\rho = +0.7732$
  - `atr_pct_14` $\leftrightarrow$ `proximity_high60`: $\rho = -0.5654$ (high-volatility stocks tend to trade further below 60-day highs)
  - `atr_pct_14` $\leftrightarrow$ `return_20`: $\rho = -0.1293$ (volatility is largely orthogonal to 20-day momentum)

---

## 6. Market-Cap Cohort Breakdown

Base rates and favorable decile lifts across market-cap size tiers:

| Feature ID | Large-Cap ($3\text{B}\le\text{Cap}<5\text{B}$) Lift [Base 12.57%] | Mid-Cap ($5\text{B}\le\text{Cap}<20\text{B}$) Lift [Base 9.20%] | Large-Cap ($20\text{B}\le\text{Cap}<200\text{B}$) Lift [Base 6.13%] | Mega-Cap ($\ge 200\text{B}$) Lift [Base 4.28%] |
|---|:---:|:---:|:---:|:---:|
| `atr_pct_14` | 1.8384x | 2.1963x | 2.5028x | 2.4552x |
| `sma20_slope_5` | 1.1578x | 1.2033x | 1.2263x | 1.5833x |
| `close_vs_sma20` | 1.1448x | 1.1895x | 1.2132x | 1.5492x |
| `return_5` | 1.1534x | 1.1949x | 1.2116x | 1.5380x |
| `relative_volume_20` | 1.0963x | 1.1218x | 1.1345x | 1.2982x |
| `proximity_high20` | 0.7816x | 0.7410x | 0.7161x | 0.6558x |

Key insight: The base rate of achieving a clean +10% target within 10 days decreases sharply with size (12.57% for \$3B–\$5B down to 4.28% for \$200B+), but the relative lift of the top technical and volatility features remains robust—and in fact increases in relative terms—within large and mega caps.

---

## 7. Frozen Baseline Comparator Verification

The frozen Stage C benchmark comparator was re-verified against the exact same 20:30 population:
- **Baseline Model:** `volatility_aware_momentum_5`
- **Base Rate:** **8.8644%**
- **Top-10% Clean Rate:** **15.3533%** (**1.7320x lift**)
- **Top-25% Clean Rate:** **12.6881%** (**1.4314x lift**)
- Verification status: **Identical byte-for-byte match with Stage C baseline records.**

---

## 8. Preregistration Errata / Interpretation Notes

### A. LOWER Decile Label Wording Inconsistency in Locked Spec
In `docs/research/specs/LONG-002D1-v1.json`, the specification text refers to Decile 10 as top decile for all features, but for LOWER hypothesized directions (`true_range_compression_5_20`), lowest numerical values are favorable. The runtime implementation strictly mapped favorable observations ($\ge 90$th percentile under the respective sort direction: ascending for LOWER, descending for HIGHER) to Decile 10 (favorable) consistently, ensuring that across all candidate features Decile 10 uniformly represents the preregistered favorable hypothesis.

### B. Bootstrap Terminology
The locked spec mentions "stationary block bootstrap" in prose, but specifies deterministic non-overlapping blocks of calendar sessions (21 and 42 trading sessions). The implementation strictly executed non-overlapping block bootstrap (Politis & Romano 1994 style block resampling without random geometric block lengths) with fixed seed `20260927` to guarantee exact determinism and reproducibility.

---

## 9. Artifact Catalog & Cryptographic Integrity

All external datasets and committed summaries have been verified:

### External Datasets (`data/research/long_002d1/`)
| File Name | Rows | Byte Size | SHA-256 Digest |
|---|---:|---:|---|
| `feature_table.parquet` | 758,731 | 136,524,010 | `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` |
| `feature_decile_detail.parquet` | 150 | 16,638 | `68111ca55d7dadb2151688c875cd9e056903f486cbe8f2b2b2f4de861ea42754` |
| `bootstrap_detail.parquet` | 15,000 | 284,398 | `7906d5bdeea3eee1fc0c9a556f4491234e1e1f815365891e31dbe5834fb8821b` |
| `redundancy_matrix.parquet` | 15 | 12,944 | `a11c360158307d20c9cb76fd582ca9f4d39a37b12db2e1d9160df86fa1dcc8c8` |

### Committed Summaries — Official Corrected Run (`docs/research/artifacts/LONG-002D1/2026-09-28-003539/`)
| File Name | Byte Size | SHA-256 Digest | Description |
|---|---:|---|---|
| `execution_metadata.json` | 2,217 | `0c660bff841820f6a5075ba0f89a609cc9b1a8dfd6bf33379fd159c5f37a521b` | Full run timing, benchmark report, file catalog, and denominators |
| `feature_registry.json` | 5,027 | `61ba48b5562c76b101b30bedd3d1695e5b35f6ec6c076356e4db5e8d28df1e39` | Machine-readable feature definitions, roles, directions, and formulas |
| `feature_census_summary.json` | 114,833 | `f0c962597b0ea38b6cdd501c010b811397979fc36d26b918486ab72f839a1b21` | Full decile tables, annual stability, and market-cap cohort breakdowns |
| `bootstrap_summary.json` | 5,747 | `5396dbcfb717d8baaba6c4f54eef72dc497f7760bed8bd0f85a6a5166ee208c0` | 21-session and 42-session block bootstrap distributions |
| `redundancy_summary.json` | 8,482 | `4a00107c44c310a34da824f6a7cc632a88f16f326eb96e88771e163505d6aba2` | Pairwise Spearman correlation matrix and high-redundancy candidate flags |
| `data_quality_summary.json` | 207,483 | `60a4fcac98e38e0ebf29d7f0442371a6ff4a7dbbfad3f3147aaf04f1ad788f97` | Provider cache payload audit (2,797 hits, 0 misses, 0 attempts, 0 outbound HTTP) |
| `checksums.sha256` | 447 | — | Cryptographic checksums of committed summary artifacts |

### Superseded Artifacts — Run `2026-09-27-223646`
- **Location:** `docs/research/artifacts/LONG-002D1/2026-09-27-223646/`
- **Disposition:** `superseded_execution_audit_defect`
- **Reason:** The empirical D1 population and statistical findings were correct, but runtime loaded non-study discovery candidates, causing blocked live-request-path attempts and unmatched cache provenance records.

---

## 10. Next Steps: Gary / ChatGPT Post-Run Review

Per preregistered status taxonomy rule:
- All candidate features are currently recorded with status `review_pending`.
- Gary and ChatGPT will review the empirical findings in this report to determine:
  1. Which candidate features should be carried forward into the later blinded-review and final-feature-registry work (`LONG-002D2`+).
  2. How to treat the inverted mean-reversion findings on `proximity_high20` and `proximity_high60` (e.g. formulating explicit dip-buying / mean-reversion hypotheses vs retaining them as momentum break candidates).
  3. Whether to pair volatility conditioning (`atr_pct_14`) with trend-following signals (`sma20_slope_5`, `close_vs_sma20`, `return_5`) in subsequent modeling slices.
- `LONG-002D2` remains unauthorized until this post-run review is formally concluded.
