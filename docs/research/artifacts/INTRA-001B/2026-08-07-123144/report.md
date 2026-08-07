# INTRA-001B Schwab Five-Minute Data Capability Probe Report

**Task ID:** INTRA-001B-PROBE
**Provider:** schwab
**Outcome:** `not_supported`
**Approved for INTRA-001 five-minute OHLCV:** False
**Approved as complete INTRA-001 data source:** False
**Pre-registration commit:** `09fdbc4`


## 1. Decision summary

- Direct full range supported: False
- Chunked historical windows supported: False
- Selected request method: `none`
- Selected windowing policy: `none`
- Repeatability passed: True
- Method parity passed: True
- Chunk overlap passed: False
- Coverage threshold passed: False



## 2. Research classification

This is a research-only data-capability probe (INTRA-001B-PROBE). It does not implement the INTRA-001 trading setup, detector, backtester, VWAP logic, baselines, gates, or production integration. It does not call account, position, balance, transaction, or order endpoints.


## 3. Specification SHAs

- INTRA-001B probe spec SHA-256: `e97a5a9c99d7b203efcbbc6961777e0adfa4345868f03fe33dd35f483eb41dce`
- INTRA-001 strategy spec SHA-256: `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- Pre-registration commit: `09fdbc4`



## 4. Schwab-py version

`1.5.1`


## 5. Method signatures

- `client.get_price_history_every_five_minutes(symbol, start_datetime=..., end_datetime=..., need_extended_hours_data=False)`
- `client.get_price_history(symbol, frequency_type=Client.PriceHistory.FrequencyType.MINUTE, frequency=Client.PriceHistory.Frequency.EVERY_FIVE_MINUTES, start_datetime=..., end_datetime=..., need_extended_hours_data=False)`


## 6. Credential handling

Schwab OAuth tokens and app credentials are loaded from environment variables and the token file configured by `SCHWAB_TOKEN_PATH` (default `~/.tradex_schwab_token.json`). No credentials, tokens, or HTTP headers are committed or written into this report.


## 7. Request plan

Executed 60 request/repetition combinations across the locked full-range, bounded-window, and overlap probes.


## 8. Results overview

60 of 60 requests returned HTTP 200.


## 9. Request audit

See `request_audit.csv` in the safe artifact bundle.

| probe_id | symbol | method | repetition | requested_eastern_start | requested_eastern_end | requested_utc_start | requested_utc_end | http_status | safe_error_classification | raw_candle_count | normalized_candle_count | raw_earliest_timestamp | raw_latest_timestamp | requested_range_earliest | requested_range_latest | out_of_range_candles | unique_regular_sessions | expected_eligible_sessions | expected_regular_session_bars | returned_regular_session_bars | primary_session_bars | early_close_session_bars | extended_hours_bars | regular_session_coverage_pct | missing_regular_session_bars | duplicate_timestamps | duplicate_bar_rate_pct | zero_volume_bars | zero_volume_rate_pct | invalid_ohlc_rows | non_five_minute_intervals | candle_payload_sha256 | requested_range_normalized_sha256 | date_bound_classification | timestamp_semantics_classification | threshold_result | retry_after_seconds | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-convenience_every_five_minutes-rep1 | SPY | convenience_every_five_minutes | 1 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 2262 | 2262 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 27 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.716297786720322 | 75426 | 0 | 0.0 | 0 | 0.0 | 0 | 0 | 385a716dc174b5e4e5ea756a4532d84a898de1be76c5207ef3422b7bfbe58a4b | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | clipped_to_recent_history | bar_start | failed | None |  |
| full-SPY-convenience_every_five_minutes-rep2 | SPY | convenience_every_five_minutes | 2 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 2262 | 2262 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 27 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.716297786720322 | 75426 | 0 | 0.0 | 0 | 0.0 | 0 | 0 | 385a716dc174b5e4e5ea756a4532d84a898de1be76c5207ef3422b7bfbe58a4b | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | clipped_to_recent_history | bar_start | failed | None |  |
| full-SPY-raw_price_history_five_minutes-rep1 | SPY | raw_price_history_five_minutes | 1 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 2262 | 2262 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 27 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.716297786720322 | 75426 | 0 | 0.0 | 0 | 0.0 | 0 | 0 | 385a716dc174b5e4e5ea756a4532d84a898de1be76c5207ef3422b7bfbe58a4b | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | clipped_to_recent_history | bar_start | failed | None |  |
| full-SPY-raw_price_history_five_minutes-rep2 | SPY | raw_price_history_five_minutes | 2 | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 2022-01-03T05:00:00.000000+0000 | 2026-01-01T04:59:59.999999+0000 | 200 | none | 2262 | 2262 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 2025-11-19T14:30:00.000000+0000 | 2025-12-31T20:55:00.000000+0000 | 0 | 27 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.716297786720322 | 75426 | 0 | 0.0 | 0 | 0.0 | 0 | 0 | 385a716dc174b5e4e5ea756a4532d84a898de1be76c5207ef3422b7bfbe58a4b | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | clipped_to_recent_history | bar_start | failed | None |  |
| window-2022-02-SPY-convenience_every_five_minutes-rep1 | SPY | convenience_every_five_minutes | 1 | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 2022-02-01T05:00:00.000000+0000 | 2022-03-01T04:59:59.999999+0000 | 200 | none | 0 | 0 | None | None | None | None | 0 | 0 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0 | 0.0 | 0 | 0.0 | 0 | 0 | 8a52b0a2a9208177e6b75a950b7a60fcb4c1ac0f264bba6694391cfe45dc866e | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | empty | undetermined | failed | None |  |



## 10. Date-bound classifications

| probe_id | date_bound | threshold |
| --- | --- | --- |
| full-SPY-convenience_every_five_minutes-rep1 | clipped_to_recent_history | failed |
| full-SPY-convenience_every_five_minutes-rep2 | clipped_to_recent_history | failed |
| full-SPY-raw_price_history_five_minutes-rep1 | clipped_to_recent_history | failed |
| full-SPY-raw_price_history_five_minutes-rep2 | clipped_to_recent_history | failed |
| window-2022-02-SPY-convenience_every_five_minutes-rep1 | empty | failed |
| window-2022-02-SPY-convenience_every_five_minutes-rep2 | empty | failed |
| window-2022-02-SPY-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2022-02-SPY-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2022-02-AAPL-convenience_every_five_minutes-rep1 | empty | failed |
| window-2022-02-AAPL-convenience_every_five_minutes-rep2 | empty | failed |
| window-2022-02-AAPL-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2022-02-AAPL-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2022-02-JPM-convenience_every_five_minutes-rep1 | empty | failed |
| window-2022-02-JPM-convenience_every_five_minutes-rep2 | empty | failed |
| window-2022-02-JPM-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2022-02-JPM-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2023-08-SPY-convenience_every_five_minutes-rep1 | empty | failed |
| window-2023-08-SPY-convenience_every_five_minutes-rep2 | empty | failed |
| window-2023-08-SPY-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2023-08-SPY-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2023-08-AAPL-convenience_every_five_minutes-rep1 | empty | failed |
| window-2023-08-AAPL-convenience_every_five_minutes-rep2 | empty | failed |
| window-2023-08-AAPL-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2023-08-AAPL-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2023-08-JPM-convenience_every_five_minutes-rep1 | empty | failed |
| window-2023-08-JPM-convenience_every_five_minutes-rep2 | empty | failed |
| window-2023-08-JPM-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2023-08-JPM-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2024-06-SPY-convenience_every_five_minutes-rep1 | empty | failed |
| window-2024-06-SPY-convenience_every_five_minutes-rep2 | empty | failed |
| window-2024-06-SPY-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2024-06-SPY-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2024-06-AAPL-convenience_every_five_minutes-rep1 | empty | failed |
| window-2024-06-AAPL-convenience_every_five_minutes-rep2 | empty | failed |
| window-2024-06-AAPL-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2024-06-AAPL-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2024-06-JPM-convenience_every_five_minutes-rep1 | empty | failed |
| window-2024-06-JPM-convenience_every_five_minutes-rep2 | empty | failed |
| window-2024-06-JPM-raw_price_history_five_minutes-rep1 | empty | failed |
| window-2024-06-JPM-raw_price_history_five_minutes-rep2 | empty | failed |
| window-2025-12-SPY-convenience_every_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-SPY-convenience_every_five_minutes-rep2 | honored_exactly | passed |
| window-2025-12-SPY-raw_price_history_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-SPY-raw_price_history_five_minutes-rep2 | honored_exactly | passed |
| window-2025-12-AAPL-convenience_every_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-AAPL-convenience_every_five_minutes-rep2 | honored_exactly | passed |
| window-2025-12-AAPL-raw_price_history_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-AAPL-raw_price_history_five_minutes-rep2 | honored_exactly | passed |
| window-2025-12-JPM-convenience_every_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-JPM-convenience_every_five_minutes-rep2 | honored_exactly | passed |
| window-2025-12-JPM-raw_price_history_five_minutes-rep1 | honored_exactly | passed |
| window-2025-12-JPM-raw_price_history_five_minutes-rep2 | honored_exactly | passed |
| overlap-left-SPY-convenience_every_five_minutes-rep1 | empty | failed |
| overlap-left-SPY-convenience_every_five_minutes-rep2 | empty | failed |
| overlap-left-SPY-raw_price_history_five_minutes-rep1 | empty | failed |
| overlap-left-SPY-raw_price_history_five_minutes-rep2 | empty | failed |
| overlap-right-SPY-convenience_every_five_minutes-rep1 | empty | failed |
| overlap-right-SPY-convenience_every_five_minutes-rep2 | empty | failed |
| overlap-right-SPY-raw_price_history_five_minutes-rep1 | empty | failed |
| overlap-right-SPY-raw_price_history_five_minutes-rep2 | empty | failed |



## 11. Coverage summary

| base_probe_id | symbol | method | requested_eastern_start | requested_eastern_end | expected_eligible_sessions | expected_regular_session_bars | returned_regular_session_bars | primary_session_bars | early_close_session_bars | extended_hours_bars | regular_session_coverage_pct | missing_regular_session_bars | duplicate_bar_rate_pct | zero_volume_rate_pct | invalid_ohlc_rows | non_five_minute_intervals | timestamp_semantics_classification | date_bound_classification | threshold_result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.7163 | 75426 | 0.0 | 0.0 | 0 | 0 | bar_start | clipped_to_recent_history | failed |
| full-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2022-01-03T00:00:00.000000-0500 | 2025-12-31T23:59:59.999999-0500 | 994 | 77532 | 2106 | 2106 | 84 | 72 | 2.7163 | 75426 | 0.0 | 0.0 | 0 | 0 | bar_start | clipped_to_recent_history | failed |
| window-2022-02-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2022-02-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2022-02-AAPL-convenience_every_five_minutes | AAPL | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2022-02-AAPL-raw_price_history_five_minutes | AAPL | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2022-02-JPM-convenience_every_five_minutes | JPM | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2022-02-JPM-raw_price_history_five_minutes | JPM | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 | 2022-02-28T23:59:59.999999-0500 | 19 | 1482 | 0 | 0 | 0 | 0 | 0.0 | 1482 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2023-08-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2023-08-01T00:00:00.000000-0400 | 2023-08-31T23:59:59.999999-0400 | 23 | 1794 | 0 | 0 | 0 | 0 | 0.0 | 1794 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |
| window-2023-08-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2023-08-01T00:00:00.000000-0400 | 2023-08-31T23:59:59.999999-0400 | 23 | 1794 | 0 | 0 | 0 | 0 | 0.0 | 1794 | 0.0 | 0.0 | 0 | 0 | undetermined | empty | failed |



## 12. Timestamp semantics

- `bar_start`: 16
- `undetermined`: 44


## 13. Repeatability

| base_probe_id | symbol | method | date_range | repeat_hash_match | rep1_http_status | rep2_http_status | rep1_candle_count | rep2_candle_count | rep1_hash | rep2_hash | rep1_threshold | rep2_threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 2262 | 2262 | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | failed | failed |
| full-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 2262 | 2262 | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | failed | failed |
| window-2022-02-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2022-02-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2022-02-AAPL-convenience_every_five_minutes | AAPL | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2022-02-AAPL-raw_price_history_five_minutes | AAPL | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2022-02-JPM-convenience_every_five_minutes | JPM | convenience_every_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2022-02-JPM-raw_price_history_five_minutes | JPM | raw_price_history_five_minutes | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-AAPL-convenience_every_five_minutes | AAPL | convenience_every_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-AAPL-raw_price_history_five_minutes | AAPL | raw_price_history_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-JPM-convenience_every_five_minutes | JPM | convenience_every_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2023-08-JPM-raw_price_history_five_minutes | JPM | raw_price_history_five_minutes | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-AAPL-convenience_every_five_minutes | AAPL | convenience_every_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-AAPL-raw_price_history_five_minutes | AAPL | raw_price_history_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-JPM-convenience_every_five_minutes | JPM | convenience_every_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2024-06-JPM-raw_price_history_five_minutes | JPM | raw_price_history_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| window-2025-12-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1716 | 1716 | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | passed | passed |
| window-2025-12-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1716 | 1716 | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | passed | passed |
| window-2025-12-AAPL-convenience_every_five_minutes | AAPL | convenience_every_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1712 | 1712 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | passed | passed |
| window-2025-12-AAPL-raw_price_history_five_minutes | AAPL | raw_price_history_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1712 | 1712 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | passed | passed |
| window-2025-12-JPM-convenience_every_five_minutes | JPM | convenience_every_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1696 | 1696 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | passed | passed |
| window-2025-12-JPM-raw_price_history_five_minutes | JPM | raw_price_history_five_minutes | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1696 | 1696 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | passed | passed |
| overlap-left-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| overlap-left-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| overlap-right-SPY-convenience_every_five_minutes | SPY | convenience_every_five_minutes | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |
| overlap-right-SPY-raw_price_history_five_minutes | SPY | raw_price_history_five_minutes | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 0 | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | failed | failed |



## 14. Method parity

| window | symbol | repetition | convenience_probe_id | raw_probe_id | convenience_hash | raw_hash | classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY | SPY | 1 | full-SPY-convenience_every_five_minutes-rep1 | full-SPY-raw_price_history_five_minutes-rep1 | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | identical |
| full-SPY | SPY | 2 | full-SPY-convenience_every_five_minutes-rep2 | full-SPY-raw_price_history_five_minutes-rep2 | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | 6124ab869547181cbbfc1ba44d8579a84865e5a4304900f0477b0499ee44f38d | identical |
| window-2022-02-SPY | SPY | 1 | window-2022-02-SPY-convenience_every_five_minutes-rep1 | window-2022-02-SPY-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2022-02-SPY | SPY | 2 | window-2022-02-SPY-convenience_every_five_minutes-rep2 | window-2022-02-SPY-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2022-02-AAPL | AAPL | 1 | window-2022-02-AAPL-convenience_every_five_minutes-rep1 | window-2022-02-AAPL-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2022-02-AAPL | AAPL | 2 | window-2022-02-AAPL-convenience_every_five_minutes-rep2 | window-2022-02-AAPL-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2022-02-JPM | JPM | 1 | window-2022-02-JPM-convenience_every_five_minutes-rep1 | window-2022-02-JPM-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2022-02-JPM | JPM | 2 | window-2022-02-JPM-convenience_every_five_minutes-rep2 | window-2022-02-JPM-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-SPY | SPY | 1 | window-2023-08-SPY-convenience_every_five_minutes-rep1 | window-2023-08-SPY-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-SPY | SPY | 2 | window-2023-08-SPY-convenience_every_five_minutes-rep2 | window-2023-08-SPY-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-AAPL | AAPL | 1 | window-2023-08-AAPL-convenience_every_five_minutes-rep1 | window-2023-08-AAPL-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-AAPL | AAPL | 2 | window-2023-08-AAPL-convenience_every_five_minutes-rep2 | window-2023-08-AAPL-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-JPM | JPM | 1 | window-2023-08-JPM-convenience_every_five_minutes-rep1 | window-2023-08-JPM-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2023-08-JPM | JPM | 2 | window-2023-08-JPM-convenience_every_five_minutes-rep2 | window-2023-08-JPM-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-SPY | SPY | 1 | window-2024-06-SPY-convenience_every_five_minutes-rep1 | window-2024-06-SPY-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-SPY | SPY | 2 | window-2024-06-SPY-convenience_every_five_minutes-rep2 | window-2024-06-SPY-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-AAPL | AAPL | 1 | window-2024-06-AAPL-convenience_every_five_minutes-rep1 | window-2024-06-AAPL-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-AAPL | AAPL | 2 | window-2024-06-AAPL-convenience_every_five_minutes-rep2 | window-2024-06-AAPL-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-JPM | JPM | 1 | window-2024-06-JPM-convenience_every_five_minutes-rep1 | window-2024-06-JPM-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2024-06-JPM | JPM | 2 | window-2024-06-JPM-convenience_every_five_minutes-rep2 | window-2024-06-JPM-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| window-2025-12-SPY | SPY | 1 | window-2025-12-SPY-convenience_every_five_minutes-rep1 | window-2025-12-SPY-raw_price_history_five_minutes-rep1 | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | identical |
| window-2025-12-SPY | SPY | 2 | window-2025-12-SPY-convenience_every_five_minutes-rep2 | window-2025-12-SPY-raw_price_history_five_minutes-rep2 | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | 27d1b7b09d5a89db8bbd6b42ee5b313f12e3fb2842adbc391011094e4cab0f1e | identical |
| window-2025-12-AAPL | AAPL | 1 | window-2025-12-AAPL-convenience_every_five_minutes-rep1 | window-2025-12-AAPL-raw_price_history_five_minutes-rep1 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | identical |
| window-2025-12-AAPL | AAPL | 2 | window-2025-12-AAPL-convenience_every_five_minutes-rep2 | window-2025-12-AAPL-raw_price_history_five_minutes-rep2 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | 2338711e8261d551a0282f8359b3113d23d3623ea3bb9703e5df6a756bc8f6f8 | identical |
| window-2025-12-JPM | JPM | 1 | window-2025-12-JPM-convenience_every_five_minutes-rep1 | window-2025-12-JPM-raw_price_history_five_minutes-rep1 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | identical |
| window-2025-12-JPM | JPM | 2 | window-2025-12-JPM-convenience_every_five_minutes-rep2 | window-2025-12-JPM-raw_price_history_five_minutes-rep2 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | abf69a2845bb54b00431de254841d48d3f45345d64ff13656b9fd414fbb1b971 | identical |
| overlap-left-SPY | SPY | 1 | overlap-left-SPY-convenience_every_five_minutes-rep1 | overlap-left-SPY-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| overlap-left-SPY | SPY | 2 | overlap-left-SPY-convenience_every_five_minutes-rep2 | overlap-left-SPY-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| overlap-right-SPY | SPY | 1 | overlap-right-SPY-convenience_every_five_minutes-rep1 | overlap-right-SPY-raw_price_history_five_minutes-rep1 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |
| overlap-right-SPY | SPY | 2 | overlap-right-SPY-convenience_every_five_minutes-rep2 | overlap-right-SPY-raw_price_history_five_minutes-rep2 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | not_comparable |



## 15. Chunk overlap

| symbol | method | left_probe_id | right_probe_id | overlap_start | overlap_end | left_overlap_bars | right_overlap_bars | left_overlap_hash | right_overlap_hash | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | convenience_every_five_minutes | overlap-left-SPY-convenience_every_five_minutes-rep2 | overlap-right-SPY-convenience_every_five_minutes-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 0 | 0 |  |  | not_comparable |
| SPY | raw_price_history_five_minutes | overlap-left-SPY-raw_price_history_five_minutes-rep2 | overlap-right-SPY-raw_price_history_five_minutes-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 0 | 0 |  |  | not_comparable |



## 16. Decision details

```json
{
  "approved_as_complete_intra_001_data_source": false,
  "approved_for_intra_001_five_minute_ohlcv": false,
  "blockers": [
    "Schwab did not satisfy the locked coverage, repeatability, method parity, or chunk-overlap requirements.",
    "Chunk overlap test was not comparable because one or both overlap windows contained no requested-range data; deterministic stitching could not be verified."
  ],
  "chunk_overlap_passed": false,
  "chunked_historical_windows_supported": false,
  "coverage_threshold_passed": false,
  "date_filtering_required": false,
  "direct_full_range_supported": false,
  "limitations": [
    "This is an as-of observation using the locked symbol set and sample windows; Schwab behavior/entitlements may change.",
    "The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements."
  ],
  "method_parity_passed": true,
  "outcome": "not_supported",
  "pre_registration_commit": "09fdbc4",
  "probe_spec_sha256": "e97a5a9c99d7b203efcbbc6961777e0adfa4345868f03fe33dd35f483eb41dce",
  "production_behavior_changed": false,
  "provider": "schwab",
  "recommended_next_assignment": "devin/intra-001b-alternative-ohlcv-source",
  "remaining_delisted_symbol_support_required": true,
  "remaining_security_master_required": true,
  "remaining_universe_source_required": true,
  "remaining_volume_provenance_disclosure_required": true,
  "repeatability_passed": true,
  "schwab_py_version": "1.5.1",
  "selected_request_method": "none",
  "selected_windowing_policy": "none",
  "strategy_spec_sha256": "09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464",
  "task_id": "INTRA-001B-PROBE",
  "timestamp_normalization_required": true,
  "timestamp_semantics": "bar_start"
}
```


## 17. Blockers

- Schwab did not satisfy the locked coverage, repeatability, method parity, or chunk-overlap requirements.
- Chunk overlap test was not comparable because one or both overlap windows contained no requested-range data; deterministic stitching could not be verified.


## 18. Limitations

- This is an as-of observation using the locked symbol set and sample windows; Schwab behavior/entitlements may change.
- The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements.


## 19. Final outcome

The final outcome is `not_supported`. Approved for INTRA-001 five-minute OHLCV: False. Approved as a complete INTRA-001 data source: False.


## 20. Recommended next assignment

devin/intra-001b-alternative-ohlcv-source


## 21. Provider contract compliance

Schwab returned HTTP 200 for all requests, with the canonical `candles` payload. Data were normalized to UTC-indexed OHLCV and checked for duplicates, zero-volume rows, invalid OHLC relationships, and non-five-minute intervals.


## 22. Data provenance

All five-minute OHLCV payloads came directly from `schwab-py` calls to Schwab's price-history endpoint. No third-party provider, synthetic data, or cached prices were used.


## 23. Request cadence and rate limiting

Sequential requests with `request_delay_seconds=0.75` between calls. No HTTP 429 responses were observed during the probe.


## 24. Retry and error handling

Maximum persistent retry count was 1. No 5xx or transient errors occurred; all 60 attempts completed without a retry.


## 25. Coverage by symbol

| symbol | requests | avg_coverage_pct |
| --- | --- | --- |
| AAPL | 4 | 100.0 |
| JPM | 4 | 100.0 |
| SPY | 8 | 51.3581 |



## 26. Date-bound classification counts

| classification | count |
| --- | --- |
| empty | 44 |
| honored_exactly | 12 |
| clipped_to_recent_history | 4 |



## 27. Timestamp semantics counts

| classification | count |
| --- | --- |
| bar_start | 16 |



## 28. Repeatability observations

Repeat hashes match for every base probe_id where data were returned. Identical requests produced identical requested-range normalized SHA-256 values.


## 29. Method parity observations

The convenience and raw Schwab methods produced identical requested-range normalized hashes for every comparable window. No material method discrepancy was detected.


## 30. Chunk overlap observations

Overlap windows from 2024-06 were empty because Schwab did not return candles for that range. Consequently, left/right overlap could not be compared and is classified `not_comparable`; this is a missing-data limitation, not a timestamp/value mismatch.


## 31. Multi-year history capability

Of 16 data-bearing responses, the longest returned span is the full-range SPY request, which covered only 4 duplicated repetitions of roughly 2262 candles. Bounded windows from 2022, 2023, and 2024 returned zero candles.


## 32. Clipped vs chunked behavior

The full-range request returned a `clipped_to_recent_history` payload rather than the requested 2022-2025 span. Bounded monthly chunks from prior years returned empty payloads, so bounded chunking cannot reconstruct the required multi-year panel.


## 33. Extended-hours and early-close handling

The probe requested `need_extended_hours_data=False`. Returned payloads still contained some pre/post-market and early-close bars, which were counted and separated from primary regular-session coverage.


## 34. Non-five-minute intervals

0 requests contained returned timestamps within market hours that did not fall on the expected five-minute grid. Missing expected bars are reflected as reduced coverage; genuinely off-grid timestamps are reported here.


## 35. Zero-volume and invalid OHLC

0 requests had zero-volume bars; 0 requests had invalid OHLC rows. The returned Schwab data were structurally well-formed.


## 36. Convenience vs raw method comparison

The convenience and raw Schwab methods produced identical requested-range normalized hashes for every comparable, data-bearing window.


## 37. Operational environment

Probe executed via `uv run python -m tradex.research.intraday_data_probe run` on the Devin box, using the locked spec, `schwab-py==1.5.1`, and the Schwab OAuth token at the default `~/.tradex_schwab_token.json` path.


## 38. Security and confidentiality

OAuth tokens, app keys, headers, full OHLCV CSVs, and payload JSONs remain outside the repo. Only safe aggregate CSVs and decision metadata are committed.


## 39. Reproducibility and next steps

Re-run with `python -m tradex.research.intraday_data_probe run --spec docs/research/specs/INTRA-001B-schwab-probe-v1.json --strategy-spec docs/research/specs/INTRA-001-v1.json`. Recommended next assignment: `devin/intra-001b-alternative-ohlcv-source`.
