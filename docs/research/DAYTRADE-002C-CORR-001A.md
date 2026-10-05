# DAYTRADE-002C-CORR-001A — Timestamp-Schema Integration Fix & Corrected Re-execution Readiness

> [!IMPORTANT]
> **Executive Summary & Governance Status**
>
> * **Task ID:** `DAYTRADE-002C-CORR-001A`
> * **Title:** Fix DAYTRADE-002 normalized timestamp-schema integration defect and establish corrected re-execution readiness
> * **Status:** `correction_implemented_pending_independent_review`
> * **Corrected Re-execution Authorized:** `false` (strictly unauthorized; requires separate Gary authorization in task `DAYTRADE-002C-CORR-001B`)
> * **Holdout Status:** `unread_not_acquired` (zero provider calls; holdout strictly unread and unacquired)
> * **Real Market-Data Access in this Task:** `NONE` (zero live provider requests, zero private dataset reads)
> * **Production Promotion Eligible:** `false`
> * **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved
> * **Starting Main Commit SHA:** `70d41000bb8ce17e3fca2300ac3dc8e25df5f186`
> * **Affected Historical Execution SHA:** `774b37efe883233d0c3f2a888e37aebf0851d347` (merge commit of PR #91 / `DAYTRADE-002B`)
> * **Canonical Specification SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
> * **Preholdout Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`

---

## 1. Defect Description & Mechanism

### 1.1 Evaluator Integration Disconnect

The study execution defect that rendered `DAYTRADE-002C` invalid was located at the boundary between canonical bar persistence/loading and data-quality session auditing:

1. **Canonical Normalized Writer:**
   [`tradex/research/daytrade_momentum/dataset.py::write_normalized_bars_csv()`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tradex/research/daytrade_momentum/dataset.py#L153-L201)
   persists exactly the locked 6-column CSV schema:
   ```text
   bar_start,open,high,low,close,volume
   ```
   with UTC ISO-8601 timestamps (e.g. `2026-01-02T14:30:00Z`).

2. **Canonical Normalized Reader:**
   [`tradex/research/daytrade_momentum/dataset.py::read_normalized_bars_csv()`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tradex/research/daytrade_momentum/dataset.py#L203-L225)
   validates that exact 6-column header and adds an internal parsed helper column:
   ```python
   parsed_ts = pd.to_datetime(df["bar_start"], utc=True, errors="coerce")
   ...
   df["dt_parsed"] = parsed_ts
   ```
   yielding DataFrame columns:
   `["bar_start", "open", "high", "low", "close", "volume", "dt_parsed"]`.

3. **Data-Quality Session Auditor:**
   Prior to this correction, [`tradex/research/daytrade_momentum/quality.py::audit_ticker_session()`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tradex/research/daytrade_momentum/quality.py#L101-L105)
   resolved bar timestamps using only:
   ```python
   raw_ts = row.get("datetime") or row.get("timestamp") or row.get("t")
   ```
   It did **NOT** consume either `dt_parsed` or `bar_start`.

### 1.2 Impact on Historical Execution DAYTRADE-002C

Because canonical persisted CSV files contained `bar_start` and the reader added `dt_parsed`, none of `datetime`, `timestamp`, or `t` existed in real loaded bar DataFrames. Consequently:
- `raw_ts` evaluated to `None` for every single bar row;
- the auditor's fail-closed guard `if raw_ts is None or pd.isna(raw_ts): malformed_timestamp_count += 1; continue` classified 100% of bars (390 per session) as malformed timestamps;
- zero bars were aligned with the XNYS regular-session grid, categorizing every ticker-session as having 390 missing bars (100.0% missing rate);
- 100% of ticker-sessions were excluded (930 development sessions across 62 trading dates; 615 validation sessions across 41 trading dates);
- the raw evaluator mechanically emitted `INCONCLUSIVE / step_2_evidence_sufficiency`.

As formally recorded in [`docs/research/DAYTRADE-002C-RESULTS.md`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/docs/research/DAYTRADE-002C-RESULTS.md), the governing research classification of that execution was **`INVALID`** (`invalidity_category = evaluator_implementation_defect`). Zero valid strategy evidence was produced.

---

## 2. Correction Implementation

### 2.1 Exact Code Changes

In [`tradex/research/daytrade_momentum/quality.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tradex/research/daytrade_momentum/quality.py):

1. **Defined Locked Candidate Precedence Tuple:**
   ```python
   TIMESTAMP_CANDIDATE_COLUMNS: tuple[str, ...] = (
       "dt_parsed",
       "bar_start",
       "datetime",
       "timestamp",
       "t",
   )
   ```

2. **Implemented Explicit Candidate Extractor & Resolver (`_resolve_bar_timestamp`):**
   - Candidate discovery checks existence in `pd.Series`, `dict`, or object attributes without silent boolean coercion.
   - Evaluates in strict precedence:
     1. `dt_parsed`
     2. `bar_start`
     3. `datetime`
     4. `timestamp`
     5. `t`
   - Verifies each candidate: exists, is not `None`, is not `pd.isna()`.
   - Once a non-null candidate is selected, normalizes it to a timezone-aware UTC `datetime.datetime` exactly once.
   - If a candidate is malformed (e.g. invalid string, unparseable date), fails closed by returning `None` (counted as `malformed_timestamp_count += 1`). It does **not** silently fall back to a lower-precedence candidate.
   - Arbitrary unknown columns (e.g. `time`, `date`, `ts`) are strictly rejected.

3. **Integrated Resolver into `audit_ticker_session`:**
   Replaced the defective `row.get("datetime") or ...` lookup with:
   ```python
   dt = _resolve_bar_timestamp(row)
   if dt is None:
       malformed_timestamp_count += 1
       continue
   ```

### 2.2 Behaviors Deliberately Unchanged

To preserve complete research integrity and prevent methodology drift, the following remain strictly unchanged:
- **Locked Specification:** `docs/research/specs/DAYTRADE-002A-v1.json` is byte-for-byte untouched (SHA-256 `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`).
- **Universe:** Fixed 15-ETF universe (`XLK`, `XLV`, `XLF`, `XLY`, `XLP`, `XLE`, `XLI`, `XLB`, `XLU`, `XLRE`, `XLC`, `SPY`, `QQQ`, `IWM`, `DIA`).
- **Date Ranges:** Context anchor `2025-12-31`, warmup `2026-01-02`–`2026-01-30`, development `2026-02-02`–`2026-04-30`, validation `2026-05-01`–`2026-06-30`, holdout `2026-07-01`–`2026-08-31`.
- **Trading Rules & Endpoints:** Signal formula (first half-hour return relative to previous session 15:59 close), rolling 20-session threshold, 80th percentile cutoff, entry at 15:30 open, exit at 15:59 close.
- **Cost Model & Baselines:** Primary net return at 2 bps friction, matched non-event baselines, stationary block bootstrap with seed `20260901`, 95% confidence intervals.
- **Data Quality Thresholds:** Realizable session thresholds (19 missing pass / 20 missing exclude; 3 duplicates pass / 4 duplicates exclude; 5.0% split exclusion gate).
- **Timezone & Calendar:** Exchange calendar `XNYS`, timezone `America/New_York`, 390-minute regular-session grid.
- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.

---

## 3. Empirical Verification & Regression Evidence

### 3.1 Deterministic Reproduction of Defect

Before implementing the fix, a deterministic regression test executing the real production serialization path:
```text
generate_synthetic_session_bars()
    -> write_normalized_bars_csv()
    -> read_normalized_bars_csv()
    -> audit_ticker_session()
```
reproduced the exact failure mode observed in DAYTRADE-002C:
```text
total_bars = 0
missing_bars = 390
malformed_timestamp_count = 390
duplicate_bars = 0
excluded = True
session.is_valid = False
```

### 3.2 Corrected Verification Results

With the correction applied, targeted test suites confirm full compatibility:

1. **Canonical Round-Trip Regression ([`test_canonical_roundtrip_persisted_schema_regression`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L187)):**
   - `report.total_bars == 390`
   - `report.missing_bars == 0`
   - `report.malformed_timestamp_count == 0`
   - `report.duplicate_bars == 0`
   - `report.excluded is False`
   - `session.is_valid is True`
   - `len(session.bars) == 390`
   - `session.get_09_59_close() == 105.50` (point-in-time signal bar preserved)
   - `session.get_15_30_open() == 106.25` (point-in-time entry bar preserved)
   - `session.get_15_59_close() == 108.00` (point-in-time exit bar preserved)

2. **Direct `bar_start` Compatibility ([`test_direct_bar_start_compatibility`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L248)):**
   DataFrames with only the persisted schema (`bar_start`) audit cleanly with 390 valid bars.

3. **`dt_parsed` Precedence & Fallback ([`test_dt_parsed_precedence_over_bar_start`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L279)):**
   `dt_parsed` is consumed deterministically when present; falls back cleanly to `bar_start` when `dt_parsed` is `None` or `pd.NaT`.

4. **Full Precedence Hierarchy & Fail-Closed Guard ([`test_timestamp_candidate_precedence_full_hierarchy`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L302)):**
   Precedence `dt_parsed > bar_start > datetime > timestamp > t` is enforced; malformed higher candidates fail closed; unknown columns are rejected.

5. **Existing In-Memory Alias Compatibility ([`test_existing_alias_compatibility`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L338)):**
   Synthetic DataFrames using `datetime`, `timestamp`, or `t` continue to audit as 390 valid bars.

6. **Round-Trip Boundary Invariants ([`test_canonical_roundtrip_missing_bars_boundary`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L365), [`test_canonical_roundtrip_duplicate_bars_boundary`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/fix_timestamp_schema_integration/tests/research/daytrade_momentum/test_quality.py#L396)):**
   - 19 missing bars -> `PASS` (`missing_rate_pct = 4.87%`)
   - 20 missing bars -> `EXCLUDE` (`missing_rate_pct = 5.13%`)
   - 3 duplicate bars -> `PASS` (`duplicate_rate_pct = 0.77%`)
   - 4 duplicate bars -> `EXCLUDE` (`duplicate_rate_pct = 1.03%`)

---

## 4. Research-Integrity Assessment & Re-execution Readiness

### 4.1 Assessment of Prior Run

The initial execution of `DAYTRADE-002C` on commit `774b37efe883233d0c3f2a888e37aebf0851d347` produced **NO VALID STRATEGY EVIDENCE**. Because 100% of observations were blocked at ingestion by the schema mismatch, no empirical return, event count, breadth, or confidence interval was observed.

Under research governance:
- The historical artifacts in `docs/research/artifacts/DAYTRADE-002C-v1/` remain immutable audit evidence of that invalid execution.
- No strategy hypothesis was confirmed, rejected, or meaningfully evaluated.

### 4.2 Conditions for a Separately Authorized Corrected Re-execution

A corrected re-execution of the **SAME** preholdout dataset may be considered methodologically permissible **ONLY** if separately authorized by Gary and all ten of the following conditions remain true:

1. **Correction Scope Boundary:** The correction is strictly limited to the predetermined `bar_start`/`dt_parsed` timestamp-schema compatibility defect;
2. **No Methodology Changes:** Zero signal, threshold, calendar, universe, baseline, bootstrap, cost, or gate parameter changes occur;
3. **Spec Immutability:** The locked specification JSON (`DAYTRADE-002A-v1.json`) remains byte-for-byte identical (SHA-256 `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`);
4. **Dataset Byte Reuse:** The exact existing preholdout dataset bytes in `~/.tradex/research/daytrade_002_v1/preholdout/` are reused;
5. **Manifest & Digest Verification:** The existing preholdout manifest SHA-256 (`1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`) and all 15 source bar file digests are reverified before execution;
6. **No Market Data Reacquisition:** Zero market-data provider requests or re-acquisitions occur;
7. **Freeze at Corrected Code SHA:** A new freeze record binds the evaluator at the corrected merged commit SHA;
8. **Separate Execution Task:** Development and validation are re-executed under a separately authorized task (expected `DAYTRADE-002C-CORR-001B`);
9. **Single-Execution Invariant:** Corrected development and validation are each executed exactly once;
10. **Holdout Quarantine:** The holdout split remains strictly unread and unacquired unless validation independently earns `supported` and a subsequent Gary authorization explicitly permits holdout access.

> [!CAUTION]
> **Re-execution Authorization Status**
>
> Corrected re-execution is **NOT** authorized by this document or PR.
> `corrected_reexecution_authorized = false`.
> The implementation in this PR prepares TradeX for independent review. The empirical rerun will take place only after this PR is reviewed, approved, and merged to `main`.
