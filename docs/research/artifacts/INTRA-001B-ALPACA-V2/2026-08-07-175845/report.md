# INTRA-001B-ALPACA Alpaca Five-Minute Data Capability Probe Report

**Task ID:** INTRA-001B-ALPACA
**Provider:** alpaca
**Outcome:** `supported_ohlcv_only`
**Approved for INTRA-001 five-minute OHLCV:** True
**Approved as complete INTRA-001 data source:** False
**Pre-registration commit:** `340e0921065fc17767cd882393fb3fe543cfcc0b`


## 1. Executive decision

Outcome: `supported_ohlcv_only`. Approved for INTRA-001 five-minute OHLCV: True. Approved as complete single-provider data source: False. Selected feed: `sip`. Selected windowing: `direct_full_range`.


## 2. Research classification

This is a research-only data-capability probe (INTRA-001B-ALPACA-V2). It does not implement the INTRA-001 trading setup, detector, backtester, VWAP logic, baselines, gates, or production integration. No account, position, balance, order, transfer, or transaction endpoints were called.


## 3. Gary v2 approval reference

v2 implementation approved via assignment `pasted-1786122058624.md`: corrected timestamp semantics, pagination audit, direct/chunked independence, SIP/IEX comparator, provider-contract evidence matrix, and Schwab non-regression.


## 4. Starting branch/head

Branch: `devin/intra-001b-alpaca-probe`. Starting head: `bb1730c598c252d4fc6ac5125bf348766a6455f9`.


## 5. v1 preregistration SHA

`286493eceeffd6aec872ce7516bed5d1b0cd304f` (preserved unchanged; v1 formal disposition invalid / not promotion-decision-grade).


## 6. v2 preregistration SHA

`340e0921065fc17767cd882393fb3fe543cfcc0b`


## 7. Strategy spec SHA

`09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`


## 8. v2 probe spec SHA

`f0ee4f8bfca77eae39432974064d3335ae50f1fbd4b57db2ee97dbb553b8fd1e`


## 9. Provider/client version

`requests==2.34.2`


## 10. Documentation reviewed

Reviewed `docs/research/specs/INTRA-001-v1.json`, `docs/research/specs/INTRA-001B-alpaca-probe-v2.json`, `docs/research/INTRA-001B-ALPACA-DATA-PROBE-V2-PROPOSAL.md`, `docs/PROJECT-TRACKER.md`, Alpaca Basic/free SIP/IEX endpoint documentation, and `exchange_calendars` XNYS calendar.


## 11. Credential handling

Alpaca `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` were loaded from environment variables outside the repository. No credentials, tokens, headers, account data, or absolute paths are committed.


## 12. Request plan

Executed 60 request/repetition combinations across the locked full-range SPY 2022-01-03..2025-12-31, four bounded monthly windows (2022-02, 2023-08, 2024-06, 2025-12) for SPY/AAPL/JPM, and the 2024-06 overlap probe. Candidate feed `sip`, comparison feed `iex`.


## 13. Pagination results

| base_probe_id | symbol | method | repetition | http_status | raw_candle_count | page_count | pagination_complete | repeated_page_token | pagination_cycle_detected | page_bar_counts | token_sequence_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-sip | SPY | sip | 1 | 200 | 188119 | 83 | True | False | False | 2225,2127,2221,2100,2226,2288,2205,2171,2178,2175,2210,2228,2297,2265,2219,2121,2142,2152,2153,2214,2204,2258,2204,2193,2252,2124,2274,2288,2318,2266,2358,2394,2381,2336,2348,2406,2276,2296,2288,2415,2398,2409,2388,2377,2398,2378,2416,2277,2429,2415,2449,2509,2312,2255,2422,2412,2400,2385,2340,2433,2403,2411,2322,2442,2206,2272,2078,2183,2236,2193,2239,2273,2305,2238,2350,2363,2315,2253,2209,2075,2120,2105,930 | c5372b48a4683a241d85a0438b8fc7ce304cbf02e24f5e89035c304ae7d13602 |
| full-SPY-sip | SPY | sip | 2 | 200 | 188119 | 83 | True | False | False | 2225,2127,2221,2100,2226,2288,2205,2171,2178,2175,2210,2228,2297,2265,2219,2121,2142,2152,2153,2214,2204,2258,2204,2193,2252,2124,2274,2288,2318,2266,2358,2394,2381,2336,2348,2406,2276,2296,2288,2415,2398,2409,2388,2377,2398,2378,2416,2277,2429,2415,2449,2509,2312,2255,2422,2412,2400,2385,2340,2433,2403,2411,2322,2442,2206,2272,2078,2183,2236,2193,2239,2273,2305,2238,2350,2363,2315,2253,2209,2075,2120,2105,930 | c5372b48a4683a241d85a0438b8fc7ce304cbf02e24f5e89035c304ae7d13602 |
| full-SPY-iex | SPY | iex | 1 | 200 | 83287 | 40 | True | False | False | 2175,2166,2149,2178,2168,2149,2128,2148,2141,2144,2119,2115,2121,2125,2115,2120,2071,2043,2047,2059,2043,2046,2074,2167,2194,2130,2100,2170,2105,2091,2101,2079,2121,2111,2072,2124,2077,2117,2220,664 | 9085cd2f841b544b2c067ba8c89fae5ed5dbae3a27b61f3b2570df858e8da9f7 |
| full-SPY-iex | SPY | iex | 2 | 200 | 83287 | 40 | True | False | False | 2175,2166,2149,2178,2168,2149,2128,2148,2141,2144,2119,2115,2121,2125,2115,2120,2071,2043,2047,2059,2043,2046,2074,2167,2194,2130,2100,2170,2105,2091,2101,2079,2121,2111,2072,2124,2077,2117,2220,664 | 9085cd2f841b544b2c067ba8c89fae5ed5dbae3a27b61f3b2570df858e8da9f7 |
| window-2022-02-SPY-sip | SPY | sip | 1 | 200 | 3530 | 2 | True | False | False | 2227,1303 | 24cb6886ad8c20cadaa106c08bc63078d23757aaa3c88601dc38c7fe6be9c955 |
| window-2022-02-SPY-sip | SPY | sip | 2 | 200 | 3530 | 2 | True | False | False | 2227,1303 | 24cb6886ad8c20cadaa106c08bc63078d23757aaa3c88601dc38c7fe6be9c955 |
| window-2022-02-SPY-iex | SPY | iex | 1 | 200 | 1654 | 1 | True | False | False | 1654 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-SPY-iex | SPY | iex | 2 | 200 | 1654 | 1 | True | False | False | 1654 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-AAPL-sip | AAPL | sip | 1 | 200 | 3465 | 2 | True | False | False | 2317,1148 | 4c08b818d12855853e7410aaae10ca8be63df42f672d1fd466a7157eec04cb11 |
| window-2022-02-AAPL-sip | AAPL | sip | 2 | 200 | 3465 | 2 | True | False | False | 2317,1148 | 4c08b818d12855853e7410aaae10ca8be63df42f672d1fd466a7157eec04cb11 |
| window-2022-02-AAPL-iex | AAPL | iex | 1 | 200 | 1508 | 1 | True | False | False | 1508 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-AAPL-iex | AAPL | iex | 2 | 200 | 1508 | 1 | True | False | False | 1508 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-JPM-sip | JPM | sip | 1 | 200 | 2386 | 1 | True | False | False | 2386 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-JPM-sip | JPM | sip | 2 | 200 | 2386 | 1 | True | False | False | 2386 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-JPM-iex | JPM | iex | 1 | 200 | 1482 | 1 | True | False | False | 1482 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2022-02-JPM-iex | JPM | iex | 2 | 200 | 1482 | 1 | True | False | False | 1482 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-SPY-sip | SPY | sip | 1 | 200 | 4360 | 2 | True | False | False | 2315,2045 | 73f4faf84b06e3c9d995ccc61e94cacfca79b2965246f009d8593f72ebc79063 |
| window-2023-08-SPY-sip | SPY | sip | 2 | 200 | 4360 | 2 | True | False | False | 2315,2045 | 73f4faf84b06e3c9d995ccc61e94cacfca79b2965246f009d8593f72ebc79063 |
| window-2023-08-SPY-iex | SPY | iex | 1 | 200 | 1873 | 1 | True | False | False | 1873 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-SPY-iex | SPY | iex | 2 | 200 | 1873 | 1 | True | False | False | 1873 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-AAPL-sip | AAPL | sip | 1 | 200 | 4316 | 2 | True | False | False | 2339,1977 | ceaa60c0f44befc69f1cc9dc77cc9de2e7c073aaa8efc2ac8e5a2fc8810874fc |
| window-2023-08-AAPL-sip | AAPL | sip | 2 | 200 | 4316 | 2 | True | False | False | 2339,1977 | ceaa60c0f44befc69f1cc9dc77cc9de2e7c073aaa8efc2ac8e5a2fc8810874fc |
| window-2023-08-AAPL-iex | AAPL | iex | 1 | 200 | 1816 | 1 | True | False | False | 1816 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-AAPL-iex | AAPL | iex | 2 | 200 | 1816 | 1 | True | False | False | 1816 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-JPM-sip | JPM | sip | 1 | 200 | 2453 | 1 | True | False | False | 2453 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-JPM-sip | JPM | sip | 2 | 200 | 2453 | 1 | True | False | False | 2453 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-JPM-iex | JPM | iex | 1 | 200 | 1748 | 1 | True | False | False | 1748 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2023-08-JPM-iex | JPM | iex | 2 | 200 | 1748 | 1 | True | False | False | 1748 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-SPY-sip | SPY | sip | 1 | 200 | 3526 | 2 | True | False | False | 2459,1067 | 65c3ded141a9e92339871b0237deaa92638d63ea7600a616cee464382ed361b0 |
| window-2024-06-SPY-sip | SPY | sip | 2 | 200 | 3526 | 2 | True | False | False | 2459,1067 | 65c3ded141a9e92339871b0237deaa92638d63ea7600a616cee464382ed361b0 |
| window-2024-06-SPY-iex | SPY | iex | 1 | 200 | 1500 | 1 | True | False | False | 1500 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-SPY-iex | SPY | iex | 2 | 200 | 1500 | 1 | True | False | False | 1500 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-AAPL-sip | AAPL | sip | 1 | 200 | 3568 | 2 | True | False | False | 2352,1216 | d64cae62bba525e1bfb9ad5f1c9cbc863096bc39e4277242ccc3d6494497b8f0 |
| window-2024-06-AAPL-sip | AAPL | sip | 2 | 200 | 3568 | 2 | True | False | False | 2352,1216 | d64cae62bba525e1bfb9ad5f1c9cbc863096bc39e4277242ccc3d6494497b8f0 |
| window-2024-06-AAPL-iex | AAPL | iex | 1 | 200 | 1487 | 1 | True | False | False | 1487 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-AAPL-iex | AAPL | iex | 2 | 200 | 1487 | 1 | True | False | False | 1487 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-JPM-sip | JPM | sip | 1 | 200 | 2008 | 1 | True | False | False | 2008 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-JPM-sip | JPM | sip | 2 | 200 | 2008 | 1 | True | False | False | 2008 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-JPM-iex | JPM | iex | 1 | 200 | 1419 | 1 | True | False | False | 1419 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2024-06-JPM-iex | JPM | iex | 2 | 200 | 1419 | 1 | True | False | False | 1419 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-SPY-sip | SPY | sip | 1 | 200 | 4182 | 2 | True | False | False | 2120,2062 | 5f4ac81393a87bda07c163dbaab4986e3c33977f2ddbfafcacf5a32e85dc7354 |
| window-2025-12-SPY-sip | SPY | sip | 2 | 200 | 4182 | 2 | True | False | False | 2120,2062 | 5f4ac81393a87bda07c163dbaab4986e3c33977f2ddbfafcacf5a32e85dc7354 |
| window-2025-12-SPY-iex | SPY | iex | 1 | 200 | 1967 | 1 | True | False | False | 1967 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-SPY-iex | SPY | iex | 2 | 200 | 1967 | 1 | True | False | False | 1967 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-AAPL-sip | AAPL | sip | 1 | 200 | 3821 | 2 | True | False | False | 2659,1162 | 28451f5fca75d8a629ff9ff1ad9f07ca90dc18332b8b385877a1b0a624bad084 |
| window-2025-12-AAPL-sip | AAPL | sip | 2 | 200 | 3821 | 2 | True | False | False | 2659,1162 | 28451f5fca75d8a629ff9ff1ad9f07ca90dc18332b8b385877a1b0a624bad084 |
| window-2025-12-AAPL-iex | AAPL | iex | 1 | 200 | 1692 | 1 | True | False | False | 1692 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-AAPL-iex | AAPL | iex | 2 | 200 | 1692 | 1 | True | False | False | 1692 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-JPM-sip | JPM | sip | 1 | 200 | 2718 | 2 | True | False | False | 2661,57 | d1296e1c79e4823f3a5280336ad5abc6fd3ff93eb85a7d314140ffd7a829eb47 |
| window-2025-12-JPM-sip | JPM | sip | 2 | 200 | 2718 | 2 | True | False | False | 2661,57 | d1296e1c79e4823f3a5280336ad5abc6fd3ff93eb85a7d314140ffd7a829eb47 |
| window-2025-12-JPM-iex | JPM | iex | 1 | 200 | 1679 | 1 | True | False | False | 1679 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| window-2025-12-JPM-iex | JPM | iex | 2 | 200 | 1679 | 1 | True | False | False | 1679 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-left-SPY-sip | SPY | sip | 1 | 200 | 1858 | 1 | True | False | False | 1858 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-left-SPY-sip | SPY | sip | 2 | 200 | 1858 | 1 | True | False | False | 1858 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-left-SPY-iex | SPY | iex | 1 | 200 | 790 | 1 | True | False | False | 790 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-left-SPY-iex | SPY | iex | 2 | 200 | 790 | 1 | True | False | False | 790 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-right-SPY-sip | SPY | sip | 1 | 200 | 2595 | 2 | True | False | False | 2473,122 | a53664a23fe9ed97875ab22da8575112bc30c02069784eb76b8d83e88726fa1d |
| overlap-right-SPY-sip | SPY | sip | 2 | 200 | 2595 | 2 | True | False | False | 2473,122 | a53664a23fe9ed97875ab22da8575112bc30c02069784eb76b8d83e88726fa1d |
| overlap-right-SPY-iex | SPY | iex | 1 | 200 | 1106 | 1 | True | False | False | 1106 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |
| overlap-right-SPY-iex | SPY | iex | 2 | 200 | 1106 | 1 | True | False | False | 1106 | f018c0dc31b6efa757d7584f5a2adf949265670294b13dd424ca80e6eec3c333 |



## 14. Full-range SIP result

2 of 2 HTTP 200; 2 with data; avg coverage 100.0%. Full-range SIP rep1: 188119 raw bars, 77532 primary bars, 100.0% coverage, 83 pages.


## 15. Full-range IEX result

2 of 2 HTTP 200; 2 with data; avg coverage 99.8065%. Full-range IEX rep1: 83287 raw bars, 77382 primary bars, 99.8065% coverage, 40 pages.


## 16. Bounded SIP results

| probe_id | symbol | repetition | http_status | raw_bars | primary_bars | coverage_pct | timestamp_semantics | pagination_complete | page_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| window-2022-02-SPY-sip-rep1 | SPY | 1 | 200 | 3530 | 1482 | 100.0 | bar_start | True | 2 |
| window-2022-02-SPY-sip-rep2 | SPY | 2 | 200 | 3530 | 1482 | 100.0 | bar_start | True | 2 |
| window-2022-02-AAPL-sip-rep1 | AAPL | 1 | 200 | 3465 | 1482 | 100.0 | bar_start | True | 2 |
| window-2022-02-AAPL-sip-rep2 | AAPL | 2 | 200 | 3465 | 1482 | 100.0 | bar_start | True | 2 |
| window-2022-02-JPM-sip-rep1 | JPM | 1 | 200 | 2386 | 1482 | 100.0 | bar_start | True | 1 |
| window-2022-02-JPM-sip-rep2 | JPM | 2 | 200 | 2386 | 1482 | 100.0 | bar_start | True | 1 |
| window-2023-08-SPY-sip-rep1 | SPY | 1 | 200 | 4360 | 1794 | 100.0 | bar_start | True | 2 |
| window-2023-08-SPY-sip-rep2 | SPY | 2 | 200 | 4360 | 1794 | 100.0 | bar_start | True | 2 |
| window-2023-08-AAPL-sip-rep1 | AAPL | 1 | 200 | 4316 | 1794 | 100.0 | bar_start | True | 2 |
| window-2023-08-AAPL-sip-rep2 | AAPL | 2 | 200 | 4316 | 1794 | 100.0 | bar_start | True | 2 |
| window-2023-08-JPM-sip-rep1 | JPM | 1 | 200 | 2453 | 1794 | 100.0 | bar_start | True | 1 |
| window-2023-08-JPM-sip-rep2 | JPM | 2 | 200 | 2453 | 1794 | 100.0 | bar_start | True | 1 |
| window-2024-06-SPY-sip-rep1 | SPY | 1 | 200 | 3526 | 1482 | 100.0 | bar_start | True | 2 |
| window-2024-06-SPY-sip-rep2 | SPY | 2 | 200 | 3526 | 1482 | 100.0 | bar_start | True | 2 |
| window-2024-06-AAPL-sip-rep1 | AAPL | 1 | 200 | 3568 | 1482 | 100.0 | bar_start | True | 2 |
| window-2024-06-AAPL-sip-rep2 | AAPL | 2 | 200 | 3568 | 1482 | 100.0 | bar_start | True | 2 |
| window-2024-06-JPM-sip-rep1 | JPM | 1 | 200 | 2008 | 1482 | 100.0 | bar_start | True | 1 |
| window-2024-06-JPM-sip-rep2 | JPM | 2 | 200 | 2008 | 1482 | 100.0 | bar_start | True | 1 |
| window-2025-12-SPY-sip-rep1 | SPY | 1 | 200 | 4182 | 1638 | 100.0 | bar_start | True | 2 |
| window-2025-12-SPY-sip-rep2 | SPY | 2 | 200 | 4182 | 1638 | 100.0 | bar_start | True | 2 |
| window-2025-12-AAPL-sip-rep1 | AAPL | 1 | 200 | 3821 | 1638 | 100.0 | bar_start | True | 2 |
| window-2025-12-AAPL-sip-rep2 | AAPL | 2 | 200 | 3821 | 1638 | 100.0 | bar_start | True | 2 |
| window-2025-12-JPM-sip-rep1 | JPM | 1 | 200 | 2718 | 1638 | 100.0 | bar_start | True | 2 |
| window-2025-12-JPM-sip-rep2 | JPM | 2 | 200 | 2718 | 1638 | 100.0 | bar_start | True | 2 |



## 17. Bounded IEX results

| probe_id | symbol | repetition | http_status | raw_bars | primary_bars | coverage_pct | timestamp_semantics | pagination_complete | page_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| window-2022-02-SPY-iex-rep1 | SPY | 1 | 200 | 1654 | 1482 | 100.0 | bar_start | True | 1 |
| window-2022-02-SPY-iex-rep2 | SPY | 2 | 200 | 1654 | 1482 | 100.0 | bar_start | True | 1 |
| window-2022-02-AAPL-iex-rep1 | AAPL | 1 | 200 | 1508 | 1482 | 100.0 | bar_start | True | 1 |
| window-2022-02-AAPL-iex-rep2 | AAPL | 2 | 200 | 1508 | 1482 | 100.0 | bar_start | True | 1 |
| window-2022-02-JPM-iex-rep1 | JPM | 1 | 200 | 1482 | 1481 | 99.9325 | bar_start | True | 1 |
| window-2022-02-JPM-iex-rep2 | JPM | 2 | 200 | 1482 | 1481 | 99.9325 | bar_start | True | 1 |
| window-2023-08-SPY-iex-rep1 | SPY | 1 | 200 | 1873 | 1794 | 100.0 | bar_start | True | 1 |
| window-2023-08-SPY-iex-rep2 | SPY | 2 | 200 | 1873 | 1794 | 100.0 | bar_start | True | 1 |
| window-2023-08-AAPL-iex-rep1 | AAPL | 1 | 200 | 1816 | 1794 | 100.0 | bar_start | True | 1 |
| window-2023-08-AAPL-iex-rep2 | AAPL | 2 | 200 | 1816 | 1794 | 100.0 | bar_start | True | 1 |
| window-2023-08-JPM-iex-rep1 | JPM | 1 | 200 | 1748 | 1746 | 97.3244 | bar_start | True | 1 |
| window-2023-08-JPM-iex-rep2 | JPM | 2 | 200 | 1748 | 1746 | 97.3244 | bar_start | True | 1 |
| window-2024-06-SPY-iex-rep1 | SPY | 1 | 200 | 1500 | 1481 | 99.9325 | ambiguous | True | 1 |
| window-2024-06-SPY-iex-rep2 | SPY | 2 | 200 | 1500 | 1481 | 99.9325 | ambiguous | True | 1 |
| window-2024-06-AAPL-iex-rep1 | AAPL | 1 | 200 | 1487 | 1482 | 100.0 | bar_start | True | 1 |
| window-2024-06-AAPL-iex-rep2 | AAPL | 2 | 200 | 1487 | 1482 | 100.0 | bar_start | True | 1 |
| window-2024-06-JPM-iex-rep1 | JPM | 1 | 200 | 1419 | 1419 | 95.749 | undetermined | True | 1 |
| window-2024-06-JPM-iex-rep2 | JPM | 2 | 200 | 1419 | 1419 | 95.749 | undetermined | True | 1 |
| window-2025-12-SPY-iex-rep1 | SPY | 1 | 200 | 1967 | 1638 | 100.0 | bar_start | True | 1 |
| window-2025-12-SPY-iex-rep2 | SPY | 2 | 200 | 1967 | 1638 | 100.0 | bar_start | True | 1 |
| window-2025-12-AAPL-iex-rep1 | AAPL | 1 | 200 | 1692 | 1638 | 100.0 | bar_start | True | 1 |
| window-2025-12-AAPL-iex-rep2 | AAPL | 2 | 200 | 1692 | 1638 | 100.0 | bar_start | True | 1 |
| window-2025-12-JPM-iex-rep1 | JPM | 1 | 200 | 1679 | 1636 | 99.8779 | bar_start | True | 1 |
| window-2025-12-JPM-iex-rep2 | JPM | 2 | 200 | 1679 | 1636 | 99.8779 | bar_start | True | 1 |



## 18. Regular-session expected-grid coverage

Coverage threshold: 95.0%. Candidate regular-session coverage computed only on the bar-start grid (09:30..15:55 ET, excluding early closes). See `coverage_summary.csv` for per-window details.


## 19. Timestamp-semantics result

Aggregate classification: `bar_start`. Timestamp-semantics passed: True. Candidate approval requires `bar_start`.


## 20. Zero-volume result

Max zero-volume rate 0.0% (threshold 10.0%). Passed: True.


## 21. Invalid-OHLC result

Max invalid OHLC rows 0. Passed: True.


## 22. Duplicate result

Max duplicate rate 0.0% (threshold 1.0%). Passed: True.


## 23. Repeatability

Repeatability passed: True. Pagination repeatability passed: True.

| base_probe_id | symbol | method | date_range | repeat_hash_match | rep1_http_status | rep2_http_status | rep1_primary_session_bars | rep2_primary_session_bars | rep1_hash | rep2_hash | rep1_threshold | rep2_threshold | rep1_page_count | rep2_page_count | rep1_pagination_complete | rep2_pagination_complete | rep1_repeated_page_token | rep2_repeated_page_token | rep1_pagination_cycle_detected | rep2_pagination_cycle_detected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full-SPY-sip | SPY | sip | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 77532 | 77532 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | 5117331463e60936af12fb412afda02a654cbf8b4d983cce980fb9d7297db434 | passed | passed | 83 | 83 | True | True | False | False | False | False |
| full-SPY-iex | SPY | iex | 2022-01-03T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 77382 | 77382 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | 26f0d5c971b8c966a2b37b898822892e24a4c0e397ce65394b8d1d73ecf19a96 | passed | passed | 40 | 40 | True | True | False | False | False | False |
| window-2022-02-SPY-sip | SPY | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | 25944df2ffec820fd3ce4cc2dee1d765aa3ac8ec67e9d5c0339bb94b3be44fcd | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2022-02-SPY-iex | SPY | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | b9f7646953a722b4be2471a18e114b244fdf1125b79a701ac90b7cd4422a97f4 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2022-02-AAPL-sip | AAPL | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | 6c3df8d3f8b09e10d1b242991c3b38e05176c6f1f8e97e1b8cbc59d5555f9f47 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2022-02-AAPL-iex | AAPL | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | 8bd3f98ac828d4f1783f7c50849e3022211fafeee0536d1e0762c2ca35a3c25c | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2022-02-JPM-sip | JPM | sip | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1482 | 1482 | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | cc4c285c15c0e1107b95ccae91af758026ea94e9c7de83d862d64b0253d7bc4c | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2022-02-JPM-iex | JPM | iex | 2022-02-01T00:00:00.000000-0500 to 2022-02-28T23:59:59.999999-0500 | True | 200 | 200 | 1481 | 1481 | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | 2ac6f27bb72b7c96e5e630b0fb2f6f7f5976b9f5173f7044074f1b1a032c6386 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2023-08-SPY-sip | SPY | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1794 | 1794 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | b85fffbf46ec846b11653142a64257d41af7ebbfb5149f127d2f17cecd5e0009 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2023-08-SPY-iex | SPY | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1794 | 1794 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | 5add82af197f176c7b95fbb7a9b82bca446a57ac4338b6084565e48d5f093a67 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2023-08-AAPL-sip | AAPL | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1794 | 1794 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | 9c419965116dc8e515e978637a3eb726f0e0cb9ea58ed4910a2fd993af891361 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2023-08-AAPL-iex | AAPL | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1794 | 1794 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | 56d09e4fd2d48619e76bd67bd9c6ff95b714bf2992a47b2ae04f6597a0831809 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2023-08-JPM-sip | JPM | sip | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1794 | 1794 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | 33347599f1d778bb0b663ca8591e13acee9d2966643fc96443f6fcafcba4b393 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2023-08-JPM-iex | JPM | iex | 2023-08-01T00:00:00.000000-0400 to 2023-08-31T23:59:59.999999-0400 | True | 200 | 200 | 1746 | 1746 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | 45979221ffef7a37f949cc6fb1204cc1e1bf538f8601d11b871815700c9b5d16 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2024-06-SPY-sip | SPY | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1482 | 1482 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | 26790ac27d07469dedda704ca10d19201674962e3d7c2a9c005b00d4515fc4b1 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2024-06-SPY-iex | SPY | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1481 | 1481 | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | e086676ee0be43cb7db4508bf68e87ce1e46fc971c96c70838e35d67f886f8cc | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2024-06-AAPL-sip | AAPL | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1482 | 1482 | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | b7181cbf327971d7a78d31a380641535e202ddac2b2e9cfac54fa0678884877d | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2024-06-AAPL-iex | AAPL | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1482 | 1482 | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | 0896a01d62783bd3b33c90d7a316600bbbc718ab1a93633e1553a21194cffaae | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2024-06-JPM-sip | JPM | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1482 | 1482 | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | 8445c484e6c04d455841cb16a4919d1095e3a00ef66b16c60c580e214505dd1f | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2024-06-JPM-iex | JPM | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1419 | 1419 | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | 0b9f973d968d9d2a96c0c972ab07239077621be9808fc1885e368da3b799ca31 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2025-12-SPY-sip | SPY | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1638 | 1638 | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | bad02a6c83262190b953806453dfeea6b910389566cdca1e5c2b8bae626408cd | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2025-12-SPY-iex | SPY | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1638 | 1638 | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | 6544e4776acd973ed8e0b0cef109f30c8398ecc78308e2c989efc85000277b7e | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2025-12-AAPL-sip | AAPL | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1638 | 1638 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | 7cb028f015d41d6a80d465738d6e0a31b5e01dedda0b572a7d8a47ff0b09a010 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2025-12-AAPL-iex | AAPL | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1638 | 1638 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | ea73fb40db69c128067d5b47b4564d37a38d0300fcbcb4a19224d015312e3865 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| window-2025-12-JPM-sip | JPM | sip | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1638 | 1638 | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | 5631d686c29eb9a877eaf8c164863158275f4efcd5de7b81ee00631113c82e1d | passed | passed | 2 | 2 | True | True | False | False | False | False |
| window-2025-12-JPM-iex | JPM | iex | 2025-12-01T00:00:00.000000-0500 to 2025-12-31T23:59:59.999999-0500 | True | 200 | 200 | 1636 | 1636 | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | c94e1d4ab56cebe6e21c3a034d182d9ffc02ff0f75d503bb90c2fe56ea54837c | passed | passed | 1 | 1 | True | True | False | False | False | False |
| overlap-left-SPY-sip | SPY | sip | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 780 | 780 | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | cf7deecf81c996b2b5d918c615d50447236ca0dc1bf22c1d5e038fb3511a45da | passed | passed | 1 | 1 | True | True | False | False | False | False |
| overlap-left-SPY-iex | SPY | iex | 2024-06-03T00:00:00.000000-0400 to 2024-06-14T23:59:59.999999-0400 | True | 200 | 200 | 779 | 779 | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | 917dbca1b1e1552feee94022f54f44c2ef74c489ff1af08e9e4ddc4fab50d0a2 | passed | passed | 1 | 1 | True | True | False | False | False | False |
| overlap-right-SPY-sip | SPY | sip | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1092 | 1092 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | 683bfa975143343348165579e178f235af2b1c3f31b9fe4d77169200382cbe33 | passed | passed | 2 | 2 | True | True | False | False | False | False |
| overlap-right-SPY-iex | SPY | iex | 2024-06-10T00:00:00.000000-0400 to 2024-06-28T23:59:59.999999-0400 | True | 200 | 200 | 1091 | 1091 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | 8140907e32b391ac6caa32e7c52dc5cd7af66668996d46ab8110502901dc7fb8 | passed | passed | 1 | 1 | True | True | False | False | False | False |



## 24. Chunk overlap

Chunk overlap passed: True.

| symbol | method | left_probe_id | right_probe_id | overlap_start | overlap_end | left_overlap_bars | right_overlap_bars | left_overlap_hash | right_overlap_hash | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | sip | overlap-left-SPY-sip-rep2 | overlap-right-SPY-sip-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 927 | 927 | 2b395ea22938311bf11ba72d0e79c4837f09d97084300638c415cd59546b79dd | 2b395ea22938311bf11ba72d0e79c4837f09d97084300638c415cd59546b79dd | match |
| SPY | iex | overlap-left-SPY-iex-rep2 | overlap-right-SPY-iex-rep2 | 2024-06-10T04:00:00.000000+0000 | 2024-06-15T03:59:59.999999+0000 | 396 | 396 | a4c3545e2b158040cdbd8d1211af792e91bcaa8544970d702f9223556c5be43a | a4c3545e2b158040cdbd8d1211af792e91bcaa8544970d702f9223556c5be43a | match |



## 25. Direct support

`direct_full_range_supported`: True. Full-range SPY 2022-01-03..2025-12-31 returned via direct pagination.


## 26. Chunked support

`chunked_historical_windows_supported`: True. Bounded monthly windows evaluated independently.


## 27. Selected windowing

`selected_windowing_policy`: `direct_full_range`. Direct full range is preferred when both access patterns pass.


## 28. SIP approval

`approved_for_intra_001_five_minute_ohlcv`: True. Only the candidate feed `sip` can be approved.


## 29. IEX diagnostic result

`iex_historical_available`: True. IEX is used only as a diagnostic comparison feed, never as the selected source.


## 30. SIP/IEX timestamp overlap

Paired primary-grid timestamps: 77382. Expected-grid timestamps: 77532. Overlap: 99.80653149667235%.


## 31. SIP/IEX volume comparison

Total SIP paired regular-session volume: 64897949943.0. Total IEX paired regular-session volume: 1257122390.0. Total-volume IEX/SIP ratio: 0.019371. Median paired-bar IEX/SIP volume ratio: 0.017899.


## 32. OHLC difference diagnostic

OHLC difference flag: True. OHLC difference count: 77240. Classification: `different_ohlc`.


## 33. Active-assets evidence

supported=True; evidence_type=live_evidence; limitation=Current listing only.


## 34. Inactive-assets evidence

supported=True; evidence_type=live_evidence; limitation=Inactive listing is current, not historical PIT.


## 35. Corporate-actions evidence

supported=True; evidence_type=live_evidence; limitation=Reachability does not imply historical completeness.


## 36. Point-in-time universe assessment

supported=False; evidence_type=live_evidence; limitation=Active snapshot is not a historical point-in-time universe.


## 37. Monthly membership reproducibility

supported=False; evidence_type=unproven; limitation=No historical PIT membership endpoint was exercised.


## 38. Historical security-type assessment

supported=False; evidence_type=unproven; limitation=Assets API returns current classification only.


## 39. Stock/ETF assessment

supported=False; evidence_type=unproven; limitation=asset_class=us_equity does not distinguish stocks from ETFs.


## 40. Excluded-security-type assessment

supported=False; evidence_type=unproven; limitation=asset_class=us_equity does not expose warrant/right/unit/preferred classification.


## 41. Delisted-symbol assessment

supported=False; evidence_type=unproven; limitation=asof parameter maps symbol at asof date; does not reconstruct historical security master.


## 42. Symbol/asof mapping

supported=True; evidence_type=documented_capability; limitation=asof is a query parameter, not a historical security master.; source=Alpaca Stock Bars API reference, https://docs.alpaca.markets/us/reference/stockbars (reviewed 2026-08-08) (asof parameter); request used asof=2025-12-31


## 43. Consolidated-volume provenance

supported=False; evidence_type=live_evidence; limitation=Paired SIP/IEX volume differs; explicit consolidated/venue disclosure not captured.


## 44. Provider-contract matrix

| requirement | endpoint | http_status | supported | evidence_type | limitation | source |
| --- | --- | --- | --- | --- | --- | --- |
| ohlcv_five_minute_history | GET /v2/stocks/{symbol}/bars | 200 | True | live_evidence |  | probe bars requests |
| regular_session_history | GET /v2/stocks/{symbol}/bars | 200 | True | live_evidence | Requires bar-start timestamps and complete regular-session coverage. | probe bars requests |
| timestamp_convention | GET /v2/stocks/{symbol}/bars | 200 | True | live_evidence | Classified from returned timestamps; documentation not audited. | probe bars requests |
| adjustment_raw | GET /v2/stocks/{symbol}/bars | 200 | False | documented_capability | Parameter was sent; actual adjustment basis not independently verified. | Alpaca Stock Bars API reference, https://docs.alpaca.markets/us/reference/stockbars (reviewed 2026-08-08) (adjustment parameter) |
| consolidated_volume_provenance | GET /v2/stocks/{symbol}/bars?feed=sip|iex | 200 | False | live_evidence | Paired SIP/IEX volume differs; explicit consolidated/venue disclosure not captured. | probe feed comparison |
| venue_volume_iex_historical | GET /v2/stocks/{symbol}/bars?feed=iex | 200 | True | live_evidence | IEX is a diagnostic comparison feed only. | probe bars requests |
| point_in_time_universe | GET /v2/assets | 200 | False | live_evidence | Active snapshot is not a historical point-in-time universe. | active_assets_count=14202 |
| monthly_pit_reproducibility | GET /v2/assets | 200 | False | unproven | No historical PIT membership endpoint was exercised. |  |
| current_active_asset_master | GET /v2/assets?status=active | 200 | True | live_evidence | Current listing only. | active_assets_count=14202 |
| current_inactive_asset_master | GET /v2/assets?status=inactive | 200 | True | live_evidence | Inactive listing is current, not historical PIT. | inactive_assets_count=19202 |
| delisted_symbol_handling | GET /v2/stocks/{symbol}/bars | 0 | False | unproven | asof parameter maps symbol at asof date; does not reconstruct historical security master. |  |
| symbol_mapping_asof | GET /v2/stocks/{symbol}/bars | 200 | True | documented_capability | asof is a query parameter, not a historical security master. | Alpaca Stock Bars API reference, https://docs.alpaca.markets/us/reference/stockbars (reviewed 2026-08-08) (asof parameter); request used asof=2025-12-31 |
| security_type_stock_etf | GET /v2/assets | 200 | False | unproven | asset_class=us_equity does not distinguish stocks from ETFs. |  |
| security_type_warrant_right_unit_preferred | GET /v2/assets | 200 | False | unproven | asset_class=us_equity does not expose warrant/right/unit/preferred classification. |  |
| historical_security_type | GET /v2/assets | 200 | False | unproven | Assets API returns current classification only. |  |
| corporate_action_endpoint_reachable | GET /v1/corporate-actions | 200 | True | live_evidence | Reachability does not imply historical completeness. | corporate_actions_response_type=dict |
| corporate_action_historical_completeness | GET /v1/corporate-actions | 200 | False | unproven | Coverage and timeliness not audited in this probe. |  |
| no_provider_mixing | probe audit | 0 | True | live_evidence | Only Alpaca endpoints were called. | probe request log |
| manifest_feasibility | probe audit | 0 | False | unproven | Single-provider contract not satisfied; data-source mixing decision required. |  |



## 45. probe_did_not_mix_providers

`probe_did_not_mix_providers`: True. All requests were directed to Alpaca only; no Schwab, IEX-as-source, Yahoo, Polygon, IBKR, or other provider was used for the candidate data.


## 46. single_provider_contract_satisfied

`single_provider_contract_satisfied`: False. True only when every provider-contract matrix dimension is satisfied, pagination/timestamp/quality gates pass, and direct or chunked support is proven.


## 47. Complete-provider decision

`approved_as_complete_intra_001_data_source`: False. Complete-provider approval requires `single_provider_contract_satisfied` and `approved_for_intra_001_five_minute_ohlcv` both true.


## 48. Methodology decision required

`methodology_decision_required`: True. Reason: OHLCV data are available but complete single-provider contract cannot be satisfied; provider-mixing decision required.


## 49. Limitations

- This is an as-of observation using the locked symbol set and sample windows; provider behavior/entitlements may change.
- The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements unless explicitly verified.


## 50. Final outcome

The final outcome is `supported_ohlcv_only`. Approved for INTRA-001 five-minute OHLCV: True. Approved as a complete INTRA-001 data source: False.


## 51. Tracker disposition

`docs/PROJECT-TRACKER.md` updated: v1 frozen as invalid, v2 outcome `supported_ohlcv_only`, v2 artifact path to be recorded, next assignment `gary-decision-intra-001-provider-mixing`.


## 52. Recommended next assignment

`gary-decision-intra-001-provider-mixing`


## 53. Artifact safety

Safe artifact bundle contains only aggregated CSVs and decision metadata. Full raw/normalized OHLCV CSVs, provider payload JSONs, pagination tokens, API secrets, and account data are excluded and remain outside the repository.


## 54. Tests

Credential-free regression tests: passed. Full isolated suite with temporary HOME: passed. Ruff: clean. JSON validation: valid. Artifact checksums: verified. Real `~/.tradex` persistence: unchanged.


## 55. Exact CI merge-ref evidence

CI workflow ID: `31211100887`. CI job ID: `92973850931`. Merge ref: `1a5c9e93ea923cc2e2cb1edc0e3e104d348997a6`


## 56. Production boundary

No production trading behavior changed. `tradex/data/fetcher.py` and `tradex/data/history.py` were not modified. No broker account, balance, position, order, transfer, or transaction endpoints were called. The v2 probe is research-only and does not promote Alpaca to a production data source without Gary's explicit approval.

## 57. Post-live derived-output corrections and pre/post audit

This report and ``decision.json`` were regenerated on 2026-08-07T19:27:05.428423+00:00 from the frozen v2 provider evidence only.
No new Alpaca market-data or reference API calls were made.

- Frozen private evidence SHA-256: ``c294cac09a68f1991cb5ba51a2a37668582efccfa191e3fb077dfa68c2bc2182``
- v1 pre-registration commit: ``286493eceeffd6aec872ce7516bed5d1b0cd304f`` (preserved byte-for-byte)
- v2 pre-registration commit: ``340e0921065fc17767cd882393fb3fe543cfcc0b`` (resolved and verified as ancestor of final head)
- Approved starting head: ``bb1730c598c252d4fc6ac5125bf348766a6455f9``
- Final head at regeneration: ``340e0921065fc17767cd882393fb3fe543cfcc0b``

### Corrections applied

1. ``candidate_timestamp_semantics`` is now aggregated over candidate SIP records only; the comparison IEX feed is excluded from the candidate summary.
2. ``method_parity_passed`` is now ``null`` / not applicable for Alpaca v2 because Alpaca has no Schwab-style method-pair comparison; SIP/IEX diagnostics remain in ``feed_comparison.csv``.
3. ``inactive_asset_listing_supported`` now derives from the ``current_inactive_asset_master`` provider-contract row instead of the active-assets row.
4. The legacy ``no_provider_mixing_contract_satisfied`` field is omitted from v2 ``decision.json`` in favor of ``probe_did_not_mix_providers`` (true) and ``single_provider_contract_satisfied`` (false).
5. The v2 decision schema now includes ``probe_version``, ``target_entitlement``, ``v1_pre_registration_commit``, ``v2_pre_registration_commit``, ``client_version``, and ``excluded_security_types_supported``.
6. Official Alpaca documentation titles/links and review date are recorded for rows classified as ``documented_capability``.

### Pre/post audit

- Aggregate timestamp semantics over **all** records: ``ambiguous``
- Aggregate timestamp semantics over **candidate SIP** records: ``bar_start``
- Core gate/outcome unchanged by corrections: ``True``

Core gate comparison (old → new):

- `outcome`: `supported_ohlcv_only` → `supported_ohlcv_only`
- `approved_for_intra_001_five_minute_ohlcv`: `True` → `True`
- `approved_as_complete_intra_001_data_source`: `False` → `False`
- `direct_full_range_supported`: `True` → `True`
- `chunked_historical_windows_supported`: `True` → `True`
- `single_provider_contract_satisfied`: `False` → `False`
- `selected_request_method`: `sip` → `sip`
- `selected_windowing_policy`: `direct_full_range` → `direct_full_range`
- `timestamp_semantics_passed`: `True` → `True`
- `candidate_timestamp_semantics`: `bar_start` → `bar_start`

**AUDIT PASS**: the post-live derived-output corrections did not change the preregistered core support gates or the empirical disposition ``supported_ohlcv_only``.
