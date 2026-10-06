# LONG-002E1: Preregistered Development-Only Round-1 Candidate-System Search Results

- **Task ID:** `LONG-002E1-ROUND1-CANDIDATE-SEARCH-001`
- **Program:** `LONG-002` (Rapid-Upside Long Opportunity Program)
- **Phase:** `LONG-002E1` (Round-1 Candidate Search)
- **Authorization:** Gary Yang (authorized 2026-10-05)
- **Classification:** Research-Only (Development Split Only)
- **Base Git SHA:** `8058c5d858b70090335338176f11a20ddfd04502`
- **Preregistration Commit SHA:** `49103f84ffbf7cd7b60216c2866ad103282bae58`
- **Preregistration Spec SHA-256:** `d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0`
- **Execution Code SHA:** `8446ca948032b599314315a33f3380425cdc9e03`
- **Official Run ID:** `LONG-002E1-20261006_133722`
- **Round-1 Search Budget Accounting:** 36 / 36 configurations attempted and accounted
- **Remaining LONG-002E Search Budget:** 12 configurations
- **Round 2 Authorized:** `false` (`requires_separate_assignment = true`)
- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)

---

## 1. Executive Summary & Purpose

LONG-002E1 is the first controlled empirical candidate-system search for the LONG-002 program. Among the 8 frozen features established in LONG-002D3B, exactly 36 material configurations across 3 approved model families were evaluated strictly on the DEVELOPMENT split (2016–2020 at 20:30 ET) using chronological expanding-window out-of-fold evaluation (2017–2020 primary evaluation period).

> [!IMPORTANT]
> This report presents DEVELOPMENT-ONLY evidence. It does NOT constitute validation, holdout, or shadow support, and does NOT authorize production changes, trading triggers, or Round 2 execution.

## 2. Matched Baseline Comparator Performance (VAM5)

All candidate configurations are evaluated on the exact same common population and dates as the frozen baseline comparator `volatility_aware_momentum_5` (50% return_5 percentile + 50% atr_pct_14 percentile).

- **Evaluation Period:** 2017-01-01 to 2020-12-31 (981 dates)
- **OOF Base Rate:** 8.8685%
- **Matched VAM5 Precision@10:** 21.0439% (2.3729x lift)
- **Matched VAM5 Precision@25:** 18.1615% (2.0479x lift)
- **Matched VAM5 Clean Move Value @10:** 3.3499
- **Matched VAM5 Adverse Rate @10:** 43.8700%

### Annual Matched VAM5 Precision@10:

| Year | Matched VAM5 Precision@10 |
|:---:|:---:|
| 2017 | 12.3506% |
| 2018 | 17.7291% |
| 2019 | 23.6111% |
| 2020 | 32.1311% |

---

## 3. Round-1 Family Summary & Dispositions

### Family: `cross_sectional_rank_score`
- Total Configs: 12 | Eligible: 0 | Inconclusive: 0 | Not Supported: 12 | Invalid: 0
- Best Configuration (by locked ordering): `RANK_S2_T2`

| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `RANK_S2_T2` | S2 | `round1_not_supported` | 18.1189% | -2.9251% | 15.6439% | -2.5176% | [-0.0451, -0.0150] | 0/4 | 42.1400% | 2.86 |
| `RANK_S4_T2` | S4 | `round1_not_supported` | 17.6744% | -3.3695% | 15.9503% | -2.2112% | [-0.0477, -0.0207] | 0/4 | 41.7000% | 2.78 |
| `RANK_S1_T2` | S1 | `round1_not_supported` | 17.5917% | -3.4522% | 15.3830% | -2.7785% | [-0.0518, -0.0185] | 0/4 | 42.1300% | 2.75 |
| `RANK_S3_T2` | S3 | `round1_not_supported` | 17.4470% | -3.5969% | 15.8054% | -2.3561% | [-0.0503, -0.0228] | 0/4 | 41.4300% | 2.73 |
| `RANK_S2_T3` | S2 | `round1_not_supported` | 17.1473% | -3.8966% | 14.8489% | -3.3126% | [-0.0525, -0.0257] | 0/4 | 41.2300% | 2.66 |
| `RANK_S1_T3` | S1 | `round1_not_supported` | 16.8165% | -4.2274% | 14.4389% | -3.7226% | [-0.0583, -0.0260] | 0/4 | 41.3900% | 2.61 |
| `RANK_S4_T3` | S4 | `round1_not_supported` | 16.7028% | -4.3411% | 14.7081% | -3.4534% | [-0.0568, -0.0309] | 0/4 | 41.1400% | 2.57 |
| `RANK_S3_T3` | S3 | `round1_not_supported` | 16.5685% | -4.4755% | 14.7039% | -3.4576% | [-0.0578, -0.0323] | 0/4 | 41.0500% | 2.53 |
| `RANK_S1_T1` | S1 | `round1_not_supported` | 16.2584% | -4.7855% | 13.9213% | -4.2402% | [-0.0656, -0.0313] | 0/4 | 41.1500% | 2.52 |
| `RANK_S2_T1` | S2 | `round1_not_supported` | 15.8140% | -5.2300% | 13.4741% | -4.6874% | [-0.0712, -0.0355] | 0/4 | 40.3900% | 2.45 |
| `RANK_S4_T1` | S4 | `round1_not_supported` | 14.2739% | -6.7700% | 12.4555% | -5.7060% | [-0.0857, -0.0517] | 0/4 | 38.4000% | 2.11 |
| `RANK_S3_T1` | S3 | `round1_not_supported` | 14.1189% | -6.9251% | 12.4762% | -5.6853% | [-0.0866, -0.0537] | 0/4 | 38.7400% | 2.09 |


### Family: `regularized_probabilistic`
- Total Configs: 12 | Eligible: 0 | Inconclusive: 12 | Not Supported: 0 | Invalid: 0
- Best Configuration (by locked ordering): `LOGIT_S4_C300`

| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `LOGIT_S4_C300` | S4 | `round1_inconclusive` | 26.8109% | +2.7216% | 25.2420% | +4.2909% | [0.0054, 0.0489] | 2/4 | 39.2500% | 5.11 |
| `LOGIT_S4_C030` | S4 | `round1_inconclusive` | 26.7969% | +2.7076% | 25.2476% | +4.2965% | [0.0052, 0.0488] | 2/4 | 39.2000% | 5.11 |
| `LOGIT_S4_C003` | S4 | `round1_inconclusive` | 26.7132% | +2.6239% | 25.2643% | +4.3133% | [0.0046, 0.0489] | 2/4 | 39.3000% | 5.10 |
| `LOGIT_S3_C300` | S3 | `round1_inconclusive` | 26.6294% | +2.5401% | 25.1860% | +4.2350% | [0.0033, 0.0461] | 2/4 | 39.0800% | 5.09 |
| `LOGIT_S2_C300` | S2 | `round1_inconclusive` | 26.6155% | +2.5262% | 25.1916% | +4.2406% | [0.0031, 0.0464] | 2/4 | 39.0900% | 5.09 |
| `LOGIT_S3_C030` | S3 | `round1_inconclusive` | 26.6015% | +2.5122% | 25.1916% | +4.2406% | [0.0031, 0.0464] | 2/4 | 39.1100% | 5.08 |
| `LOGIT_S2_C030` | S2 | `round1_inconclusive` | 26.6015% | +2.5122% | 25.1916% | +4.2406% | [0.0028, 0.0464] | 2/4 | 39.0600% | 5.09 |
| `LOGIT_S2_C003` | S2 | `round1_inconclusive` | 26.5457% | +2.4564% | 25.1972% | +4.2462% | [0.0024, 0.0461] | 2/4 | 39.0800% | 5.07 |
| `LOGIT_S3_C003` | S3 | `round1_inconclusive` | 26.5178% | +2.4285% | 25.2364% | +4.2853% | [0.0021, 0.0458] | 2/4 | 39.0600% | 5.07 |
| `LOGIT_S1_C003` | S1 | `round1_inconclusive` | 26.1828% | +2.0935% | 25.2979% | +4.3469% | [-0.0020, 0.0422] | 2/4 | 38.7400% | 5.00 |
| `LOGIT_S1_C030` | S1 | `round1_inconclusive` | 26.1689% | +2.0796% | 25.2979% | +4.3469% | [-0.0021, 0.0419] | 2/4 | 38.7600% | 5.00 |
| `LOGIT_S1_C300` | S1 | `round1_inconclusive` | 26.1689% | +2.0796% | 25.2979% | +4.3469% | [-0.0021, 0.0419] | 2/4 | 38.7600% | 5.00 |


### Family: `shallow_strongly_regularized_gbdt`
- Total Configs: 12 | Eligible: 0 | Inconclusive: 12 | Not Supported: 0 | Invalid: 0
- Best Configuration (by locked ordering): `GBDT_S1_G2`

| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `GBDT_S1_G2` | S1 | `round1_inconclusive` | 25.4431% | +1.3538% | 24.6210% | +3.6699% | [-0.0062, 0.0322] | 2/4 | 40.9200% | 4.07 |
| `GBDT_S1_G3` | S1 | `round1_inconclusive` | 25.3454% | +1.2561% | 24.7273% | +3.7762% | [-0.0052, 0.0290] | 2/4 | 41.3500% | 4.06 |
| `GBDT_S3_G3` | S3 | `round1_inconclusive` | 25.2756% | +1.1863% | 24.4643% | +3.5133% | [-0.0088, 0.0303] | 2/4 | 41.4000% | 3.96 |
| `GBDT_S3_G2` | S3 | `round1_inconclusive` | 25.1919% | +1.1026% | 24.4699% | +3.5189% | [-0.0087, 0.0291] | 2/4 | 41.1400% | 3.99 |
| `GBDT_S4_G2` | S4 | `round1_inconclusive` | 25.0942% | +1.0049% | 24.3133% | +3.3622% | [-0.0095, 0.0277] | 2/4 | 41.0700% | 4.00 |
| `GBDT_S1_G1` | S1 | `round1_inconclusive` | 25.0663% | +0.9770% | 24.6042% | +3.6531% | [-0.0098, 0.0275] | 2/4 | 40.2900% | 4.07 |
| `GBDT_S2_G2` | S2 | `round1_inconclusive` | 25.0663% | +0.9770% | 24.5483% | +3.5972% | [-0.0105, 0.0282] | 2/4 | 41.5800% | 3.98 |
| `GBDT_S2_G3` | S2 | `round1_inconclusive` | 25.0384% | +0.9491% | 24.6769% | +3.7259% | [-0.0109, 0.0277] | 2/4 | 41.8400% | 3.92 |
| `GBDT_S4_G3` | S4 | `round1_inconclusive` | 25.0384% | +0.9491% | 24.0503% | +3.0993% | [-0.0109, 0.0275] | 2/4 | 41.0200% | 4.01 |
| `GBDT_S2_G1` | S2 | `round1_inconclusive` | 24.7592% | +0.6699% | 24.6713% | +3.7203% | [-0.0128, 0.0250] | 2/4 | 40.1400% | 4.03 |
| `GBDT_S4_G1` | S4 | `round1_inconclusive` | 24.7034% | +0.6141% | 24.5594% | +3.6084% | [-0.0138, 0.0249] | 2/4 | 40.4300% | 3.88 |
| `GBDT_S3_G1` | S3 | `round1_inconclusive` | 24.2987% | +0.2094% | 24.4923% | +3.5413% | [-0.0175, 0.0218] | 2/4 | 40.6400% | 3.83 |


---

## 4. Search Budget Accounting & Round-2 Readiness

- **Round-1 Configurations Budgeted:** 36
- **Round-1 Configurations Attempted:** 36
- **Round-1 Configurations Completed:** 36
- **Round-1 Budget Remaining:** 0
- **Total E Budget:** 48
- **Remaining E Budget for Round 2:** 12
- **Overall Readiness Disposition:** `no_round2_candidate_supported`
- **Round 2 Authorized:** `false`
- **Requires Separate Assignment:** `true`

### Eligible Configuration IDs for Potential Round 2:

- *None*

---

## 5. Artifact Inventory & Cryptographic Checksums

| Artifact File | SHA-256 Digest |
|:---|:---|
| [`annual_stability.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/annual_stability.json) | `0f03430591977623ffcfc1f42f2e3fdb90abd2132258ee9a165223422719169d` |
| [`baseline_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/baseline_summary.json) | `ddec0f4edca260cac71cfc9d604608ee69a33a9df9d7b338458cab18600fb80b` |
| [`bootstrap_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/bootstrap_summary.json) | `030be403dafb332e9af15da5d01074a65461d90af6c5e13408bb1610afad403b` |
| [`configuration_registry.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/configuration_registry.json) | `170c06d87f898b6697066714df4a83807658ad007edcea57086a9f798813b86a` |
| [`execution_metadata.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/execution_metadata.json) | `4dc1d428d3340f17316e13de3e274ce4a50a8cc73bdfb60fb7b20915cdd7e0e9` |
| [`experiment_ledger.jsonl`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/experiment_ledger.jsonl) | `d94c418498c19d8d2300b67c02598ce15c875df02597768e619a827ed5d919fa` |
| [`external_files_manifest.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/external_files_manifest.json) | `c90e4bc66ec5e2f8ce38d1ac03e9dbfc6b040c5a1f33983cd5140507a7c7c1d8` |
| [`family_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/family_summary.json) | `41143fc4aee40fecf937511316730d674f04b50253b6e11356bcd455ba45da12` |
| [`input_integrity.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/input_integrity.json) | `36f0aa8e4cb2e439cd11a8291c37d7fdb1644cd1f7aa5d2514f409721b174141` |
| [`model_diagnostics.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/model_diagnostics.json) | `ef7a98cbf32eeaab2453d942152cbd6cc48d74c06251e72eaae0f267931d6372` |
| [`round1_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/round1_summary.json) | `9d9fb8900d165d7aee28e04794ae91152dd6e4f0d529bdb12594f6dbf02802d9` |
| [`round2_readiness.json`](artifacts/LONG-002E1/LONG-002E1-20261006_133722/round2_readiness.json) | `2bdce9b4c0ad37eb0ffb33b437c97404e5d6eab734ee4c7d85788a51322767a6` |

---

## 6. Stop Condition & Governance Invariants

- Execution is complete and verified.
- Round 2 is NOT executed and remains strictly unauthorized.
- Validation (2021–2022), Holdout (2023–2025), and Shadow (2026+) remain strictly quarantined.
- `APPROVED_PRODUCTION_STRATEGIES == ()` is preserved. Zero production trading logic changes.
- Zero market data provider calls were made.