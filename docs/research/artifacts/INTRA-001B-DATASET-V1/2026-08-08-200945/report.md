# INTRA-001B-DATASET-V1 One-Year Dataset Build Report

- **Task ID:** INTRA-001B-DATASET-V1
- **Dataset ID:** INTRA-001B-DATASET-V1
- **Disposition:** valid
- **Reason:** Data quality valid: 6 of 756 symbol-months rejected (0.7937%)
- **Branch:** devin/intra-001b-one-year-snapshot
- **Live run head:** ee4b7b897f3768f6fa6608c2fdba28384b9a5d91
- **Pre-registration commit:** 60e46e25b38e9e7ef9316bf49bb0a51cf092121c
- **Starting main SHA:** d3df7bffb5266e19c356c1027eadc7ee047a731a
- **Ran at:** 2026-08-08T20:09:45.504809+00:00

## Locked data contract

- Original strategy spec: `docs/research/specs/INTRA-001-v1.json` (SHA-256 `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`)
- Amendment v3: `docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json` (SHA-256 `94cc27820c97086a27252e2392c6fcf5ebcba4be482e026e1a80ff523ed1e48b`)
- V4 decision doc: `docs/research/INTRA-001B-REFERENCE-V4.md` (SHA-256 `23afcdad8a72efff9508a6958a4b05dfbf8b88ab2356414730f97b5298bf4d02`)
- OHLCV provider: `alpaca` feed `sip`
- Reference provider: `massive` with `accepted_with_documented_limitations`
- Dataset: `2025-01-02` through `2025-12-31`
- Monthly PIT dates: 2024-12-31, 2025-01-31, 2025-02-28, 2025-03-31, 2025-04-30, 2025-05-31, 2025-06-30, 2025-07-31, 2025-08-31, 2025-09-30, 2025-10-31, 2025-11-30

## Universe

- Unique selected stocks: 97
- Total stock symbol-months: 600
- Fixed ETF count: 13

### Monthly stock counts

- 2025-01: 50
- 2025-02: 50
- 2025-03: 50
- 2025-04: 50
- 2025-05: 50
- 2025-06: 50
- 2025-07: 50
- 2025-08: 50
- 2025-09: 50
- 2025-10: 50
- 2025-11: 50
- 2025-12: 50

## Data quality

- Disposition: valid
- Max missing-bar rate: 31.1355%
- Max zero-volume rate: 0.0%
- Max duplicate rate: 0.0%
- Symbols rejected: 0.7937%

## Resource usage

- Massive HTTP requests: 440
- Alpaca HTTP requests: 1885
- HTTP errors: 0
- HTTP 429s: 0
- Pagination cycles: 0
- Incomplete requests: 0
- Runtime (seconds): 0.0
- Local storage (bytes): 269872983

## Ranking methodology

- Ranking timeframe: 1Day
- Ranking parity passed: True
- Parity fallback used: False

## Limitations

- Massive/Polygon does not surface an explicit OTC marker; conservative exclusion is performed through the exchange allowlist and security-type allowlist.
- Duplicate symbols in inactive snapshots are excluded from the active universe.
- The 2025-only dataset is shorter than the original 2022-2025 contract; sample minimums and gates are unchanged.

## Next step

`devin/intra-001-c-research-engine` — build the research engine and run development/validation/holdout evaluation under a separate, explicitly approved PR.

---
This report is a research artifact only. It does not authorize production changes.
