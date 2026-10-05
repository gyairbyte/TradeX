# LONG-002D3B: Quantitative-Only Research Amendment, Final Feature Registry Freeze, and Recommendation-Episode Evaluation Contract

- **Task ID:** `LONG-002D3B-QUANTITATIVE-FREEZE-001`
- **Program:** `LONG-002` (Rapid-Upside Opportunity Research)
- **Phase:** `LONG-002D3B`
- **Title:** Quantitative-Only Research Amendment, Final Feature Registry Freeze, and Recommendation-Episode Evaluation Contract
- **Classification:** Research-Only (Specification / Decision / Readiness)
- **Authorizer:** Gary Yang
- **Authorization Date:** 2026-10-05
- **Bounded by:** ChatGPT
- **Status:** Complete, Verified, and Frozen
- **Readiness Disposition:** `ready_for_long_002e_authorization` (`long_002e_authorized: false`)
- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)

---

## 1. Executive Summary & Authorization Context

The original `LONG-002` program specification ([`docs/research/specs/LONG-002-v1.json`](specs/LONG-002-v1.json)) stated that the final model feature set would be decided in `LONG-002D` after:
1. Core technical and market-context KPI discovery; and
2. Discretionary human blinded chart review.

Gary Yang has explicitly elected **NOT** to perform discretionary human blinded chart review. In accordance with the repository research protocol ([`docs/RESEARCH-PROTOCOL.md`](../RESEARCH-PROTOCOL.md)), this prerequisite is not silently bypassed. Instead, formal amendment [`LONG-002D-AMEND-001`](LONG-002D-AMEND-001.md) waives the human review requirement and transitions the program to a **quantitative-only feature registry freeze** based strictly on completed development evidence from:
- `LONG-002C` (Outcome census, master episodes, frozen baseline comparator `volatility_aware_momentum_5`);
- `LONG-002D1` (Core technical and market-context univariate KPI census); and
- `LONG-002D2` (Incremental reranking study on `relative_volume_20` and `sma20_slope_5`).

### Primary Scope & Boundaries
- **Research-Only Decision & Specification:** No new empirical model fitting, no outcome-matrix mining, and no new data studies were performed.
- **Zero Raw Row Data Access:** No row-level Parquet datasets (`outcome_matrix.parquet`, `feature_table.parquet`), validation data, holdout data, shadow data, pilot answer keys, or new chart outcomes were loaded or inspected.
- **Strict Quarantines:** Validation (2021–2022), holdout (2023–2025), and prospective shadow (2026+) remain completely unopened and quarantined.
- **Production Status:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved. Zero changes to trading logic or live systems.
- **LONG-002E Remains Unauthorized:** This milestone establishes readiness for Gary Yang and ChatGPT to consider authorizing `LONG-002E`. It does **not** itself authorize `LONG-002E`.

---

## 2. Disposition of LONG-002D3A Tooling & Waiver Terms

Gary Yang explicitly authorized continuation after waiving the discretionary human chart-review study:
- **D3A Tooling:** Completed, audited, and verified (`tests/research/long_002d3a/` 79 passing tests).
- **24-Case Human Pilot:** Waived by Gary Yang before execution; not executed.
- **240-Case Main Human Study:** Waived by Gary Yang; sample was not generated.
- **Human Labels Collected:** Exactly 0.
- **Human Predictive Evidence:** None. No human-label performance claims are made.
- **Answer Key Quarantine:** The 24-case pilot answer key remains strictly external, gitignored, unrevealed, and cryptographically committed in `answer_key_commitment.json` (`3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103`).

All `LONG-002D3A` artifacts and code are preserved intact. D3A provides verified tooling that could be separately reactivated in the future under explicit Gary Yang authorization, strict blinding preservation, and a formal development amendment.

---

## 3. Final Frozen Quantitative Feature Registry

The final frozen quantitative feature registry is formally committed in [`docs/research/artifacts/LONG-002D3B/feature_registry.json`](artifacts/LONG-002D3B/feature_registry.json).

Every candidate, reference, and diagnostic feature from the `LONG-002D1` core census (15 features total) is explicitly classified using the controlled disposition vocabulary:
- `baseline_component`
- `carry_core`
- `carry_bounded_challenger`
- `context_only`
- `reference_only`
- `excluded`
- `separate_preregistration_required`

### Comprehensive Feature Disposition Catalog

| Feature ID | Family | D1 Role | D1 Univariate Evidence Summary | D2 Reranking Evidence Summary | Final Disposition | Allowed in LONG-002E? | Allowed as Standalone Ranker? | Permitted Direction | Limitations & Governance Bounds |
|---|---|:---:|---|---|:---:|:---:|:---:|:---:|---|
| `return_5` | short_horizon_momentum | reference | 1.2446x favorable decile lift (clean rate 11.03% vs base 8.86%), 21-session CI [1.13, 1.38], 5/5 yrs positive | N/A | `baseline_component` | **True** | **True** | HIGHER | Core momentum reference component of frozen VAM5. Horizon fixed at 5 sessions; no lookback tuning. |
| `atr_pct_14` | volatility_movement_capacity | reference | Strongest D1 univariate feature: 2.2816x favorable decile lift (clean rate 20.22%), 21-session CI [1.94, 2.70], strictly monotonic deciles, 5/5 yrs positive | N/A | `carry_core` | **True** | **True** | HIGHER | Core volatility/capacity input and component of frozen VAM5. No alternate ATR periods authorized. |
| `return_20` | medium_horizon_momentum | reference | 1.2122x favorable decile lift (clean rate 10.75%), 21-session CI [1.11, 1.33], 5/5 yrs positive | N/A | `carry_bounded_challenger` | **True** | **True** | HIGHER | Medium-horizon momentum input. No alternate lookback search authorized. |
| `return_60` | longer_horizon_momentum | reference | 1.2536x favorable decile lift (clean rate 11.11%), 21-session CI [1.08, 1.44], 5/5 yrs positive | N/A | `carry_bounded_challenger` | **True** | **True** | HIGHER | Longer-horizon momentum input. No alternate lookback search authorized. |
| `close_vs_sma20` | trend_location | candidate | 1.2083x favorable decile lift (clean rate 10.71%), 21-session CI [1.10, 1.34], 4/5 yrs positive | N/A | `carry_bounded_challenger` | **True** | **True** | HIGHER | Trend/location input. No alternate moving-average period search authorized. |
| `close_vs_sma60` | trend_location | candidate | 1.1967x favorable decile lift (clean rate 10.61%), 21-session CI [1.07, 1.33], 4/5 yrs positive | N/A | `carry_bounded_challenger` | **True** | **True** | HIGHER | Trend/location input. No alternate moving-average period search authorized. |
| `sma20_slope_5` | moving_average_slope | candidate | 1.2238x favorable decile lift (clean rate 10.85%), 21-session CI [1.11, 1.34], 5/5 yrs positive; strong overlap with `return_20` ($\rho \approx +0.919$) | Standalone rerank underperformed matched VAM5: -3.3583 pp delta (11.9950% vs 15.3533%), 21-session CI [-0.0415, -0.0258], 0/5 yrs positive | `carry_bounded_challenger` | **True** | **False** | HIGHER | Strong collinearity with `return_20` ($\rho \approx +0.919$); underperformed matched VAM5; may only appear in registered multivariate E configurations; NOT an independently supported ranker. |
| `relative_volume_20` | volume | candidate | 1.1307x favorable decile lift (clean rate 10.02%), 21-session CI [1.07, 1.20], 4/5 yrs positive | Standalone rerank decisively `NOT_SUPPORTED`: -2.9212 pp delta (12.4321% vs 15.3533%), -2,232 clean events, 21-session CI [-0.0352, -0.0235] entirely below zero, 0/5 yrs positive | `carry_bounded_challenger` | **True** | **False** | HIGHER | D1 univariate association modest; D2 standalone reranking was decisively `NOT_SUPPORTED`; permitted only as bounded multivariate/contextual input in E; no standalone ranker; no threshold tuning. |
| `proximity_high20` | breakout_proximity | candidate | Preregistered HIGHER hypothesis contradicted: Decile 10 clean rate 6.48% (0.7307x lift), 21-session CI [0.65, 0.80], 0/5 yrs favorable | N/A | `excluded` | **False** | **False** | None | Preregistered HIGHER hypothesis contradicted. Direction inversion prohibited inside E. |
| `proximity_high60` | breakout_proximity | candidate | Preregistered HIGHER hypothesis contradicted: Decile 10 clean rate 6.10% (0.6886x lift), 21-session CI [0.59, 0.78], 0/5 yrs favorable | N/A | `excluded` | **False** | **False** | None | Preregistered HIGHER hypothesis contradicted. Direction inversion prohibited inside E. |
| `true_range_compression_5_20` | compression | candidate | 1.0087x favorable decile lift (clean rate 8.94%), 21-session CI [0.96, 1.06], 2/5 yrs favorable | N/A | `excluded` | **False** | **False** | None | Insufficient/neutral D1 evidence for current bounded registry; 95% CI spans 1.00. |
| `dollar_volume_trend_20_60` | dollar_volume_trend | candidate | 1.0022x favorable decile lift (clean rate 8.88%), 21-session CI [0.91, 1.10], 3/5 yrs favorable | N/A | `excluded` | **False** | **False** | None | Insufficient/neutral D1 evidence for current bounded registry; essentially zero edge over base rate. |
| `up_volume_share_20` | volume_structure | candidate | Preregistered HIGHER hypothesis contradicted: Decile 10 clean rate 7.84% (0.8842x lift), 21-session CI [0.81, 0.96], 0/5 yrs favorable | N/A | `excluded` | **False** | **False** | None | Preregistered HIGHER hypothesis contradicted. Inverse univariate association. |
| `spy_return_20` | market_regime_context | candidate_diagnostic | Date-level diagnostic: 1.5473x lift on favorable dates, but 21-session CI spans [0.90, 2.18], 1/5 yrs favorable due to macro date clustering (2020 bounce) | Confirmed candidate delta degradation was uniform across Lower, Middle, and Upper market regimes | `context_only` | **False (as ranking feature)** | **False** | None | Permitted strictly as descriptive market context, regime diagnostics, and robustness reporting. Must NOT become an outcome-tuned ranking feature in initial E. |
| `stock_minus_spy_20` | benchmark_relative | reference | Produces identical same-date cross-sectional ranks and 1.2122x lift as `return_20` on identical non-null sets ($\text{rank}_i(r_i - r_{\text{SPY}}) \equiv \text{rank}_i(r_i)$) | N/A | `reference_only` | **False** | **False** | None | Reference and redundancy diagnostic rather than distinct independent ranking feature. |

---

## 4. Frozen Baseline System Comparator

- **System Identifier:** `volatility_aware_momentum_5` (VAM5)
- **Final Disposition:** `FROZEN BASELINE COMPARATOR`
- **Formula:** `0.5 * cross_sectional_momentum_5_pct + 0.5 * cross_sectional_atr_pct_14_pct`
- **Locked Development Reference Performance (2016–2020 at 20:30 ET):**
  - Top-10% Clean Rate: **15.3533%** (**1.7320x lift**, 11,731 clean events / 76,407 observations)
  - Top-25% Clean Rate: **12.6881%** (**1.4314x lift**, 24,144 clean events / 190,288 observations)
  - Base Rate: **8.8644%** (67,257 clean events / 758,731 observations)
- **Governance Requirements:**
  - Preserves exact Stage C definition without modification.
  - Zero retuning of weights (retains fixed 50/50 percentile combination).
  - Zero threshold changes.
  - Zero lookback changes.
  - VAM5 is a frozen SYSTEM comparator, not a newly optimized `LONG-002E` candidate.

---

## 5. Exclusions & Discipline Safeguards

### A. Post-Hoc Pullback Finding Excluded from LONG-002E
In `LONG-002D1`, Decile 1 of `proximity_high20` (stocks trading furthest below rolling 20-session highs, average $-14.26\%$) exhibited an empirical clean-event rate of 14.58% (1.6448x lift). Because this inverse relationship contradicted the preregistered HIGHER breakout hypothesis, it represents post-hoc exploratory dip-buying evidence.
- **Disposition:** `separate_preregistration_required`.
- **Policy:** Strictly excluded from the frozen `LONG-002E` feature registry.
- **Prohibitions:** Do **NOT** create a reverse proximity feature, pullback threshold, dip score, or inverted proximity rank inside `LONG-002E`. Any dip-buying formulation requires a separate, preregistered research program approved by Gary Yang.

### B. Optional Data Families Excluded
The initial `LONG-002E` registry excludes predictive features from:
- Fundamentals (financial statement ratios, growth, margins);
- Analyst revisions and consensus estimates;
- News and sentiment catalysts;
- Options flow, chain snapshots, or volume/OI ratios;
- Short interest;
- Insider transactions;
- Institutional ownership/positioning.

**Reason:** No completed quantitative D-stage evidence currently qualifies these data sources for the frozen initial E registry. They may be reconsidered only through a separate, preregistered, Gary-approved development amendment.

### C. Prohibition on Silent Feature Engineering
`LONG-002E` must **NOT** create new outcome-informed transforms from the frozen registry without amendment. Specifically prohibited:
- Custom composite ratios (e.g. `return_20 / ATR`);
- Custom momentum composites;
- New volume ratios or hand-tuned volume thresholds;
- Arbitrary unpreregistered feature interactions;
- Custom nonlinear transforms;
- Indicator-period searches outside frozen registry lookbacks.

Regularized model families may mathematically combine frozen features as part of their formal model structure. Any explicit feature interactions must be registered as material configurations counting against the 48-configuration search budget.

---

## 6. Recommendation-Episode Evaluation Contract

The original `LONG-002` contract mandates a unique recommendation-episode lifecycle/grouping rule before model evaluation sample gates are applied. This contract is formally frozen in [`docs/research/artifacts/LONG-002D3B/recommendation_episode_contract.json`](artifacts/LONG-002D3B/recommendation_episode_contract.json).

### Core Construct: `evaluation_recommendation_episode`
An evaluation recommendation episode is a deterministic grouping construct designed to evaluate candidate system recommendations without treating contiguous daily surfaced rows as independent events.

### Primary Decision Snapshot
- **Cutoff Time:** `20:30 America/New_York` (evening decision snapshot) on the `XNYS` exchange calendar.

### Lifecycle Grouping Rules
1. **Episode Start:**
   An episode opens on the first official 20:30 snapshot where an immutable security is surfaced by a candidate system (assigned to `Enter Now`, `Armed`, or `Qualified Waitlist`) after not currently being part of an active evaluation episode for that system. Exactly **one active evaluation episode per immutable security per candidate system** is permitted.
2. **Episode Continuation:**
   An active episode continues across consecutive official 20:30 snapshots while the security remains surfaced. State transitions among visible surfaced states (`Enter Now` $\leftrightarrow$ `Armed` $\leftrightarrow$ `Qualified Waitlist`) do **NOT** create a new evaluation episode. Contiguous surfaced observations remain grouped within the same single active episode.
3. **Episode Close:**
   An episode terminates on the earliest occurrence of:
   - First official 20:30 snapshot where the security is no longer surfaced (downgraded to `Hidden` / disqualified);
   - Exactly **21 trading sessions** after episode start date; or
   - Explicit recommendation invalidation under a later frozen state/entry contract.
4. **Anti-Double-Count Rule (Persistent Signal Safeguard):**
   If the 21-session maximum cap is reached while the security remains continuously surfaced, the episode closes and a new episode is **NOT** automatically opened on the next trading session. The security becomes eligible to start a new evaluation recommendation episode only after at least **one official 20:30 snapshot in which it is NOT surfaced** (hidden / unsurfaced reset required). This prevents a persistent, permanently qualifying signal from inflating independent sample counts.
5. **Future Entry-Plan Rule:**
   Once `LONG-002F` introduces frozen entry-plan IDs, a material change to a frozen entry plan, trigger, or invalidation closes the prior recommendation ID and creates a new operational recommendation ID. However, this later operational rule must not retroactively alter the `LONG-002E` evaluation grouping without an explicit amendment.
6. **Deterministic Collision-Resistant Identity:**
   Every episode ID is deterministically computed from:
   $$\text{ID} = \text{REC\_}\{\text{system\_id}\}\_\{\text{immutable\_security\_id}\}\_\{\text{start\_date}\}\_\{\text{cutoff}\}$$

### Conceptual Distinctions
- **Stage C Master Opportunity Episodes:** Ex-post ground-truth outcome labeling windows (spanning up to 21 sessions following the earliest anchor entry that achieves clean +10%) that group natural market outcome phenomena.
- **Evaluation Recommendation Episodes:** Candidate-system-generated evaluation grouping units reflecting when a specific model surfaces a security.
- **Live Orders / Brokerage Positions:** Neither construct represents live brokerage orders, broker-fill executions, or portfolio positions.

### Model-Evaluation Denominator Rules
`LONG-002E` must report **BOTH**:
1. Observation-level diagnostics (raw daily observation metrics); and
2. Unique evaluation recommendation-episode metrics.

Raw daily rows must **NOT** be treated as independent recommendations or used as the denominator for product-usefulness claims. Primary sample counts and product-usefulness metrics must evaluate unique evaluation recommendation episodes alongside independent master opportunity episodes, distinct tickers, calendar coverage, and year/sector concentration.

---

## 7. Preserved LONG-002E Search Budget & Boundaries

This document does **not** authorize `LONG-002E`. However, readiness requirements preserve the existing contract bounds:

### Allowed Model Families
1. **Transparent cross-sectional rank/score system:** Retains equal-weight reference form; alternative weighting from small registered set, not continuous unconstrained optimization.
2. **Regularized probabilistic/time-to-event system:** Regularized logistic or discrete-time logistic hazard-style models.
3. **Shallow strongly regularized gradient-boosted trees:** The only permitted nonlinear challenger.

### Strict Model Search Budget
- **Round 1:** Maximum 12 material configurations per family, 36 total across 3 families.
- **Round 2:** Maximum 12 additional material configurations across all families.
- **Absolute Maximum:** **48 materially distinct configurations.**
- **Experiment Ledger:** Every attempted configuration, including failures, must be recorded in the committed experiment ledger.

### Explicitly Prohibited Techniques
AutoML, deep neural networks, transformers for prediction, reinforcement learning, genetic/evolutionary search, unrestricted stacking/ensembles, unrestricted hyperparameter searches, and LLM-generated trading probabilities remain strictly prohibited.

---

## 8. Quantitative Readiness Decision

The readiness decision is formally committed in [`docs/research/artifacts/LONG-002D3B/readiness_decision.json`](artifacts/LONG-002D3B/readiness_decision.json).

- **Disposition:** `ready_for_long_002e_authorization`
- `long_002e_authorized`: `false`
- `requires_separate_gary_authorization`: `true`

### Meaning of Disposition
This disposition certifies that all quantitative D-stage prerequisites are complete, verified, and sufficiently locked for Gary Yang and ChatGPT to evaluate whether to authorize `LONG-002E`. It does **NOT** authorize `LONG-002E` execution, model fitting, validation access, holdout access, shadow access, or production changes.

---

## 9. Committed Artifact Inventory & Cryptographic Checksums

All committed artifacts for `LONG-002D3B` are located in `docs/research/artifacts/LONG-002D3B/`:

| Artifact File | Description | SHA-256 Digest |
|---|---|---|
| [`feature_registry.json`](artifacts/LONG-002D3B/feature_registry.json) | Final frozen quantitative feature registry (15 D1 features classified + VAM5 baseline comparator) | `f49f2d9ab1032b7cb15ff6275d2ee790864bab00b6dfaf4ffa760bdb82c3922b` |
| [`recommendation_episode_contract.json`](artifacts/LONG-002D3B/recommendation_episode_contract.json) | Frozen evaluation recommendation-episode grouping rules and anti-double-count contract | `6ccfd778ce971fa42cc37ee3b822585b02cdca520e56b729218b78b60b52ad04` |
| [`readiness_decision.json`](artifacts/LONG-002D3B/readiness_decision.json) | Quantitative D-stage readiness decision (`ready_for_long_002e_authorization`) | `f47ba4630594d05343a061b6c53540cc0e5401d56ed5a86a66e1e0a8a0b859fa` |
| [`checksums.sha256`](artifacts/LONG-002D3B/checksums.sha256) | Cryptographic checksums of committed summary JSON artifacts | — |

---

## 10. Stop Condition & Governance Verification

- **Task Status:** Complete and verified.
- **Draft PR:** Open one focused draft PR against `main` on branch `antigravity/long-002d3b-quantitative-freeze`.
- **Merge Status:** Do **NOT** merge. Return PR to ChatGPT and Gary Yang for independent review.
- **Stop Condition:** Stop after the draft PR and completion report. Do **NOT** begin `LONG-002E`.
