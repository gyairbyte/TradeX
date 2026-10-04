# DAYTRADE-002C — Bounded Real Preholdout Acquisition & Momentum Study Execution Results

> [!IMPORTANT]
> **Executive Summary & Research-Validity Classification**
>
> * **Execution Validity:** **`INVALID`**
> * **Invalidity Category:** Evaluator implementation / schema-contract defect
> * **Invalidity Reason:** Evaluator timestamp-schema defect prevented all real bars from reaching session evaluation (`write_normalized_bars_csv()` serializes `bar_start`, whereas `quality.py:audit_ticker_session()` looked only for `datetime`, `timestamp`, `t`).
> * **Raw Evaluator Dispositions:** `INCONCLUSIVE / step_2_evidence_sufficiency` (both development and validation)
> * **Strategy Evidence Status:** **NO VALID STRATEGY EVIDENCE PRODUCED**
> * **Governing Research Conclusion:** This execution run produced **zero valid empirical evidence** regarding the early-to-late intraday ETF momentum hypothesis. The raw development and validation evaluator artifacts are preserved strictly as audit evidence of the failed execution. Values of 0 events, 0.0 mean return, 0.0% breadth, and non-computable bootstrap CIs are mechanical consequences of 0 eligible observations under the defective evaluator and must **NOT** be interpreted as empirical strategy performance. The hypothesis is **neither rejected, supported, nor meaningfully inconclusive** from this run.

* **Task ID:** `DAYTRADE-002C`
* **Title:** Bounded Real Preholdout Acquisition & Momentum Study Execution
* **Classification:** Research-only real-data execution (zero production impact)
* **Execution Date:** 2026-10-04
* **Evaluator Base Commit SHA:** `774b37efe883233d0c3f2a888e37aebf0851d347` (merge commit of PR #91 / `DAYTRADE-002B`)
* **Canonical Specification:** `docs/research/specs/DAYTRADE-002A-v1.json`
* **Locked Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Preholdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Evidence Confidence Cap:** `limited_but_usable_evidence` (preregistered ceiling; strategy evidence usability is `false` for this invalid run)
* **Production Promotion Eligible:** `False`
* **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 1. Study Identity and Contract

| Dimension | Specification Value |
|---|---|
| **Task ID** | `DAYTRADE-002C` |
| **Execution Validity** | `INVALID` (evaluator timestamp-schema defect) |
| **Strategy Evidence Status** | `NO VALID STRATEGY EVIDENCE PRODUCED` |
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
| **Holdout Status** | `unread_not_acquired` (zero provider calls; holdout strictly unread) |
| **Production Promotion** | Ineligible (`production_promotion_eligible = false`) |

---

## 2. Dataset Evidence & Provider Provenance

The preholdout dataset partition (context anchor `2025-12-31`, warmup through `2026-01-30`, development through `2026-04-30`, and validation through `2026-06-30`) was acquired successfully and exactly once using the frozen `build-dataset --split preholdout --execute-provider` command against Alpaca SIP.

* **Private Dataset Root:** `~/.tradex/research/daytrade_002_v1/`
* **Pre-Holdout Manifest Path:** `preholdout/manifest.lock.json`
* **Pre-Holdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
* **Logical Provider Calls:** `105` (15 ETFs × 7 monthly intervals covering 2025-12-31 through 2026-06-30)
* **HTTP Pages Retrieved:** `149` (average ~1.4 pages per monthly chunk; all within the 100-page limit)
* **HTTP Attempts:** `149`
* **HTTP Retries:** `44` (subsequent page requests handled without rate-limit errors)
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

The market data acquisition against Alpaca SIP was completed successfully and with complete provenance.

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

## 4. Raw Evaluator Output: Development Split (Audit Evidence Only)

Development was executed exactly once using the frozen evaluator and bound freeze record. Because of the evaluator timestamp-schema defect, all target sessions were excluded by the data-quality audit. The raw evaluator output below is preserved **only as audit evidence of the failed execution** and does not constitute empirical strategy performance evidence.

* **Split Period:** `2026-02-02` through `2026-04-30` (62 regular trading sessions)
* **Expected Ticker-Sessions:** 930 (62 sessions × 15 ETFs)
* **Eligible Ticker-Sessions:** 0 (all excluded due to evaluator defect)
* **DQ-Excluded Ticker-Sessions:** 930 (100.00%)
* **Raw Evaluator Disposition:** **`inconclusive`**
* **Raw Evaluator Step:** `step_2_evidence_sufficiency`
* **Raw Reason:** `sample_gate_failed (events=0, etfs=0, dates=0); data_quality_gate_failed (100.00%)`
* **Governing Research Conclusion:** **`INVALID EXECUTION`** (supersedes raw inconclusive disposition)

### Raw Development Metrics (Audit Record)

| Metric | Raw Value | Research Meaning |
|---|---|---|
| **Expected Ticker-Sessions** | 930 | Total sessions on calendar |
| **Eligible Ticker-Sessions** | 0 | Defect prevented bar parsing |
| **DQ-Excluded Ticker-Sessions** | 930 (100.00%) | Defect consequence |
| **Event Count** | 0 | Defect consequence (NOT zero setups) |
| **Represented ETFs** | 0 | Defect consequence |
| **Event Session Count (Dates)** | 0 | Defect consequence |
| **Long Event Count** | 0 | Defect consequence |
| **Short Event Count** | 0 | Defect consequence |
| **Maximum Single-ETF Concentration** | 0.00% | Degenerate calculation |
| **Multi-Signal Session Count & Rate** | 0 (0.00%) | Degenerate calculation |
| **Mean Gross Signed Return (30m)** | 0.0 | Degenerate calculation (empty set) |
| **Median Gross Signed Return (30m)** | 0.0 | Degenerate calculation (empty set) |
| **Gross Win Rate (30m)** | 0.00% | Degenerate calculation (empty set) |
| **Mean Net Return @ 2 bps (Primary)** | 0.0 | Degenerate calculation (empty set) |
| **Matched Baseline Mean Return** | None | No baseline computed |
| **Event-minus-Baseline Uplift (Mean)** | None | No uplift computed |
| **Primary Net Return 95% Clustered CI** | `non_computable` | `error_reason: no_eligible_target_dates` |
| **Baseline Uplift 95% Clustered CI** | `non_computable` | `error_reason: no_eligible_target_dates` |

---

## 5. Raw Evaluator Output: Validation Split (Audit Evidence Only)

Validation was executed exactly once immediately after development, with zero code, parameter, or configuration modifications. The raw evaluator output below is preserved **only as audit evidence of the failed execution**.

* **Split Period:** `2026-05-01` through `2026-06-30` (41 regular trading sessions)
* **Expected Ticker-Sessions:** 615 (41 sessions × 15 ETFs)
* **Eligible Ticker-Sessions:** 0 (all excluded due to evaluator defect)
* **DQ-Excluded Ticker-Sessions:** 615 (100.00%)
* **Raw Evaluator Disposition:** **`inconclusive`**
* **Raw Evaluator Step:** `step_2_evidence_sufficiency`
* **Raw Reason:** `sample_gate_failed (events=0, etfs=0, dates=0); data_quality_gate_failed (100.00%)`
* **Governing Research Conclusion:** **`INVALID EXECUTION`** (supersedes raw inconclusive disposition)

### Raw Validation Gate Results (Audit Record)

| Gate | Raw Status | Realized Criteria & Analysis |
|---|---|---|
| **1. Sample Gate** | **FAIL** | 0 events, 0 ETFs, 0 dates. Consequence of evaluator defect, not empirical ETF behavior. |
| **2. Concentration Gate** | **PASS** | $0.00\%$. Degenerate metric on empty set. |
| **3. Data Quality Gate** | **FAIL** | $100.00\%$ excluded. Caused by evaluator timestamp-schema mismatch. |
| **4. Primary Net-Effect Gate** | **FAIL** | CI `non_computable`. Consequence of zero observations. |
| **5. Baseline-Uplift Gate** | **FAIL** | CI `non_computable`. Consequence of zero observations. |
| **6. Cross-ETF Breadth Gate** | **FAIL** | $0.00\%$. Degenerate metric on empty set. |

---

## 6. Root Cause Analysis & Precedence Hierarchy

### Technical Mechanism of the Evaluator Defect

1. **Normalized CSV Schema:** The dataset acquisition adapter ([`write_normalized_bars_csv`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/untitled-worktree/tradex/research/daytrade_momentum/dataset.py#L153-L160)) writes normalized bar CSVs with the locked schema:
   ```text
   bar_start,open,high,low,close,volume
   ```
2. **Reader Loading:** The reader function ([`read_normalized_bars_csv`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/untitled-worktree/tradex/research/daytrade_momentum/dataset.py#L203-L225)) loads these columns into pandas DataFrames and adds a parsed datetime helper `dt_parsed`.
3. **Session Audit Timestamp Resolution:** In [`quality.py:audit_ticker_session`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/untitled-worktree/tradex/research/daytrade_momentum/quality.py#L101-L105) (line 101), the loop resolves the bar timestamp using:
   ```python
   raw_ts = row.get("datetime") or row.get("timestamp") or row.get("t")
   ```
   Notice that `bar_start` was omitted from that lookup tuple.
4. **Fail-Closed Malformed Counting:** Because the DataFrame contains `bar_start` (not `datetime`, `timestamp`, or `t`), `raw_ts` evaluated to `None` for every single row. The evaluator's fail-closed guard:
   ```python
   if raw_ts is None or pd.isna(raw_ts):
       malformed_timestamp_count += 1
       continue
   ```
   caused all 390 bars of every session to be counted as malformed and skipped from grid alignment.
5. **Session Exclusion & Gate Trigger:** With 0 aligned bars, every ticker-session was categorized as `missing_bars = 390` (`excess_missing_bars_390_pct_100.00`), producing an exclusion rate of 100.0% in both development (930 sessions) and validation (615 sessions). Under the raw evaluator logic, this triggered `sample_gate_failed` and `data_quality_gate_failed` under `step_2_evidence_sufficiency`.

### Governing Disposition Precedence: Step 1 (Invalid) vs Step 2 (Inconclusive)

The locked research protocol and disposition hierarchy establish:
* **Step 1 (Invalidity):** A material methodology, implementation, or data-integrity defect renders the study execution **`invalid`**.
* **Step 2 (Evidence Sufficiency Failure):** Valid execution where empirical data fails sample size, breadth, or natural data-quality criteria yields **`inconclusive`**.

Because the data exclusion was caused entirely by an evaluator implementation defect (failure to read the valid, acquired `bar_start` timestamps) rather than genuine market data defects:
* The **governing research disposition** is **`INVALID`**.
* The raw evaluator outputs (`inconclusive / step_2_evidence_sufficiency`) are preserved strictly as audit artifacts of the defective execution.
* **No empirical strategy conclusion** can be drawn: the early-to-late intraday ETF momentum hypothesis is neither supported, rejected, nor meaningfully inconclusive from this run.

### Strict Research Integrity Compliance

Pursuant to Section 15 of the assignment (*Real-Data Integrity Rule After First Access*):
> *"Once real 2026 data has been acquired: the methodology and evaluator are frozen... If a real-world execution defect is discovered: 1. stop; 2. preserve evidence; 3. classify execution as invalid/incomplete as appropriate; 4. report the defect; 5. do not fix and rerun within this task. No data-driven repair is authorized."*

In accordance with this protocol:
* **Zero evaluator code changes were made** after data acquisition began.
* **Zero post-hoc fixes or reruns were performed** in this task.
* The raw evaluator artifacts are preserved byte-for-byte as historical audit evidence.
* Any code correction and re-execution must take place in a separately authorized task approved by Gary.

---

## 7. Holdout Partition Status

* **Status:** **`unread_not_acquired`**
* **Holdout Market Data:**
  * **NOT ACQUIRED**
  * **NOT READ**
  * **NOT PARSED**
  * **NOT EVALUATED**
* **Zero Provider Calls:** Exactly 0 provider calls were made for July or August 2026.
* **Governance Rule:** Because validation did not earn `supported` (the execution was invalid and the raw disposition was inconclusive), holdout access remains strictly prohibited. The holdout partition remains completely sealed and unacquired.

---

## 8. Safe Artifact Bundle Verification

The raw evaluator artifacts in external storage were copied to the repository under [`docs/research/artifacts/DAYTRADE-002C-v1/`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/untitled-worktree/docs/research/artifacts/DAYTRADE-002C-v1/):

* `development/` (14 raw evaluator artifacts; `checksums.sha256` verified)
* `validation/` (14 raw evaluator artifacts; `checksums.sha256` verified)
* `evidence-index.json` (wrapper index explicitly classifying execution validity as `invalid`, `strategy_evidence_usable = false`, and recording raw evaluator dispositions)

The raw evaluator artifacts in `development/` and `validation/` remain byte-for-byte identical to what the frozen evaluator generated, preserving the audit trail. No raw bar CSVs, provider secrets, or request authorization headers exist in tracked repository files.

---

## 9. Research Limitations & Governance Invariants

1. **Evidence Usability:** **Zero usable strategy evidence** was produced by this execution run (`strategy_evidence_usable = false`).
2. **Confidence Cap:** Formally capped at `limited_but_usable_evidence` under the locked spec, but the run itself is classified `invalid`.
3. **Hypothesis Status:** Unresolved. The hypothesis has not received a valid empirical test against 2026 data.
4. **Correction Requirements:** Correcting the timestamp lookup and executing a valid study requires a separate Gary-authorized task.
5. **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.
6. **Zero Production Promotion:** This assignment authorizes zero changes to live trading, automated alerts, scoring, ranking, or order execution.
