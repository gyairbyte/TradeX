# SHORT-001: Short-term market-context disposition

## 1. Decision summary

`SHORT-001` is **Inconclusive (Outcome I)** after the v2 ingestion remediation and rerun.

The engineering and research infrastructure is complete and verified: point-in-time market-regime and relative-strength context, candidate policies, development/validation candidate selection, untouched holdout event-study gate, and paired executable-backtest gate all exist and work as designed.

The locked v1 real-data attempt (PR #38) failed data ingestion with `23` hard-invalid OHLC rows across `19` symbols, so it was **Outcome E — Invalid study**. The v2 rerun used the locked `short-001-hard-invalid-row-exclusion-v2` ingestion policy to drop those `23` rows (`0.028%` of `82,035`) while preserving the complete 45-symbol panel and recording deterministic audit evidence. The unchanged evaluation then produced no candidate that passed the predefined development/validation criteria (`selected_policy: null`; `selection_reason: "no policy passed development and validation criteria"`).

No production score, weight, threshold, rank, eligibility, alert, or screener behavior was changed. No context policy is exposed in production.

## 2. Original hypothesis

Adding point-in-time market-regime and relative-strength filters to the existing short-term score improves the risk-adjusted short-term outcomes of eligible setups without unacceptable drawdown or single-ticker dependence.

The candidate filters were:

- `market_rs` — broad market bullish regime and positive market relative strength.
- `market_sector_rs` — broad market and sector bullish regime and positive sector relative strength.

## 3. Implemented research infrastructure

The following is in place and covered by focused tests under `tests/market/` and `tests/research/short_context/`:

- `tradex/market/context.py` computes point-in-time market and sector context using only bars at or before the signal timestamp.
- `tradex/market/models.py` defines `ShortContextPolicy` (`off`, `market_rs`, `market_sector_rs`) and `ShortTermMarketContext`.
- `tradex/signals/short_term.py` accepts optional `context` and `context_policy` kwargs, preserves the existing numeric `score` as `base_score`, and adds `context_eligible`, `context_status`, `context_reasons`, and `market_context`. The default `context_policy` is `OFF`.
- `tradex/research/short_context/` provides the full study pipeline:
  - `spec.py` — locked JSON spec validation and loading.
  - `events.py` — point-in-time event generation with forward returns and explicit split membership.
  - `comparison.py` — development/validation candidate selection and holdout event-study gate.
  - `backtest.py` — per-ticker paired executable backtests over the untouched holdout.
  - `report.py` — deterministic artifact generation with SHA-256 locks.
  - `cli.py` — `snapshot` and `evaluate` subcommands.
- `tests/research/short_context/conftest.py` contains the canonical deterministic synthetic fixture.

## 4. Production boundary

The production path does **not** use a context policy:

- `tradex/screener/engine.py` maps `short` to `tradex.signals.short_term.score` and calls it with no `context` or `context_policy` argument, so the default `ShortContextPolicy.OFF` applies.
- The Streamlit dashboard does not expose a `SHORT-001` context toggle.
- The watcher, alerts, confluence, and ranking modules do not reference `ShortContextPolicy`, `context_policy`, or `short_context`.
- No user setting, saved weights file, or persistence schema silently enables `SHORT-001`.
- `short_term.score(..., context=..., context_policy=...)` is available for research use only.

## 5. Predefined candidate-selection criteria

Candidate selection in `tradex/research/short_context/comparison.py::select_candidate` uses **only** the `development` and `validation` splits. The `holdout` split is explicitly dropped first.

For each `market_rs` and `market_sector_rs` policy the pipeline computes:

1. Development mean net return (primary horizon and slippage) must be **strictly greater** than the development baseline.
2. Validation `event_count` must be at least `minimum_validation_events`.
3. Validation `retention_pct` must be at least `minimum_event_retention_pct`.
4. Validation `coverage_pct` must be at least `minimum_ticker_coverage_pct`.
5. Validation mean net return must be **strictly greater** than validation baseline.
6. Validation equal-weighted per-ticker mean must be **strictly greater** than baseline.
7. Validation median net return must be **greater than or equal** to baseline.
8. Validation positive-return rate must be within 2 percentage points of baseline (i.e., not degraded by more than 2 pp).

If multiple policies qualify, the policy with the largest validation equal-weighted per-ticker mean improvement wins; ties prefer the simpler `market_rs` policy.

Default spec values:

- `minimum_validation_events`: same as `minimum_holdout_events` (100).
- `minimum_event_retention_pct`: 25.0
- `minimum_ticker_coverage_pct`: 50.0
- `baseline_score_threshold`: 40
- `primary_horizon_bars`: 3
- `primary_slippage_bps`: 5.0
- `horizons`: `(1, 3, 5)`
- `slippage_scenarios_bps`: `(0.0, 5.0, 10.0)`
- `commission_bps`: 0.0

## 6. Event-study holdout gate

`tradex/research/short_context/comparison.py::_holdout_failures` enforces the holdout event-study criteria on the **selected** policy using only the untouched `holdout` split:

1. Candidate `event_count` >= `minimum_holdout_events` (default 100).
2. Candidate `unique_tickers` >= `minimum_holdout_tickers` (default 10).
3. Candidate `retention_pct` >= `minimum_event_retention_pct` (default 25.0%).
4. Candidate `coverage_pct` >= `minimum_ticker_coverage_pct` (default 50.0%).
5. Candidate mean net return **>** baseline mean.
6. Candidate equal-weighted per-ticker mean **>** baseline.
7. Candidate median net return **>=** baseline median.
8. Candidate positive-return rate **not** more than 2 percentage points below baseline.
9. Improvement must not be produced by only one ticker (`candidate.unique_tickers == 1` is rejected).
10. At least half of represented holdout tickers must have candidate per-ticker mean >= baseline per-ticker mean.

If any check fails, the gate returns `passed=false` with the corresponding `failure_reasons`.

## 7. Paired executable-backtest gate

`tradex/research/short_context/backtest.py::_backtest_gate_failures` evaluates the holdout using the production backtest engine:

1. Candidate backtest results exist and are non-empty.
2. Baseline backtest results exist and are non-empty.
3. At least one ticker appears in both baseline and candidate results.
4. Candidate `total_trades` is non-zero for at least one overlapping ticker.
5. Improvement must not be produced by only one ticker (more than one overlapping ticker with candidate trades).
6. Median candidate `expectancy_pct` across eligible tickers is **strictly greater** than median baseline `expectancy_pct`.
7. Mean candidate `expectancy_pct` across eligible tickers is **strictly greater** than mean baseline `expectancy_pct`.
8. Median candidate `total_return_pct` is **not lower** than median baseline `total_return_pct`.
9. Median candidate `max_drawdown_pct` is not worse than baseline by more than 2 percentage points (`median_dd_candidate >= median_dd_baseline - 2.0`).

The gate is `passed` only when `selected_policy` is not `None` and the `failure_reasons` list is empty.

A dual-gate promotion requires both the event-study gate and the paired-backtest gate to pass. Passing the gates makes a policy **eligible for consideration**; it does not authorize production integration.

## 8. Synthetic verification result

A deterministic end-to-end rerun was executed using the synthetic fixture pattern from `tests/research/short_context/conftest.py`.

- Command: `uv run python /tmp/run_short_context_synthetic.py` (temp harness; not committed).
- Source: one target (`AAPL`), one market proxy (`SPY`), one sector proxy (`XLK`), 252 synthetic daily bars, splits `development 2020-01-01–2020-06-30`, `validation 2020-07-01–2020-09-30`, `holdout 2020-10-01–2020-12-31`.
- Reduced minimums were used for the synthetic rerun so a candidate could be selected and the gates could be fully exercised. These values (`minimum_holdout_events=5`, `minimum_holdout_tickers=1`, `minimum_event_retention_pct=10.0`, `minimum_ticker_coverage_pct=10.0`) are the pre-existing values in the canonical repository fixture (`tests/research/short_context/conftest.py`) and were reused unchanged; they were not selected or tuned after observing this rerun.

Outputs were byte-identical across two consecutive runs with the same inputs.

### 8.1 Selected policy

- `selected_policy`: `market_sector_rs`
- `selection_reason`: selected by largest validation equal-weighted per-ticker mean improvement; tie-break prefers `market_rs`

### 8.2 Event-study holdout gate

- `passed`: `false`
- Failure reasons:
  - holdout mean return not greater than baseline
  - holdout equal-weighted per-ticker mean not greater than baseline
  - holdout median return lower than baseline
  - holdout positive-return rate degraded more than 2 percentage points
  - improvement produced by only one ticker
  - fewer than half of represented holdout tickers improved (0/1)

### 8.3 Paired executable-backtest gate

- `passed`: `false`
- Failure reasons:
  - improvement produced by only one ticker
  - median candidate total return lower than baseline

### 8.4 Key counts

- Split event counts: development 50 baseline / 15 candidate (`market_sector_rs`), validation 61 baseline / 23 candidate, holdout 49 baseline / 16 candidate.
- Holdout ticker count: 1 (`AAPL`).
- Candidate retention: 32.65%
- Candidate coverage: 100.00%
- Holdout candidate mean net return: -0.0930% vs baseline 0.0649%
- Holdout candidate median net return: -0.2924% vs baseline -0.0399%

### 8.5 Data-quality findings

- No duplicate timestamps, missing required values, or invalid OHLC rows in the synthetic target series.
- Data source is `synthetic`; survivorship, delisting, index-membership, corporate-action, and liquidity biases are not modeled.

### 8.6 Manifest and context-spec checksums

- Manifest SHA-256: `b006af6c114c080bac0485befc77bafc581ab0af28d5ae7081cc6afc4ef8aa77`
- Context-spec SHA-256: `2498eb4bcbc7459af108fec4cfae8a7cea2c0d4740d49473a67529c9d90f82a4`

### 8.7 Determinism evidence

Two runs from the same manifest and spec produced identical SHA-256 hashes for all generated files:

```
context_events.csv:         56811cc56632687ffbe8687541b13133b945c0ae5df06b24c85f906e52625192
candidate_comparison.csv:   bd66b2563ab85ae6bbe292f05922eac559a155c7976d6efc1e95ef166aa93533
holdout_evaluation.csv:     dac66bd5036554de3adf54955d151ab1cc1f0a2337113de08d190c2c0a1352e2
paired_backtests.csv:       4725812a3baf89750bca29383d0123878291409df54f02d1ba485bea64605623
ticker_comparison.csv:      46656fd27de06fa373ee36869a486d8199999c9df77db58797c4737e6693a8d0
data_quality.csv:           1b56d86e4ba1475227e9f356d257ced882c4034c6b0b6c6d5fd21aff9a436ca6
study.json:                 46d2e020e2792a27cd7428caeb5f6c94dbb72450e60314f127affc75f723047d
report.md:                  5f6164e8f8e137ac9ca564da2fbe1ef9dc0fd23451337e99fb69127a07d02804
manifest.lock.json:         804d33374b1d402b3a51c6e7fc043b6bc63c14a83659d345cd2bb33616419c01
context_spec.lock.json:     435743fecf4a4bba3072663e4fdeb16312600312f88afa9cb5488d4408c26ca0
candidate_selection.json:   3b5f6580341e12a545a520f0c35d8a0b3e459f6bdf0cf7b373a161478fc032a6
```

## 9. Real-data evidence inventory

A committed, manifest-locked SHORT-001 real-data v1 study now exists at `docs/research/artifacts/SHORT-001/2026-08-01-5ae8a420/` and is recorded in `docs/research/SHORT-001-SCHWAB-STUDY.md`. It contains the pre-registered context spec, per-symbol fetch audit, and a list of hard-invalid OHLCV rows. It does **not** contain a complete `manifest.lock.json`, `study.json`, event-study, paired-backtest, or candidate-selection output because the snapshot failed before a manifest could be generated. The data-ingestion failure is documented as **Outcome E — Invalid study**.

The only complete end-to-end SHORT-001 outcome with all gate artifacts remains the deterministic synthetic run.

## 10. What the evidence supports

- The infrastructure correctly computes point-in-time context from only available bars.
- Naive timestamps are rejected (`_require_aware`), stale context is flagged (`_is_stale`), and missing/stale/incomplete context is surfaced honestly.
- Candidate selection uses development and validation only; holdout is excluded.
- The event-study and paired-backtest gates enforce the documented criteria.
- The full pipeline is deterministic when inputs and splits are locked.
- The existing gates reject the synthetic candidate on the holdout for multiple reasons (mean, median, positive rate, single-ticker dependence).

## 11. What the evidence does not support

- Whether `market_rs` or `market_sector_rs` improve real-market short-term outcomes.
- Whether the policy works across a diversified, survivorship-bias-corrected universe of stocks and ETFs.
- Whether the thresholds, sample minimums, and drawdown tolerance are appropriate for real data.

A synthetic one-ticker run cannot validate or reject the market hypothesis. It validates the software, not the edge.

## 12. Bias and integrity review

- **Lookahead bias:** Context is computed from the most recent proxy bar `<= signal_time`; no future bars are used.
- **Split leakage:** `select_candidate` drops the `holdout` split before any metric used for selection.
- **Forward returns:** Complete outcomes do not cross split boundaries.
- **Survivorship/delisting:** Not addressed because the synthetic fixture has no delistings.
- **Parameter fishing:** The rerun used fixed spec values; no threshold, sample minimum, or split was tuned after seeing results.
- **Determinism:** Two identical-input runs produced byte-identical outputs.
- **Real-data bias:** Real Schwab daily OHLCV data were fetched in the v1 study, but the snapshot failed before any model was fit or evaluated, so no signal/outcome bias was introduced. The ingestion gate rejected malformed rows rather than hiding them.

## 13. Final disposition

`SHORT-001` status: **Blocked** (data invalid; v1 real-data attempt failed ingestion).

Reason: research infrastructure and methodology are implemented and verified, and a locked real-data v1 study was attempted. The Schwab daily OHLCV data for the locked 45-symbol panel contained 23 hard-invalid OHLC rows across 19 symbols (0.028% of 82,035 rows), preventing snapshot generation. The v1 attempt is invalid (Outcome E), but this is not the end of SHORT-001. A separate, approved research-only data-ingestion remediation PR is required to drop hard-invalid rows using the PATTERN-001 precedent, preserve the locked panel, and rerun the unchanged snapshot/evaluation before the hypothesis can be evaluated.

## 14. Requirements to reopen

A new real-data study must:

1. Be predefined in writing (universe, proxies, splits, date ranges, costs, horizons, slippage, sample minimums, gate thresholds).
2. Be manifest-locked with SHA-256 hashes for all input OHLCV files.
3. Use a locked context-spec JSON with no post-hoc changes to policies or thresholds.
4. Include at least ten holdout tickers (stocks and/or ETFs) and enough events to meet `minimum_holdout_events`.
5. Run the existing `snapshot` and `evaluate` CLI commands without modifying gate logic.
6. Preserve an untouched holdout not used for candidate selection.
7. Produce all required artifacts: `study.json`, `context_events.csv`, `candidate_comparison.csv`, `candidate_selection.json`, `holdout_evaluation.csv`, `paired_backtests.csv`, `ticker_comparison.csv`, `data_quality.csv`, `manifest.lock.json`, `context_spec.lock.json`, `report.md`.
8. Pass the dual-gate promotion criteria if promotion is to be considered.

## 15. Production-promotion requirements

Even if a future real-data study passes both gates, a **separate Gary-approved production-integration assignment** is required before any context policy is exposed in:

- `tradex/screener/engine.py`
- `tradex/ui/dashboard.py`
- `tradex/tracker/watcher.py`
- confluence, alerts, rankings, or default settings

No promotion may occur in this disposition PR.

## 16. Verification evidence

- `git diff --check` clean.
- `uv run ruff check tests scripts` clean.
- `uv run pytest tests/market tests/research/short_context -q` → 80 passed.
- `uv run pytest tests -q` with `HOME` redirected and all six canonical persistence paths (`TRADEX_DB_PATH`, `TRADEX_WATCHLISTS_DB_PATH`, `TRADEX_WEIGHTS_PATH`, `TRADEX_FP_DB`, `TRADEX_EARNINGS_CACHE_PATH`, `ALERT_STATE_PATH`) redirected to a temporary directory → 1229 passed, 5 pre-existing `datetime.utcnow()` deprecation warnings.
- Real `~/.tradex/signals.db`, `~/.tradex/watchlists.db`, `~/.tradex/fingerprints.db`, `~/.tradex/earnings_cache.db`, and `~/.tradex/alerts.db` mtimes were unchanged; `~/.tradex/weights.json` was absent both before and after.
- `uv run python -m tradex.research.short_context --help`, `snapshot --help`, and `evaluate --help` work offline.
- Focused documentation/search audit of `README.md`, `SETUP.md`, `CLAUDE.md`, `docs/PROJECT-TRACKER.md`, and `docs/research/SHORT-001.md` found no stale or contradictory SHORT-001 status claims.
- The synthetic rerun produced the outputs and checksums listed in section 8.
- Production boundary verified: no `context_policy`, `ShortContextPolicy`, or `short_context` references found in `tradex/screener`, `tradex/tracker`, `tradex/ui`, or `tradex/alerts`.

## 17. Known limitations

- Only the synthetic fixture has been exercised end-to-end.
- The synthetic fixture uses a single target ticker, so robustness criteria that require multiple tickers (e.g., "at least half improved") are mechanically failed in the rerun.
- A meaningful real-market test needs a representative, point-in-time universe with sector proxies and adequate holdout sample size.
- Provider data quality, survivorship bias, delisting bias, corporate actions, and liquidity capacity are not modeled in the synthetic run.

## 18. v2 ingestion remediation rerun

On 2026-08-07 the locked `short-001-hard-invalid-row-exclusion-v2` ingestion policy was applied to the unchanged `SHORT-001-schwab-v1.json` context specification and the same 45-symbol Schwab panel.

- Ingestion policy: `docs/research/specs/SHORT-001-ingestion-v2.json` (SHA-256 `f9a3f473fe14620984caca34cd6386000b87fea47a44e32d83bd05852c3ef23e`).
- Snapshot manifest SHA-256: `e5b64b56328c4de588ff7b126f8aedd73c81951b61bde915b7e410afb1f6813b`.
- Raw rows: `82,035`; cleaned rows: `82,012`; invalid rows removed: `23` (`0.028037%`) across `19` symbols.
- All predefined data-quality thresholds passed; the complete 45-symbol panel was retained.
- No OHLCV values were repaired, clamped, interpolated, substituted, or inferred.
- The unchanged evaluation was run with `--warmup-bars 60 --horizons 1,3,5 --slippage-bps 0.0,5.0,10.0 --commission-bps 0.0`.
- Result: `selected_policy: null`; `selection_reason: "no policy passed development and validation criteria"`.
- No holdout event-study or paired-backtest evaluation of a candidate was performed because no candidate was selected.
- Outcome: **Inconclusive (Outcome I)**. The data-quality remediation succeeded, but the predefined candidate-selection gate did not identify a policy worth evaluating on holdout.
- Safe artifact bundle: `docs/research/artifacts/SHORT-001/2026-08-07-e5b64b56/`.
- Full report: `docs/research/SHORT-001-SCHWAB-STUDY-V2.md`.

No production behavior changed. The production default `ShortContextPolicy.OFF` remains in effect.
