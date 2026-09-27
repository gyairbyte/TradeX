# DAYTRADE-002B — Locked Early-to-Late ETF Momentum Evaluator & Pipeline Foundation

This document records the implementation of `DAYTRADE-002B`: the locked research evaluation engine, point-in-time signal and execution pipeline, direction-matched baseline pool, session-date clustered bootstrap, 5-step disposition precedence hierarchy, 23-point holdout security guard, and bounded dataset pipeline foundation for the locked `DAYTRADE-002A` early-to-late intraday ETF momentum study.

> [!IMPORTANT]
> **Zero Network / Zero Real-Data Invariant:**
> DAYTRADE-002B executes **zero market-data provider calls** and accesses no real market data. It contacts neither Alpaca nor any other external API. Real historical data development, validation, and holdout evaluation remain strictly unauthorized until this foundation is independently reviewed and merged.
> `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.

---

## 1. Locked Source of Truth

* **Canonical Specification:** `docs/research/specs/DAYTRADE-002A-v1.json`
* **Locked SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Base Commit:** `74ee008f451d430ec3332587a39b0869534be8e4` (PR #90 merge commit on `main`)
* **Task ID:** `DAYTRADE-002B`
* **Branch:** `antigravity/daytrade-002b-momentum-engine`

The implementation strictly validates this hash at runtime via `load_and_verify_spec()` and fails closed if any parameter, universe symbol, or split date differs.

---

## 2. Four Approved Clarifications Incorporated

1. **Clarification 1 (Realizable Data Quality Boundaries):**
   - For a standard 390-minute regular session on XNYS, 5.0% missing rate corresponds to 19.5 bars. Realizable discrete integer boundaries:
     - 19 missing bars ($19 / 390 = 4.8718\% \le 5.0\%$) $\rightarrow$ **PASS** (not excluded).
     - 20 missing bars ($20 / 390 = 5.1282\% > 5.0\%$) $\rightarrow$ **EXCLUDE**.
   - For duplicates, 1.0% corresponds to 3.9 bars:
     - 3 duplicates ($3 / 390 = 0.7692\% \le 1.0\%$) $\rightarrow$ **PASS** (not excluded).
     - 4 duplicates ($4 / 390 = 1.0256\% > 1.0\%$) $\rightarrow$ **EXCLUDE**.
   - Split-level data quality gate tests the exact 5.0% boundary against total expected sessions ($15 \times \text{expected\_sessions}$).

2. **Clarification 2 (Preceding Close vs. Valid Threshold History):**
   - Signal return denominator $\text{close}(i, \text{prev\_regular}, 15:59)$ requires only a usable, positive, finite 15:59 close from the exact immediately preceding regular XNYS session. It does not require that previous session to have passed all 390-bar DQ checks.
   - In contrast, participating in the rolling 20-session threshold history requires the session to be strictly valid (`session.is_valid is True`) with a computable first-half-hour return.

3. **Clarification 3 (Metric-Specific Bootstrap CI Computability):**
   - `primary_net_return_ci` and `uplift_ci` statuses are evaluated independently.
   - If event mean is computable across all bootstrap replicates but the matched baseline pool for a sampled ETF/direction is empty in any replicate, `uplift_ci.status = "non_computable"` while `primary_net_return_ci.status = "computable"`.
   - Never substitute zero or drop replicates.

4. **Clarification 4 (Complete 23-Point Holdout Access Guard):**
   - Strictly enforced before any holdout data loading or provider client instantiation:
     1. `validation_artifact_dir` exists and is a directory.
     2. `study.json` present.
     3. `spec.lock.json` present.
     4. `freeze.json` present.
     5. `manifest.lock.json` present.
     6. `bootstrap.json` present.
     7. `metrics.json` present.
     8. `data_quality.csv` present.
     9. `report.md` present.
     10. `checksums.sha256` present.
     11. Checksums match current file digests.
     12. Spec SHA matches canonical `DAYTRADE_002A_SPEC_SHA256`.
     13. Manifest provider == `"alpaca"`.
     14. Manifest feed == `"sip"`.
     15. Manifest timeframe == `"1Min"`.
     16. Manifest adjustment == `"split"`.
     17. Manifest calendar == `"XNYS"`.
     18. Manifest timezone == `"America/New_York"`.
     19. Manifest universe matches frozen 15 ETFs in exact order.
     20. Freeze record matches current git commit and file digests.
     21. Validation split achieved exactly `"supported"` disposition.
     22. Validation provenance matches spec hash, code freeze hash, and manifest lineage.
     23. `APPROVED_PRODUCTION_STRATEGIES == ()`.

---

## 3. Package Architecture

The dedicated implementation resides in `tradex/research/daytrade_momentum/`:

```text
tradex/research/daytrade_momentum/
    __init__.py          Public exports and version
    __main__.py          CLI entrypoint (python -m tradex.research.daytrade_momentum)
    spec.py              Locked spec loader and SHA-256 verification
    models.py            Dataclasses and JSON-safe recursive serialization
    calendar.py          XNYS regular-session grid (390 bars), early closes, immediately prior session
    quality.py           Per-ticker-session quality audit and split-level summary
    events.py            First-half-hour signal calculation, rolling 20-session threshold, event classification
    outcomes.py          Gross signed returns, algebraic equivalence, friction models (0/2/5 bps), win rate
    baseline.py          Direction-matched non-event baseline pool (ticker, split, direction) and uplift
    bootstrap.py         Session-date cluster bootstrap (2,000 resamples, seed 20260926, metric-specific CI)
    gates.py             All 6 validation gates and locked 5-step disposition precedence hierarchy
    study.py             Split evaluation orchestrator and guarded holdout access verification
    freeze.py            Evaluation code freeze (git commit SHA, file hashes, tree cleanliness)
    dataset.py           Dataset manifest contract, security bounds, and Alpaca acquisition adapter
    artifacts.py         Deterministic safe artifact bundle writer (14 artifacts) and SHA-256 checksums
    cli.py               Research CLI (verify-spec, freeze, evaluate, build-dataset)
    synthetic.py         Synthetic OHLCV fixtures and controllable session bar generators
```

Test suite resides in:
```text
tests/research/daytrade_momentum/
    conftest.py                  Shared fixtures and temporary output directories
    test_spec.py                 Spec loading, hash verification, frozen universe isolation
    test_calendar.py             Session grid, left-edge timestamps, early closes, prior session
    test_quality.py              Realizable 19 vs 20 missing bars, 3 vs 4 duplicates, split DQ boundary
    test_events.py               First-half-hour return, Clarification 2 prior close, rolling quantile, PIT
    test_outcomes.py             Gross signed return, algebraic equivalence, 0/2/5 bps friction, win rate
    test_baseline.py             Direction-matched pool indexing, uplift, empty bucket non-computable
    test_bootstrap.py            Session-date clustering, simultaneous baseline, Clarification 3 CI status
    test_metrics.py              All 30 locked metrics, multi-signal count/rate, concentration, breadth
    test_gates.py                All 6 validation gates and exact 5-step disposition precedence
    test_dataset_manifest.py     Dataset root security (reject inside repo), manifest contract, dry-run
    test_freeze.py               Code freeze record, clean worktree verification, tamper rejection
    test_holdout_guard.py        All 23 holdout checks, unsupported blocking, pre-holdout history isolation
    test_artifacts.py            Artifact bundle writer (14 files), checksums validation, JSON safety
    test_cli.py                  CLI subcommands (verify-spec, freeze, evaluate, build-dataset)
    test_e2e_pipeline.py         End-to-end evaluation pipeline on development and validation
```

---

## 4. Key Methodology and Locked Semantics

### 4.1 First-Half-Hour Signal Return
$$\text{first\_half\_hour\_return}(i, D) = \frac{\text{close}(i, D, \text{09:59 bar})}{\text{close}(i, \text{previous\_regular\_session}, \text{15:59 bar})} - 1$$
- Known and available at 10:00:00 ET.
- Prohibits all future intraday bars between 10:00 and 15:30.

### 4.2 Rolling 20-Valid-Session 80th Percentile Threshold
- Computed strictly over previous 20 valid completed regular sessions for ticker $i$.
- Current session $D$ excluded.
- Uses `numpy.quantile(abs(history), q=0.80, method='linear')`.
- Zero returns participate via `abs(0.0) = 0.0`.

### 4.3 Classification
- **Event:** $|\text{signal\_return}| \ge \text{threshold}$ and $\text{signal\_return} \ne 0$:
  - `LONG` if $\text{signal\_return} > 0$
  - `SHORT` if $\text{signal\_return} < 0$
- **Baseline Candidate (Non-Event):** $|\text{signal\_return}| < \text{threshold}$ and $\text{signal\_return} \ne 0$:
  - Direction matches sign of $\text{signal\_return}$.

### 4.4 Forward Execution and Friction
- Entry at 15:30:00 ET open; Exit at 15:59:00 ET close (representing $[15:59, 16:00)$ interval).
- Official closing auction price used: `False`.
- Primary net return: $\text{net} = \text{gross} - 0.0004$ (2 bps/side = 4 bps round-trip).
- Sensitivities: 0 bps and 5 bps/side (10 bps round-trip).

### 4.5 Direction-Matched Baseline & Uplift
- Pool indexed by $(\text{ticker}, \text{split}, \text{direction})$.
- $\text{uplift} = \text{event\_net\_return} - \text{mean}(\text{matched non-events})$.
- Non-computable if baseline bucket is empty; never substitute zero.

### 4.6 Session-Date Clustered Bootstrap
- Clustered on `session_date` (all 15 ETF observations on that date resampled together).
- Multiplicity preserved when a date is drawn multiple times.
- Baseline recomputed inside each replicate.
- Metric-specific non-computability per Clarification 3.

### 4.7 5-Step Disposition Precedence Hierarchy
- **Step 1 (Invalidity):** Integrity defect $\rightarrow$ `"invalid"`
- **Step 2 (Evidence Sufficiency):** Sample gate, concentration gate, or DQ gate fails $\rightarrow$ `"inconclusive"`
- **Step 3 (Directional Hypothesis Failure):** Primary net mean $\le 0$, mean uplift $\le 0$, or breadth $< 60\%$ $\rightarrow$ `"rejected"`
- **Step 4 (Statistical Uncertainty):** Positive means and breadth pass, but CI lower bound $\le 0$ or CI non-computable $\rightarrow$ `"inconclusive"`
- **Step 5 (Support):** All 6 gates pass simultaneously $\rightarrow$ `"supported"`

---

## 5. PR #91 Final Corrections Incorporated

1. **Threshold History Walkback Across Earlier Authorized Splits:**
   - Evaluator walks back across split boundaries to acquire exactly the previous 20 valid completed regular sessions:
     - Development history walks back to include the `2025-12-31` context anchor date and 20 warmup sessions (`2025-12-01` to `2025-12-31`).
     - Validation history walks back into development history (`2025-12-31` to validation end).
     - Holdout history walks back into validation history (`2025-12-31` to holdout end).
   - Prevents threshold distortion at split boundaries while maintaining strict temporal isolation.

2. **Canonical Dataset Directory Layout:**
   - Standardized to `preholdout/manifest.lock.json` and `holdout/manifest.lock.json` with sibling `bars/{ticker}.csv`.
   - Prohibits placing dataset roots within the repository tree.

3. **Strict Code Freeze Verification:**
   - `verify_freeze_state()` cryptographically binds to manifest SHA-256, verifies git commit matches repository HEAD, enforces clean worktree status, and checks digests of 14 core evaluation files.
   - CLI `cmd_freeze` requires explicit `--manifest` or `--dataset-root`.

4. **Fail-Closed Dataset Acquisition & Normalization:**
   - Enforces 100-page limit and max 1 retry for pagination.
   - Discards unparseable timestamps fail-closed without fabricating artificial sessions.

---

## 6. Verification Results

- **New Test Suite:** `uv run pytest tests/research/daytrade_momentum -q`
  - **80 passed** in 234.29s (15 test modules)
- **Regression Suites:** `uv run pytest tests/research/daytrade_002a/test_spec.py tests/research/daytrade_reversal tests/research/daytrade_001b/test_spec.py tests/research/daytrade_mvp tests/research/intraday_dataset tests/product/test_mvp_arch_001.py -q`
  - **266 passed, 1 warning** in 406.37s
- **Lint Check:** `uv run ruff check tests scripts tradex/research/daytrade_momentum tradex/research/intraday_dataset`
  - **All checks passed!** Zero errors.
- **Git Diff:** `git diff --check` passed cleanly.

