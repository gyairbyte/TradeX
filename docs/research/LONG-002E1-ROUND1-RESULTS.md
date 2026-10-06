# LONG-002E1: Preregistered Development-Only Round-1 Candidate-System Search Results

- **Task ID:** `LONG-002E1-ROUND1-CANDIDATE-SEARCH-001`
- **Correction Contract:** `LONG-002E1-CORR-001`
- **Correction Spec SHA-256:** `6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96`
- **Attempt Number:** 2 (Consumes New Material Budget Slot: `false`)
- **Superseded Run ID:** `LONG-002E1-20261006_133722` *(preserved as audit evidence; invalid for decision use)*
- **Program:** `LONG-002` (Rapid-Upside Long Opportunity Program)
- **Phase:** `LONG-002E1` (Round-1 Candidate Search)
- **Authorization:** Gary Yang (authorized 2026-10-05)
- **Classification:** Research-Only (Development Split Only)
- **Base Git SHA:** `8058c5d858b70090335338176f11a20ddfd04502`
- **Preregistration Commit SHA:** `49103f84ffbf7cd7b60216c2866ad103282bae58`
- **Preregistration Spec SHA-256:** `d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0`
- **Execution Code SHA:** `b0727cbd39958c37eca10c286603b8126028672e`
- **Official Run ID:** `LONG-002E1-20261006_152832`
- **Round-1 Search Budget Accounting:** 36 / 36 material configurations attempted and accounted
- **Remaining LONG-002E Search Budget:** 12 configurations
- **Round 2 Authorized:** `false` (`requires_separate_assignment = true`)
- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)

---

> [!WARNING]
> **Audit Notice — Superseded Run:** This execution supersedes run `LONG-002E1-20261006_133722`. The original run suffered from Fold-1 design asymmetry (post-purge 2016 training set had 0 rows leaving fitted models unpredicted for 2017), non-common evaluation periods (2017–2020 vs 2018–2020), positional outcome join, and unverified execution provenance. Per `LONG-002E1-CORR-001`, all 36 configurations are re-executed across the common 2018–2020 evaluation period (730 sessions) under a 3-of-3 annual positive stability requirement.

## 1. Executive Summary & Purpose

LONG-002E1 is the first controlled empirical candidate-system search for the LONG-002 program. Among the 8 frozen features established in LONG-002D3B, exactly 36 material configurations across 3 approved model families were evaluated strictly on the DEVELOPMENT split (2016–2020 at 20:30 ET) using chronological expanding-window out-of-fold evaluation (2018–2020 common evaluation period across 730 sessions).

> [!IMPORTANT]
> This report presents DEVELOPMENT-ONLY evidence. It does NOT constitute validation, holdout, or shadow support, and does NOT authorize production changes, trading triggers, or Round 2 execution.

## 2. Matched Baseline Comparator Performance (VAM5)

All candidate configurations are evaluated on the exact same common population and dates as the frozen baseline comparator `volatility_aware_momentum_5` (50% return_5 percentile + 50% atr_pct_14 percentile).

- **Evaluation Period:** 2018-01-01 to 2020-12-31 (730 dates)
- **OOF Base Rate:** 10.0498%
- **Matched VAM5 Precision@10:** 24.0893% (2.3970x lift)
- **Matched VAM5 Precision@25:** 20.9510% (2.0847x lift)
- **Matched VAM5 Clean Move Value @10:** 4.0084
- **Matched VAM5 Adverse Rate @10:** 44.7500%

### Annual Matched VAM5 Precision@10:

| Year | Matched VAM5 Precision@10 |
|:---:|:---:|
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
| `RANK_S2_T2` | S2 | `round1_not_supported` | 20.8932% | -3.1961% | 18.3329% | -2.6182% | [-0.0506, -0.0140] | 0/3 | 44.9800% | 3.44 |
| `RANK_S4_T2` | S4 | `round1_not_supported` | 20.3908% | -3.6985% | 18.5846% | -2.3664% | [-0.0544, -0.0201] | 0/3 | 44.6100% | 3.34 |
| `RANK_S1_T2` | S1 | `round1_not_supported` | 20.3070% | -3.7823% | 18.0140% | -2.9371% | [-0.0593, -0.0181] | 0/3 | 45.2600% | 3.31 |
| `RANK_S3_T2` | S3 | `round1_not_supported` | 20.1396% | -3.9498% | 18.3944% | -2.5566% | [-0.0573, -0.0232] | 0/3 | 44.4800% | 3.29 |
| `RANK_S2_T3` | S2 | `round1_not_supported` | 20.0558% | -4.0335% | 17.3930% | -3.5580% | [-0.0579, -0.0227] | 0/3 | 44.5400% | 3.24 |
| `RANK_S1_T3` | S1 | `round1_not_supported` | 19.4976% | -4.5918% | 16.9399% | -4.0112% | [-0.0646, -0.0275] | 0/3 | 44.9500% | 3.15 |
| `RANK_S4_T3` | S4 | `round1_not_supported` | 19.3580% | -4.7313% | 17.2587% | -3.6923% | [-0.0628, -0.0305] | 0/3 | 44.6100% | 3.10 |
| `RANK_S3_T3` | S3 | `round1_not_supported` | 19.3022% | -4.7872% | 17.1636% | -3.7874% | [-0.0636, -0.0320] | 0/3 | 44.5100% | 3.06 |
| `RANK_S1_T1` | S1 | `round1_not_supported` | 18.8416% | -5.2477% | 16.3524% | -4.5986% | [-0.0727, -0.0325] | 0/3 | 44.8800% | 3.04 |
| `RANK_S2_T1` | S2 | `round1_not_supported` | 18.3810% | -5.7083% | 15.8098% | -5.1413% | [-0.0772, -0.0367] | 0/3 | 44.1200% | 2.96 |
| `RANK_S4_T1` | S4 | `round1_not_supported` | 16.7900% | -7.2994% | 14.6126% | -6.3385% | [-0.0933, -0.0519] | 0/3 | 42.5700% | 2.56 |
| `RANK_S3_T1` | S3 | `round1_not_supported` | 16.4550% | -7.6343% | 14.5790% | -6.3720% | [-0.0956, -0.0567] | 0/3 | 42.9700% | 2.52 |


### Family: `regularized_probabilistic`
- Total Configs: 12 | Eligible: 0 | Inconclusive: 12 | Not Supported: 0 | Invalid: 0
- Best Configuration (by locked ordering): `LOGIT_S4_C300`

| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `LOGIT_S4_C300` | S4 | `round1_inconclusive` | 26.8109% | +2.7216% | 25.2420% | +4.2909% | [0.0054, 0.0489] | 2/3 | 39.2500% | 5.11 |
| `LOGIT_S4_C030` | S4 | `round1_inconclusive` | 26.7969% | +2.7076% | 25.2476% | +4.2965% | [0.0052, 0.0488] | 2/3 | 39.2000% | 5.11 |
| `LOGIT_S4_C003` | S4 | `round1_inconclusive` | 26.7132% | +2.6239% | 25.2643% | +4.3133% | [0.0046, 0.0489] | 2/3 | 39.3000% | 5.10 |
| `LOGIT_S3_C300` | S3 | `round1_inconclusive` | 26.6294% | +2.5401% | 25.1860% | +4.2350% | [0.0033, 0.0461] | 2/3 | 39.0800% | 5.09 |
| `LOGIT_S2_C300` | S2 | `round1_inconclusive` | 26.6155% | +2.5262% | 25.1916% | +4.2406% | [0.0031, 0.0464] | 2/3 | 39.0900% | 5.09 |
| `LOGIT_S3_C030` | S3 | `round1_inconclusive` | 26.6015% | +2.5122% | 25.1916% | +4.2406% | [0.0031, 0.0464] | 2/3 | 39.1100% | 5.08 |
| `LOGIT_S2_C030` | S2 | `round1_inconclusive` | 26.6015% | +2.5122% | 25.1916% | +4.2406% | [0.0028, 0.0464] | 2/3 | 39.0600% | 5.09 |
| `LOGIT_S2_C003` | S2 | `round1_inconclusive` | 26.5457% | +2.4564% | 25.1972% | +4.2462% | [0.0024, 0.0461] | 2/3 | 39.0800% | 5.07 |
| `LOGIT_S3_C003` | S3 | `round1_inconclusive` | 26.5178% | +2.4285% | 25.2364% | +4.2853% | [0.0021, 0.0458] | 2/3 | 39.0600% | 5.07 |
| `LOGIT_S1_C003` | S1 | `round1_inconclusive` | 26.1828% | +2.0935% | 25.2979% | +4.3469% | [-0.0020, 0.0422] | 2/3 | 38.7400% | 5.00 |
| `LOGIT_S1_C030` | S1 | `round1_inconclusive` | 26.1689% | +2.0796% | 25.2979% | +4.3469% | [-0.0021, 0.0419] | 2/3 | 38.7600% | 5.00 |
| `LOGIT_S1_C300` | S1 | `round1_inconclusive` | 26.1689% | +2.0796% | 25.2979% | +4.3469% | [-0.0021, 0.0419] | 2/3 | 38.7600% | 5.00 |


### Family: `shallow_strongly_regularized_gbdt`
- Total Configs: 12 | Eligible: 0 | Inconclusive: 12 | Not Supported: 0 | Invalid: 0
- Best Configuration (by locked ordering): `GBDT_S1_G2`

| Config ID | Subset | Status | P@10 | Delta vs VAM5 | P@25 | P@25 Delta | 21d BS 95% CI | Pos Yrs | Adverse @10 | ECMV @10 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `GBDT_S1_G2` | S1 | `round1_inconclusive` | 25.4431% | +1.3538% | 24.6210% | +3.6699% | [-0.0062, 0.0322] | 2/3 | 40.9200% | 4.07 |
| `GBDT_S1_G3` | S1 | `round1_inconclusive` | 25.3454% | +1.2561% | 24.7273% | +3.7762% | [-0.0052, 0.0290] | 2/3 | 41.3500% | 4.06 |
| `GBDT_S3_G3` | S3 | `round1_inconclusive` | 25.2756% | +1.1863% | 24.4643% | +3.5133% | [-0.0088, 0.0303] | 2/3 | 41.4000% | 3.96 |
| `GBDT_S3_G2` | S3 | `round1_inconclusive` | 25.1919% | +1.1026% | 24.4699% | +3.5189% | [-0.0087, 0.0291] | 2/3 | 41.1400% | 3.99 |
| `GBDT_S4_G2` | S4 | `round1_inconclusive` | 25.0942% | +1.0049% | 24.3133% | +3.3622% | [-0.0095, 0.0277] | 2/3 | 41.0700% | 4.00 |
| `GBDT_S1_G1` | S1 | `round1_inconclusive` | 25.0663% | +0.9770% | 24.6042% | +3.6531% | [-0.0098, 0.0275] | 2/3 | 40.2900% | 4.07 |
| `GBDT_S2_G2` | S2 | `round1_inconclusive` | 25.0663% | +0.9770% | 24.5483% | +3.5972% | [-0.0105, 0.0282] | 2/3 | 41.5800% | 3.98 |
| `GBDT_S2_G3` | S2 | `round1_inconclusive` | 25.0384% | +0.9491% | 24.6769% | +3.7259% | [-0.0109, 0.0277] | 2/3 | 41.8400% | 3.92 |
| `GBDT_S4_G3` | S4 | `round1_inconclusive` | 25.0384% | +0.9491% | 24.0503% | +3.0993% | [-0.0109, 0.0275] | 2/3 | 41.0200% | 4.01 |
| `GBDT_S2_G1` | S2 | `round1_inconclusive` | 24.7592% | +0.6699% | 24.6713% | +3.7203% | [-0.0128, 0.0250] | 2/3 | 40.1400% | 4.03 |
| `GBDT_S4_G1` | S4 | `round1_inconclusive` | 24.7034% | +0.6141% | 24.5594% | +3.6084% | [-0.0138, 0.0249] | 2/3 | 40.4300% | 3.88 |
| `GBDT_S3_G1` | S3 | `round1_inconclusive` | 24.2987% | +0.2094% | 24.4923% | +3.5413% | [-0.0175, 0.0218] | 2/3 | 40.6400% | 3.83 |


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
| [`annual_stability.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/annual_stability.json) | `5a9d15232fc09a76a70422a57c8c137d86df25f2214037a449ba4ee9a3c8f5cf` |
| [`baseline_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/baseline_summary.json) | `3838600a636a9539337201d551933115211f89476bbaee9d0baa2a8391fa126d` |
| [`bootstrap_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/bootstrap_summary.json) | `0360f0575643eea40ac8ce11f0223096d728a50a469c2acd84670ebfefb1b6de` |
| [`configuration_registry.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/configuration_registry.json) | `170c06d87f898b6697066714df4a83807658ad007edcea57086a9f798813b86a` |
| [`execution_metadata.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/execution_metadata.json) | `3f09446337027f0f25ed27442d88387fa6d29ba9ad86163d525dca827e27106a` |
| [`experiment_ledger.jsonl`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/experiment_ledger.jsonl) | `743e59af93b9e8e48f6f2e641eec2ddc61eeb12656b2a895f55ddb0dc95bcb06` |
| [`external_files_manifest.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/external_files_manifest.json) | `8f48165db2e3e4a2e0c6591b75d1939c7b7ec18b6bbe7b76c2d53bddf4b7e9f8` |
| [`family_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/family_summary.json) | `d0ff2ae974eda304907469165fbf899ffec99fdea981bb4d2d60e0dbf67b6788` |
| [`input_integrity.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/input_integrity.json) | `36f0aa8e4cb2e439cd11a8291c37d7fdb1644cd1f7aa5d2514f409721b174141` |
| [`model_diagnostics.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/model_diagnostics.json) | `84bcb2c55934f24206f4a1003f3a8896deb127b1de0c9980f5238fe337873f71` |
| [`round1_summary.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/round1_summary.json) | `dfde6712084a7ac1d9c58f8c5babb22cf24aba146e2762bc5368cb7d90201708` |
| [`round2_readiness.json`](artifacts/LONG-002E1/LONG-002E1-20261006_152832/round2_readiness.json) | `3cefece3c3222813a7b5fa30daf494ccd30073e25d0e56f43c2c07eded7f927d` |

---

## 6. Stop Condition & Governance Invariants

- Execution is complete and verified.
- Round 2 is NOT executed and remains strictly unauthorized.
- Validation (2021–2022), Holdout (2023–2025), and Shadow (2026+) remain strictly quarantined.
- `APPROVED_PRODUCTION_STRATEGIES == ()` is preserved. Zero production trading logic changes.
- Zero market data provider calls were made.