# LONG-002D-AMEND-001: Quantitative-Only Research Amendment and Human Review Prerequisite Waiver

- **Amendment ID:** `LONG-002D-AMEND-001`
- **Task ID:** `LONG-002D3B-QUANTITATIVE-FREEZE-001`
- **Program:** `LONG-002` (Rapid-Upside Opportunity Research)
- **Phase:** `LONG-002D`
- **Classification:** Research Governance Amendment
- **Authorizer:** Gary Yang
- **Authorization Date:** 2026-10-05
- **Status:** Gary Approved
- **Machine-Readable Spec:** [`docs/research/specs/LONG-002D-AMEND-001.json`](specs/LONG-002D-AMEND-001.json)
- **Production Promotion Eligible:** `false`
- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)

---

## 1. Executive Summary & Authorization Context

The original `LONG-002` research contract ([`docs/research/specs/LONG-002-v1.json`](specs/LONG-002-v1.json)) specified that the final model feature set would be decided in `LONG-002D` following:
1. Core technical and market-context KPI discovery; and
2. Discretionary human blinded chart review.

Gary Yang has explicitly elected **NOT** to perform the discretionary human blinded chart-review study. In accordance with repository research governance ([`docs/RESEARCH-PROTOCOL.md`](../RESEARCH-PROTOCOL.md)), the project does not silently ignore or bypass contract prerequisites. Instead, this formal amendment documents the waiver and transition to a quantitative-only research path.

Gary Yang explicitly authorized the continuation of `LONG-002` using a **quantitative-only feature-registry freeze** grounded strictly upon already-completed development evidence from:
- `LONG-002C` (Outcome census, master episodes, frozen baseline comparator `volatility_aware_momentum_5`);
- `LONG-002D1` (Core technical and market-context univariate KPI census); and
- `LONG-002D2` (Incremental reranking study on `relative_volume_20` and `sma20_slope_5`).

---

## 2. Explicit Human Review Waiver Terms

The `LONG-002D3A` human review path is formally **WAIVED**.

Specifically:
- The 24-case human pilot review will **not** be executed;
- The 240-case main blinded human study sample will **not** be generated;
- **No** human labels have been or will be collected;
- **No** human-label predictive performance claim has been or will be made;
- **No** pilot outcome reveal has occurred or is required;
- **No** feature derived from human chart review may be introduced into `LONG-002`.

Human blinded review was waived by Gary Yang before execution and contributed no evidence.

---

## 3. Formal Amendment Status Declarations

| Status Dimension | Contract State | Notes |
|---|---|---|
| `human_blinded_review_status` | `waived_by_gary_not_executed` | Discretionary human review path waived by Gary Yang |
| `pilot_human_labels_collected` | `false` | Zero human pilot labels collected |
| `main_240_human_sample_generated` | `false` | Main 240-case study was never sampled or generated |
| `human_review_evidence_used_for_feature_selection` | `false` | Feature decisions derived strictly from quantitative development evidence |
| `human_review_required_for_long_002e` | `false` | Prerequisite waived by this amendment |
| `quantitative_kpi_discovery_required` | `true` | Completed in LONG-002D1 |
| `final_quantitative_registry_freeze_required` | `true` | Required and completed in LONG-002D3B |
| `recommendation_episode_contract_required` | `true` | Required and completed in LONG-002D3B |
| `validation_access_authorized` | `false` | Validation split (2021–2022) remains strictly quarantined |
| `holdout_access_authorized` | `false` | Holdout split (2023–2025) remains strictly quarantined |
| `shadow_access_authorized` | `false` | Prospective shadow remains strictly unopened |
| `long_002e_authorized` | `false` | Model fitting remains unauthorized pending separate Gary authorization |
| `production_change_authorized` | `false` | Production remains unchanged (`APPROVED_PRODUCTION_STRATEGIES == ()`) |

---

## 4. Preservation of LONG-002D3A Tooling

All `LONG-002D3A` artifacts, tooling, and tests are fully preserved:
- **D3A Tooling Status:** Completed and verified (`tests/research/long_002d3a/` 79 passing tests).
- **24-Case Human Pilot:** `waived_not_executed`.
- **240-Case Main Study:** `waived_not_generated`.
- **Human Labels Collected:** `0`.
- **Human Predictive Evidence:** `none`.
- **Answer Key Integrity:** The 24-case pilot answer key remains strictly external, gitignored, unrevealed, and cryptographically committed in `answer_key_commitment.json` (`3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103`).

D3A represents fully functioning research tooling that could be separately reactivated in the future. If human review is ever reactivated:
1. It requires separate explicit Gary Yang authorization;
2. Blinding must be strictly preserved;
3. Results may **not** silently modify an already-active `LONG-002E` feature registry;
4. Any feature registry change after `LONG-002E` begins requires a formal development amendment.

---

## 5. Scope Boundary & Preserved Invariants

This amendment supersedes **ONLY** the requirement that blinded human review be completed before the final feature registry can be frozen.

It does **NOT** loosen any of the following core governance safeguards:
- **Point-in-Time Integrity:** Strict PIT data integrity and as-of cutoff enforcement remain mandatory.
- **Development-Only Grounding:** All feature evaluations and decisions are based strictly on development split evidence (`2016-01-01` to `2020-12-31`).
- **Feature Registry Freeze:** The feature registry must be completely frozen before any `LONG-002E` model experiments begin.
- **Search Budget Caps:** The maximum model search budget remains strictly capped at 48 materially distinct configurations (Round 1: 12 per family, 36 total across 3 families; Round 2: 12 additional across all families).
- **Experiment Ledger:** Every attempted configuration, including failures, must be registered in the experiment ledger.
- **Split Quarantines:**
  - Validation split (`2021-01-01` to `2022-12-31`) remains unopened and quarantined.
  - Holdout split (`2023-01-01` to `2025-12-31`) remains unread, untouched, and strictly quarantined.
  - Shadow replay (`2026-01-01` onward) remains unopened.
- **Model Family Restrictions:** Strictly bounded to:
  1. Transparent cross-sectional rank/score system;
  2. Regularized probabilistic/time-to-event system; and
  3. Shallow strongly regularized gradient-boosted trees.
  *(No AutoML, neural nets, transformers, RL, evolutionary search, or unrestricted ensembles).*
- **Promotion & Production Gates:** Promotion gates remain unchanged. Holdout support authorizes only prospective shadow consideration. `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.

---

## 6. Upstream Locked Specification Hashes

| Upstream Specification | Relative Path | Cryptographic SHA-256 Digest | Status |
|---|---|---|:---:|
| `LONG-002-v1.json` | [`docs/research/specs/LONG-002-v1.json`](specs/LONG-002-v1.json) | `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5` | Verified Match |
| `LONG-002D1-v1.json` | [`docs/research/specs/LONG-002D1-v1.json`](specs/LONG-002D1-v1.json) | `cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381` | Verified Match |
| `LONG-002D2-v1.json` | [`docs/research/specs/LONG-002D2-v1.json`](specs/LONG-002D2-v1.json) | `db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8` | Verified Match |
| `LONG-002D3A-v1.json` | [`docs/research/specs/LONG-002D3A-v1.json`](specs/LONG-002D3A-v1.json) | `7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427` | Verified Match |
| `LONG-002D3A-CORR-001.json` | [`docs/research/specs/LONG-002D3A-CORR-001.json`](specs/LONG-002D3A-CORR-001.json) | `f0c239ab934cb7435ed914a33e1224b490974218016b442cba4793a7a8f87cfe` | Verified Match |
