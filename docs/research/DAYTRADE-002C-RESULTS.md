# DAYTRADE-002C — Bounded Real Preholdout Acquisition & Momentum Study Execution Results

This document records the empirical evidence, provider provenance, and execution results of the bounded real-data study for `DAYTRADE-002C` (locked early-to-late intraday ETF momentum).

* **Task ID:** `DAYTRADE-002C`
* **Title:** Bounded Real Preholdout Acquisition & Momentum Study Execution
* **Classification:** Research-only real-data execution (zero production impact)
* **Execution Date:** 2026-10-04
* **Evaluator Base Commit SHA:** `774b37efe883233d0c3f2a888e37aebf0851d347` (merge commit of PR #91 / `DAYTRADE-002B`)
* **Canonical Specification:** `docs/research/specs/DAYTRADE-002A-v1.json`
* **Locked Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Preholdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Evidence Confidence Cap:** `limited_but_usable_evidence`
* **Production Promotion Eligible:** `False`
* **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 1. Study Identity and Contract

| Dimension | Specification Value |
|---|---|
| **Task ID** | `DAYTRADE-002C` |
| **Evaluator Code SHA** | `774b37efe883233d0c3f2a888e37aebf0851d347` (clean frozen evaluator from PR #91) |
| **Locked Spec SHA-256** | `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127` |
| **Preholdout Manifest SHA-256** | `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb` |
| **Freeze Timestamp** | `2026-10-04T00:26:19.569551+00:00` |
| **Market Data Provider** | Alpaca Market Data API (`alpaca`) |
| **Market Data Feed** | `sip` (Securities Information Processor consolidated tape, no fallback) |
| **Timeframe & Adjustment** | `1Min`, split-adjusted only (`split`), cash dividends excluded |
| **Exchange Calendar** | `XNYS` regular trading sessions (09:30–16:00 ET; early closes excluded) |
| **Timezone** | `America/New_York` |
| **Universe** | Fixed 15-ETF liquid sector and broad-market panel: `XLK`, `XLV`, `XLF`, `XLY`, `XLP`, `XLE`, `XLI`, `XLB`, `XLU`, `XLRE`, `XLC`, `SPY`, `QQQ`, `IWM`, `DIA` |
| **Dataset Partitions** | Context Anchor: `2025-12-31`<br>Warm-up: `2026-01-02` through `2026-01-30`<br>Development: `2026-02-02` through `2026-04-30`<br>Validation: `2026-05-01` through `2026-06-30`<br>Holdout (prohibited): `2026-07-01` through `2026-08-31` |
| **Private Dataset Root** | `~/.tradex/research/daytrade_002_v1/preholdout` (external to all repositories/worktrees; raw OHLCV files are strictly private and uncommitted) |
| **External Run Root** | `~/.tradex/research/daytrade_002c_v1/` (freeze, development, validation external execution workspaces) |
| **Evidence Confidence Cap** | `limited_but_usable_evidence` |
| **Production Promotion** | Ineligible (`production_promotion_eligible = false`) |

---

## 2. Dataset Evidence & Provider Provenance

The preholdout dataset partition (context anchor `2025-12-31`, warmup through `2026-01-30`, development through `2026-04-30`, and validation through `2026-06-30`) was acquired exactly once using the frozen `build-dataset --split preholdout --execute-provider` command against Alpaca SIP.

* **Private Dataset Root:** `~/.tradex/research/daytrade_002_v1/`
* **Pre-Holdout Manifest Path:** `preholdout/manifest.lock.json`
* **Pre-Holdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Logical Provider Calls:** `105` (15 ETFs × 7 monthly intervals covering 2025-12-31 through 2026-06-30)
* **HTTP Pages Retrieved:** `149` (all requests well within the 100-page limit per monthly interval)
* **HTTP Attempts:** `149`
* **HTTP Retries:** `44` (subsequent page requests handled without rate-limit failures)
* **HTTP 429 Count:** `0`
* **HTTP Error Count:** `0`
* **Provider Malformed Timestamps:** `0` across all 15 ETFs
* **Total Malformed Timestamps Reported by Provider:** `0`
* **Pagination Complete:** `True`
* **Safe Error Classification:** `"none"`
* **Represented Universe Symbols:** `15` of 15 locked symbols (`XLK`, `XLV`, `XLF`, `XLY`, `XLP`, `XLE`, `XLI`, `XLB`, `XLU`, `XLRE`, `XLC`, `SPY`, `QQQ`, `IWM`, `DIA`).
* **Source Bar Files:** Exactly 15 CSV files in `bars/` with verified individual SHA-256 cryptographic digests:
  * `bars/XLK.csv`: `16cde6316e82fb233ac84cc4c2d3dadb159a8c9b24d8b923718e3c294040601c`
  * `bars/XLV.csv`: `0848560d3b67e46354bd78789db3ae68b3c20bdce4e2d5708bf18da6656a84b5`
  * `bars/XLF.csv`: `87a6b8efcae214103465edad22cff28e142f4eafeec1ec9c38a078cf314ae0ee`
  * `bars/XLY.csv`: `e4daaa9f6041bba49751639fc0af551786b86270b629a8bc208c3205e004c86d`
  * `bars/XLP.csv`: `8d6a58b33d6dee0f113d0d9ce94bc63a5b133025d33b52a7759b3356cbaaa199`
  * `bars/XLE.csv`: `1634947222e1c14d66bdc61fc7a716a1d916556ee269b03752ef1ddfecc583e2`
  * `bars/XLI.csv`: `6f7d560e7087fb160a3b7596d90e86072e2b8ebfc285b405b6137bb1e9bb8700`
  * `bars/XLB.csv`: `ec05784b30aee9b4a1601c10c7e019ba86bb38e6ccb47f3af749193f9a9bc493`
  * `bars/XLU.csv`: `83ae5d609ef3acc9ec32048c8a023676d06999e2c7b99a306da424f968302624`
  * `bars/XLRE.csv`: `b3abd58e931b547376c160dfeb88580f8dadba68d5ef7def102ee634e75acd24`
  * `bars/XLC.csv`: `db4742679cf27d0b2210498343aebcbcb6bbd4bb8d90db2dc75182a6f1f5541c`
  * `bars/SPY.csv`: `bee62d98a76a6e73fad75bdfb83d8bfc4ec2d54465c3de8ea4626b09dcb30c9b`
  * `bars/QQQ.csv`: `44e6523fe8c07b69b736496a99d0e9386ac87f447605fd41becc50d65568e667`
  * `bars/IWM.csv`: `7393d59c10811bdbe7a94ab8fee8066a3ef1f8b95c5d0896309f7cad9997539d`
  * `bars/DIA.csv`: `286cb40f7a8473786ae1e45f84b2d7b49c4857ec9e968118760208caa8b5fe22`
* **Zero Unmanifested Files:** Verified fail-closed; no extraneous files exist in `bars/`.

---

## 3. Evaluator Freeze State

Before study execution, the evaluator was frozen against the acquired dataset manifest using `freeze`:
* **Freeze File:** `~/.tradex/research/daytrade_002c_v1/freeze/freeze.json`
* **Bound Git Commit SHA:** `774b37efe883233d0c3f2a888e37aebf0851d347`
* **Worktree Cleanliness:** `true`
* **Bound Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Bound Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Bound Evaluation Files:** 36 Python source, test, spec, and documentation file digests cryptographically bound.

---

## 4. Development Split (Diagnostic Only)

Development was executed exactly once using the frozen evaluator and bound freeze record. Development is diagnostic only; its outcome causes zero parameter, threshold, code, or methodology alterations.

* **Split Period:** `2026-02-02` through `2026-04-30` (62 regular trading sessions)
* **Expected Ticker-Sessions:** 930 (62 sessions × 15 ETFs)
* **Disposition:** **`inconclusive`**
* **Disposition Step:** `step_2_evidence_sufficiency`
* **Disposition Reason:** `sample_gate_failed (events=0, etfs=0, dates=0); data_quality_gate_failed (100.00%)`

### Core Development Metrics

| Metric | Value |
|---|---|
| **Expected Ticker-Sessions** | 930 |
| **Eligible Ticker-Sessions** | 0 |
| **DQ-Excluded Ticker-Sessions** | 930 (100.00%) |
| **Event Count** | 0 |
| **Represented ETFs** | 0 |
| **Event Session Count (Dates)** | 0 |
| **Long Event Count** | 0 |
| **Short Event Count** | 0 |
| **Maximum Single-ETF Concentration** | 0.00% |
| **Multi-Signal Session Count & Rate** | 0 (0.00%) |
| **Mean Gross Signed Return (30m)** | 0.0 |
| **Median Gross Signed Return (30m)** | 0.0 |
| **Gross Win Rate (30m)** | 0.00% |
| **Mean Net Return @ 0 bps/side** | 0.0 |
| **Mean Net Return @ 2 bps/side (Primary)** | 0.0 |
| **Mean Net Return @ 5 bps/side (Stressed)** | 0.0 |
| **Median Net Return @ 2 bps/side** | 0.0 |
| **Matched Baseline Mean Return** | None |
| **Matched Baseline Median Return** | None |
| **Event-minus-Baseline Uplift (Mean)** | None |
| **Event-minus-Baseline Uplift (Median)** | None |
| **Represented ETFs with Positive Net Mean** | 0 of 0 (0.00%) |
| **Primary Net Return 95% Clustered CI** | `non_computable` (`error_reason: no_eligible_target_dates`) |
| **Baseline Uplift 95% Clustered CI** | `non_computable` (`error_reason: no_eligible_target_dates`) |

### Development Gate Results

| Gate | Outcome | Detail |
|---|---|---|
| `sample_gate` | **FAIL** | `event_count = 0 < 75`, `represented_etfs = 0 < 10`, `event_sessions = 0 < 20` |
| `concentration_gate` | **PASS** | `0.0% <= 15.0%` |
| `data_quality_gate` | **FAIL** | `100.0% excluded > 5.0% tolerance` |
| `primary_net_effect_gate` | **FAIL** | CI `non_computable` |
| `baseline_uplift_gate` | **FAIL** | CI `non_computable` |
| `breadth_gate` | **FAIL** | `0.0% < 60.0%` |

---

## 5. Validation Split (Formal Preregistered Evaluation)

Validation was executed exactly once immediately after development, with no code, parameter, or configuration modifications. Validation is the formal preregistered gate evaluation.

* **Split Period:** `2026-05-01` through `2026-06-30` (41 regular trading sessions)
* **Expected Ticker-Sessions:** 615 (41 sessions × 15 ETFs)
* **Disposition:** **`inconclusive`**
* **Disposition Step:** `step_2_evidence_sufficiency`
* **Disposition Reason:** `sample_gate_failed (events=0, etfs=0, dates=0); data_quality_gate_failed (100.00%)`

### Core Validation Metrics

| Metric | Value |
|---|---|
| **Expected Ticker-Sessions** | 615 |
| **Eligible Ticker-Sessions** | 0 |
| **DQ-Excluded Ticker-Sessions** | 615 (100.00%) |
| **Event Count** | 0 |
| **Represented ETFs** | 0 |
| **Event Session Count (Dates)** | 0 |
| **Long Event Count** | 0 |
| **Short Event Count** | 0 |
| **Maximum Single-ETF Concentration** | 0.00% |
| **Multi-Signal Session Count & Rate** | 0 (0.00%) |
| **Mean Gross Signed Return (30m)** | 0.0 |
| **Median Gross Signed Return (30m)** | 0.0 |
| **Gross Win Rate (30m)** | 0.00% |
| **Mean Net Return @ 0 bps/side** | 0.0 |
| **Mean Net Return @ 2 bps/side (Primary)** | 0.0 |
| **Mean Net Return @ 5 bps/side (Stressed)** | 0.0 |
| **Median Net Return @ 2 bps/side** | 0.0 |
| **Matched Baseline Mean Return** | None |
| **Matched Baseline Median Return** | None |
| **Event-minus-Baseline Uplift (Mean)** | None |
| **Event-minus-Baseline Uplift (Median)** | None |
| **Represented ETFs with Positive Net Mean** | 0 of 0 (0.00%) |
| **Primary Net Return 95% Clustered CI** | `non_computable` (`error_reason: no_eligible_target_dates`) |
| **Baseline Uplift 95% Clustered CI** | `non_computable` (`error_reason: no_eligible_target_dates`) |

### Validation Gate Results (All 6 Gates)

| Gate | Status | Criteria & Realized Value |
|---|---|---|
| **1. Sample Gate** | **FAIL** | Required $\ge 75$ events across $\ge 10$ ETFs and $\ge 20$ dates. Realized: 0 events, 0 ETFs, 0 dates. |
| **2. Concentration Gate** | **PASS** | Max single ETF $\le 15.0\%$. Realized: $0.00\%$. |
| **3. Data Quality Gate** | **FAIL** | Excluded ticker-session rate $\le 5.0\%$. Realized: $100.00\%$ (615 of 615 excluded). |
| **4. Primary Net-Effect Gate** | **FAIL** | Mean net $> 0$ and 95% CI lower $> 0$. Realized: CI `non_computable`. |
| **5. Baseline-Uplift Gate** | **FAIL** | Mean uplift $> 0$ and 95% CI lower $> 0$. Realized: CI `non_computable`. |
| **6. Cross-ETF Breadth Gate** | **FAIL** | $\ge 60.0\%$ represented ETFs with positive net return. Realized: $0.00\%$. |

---

## 6. Diagnostic Root Cause Analysis

### Empirical Mechanism of Data Quality Failure

Investigation into why the data-quality audit excluded 100% of ticker-sessions revealed the following exact technical mechanism:

1. **Normalized CSV Schema:** The dataset acquisition adapter (`tradex/research/daytrade_momentum/dataset.py:write_normalized_bars_csv`) writes normalized bar CSVs with the locked header:
   ```text
   bar_start,open,high,low,close,volume
   ```
2. **Reader Loading:** The reader function (`read_normalized_bars_csv`) reads these columns and creates a helper parsed datetime column `dt_parsed`.
3. **Session Audit Timestamp Resolution:** In `tradex/research/daytrade_momentum/quality.py` (`audit_ticker_session`, line 101), the loop resolves the bar timestamp using:
   ```python
   raw_ts = row.get("datetime") or row.get("timestamp") or row.get("t")
   ```
   Notice that `row.get("bar_start")` was omitted from that lookup tuple.
4. **Fail-Closed Malformed Flagging:** Because the normalized DataFrame rows contain `bar_start` (not `datetime`, `timestamp`, or `t`), `raw_ts` evaluated to `None` for every single row. The evaluator's fail-closed guard:
   ```python
   if raw_ts is None or pd.isna(raw_ts):
       malformed_timestamp_count += 1
       continue
   ```
   caused all 390 bars of every session to be counted as malformed and skipped from grid alignment.
5. **Session Exclusion & Gate Trigger:** With 0 aligned bars, every ticker-session was categorized as `missing_bars = 390` (`excess_missing_bars_390_pct_100.00`), producing an exclusion rate of 100.0% in both development (930 sessions) and validation (615 sessions). Under the locked 5-step precedence hierarchy, this directly triggered `step_2_evidence_sufficiency` failure (`inconclusive`).

### Strict Research Integrity Compliance

Pursuant to Section 15 of the task assignment (*Real-Data Integrity Rule After First Access*):
> *"Once real 2026 data has been acquired: the methodology and evaluator are frozen. Do not change: code, threshold, dates, universe, signal formula... If a real-world execution defect is discovered: 1. stop; 2. preserve evidence; 3. classify execution as invalid/incomplete as appropriate; 4. report the defect; 5. do not fix and rerun within this task. No data-driven repair is authorized."*

In accordance with this protocol:
* **Zero evaluator code changes were made.**
* **Zero post-hoc fixes or reruns were attempted.**
* The empirical results faithfully record the exact output of the merged evaluator commit `774b37efe883233d0c3f2a888e37aebf0851d347`.

---

## 7. Holdout Partition Status

* **Status:** **`unread_not_acquired`**
* **Provider Calls for Holdout:** Exactly `0`.
* **July / August 2026 Bars:**
  * **NOT ACQUIRED**
  * **NOT READ**
  * **NOT PARSED**
  * **NOT EVALUATED**
* **Governance Rule:** Because validation did not earn `supported` (it resolved to `inconclusive` under `step_2_evidence_sufficiency`), holdout access is strictly prohibited. The holdout partition remains completely sealed and unacquired.

---

## 8. Safe Artifact Bundle Verification

The evaluator generated complete 14-artifact bundles in external storage, which were verified and copied to the repository under `docs/research/artifacts/DAYTRADE-002C-v1/`:

* `docs/research/artifacts/DAYTRADE-002C-v1/development/` (14 files; `checksums.sha256` verified)
* `docs/research/artifacts/DAYTRADE-002C-v1/validation/` (14 files; `checksums.sha256` verified)
* `docs/research/artifacts/DAYTRADE-002C-v1/evidence-index.json` (machine-readable study index)

All artifact cryptographic digests match `checksums.sha256` in both bundles. No raw bar CSVs, provider secrets, or request authorization headers exist in tracked repository files.

---

## 9. Research Limitations

All evidence from this bounded real execution is subject to the preregistered constraints:

1. **Evidence-Confidence Cap:** Strictly capped at `limited_but_usable_evidence`.
2. **Evaluator Execution Defect:** The evaluator's timestamp column resolution in `quality.py` prevented empirical return distribution analysis on real bars.
3. **Finite Panel:** 15 liquid ETF snapshot.
4. **Single 2026 Market Regime:** Confirmatory window spans the first half of 2026.
5. **Hypothesis Genesis:** Conceived after observing DAYTRADE-001 results; 2025 data serves as context only.
6. **No Production Promotion:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved. This study authorizes zero changes to production trading, alerts, scoring, or order execution.
