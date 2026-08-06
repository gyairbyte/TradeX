SHORT-001 Schwab real-data study audit artifacts
Run ID: 2026-08-01-5ae8a420

These are the safe, auditable artifacts from the attempted locked real-data v1 study.
The snapshot command failed during data ingestion because 23 Schwab daily OHLCV
candles across 19 of the 45 pre-registered symbols (0.028% of approximately
82,035 fetched rows) violated hard OHLC invariants (e.g. low > open or
high < open). No manifest, event study, backtest, or candidate-selection outputs
were produced.

Files:
  README.txt                this file
  artifact_manifest.json    manifest of this bundle
  context_spec.lock.json    locked copy of SHORT-001-schwab-v1.json
  report.md                 final study report
  data_quality.csv          per-symbol fetch and bar-validation status
  bad_candles.csv           23 candles that failed OHLC invariants

Excluded (per provider terms and repository policy):
  - Raw Schwab OHLCV CSVs
  - OAuth tokens and credentials
  - Row-level provider-derived output
  - manifest.lock.json (not produced: snapshot failed before manifest generation)

Context-spec SHA-256:
  5ae8a420be97d3665c48ed82401cb4d9b0f0d71610898b7036f72453755acb45

Pre-registration commit:
  4d696729a10288bb239988c4255f3d9cf3677191

Outcome:
  Invalid v1 attempt (Outcome E). Production promotion eligible: false.
  This is not the end of SHORT-001; a narrowly scoped data-ingestion
  remediation using the PATTERN-001 malformed-row precedent is recommended.
