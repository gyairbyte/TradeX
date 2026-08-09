# INTRA-001B-DATASET-V1 One-Year Dataset Build Report

- **Task ID:** INTRA-001B-DATASET-V1
- **Dataset ID:** INTRA-001B-DATASET-V1
- **Disposition:** inconclusive
- **Reason:** Pre-normalization metrics (duplicate/malformed) are unavailable for 756 of 756 symbol-months; 6 symbol-month(s) independently failed observed data-quality thresholds (missing/zero-volume); no invalid provider/provenance/pagination/symbol-identity/manifest failures
- **Branch:** devin/intra-001b-one-year-snapshot
- **Live run head:** ee4b7b897f3768f6fa6608c2fdba28384b9a5d91
- **Bundle generation head:** ccb5e604d8497c1cbec230bc146c12019d3d0bae
- **Pre-registration commit:** 60e46e25b38e9e7ef9316bf49bb0a51cf092121c
- **Starting main SHA:** d3df7bffb5266e19c356c1027eadc7ee047a731a
- **Ran at:** 2026-08-09T01:48:44.638930+00:00

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

- Disposition: inconclusive
- Max missing-bar rate: 29.4559%
- Max zero-volume rate: 0.0%
- Max duplicate rate: unavailable (pre-normalization metrics not recovered)
- Max malformed-row rate: unavailable (pre-normalization metrics not recovered)
- Pre-normalization metrics available: False
- Symbols rejected for data quality: 0.7937%
- Observed data-quality failures independent of unverified pre-normalization metrics: 6 symbol-month(s)

### Monthly rejection summary

| Month | Total | Invalid | Unverified | Data-quality rejected | Rejected % |
|-------|-------|---------|------------|----------------------|------------|
| 2025-01 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-02 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-03 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-04 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-05 | 63 | 0 | 63 | 0 | 0.0% |
| 2025-06 | 63 | 0 | 63 | 0 | 0.0% |
| 2025-07 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-08 | 63 | 0 | 63 | 0 | 0.0% |
| 2025-09 | 63 | 0 | 63 | 0 | 0.0% |
| 2025-10 | 63 | 0 | 63 | 0 | 0.0% |
| 2025-11 | 63 | 0 | 63 | 1 | 1.5873% |
| 2025-12 | 63 | 0 | 63 | 0 | 0.0% |

## Resource usage

- Massive HTTP requests: 440
- Massive incomplete snapshots: 0
- Per-phase Alpaca counters available: False
- Alpaca ranking logical calls: unavailable
- Alpaca ranking HTTP pages: unavailable
- Alpaca ranking HTTP attempts: unavailable
- Alpaca ranking HTTP 429s: unavailable
- Alpaca ranking HTTP errors: unavailable
- Alpaca OHLCV logical calls: unavailable
- Alpaca OHLCV HTTP pages: unavailable
- Alpaca OHLCV HTTP attempts: unavailable
- Alpaca OHLCV HTTP 429s: unavailable
- Alpaca OHLCV HTTP errors: unavailable
- HTTP errors (total): 0
- HTTP 429s (total): 0
- Pagination cycles: 0
- Incomplete requests: 0
- Original aggregate Alpaca HTTP requests (ranking + OHLCV): 1885
- Runtime (seconds): unavailable — Historical runtime unavailable
- Local storage (bytes): 270242839

## Ranking methodology

- Ranking timeframe: 1Day
- Ranking parity passed: False
- Ranking parity message: 1Day volume is not equivalent to regular-session-only volume; 1Day ranking is authorized by amendment; bounded 60-symbol sensitivity sample top-50 set matched, absolute dollar-volume parity did not
- Parity fallback used: False

## Limitations

- Massive/Polygon does not surface an explicit OTC marker; conservative exclusion is performed through the exchange allowlist and security-type allowlist.
- Duplicate symbols in inactive snapshots are excluded from the active universe.
- The 2025-only dataset is shorter than the original 2022-2025 contract; sample minimums and gates are unchanged.
- Alpaca SIP 1Day volume is a total-liquidity proxy that includes pre-market and after-hours volume; it is not exact regular-session volume. The locked ranking formula uses this proxy.
- Pre-normalization duplicate/malformed metrics for this bundle: unavailable (recomputed from normalized parquet; original 2026-08-08-200945 run normalized before recording). The corrected pipeline now preserves and counts these values before deduplication for future runs.
- The five whole-market ~78-bar discrepancies in the original data_quality.csv were caused by an off-by-one expected-session construction in `_sessions_in_range`: it included the first regular session of the next calendar month when that day was a trading day and then counted 78 bars for that not-yet-open session. The corrected implementation uses session open/close UTC comparisons. Affected months and their extra expected-but-absent sessions: March 2025 = 2025-04-01; April 2025 = 2025-05-01; June 2025 = 2025-07-01; July 2025 = 2025-08-01; September 2025 = 2025-10-01.

## Next step

`devin/intra-001-c-research-engine` — implement session VWAP, opening-drive state, pullback/reclaim detector, and baselines with synthetic tests only. Development/validation/holdout evaluation belongs to `devin/intra-001-d-locked-study` under a separate, explicitly approved PR.

---
This report is a research artifact only. It does not authorize production changes.
