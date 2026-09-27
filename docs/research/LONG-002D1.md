# LONG-002D1 — Core Technical & Market-Context Feature Census Preregistration

- **Task ID:** `LONG-002D1-CORE-KPI-CENSUS`
- **Program:** `LONG-002` (Rapid-Upside Long Opportunity Program)
- **Phase:** `LONG-002D1` (Core Technical / Market-Context KPI Census)
- **Classification:** `research-only` (development split census only)
- **Status:** `preregistered`
- **Production Promotion Eligible:** `false` (`APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved)
- **Machine-Readable Specification:** [`docs/research/specs/LONG-002D1-v1.json`](./specs/LONG-002D1-v1.json)
- **Spec SHA-256:** `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381`
- **Upstream Stage C Run ID:** `2026-09-27-161243`
- **Upstream Stage C Code SHA:** `d6a300e556c690c83ff8b9265833667c02dc94ec`
- **Primary Endpoint:** Clean +10% within 10 trading sessions (`primary_retained`)
- **Frozen Development Baseline Comparator:** `volatility_aware_momentum_5` (Top-10 Lift: 1.7320x, Clean Rate: 15.3533%)

---

## 1. Executive Summary & Objective

This document establishes the official preregistered research specification for **`LONG-002D1`**, the first slice of the `LONG-002D` discovery phase.

The objective of `LONG-002D1` is to answer:
> *"Which simple, explainable technical/context feature hypotheses show enough development evidence, coverage, stability, or distinct information to justify carrying forward into the later blinded-review/final-feature-registry work?"*

### Critical Boundaries:
- **This is NOT model development.**
- Do NOT fit a predictive model (no logistic regression, trees, neural nets, or scoring models).
- Do NOT optimize feature weights or thresholds.
- Do NOT create a production score or ranking.
- Do NOT access validation (2021–2022), holdout (2023–2025), or shadow (2026+) data.
- The goal is to cheaply and descriptively narrow the hypothesis space before `LONG-002D2` and `LONG-002E`.

---

## 2. Upstream Source Evidence Verification

All analysis consumes the immutable development dataset generated and approved under `LONG-002C-EXEC-001` (Run ID: `2026-09-27-161243`).

### Verified Stage C External Parquet Checksums:
All 11 external Parquet files located at `data/research/long_002c/` have been verified byte-for-byte against committed digests:

| Parquet File | Expected Row Count | Expected Bytes | SHA-256 Digest |
|---|---|---|---|
| `decision_observations.parquet` | 2,815,600 | 40,622,094 | `722bee866cabb697931dfb96abaf7f9250f1cd1240b405d2e308af0b6bbb48af` |
| `data_eligibility.parquet` | 2,815,600 | 21,858,159 | `16147606e629daf02e54db4b6b0127ede04aeb45608f27900a92f73805baa4d9` |
| `security_classification_status.parquet` | 2,815,600 | 3,087,801 | `65adc6170f2095371f3842153256b96c16042b88c6716d78c329f45ffb8d4d6d` |
| `earnings_schedule_status.parquet` | 2,815,600 | 3,062,791 | `439b85a5c5c2ed618585007fe6e62ef213eb2600bb47ba222f35ff338557d05b` |
| `outcome_matrix.parquet` | 13,657,194 | 283,336,113 | `b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3` |
| `master_episodes.parquet` | 16,139 | 502,442 | `1fe5b36f98919465007a720908c626203e5272b054a4ef76be772db279b3cc98` |
| `constituent_memberships.parquet` | 677,736 | 624,457 | `53a8adc92f1210ef3a1b6d10c9eedd1f360dad2760897f97b5d293f473734b11` |
| `baseline_comparator_outputs.parquet` | 21,244,524 | 190,588,243 | `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` |
| `data_quality_coverage.parquet` | 1,291 | 24,845 | `265973b7e88ce98f65c492836fd8a4949d72c5de7e28fc4e62442bc01993e9bb` |
| `provenance_records.parquet` | 8,211 | 1,225,777 | `4ff93f7008310df2e115937ed6acbc2d435f58f06130a369f4b5b72615f4554f` |
| `exclusions.parquet` | 3,684,007 | 5,967,704 | `9624d11dd191d967d6a3160e2f877d02027d744dcd5b2d46a6b638837ba97da8` |

### Provider Isolation & Cache Provenance:
- Cache directory is used strictly **READ-ONLY**.
- `allow_live=False` is enforced. Any attempted live network call fails closed.
- In addition to Stage C Parquet digests, the SHA-256 of every cached daily-bar payload consumed by D1 is recorded and verified against Stage C provenance records where possible; any provenance limitation is explicitly disclosed.

---

## 3. Study Population & Primary Endpoint

- **Split:** Development only (`2016-01-01` through `2020-12-31`, 1,259 sessions).
- **Decision Cutoff:** `20:30` ET post-close snapshot only. (09:00 is strictly out of scope for D1).
- **Eligibility Filter:** `raw_outcome_eligible == True` and `split_boundary_purged == False`.
- **Primary Population Denominator:** Exactly **758,731** observations.
- **Primary Endpoint:** Clean +10% within 10 trading sessions (`target_pct == 10.0` and `horizon_sessions == 10`).
- **Primary Base Rate:** Exactly **67,257 clean events** (**8.8644%** prevalence).

---

## 4. D1 Core Feature Registry

The feature set is intentionally bounded to 15 features (4 reference features, 9 core candidate features, 1 market-regime diagnostic, and 1 redundancy diagnostic).

All technical indicators use split-normalized, dividend-unadjusted analytical prices. Dollar-volume trend uses as-traded close $\times$ volume.

### Reference Features:
- **R1. `return_5`:** `close_t / close_t-5 - 1` (min 5 prior sessions).
- **R2. `return_20`:** `close_t / close_t-20 - 1` (min 20 prior sessions).
- **R3. `return_60`:** `close_t / close_t-60 - 1` (min 60 prior sessions).
- **R4. `atr_pct_14`:** `Wilder_ATR14_t / close_t` (min 14 prior sessions).

### Core Candidate Features:
- **F1. `close_vs_sma20`:** `close_t / SMA20_t - 1`. Hypothesized direction: **HIGHER**.
- **F2. `close_vs_sma60`:** `close_t / SMA60_t - 1`. Hypothesized direction: **HIGHER**.
- **F3. `sma20_slope_5`:** `SMA20_t / SMA20_t-5 - 1`. Hypothesized direction: **HIGHER**.
- **F4. `proximity_high20`:** `close_t / rolling_max_close_20_t - 1`. Hypothesized direction: **HIGHER** (closer to 0 is higher).
- **F5. `proximity_high60`:** `close_t / rolling_max_close_60_t - 1`. Hypothesized direction: **HIGHER**.
- **F6. `true_range_compression_5_20`:** `median(TR over latest 5) / median(TR over latest 20)`. Hypothesized direction: **LOWER**.
- **F7. `relative_volume_20`:** `volume_t / median(volume over prior 20 completed sessions, excluding t)`. Hypothesized direction: **HIGHER**.
- **F8. `dollar_volume_trend_20_60`:** `median(as_traded_close * volume over latest 20) / median(as_traded_close * volume over latest 60) - 1`. Hypothesized direction: **HIGHER**.
- **F9. `up_volume_share_20`:** `sum(volume for sessions in latest 20 where close_s > close_{s-1}) / sum(volume over latest 20)`. Hypothesized direction: **HIGHER**.
- **F10. `spy_return_20`:** `SPY close_t / SPY close_t-20 - 1`. Hypothesized direction: **HIGHER** (Date-level market-regime context diagnostic).
- **F11. `stock_minus_spy_20`:** `return_20 - spy_return_20`. **Reference / Redundancy Diagnostic**.

### Missing-Value & Lookback Policy:
Features requiring unavailable history evaluate to **`NULL` (`NaN`)**, never imputed with 0.

---

## 5. Preregistered Ranking & Evaluation Semantics

1. **Cross-Sectional Stock Ranking:**
   - Evaluated strictly within each 20:30 `as_of_date` cross-section across non-null eligible observations.
   - For `HIGHER`: descending order, with deterministic `immutable_security_id` ASC tie-break.
   - For `LOWER`: ascending order, with deterministic `immutable_security_id` ASC tie-break.
   - Percentile convention matching Stage C frozen baseline:
     $$\text{percentile} = 100.0 \times \frac{N_{\text{valid}} - \text{rank\_idx}}{N_{\text{valid}}}$$
     where $\text{rank\_idx} \in \{0, \dots, N_{\text{valid}} - 1\}$.
   - Top Decile: $\text{percentile} \ge 90.0$.
   - Top Quartile: $\text{percentile} \ge 75.0$.
   - **Redundancy Invariant:** Within any same-date cross-section, subtracting a constant `spy_return_20` preserves identical relative stock ordering; therefore, `stock_minus_spy_20` must reproduce the identical same-date ranking as `return_20` on identical non-null sets.

2. **Market-Regime Diagnostic (`spy_return_20`):**
   - Deciles are formed across unique development trading dates (1,239 valid dates).
   - Date deciles are mapped to observations for outcome evaluation.
   - Both unique date count and observation count are reported per decile.
   - SPY regime lift is not presented as directly comparable to cross-sectional stock-selection lift.

3. **Dependence-Aware Uncertainty:**
   - 1,000 stationary calendar block bootstrap iterations.
   - Primary: 21-session calendar blocks (60 blocks).
   - Robustness: 42-session calendar blocks (30 blocks).
   - Fixed preregistered seed: `20260927`.
   - Metric: Favorable-decile clean-rate lift over common base rate.
   - Market cross-sections are kept intact within calendar blocks.

4. **Redundancy Analysis:**
   - Pairwise Spearman correlation matrix on the deterministic common non-null sample.
   - Flag $|\rho| \ge 0.95$ as `high_redundancy_candidate`.

5. **Status Taxonomy & Carry-Forward Rule:**
   - All candidate features are initialized to `review_pending`.
   - Reference features and diagnostics are marked `reference`.
   - Mechanical flags (`high_redundancy_candidate`, `coverage_limited`) are applied deterministically.
   - No feature is auto-assigned `descriptively_promising` or `weak_or_inconsistent`. Gary Yang and ChatGPT will review the empirical packet and determine carry-forward to `LONG-002D2`.

---

## 6. Runtime Gate & Performance Controls

To prevent repeating the LONG-002C performance bottleneck, a pre-launch benchmark over 25 representative eligible securities is executed first:
- Preferred projected full feature-construction runtime: **< 10 minutes**.
- Hard gate: **< 20 minutes**.
- Descriptive aggregation and bootstrap phase is also measured (< 10 minutes).
- Peak memory working set is audited.
- If runtime exceeds gate, execution halts.

---

## 7. Artifact Schema

### External Datasets (`data/research/long_002d1/` — Gitignored):
- `feature_table.parquet`: Full row-level feature values and cross-sectional ranks ($N = 758,731$).
- `feature_decile_detail.parquet`: Decile detail tables across all features.
- `bootstrap_detail.parquet`: 1,000 iteration bootstrap distribution records.
- `redundancy_matrix.parquet`: Full pairwise correlation matrix.

### Committed Summary Manifest (`docs/research/artifacts/LONG-002D1/<run-id>/`):
- `execution_metadata.json`: Runtime, parameters, environment, external Parquet manifests with row counts, bytes, and SHA-256 digests.
- `feature_registry.json`: Preregistered feature definitions and formulas.
- `feature_census_summary.json`: Census tables, deciles, annual breakdowns, stability.
- `bootstrap_summary.json`: 21-session and 42-session 95% bootstrap intervals.
- `redundancy_summary.json`: Spearman correlation matrix and redundancy flags.
- `data_quality_summary.json`: Usable observation counts, coverage, and cache payload provenance audit.
- `checksums.sha256`: Formal checksum index.
- Results report: `docs/research/LONG-002D1-RESULTS.md`.
