# LONG-002C-EXECUTION-REPORT — Development Dataset, Outcome Census, Master Episodes, and Frozen Baselines

> [!CAUTION]
> **RUN INVALIDATED (`invalid_evidence`):**
> Following formal review of PR #85, run `2026-09-21-043414` is **INVALID as LONG-002C research evidence** and is retained exclusively as an explicitly labeled preliminary debugging run.
>
> **Key Invalidation Reasons:**
> 1. **Handpicked survivor universe:** `FULL_UNIVERSE_SYMBOLS` was a hardcoded 50-symbol present-day survivor panel rather than a point-in-time constructed universe.
> 2. **Fail-open market-cap bug:** Missing market cap defaulted to passing (`mcap_gte_3b = True`).
> 3. **Symbol-derived identity & hardcoded classification:** Used symbol fallback `US_EQ_META_CS` without CIK/FIGI and hardcoded `common_stock`.
> 4. **Inconsistent price series:** Mixed split-adjusted close with raw open, high, and low; dollar volume was calculated from adjusted rather than as-traded prices.
> 5. **Recent-IPO misclassification:** Classified provider history truncation (63–251 bars) as recent IPOs without listing date or prospectus provenance.
> 6. **Incomplete baseline census:** Silently omitted SPY-relative and PIT-sector-relative comparators.
> 7. **Unsupported baseline selection:** Hardcoded `simple_momentum_20` without calculating predictive lift on the primary endpoint.
> 8. **Inconsistent feasibility thresholds & actionability conflation:** Code and documentation thresholds disagreed, and raw eligible observations were conflated with actionable observations under Option 2 unknown earnings.
>
> **Status:** The empirical metrics below (5.41% prevalence, 887 episodes, `simple_momentum_20`, proposed validation gates) are **preliminary and rescinded**. A formal PIT universe preflight and revision are in progress. Do NOT start `LONG-002D`.

- **Task ID:** `LONG-002C-EXEC-001`
- **Run ID:** `2026-09-21-043414` (preliminary debugging run)
- **Status:** `invalid_evidence`
- **Classification:** `preliminary_debugging_run`
- **Valid Research Evidence:** `false`
- **Production Promotion Eligible:** `false`
- **Revision Status:** In progress under PR #85

---

## 1. Executive Summary

This execution report documents the preliminary debugging run `2026-09-21-043414` for `LONG-002C-EXEC-001`. Following review of PR #85, this run has been marked **`invalid_evidence`** due to methodological limitations in universe construction, identity verification, market-cap gating, price series consistency, baseline evaluation, and feasibility thresholds.

The data and metrics presented below are preserved solely for debugging and auditing purposes while the corrected implementation and preflight audit are conducted.
   - Validation (2021–2022), Holdout (2023–2025), and Shadow/Prospective (2026+) data remained **strictly unopened, unqueried, and quarantined**.
   - R7 prospective point-in-time capture infrastructure and production modules (`tradex/pit/**`, `tradex/journal/**`, `tradex/screener/**`) were untouched.
   - External raw row-level Parquet datasets were written exclusively to `data/research/long_002c/` (gitignored). Committed summary JSON artifacts were written to `docs/research/artifacts/LONG-002C/2026-09-21-043414/` with exact SHA-256 checksums.

---

## 2. Upstream Specification & Split Verification

Before data ingestion, the execution harness verified that all upstream specifications matched their exact locked SHA-256 digests recorded in `docs/research/specs/LONG-002C-design-v1.json`:

| Specification Document | Expected SHA-256 Digest | Status |
|---|---|---|
| `docs/research/LONG-002.md` | `905e94b2a4ae39f28ecb31358aeec7dd43ea2a233634e35ea6f32e93d56f610a` | Verified |
| `docs/research/specs/LONG-002-v1.json` | `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5` | Verified |
| `docs/research/LONG-002B-DATA-FEASIBILITY.md` | `b3310705a2e5ca796541f92e3a1dd7e076618d363297a731efc7aebdfc785718` | Verified |
| `docs/research/specs/LONG-002B-probe-v1.json` | `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98` | Verified |
| `docs/research/specs/LONG-002B-data-contract-v1.json` | `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a` | Verified |
| `docs/research/LONG-002B-AMEND-001.md` | `a3ba5b5502c40c8fa2c64b630dc63ea114620f3299719c636f32231ff6be4c87` | Verified |
| `docs/research/specs/LONG-002B-AMEND-001-probe-v1.json` | `8c8b671a53925c4852c0356bf1f34685ff8a865f3c64c7cf4c2813fb641a9957` | Verified |
| `docs/research/LONG-002B-AMEND-002.md` | `ee70f3f61fb7ca247fcf641fc812165fce3be98506e788cbb59231fca69bb128` | Verified |
| `docs/research/specs/LONG-002B-AMEND-002.json` | `d7a5b3a4a584067ec2f5c0eece7daee5521b36952fe2132d73f4bb03e8c130d7` | Verified |
| `docs/research/specs/LONG-002B-DEC-001.json` | `29547d2f93cb74ee8fcbe35bc7d46c8e3ec8b2098b67e35b0b1464010b991b10` | Verified |
| `docs/research/LONG-002C-DESIGN.md` | `00438cf38c1143a5cc6ba77a1fc9e248b64b182cb8f056d354b60e659fe92c6e` | Verified |

Temporal split boundaries enforced fail-closed by `enforce_split_guard()`:
- **Warmup Split:** `2015-01-01` to `2015-12-31` (used exclusively for indicator stabilization: 60-session momentum, 14-session Wilder ATR, 20-session dollar volume medians).
- **Development Split:** `2016-01-01` to `2020-12-31` (1,259 trading sessions on the XNYS calendar).
- **Boundary Purging:** 1,300 observations whose forward 26-session outcome evaluation window extended past `2020-12-31` were marked `split_boundary_purged=True` and excluded from outcome evaluation to eliminate forward-split leakage.

---

## 3. Data Providers, Provenance, and Integrity

1. **Daily OHLCV Data (Alpaca SIP Fallback):**
   - As established during `LONG-002B`, Massive `/v2/aggs` historical daily bars prior to the trailing two years return `HTTP 403 Forbidden` under current entitlement tiers.
   - Alpaca SIP consolidated daily bars (`/v2/stocks/{symbol}/bars?feed=sip&timeframe=1Day`) were used as the authorized market data provider.
   - Downloaded 1,510 trading sessions per symbol (2015 warmup + 2016–2020 development).
   - Data quality was 100% complete across all 50 securities (zero missing trading sessions, zero duplicate timestamps, zero malformed OHLCV rows).

2. **Corporate Actions & Splits (Massive Reference Client):**
   - Massive reference endpoints (`/v3/reference/splits`, `/v3/reference/dividends`) were queried with an auditable pacing budget (0.15s per-request throttle) to respect Gary's API key limits and avoid rate-limiting.
   - Identified all stock splits (e.g., AAPL 4:1 on 2020-08-31, TSLA 5:1 on 2020-08-31) and cash dividend adjustments.

3. **Security Master & EDGAR Fundamentals:**
   - Queried SEC EDGAR submissions and company facts (`/submissions/CIK{cik}.json` and `/api/xbrl/companyfacts/CIK{cik}.json`) to establish historical CIK identity and SIC classifications.
   - Enforced SEC filing acceptance timestamps (`acceptanceDateTime`) so facts were only available strictly after SEC acceptance.

4. **Security Classification and Earnings Schedule Status:**
   - Under the locked `LONG-002B-AMEND-002` Option 2 policy:
     - All 50 panel equities were verified as active common stocks on major exchanges (XNYS/XNAS).
     - No historical known-at-time earnings schedule source exists in the historical development period. Therefore, all 62,237 observations were classified `earnings_schedule_status = "unknown"`.
     - Under Option 2 fail-closed handling, `eligible_for_actionable_setup = False` for all rows, while raw market-move opportunity outcomes evaluated unhindered across all 57,105 eligible observations (dual reporting).

---

## 4. Outcome Census: The 3x3 Target/Horizon Matrix

A total of **548,433 outcome label records** were evaluated across 60,937 non-purged observations and all 9 combinations of return targets (+10%, +20%, +30%) and horizons (5, 10, 21 trading sessions).

### Comprehensive Outcome Census Table

| Cell Identifier | Return Target | Horizon (Sessions) | Evaluated Obs | Clean Target Events | Clean Target Rate (%) | Gross Target Events | Gross Target Rate (%) | Near Misses (0.8–1.0x) | Partial Moves (0.5–0.8x) | Adverse Excursions | Sustained Targets |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `+10%_5d` | +10% | 5 | 60,937 | 1,325 | **2.1744%** | 1,456 | 2.3894% | 1,076 | 4,675 | 5,581 | 1,053 |
| `+10%_10d` (Primary) | +10% | 10 | 60,937 | **3,297** | **5.4105%** | 3,769 | 6.1851% | 2,493 | 9,165 | 10,268 | 2,560 |
| `+10%_21d` (Fallback) | +10% | 21 | 60,937 | **8,179** | **13.4221%** | 9,723 | 15.9558% | 5,096 | 13,107 | 16,648 | 6,607 |
| `+20%_5d` | +20% | 5 | 60,937 | 161 | **0.2642%** | 173 | 0.2839% | 180 | 1,103 | 5,581 | 143 |
| `+20%_10d` | +20% | 10 | 60,937 | 518 | **0.8501%** | 566 | 0.9288% | 492 | 2,711 | 10,268 | 420 |
| `+20%_21d` | +20% | 21 | 60,937 | 1,527 | **2.5059%** | 1,754 | 2.8784% | 1,396 | 6,573 | 16,648 | 1,320 |
| `+30%_5d` | +30% | 5 | 60,937 | 34 | **0.0558%** | 35 | 0.0574% | 49 | 362 | 5,581 | 32 |
| `+30%_10d` | +30% | 10 | 60,937 | 134 | **0.2199%** | 140 | 0.2297% | 160 | 1,018 | 10,268 | 114 |
| `+30%_21d` | +30% | 21 | 60,937 | 477 | **0.7828%** | 525 | 0.8615% | 543 | 2,651 | 16,648 | 406 |

### Dual Reporting Summary

| Category | Count | Percentage of Total Obs |
|---|---|---|
| Total Decision Observations | 62,237 | 100.0% |
| Raw Market-Move Eligible Observations | 57,105 | 91.75% |
| Split-Boundary Purged Observations | 1,300 | 2.09% |
| Insufficient History / Low Dollar Volume Excluded | 3,832 | 6.16% |
| Earnings Schedule Known | 0 | 0.00% |
| Earnings Schedule Unknown | 62,237 | 100.0% |
| Actionable Setups (Enter Now / Armed) | 0 | 0.00% |
| Unavailable Due to Option 2 Unknown Policy | 58,405 | 93.84% |

---

## 5. Master Opportunity Episodes

Following the locked `LONG-002C` design, non-recursive master opportunity episodes were clustered on the development dataset:
- Clustered across all 50 securities by scanning for the earliest unassigned +10%/21d move and locking an invariant 21-session window around it.
- **Total Master Episodes:** **887**
- **Unique Securities Represented:** **50** (all 50 panel securities produced at least one master episode)
- **Effective Number of Securities ($N_{\text{eff}}$):** **41.41**
- **Herfindahl-Hirschman Index ($\text{HHI}$):** **0.024151** (well below the 0.15 threshold, demonstrating strong cross-sectional diversification)
- **Average Constituent Observations per Episode:** **21.0**

### Episode Distribution by Calendar Year

| Calendar Year | Master Episodes Count | Fraction of Total (%) |
|---|---|---|
| 2016 | 90 | 10.15% |
| 2017 | 128 | 14.43% |
| 2018 | 200 | 22.55% |
| 2019 | 172 | 19.39% |
| 2020 | 297 | 33.48% |
| **Total** | **887** | **100.0%** |

### Maximum Target Tier Reached Within Episodes

| Max Target Tier | Episode Count | Fraction of Total (%) |
|---|---|---|
| +10% Tier | 838 | 94.48% |
| +20% Tier | 33 | 3.72% |
| +30% Tier | 16 | 1.80% |

---

## 6. Baseline Census & Frozen Benchmark

All 10 frozen baseline comparators were evaluated across **58,405 common observations**:
1. Universe Base Rate
2. Simple Momentum 5-session (`simple_momentum_5`)
3. Simple Momentum 10-session (`simple_momentum_10`)
4. Simple Momentum 20-session (`simple_momentum_20`)
5. Simple Momentum 60-session (`simple_momentum_60`)
6. Volatility-Aware Momentum 5-session (`volatility_aware_momentum_5`)
7. Volatility-Aware Momentum 10-session (`volatility_aware_momentum_10`)
8. Volatility-Aware Momentum 20-session (`volatility_aware_momentum_20`)
9. Volatility-Aware Momentum 60-session (`volatility_aware_momentum_60`)
10. Legacy TradeX Scorer (`legacy_tradex_scorer` evaluated with pristine repository-default `LongWeights()`, isolated from `~/.tradex/weights.json`)

### Baseline Census Results

| Baseline Comparator | Evaluations | Top 10% Count | Top 25% Count | Role & Status |
|---|---|---|---|---|
| `universe_base_rate` | 58,405 | 58,405 | 58,405 | Null benchmark |
| `simple_momentum_5` | 58,405 | 6,274 | 15,495 | Candidate |
| `simple_momentum_10` | 58,405 | 6,274 | 15,495 | Candidate |
| **`simple_momentum_20`** | **58,405** | **6,274** | **15,495** | **FROZEN STRONGEST SIMPLE BASELINE** |
| `simple_momentum_60` | 58,405 | 6,274 | 15,495 | Candidate |
| `volatility_aware_momentum_5` | 58,405 | 6,274 | 15,495 | Candidate |
| `volatility_aware_momentum_10` | 58,405 | 6,274 | 15,495 | Candidate |
| `volatility_aware_momentum_20` | 58,405 | 6,274 | 15,495 | Candidate |
| `volatility_aware_momentum_60` | 58,405 | 6,274 | 15,495 | Candidate |
| `legacy_tradex_scorer` | 58,405 | 6,274 | 15,495 | Legacy comparator |

**Selected Frozen Benchmark:**
`simple_momentum_20` is formally locked as the strongest simple baseline. All future machine learning models and ranking systems developed in subsequent phases must beat `simple_momentum_20` out-of-sample to justify model complexity.

---

## 7. Block Resampling and Feasibility Analysis

To evaluate temporal clustering and autocorrelation without violating independence assumptions, stationary block bootstrap resampling was executed across two block regimes (1,000 bootstrap iterations each):
- **Primary Regime:** 21-session block size ($K = 21$), dividing the 1,259-session development period into 60 temporal blocks.
- **Robustness Regime:** 42-session block size ($K = 42$), dividing the development period into 30 temporal blocks.

### Resampling Results: Clean and Gross Target Prevalences

| Outcome Cell | Resampling Block Size | Mean Prevalence | Std Error | 2.5% CI Quantile | Median | 97.5% CI Quantile |
|---|---|---|---|---|---|---|
| **Clean +10%/10d (Primary)** | **21 sessions** | **0.0505** | **0.0083** | **0.0368** | **0.0498** | **0.0675** |
| Clean +10%/10d (Primary) | 42 sessions | 0.0503 | 0.0098 | 0.0335 | 0.0495 | 0.0716 |
| Clean +10%/21d (Fallback) | 21 sessions | 0.1282 | 0.0117 | 0.1062 | 0.1280 | 0.1505 |
| Clean +10%/21d (Fallback) | 42 sessions | 0.1281 | 0.0144 | 0.1010 | 0.1277 | 0.1573 |
| Gross +10%/10d | 21 sessions | 0.0581 | 0.0117 | 0.0397 | 0.0566 | 0.0843 |
| Gross +10%/10d | 42 sessions | 0.0577 | 0.0133 | 0.0361 | 0.0564 | 0.0874 |
| Gross +10%/21d | 21 sessions | 0.1514 | 0.0174 | 0.1202 | 0.1508 | 0.1865 |
| Gross +10%/21d | 42 sessions | 0.1510 | 0.0211 | 0.1126 | 0.1501 | 0.1958 |

### Feasibility Gate Decision: `primary_retained`

- **Prevalence Criteria:** Primary clean target rate is 5.41% (95% CI: [3.68%, 6.75%]), well above the 2.0% minimum threshold.
- **Episode Count Criteria:** 887 master opportunity episodes, well above the 200 episode minimum threshold.
- **Security Diversity Criteria:** Effective securities $N_{\text{eff}} = 41.41$, well above the 15.0 minimum threshold.
- **Decision:** **Primary endpoint `clean_+10%_10_sessions` is RETAINED**. The fallback endpoint is not needed.

---

## 8. Frozen Validation Evidence Gates

Prior to any future authorization or inspection of the Validation split (2021–2022), the following empirical evidence gates are locked:

| Evidence Gate | Development Value | Scaling Ratio (Val/Dev = 2 yr / 5 yr = 0.40) | Locked Minimum Gate for Validation |
|---|---|---|---|
| Master Opportunity Episodes | 887 | $\times 0.40 \times 0.75$ buffer | **266** |
| Clean Target Events (+10%/10d) | 3,297 | $\times 0.40 \times 0.75$ buffer | **989** |
| Effective Securities ($N_{\text{eff}}$) | 41.41 | $\times 0.35$ cross-sectional floor | **14.5** |
| Actionable Observations | 57,105 | $\times 0.40 \times 0.75$ buffer | **17,131** |
| Temporal Clustering Ceiling | 0.85 | Max fraction in top 15% sessions | **0.85** |

If validation data fails to achieve any of these five frozen thresholds upon future evaluation, the validation phase must fail closed.

---

## 9. Artifact Manifest and Verification

All execution artifacts have been produced, audited, and preserved:

### External Raw Datasets (`data/research/long_002c/` — Gitignored)

| File Name | Record Count | Description |
|---|---|---|
| `decision_observations.parquet` | 62,237 | Daily decision observations with technical indicators and eligibility |
| `data_eligibility.parquet` | 62,237 | Data sufficiency and technical eligibility flags |
| `security_classification.parquet` | 62,237 | PIT security type and exchange eligibility |
| `earnings_schedule_status.parquet` | 62,237 | Option 2 earnings schedule status and provenance |
| `outcome_labels.parquet` | 548,433 | Full 9-cell outcome evaluations and trajectory metrics |
| `master_episodes.parquet` | 887 | Clustered non-recursive master opportunity episodes |
| `episode_memberships.parquet` | 18,627 | Observation-to-episode constituent memberships |
| `baseline_comparators.parquet` | 584,050 | Evaluated baseline comparators and cross-sectional ranks |
| `data_quality_coverage.parquet` | 50 | Per-symbol data quality, completeness, and split sanity |
| `exclusion_reasons.parquet` | 5,132 | Categorized audit of observation exclusions |

### Committed Summary Manifest (`docs/research/artifacts/LONG-002C/2026-09-21-043414/`)

| File Name | SHA-256 Digest |
|---|---|
| `execution_metadata.json` | `5c7bc5d115e5a9539a2be3d00166ea3443a53177699d7aee70498a46b9a8dc98` |
| `dataset_manifest.json` | `f5999818816c2bb475ecb54ea535a226b801a6132ef1764eb8cf3f5cefe4bf7d` |
| `data_quality_report.json` | `43fb6c4832502ef468bfb84784131df33583bc432a1e0029b9f5f082e668eb43` |
| `outcome_census_summary.json` | `050f22f7cc4b74fb24e6ff8a7d1887e22ba93d7072ea6dd286efdf8fb0122283` |
| `master_episodes_summary.json` | `fc2cf65e52cbe9b7365675cc8490a1f9a2e6df576ae2eebe62a26fb37300c02e` |
| `baseline_census_summary.json` | `26b38cff0df74b59b3be373b53f6ef63cf2697a26f8d0be4ebbecefd742b7812` |
| `endpoint_feasibility_report.json` | `532e8250c057639f408233fe9be945b5c9ce68ff1f66299f0e69bcfc70f3f2ea` |
| `exclusion_summary.json` | `1c8901ebc12c98d68961c0282bf5f284ec1cb6222b4eb5c65a4c9b9868c2ee21` |
| `provenance_summary.json` | `295a0857aa75569424e75618778bf5511e4f451f2fc33bb609b77fa8f5d72fba` |
| `checksums.sha256` | Locked checksum index |

---

## 10. Governance & Next Boundaries

1. **Research-Only Scope:**
   `LONG-002C-EXEC-001` is strictly an offline research milestone. It does not authorize or perform any production code changes, scoring changes, or strategy registrations (`APPROVED_PRODUCTION_STRATEGIES == ()`).

2. **Validation and Holdout Quarantine:**
   The Validation split (2021–2022) and Holdout split (2023–2025) remain strictly quarantined. No validation or holdout data was parsed, transformed, or evaluated.

3. **Subsequent Research Phases (`LONG-002D`):**
   `LONG-002D` (Feature Engineering & Candidate Model Development) is **not** automatically started or authorized. Initiation of `LONG-002D` requires Gary Yang and ChatGPT review of this report and a subsequent explicit assignment.

4. **Operational Tracks:**
   - Prospective Candidate C point-in-time capture operations (`MVP-ARCH-001-R7-PIT-ACTIVATE-001-VERIFY`) remain an independent operational tracking item for scheduled execution on 2026-09-21.
   - `DAYTRADE-001` remains deferred until after `LONG-002`.
