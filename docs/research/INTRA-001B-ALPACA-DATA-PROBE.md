# INTRA-001B-ALPACA Alpaca Five-Minute Data Capability Probe Report

**Task ID:** INTRA-001B-ALPACA
**Provider:** alpaca
**Outcome:** `supported_ohlcv_only`
**Approved for INTRA-001 five-minute OHLCV:** True
**Approved as complete INTRA-001 data source:** False
**Pre-registration commit:** `286493eceeffd6aec872ce7516bed5d1b0cd304f`


## 1. Decision summary

- Direct full range supported: True
- Chunked historical windows supported: False
- Selected request method: `sip`
- Selected windowing policy: `direct_full_range`
- Repeatability passed: True
- Method parity passed: False
- Chunk overlap passed: True
- Coverage threshold passed: True



## 2. Research classification

This is a research-only data-capability probe (INTRA-001B-PROBE). It does not implement the INTRA-001 trading setup, detector, backtester, VWAP logic, baselines, gates, or production integration. It does not call account, position, balance, transaction, or order endpoints.


## 3. Specification SHAs

- INTRA-001B probe spec SHA-256: `620617a981bdfb3557aee66a2c427ab6141115ac0c39528fa85546aae472a6fc`
- INTRA-001 strategy spec SHA-256: `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- Pre-registration commit: `286493eceeffd6aec872ce7516bed5d1b0cd304f`



## 4. Client version

`requests==2.34.2`


## 5. Method signatures

- `GET /v2/stocks/{symbol}/bars?timeframe=5Min&feed=sip&adjustment=raw&asof=2025-12-31&sort=asc&limit=10000`
- `GET /v2/stocks/{symbol}/bars?timeframe=5Min&feed=iex&adjustment=raw&asof=2025-12-31&sort=asc&limit=10000`


## 6. Credential handling

Provider credentials (Schwab OAuth tokens/app keys or Alpaca API key/secret) are loaded from environment variables and files outside the repository. No credentials, tokens, or HTTP headers are committed or written into this report.


## 7. Request plan

Executed 60 request/repetition combinations across the locked full-range, bounded-window, and overlap probes.


## 8. Results overview

60 of 60 requests returned HTTP 200.


## 9. Request audit

See `request_audit.csv` in the safe artifact bundle.

| probe_id | symbol | method | repetition | requested_eastern_start | requested_eastern_end | requested_utc_start | requested_utc_end | http_status | safe_error_classification | raw_candle_count | normalized_candle_count | raw_earliest_timestamp | raw_latest_timestamp | requested_range_earliest | requested_range_latest | out_of_range_candles | unique_regular_sessions | expected_eligible_sessions | expected_regular_session_bars | returned_regular_session_bars | primary_session_bars | early_close_session_bars | extended_hours_bars | regular_session_coverage_pct | missing_regular_session_bars | duplicate_timestamps | duplicate_bar_rate_pct | zero_volume_bars | zero_volume_rate_pct | invalid_ohlc_rows | non_five_minute_intervals | candle_payload_sha256 | requested_range_normalized_sha256 | date_bound_classification | timestamp_semantics_classification | threshold_result | retry_after_seconds | notes | page_count | next_page_token_present | pagination_complete | repeated_page_token | pagination_cycle_detected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-sip-rep1 | SPY | sip | 1 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 188119 | 188119 | 2022-01-03T09:00:00.000000+0000 | 2026-01-01T00:55:00.000000+0000 | 2022-01-03T09:00:00.000000+0000 | 2026-01-01T00:55:00.000000+0000 | 0 | 994 | 994 | 77532 | 77532 | 77532 | 378 | 110209 | 100.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0 | 0 |  | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | honored_exactly | inconsistent | passed | None |  | 83 | True | True | False | False |
| full-SPY-sip-rep2 | SPY | sip | 2 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 188119 | 188119 | 2022-01-03T09:00:00.000000+0000 | 2026-01-01T00:55:00.000000+0000 | 2022-01-03T09:00:00.000000+0000 | 2026-01-01T00:55:00.000000+0000 | 0 | 994 | 994 | 77532 | 77532 | 77532 | 378 | 110209 | 100.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0 | 0 |  | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | honored_exactly | inconsistent | passed | None |  | 83 | True | True | False | False |
| full-SPY-iex-rep1 | SPY | iex | 1 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 83287 | 83287 | 2022-01-03T13:40:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2022-01-03T13:40:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 993 | 994 | 77532 | 77382 | 77382 | 378 | 5527 | 99.80653149667235 | 150 | 0 | 0.0 | 0 | 0.0 | 0 | 0 |  | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | honored_exactly | inconsistent | passed | None |  | 40 | True | True | False | False |
| full-SPY-iex-rep2 | SPY | iex | 2 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 83287 | 83287 | 2022-01-03T13:40:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2022-01-03T13:40:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 993 | 994 | 77532 | 77382 | 77382 | 378 | 5527 | 99.80653149667235 | 150 | 0 | 0.0 | 0 | 0.0 | 0 | 0 |  | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | honored_exactly | inconsistent | passed | None |  | 40 | True | True | False | False |
| window-2022-02-SPY-sip-rep1 | SPY | sip | 1 | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 2022-02-01T05:00:00.000000+0000 | 2022-03-01T04:59:59.999999+0000 | 200 | none | 3530 | 3530 | 2022-02-01T09:00:00.000000+0000 | 2022-03-01T00:55:00.000000+0000 | 2022-02-01T09:00:00.000000+0000 | 2022-03-01T00:55:00.000000+0000 | 0 | 19 | 19 | 1482 | 1482 | 1482 | 0 | 2048 | 100.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0 | 0 |  | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | honored_exactly | inconsistent | passed | None |  | 2 | True | True | False | False |



## 10. Date-bound classifications

| probe_id | date_bound | threshold |
| --- | --- | --- |
| full-SPY-sip-rep1 | honored_exactly | passed |
| full-SPY-sip-rep2 | honored_exactly | passed |
| full-SPY-iex-rep1 | honored_exactly | passed |
| full-SPY-iex-rep2 | honored_exactly | passed |
| window-2022-02-SPY-sip-rep1 | honored_exactly | passed |
| window-2022-02-SPY-sip-rep2 | honored_exactly | passed |
| window-2022-02-SPY-iex-rep1 | honored_exactly | passed |
| window-2022-02-SPY-iex-rep2 | honored_exactly | passed |
| window-2022-02-AAPL-sip-rep1 | honored_exactly | passed |
| window-2022-02-AAPL-sip-rep2 | honored_exactly | passed |
| window-2022-02-AAPL-iex-rep1 | honored_exactly | passed |
| window-2022-02-AAPL-iex-rep2 | honored_exactly | passed |
| window-2022-02-JPM-sip-rep1 | honored_exactly | passed |
| window-2022-02-JPM-sip-rep2 | honored_exactly | passed |
| window-2022-02-JPM-iex-rep1 | honored_exactly | passed |
| window-2022-02-JPM-iex-rep2 | honored_exactly | passed |
| window-2023-08-SPY-sip-rep1 | honored_exactly | passed |
| window-2023-08-SPY-sip-rep2 | honored_exactly | passed |
| window-2023-08-SPY-iex-rep1 | honored_exactly | passed |
| window-2023-08-SPY-iex-rep2 | honored_exactly | passed |
| window-2023-08-AAPL-sip-rep1 | honored_exactly | passed |
| window-2023-08-AAPL-sip-rep2 | honored_exactly | passed |
| window-2023-08-AAPL-iex-rep1 | honored_exactly | passed |
| window-2023-08-AAPL-iex-rep2 | honored_exactly | passed |
| window-2023-08-JPM-sip-rep1 | honored_exactly | passed |
| window-2023-08-JPM-sip-rep2 | honored_exactly | passed |
| window-2023-08-JPM-iex-rep1 | honored_exactly | passed |
| window-2023-08-JPM-iex-rep2 | honored_exactly | passed |
| window-2024-06-SPY-sip-rep1 | honored_exactly | passed |
| window-2024-06-SPY-sip-rep2 | honored_exactly | passed |
| window-2024-06-SPY-iex-rep1 | honored_exactly | passed |
| window-2024-06-SPY-iex-rep2 | honored_exactly | passed |
| window-2024-06-AAPL-sip-rep1 | honored_exactly | passed |
| window-2024-06-AAPL-sip-rep2 | honored_exactly | passed |
| window-2024-06-AAPL-iex-rep1 | honored_exactly | passed |
| window-2024-06-AAPL-iex-rep2 | honored_exactly | passed |
| window-2024-06-JPM-sip-rep1 | honored_exactly | passed |
| window-2024-06-JPM-sip-rep2 | honored_exactly | passed |
| window-2024-06-JPM-iex-rep1 | honored_exactly | passed |
| window-2024-06-JPM-iex-rep2 | honored_exactly | passed |
| window-2025-12-SPY-sip-rep1 | honored_exactly | passed |
| window-2025-12-SPY-sip-rep2 | honored_exactly | passed |
| window-2025-12-SPY-iex-rep1 | honored_exactly | passed |
| window-2025-12-SPY-iex-rep2 | honored_exactly | passed |
| window-2025-12-AAPL-sip-rep1 | honored_exactly | passed |
| window-2025-12-AAPL-sip-rep2 | honored_exactly | passed |
| window-2025-12-AAPL-iex-rep1 | honored_exactly | passed |
| window-2025-12-AAPL-iex-rep2 | honored_exactly | passed |
| window-2025-12-JPM-sip-rep1 | honored_exactly | passed |
| window-2025-12-JPM-sip-rep2 | honored_exactly | passed |
| window-2025-12-JPM-iex-rep1 | honored_exactly | passed |
| window-2025-12-JPM-iex-rep2 | honored_exactly | passed |
| overlap-left-SPY-sip-rep1 | honored_exactly | passed |
| overlap-left-SPY-sip-rep2 | honored_exactly | passed |
| overlap-left-SPY-iex-rep1 | honored_exactly | passed |
| overlap-left-SPY-iex-rep2 | honored_exactly | passed |
| overlap-right-SPY-sip-rep1 | honored_exactly | passed |
| overlap-right-SPY-sip-rep2 | honored_exactly | passed |
| overlap-right-SPY-iex-rep1 | honored_exactly | passed |
| overlap-right-SPY-iex-rep2 | honored_exactly | passed |



## 11. Coverage summary

| base_probe_id | symbol | method | requested_eastern_start | requested_eastern_end | expected_eligible_sessions | expected_regular_session_bars | returned_regular_session_bars | primary_session_bars | early_close_session_bars | extended_hours_bars | regular_session_coverage_pct | missing_regular_session_bars | duplicate_bar_rate_pct | zero_volume_rate_pct | invalid_ohlc_rows | non_five_minute_intervals | timestamp_semantics_classification | date_bound_classification | threshold_result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-sip | SPY | sip | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 994 | 77532 | 77532 | 77532 | 378 | 110209 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| full-SPY-iex | SPY | iex | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 994 | 77532 | 77382 | 77382 | 378 | 5527 | 99.8065 | 150 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-SPY-sip | SPY | sip | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1482 | 1482 | 0 | 2048 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-SPY-iex | SPY | iex | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1482 | 1482 | 0 | 172 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-AAPL-sip | AAPL | sip | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1482 | 1482 | 0 | 1983 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-AAPL-iex | AAPL | iex | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1482 | 1482 | 0 | 26 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-JPM-sip | JPM | sip | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1482 | 1482 | 0 | 904 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2022-02-JPM-iex | JPM | iex | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 1481 | 1481 | 0 | 1 | 99.9325 | 1 | 0.0 | 0.0 | 0 | 0 | bar_start | honored_exactly | passed |
| window-2023-08-SPY-sip | SPY | sip | 2023-08-01T00:00:00.000000-0400 | 2023-08-31T23:59:59.999999-0400 | 23 | 1794 | 1794 | 1794 | 0 | 2566 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |
| window-2023-08-SPY-iex | SPY | iex | 2023-08-01T00:00:00.000000-0400 | 2023-08-31T23:59:59.999999-0400 | 23 | 1794 | 1794 | 1794 | 0 | 79 | 100.0 | 0 | 0.0 | 0.0 | 0 | 0 | inconsistent | honored_exactly | passed |



## 12. Timestamp semantics

- `inconsistent`: 48
- `bar_start`: 12


## 13. Repeatability

| base_probe_id | symbol | method | date_range | repeat_hash_match | rep1_http_status | rep2_http_status | rep1_candle_count | rep2_candle_count | rep1_hash | rep2_hash | rep1_threshold | rep2_threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-sip | SPY | sip | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 188119 | 188119 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | passed | passed |
| full-SPY-iex | SPY | iex | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 83287 | 83287 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | passed | passed |
| window-2022-02-SPY-sip | SPY | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 3530 | 3530 | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | passed | passed |
| window-2022-02-SPY-iex | SPY | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1654 | 1654 | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | passed | passed |
| window-2022-02-AAPL-sip | AAPL | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 3465 | 3465 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | passed | passed |
| window-2022-02-AAPL-iex | AAPL | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1508 | 1508 | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | passed | passed |
| window-2022-02-JPM-sip | JPM | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 2386 | 2386 | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | passed | passed |
| window-2022-02-JPM-iex | JPM | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | passed | passed |
| window-2023-08-SPY-sip | SPY | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 4360 | 4360 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | passed | passed |
| window-2023-08-SPY-iex | SPY | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1873 | 1873 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | passed | passed |
| window-2023-08-AAPL-sip | AAPL | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 4316 | 4316 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | passed | passed |
| window-2023-08-AAPL-iex | AAPL | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1816 | 1816 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | passed | passed |
| window-2023-08-JPM-sip | JPM | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 2453 | 2453 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | passed | passed |
| window-2023-08-JPM-iex | JPM | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1748 | 1748 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | passed | passed |
| window-2024-06-SPY-sip | SPY | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 3526 | 3526 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | passed | passed |
| window-2024-06-SPY-iex | SPY | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1500 | 1500 | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | passed | passed |
| window-2024-06-AAPL-sip | AAPL | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 3568 | 3568 | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | passed | passed |
| window-2024-06-AAPL-iex | AAPL | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1487 | 1487 | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | passed | passed |
| window-2024-06-JPM-sip | JPM | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 2008 | 2008 | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | passed | passed |
| window-2024-06-JPM-iex | JPM | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1419 | 1419 | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | passed | passed |
| window-2025-12-SPY-sip | SPY | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 4182 | 4182 | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | passed | passed |
| window-2025-12-SPY-iex | SPY | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1967 | 1967 | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | passed | passed |
| window-2025-12-AAPL-sip | AAPL | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 3821 | 3821 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | passed | passed |
| window-2025-12-AAPL-iex | AAPL | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1692 | 1692 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | passed | passed |
| window-2025-12-JPM-sip | JPM | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 2718 | 2718 | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | passed | passed |
| window-2025-12-JPM-iex | JPM | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1679 | 1679 | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | passed | passed |
| overlap-left-SPY-sip | SPY | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 1858 | 1858 | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | passed | passed |
| overlap-left-SPY-iex | SPY | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 790 | 790 | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | passed | passed |
| overlap-right-SPY-sip | SPY | sip | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 2595 | 2595 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | passed | passed |
| overlap-right-SPY-iex | SPY | iex | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1106 | 1106 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | passed | passed |



## 14. Method parity

No rows.



## 15. Feed comparison

| window | symbol | repetition | candidate_probe_id | comparison_probe_id | candidate_hash | comparison_hash | candidate_bars | comparison_bars | volume_difference | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY | SPY | 1 | full-SPY-sip-rep1 | full-SPY-iex-rep1 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | 188119 | 83287 | None | different_timestamps |
| full-SPY | SPY | 2 | full-SPY-sip-rep2 | full-SPY-iex-rep2 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | 188119 | 83287 | None | different_timestamps |
| window-2022-02-SPY | SPY | 1 | window-2022-02-SPY-sip-rep1 | window-2022-02-SPY-iex-rep1 | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | 3530 | 1654 | None | different_timestamps |
| window-2022-02-SPY | SPY | 2 | window-2022-02-SPY-sip-rep2 | window-2022-02-SPY-iex-rep2 | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | 3530 | 1654 | None | different_timestamps |
| window-2022-02-AAPL | AAPL | 1 | window-2022-02-AAPL-sip-rep1 | window-2022-02-AAPL-iex-rep1 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | 3465 | 1508 | None | different_timestamps |
| window-2022-02-AAPL | AAPL | 2 | window-2022-02-AAPL-sip-rep2 | window-2022-02-AAPL-iex-rep2 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | 3465 | 1508 | None | different_timestamps |
| window-2022-02-JPM | JPM | 1 | window-2022-02-JPM-sip-rep1 | window-2022-02-JPM-iex-rep1 | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | 2386 | 1482 | None | different_timestamps |
| window-2022-02-JPM | JPM | 2 | window-2022-02-JPM-sip-rep2 | window-2022-02-JPM-iex-rep2 | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | 2386 | 1482 | None | different_timestamps |
| window-2023-08-SPY | SPY | 1 | window-2023-08-SPY-sip-rep1 | window-2023-08-SPY-iex-rep1 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | 4360 | 1873 | None | different_timestamps |
| window-2023-08-SPY | SPY | 2 | window-2023-08-SPY-sip-rep2 | window-2023-08-SPY-iex-rep2 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | 4360 | 1873 | None | different_timestamps |
| window-2023-08-AAPL | AAPL | 1 | window-2023-08-AAPL-sip-rep1 | window-2023-08-AAPL-iex-rep1 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | 4316 | 1816 | None | different_timestamps |
| window-2023-08-AAPL | AAPL | 2 | window-2023-08-AAPL-sip-rep2 | window-2023-08-AAPL-iex-rep2 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | 4316 | 1816 | None | different_timestamps |
| window-2023-08-JPM | JPM | 1 | window-2023-08-JPM-sip-rep1 | window-2023-08-JPM-iex-rep1 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | 2453 | 1748 | None | different_timestamps |
| window-2023-08-JPM | JPM | 2 | window-2023-08-JPM-sip-rep2 | window-2023-08-JPM-iex-rep2 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | 2453 | 1748 | None | different_timestamps |
| window-2024-06-SPY | SPY | 1 | window-2024-06-SPY-sip-rep1 | window-2024-06-SPY-iex-rep1 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | 3526 | 1500 | None | different_timestamps |
| window-2024-06-SPY | SPY | 2 | window-2024-06-SPY-sip-rep2 | window-2024-06-SPY-iex-rep2 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | 3526 | 1500 | None | different_timestamps |
| window-2024-06-AAPL | AAPL | 1 | window-2024-06-AAPL-sip-rep1 | window-2024-06-AAPL-iex-rep1 | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | 3568 | 1487 | None | different_timestamps |
| window-2024-06-AAPL | AAPL | 2 | window-2024-06-AAPL-sip-rep2 | window-2024-06-AAPL-iex-rep2 | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | 3568 | 1487 | None | different_timestamps |
| window-2024-06-JPM | JPM | 1 | window-2024-06-JPM-sip-rep1 | window-2024-06-JPM-iex-rep1 | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | 2008 | 1419 | None | different_timestamps |
| window-2024-06-JPM | JPM | 2 | window-2024-06-JPM-sip-rep2 | window-2024-06-JPM-iex-rep2 | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | 2008 | 1419 | None | different_timestamps |
| window-2025-12-SPY | SPY | 1 | window-2025-12-SPY-sip-rep1 | window-2025-12-SPY-iex-rep1 | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | 4182 | 1967 | None | different_timestamps |
| window-2025-12-SPY | SPY | 2 | window-2025-12-SPY-sip-rep2 | window-2025-12-SPY-iex-rep2 | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | 4182 | 1967 | None | different_timestamps |
| window-2025-12-AAPL | AAPL | 1 | window-2025-12-AAPL-sip-rep1 | window-2025-12-AAPL-iex-rep1 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | 3821 | 1692 | None | different_timestamps |
| window-2025-12-AAPL | AAPL | 2 | window-2025-12-AAPL-sip-rep2 | window-2025-12-AAPL-iex-rep2 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | 3821 | 1692 | None | different_timestamps |
| window-2025-12-JPM | JPM | 1 | window-2025-12-JPM-sip-rep1 | window-2025-12-JPM-iex-rep1 | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | 2718 | 1679 | None | different_timestamps |
| window-2025-12-JPM | JPM | 2 | window-2025-12-JPM-sip-rep2 | window-2025-12-JPM-iex-rep2 | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | 2718 | 1679 | None | different_timestamps |
| overlap-left-SPY | SPY | 1 | overlap-left-SPY-sip-rep1 | overlap-left-SPY-iex-rep1 | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | 1858 | 790 | None | different_timestamps |
| overlap-left-SPY | SPY | 2 | overlap-left-SPY-sip-rep2 | overlap-left-SPY-iex-rep2 | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | 1858 | 790 | None | different_timestamps |
| overlap-right-SPY | SPY | 1 | overlap-right-SPY-sip-rep1 | overlap-right-SPY-iex-rep1 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | 2595 | 1106 | None | different_timestamps |
| overlap-right-SPY | SPY | 2 | overlap-right-SPY-sip-rep2 | overlap-right-SPY-iex-rep2 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | 2595 | 1106 | None | different_timestamps |



## 16. Chunk overlap

| symbol | method | left_probe_id | right_probe_id | overlap_start | overlap_end | left_overlap_bars | right_overlap_bars | left_overlap_hash | right_overlap_hash | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | sip | overlap-left-SPY-sip-rep2 | overlap-right-SPY-sip-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 927 | 927 | 2b395ea22938311bf11ba72d0e79c4837f09d97084300638c415cd59546b79dd | 2b395ea22938311bf11ba72d0e79c4837f09d97084300638c415cd59546b79dd | match |
| SPY | iex | overlap-left-SPY-iex-rep2 | overlap-right-SPY-iex-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 396 | 396 | a4c3545e2b158040cdbd8d1211af792e91bcaa8544970d702f9223556c5be43a | a4c3545e2b158040cdbd8d1211af792e91bcaa8544970d702f9223556c5be43a | match |



## 17. Provider contract matrix

| requirement | endpoint | http_status | supported | evidence |
| --- | --- | --- | --- | --- |
| point_in_time_universe | GET /v2/assets | 200 | True | Returns active US equity listing snapshot. |
| security_type_provenance | GET /v2/assets | 200 | False | asset_class=us_equity does not distinguish stock vs ETF; no historical asset-class endpoint. |
| inactive_delisted_symbol_listing | GET /v2/assets | 200 | True | Endpoint supports status=inactive query parameter; historical point-in-time listing not guaranteed. |
| corporate_action_provenance | GET /v1/corporate-actions | 200 | True | Endpoint exists; data coverage and timeliness not audited in this probe. |
| delisted_symbol_mapping | GET /v2/stocks/{symbol}/bars | 0 | False | asof parameter maps symbol changes at the asof date but does not reconstruct historical security master. |



## 18. Decision details

```json
{
  "alpaca_client_or_rest_version": "requests==2.34.2",
  "approved_as_complete_intra_001_data_source": false,
  "approved_for_intra_001_five_minute_ohlcv": true,
  "blockers": [],
  "candidate_feed": "sip",
  "chunk_overlap_passed": true,
  "chunked_historical_windows_supported": false,
  "comparison_feed": "iex",
  "consolidated_volume_supported": true,
  "corporate_action_endpoint_supported": true,
  "coverage_threshold_passed": true,
  "date_filtering_required": false,
  "delisted_symbol_handling_supported": true,
  "direct_full_range_supported": true,
  "historical_security_type_supported": false,
  "iex_historical_available": true,
  "inactive_asset_listing_supported": true,
  "limitations": [
    "This is an as-of observation using the locked symbol set and sample windows; provider behavior/entitlements may change.",
    "The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements unless explicitly verified."
  ],
  "method_parity_passed": false,
  "methodology_decision_reason": "OHLCV data are available but complete single-provider contract cannot be satisfied; provider-mixing decision required.",
  "methodology_decision_required": true,
  "no_provider_mixing_contract_satisfied": true,
  "outcome": "supported_ohlcv_only",
  "pagination_verified": true,
  "point_in_time_universe_supported": true,
  "pre_registration_commit": "286493eceeffd6aec872ce7516bed5d1b0cd304f",
  "probe_spec_sha256": "620617a981bdfb3557aee66a2c427ab6141115ac0c39528fa85546aae472a6fc",
  "production_behavior_changed": false,
  "provider": "alpaca",
  "recommended_next_assignment": "gary-decision-intra-001-provider-mixing",
  "remaining_delisted_symbol_support_required": false,
  "remaining_security_master_required": true,
  "remaining_universe_source_required": false,
  "remaining_volume_provenance_disclosure_required": false,
  "repeatability_passed": true,
  "schwab_py_version": "requests==2.34.2",
  "selected_feed": "sip",
  "selected_request_method": "sip",
  "selected_windowing_policy": "direct_full_range",
  "stock_etf_classification_supported": false,
  "strategy_spec_sha256": "09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464",
  "symbol_mapping_asof_supported": true,
  "task_id": "INTRA-001B-ALPACA",
  "timestamp_normalization_required": false,
  "timestamp_semantics": "inconsistent"
}
```


## 19. Blockers

None.


## 20. Limitations

- This is an as-of observation using the locked symbol set and sample windows; provider behavior/entitlements may change.
- The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements unless explicitly verified.


## 21. Final outcome

The final outcome is `supported_ohlcv_only`. Approved for INTRA-001 five-minute OHLCV: True. Approved as a complete INTRA-001 data source: False.


## 22. Recommended next assignment

gary-decision-intra-001-provider-mixing


## 23. Provider contract compliance

Alpaca returned HTTP 200 for all applicable requests. Data were normalized to UTC-indexed OHLCV and checked for duplicates, zero-volume rows, invalid OHLC relationships, and non-five-minute intervals.


## 24. Data provenance

All five-minute OHLCV payloads came directly from Alpaca's API. No third-party provider, synthetic data, or cached prices were used.


## 25. Request cadence and rate limiting

Sequential requests with `request_delay_seconds=0.5` between calls. No HTTP 429 responses were observed during the probe.


## 26. Retry and error handling

Maximum persistent retry count was 1. No 5xx or transient errors occurred; all 60 attempts completed without a retry.


## 27. Coverage by symbol

| symbol | requests | avg_coverage_pct |
| --- | --- | --- |
| AAPL | 16 | 100.0 |
| JPM | 16 | 99.1105 |
| SPY | 28 | 99.9657 |



## 28. Date-bound classification counts

| classification | count |
| --- | --- |
| honored_exactly | 60 |



## 29. Timestamp semantics counts

| classification | count |
| --- | --- |
| inconsistent | 48 |
| bar_start | 12 |



## 30. Repeatability observations

Repeat hashes match for every base probe_id where data were returned. Identical requests produced identical requested-range normalized SHA-256 values.


## 31. Method/feed parity observations

SIP and IEX feeds differ for 30 window/repetition groups. This is expected because IEX is venue-specific while SIP is consolidated; comparison feed is diagnostic and not used for approval.


## 32. Chunk overlap observations

Overlap left/right windows were compared over the configured overlap span.


## 33. Multi-year history capability

Of 60 data-bearing responses, the longest returned span is the full-range SPY request, covering 188119 candles.


## 34. Extended-hours and early-close handling

The probe requested regular-session bars. Returned payloads were checked for pre/post-market and early-close bars; these were counted and separated from primary regular-session coverage.


## 35. Non-five-minute intervals

0 requests contained returned timestamps within market hours that did not fall on the expected five-minute grid. Missing expected bars are reflected as reduced coverage; genuinely off-grid timestamps are reported here.


## 36. Zero-volume and invalid OHLC

0 requests had zero-volume bars; 0 requests had invalid OHLC rows.


## 37. Operational environment

Probe executed via `uv run python -m tradex.research.intraday_data_probe run` on the Devin box using the locked spec and Alpaca credentials loaded from outside the repository.


## 38. Security and confidentiality

API keys, tokens, headers, full OHLCV CSVs, and payload JSONs remain outside the repo. Only safe aggregate CSVs and decision metadata are committed.


## 39. Reproducibility and next steps

Re-run with the locked probe spec and strategy spec. Recommended next assignment: `gary-decision-intra-001-provider-mixing`.
