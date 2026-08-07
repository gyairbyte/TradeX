SHORT-001 Schwab real-data study v2 audit artifacts
Run ID: 2026-08-07-e5b64b56

These are the safe, auditable artifacts from the locked SHORT-001 v2 real-data
rerun using the `short-001-hard-invalid-row-exclusion-v2` ingestion policy.

The ingestion policy dropped 23 malformed daily OHLCV rows across 19 of the 45
pre-registered symbols (0.028% of 82,035 fetched rows) and passed all predefined
data-quality thresholds. No values were repaired, clamped, interpolated, or
inferred. The unchanged SHORT-001 Schwab v1 context spec and evaluation
parameters were then applied.

Snapshot:
  raw_total_rows:        82,035
  cleaned_total_rows:    82,012
  invalid_rows_removed:  23
  total_invalid_rate:    0.028037%
  affected_symbols:      19
  all_symbols_retained:  true
  threshold_result:      passed

Evaluation outcome:
  selected_policy:       null
  selection_reason:      no policy passed development and validation criteria
  production_promotion_eligible: false

Files:
  README.txt                          this file
  artifact_manifest.json              manifest of this bundle
  checksums.sha256                    SHA-256 checksums of included files
  context_spec.lock.json              locked copy of SHORT-001-schwab-v1.json
  ingestion_spec.lock.json            locked copy of SHORT-001-ingestion-v2.json
  snapshot/
    manifest.json                     locked snapshot manifest
    AAPL.csv ... XOM.csv              cleaned, manifest-locked OHLCV CSVs
    snapshot_audit.json               snapshot-level cleaning audit
    invalid_rows.csv                  the 23 rows that were dropped
    snapshot_data_quality.csv         per-ticker raw/cleaned row counts
    snapshot_checksums.sha256         snapshot-internal checksums
    ingestion_spec.lock.json          policy lock inside snapshot
  evaluation/
    report.md                         final study report
    candidate_selection.json          candidate policy selection and metrics
    candidate_comparison.csv            development/validation candidate comparison
    holdout_evaluation.csv            holdout event-study metrics (empty; no candidate)
    paired_backtests.csv              paired-backtest metrics per ticker
    ticker_comparison.csv             per-ticker robustness comparison
    data_quality.csv                  per-ticker data-quality summary
    manifest.lock.json                manifest reference copied into result
    context_spec.lock.json            context spec reference copied into result
    ingestion_spec.lock.json          ingestion spec reference copied into result
    snapshot_audit.lock.json          snapshot audit reference copied into result

Excluded (per provider terms and repository policy):
  - Raw Schwab OHLCV CSVs (cleaned, manifest-locked OHLCV CSVs are included)
  - OAuth tokens and credentials
  - Row-level provider-derived output beyond the 23 invalid rows
  - context_events.csv and study.json (large, reproducible from the locked manifest + spec)

Context-spec SHA-256:
  5ae8a420be97d3665c48ed82401cb4d9b0f0d71610898b7036f72453755acb45

Ingestion-spec SHA-256:
  f9a3f473fe14620984caca34cd6386000b87fea47a44e32d83bd05852c3ef23e

Snapshot manifest SHA-256:
  e5b64b56328c4de588ff7b126f8aedd73c81951b61bde915b7e410afb1f6813b

Outcome:
  Completed — Not supported. The data-quality remediation succeeded and the
  predefined candidate-selection gate ran as designed, but no candidate context
  policy passed the development/validation criteria, so no holdout evaluation
  of a candidate was performed. Production promotion is not eligible.
