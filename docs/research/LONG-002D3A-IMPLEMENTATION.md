# LONG-002D3A: Blinded Review Tooling, Pilot Freeze, and Main-Study Contract Foundation — Implementation Report

- **Task ID:** `LONG-002D3A-BLINDED-REVIEW-PILOT-001`
- **Program:** `LONG-002` (Rapid-Upside Opportunity Research)
- **Phase:** `LONG-002D3A`
- **Title:** Blinded Review Tooling, Pilot Freeze, and Main-Study Contract Foundation
- **Classification:** `research_only`
- **Authorizer:** Gary Yang
- **Authorization Date:** 2026-10-03
- **Bounded by:** ChatGPT
- **Preregistration Spec:** `docs/research/specs/LONG-002D3A-v1.json`
- **Spec SHA-256:** `7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427`
- **Preregistration Commit SHA:** `a6345f97330358b1dfbbdf7c11e6aba9f10e2c87`
- **Spec Immutability:** Verified clean; `git diff a6345f97330358b1dfbbdf7c11e6aba9f10e2c87..HEAD -- docs/research/specs/LONG-002D3A-v1.json` is empty.
- **Official Execution Run ID:** `2026-10-04-131000`
- **Branch:** `antigravity/long-002d3a-blinded-review-pilot`
- **Production Promotion Eligible:** `false`
- **Approved Production Strategies:** `[]` (`APPROVED_PRODUCTION_STRATEGIES == ()`)
- **Status:** Complete, Tested, Audited, and Verified

---

## 1. Executive Summary & Boundaries

This document certifies the complete implementation and empirical verification of **LONG-002D3A**, establishing the preregistered blinded qualitative review tooling, deterministic 24-case pilot freeze, cryptographic answer key commitment, and future main-study sampling contract foundation for the `LONG-002` research program.

### Scope & Invariant Summary
1. **Dedicated Preregistration Commit:** Preregistration specification `docs/research/specs/LONG-002D3A-v1.json` was committed prior to empirical execution in commit `a6345f97330358b1dfbbdf7c11e6aba9f10e2c87` with SHA-256 digest `7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427`. The specification has remained completely immutable.
2. **Deterministic Pilot Sample ($N=24$):** Exactly 24 pilot cases were sampled deterministically using seed `20261003` across the four locked strata:
   - 6 Positive Master Opportunity Episodes (`positive_master_episode`)
   - 6 Near-Misses (`near_miss`)
   - 6 Adverse Traps (`adverse_trap`)
   - 6 Ordinary Non-Movers (`ordinary_non_mover`)
3. **Ticker & Annual Diversity:** Exactly 24 distinct tickers are represented (0 ticker overlap), with candidate coverage spanning development years 2016 through 2020.
4. **Opaque Case Identifiers:** Case IDs `D3A-PILOT-001` through `D3A-PILOT-024` are strictly opaque and deterministically shuffled so case presentation order leaks no information about sample stratum, outcome, ticker, or date.
5. **Answer Key Quarantine & Cryptographic Commitment:** The unblinded ground truth (`pilot_answer_key.json`) is stored strictly in the external gitignored data directory (`data/research/long_002d3a/2026-10-04-131000/pilot_answer_key.json`). Its cryptographic SHA-256 commitment (`3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103`, 11,748 bytes, 24 records) is recorded in committed artifact `answer_key_commitment.json`. The answer key content is NEVER committed to git.
6. **Blinded Case Packets:**
   - **Stage A (Technical Only):** Normalized OHLC bars (base 100.0 at `T-60`), moving averages, scale-invariant ATR% 14, relative volume, pre-decision momentum metrics, and benchmark SPY context.
   - **Stage B (Qualified PIT Context):** Retains Stage A and introduces point-in-time qualitative cohorts (market cap cohort, trading history cohort, fail-closed unknown earnings schedule status).
   - **Zero Leakage:** All 24 cases passed the exhaustive 10-point blinding audit with zero ticker, security ID, calendar date, stratum name, future bar, or outcome leakage.
7. **Standalone Static HTML Reviewer:** Generated local self-contained HTML review application (`index.html`) featuring interactive SVG candlestick charting, technical metrics, Stage B toggle, and client-side review form with localStorage and JSON export. Requires zero external CDNs, zero server processes, and zero network calls.
8. **Reviewer Label Schema & Ingestion Contract:** Strict schema validation with separate persistence for Stage A and Stage B review submissions in `PilotReviewStore`.
9. **Future Main-Study Contract Foundation:** Locked structural parameters for the future 240-case study (seed `20261004`, 120/40/40/40 strata breakdown, 12 batches of 20, permanent exclusion of all 24 pilot observation keys). The 240-case sample remains strictly UNGENERATED in this PR.
10. **Strict Non-Scope Boundaries Preserved:** Zero human review execution performed in this PR; zero pilot answer reveals; zero model fitting; zero feature registry freezes; zero provider network calls (`0 live attempts, 0 HTTP calls`); `APPROVED_PRODUCTION_STRATEGIES == ()`.

---

## 2. Upstream Input Integrity & Cryptographic Verifications

All input files were verified byte-for-byte against the locked preregistered checksums before empirical execution:

| Dataset / Table | File Path | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|---|
| Decision Observations | `data/research/long_002c/decision_observations.parquet` | `722bee866cabb697931dfb96abaf7f9250f1cd1240b405d2e308af0b6bbb48af` | `722bee866cabb697931dfb96abaf7f9250f1cd1240b405d2e308af0b6bbb48af` | MATCH [OK] |
| Outcome Matrix | `data/research/long_002c/outcome_matrix.parquet` | `b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3` | `b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3` | MATCH [OK] |
| Master Episodes | `data/research/long_002c/master_episodes.parquet` | `1fe5b36f98919465007a720908c626203e5272b054a4ef76be772db279b3cc98` | `1fe5b36f98919465007a720908c626203e5272b054a4ef76be772db279b3cc98` | MATCH [OK] |
| Constituent Memberships | `data/research/long_002c/constituent_memberships.parquet` | `53a8adc92f1210ef3a1b6d10c9eedd1f360dad2760897f97b5d293f473734b11` | `53a8adc92f1210ef3a1b6d10c9eedd1f360dad2760897f97b5d293f473734b11` | MATCH [OK] |
| Baseline Outputs | `data/research/long_002c/baseline_comparator_outputs.parquet` | `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` | `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` | MATCH [OK] |
| Feature Table | `data/research/long_002d1/feature_table.parquet` | `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` | `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` | MATCH [OK] |
| Discovery Manifest | `data/research/long_002c/discovery_manifest.json` | `d1bf16d6b475c93b5c47e81a47af5597fd514432880107030040a81fd61e9947` | `d1bf16d6b475c93b5c47e81a47af5597fd514432880107030040a81fd61e9947` | MATCH [OK] |

---

## 3. Deterministic Pilot Sample Construction

The empirical pilot sample was generated using `sample_pilot_cases` under frozen seed `20261003` from the verified Stage C population (Development period: `2016-01-01` to `2020-12-31`, cutoff `20:30` ET).

### Strata Definitions & Quotas ($N=24$, 6 per stratum)
1. **Positive Master Episode ($n=6$):** Anchor observations of valid Stage C master opportunity episodes at the 20:30 snapshot (`clean_target_reached_10_21 == True`).
2. **Near-Miss ($n=6$):** Observations strictly outside any active master episode window with `clean_target_reached == False` and `near_miss == True` on the primary (+10% / 10 sessions) cell.
3. **Adverse Trap ($n=6$):** Observations outside active master episodes not qualifying as near-miss with `clean_target_reached == False`, `near_miss == False`, and `adverse_excursion == True`.
4. **Ordinary Non-Mover ($n=6$):** Observations outside active master episodes not qualifying as near-miss or adverse trap with `target_progress_ratio < 0.50` and `clean_target_reached == False`.

### Stratification Guardrails
- **Precedence & Independence:** Strict class priority precedence (`positive_master_episode` > `near_miss` > `adverse_trap` > `ordinary_non_mover`) ensures no ambiguous membership.
- **Control Exclusion:** All active positive master episode anchors and 21-session constituent members were explicitly excluded from control candidate pools.
- **Diversity Enforcement:**
  - **Ticker Diversity:** Exactly 24 unique tickers across all 24 cases (0 duplicate tickers).
  - **Annual Diversity:** Every stratum samples cases across the development years 2016–2020.
- **Deterministic Shuffling:** All 24 cases were shuffled once using random seed `20261003` before assigning sequential opaque identifiers `D3A-PILOT-001` through `D3A-PILOT-024`.

---

## 4. Anonymization, Blinding, and Leakage Safeguards

### Normalization and Relative Time Indexing
- **Lookback Window:** Up to 61 daily trading sessions (`T-60` to `T0` inclusive).
- **Price Scaling:** Price series is scaled such that the first bar close in the lookback window is normalized to base `100.0`. All open, high, low, close, and moving average values are scaled proportionally, preserving all percentage returns and technical ratios.
- **Zero Future Leakage:** Historical bars end strictly at decision cutoff `T0`. The relative index is $\le 0$ for all bars.

### Exhaustive Blinding Audit
Every generated case packet was subjected to `audit_single_case`, enforcing:
1. **Zero Ticker Leakage:** Ticker symbol does not appear in any key, value, or nested text.
2. **Zero Security ID Leakage:** `immutable_security_id` does not appear anywhere in review packets.
3. **Zero Calendar Date Leakage:** Exact calendar dates (`YYYY-MM-DD`) are strictly absent from review packets.
4. **Zero True Class Leakage:** Stratum names are strictly absent from review packets.
5. **Zero Outcome Leakage:** Outcome labels (`clean_target_reached`, `mfe_pct`, `mae_pct`, etc.) are strictly absent.
6. **Zero Future Bar Leakage:** Last bar is labeled `T0` with relative index `0`; no positive index bars exist.
7. **Stage A Isolation:** Fundamental and event fields (`market_cap_cohort`, earnings status, etc.) are strictly excluded from Stage A.
8. **Stage B Retention:** Stage B properly nests the Stage A technical view.

**Audit Result:** All 24 pilot cases passed all 10 checks with zero violations detected (`violations_detected: 0`).

---

## 5. Answer Key Quarantine & Cryptographic Commitment

### Storage & Git Isolation
- **Git Policy:** `data/` is strictly gitignored. `git check-ignore data/research/long_002d3a/2026-10-04-131000/pilot_answer_key.json` confirms exclusion from version control.
- **External Path:** `data/research/long_002d3a/2026-10-04-131000/pilot_answer_key.json`
- **Committed Commitment File:** `docs/research/artifacts/LONG-002D3A/2026-10-04-131000/answer_key_commitment.json`

### Commitment Cryptographic Values
```json
{
  "byte_count": 11748,
  "created_at_utc": "2026-10-04T13:07:30.252733+00:00",
  "relative_external_path": "data/research/long_002d3a/2026-10-04-131000/pilot_answer_key.json",
  "row_count": 24,
  "run_id": "2026-10-04-131000",
  "schema_version": "v1",
  "sha256": "3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103",
  "spec_sha256": "7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427"
}
```

---

## 6. Standalone Local Static HTML Reviewer

The review interface is generated as a single standalone HTML document:
`data/research/long_002d3a/2026-10-04-131000/pilot_blinded/index.html`

### Features
- **Self-Contained Architecture:** Embeds all 24 blinded case packets as clean JSON data. Uses native browser SVG rendering for charts. Zero external dependencies, CDN scripts, fonts, or tracking.
- **Stage A Technical Panel:** Displays normalized candlestick chart with SMA20 (blue) and SMA50 (amber) overlays, relative volume indicator, pre-decision returns, ATR% 14, and SPY benchmark comparison.
- **Stage B Context Panel:** Reveals qualified point-in-time qualitative cohorts (market cap cohort, trading history cohort, earnings schedule status) alongside Stage A technicals.
- **Interactive Review Form:** Conforms to the locked reviewer label schema with separate tabs for Stage A and Stage B review submission.
- **Client-Side Persistence:** Automatically saves labels in browser `localStorage` and provides a one-click "Export All Labels" button saving `pilot_review_labels.json`.
- **Case Navigation:** Case selector dropdown with progress status pills (`Unlabeled`, `Stage A Only`, `Stage B Only`, `Stages A & B Labeled`).

---

## 7. Reviewer Label Schema & Ingestion Contract

The schema is formally defined in `docs/research/artifacts/LONG-002D3A/2026-10-04-131000/review_schema.json`.

### Form Fields
- `surface_decision`: `surface` | `do_not_surface`
- `visible_state_if_surfaced`: `Enter Now` | `Armed` | `Qualified Waitlist` | `null`
- `expected_target_pct`: `10` | `20` | `30` | `null`
- `expected_horizon_sessions`: `5` | `10` | `21` | `null`
- `qualitative_confidence`: integer `1`–`5`
- `setup_archetype`: `setup_archetype` | `other` | `unclear`
- `entry_plan`: string
- `trigger_or_zone`: string
- `max_validity_sessions`: integer `1`–`5` | `null`
- `gap_handling`: string
- `invalidation`: string
- `positive_reasons`: list of strings (max 3 items)
- `material_risks_counterarguments`: string

### Ingestion Contract (`PilotReviewStore`)
- Stage A and Stage B review submissions are stored in separate files (`<case_id>_stage_a.json` and `<case_id>_stage_b.json`).
- Prevents accidental overwrites unless explicitly authorized.
- Provides real-time review progress tracking.

---

## 8. Future Main-Study Sampling Contract Foundation

The structural specification for the future 240-case main review study is locked in:
`docs/research/artifacts/LONG-002D3A/2026-10-04-131000/main_study_contract.json`

### Structural Parameters
- **Sample Size:** 240 cases
- **Random Seed:** `20261004`
- **Strata Distribution:**
  - 120 Positive Master Episodes (`positive_master_episode`)
  - 40 Near-Misses (`near_miss`)
  - 40 Adverse Traps (`adverse_trap`)
  - 40 Ordinary Non-Movers (`ordinary_non_mover`)
- **Batching Structure:** 12 review batches of 20 cases each
- **Ticker Limit:** Maximum 2 appearances per ticker
- **Permanent Pilot Exclusion:** All 24 pilot observation keys (`immutable_security_id`, `as_of_date`, `cutoff_time`) are permanently excluded from the future candidate pool.
- **Execution Gate:** `execution_status: "NOT_EXECUTED_IN_THIS_PR"`. Generation requires formal authorization from Gary Yang and completed pilot workflow review.

---

## 9. Verification & Deterministic Test Results

### Automated Test Coverage
- **LONG-002D3A Focused Test Suite:** **49 passed in 33.60s** (`tests/research/long_002d3a/`)
  - `test_spec_contract.py` (10 tests)
  - `test_main_contract_synthetic.py` (6 tests)
  - `test_sampling_deterministic.py` (6 tests)
  - `test_blinding_and_audit.py` (8 tests)
  - `test_review_store_and_schema.py` (8 tests)
  - `test_viewer_generation.py` (2 tests)
  - `test_artifacts_commitment_and_cli.py` (9 tests)
- **Regression Test Suites:** **220 passed in 24.45s**
  - `tests/research/long_002d2`
  - `tests/research/long_002d`
  - `tests/research/long_002c`
  - `tests/research/test_long_002_spec.py`
- **Lint Check:** `uv run ruff check tests scripts tradex/research/long_002d3a tests/research/long_002d3a` — **All checks passed (0 errors)**.
- **Git Diff Check:** `git diff --check` — **Clean (0 errors, 0 whitespace violations)**.
- **Spec Immutability:** `git diff a6345f97330358b1dfbbdf7c11e6aba9f10e2c87..HEAD -- docs/research/specs/LONG-002D3A-v1.json` — **Clean (0 diff lines)**.

---

## 10. CLI Reference & Verification Commands

### CLI Subcommands
The CLI entry point `tradex.research.long_002d3a.cli` provides four subcommands:

1. **Run Pipeline:**
   ```bash
   uv run python -m tradex.research.long_002d3a.cli run --run-id 2026-10-04-131000
   ```
2. **Verify Commitments & Checksums:**
   ```bash
   uv run python -m tradex.research.long_002d3a.cli verify --run-id 2026-10-04-131000
   ```
3. **Open Viewer:**
   ```bash
   uv run python -m tradex.research.long_002d3a.cli open-viewer --run-id 2026-10-04-131000
   ```
   *(Add `--no-browser` to display the file URI without opening a browser window).*
4. **Record Reviewer Label:**
   ```bash
   uv run python -m tradex.research.long_002d3a.cli record-label --run-id 2026-10-04-131000 --case-id D3A-PILOT-001 --stage stage_a --label-json "<json_or_file>"
   ```

---

## 11. Committed Artifact Inventory

The committed safe artifact bundle is located at:
`docs/research/artifacts/LONG-002D3A/2026-10-04-131000/`

- `answer_key_commitment.json` — External answer key cryptographic hash, byte size, and row count commitment.
- `execution_metadata.json` — Complete environment, runtime, governance, and audit metadata.
- `input_integrity.json` — Cryptographic verification of all 7 Stage C upstream inputs.
- `pilot_sampling_summary.json` — Aggregate sampling summary (strata counts, annual distribution, unique tickers; zero sensitive fields).
- `pilot_blinding_audit.json` — Audit verification results confirming zero leakage.
- `pilot_packet_manifest.json` — Safe review packet manifest.
- `review_schema.json` — Locked reviewer label schema definition.
- `main_study_contract.json` — Structural contract foundation for future 240-case study.
- `checksums.sha256` — SHA-256 digests of all committed artifact JSON files.

---

## 12. Correction Assignment LONG-002D3A-CORR-001

### Purpose & Review Decision
Following code review by Gary Yang and ChatGPT on Draft PR #95, correction assignment **LONG-002D3A-CORR-001** was executed to correct reviewer-visible Point-in-Time (PIT) context evidence, execution code provenance, locked seed enforcement, company-name leakage auditing, and forward exclusion-key artifact hygiene, while strictly retaining the exact frozen 24-case pilot sample.

### Invariant: Exact Sample Retention
- **Sample Preserved:** The exact 24 pilot cases from source run `2026-10-04-131000` were retained byte-for-byte.
- **No Resampling or Reshuffling:** Sampler was not invoked; cases were reconstructed directly from the frozen source answer key (`data/research/long_002d3a/2026-10-04-131000/pilot_answer_key.json`, SHA-256 `3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103`).
- **Case IDs & Order:** Identical ordering from `D3A-PILOT-001` through `D3A-PILOT-024`.
- **Accepted Workflow-Pilot Limitation:** As noted in the preregistered correction contract, the fact that pilot identities/dates were recoverable in Git history is an accepted workflow-pilot limitation. Gary has not inspected that mapping; pilot labels are workflow/presentation feedback only; no performance claims will be made.

### Corrections Implemented
1. **Stage B PIT Evidence Joins:**
   - Joined `data/research/long_002c/data_eligibility.parquet` (`market_cap`, `cohort_type`, `trading_history_sessions`).
   - Joined `data/research/long_002c/security_classification_status.parquet` (`is_eligible_common_stock`, `inferred_classification`).
   - Joined `data/research/long_002c/earnings_schedule_status.parquet` (`schedule_status`, `announcement_timing`, `sessions_to_earnings`).
   - Fabricated defaults (`"established"`, `252` sessions) were completely removed. Missing source values remain `unknown` / `null`.
2. **Execution Code Provenance:**
   - Recorded `execution_code_sha = "e83dec0813514e2d8627a513deae93eb3b03f0e9"` (matching `git rev-parse HEAD` of the committed implementation).
   - Recorded `git_worktree_clean_at_start = true`.
3. **Locked Seed Enforcement:**
   - Enforced `PILOT_SEED == 20261003`. Non-locked seeds fail closed with a clear error.
4. **Genuine Company-Name Leakage Audit:**
   - Verified that company names from `discovery_manifest.json` are audited across Stage A, Stage B, and viewer HTML (`company_name_checks_applicable_count = 24`, 0 violations detected).
5. **Forward Blinding Hygiene:**
   - Removed raw pilot observation keys from committed `main_study_contract.json`.
   - Committed `pilot_exclusion_commitment.json` referencing external gitignored `data/research/long_002d3a/2026-10-04-223000/pilot_exclusion_keys.json` (SHA-256 `3f9ab79c1e258471ff02cf3a4b859fe739c0fe08f161f1bd739a4b715478be00`, 24 records).
   - Committed `sample_equivalence.json` documenting 100% exact sample equivalence without disclosing sensitive mappings.

### Correction Run & Verification Artifacts
- **Correction Run ID:** `2026-10-04-223000`
- **Superseded Run ID:** `2026-10-04-131000` (superseded for Stage B context and execution provenance; sample preserved)
- **Committed Artifacts Directory:** `docs/research/artifacts/LONG-002D3A/2026-10-04-223000/`
- **Corrected Reviewer URL Command:**
  ```bash
  uv run python -m tradex.research.long_002d3a.cli open-viewer --run-id 2026-10-04-223000
  ```
- **Verification Command:**
  ```bash
  uv run python -m tradex.research.long_002d3a.cli verify --run-id 2026-10-04-223000
  ```
- **Test Suite Verification:**
  ```bash
  uv run pytest tests/research/long_002d3a -q
  ```
  Result: **79 passed** (including all 40 requirements in `test_corr_001_corrections.py`).
