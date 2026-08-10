# INTRA-001D Real-Data Study Report

## Study status
- **Holdout status:** not_run_validation_inconclusive
- **Production promotion eligible:** False
- **Dataset evidence label:** locked INTRA-001B-DATASET-V1 with verified manifest.lock.json, data_quality.csv, and universe_manifest.csv
- **Evidence eligible:** False
- **Split:** validation
- **Runtime (seconds):** 5.2511
- **Disposition:** `inconclusive`
- **Reason:** sample_or_data_sufficiency_minimums_not_met: executed_candidate_trades_0_below_300; represented_stock_symbols_0_below_25; represented_etfs_0_below_8; stock_stratum_trades_0_below_100; etf_stratum_trades_0_below_75; data_sufficiency_failed; missing_bar_rate_0.2946_above_5% (1 symbol-month); monthly_rejection_2025-01_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-02_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-03_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-04_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-05_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-06_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-07_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-08_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-09_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-10_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-11_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-12_63/63_100.00%_above_5.0% (1 symbol-month); pre_normalization_metrics_unavailable (189 symbol-months)

## Locked spec and dataset
- **Spec SHA-256:** `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- **Dataset:** `INTRA-001B-DATASET-V1`
- **Synthetic engine:** False

## Gate results
| Gate | Passed | Reason |
|---|---|---|
| 1_sample_and_data_sufficiency | FAIL | executed_candidate_trades_0_below_300; represented_stock_symbols_0_below_25; represented_etfs_0_below_8; stock_stratum_trades_0_below_100; etf_stratum_trades_0_below_75; data_sufficiency_failed; missing_bar_rate_0.2946_above_5% (1 symbol-month); monthly_rejection_2025-01_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-02_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-03_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-04_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-05_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-06_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-07_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-08_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-09_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-10_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-11_63/63_100.00%_above_5.0% (1 symbol-month); monthly_rejection_2025-12_63/63_100.00%_above_5.0% (1 symbol-month); pre_normalization_metrics_unavailable (189 symbol-months) |
| 2_candidate_pooled_expectancy_positive_5bps | FAIL | pooled_expectancy=0.0000 |
| 3_candidate_median_expectancy_vs_baseline_a | INCONCLUSIVE | median_per_symbol_expectancy_not_computable |
| 4_candidate_median_expectancy_vs_baseline_b | INCONCLUSIVE | median_per_symbol_expectancy_not_computable |
| 5_candidate_median_profit_factor_threshold | INCONCLUSIVE | profit_factor_median_not_computable |
| 6_candidate_median_profit_factor_not_below_baselines | INCONCLUSIVE | profit_factor_median_not_comparable |
| 7_positive_symbol_rate | INCONCLUSIVE | positive_symbol_rate_not_computable |
| 8_paired_symbol_outperformance_vs_baseline_a | INCONCLUSIVE | paired_overlap_0_below_15 |
| 9_median_drawdown_not_worse_than_baseline | INCONCLUSIVE | median_mdd_not_computable |
| 10_stock_and_etf_strata_nonneg_expectancy | PASS | stock=0.0000_etf=0.0000 |
| 11_candidate_pooled_expectancy_nonneg_10bps | PASS | pooled_expectancy_10bps=0.0000 |
| 12_concentration_limits | PASS | concentration_within_limits |

## Candidate
- Total signals: 0
- No signal: 0
- Rejected: 0
- Executed trades: 0

## Baseline A
- Total signals: 0
- No signal: 0
- Rejected: 0
- Executed trades: 0

## Baseline B
- Total signals: 0
- No signal: 0
- Rejected: 0
- Executed trades: 0

## Cost sensitivity
| Strategy | Scenario | Signals | Executed | Pooled expectancy | Total return | Overall MDD | Median per-symbol expectancy | Positive trade rate | Avg holding minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| candidate | candidate:primary_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_a | baseline_a:primary_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_b | baseline_b:primary_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| candidate | candidate:slippage_0bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_a | baseline_a:slippage_0bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_b | baseline_b:slippage_0bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| candidate | candidate:slippage_2.5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_a | baseline_a:slippage_2.5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_b | baseline_b:slippage_2.5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| candidate | candidate:slippage_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_a | baseline_a:slippage_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_b | baseline_b:slippage_5bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| candidate | candidate:slippage_10bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_a | baseline_a:slippage_10bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |
| baseline_b | baseline_b:slippage_10bps | 0 | 0 | 0.0 | 0 | 0.0 | N/A | N/A | N/A |

## Monthly data-quality rejection summary

| Month | Total | Rejected | Rejected % | Rejected by split |
|---|---|---|---|---|
| 2025-01 | 63 | 63 | 100.0 | development=63 |
| 2025-02 | 63 | 63 | 100.0 | development=63 |
| 2025-03 | 63 | 63 | 100.0 | development=63 |
| 2025-04 | 63 | 63 | 100.0 | development=63 |
| 2025-05 | 63 | 63 | 100.0 | development=63 |
| 2025-06 | 63 | 63 | 100.0 | development=63 |
| 2025-07 | 63 | 63 | 100.0 | validation=63 |
| 2025-08 | 63 | 63 | 100.0 | validation=63 |
| 2025-09 | 63 | 63 | 100.0 | validation=63 |
| 2025-10 | 63 | 63 | 100.0 | holdout=63 |
| 2025-11 | 63 | 63 | 100.0 | holdout=63 |
| 2025-12 | 63 | 63 | 100.0 | holdout=63 |
| **Total** | **756** | **756** | **100.0** | development=378; holdout=189; validation=189 |

## Data-quality rejection reconciliation

- Total data-quality rejected symbol-months: **756** (development=378 ; holdout=189 ; validation=189).
- The locked data-quality file records six BKNG symbol-months rejected for `missing_bar_rate; pre_normalization_metrics_unavailable` (4 development, 1 validation, 1 holdout). This is within the locked `symbols_rejected_for_data_quality_pct_max = 5%` per monthly universe and does not trigger an invalid disposition.
- The remaining rejected symbol-months are rejected solely for `pre_normalization_metrics_unavailable` and are not counted as missing-bar-rate failures.

## Limitations
- This report is produced by the locked INTRA-001C engine and INTRA-001D adapter.
- Pre-normalization duplicate/malformed metrics are unverified for this dataset; the split is treated as inconclusive.
- Real-data results are not evidence for production promotion unless both validation and holdout are supported.
