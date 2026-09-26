# DAYTRADE-001C1 — Locked Reversal Study Engine & Data Pipeline Foundation

This document records the implementation of `DAYTRADE-001C1`: the deterministic research engine, point-in-time forward outcome pipeline, joint cluster bootstrap, 5-step disposition precedence hierarchy, holdout security guard, and bounded dataset pipeline foundation for the locked `DAYTRADE-001B` 1-minute extreme downside reversal study.

> [!IMPORTANT]
> **Zero Network / Zero Real-Data Invariant:**
> DAYTRADE-001C1 executes **zero market-data provider calls** and accesses no real market data. It contacts neither Alpaca nor any other external API. Real historical data development, validation, and holdout evaluation remain strictly unauthorized until this foundation is independently reviewed and merged.
> `APPROVED_PRODUCTION_STRATEGIES == ()` remains preserved.

---

## 1. Locked Source of Truth

* **Canonical Specification:** `docs/research/specs/DAYTRADE-001B-v1.json`
* **Locked SHA-256:** `0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620`
* **Base Commit:** `88de1eaf6eda321b5c163e58ec41629394dc3fcc` (PR #87 merge commit on `main`)
* **Task ID:** `DAYTRADE-001C1`
* **Branch:** `antigravity/daytrade-001c1-reversal-engine`

The implementation strictly validates this hash at runtime via `load_and_verify_spec()` and fails closed if any parameter, universe symbol, or split date differs.

---

## 2. Package Architecture

The dedicated implementation resides in `tradex/research/daytrade_reversal/`:

```text
tradex/research/daytrade_reversal/
    __init__.py          Public exports and version
    __main__.py          CLI entrypoint (python -m tradex.research.daytrade_reversal)
    spec.py              Locked spec loader and SHA-256 verification
    models.py            Dataclasses and JSON-safe recursive serialization
    calendar.py          XNYS regular-session grid (390 bars) and early-close exclusion
    quality.py           Per-ticker-session quality audit (missing, duplicate, malformed)
    events.py            Rolling 20-valid-prior-session threshold and event detection
    outcomes.py          Point-in-time entry/exit return calculations and friction deduction
    baseline.py          Matched non-event baseline pool (arithmetic mean) and uplift
    bootstrap.py         Deterministic joint cluster bootstrap (2,000 resamples, seed 20260925)
    gates.py             Validation gates evaluator and 5-step disposition precedence
    study.py             Split evaluation orchestrator and guarded holdout evaluator
    freeze.py            Evaluation code freeze (git commit SHA, file hashes, cleanliness)
    dataset.py           Dataset manifest contract, security bounds, and Alpaca adapter
    artifacts.py         Deterministic artifact bundle writer and SHA-256 checksums
    cli.py               Narrow research CLI (verify-spec, freeze, evaluate, build-dataset)
    synthetic.py         Synthetic OHLCV fixtures covering all 30 locked test scenarios
```

Corresponding test suite lives in:
```text
tests/research/daytrade_reversal/
    conftest.py                  Shared fixtures and temp output directories
    test_spec.py                 Spec loading and hash verification tests
    test_calendar.py             Session grid and early-close exclusion tests
    test_quality.py              Data quality and split exclusion gate tests
    test_events.py               20-session rolling quantile and overlap tests
    test_outcomes.py             Next-bar open execution and friction tests
    test_baseline.py             Baseline matching and uplift tests
    test_bootstrap.py            Cluster bootstrap determinism and failure tests
    test_gates.py                Gates and 5-step precedence tests
    test_holdout_guard.py        Holdout loader isolation and security tests
    test_dataset_manifest.py     Manifest contract, secrets prohibition, pagination tests
    test_synthetic_scenarios.py  Direct tests for all 30 locked Section 26 scenarios
    test_cli.py                  CLI subcommands and artifact generation tests
```

---

## 3. Data Flow and Information Availability

```
Raw OHLCV Bars
       ↓
[ calendar.py: XNYS Session Grid ] (09:30-16:00 ET; 390 expected 1-min bars; early close excluded)
       ↓
[ quality.py: Session Audit ] (Missing > 5%, Duplicate > 1%, Malformed -> exclude session)
       ↓
[ events.py: 20 Prior Valid Sessions ] (Exclude current session D; exclude 09:30; window 09:31-15:54)
       ↓
[ events.py: Empirical Quantile ] threshold_D = numpy.quantile(..., q=0.001, method="linear")
       ↓
[ events.py: Signal Detection ] return_t <= threshold_D (at available_at = t + 1 min)
       ↓
[ outcomes.py: PIT Execution ] Entry at open[t+1]; Exits at close[t+1], close[t+2], close[t+5]
       ↓
[ baseline.py: Matched Baseline Pool ] Non-events: same ticker + minute + split + valid horizon
       ↓
[ bootstrap.py: Joint Cluster Bootstrap ] Resample (ticker, session_date); recompute events & baseline
       ↓
[ gates.py: 5-Step Precedence ] invalid -> inconclusive -> rejected -> inconclusive -> supported
       ↓
[ artifacts.py: Safe Artifact Bundle ] All JSON-safe, report.md, checksums.sha256
```

---

## 4. Key Methodology and Locked Semantics

### 4.1 Point-in-Time Semantics
- A 1-minute bar starting at $t$ is completed and available only at `available_at = t + 1 minute`.
- The extreme-move event is detected at `available_at`.
- Hypothetical execution occurs at the **open of minute $t+1$**.
- Execution at the close of minute $t$ or within minute $t$ is strictly prohibited.
- Primary 1-minute gross return: $(close_{t+1} - open_{t+1}) / open_{t+1}$.
- Secondary returns:
  - 2-minute: $(close_{t+2} - open_{t+1}) / open_{t+1}$
  - 5-minute: $(close_{t+5} - open_{t+1}) / open_{t+1}$
- Forward outcomes must never cross 16:00 session close or split boundaries.

### 4.2 Data Quality Semantics
- Evaluated per ticker-session before event identification.
- Normal NYSE session expects 390 regular 1-minute bars.
- Missing bar rate $> 5.0\%$ ($> 19$ missing bars) excludes the ticker-session.
- Duplicate bar rate $> 1.0\%$ ($> 3$ duplicate bars) excludes the ticker-session.
- Malformed timestamps fail closed for affected rows and are recorded.
- Synthetic interpolation or filling of missing bars is prohibited.
- Split-level gate: if $> 5.0\%$ of ticker-sessions in a split are excluded for data-quality reasons, the split cannot be supported (Step 2 `inconclusive`).

### 4.3 Quantile Implementation Method
- Quantile calculation uses:
  ```python
  numpy.quantile(returns, q=0.001, method="linear")
  ```
- Uses only completed within-session 1-minute returns with bar starts `09:31` through `15:54` ET from the previous 20 valid regular sessions.
- Excludes the 09:30 opening return.
- Current session $D$ is excluded from its own threshold.

### 4.4 Baseline Reference Mechanics
- For each event and horizon:
  $$\text{baseline\_reference\_return} = \frac{1}{|B|} \sum_{b \in B} R_b$$
  where $B$ is the set of qualifying non-event observations for the same ticker, same minute-of-day, same split, and complete forward horizon.
- Event uplift:
  $$\text{uplift} = R_{\text{event}} - \text{baseline\_reference\_return}$$
- Primary gate evaluates 1-minute return under locked 2 bps/side ($0.0004$ round-trip) friction.
- If an event has no qualifying non-events in its bucket, matched baseline and uplift are explicitly `None` (non-computable).

### 4.5 Overlapping Events Definition
- Canonical analysis interval: maximum 5-minute forward window `[t+1 open, t+5 close]`.
- An event is classified as overlapping if its analysis interval intersects another event's analysis interval.
- Reports `overlapping_event_count` and `overlapping_event_rate = overlapping_event_count / event_count`.
- Distinguishes same-ticker overlap vs cross-ticker simultaneous/overlapping events.
- Overlap is descriptive only and does not filter trades or alter gates.

### 4.6 Joint Cluster Bootstrap Mechanics
- Cluster variable: `(ticker, session_date)`.
- Replications: `2,000`.
- Random seed: `20260925`.
- In each replicate:
  1. Resample ticker-session clusters with replacement.
  2. Retain events and non-events belonging to the sampled clusters.
  3. Recompute primary event mean return.
  4. Recompute matched baseline pool and uplift jointly using resampled non-events (baseline is never held fixed).
- Non-computable replicate handling:
  - If any replicate cannot compute event mean or baseline uplift, do not substitute zero, do not drop the replicate, do not reduce the denominator.
  - Set CI status to `non_computable` and bounds to `None`.
  - In the disposition engine, a non-computable CI resolves to `inconclusive` (Step 4).

### 4.7 Deterministic 5-Step Disposition Precedence
1. **Step 1 — `invalid`:** Methodological or integrity defects (lookahead bias, split contamination, premature holdout access, corrupt inputs).
2. **Step 2 — `inconclusive`:** Evidence sufficiency failures ($< 300$ events, $< 15$ tickers, $> 15.0\%$ concentration, $> 5.0\%$ excluded sessions).
3. **Step 3 — `rejected`:** Directional failures (mean primary net $\le 0$, mean uplift $\le 0$, or ticker breadth $< 60.0\%$).
4. **Step 4 — `inconclusive`:** Statistical uncertainty (positive means and passing breadth, but primary net 95% CI lower bound $\le 0$ or uplift 95% CI lower bound $\le 0$, or non-computable CI).
5. **Step 5 — `supported`:** All five locked gates pass simultaneously.

### 4.8 Holdout Protection Guard
- Holdout evaluation (`load_and_evaluate_holdout`) requires proof that:
  1. Validation was executed using the frozen evaluator;
  2. Validation disposition is strictly `supported`;
  3. Spec SHA and manifest SHA are verified;
  4. Current git HEAD and code freeze record match.
- If any prerequisite fails, the holdout loader callback is **never invoked**.

### 4.9 Dataset Safety Bounds
- `--dataset-root` must resolve outside the tracked Git repository/worktree (in-repo destinations fail closed).
- Hard limit of 100 pages per calendar month chunk (`max_pages_per_calendar_month_chunk = 100`). Exceeding this limit terminates fail-closed.
- Maximum 1 retry per failed page.
- Manifests and artifacts strictly prohibit API keys, authorization headers, environment secrets, and raw response bodies.

---

## 5. Future DAYTRADE-001C2 Execution Sequence

When DAYTRADE-001C2 is separately authorized by Gary Yang, the execution sequence will be:

1. **Verify Spec:**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal verify-spec
   ```
2. **Build Private Dataset (outside repo):**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal build-dataset --dataset-root ~/.tradex/research/daytrade_001b/
   ```
3. **Freeze Evaluator Code:**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal freeze --output ~/.tradex/research/daytrade_001b/freeze/
   ```
4. **Evaluate Development Split (diagnostic):**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal evaluate --split development --dataset-root ~/.tradex/research/daytrade_001b/ --output ~/.tradex/research/daytrade_001b/results/dev/
   ```
5. **Evaluate Validation Split (formal gate):**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal evaluate --split validation --dataset-root ~/.tradex/research/daytrade_001b/ --output ~/.tradex/research/daytrade_001b/results/val/
   ```
6. **Conditional Holdout Evaluation (only if validation == supported):**
   ```powershell
   uv run python -m tradex.research.daytrade_reversal evaluate --split holdout --dataset-root ~/.tradex/research/daytrade_001b/ --validation-artifact-dir ~/.tradex/research/daytrade_001b/results/val/ --output ~/.tradex/research/daytrade_001b/results/holdout/
   ```

---

## 6. Limitations and Governance

- **Research-Only:** This package implements evaluation mechanics only. It contains no production signals, scores, indicators, weights, or alerts.
- **Survivorship Limitation:** Using the 2026 Dow 30 snapshot on 2025 historical data introduces survivorship and selection limitations; maximum future evidence confidence remains `limited_but_usable_evidence`.
- **Zero Real Data Evaluated:** No real market data has been fetched, parsed, or evaluated.
- **Production Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.
