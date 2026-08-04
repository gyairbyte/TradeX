# LONG-001: Long-Term Scorer Evaluation Report

## Study objective

Compare the current production `long_term.score` (threshold 40) with a simple `close > 40-week simple moving average` baseline on weekly OHLCV bars. This is a research-only evaluation; it does **not** change production scoring.

## Pre-registration authority

- Protocol source: `PR #25 comment 5182648133`
- Locked protocol file: `docs/research/LONG-001.json`
- Protocol SHA-256: `1e391594933acf0b8252cbb71cc9e100c729dd13c06702935bce739698187d97`
- Protocol lock commit: `d9ffd784a1ef36bec7ecdf6f26773fafc2428fd9`

## Spec

- Universe: `AAPL, MSFT, AMZN, GOOGL, NVDA, JPM, BAC, GS, XOM, CVX, JNJ, MRK, PFE, UNH, PG, KO, WMT, COST, HD, CAT, HON, IBM, CSCO, ORCL, MCD, NKE, DIS, BA, MMM, UPS, QQQ, IWM, DIA, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY`
- Benchmark: `SPY`
- Provider: `yahoo`
- Timeframe: `1wk`
- Adjustment policy: `provider_adjusted`
- Date range: `2007-01-01` to `2025-12-19`
- Warm-up: `2007-01-01` to `2009-12-31`
- Development: `2009-12-31` (+1 day) to `2016-12-31`
- Validation: `2016-12-31` (+1 day) to `2020-12-31`
- Holdout: `2020-12-31` (+1 day) to `2025-12-19`
- Primary horizon: `13` weeks
- Score threshold: `score >= 40`
- Score buckets: `0-24, 25-39, 40-59, 60-79, 80-100`
- Slippage scenarios (bps per side): `0.0, 10.0, 25.0`
- Decision slippage (bps per side): `5.0`
- Commission (bps): `0.0`
- Spec SHA-256: `fb1f2968743f4420d45ac4bccc4a15b0ca4ed947285a29acb49b6e74b1e819ea`
- Manifest SHA-256: `59feee465570c602924c441e8ec87c42f2cbde4d83fe3c8a0b4104c3bb648ca9`

## Weight snapshot

The study used a fresh `LongWeights()` default instance, not any saved user configuration.

| Component | Weight |
|---|---|
| secular_uptrend | 25 |
| rsi_healthy | 20 |
| volume_accumulation | 25 |
| macd_bullish | 15 |
| bb_coil | 15 |

## Data quality

| ticker | data_source | sha256 | manifest_rows | validated_rows | data_start | data_end | duplicate_timestamps | missing_required_values | invalid_ohlc_rows | split_event_counts | complete_outcomes | warnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | yahoo | a50eabeb3127393be3c906091d512e44835f607be68ae4bc9d357b807ecf1f5d | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| MSFT | yahoo | 8b293de91f38357bf4f799744b9222d902cc52c1f503fd9df20dbd1c7bcd964f | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| AMZN | yahoo | 4df1138fa4880d24dcf7ea7866484f6a16601f37783b9c3be2b71b7c011007b2 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| GOOGL | yahoo | c316170d667832d53289e063bf5d8d598bccfe4a1c58f32333079d9c2212bfb4 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| NVDA | yahoo | 66dbf0c221d74416feec9038b5dc15b9bedb1e793821b793be87584bc70063ba | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| JPM | yahoo | 872f6bd17479d0038ca36a8d328c402967c270f3ea5200b734b30aeb4abe4eee | 4768 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| BAC | yahoo | 676dde87f766543f29e450564fc20c8d2aa8349b784125971dea48fee487e991 | 4770 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| GS | yahoo | 4e2b0901ccc56e61e7b177477363123d914f3e3343c926fca0661d7c8f904797 | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XOM | yahoo | 78ba757a39a88a469ab333622d8bea7f7a899728effd745e6f645959d1abeb91 | 4759 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 14 | {'warmup': 157, 'development': 362, 'validation': 209, 'holdout': 259} | {} | [] |
| CVX | yahoo | 023a32c6fd0c4c45d900901304e813e169922da199f9e9bcf1efa0fbfa5a81d1 | 4768 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| JNJ | yahoo | efd9eada2f8022aed6113a1907c708e3f20cc75861929820f69e1043f62c3d8b | 4770 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| MRK | yahoo | b0e763073f1ec6b79022cbfe64a7fd296a86c3b0bffe11baae6dc0b432b15c13 | 4769 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| PFE | yahoo | f13e5d324607775d053ac4801f9cc075a09cb1701cf28779ff4606dbd0a6dc0c | 4762 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 11 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| UNH | yahoo | ce25e3ec3abd3b8caa1b76c5c2e9166da33fc61926845750be5360c9f4656689 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| PG | yahoo | 0d9a36e4d83b568be6ad6a1b99ac4356d2d6b80d4a68651acdb8b93dfa3fc963 | 4769 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| KO | yahoo | b64650e1690f39d18c8dc168497e48bb23a2288fb82bea39516209dc60d68442 | 4762 | 983 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 11 | {'warmup': 156, 'development': 359, 'validation': 209, 'holdout': 259} | {} | [] |
| WMT | yahoo | 25c5af6872657686e80a5cb6a86e5bbc262a8a8a6a4a1b17c82bbecd08a0392b | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| COST | yahoo | c1cc09a524dc4cc36440a8e72a859495d6a36f211781ee53cff6e757b5cffc97 | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| HD | yahoo | 8fe5ea52f9d08df59ed9051fcdac65f1d3d003e434991a4fb21018cce6592546 | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| CAT | yahoo | 55ecb9d41ee5867354961f7ad0e8d85cae8aee208449e3d1646af75b6a053420 | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| HON | yahoo | 43bd97dbaa8c146adeec0445dc0d66e2eee09c1cd0841040d6adb30992dee3cd | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| IBM | yahoo | 8c6cef45b684dd8b9d61b58289aac8e9329e9194517e77442abd4c8888e959bb | 4763 | 986 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 10 | {'warmup': 156, 'development': 362, 'validation': 209, 'holdout': 259} | {} | [] |
| CSCO | yahoo | 63b32042c2f3683e188068479dc9e97dba4fbdbfc895b102b43455805e478f72 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| ORCL | yahoo | 7ebfa36a3e336198c0af9f0b6dd83868f1a0fd025079d75147bd26c61bceafa2 | 4771 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| MCD | yahoo | a8f695d472e67a734f2774869def2e9b2d8e8ffd089957539927d93d9c2b7ee4 | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| NKE | yahoo | 2ad2862e81acc5e954fd8b0f270ccab24f01da100069baa9ed393bba340e6a23 | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| DIS | yahoo | 43afed5e5a0aa83fba9f52b21e734649a87ddee8ebe2f997e0fc8f142550a1b1 | 4771 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 364, 'validation': 208, 'holdout': 259} | {} | [] |
| BA | yahoo | e9698c88c51cf96367c42f618145bc91262c1101a985d0a9889de1ac8d4524ba | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| MMM | yahoo | 317a7a567e884a9acda28c73d5c7ea76578c90718cf6fbe8f6df7fdc45cfa176 | 4769 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| UPS | yahoo | e852d9756cc4c9b06668e048515ffdbc351b8d9bdb2bb464cc927b6810e9ce51 | 4768 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 365, 'validation': 208, 'holdout': 259} | {} | [] |
| QQQ | yahoo | c6c9a8961f84a0a92c5f7a2d891ad5f285743433e6824b6a465f82cf4a1c3236 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| IWM | yahoo | be4e90928d831ca71a9c414a1be7c2c7f7c6d8873923ea53d45acec2e0f9e242 | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| DIA | yahoo | 39a70fe0fde32003b9cfabd0e4d5ff40c49fdee760e05b65799b56065a9b403f | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLB | yahoo | 3729239d5c76ca1adecdcee8d049481bb8f02ec0d577e2ffebf490559c3258e7 | 4768 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| XLE | yahoo | 26a98f41379657f42e4aead290bd6c31318153f1aebcc1d8856a0ecbddf52cdd | 4770 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLF | yahoo | c858cc7220ce26f48c667e9d9d4c6df9fc3d516127c8c9ab9c9d313819914e7d | 4770 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 155, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLI | yahoo | 4b9027b0b64633c17dd3bc833a8240ff1b5212646d45b9cc70edec8adfcbfc8a | 4769 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 155, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLK | yahoo | d07cf1c7f0c73b0f23ded0b902b187f92b2fdc32b36eca3326eee3c0e16f5a9d | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLP | yahoo | 02d552778eec4e9fda4e88a2e44871162930f819c493e828a00ced26b613329f | 4763 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 10 | {'warmup': 155, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| XLU | yahoo | b526984f2afab2c007039df8de93f01d144aad7c45a6367223f271079e2e8a01 | 4762 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 11 | {'warmup': 154, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLV | yahoo | e7650815f36bb816a5f914854d27f8fac96a3a8539fc4d1c32796a3ec15dd79a | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLY | yahoo | 203387b2ad9fa7f1729c9c7156cafed409b0a7fce2a1f50723ab4d3f47ffd123 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| SPY | yahoo | 9d48194a3cc3e497c8b1ce01ac39997b3faf0537c6b0a6313f3ea0535d0b7494 | 4770 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 155, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |

## Events and trades

Total overlapping events: `53849`
Total non-overlapping trades: `5323`
Events by rule:
| rule | count |
|---|---|
| candidate | 28430 |
| baseline | 25419 |

## Split summary

- **development**:
  - candidate: count=955, mean_net=3.2340, win_rate=0.6565, tickers=42
  - baseline: count=875, mean_net=3.3264, win_rate=0.6606, tickers=42
  - pooled lift (pct): -0.0925, median lift at 25.0bps per side (pct): -0.0921, q10 lift (pct): -0.5036
  - positive lift fraction stock: 0.5333, positive lift fraction etf: 0.4167
- **validation**:
  - candidate: count=530, mean_net=3.3916, win_rate=0.6792, tickers=42
  - baseline: count=493, mean_net=3.4323, win_rate=0.6897, tickers=42
  - pooled lift (pct): -0.0407, median lift at 25.0bps per side (pct): -0.0405, q10 lift (pct): -0.3028
  - positive lift fraction stock: 0.5000, positive lift fraction etf: 0.5833
- **holdout**:
  - candidate: count=642, mean_net=3.2710, win_rate=0.6184, tickers=42
  - baseline: count=587, mean_net=3.6146, win_rate=0.6320, tickers=42
  - pooled lift (pct): -0.3436, median lift at 25.0bps per side (pct): -0.3423, q10 lift (pct): -1.5020
  - positive lift fraction stock: 0.5000, positive lift fraction etf: 0.5000

## thresholds

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 12516 | sufficient_sample | 3.6062 | 3.4607 | 9.9395 | 0.6654 | 3.6062 | 0.6654 | 3.0968 | 3.3992 | 0.6565 | 3.0895 | 0.6429 |
| candidate | validation | 13 | 6672 | sufficient_sample | 3.5123 | 4.0415 | 12.0416 | 0.6676 | 3.5123 | 0.6676 | 3.0388 | 3.3055 | 0.6602 | 2.9961 | 0.6481 |
| candidate | holdout | 13 | 7755 | sufficient_sample | 3.7480 | 2.9232 | 12.3185 | 0.6135 | 3.7480 | 0.6135 | 3.7975 | 3.5407 | 0.6062 | 3.2306 | 0.5933 |
| baseline | development | 13 | 11076 | sufficient_sample | 3.3224 | 3.2341 | 9.6986 | 0.6575 | 3.3224 | 0.6575 | 2.8996 | 3.1159 | 0.6484 | 2.8070 | 0.6340 |
| baseline | validation | 13 | 5894 | sufficient_sample | 3.3981 | 3.8823 | 11.8889 | 0.6608 | 3.3981 | 0.6608 | 2.5857 | 3.1915 | 0.6529 | 2.8824 | 0.6410 |
| baseline | holdout | 13 | 7005 | sufficient_sample | 3.8578 | 2.9272 | 12.1403 | 0.6157 | 3.8578 | 0.6157 | 3.8758 | 3.6503 | 0.6080 | 3.3398 | 0.5950 |
| candidate | development | 26 | 12006 | sufficient_sample | 7.3501 | 7.0145 | 13.6429 | 0.7355 | 7.3501 | 0.7355 | 6.4461 | 7.1356 | 0.7307 | 6.8147 | 0.7233 |
| candidate | validation | 26 | 6259 | sufficient_sample | 7.1701 | 6.5515 | 16.7920 | 0.6848 | 7.1701 | 0.6848 | 6.2103 | 6.9559 | 0.6808 | 6.6356 | 0.6704 |
| candidate | holdout | 26 | 7287 | sufficient_sample | 6.9692 | 5.5633 | 18.2095 | 0.6582 | 6.9692 | 0.6582 | 6.7549 | 6.7555 | 0.6513 | 6.4357 | 0.6424 |
| baseline | development | 26 | 10597 | sufficient_sample | 6.9280 | 6.5733 | 13.6453 | 0.7286 | 6.9280 | 0.7286 | 6.0050 | 6.7144 | 0.7239 | 6.3947 | 0.7160 |
| baseline | validation | 26 | 5514 | sufficient_sample | 6.8461 | 6.0648 | 16.7519 | 0.6725 | 6.8461 | 0.6725 | 5.5180 | 6.6326 | 0.6685 | 6.3132 | 0.6580 |
| baseline | holdout | 26 | 6580 | sufficient_sample | 7.2063 | 5.9435 | 17.9137 | 0.6681 | 7.2063 | 0.6681 | 6.7868 | 6.9921 | 0.6611 | 6.6716 | 0.6520 |

## cohorts

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | cohort |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 8742 | sufficient_sample | 3.8655 | 3.3663 | 10.9746 | 0.6461 | 3.8655 | 0.6461 | 3.1210 | 3.6580 | 0.6368 | 3.3474 | 0.6249 | stock |
| baseline | development | 13 | 7668 | sufficient_sample | 3.5571 | 3.1423 | 10.7694 | 0.6360 | 3.5571 | 0.6360 | 2.9467 | 3.3502 | 0.6268 | 3.0406 | 0.6142 | stock |
| candidate | development | 13 | 3774 | sufficient_sample | 3.0056 | 3.6234 | 6.9379 | 0.7101 | 3.0056 | 0.7101 | 3.0408 | 2.7998 | 0.7022 | 2.4919 | 0.6847 | etf |
| baseline | development | 13 | 3408 | sufficient_sample | 2.7943 | 3.3750 | 6.6591 | 0.7060 | 2.7943 | 0.7060 | 2.7937 | 2.5889 | 0.6972 | 2.2816 | 0.6784 | etf |
| candidate | validation | 13 | 4693 | sufficient_sample | 3.9588 | 4.2195 | 12.9518 | 0.6529 | 3.9588 | 0.6529 | 3.1072 | 3.7510 | 0.6452 | 3.4403 | 0.6341 | stock |
| baseline | validation | 13 | 4131 | sufficient_sample | 3.9746 | 4.0619 | 12.8079 | 0.6454 | 3.9746 | 0.6454 | 2.6922 | 3.7669 | 0.6369 | 3.4561 | 0.6258 | stock |
| candidate | validation | 13 | 1979 | sufficient_sample | 2.4537 | 3.8052 | 9.4582 | 0.7024 | 2.4537 | 0.7024 | 2.8767 | 2.2490 | 0.6958 | 1.9427 | 0.6812 | etf |
| baseline | validation | 13 | 1763 | sufficient_sample | 2.0473 | 3.6526 | 9.2499 | 0.6971 | 2.0473 | 0.6971 | 2.3362 | 1.8434 | 0.6903 | 1.5383 | 0.6767 | etf |
| candidate | holdout | 13 | 5360 | sufficient_sample | 4.1491 | 3.1152 | 13.7190 | 0.5998 | 4.1491 | 0.5998 | 3.8208 | 3.9410 | 0.5933 | 3.6296 | 0.5821 | stock |
| baseline | holdout | 13 | 4837 | sufficient_sample | 4.2612 | 3.1150 | 13.5780 | 0.6004 | 4.2612 | 0.6004 | 3.8787 | 4.0529 | 0.5935 | 3.7412 | 0.5824 | stock |
| candidate | holdout | 13 | 2395 | sufficient_sample | 2.8504 | 2.7299 | 8.3049 | 0.6443 | 2.8504 | 0.6443 | 3.7454 | 2.6450 | 0.6351 | 2.3375 | 0.6184 | etf |
| baseline | holdout | 13 | 2168 | sufficient_sample | 2.9577 | 2.7670 | 7.9826 | 0.6499 | 2.9577 | 0.6499 | 3.8692 | 2.7520 | 0.6402 | 2.4442 | 0.6232 | etf |
| candidate | development | 26 | 8387 | sufficient_sample | 7.8056 | 7.1467 | 15.1789 | 0.7121 | 7.8056 | 0.7121 | 6.4849 | 7.5902 | 0.7072 | 7.2679 | 0.7001 | stock |
| baseline | development | 26 | 7345 | sufficient_sample | 7.4122 | 6.6625 | 15.3174 | 0.7036 | 7.4122 | 0.7036 | 6.0997 | 7.1976 | 0.6988 | 6.8765 | 0.6912 | stock |
| candidate | development | 26 | 3619 | sufficient_sample | 6.2946 | 6.8371 | 9.0522 | 0.7900 | 6.2946 | 0.7900 | 6.3561 | 6.0822 | 0.7853 | 5.7645 | 0.7770 | etf |
| baseline | development | 26 | 3252 | sufficient_sample | 5.8344 | 6.4826 | 8.6654 | 0.7851 | 5.8344 | 0.7851 | 5.7910 | 5.6229 | 0.7804 | 5.3065 | 0.7718 | etf |
| candidate | validation | 26 | 4404 | sufficient_sample | 8.1911 | 6.8275 | 18.4812 | 0.6769 | 8.1911 | 0.6769 | 6.4106 | 7.9749 | 0.6728 | 7.6515 | 0.6639 | stock |
| baseline | validation | 26 | 3862 | sufficient_sample | 7.9172 | 6.1657 | 18.6017 | 0.6636 | 7.9172 | 0.6636 | 5.6703 | 7.7015 | 0.6592 | 7.3789 | 0.6499 | stock |
| candidate | validation | 26 | 1855 | sufficient_sample | 4.7461 | 6.1178 | 11.4962 | 0.7035 | 4.7461 | 0.7035 | 5.7347 | 4.5368 | 0.6997 | 4.2237 | 0.6857 | etf |
| baseline | validation | 26 | 1652 | sufficient_sample | 4.3421 | 5.8816 | 10.8991 | 0.6931 | 4.3421 | 0.6931 | 5.1620 | 4.1336 | 0.6901 | 3.8217 | 0.6768 | etf |
| candidate | holdout | 26 | 5042 | sufficient_sample | 7.8649 | 6.0073 | 20.4479 | 0.6436 | 7.8649 | 0.6436 | 6.8265 | 7.6494 | 0.6374 | 7.3270 | 0.6309 | stock |
| baseline | holdout | 26 | 4549 | sufficient_sample | 8.0837 | 6.1801 | 20.1473 | 0.6509 | 8.0837 | 0.6509 | 6.8099 | 7.8678 | 0.6448 | 7.5446 | 0.6377 | stock |
| candidate | holdout | 26 | 2245 | sufficient_sample | 4.9576 | 4.9332 | 11.4627 | 0.6909 | 4.9576 | 0.6909 | 6.5940 | 4.7479 | 0.6824 | 4.4341 | 0.6682 | etf |
| baseline | holdout | 26 | 2031 | sufficient_sample | 5.2411 | 5.4680 | 11.1757 | 0.7065 | 5.2411 | 0.7065 | 6.7349 | 5.0308 | 0.6977 | 4.7162 | 0.6839 | etf |

## groups

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | group |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 10867 | sufficient_sample | 3.3374 | 3.2343 | 9.6852 | 0.6579 | 3.3374 | 0.6579 | 2.9046 | 3.1309 | 0.6488 | 2.8220 | 0.6342 | baseline_and_candidate |
| baseline | development | 13 | 10867 | sufficient_sample | 3.3374 | 3.2343 | 9.6852 | 0.6579 | 3.3374 | 0.6579 | 2.9046 | 3.1309 | 0.6488 | 2.8220 | 0.6342 | baseline_and_candidate |
| candidate | development | 13 | 1649 | sufficient_sample | 5.3778 | 5.4357 | 11.3168 | 0.7150 | 5.3778 | 0.7150 | 4.3663 | 5.1673 | 0.7071 | 4.8522 | 0.7004 | candidate_only |
| baseline | development | 13 | 209 | sufficient_sample | 2.5426 | 3.1579 | 10.3402 | 0.6411 | 2.5426 | 0.6411 | 2.6402 | 2.3377 | 0.6268 | 2.0312 | 0.6220 | baseline_only |
| candidate | validation | 13 | 5770 | sufficient_sample | 3.2985 | 3.7782 | 11.8043 | 0.6586 | 3.2985 | 0.6586 | 2.5559 | 3.0921 | 0.6504 | 2.7833 | 0.6383 | baseline_and_candidate |
| baseline | validation | 13 | 5770 | sufficient_sample | 3.2985 | 3.7782 | 11.8043 | 0.6586 | 3.2985 | 0.6586 | 2.5559 | 3.0921 | 0.6504 | 2.7833 | 0.6383 | baseline_and_candidate |
| candidate | validation | 13 | 902 | sufficient_sample | 4.8802 | 5.4918 | 13.3801 | 0.7251 | 4.8802 | 0.7251 | 6.1282 | 4.6706 | 0.7228 | 4.3571 | 0.7106 | candidate_only |
| baseline | validation | 13 | 124 | sufficient_sample | 8.0342 | 7.5430 | 14.5820 | 0.7661 | 8.0342 | 0.7661 | 3.9738 | 7.8184 | 0.7661 | 7.4954 | 0.7661 | baseline_only |
| candidate | holdout | 13 | 6789 | sufficient_sample | 3.8667 | 2.9286 | 12.1364 | 0.6154 | 3.8667 | 0.6154 | 3.8539 | 3.6592 | 0.6077 | 3.3486 | 0.5946 | baseline_and_candidate |
| baseline | holdout | 13 | 6789 | sufficient_sample | 3.8667 | 2.9286 | 12.1364 | 0.6154 | 3.8667 | 0.6154 | 3.8539 | 3.6592 | 0.6077 | 3.3486 | 0.5946 | baseline_and_candidate |
| candidate | holdout | 13 | 966 | sufficient_sample | 2.9141 | 2.8486 | 13.4999 | 0.6004 | 2.9141 | 0.6004 | 3.4009 | 2.7085 | 0.5952 | 2.4008 | 0.5839 | candidate_only |
| baseline | holdout | 13 | 216 | sufficient_sample | 3.5783 | 2.7835 | 12.2580 | 0.6250 | 3.5783 | 0.6250 | 4.5630 | 3.3713 | 0.6157 | 3.0617 | 0.6065 | baseline_only |
| candidate | development | 26 | 10393 | sufficient_sample | 6.9338 | 6.5453 | 13.5706 | 0.7293 | 6.9338 | 0.7293 | 6.0367 | 6.7202 | 0.7245 | 6.4005 | 0.7164 | baseline_and_candidate |
| baseline | development | 26 | 10393 | sufficient_sample | 6.9338 | 6.5453 | 13.5706 | 0.7293 | 6.9338 | 0.7293 | 6.0367 | 6.7202 | 0.7245 | 6.4005 | 0.7164 | baseline_and_candidate |
| candidate | development | 26 | 1613 | sufficient_sample | 10.0324 | 10.0612 | 13.8024 | 0.7756 | 10.0324 | 0.7756 | 9.0768 | 9.8125 | 0.7706 | 9.4836 | 0.7675 | candidate_only |
| baseline | development | 26 | 204 | sufficient_sample | 6.6314 | 8.5547 | 17.0222 | 0.6912 | 6.6314 | 0.6912 | 4.3950 | 6.4183 | 0.6912 | 6.0995 | 0.6912 | baseline_only |
| candidate | validation | 26 | 5393 | sufficient_sample | 6.6885 | 6.0394 | 16.5908 | 0.6712 | 6.6885 | 0.6712 | 5.4999 | 6.4753 | 0.6675 | 6.1564 | 0.6571 | baseline_and_candidate |
| baseline | validation | 26 | 5393 | sufficient_sample | 6.6885 | 6.0394 | 16.5908 | 0.6712 | 6.6885 | 0.6712 | 5.4999 | 6.4753 | 0.6675 | 6.1564 | 0.6571 | baseline_and_candidate |
| candidate | validation | 26 | 866 | sufficient_sample | 10.1690 | 9.0387 | 17.7025 | 0.7691 | 10.1690 | 0.7691 | 10.6341 | 9.9489 | 0.7633 | 9.6195 | 0.7529 | candidate_only |
| baseline | validation | 26 | 121 | sufficient_sample | 13.8681 | 7.7705 | 21.6727 | 0.7273 | 13.8681 | 0.7273 | 6.3246 | 13.6406 | 0.7107 | 13.3002 | 0.6942 | baseline_only |
| candidate | holdout | 26 | 6366 | sufficient_sample | 7.1946 | 5.9635 | 17.8015 | 0.6689 | 7.1946 | 0.6689 | 6.7316 | 6.9804 | 0.6620 | 6.6600 | 0.6528 | baseline_and_candidate |
| baseline | holdout | 26 | 6366 | sufficient_sample | 7.1946 | 5.9635 | 17.8015 | 0.6689 | 7.1946 | 0.6689 | 6.7316 | 6.9804 | 0.6620 | 6.6600 | 0.6528 | baseline_and_candidate |
| candidate | holdout | 26 | 921 | sufficient_sample | 5.4116 | 3.3443 | 20.7450 | 0.5841 | 5.4116 | 0.5841 | 6.9157 | 5.2010 | 0.5776 | 4.8858 | 0.5700 | candidate_only |
| baseline | holdout | 26 | 214 | sufficient_sample | 7.5544 | 5.1416 | 20.9748 | 0.6449 | 7.5544 | 0.6449 | 8.4287 | 7.3395 | 0.6355 | 7.0180 | 0.6262 | baseline_only |

## score_buckets

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | score_bucket |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 4690 | sufficient_sample | 3.4331 | 3.1693 | 10.0029 | 0.6482 | 3.4331 | 0.6482 | 2.9641 | 3.2265 | 0.6405 | 2.9172 | 0.6254 | 40-59 |
| candidate | development | 13 | 7005 | sufficient_sample | 3.8140 | 3.6555 | 9.9796 | 0.6745 | 3.8140 | 0.6745 | 3.2201 | 3.6066 | 0.6650 | 3.2962 | 0.6530 | 60-79 |
| candidate | development | 13 | 821 | sufficient_sample | 2.8218 | 3.6293 | 9.1439 | 0.6857 | 2.8218 | 0.6857 | 2.8025 | 2.6163 | 0.6760 | 2.3089 | 0.6577 | 80-100 |
| candidate | validation | 13 | 2945 | sufficient_sample | 3.3705 | 4.1062 | 11.9721 | 0.6710 | 3.3705 | 0.6710 | 2.7468 | 3.1640 | 0.6652 | 2.8549 | 0.6533 | 40-59 |
| candidate | validation | 13 | 3453 | sufficient_sample | 3.6360 | 4.0407 | 12.1054 | 0.6655 | 3.6360 | 0.6655 | 3.1595 | 3.4289 | 0.6574 | 3.1191 | 0.6455 | 60-79 |
| candidate | validation | 13 | 274 | sufficient_sample | 3.4781 | 3.0383 | 11.9625 | 0.6569 | 3.4781 | 0.6569 | 4.6570 | 3.2713 | 0.6423 | 2.9620 | 0.6241 | 80-100 |
| candidate | holdout | 13 | 3598 | sufficient_sample | 4.1920 | 3.1431 | 12.5323 | 0.6242 | 4.1920 | 0.6242 | 3.6952 | 3.9839 | 0.6167 | 3.6724 | 0.6028 | 40-59 |
| candidate | holdout | 13 | 3773 | sufficient_sample | 3.3955 | 2.8487 | 12.1581 | 0.6064 | 3.3955 | 0.6064 | 3.8670 | 3.1889 | 0.5993 | 2.8798 | 0.5871 | 60-79 |
| candidate | holdout | 13 | 384 | sufficient_sample | 3.0512 | 2.0720 | 11.7052 | 0.5833 | 3.0512 | 0.5833 | 4.0727 | 2.8453 | 0.5755 | 2.5373 | 0.5651 | 80-100 |
| candidate | development | 26 | 4452 | sufficient_sample | 7.1549 | 6.6489 | 14.0836 | 0.7177 | 7.1549 | 0.7177 | 6.4481 | 6.9408 | 0.7127 | 6.6204 | 0.7060 | 40-59 |
| candidate | development | 26 | 6734 | sufficient_sample | 7.3895 | 7.1305 | 13.5295 | 0.7398 | 7.3895 | 0.7398 | 6.3928 | 7.1750 | 0.7351 | 6.8539 | 0.7271 | 60-79 |
| candidate | development | 26 | 820 | sufficient_sample | 8.0865 | 7.4007 | 12.0141 | 0.7976 | 8.0865 | 0.7976 | 6.8711 | 7.8706 | 0.7927 | 7.5474 | 0.7866 | 80-100 |
| candidate | validation | 26 | 2817 | sufficient_sample | 7.4595 | 6.8356 | 16.3671 | 0.6993 | 7.4595 | 0.6993 | 6.2327 | 7.2448 | 0.6958 | 6.9235 | 0.6851 | 40-59 |
| candidate | validation | 26 | 3174 | sufficient_sample | 6.6859 | 6.0576 | 17.0355 | 0.6670 | 6.6859 | 0.6670 | 5.9611 | 6.4727 | 0.6623 | 6.1538 | 0.6515 | 60-79 |
| candidate | validation | 26 | 268 | sufficient_sample | 9.8629 | 9.2949 | 17.9346 | 0.7425 | 9.8629 | 0.7425 | 8.9260 | 9.6434 | 0.7425 | 9.3149 | 0.7388 | 80-100 |
| candidate | holdout | 26 | 3444 | sufficient_sample | 7.6838 | 6.5459 | 17.6451 | 0.6908 | 7.6838 | 0.6908 | 6.7481 | 7.4687 | 0.6826 | 7.1468 | 0.6748 | 40-59 |
| candidate | holdout | 26 | 3475 | sufficient_sample | 6.4796 | 4.6800 | 18.7774 | 0.6345 | 6.4796 | 0.6345 | 6.8237 | 6.2669 | 0.6291 | 5.9485 | 0.6196 | 60-79 |
| candidate | holdout | 26 | 368 | sufficient_sample | 4.9053 | 3.3397 | 17.6436 | 0.5761 | 4.9053 | 0.5761 | 6.1676 | 4.6956 | 0.5679 | 4.3820 | 0.5543 | 80-100 |

## ticker_summary

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | ticker | cohort |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | development | 13 | 19 | insufficient_sample | 5.3608 | 5.3457 | 11.6407 | 0.6316 | 5.3608 | 0.6316 | 2.5715 | 5.1503 | 0.6316 | 4.8353 | 0.6316 | AAPL | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 2.6404 | 2.7710 | 10.4736 | 0.7857 | 2.6404 | 0.7857 | 2.2470 | 2.4353 | 0.7857 | 2.1285 | 0.7857 | AAPL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 11.1846 | 9.8334 | 20.6966 | 0.8462 | 11.1846 | 0.8462 | 3.5720 | 10.9625 | 0.8462 | 10.6301 | 0.8462 | AAPL | stock |
| candidate | development | 13 | 22 | sufficient_sample | 5.2343 | 7.8577 | 14.7797 | 0.5909 | 5.2343 | 0.5909 | 1.9628 | 5.0241 | 0.5909 | 4.7095 | 0.5909 | AAPL | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1102 | 2.4163 | 9.4171 | 0.7500 | 4.1102 | 0.7500 | 4.1334 | 3.9021 | 0.7500 | 3.5909 | 0.7500 | AAPL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 9.3004 | 9.8334 | 19.8162 | 0.7692 | 9.3004 | 0.7692 | 3.5093 | 9.0820 | 0.7692 | 8.7552 | 0.7692 | AAPL | stock |
| baseline | development | 13 | 22 | sufficient_sample | 8.3693 | 9.6507 | 15.1433 | 0.7727 | 8.3693 | 0.7727 | 2.8096 | 8.1527 | 0.7727 | 7.8288 | 0.7727 | AMZN | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 5.0451 | 4.9748 | 12.4992 | 0.7692 | 5.0451 | 0.7692 | 4.7921 | 4.8352 | 0.7692 | 4.5212 | 0.7692 | AMZN | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 9.6410 | 11.5476 | 16.8958 | 0.7500 | 9.6410 | 0.7500 | 1.5510 | 9.4220 | 0.7500 | 9.0942 | 0.7500 | AMZN | stock |
| candidate | development | 13 | 23 | sufficient_sample | 7.3608 | 7.8337 | 14.1907 | 0.7826 | 7.3608 | 0.7826 | 3.1786 | 7.1463 | 0.7826 | 6.8254 | 0.7826 | AMZN | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.7117 | 5.4295 | 17.0971 | 0.6000 | 0.7117 | 0.6000 | 3.1311 | 0.5105 | 0.6000 | 0.2094 | 0.6000 | AMZN | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 12.4997 | 12.2551 | 19.2826 | 0.7692 | 12.4997 | 0.7692 | 5.7010 | 12.2749 | 0.7692 | 11.9386 | 0.7692 | AMZN | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.2123 | 2.1429 | 11.8030 | 0.5909 | 3.2123 | 0.5909 | 2.7998 | 3.0061 | 0.5909 | 2.6976 | 0.5909 | BA | stock |
| baseline | holdout | 13 | 11 | insufficient_sample | 1.7311 | -2.7004 | 15.6591 | 0.2727 | 1.7311 | 0.2727 | 5.3562 | 1.5278 | 0.2727 | 1.2237 | 0.2727 | BA | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 9.6355 | 9.7830 | 15.0200 | 0.8000 | 9.6355 | 0.8000 | 3.9438 | 9.4164 | 0.8000 | 9.0887 | 0.8000 | BA | stock |
| candidate | development | 13 | 22 | sufficient_sample | 4.4749 | 2.9833 | 11.3721 | 0.5455 | 4.4749 | 0.5455 | 2.4949 | 4.2662 | 0.5455 | 3.9538 | 0.5455 | BA | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | 0.1631 | -3.5109 | 12.7524 | 0.3077 | 0.1631 | 0.3077 | 4.6860 | -0.0370 | 0.3077 | -0.3365 | 0.3077 | BA | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -1.5088 | 1.8575 | 23.9467 | 0.6667 | -1.5088 | 0.6667 | 1.8377 | -1.7055 | 0.5833 | -2.0000 | 0.5833 | BA | stock |
| baseline | development | 13 | 17 | insufficient_sample | 3.0526 | 0.2547 | 14.8385 | 0.5294 | 3.0526 | 0.5294 | 2.0883 | 2.8467 | 0.5294 | 2.5387 | 0.4118 | BAC | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 1.3006 | 3.6903 | 15.4136 | 0.5333 | 1.3006 | 0.5333 | 2.7447 | 1.0982 | 0.5333 | 0.7953 | 0.5333 | BAC | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 0.8939 | 4.5005 | 16.7626 | 0.6000 | 0.8939 | 0.6000 | 2.7965 | 0.6923 | 0.6000 | 0.3907 | 0.6000 | BAC | stock |
| candidate | development | 13 | 18 | insufficient_sample | 1.8728 | 5.6272 | 13.6491 | 0.6667 | 1.8728 | 0.6667 | 1.7807 | 1.6693 | 0.6667 | 1.3647 | 0.6667 | BAC | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 2.0688 | 1.7861 | 15.9453 | 0.5333 | 2.0688 | 0.5333 | 2.6364 | 1.8649 | 0.5333 | 1.5598 | 0.5333 | BAC | stock |
| candidate | validation | 13 | 13 | insufficient_sample | -0.0045 | 3.7390 | 15.5092 | 0.5385 | -0.0045 | 0.5385 | 3.1302 | -0.2043 | 0.5385 | -0.5032 | 0.5385 | BAC | stock |
| baseline | development | 13 | 17 | insufficient_sample | 0.8624 | 1.8108 | 12.1461 | 0.5294 | 0.8624 | 0.5294 | 3.2165 | 0.6608 | 0.5294 | 0.3593 | 0.5294 | CAT | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 6.6907 | 3.1749 | 14.8131 | 0.6429 | 6.6907 | 0.6429 | 5.1389 | 6.4775 | 0.6429 | 6.1586 | 0.6429 | CAT | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.3763 | 7.1350 | 13.3190 | 0.6923 | 5.3763 | 0.6923 | 2.8012 | 5.1657 | 0.6923 | 4.8507 | 0.6923 | CAT | stock |
| candidate | development | 13 | 20 | sufficient_sample | 1.5105 | 0.9893 | 13.9384 | 0.5500 | 1.5105 | 0.5500 | 2.5939 | 1.3077 | 0.5000 | 1.0043 | 0.5000 | CAT | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 7.1644 | 4.5869 | 14.2701 | 0.6667 | 7.1644 | 0.6667 | 4.5843 | 6.9503 | 0.6667 | 6.6299 | 0.6667 | CAT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 5.5200 | 7.5452 | 13.5388 | 0.7692 | 5.5200 | 0.7692 | 2.5694 | 5.3091 | 0.7692 | 4.9937 | 0.7692 | CAT | stock |
| baseline | development | 13 | 22 | sufficient_sample | 5.3253 | 3.8003 | 7.2227 | 0.7727 | 5.3253 | 0.7727 | 4.0199 | 5.1148 | 0.7273 | 4.8000 | 0.6818 | COST | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 4.9813 | 3.3573 | 10.3037 | 0.6250 | 4.9813 | 0.6250 | 3.7871 | 4.7716 | 0.6250 | 4.4577 | 0.6250 | COST | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.6239 | 5.3375 | 7.7615 | 0.7692 | 5.6239 | 0.7692 | 3.2482 | 5.4128 | 0.7692 | 5.0971 | 0.7692 | COST | stock |
| candidate | development | 13 | 23 | sufficient_sample | 5.1040 | 4.9237 | 6.6286 | 0.8261 | 5.1040 | 0.8261 | 3.1276 | 4.8940 | 0.8261 | 4.5798 | 0.7826 | COST | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 5.9182 | 4.0748 | 9.5575 | 0.6250 | 5.9182 | 0.6250 | 4.5551 | 5.7066 | 0.6250 | 5.3899 | 0.6250 | COST | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.0401 | 9.8453 | 9.0715 | 0.7692 | 6.0401 | 0.7692 | 4.0262 | 5.8282 | 0.7692 | 5.5112 | 0.7692 | COST | stock |
| baseline | development | 13 | 18 | insufficient_sample | 0.9172 | 0.3289 | 11.7960 | 0.5000 | 0.9172 | 0.5000 | 2.9057 | 0.7155 | 0.5000 | 0.4138 | 0.5000 | CSCO | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.2889 | 3.2806 | 10.0930 | 0.7143 | 3.2889 | 0.7143 | 3.2932 | 3.0825 | 0.7143 | 2.7737 | 0.7143 | CSCO | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 5.1522 | 3.8192 | 11.7484 | 0.5000 | 5.1522 | 0.5000 | 4.6204 | 4.9421 | 0.5000 | 4.6277 | 0.5000 | CSCO | stock |
| candidate | development | 13 | 22 | sufficient_sample | 1.1541 | 3.4006 | 10.9603 | 0.6364 | 1.1541 | 0.6364 | 2.9017 | 0.9520 | 0.5909 | 0.6496 | 0.5909 | CSCO | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 4.5537 | 3.9204 | 10.1902 | 0.8000 | 4.5537 | 0.8000 | 3.2856 | 4.3448 | 0.8000 | 4.0322 | 0.8000 | CSCO | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 1.9941 | -0.2060 | 15.4281 | 0.4615 | 1.9941 | 0.4615 | 2.6487 | 1.7903 | 0.4615 | 1.4854 | 0.4615 | CSCO | stock |
| baseline | development | 13 | 19 | insufficient_sample | 2.9110 | 1.0784 | 8.7405 | 0.5789 | 2.9110 | 0.5789 | 2.6915 | 2.7054 | 0.5263 | 2.3978 | 0.5263 | CVX | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.8453 | 4.4742 | 11.4853 | 0.6429 | 3.8453 | 0.6429 | 3.0362 | 3.6378 | 0.6429 | 3.3273 | 0.6429 | CVX | stock |
| baseline | validation | 13 | 11 | insufficient_sample | -2.4515 | -1.6711 | 10.1918 | 0.4545 | -2.4515 | 0.4545 | 1.3625 | -2.6464 | 0.4545 | -2.9380 | 0.3636 | CVX | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.0900 | 2.2085 | 9.9997 | 0.6087 | 3.0900 | 0.6087 | 3.2075 | 2.8840 | 0.6087 | 2.5759 | 0.6087 | CVX | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 4.3145 | 2.1136 | 10.9201 | 0.5882 | 4.3145 | 0.5882 | 3.6687 | 4.1061 | 0.5882 | 3.7943 | 0.5882 | CVX | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -3.0125 | 1.0768 | 15.1346 | 0.5000 | -3.0125 | 0.5000 | 1.4463 | -3.2063 | 0.5000 | -3.4962 | 0.5000 | CVX | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.0649 | 2.8856 | 5.0662 | 0.6818 | 2.0649 | 0.6818 | 2.3747 | 1.8610 | 0.6818 | 1.5559 | 0.6818 | DIA | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 2.3940 | 3.0247 | 6.4261 | 0.7500 | 2.3940 | 0.7500 | 2.5514 | 2.1894 | 0.7500 | 1.8833 | 0.6875 | DIA | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.5694 | 4.4065 | 10.9670 | 0.8462 | 1.5694 | 0.8462 | 1.9042 | 1.3664 | 0.8462 | 1.0628 | 0.8462 | DIA | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.7861 | 4.3629 | 6.0586 | 0.6667 | 2.7861 | 0.6667 | 2.9024 | 2.5808 | 0.6667 | 2.2735 | 0.6667 | DIA | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 2.1942 | 2.3210 | 6.0877 | 0.6875 | 2.1942 | 0.6875 | 2.6874 | 1.9900 | 0.6875 | 1.6845 | 0.6875 | DIA | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 2.8897 | 4.2526 | 7.0318 | 0.6154 | 2.8897 | 0.6154 | 3.1302 | 2.6842 | 0.6154 | 2.3766 | 0.6154 | DIA | etf |
| baseline | development | 13 | 21 | sufficient_sample | 4.2068 | 5.7020 | 10.7403 | 0.7143 | 4.2068 | 0.7143 | 2.2449 | 3.9986 | 0.7143 | 3.6870 | 0.7143 | DIS | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -1.8183 | -3.4472 | 7.0947 | 0.2000 | -1.8183 | 0.2000 | 6.5317 | -2.0144 | 0.2000 | -2.3079 | 0.2000 | DIS | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 1.6835 | 0.0335 | 9.2541 | 0.5000 | 1.6835 | 0.5000 | 3.6718 | 1.4803 | 0.5000 | 1.1763 | 0.5000 | DIS | stock |
| candidate | development | 13 | 22 | sufficient_sample | 4.5520 | 7.7395 | 10.9844 | 0.6818 | 4.5520 | 0.6818 | 2.4069 | 4.3431 | 0.6818 | 4.0305 | 0.6818 | DIS | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -1.4840 | -4.8586 | 12.0696 | 0.3846 | -1.4840 | 0.3846 | 4.8893 | -1.6808 | 0.3077 | -1.9754 | 0.3077 | DIS | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 4.8996 | 4.5376 | 13.2725 | 0.6923 | 4.8996 | 0.6923 | 3.6095 | 4.6900 | 0.6923 | 4.3764 | 0.6923 | DIS | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.5176 | 0.7537 | 9.4935 | 0.5714 | 3.5176 | 0.5714 | 2.6305 | 3.3108 | 0.5714 | 3.0013 | 0.5238 | GOOGL | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 9.7660 | 13.6771 | 17.3043 | 0.6667 | 9.7660 | 0.6667 | 3.1321 | 9.5467 | 0.6667 | 9.2185 | 0.6667 | GOOGL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.0811 | 7.9796 | 8.4463 | 0.7692 | 5.0811 | 0.7692 | 3.3428 | 4.8711 | 0.7692 | 4.5570 | 0.7692 | GOOGL | stock |
| candidate | development | 13 | 23 | sufficient_sample | 4.2679 | 0.7537 | 9.5322 | 0.5217 | 4.2679 | 0.5217 | 2.6662 | 4.0596 | 0.5217 | 3.7479 | 0.5217 | GOOGL | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 8.5477 | 9.3683 | 15.3016 | 0.7333 | 8.5477 | 0.7333 | 3.7373 | 8.3308 | 0.7333 | 8.0063 | 0.7333 | GOOGL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.5994 | 6.7966 | 8.6086 | 0.8462 | 6.5994 | 0.8462 | 3.8496 | 6.3865 | 0.8462 | 6.0678 | 0.8462 | GOOGL | stock |
| baseline | development | 13 | 16 | insufficient_sample | 5.3658 | 4.1647 | 11.8947 | 0.6875 | 5.3658 | 0.6875 | 3.9226 | 5.1553 | 0.6875 | 4.8403 | 0.6875 | GS | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.5687 | 8.8498 | 11.5098 | 0.7333 | 7.5687 | 0.7333 | 3.7429 | 7.3538 | 0.7333 | 7.0322 | 0.7333 | GS | stock |
| baseline | validation | 13 | 10 | insufficient_sample | -0.5274 | 0.2114 | 7.6256 | 0.5000 | -0.5274 | 0.5000 | 3.8243 | -0.7261 | 0.5000 | -1.0235 | 0.5000 | GS | stock |
| candidate | development | 13 | 20 | sufficient_sample | -0.4545 | -0.3925 | 10.4953 | 0.5000 | -0.4545 | 0.5000 | 2.0917 | -0.6534 | 0.4500 | -0.9510 | 0.4500 | GS | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 8.0212 | 5.7153 | 13.9441 | 0.6667 | 8.0212 | 0.6667 | 5.3895 | 7.8054 | 0.6667 | 7.4825 | 0.6667 | GS | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -0.9118 | -1.7557 | 7.0154 | 0.4167 | -0.9118 | 0.4167 | 3.1742 | -1.1097 | 0.4167 | -1.4060 | 0.4167 | GS | stock |
| baseline | development | 13 | 22 | sufficient_sample | 7.5598 | 11.2858 | 10.5478 | 0.7727 | 7.5598 | 0.7727 | 3.0662 | 7.3449 | 0.7273 | 7.0234 | 0.7273 | HD | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 2.3297 | 1.7539 | 13.4136 | 0.5385 | 2.3297 | 0.5385 | 4.0809 | 2.1252 | 0.5385 | 1.8193 | 0.5385 | HD | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 4.4060 | 7.3081 | 12.9323 | 0.6154 | 4.4060 | 0.6154 | 3.0046 | 4.1974 | 0.6154 | 3.8852 | 0.6154 | HD | stock |
| candidate | development | 13 | 24 | sufficient_sample | 6.8785 | 5.7546 | 9.1969 | 0.8333 | 6.8785 | 0.8333 | 3.5974 | 6.6650 | 0.7917 | 6.3455 | 0.7917 | HD | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 3.2789 | 4.5904 | 10.5697 | 0.7333 | 3.2789 | 0.7333 | 3.0590 | 3.0725 | 0.7333 | 2.7638 | 0.7333 | HD | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 5.1823 | 8.0158 | 14.5106 | 0.6923 | 5.1823 | 0.6923 | 2.9046 | 4.9722 | 0.6923 | 4.6577 | 0.6923 | HD | stock |
| baseline | development | 13 | 23 | sufficient_sample | 3.4372 | 3.6947 | 9.1256 | 0.6087 | 3.4372 | 0.6087 | 2.4091 | 3.2306 | 0.6087 | 2.9213 | 0.6087 | HON | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 1.6937 | 4.0748 | 6.8999 | 0.6154 | 1.6937 | 0.6154 | 5.1278 | 1.4905 | 0.6154 | 1.1865 | 0.6154 | HON | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 2.9298 | 4.4567 | 15.2570 | 0.7692 | 2.9298 | 0.7692 | 1.9042 | 2.7242 | 0.7692 | 2.4165 | 0.7692 | HON | stock |
| candidate | development | 13 | 24 | sufficient_sample | 4.4823 | 5.2505 | 9.3169 | 0.7083 | 4.4823 | 0.7083 | 2.9269 | 4.2735 | 0.7083 | 3.9612 | 0.6667 | HON | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.8423 | 1.9705 | 9.5139 | 0.5333 | 0.8423 | 0.5333 | 3.2565 | 0.6408 | 0.5333 | 0.3394 | 0.5333 | HON | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.3621 | 6.2549 | 11.5113 | 0.7692 | 6.3621 | 0.7692 | 4.2628 | 6.1496 | 0.7692 | 5.8316 | 0.7692 | HON | stock |
| baseline | development | 13 | 18 | insufficient_sample | 1.5485 | 0.2427 | 6.8151 | 0.6111 | 1.5485 | 0.6111 | 3.2758 | 1.3456 | 0.5556 | 1.0420 | 0.4444 | IBM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 5.1271 | 5.8032 | 8.9344 | 0.6667 | 5.1271 | 0.6667 | 2.9877 | 4.9170 | 0.6000 | 4.6027 | 0.6000 | IBM | stock |
| baseline | validation | 13 | 9 | insufficient_sample | -4.6416 | -3.4105 | 8.4768 | 0.4444 | -4.6416 | 0.4444 | 0.8831 | -4.8321 | 0.4444 | -5.1172 | 0.4444 | IBM | stock |
| candidate | development | 13 | 21 | sufficient_sample | 2.2854 | 2.5767 | 8.2938 | 0.6667 | 2.2854 | 0.6667 | 3.3995 | 2.0810 | 0.6190 | 1.7753 | 0.6190 | IBM | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 5.4204 | 5.0697 | 10.8438 | 0.6471 | 5.4204 | 0.6471 | 3.5549 | 5.2098 | 0.5882 | 4.8946 | 0.5882 | IBM | stock |
| candidate | validation | 13 | 11 | insufficient_sample | -0.7183 | 0.8264 | 7.7235 | 0.6364 | -0.7183 | 0.6364 | 2.9202 | -0.9166 | 0.6364 | -1.2135 | 0.6364 | IBM | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.0828 | 1.5397 | 8.2886 | 0.6190 | 2.0828 | 0.6190 | 2.1731 | 1.8788 | 0.6190 | 1.5737 | 0.6190 | IWM | etf |
| baseline | holdout | 13 | 13 | insufficient_sample | 2.2399 | 2.7930 | 7.7281 | 0.6154 | 2.2399 | 0.6154 | 4.2443 | 2.0356 | 0.6154 | 1.7300 | 0.6154 | IWM | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.0526 | 2.4238 | 13.7217 | 0.6154 | 1.0526 | 0.6154 | 2.7572 | 0.8507 | 0.6154 | 0.5486 | 0.6154 | IWM | etf |
| candidate | development | 13 | 23 | sufficient_sample | 2.0129 | 4.2558 | 8.7471 | 0.5217 | 2.0129 | 0.5217 | 2.1040 | 1.8091 | 0.5217 | 1.5041 | 0.5217 | IWM | etf |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.6350 | 2.6230 | 8.7868 | 0.6000 | 0.6350 | 0.6000 | 3.2887 | 0.4339 | 0.6000 | 0.1331 | 0.5333 | IWM | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.4704 | 3.9013 | 14.8012 | 0.6923 | 1.4704 | 0.6923 | 3.1641 | 1.2677 | 0.6923 | 0.9643 | 0.6923 | IWM | etf |
| baseline | development | 13 | 21 | sufficient_sample | 3.3131 | 1.8422 | 6.6207 | 0.6667 | 3.3131 | 0.6667 | 3.7649 | 3.1067 | 0.6667 | 2.7978 | 0.6190 | JNJ | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 1.4170 | 1.7025 | 7.3780 | 0.5625 | 1.4170 | 0.5625 | 2.9124 | 1.2143 | 0.5625 | 0.9111 | 0.5625 | JNJ | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.2276 | 2.7347 | 5.4751 | 0.5833 | 2.2276 | 0.5833 | 3.5679 | 2.0233 | 0.5833 | 1.7177 | 0.5833 | JNJ | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.2420 | 1.1853 | 6.7105 | 0.6522 | 3.2420 | 0.6522 | 3.1928 | 3.0358 | 0.6522 | 2.7271 | 0.6087 | JNJ | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.2804 | 0.6927 | 7.4135 | 0.5000 | 1.2804 | 0.5000 | 3.4070 | 1.0780 | 0.5000 | 0.7752 | 0.5000 | JNJ | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 1.8379 | 0.5782 | 5.4307 | 0.5385 | 1.8379 | 0.5385 | 3.6260 | 1.6345 | 0.5385 | 1.3300 | 0.5385 | JNJ | stock |
| baseline | development | 13 | 20 | sufficient_sample | 4.0092 | 2.9191 | 10.2926 | 0.7000 | 4.0092 | 0.7000 | 2.7584 | 3.8014 | 0.7000 | 3.4904 | 0.6500 | JPM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.6598 | 6.5677 | 8.9240 | 0.8000 | 7.6598 | 0.8000 | 5.1325 | 7.4447 | 0.8000 | 7.1229 | 0.8000 | JPM | stock |
| baseline | validation | 13 | 11 | insufficient_sample | 2.2591 | 4.4627 | 11.2878 | 0.6364 | 2.2591 | 0.6364 | 2.4398 | 2.0547 | 0.6364 | 1.7490 | 0.6364 | JPM | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.4955 | 3.5635 | 9.7464 | 0.6522 | 3.4955 | 0.6522 | 3.2342 | 3.2887 | 0.6522 | 2.9793 | 0.6522 | JPM | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.9788 | 5.2783 | 11.2691 | 0.6250 | 4.9788 | 0.6250 | 3.7610 | 4.7691 | 0.6250 | 4.4552 | 0.6250 | JPM | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 3.0737 | 2.0633 | 10.9369 | 0.5000 | 3.0737 | 0.5000 | 4.0093 | 2.8677 | 0.5000 | 2.5596 | 0.5000 | JPM | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.4993 | 2.8912 | 4.8654 | 0.7727 | 2.4993 | 0.7727 | 2.5155 | 2.2945 | 0.7727 | 1.9881 | 0.7273 | KO | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 2.3248 | 0.1292 | 6.4444 | 0.5333 | 2.3248 | 0.5333 | 3.1399 | 2.1204 | 0.4667 | 1.8145 | 0.4000 | KO | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.4435 | 2.2333 | 5.7330 | 0.7500 | 2.4435 | 0.7500 | 3.2083 | 2.2388 | 0.7500 | 1.9326 | 0.7500 | KO | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.1806 | 1.9058 | 4.6037 | 0.7826 | 2.1806 | 0.7826 | 2.8041 | 1.9764 | 0.7826 | 1.6710 | 0.6522 | KO | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 3.0838 | 1.1110 | 6.8339 | 0.6250 | 3.0838 | 0.6250 | 3.8390 | 2.8779 | 0.6250 | 2.5697 | 0.5625 | KO | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.0210 | 1.7626 | 4.9398 | 0.7692 | 2.0210 | 0.7692 | 3.6240 | 1.8172 | 0.7692 | 1.5122 | 0.7692 | KO | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.1482 | -0.8177 | 8.3342 | 0.4545 | 3.1482 | 0.4545 | 3.0897 | 2.9421 | 0.4545 | 2.6337 | 0.4545 | MCD | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 3.2242 | 3.1823 | 4.4958 | 0.8000 | 3.2242 | 0.8000 | 4.2506 | 3.0180 | 0.7333 | 2.7094 | 0.5333 | MCD | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 5.0642 | 5.4550 | 7.6903 | 0.6667 | 5.0642 | 0.6667 | 2.6667 | 4.8543 | 0.6667 | 4.5402 | 0.6667 | MCD | stock |
| candidate | development | 13 | 24 | sufficient_sample | 3.2742 | 3.3481 | 6.7206 | 0.6667 | 3.2742 | 0.6667 | 3.0676 | 3.0678 | 0.6667 | 2.7591 | 0.6250 | MCD | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 2.4107 | 3.0848 | 5.9099 | 0.6875 | 2.4107 | 0.6875 | 4.1785 | 2.2061 | 0.6875 | 1.8999 | 0.5625 | MCD | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 6.4858 | 6.5779 | 6.0675 | 0.7500 | 6.4858 | 0.7500 | 3.4308 | 6.2731 | 0.7500 | 5.9547 | 0.7500 | MCD | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.3763 | 2.8781 | 7.6845 | 0.5909 | 3.3763 | 0.5909 | 3.0545 | 3.1698 | 0.5909 | 2.8607 | 0.5909 | MMM | stock |
| baseline | holdout | 13 | 12 | insufficient_sample | 3.3535 | 1.5289 | 14.2554 | 0.5000 | 3.3535 | 0.5000 | 5.1533 | 3.1470 | 0.5000 | 2.8380 | 0.5000 | MMM | stock |
| baseline | validation | 13 | 10 | insufficient_sample | -2.9009 | 2.2243 | 10.7605 | 0.6000 | -2.9009 | 0.6000 | 1.2832 | -3.0949 | 0.6000 | -3.3852 | 0.5000 | MMM | stock |
| candidate | development | 13 | 24 | sufficient_sample | 3.6196 | 3.6898 | 7.5523 | 0.5833 | 3.6196 | 0.5833 | 3.2694 | 3.4126 | 0.5833 | 3.1028 | 0.5833 | MMM | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | 3.5838 | 2.9354 | 13.8631 | 0.5385 | 3.5838 | 0.5385 | 3.6398 | 3.3769 | 0.5385 | 3.0672 | 0.5385 | MMM | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -1.9568 | 2.6411 | 10.8920 | 0.5833 | -1.9568 | 0.5833 | 1.5310 | -2.1527 | 0.5833 | -2.4458 | 0.5833 | MMM | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.2036 | 1.5887 | 8.1312 | 0.6190 | 3.2036 | 0.6190 | 4.2030 | 2.9974 | 0.6190 | 2.6889 | 0.6190 | MRK | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 4.0377 | 1.6241 | 10.4762 | 0.7692 | 4.0377 | 0.7692 | 4.1398 | 3.8298 | 0.7692 | 3.5188 | 0.6923 | MRK | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.3736 | 2.3669 | 7.9699 | 0.6667 | 2.3736 | 0.6667 | 2.5652 | 2.1691 | 0.6667 | 1.8630 | 0.6667 | MRK | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.9207 | 1.6395 | 8.4051 | 0.6087 | 2.9207 | 0.6087 | 2.6345 | 2.7151 | 0.5652 | 2.4074 | 0.5652 | MRK | stock |
| candidate | holdout | 13 | 14 | insufficient_sample | 2.5635 | 1.0163 | 12.5318 | 0.5714 | 2.5635 | 0.5714 | 3.8394 | 2.3585 | 0.5714 | 2.0519 | 0.5000 | MRK | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.3086 | 2.8512 | 8.0102 | 0.6154 | 2.3086 | 0.6154 | 3.6230 | 2.1042 | 0.6154 | 1.7983 | 0.6154 | MRK | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.1091 | 1.5860 | 9.4159 | 0.6667 | 2.1091 | 0.6667 | 1.6171 | 1.9051 | 0.6667 | 1.5998 | 0.6190 | MSFT | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 4.2327 | 9.1370 | 13.4566 | 0.6000 | 4.2327 | 0.6000 | 2.9409 | 4.0244 | 0.6000 | 3.7128 | 0.6000 | MSFT | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 11.5720 | 9.3597 | 11.0305 | 0.9231 | 11.5720 | 0.9231 | 5.5391 | 11.3490 | 0.9231 | 11.0155 | 0.9231 | MSFT | stock |
| candidate | development | 13 | 22 | sufficient_sample | 3.7253 | 3.2785 | 10.6559 | 0.7273 | 3.7253 | 0.7273 | 2.6404 | 3.5181 | 0.7273 | 3.2080 | 0.6818 | MSFT | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1682 | 1.3988 | 14.1060 | 0.6875 | 4.1682 | 0.6875 | 3.5358 | 3.9600 | 0.6875 | 3.6486 | 0.5625 | MSFT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 10.3417 | 9.7755 | 8.4491 | 0.9231 | 10.3417 | 0.9231 | 4.0262 | 10.1212 | 0.9231 | 9.7914 | 0.9231 | MSFT | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.8101 | 5.3284 | 10.4633 | 0.6364 | 3.8101 | 0.6364 | 2.6677 | 3.6027 | 0.6364 | 3.2923 | 0.6364 | NKE | stock |
| baseline | holdout | 13 | 9 | insufficient_sample | -4.0403 | -7.8198 | 14.3979 | 0.3333 | -4.0403 | 0.3333 | 4.9913 | -4.2320 | 0.3333 | -4.5189 | 0.3333 | NKE | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 7.5323 | 11.5335 | 12.0757 | 0.6667 | 7.5323 | 0.6667 | 4.9356 | 7.3175 | 0.6667 | 6.9960 | 0.6667 | NKE | stock |
| candidate | development | 13 | 23 | sufficient_sample | 5.3634 | 6.8810 | 10.4743 | 0.6957 | 5.3634 | 0.6957 | 2.9566 | 5.1528 | 0.6957 | 4.8379 | 0.6957 | NKE | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -5.3128 | -7.8198 | 16.3751 | 0.3077 | -5.3128 | 0.3077 | 4.3596 | -5.5020 | 0.3077 | -5.7851 | 0.3077 | NKE | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 7.0634 | 10.2169 | 14.1997 | 0.7692 | 7.0634 | 0.7692 | 3.1363 | 6.8495 | 0.7692 | 6.5294 | 0.6923 | NKE | stock |
| baseline | development | 13 | 20 | sufficient_sample | 9.1776 | 5.6208 | 29.3876 | 0.6500 | 9.1776 | 0.6500 | 2.5345 | 8.9594 | 0.6500 | 8.6331 | 0.6000 | NVDA | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 21.9178 | 21.7756 | 32.5008 | 0.7333 | 21.9178 | 0.7333 | 3.6083 | 21.6742 | 0.7333 | 21.3097 | 0.7333 | NVDA | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 14.4849 | 13.9394 | 26.8504 | 0.8333 | 14.4849 | 0.8333 | 2.9920 | 14.2561 | 0.7500 | 13.9139 | 0.7500 | NVDA | stock |
| candidate | development | 13 | 21 | sufficient_sample | 8.0031 | 3.0844 | 31.3222 | 0.6667 | 8.0031 | 0.6667 | 3.3609 | 7.7873 | 0.6190 | 7.4644 | 0.6190 | NVDA | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 19.7312 | 18.6250 | 31.5106 | 0.7333 | 19.7312 | 0.7333 | 4.1143 | 19.4920 | 0.7333 | 19.1340 | 0.7333 | NVDA | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 14.2977 | 14.0369 | 30.3438 | 0.7500 | 14.2977 | 0.7500 | 3.2837 | 14.0694 | 0.6667 | 13.7277 | 0.6667 | NVDA | stock |
| baseline | development | 13 | 21 | sufficient_sample | 0.7501 | 1.0942 | 9.4742 | 0.6190 | 0.7501 | 0.6190 | 2.5389 | 0.5488 | 0.6190 | 0.2476 | 0.5714 | ORCL | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 8.0113 | 14.7641 | 22.2087 | 0.7143 | 8.0113 | 0.7143 | 4.6698 | 7.7954 | 0.7143 | 7.4725 | 0.7143 | ORCL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 2.4444 | 2.9649 | 6.3438 | 0.8462 | 2.4444 | 0.8462 | 4.0007 | 2.2397 | 0.8462 | 1.9334 | 0.8462 | ORCL | stock |
| candidate | development | 13 | 22 | sufficient_sample | 0.2592 | 1.0353 | 9.2605 | 0.5455 | 0.2592 | 0.5455 | 2.2053 | 0.0589 | 0.5455 | -0.2408 | 0.5455 | ORCL | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 10.9615 | 10.6895 | 18.4956 | 0.6250 | 10.9615 | 0.6250 | 3.4439 | 10.7398 | 0.6250 | 10.4081 | 0.6250 | ORCL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.2190 | 2.9649 | 6.6123 | 0.7692 | 2.2190 | 0.7692 | 2.4754 | 2.0147 | 0.7692 | 1.7091 | 0.7692 | ORCL | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.7613 | 3.1593 | 9.1451 | 0.6190 | 2.7613 | 0.6190 | 2.5646 | 2.5559 | 0.5714 | 2.2487 | 0.5714 | PFE | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -0.9945 | 0.7749 | 9.3934 | 0.5000 | -0.9945 | 0.5000 | 2.2448 | -1.1924 | 0.5000 | -1.4883 | 0.5000 | PFE | stock |
| baseline | validation | 13 | 12 | insufficient_sample | -0.5493 | 0.4402 | 10.4258 | 0.5000 | -0.5493 | 0.5000 | 2.9446 | -0.7481 | 0.5000 | -1.0454 | 0.5000 | PFE | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.7061 | 3.4508 | 9.0882 | 0.6087 | 2.7061 | 0.6087 | 2.6908 | 2.5009 | 0.6087 | 2.1939 | 0.5652 | PFE | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -1.6151 | -4.1796 | 8.2204 | 0.3846 | -1.6151 | 0.3846 | 2.4180 | -1.8117 | 0.3846 | -2.1058 | 0.3846 | PFE | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 0.8894 | 1.8111 | 8.7618 | 0.5385 | 0.8894 | 0.5385 | 2.7327 | 0.6878 | 0.5385 | 0.3862 | 0.5385 | PFE | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.9810 | 2.5128 | 5.4002 | 0.6667 | 2.9810 | 0.6667 | 3.8520 | 2.7752 | 0.6667 | 2.4674 | 0.6190 | PG | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 1.3077 | 1.9015 | 4.7631 | 0.5714 | 1.3077 | 0.5714 | 4.4146 | 1.1053 | 0.5714 | 0.8025 | 0.5714 | PG | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 3.9176 | 4.4445 | 7.2678 | 0.7500 | 3.9176 | 0.7500 | 2.9803 | 3.7100 | 0.7500 | 3.3993 | 0.7500 | PG | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.2069 | 2.5948 | 5.0242 | 0.6522 | 2.2069 | 0.6522 | 2.6776 | 2.0027 | 0.6522 | 1.6972 | 0.6522 | PG | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 1.0713 | 1.5741 | 4.6859 | 0.5333 | 1.0713 | 0.5333 | 3.6948 | 0.8694 | 0.5333 | 0.5672 | 0.5333 | PG | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 4.5356 | 5.4546 | 5.9762 | 0.7500 | 4.5356 | 0.7500 | 3.2986 | 4.3267 | 0.7500 | 4.0142 | 0.7500 | PG | stock |
| baseline | development | 13 | 23 | sufficient_sample | 3.2756 | 5.4386 | 7.0813 | 0.7391 | 3.2756 | 0.7391 | 2.2786 | 3.0692 | 0.7391 | 2.7605 | 0.6957 | QQQ | etf |
| baseline | holdout | 13 | 14 | insufficient_sample | 5.6977 | 7.8688 | 7.1831 | 0.7857 | 5.6977 | 0.7857 | 4.8581 | 5.4866 | 0.7857 | 5.1706 | 0.7857 | QQQ | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 5.5237 | 7.0227 | 10.8387 | 0.8462 | 5.5237 | 0.8462 | 2.4864 | 5.3128 | 0.8462 | 4.9974 | 0.8462 | QQQ | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.7821 | 4.5354 | 6.6514 | 0.7083 | 3.7821 | 0.7083 | 2.9714 | 3.5747 | 0.7083 | 3.2645 | 0.7083 | QQQ | etf |
| candidate | holdout | 13 | 15 | insufficient_sample | 2.5388 | 7.2561 | 8.9703 | 0.7333 | 2.5388 | 0.7333 | 2.7760 | 2.3340 | 0.7333 | 2.0274 | 0.7333 | QQQ | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 7.2302 | 7.0812 | 10.7577 | 0.8462 | 7.2302 | 0.8462 | 4.8522 | 7.0159 | 0.8462 | 6.6954 | 0.8462 | QQQ | etf |
| baseline | development | 13 | 23 | sufficient_sample | 5.6784 | 3.3654 | 8.3572 | 0.7391 | 5.6784 | 0.7391 | 2.8790 | 5.4672 | 0.7391 | 5.1513 | 0.7391 | UNH | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | -2.0211 | 0.3046 | 15.8435 | 0.5000 | -2.0211 | 0.5000 | 3.9994 | -2.2169 | 0.5000 | -2.5098 | 0.5000 | UNH | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 4.5031 | 5.6998 | 9.6880 | 0.7692 | 4.5031 | 0.7692 | 4.0606 | 4.2943 | 0.7692 | 3.9819 | 0.7692 | UNH | stock |
| candidate | development | 13 | 24 | sufficient_sample | 6.7045 | 8.4597 | 8.4888 | 0.7083 | 6.7045 | 0.7083 | 2.9191 | 6.4913 | 0.6667 | 6.1723 | 0.6667 | UNH | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | -1.3417 | 2.8059 | 13.5363 | 0.6250 | -1.3417 | 0.6250 | 6.2322 | -1.5388 | 0.6250 | -1.8338 | 0.6250 | UNH | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 3.9211 | 5.7950 | 7.6947 | 0.7692 | 3.9211 | 0.7692 | 4.0262 | 3.7135 | 0.7692 | 3.4028 | 0.7692 | UNH | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.7681 | 2.8392 | 7.2890 | 0.6818 | 2.7681 | 0.6818 | 3.0006 | 2.5628 | 0.6818 | 2.2555 | 0.6818 | UPS | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -2.2825 | -5.4246 | 9.9179 | 0.4000 | -2.2825 | 0.4000 | 0.2780 | -2.4778 | 0.4000 | -2.7699 | 0.4000 | UPS | stock |
| baseline | validation | 13 | 11 | insufficient_sample | 2.7843 | -5.8445 | 19.2669 | 0.4545 | 2.7843 | 0.4545 | 2.9906 | 2.5789 | 0.4545 | 2.2716 | 0.4545 | UPS | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.1141 | 2.9893 | 7.6909 | 0.6522 | 3.1141 | 0.6522 | 2.8686 | 2.9080 | 0.6522 | 2.5998 | 0.6522 | UPS | stock |
| candidate | holdout | 13 | 11 | insufficient_sample | -2.0985 | 0.6846 | 10.1882 | 0.5455 | -2.0985 | 0.5455 | 1.2140 | -2.2941 | 0.5455 | -2.5868 | 0.5455 | UPS | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 4.6507 | 3.6882 | 15.1569 | 0.6667 | 4.6507 | 0.6667 | 4.7853 | 4.4416 | 0.6667 | 4.1288 | 0.6667 | UPS | stock |
| baseline | development | 13 | 20 | sufficient_sample | 2.8665 | 2.1660 | 7.8070 | 0.5500 | 2.8665 | 0.5500 | 4.5268 | 2.6609 | 0.5500 | 2.3534 | 0.5500 | WMT | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 3.6152 | 1.9638 | 10.3336 | 0.6875 | 3.6152 | 0.6875 | 2.7511 | 3.4081 | 0.6250 | 3.0984 | 0.6250 | WMT | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 5.9804 | 7.4495 | 9.9113 | 0.7500 | 5.9804 | 0.7500 | 2.6603 | 5.7686 | 0.6667 | 5.4518 | 0.6667 | WMT | stock |
| candidate | development | 13 | 22 | sufficient_sample | 3.1922 | 2.6374 | 8.8312 | 0.6364 | 3.1922 | 0.6364 | 2.7710 | 2.9860 | 0.6364 | 2.6775 | 0.6364 | WMT | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 3.6152 | 1.9638 | 10.3336 | 0.6875 | 3.6152 | 0.6875 | 2.7511 | 3.4081 | 0.6250 | 3.0984 | 0.6250 | WMT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 7.1590 | 7.7308 | 9.9173 | 0.6923 | 7.1590 | 0.6923 | 3.3387 | 6.9449 | 0.6923 | 6.6246 | 0.6923 | WMT | stock |
| baseline | development | 13 | 21 | sufficient_sample | 0.8170 | 1.9527 | 8.2428 | 0.6667 | 0.8170 | 0.6667 | 2.6716 | 0.6156 | 0.6667 | 0.3142 | 0.6190 | XLB | etf |
| baseline | holdout | 13 | 13 | insufficient_sample | 1.0067 | 2.3309 | 6.9643 | 0.6923 | 1.0067 | 0.6923 | 4.1455 | 0.8049 | 0.6923 | 0.5030 | 0.6923 | XLB | etf |
| baseline | validation | 13 | 12 | insufficient_sample | 3.6421 | 4.4353 | 7.1346 | 0.8333 | 3.6421 | 0.8333 | 4.4249 | 3.4350 | 0.8333 | 3.1251 | 0.8333 | XLB | etf |
| candidate | development | 13 | 23 | sufficient_sample | 0.5030 | 4.3726 | 9.3444 | 0.6087 | 0.5030 | 0.6087 | 2.4640 | 0.3022 | 0.6087 | 0.0018 | 0.6087 | XLB | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.1176 | 1.8530 | 6.3299 | 0.6250 | 1.1176 | 0.6250 | 2.8575 | 0.9156 | 0.6250 | 0.6133 | 0.5625 | XLB | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 3.4859 | 4.0423 | 7.9668 | 0.8462 | 3.4859 | 0.8462 | 4.0429 | 3.2791 | 0.8462 | 2.9697 | 0.8462 | XLB | etf |
| baseline | development | 13 | 17 | insufficient_sample | 3.1086 | 2.0806 | 9.1262 | 0.7059 | 3.1086 | 0.7059 | 3.3920 | 2.9026 | 0.7059 | 2.5943 | 0.7059 | XLE | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 5.0719 | 1.5708 | 11.4244 | 0.6000 | 5.0719 | 0.6000 | 2.9487 | 4.8620 | 0.6000 | 4.5478 | 0.6000 | XLE | etf |
| baseline | validation | 13 | 7 | insufficient_sample | -9.0700 | -4.8687 | 18.4857 | 0.2857 | -9.0700 | 0.2857 | -0.6097 | -9.2517 | 0.2857 | -9.5236 | 0.2857 | XLE | etf |
| candidate | development | 13 | 22 | sufficient_sample | 1.4418 | 2.0410 | 11.9625 | 0.5909 | 1.4418 | 0.5909 | 3.0735 | 1.2391 | 0.5909 | 0.9359 | 0.5909 | XLE | etf |
| candidate | holdout | 13 | 17 | insufficient_sample | 5.6537 | 4.1271 | 10.9153 | 0.6471 | 5.6537 | 0.6471 | 3.8807 | 5.4426 | 0.6471 | 5.1268 | 0.6471 | XLE | etf |
| candidate | validation | 13 | 11 | insufficient_sample | -6.4326 | -3.2355 | 14.7255 | 0.2727 | -6.4326 | 0.2727 | 1.9748 | -6.6196 | 0.2727 | -6.8993 | 0.1818 | XLE | etf |
| baseline | development | 13 | 20 | sufficient_sample | 2.6619 | 3.0108 | 7.2581 | 0.7000 | 2.6619 | 0.7000 | 2.4618 | 2.4568 | 0.7000 | 2.1499 | 0.6500 | XLF | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 2.8315 | 3.2517 | 8.5082 | 0.7333 | 2.8315 | 0.7333 | 3.2358 | 2.6260 | 0.7333 | 2.3186 | 0.7333 | XLF | etf |
| baseline | validation | 13 | 11 | insufficient_sample | 0.1498 | 3.1460 | 10.3479 | 0.6364 | 0.1498 | 0.6364 | 2.2943 | -0.0503 | 0.6364 | -0.3497 | 0.6364 | XLF | etf |
| candidate | development | 13 | 23 | sufficient_sample | 1.6437 | 3.4120 | 9.1594 | 0.7391 | 1.6437 | 0.7391 | 2.0099 | 1.4406 | 0.7391 | 1.1367 | 0.7391 | XLF | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.2994 | 3.0221 | 9.2444 | 0.7500 | 4.2994 | 0.7500 | 3.6593 | 4.0910 | 0.7500 | 3.7792 | 0.7500 | XLF | etf |
| candidate | validation | 13 | 12 | insufficient_sample | 0.0838 | 2.8983 | 9.4142 | 0.5833 | 0.0838 | 0.5833 | 2.1173 | -0.1162 | 0.5833 | -0.4154 | 0.5833 | XLF | etf |
| baseline | development | 13 | 23 | sufficient_sample | 2.3692 | 3.1555 | 7.5182 | 0.6957 | 2.3692 | 0.6957 | 2.4984 | 2.1647 | 0.6957 | 1.8586 | 0.6957 | XLI | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 2.8905 | 2.4031 | 7.4715 | 0.6875 | 2.8905 | 0.6875 | 3.0720 | 2.6849 | 0.6875 | 2.3773 | 0.6875 | XLI | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.1605 | 3.0046 | 10.8723 | 0.8462 | 1.1605 | 0.8462 | 2.3884 | 0.9583 | 0.8462 | 0.6559 | 0.8462 | XLI | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.9479 | 3.0301 | 7.5000 | 0.6667 | 2.9479 | 0.6667 | 2.7863 | 2.7422 | 0.6250 | 2.4344 | 0.6250 | XLI | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.3801 | 4.1777 | 7.1073 | 0.7500 | 4.3801 | 0.7500 | 4.6771 | 4.1716 | 0.7500 | 3.8595 | 0.7500 | XLI | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 0.6006 | 3.6401 | 13.0801 | 0.7692 | 0.6006 | 0.7692 | 1.9042 | 0.3996 | 0.7692 | 0.0988 | 0.7692 | XLI | etf |
| baseline | development | 13 | 23 | sufficient_sample | 3.4941 | 5.0231 | 5.9357 | 0.7391 | 3.4941 | 0.7391 | 2.9447 | 3.2873 | 0.7391 | 2.9779 | 0.7391 | XLK | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 3.9875 | 8.5505 | 9.7227 | 0.6875 | 3.9875 | 0.6875 | 2.8955 | 3.7798 | 0.6875 | 3.4689 | 0.6875 | XLK | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 5.7183 | 6.7462 | 11.1740 | 0.8462 | 5.7183 | 0.8462 | 2.4864 | 5.5071 | 0.8462 | 5.1910 | 0.8462 | XLK | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.0670 | 3.2623 | 6.2304 | 0.6667 | 3.0670 | 0.6667 | 2.9819 | 2.8610 | 0.6667 | 2.5529 | 0.6667 | XLK | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1913 | 8.5505 | 9.2532 | 0.6875 | 4.1913 | 0.6875 | 3.1863 | 3.9831 | 0.6875 | 3.6716 | 0.6875 | XLK | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 6.6663 | 6.3559 | 11.6246 | 0.7692 | 6.6663 | 0.7692 | 3.1428 | 6.4532 | 0.7692 | 6.1343 | 0.7692 | XLK | etf |
| baseline | development | 13 | 24 | sufficient_sample | 2.9692 | 2.5683 | 3.4912 | 0.8333 | 2.9692 | 0.8333 | 2.6826 | 2.7634 | 0.7917 | 2.4556 | 0.7500 | XLP | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 1.8381 | 1.7333 | 3.0506 | 0.7333 | 1.8381 | 0.7333 | 2.9786 | 1.6346 | 0.7333 | 1.3302 | 0.7333 | XLP | etf |
| baseline | validation | 13 | 12 | insufficient_sample | 1.6557 | 3.3820 | 3.7831 | 0.6667 | 1.6557 | 0.6667 | 3.2543 | 1.4526 | 0.6667 | 1.1487 | 0.6667 | XLP | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.1745 | 3.0911 | 3.5935 | 0.8750 | 3.1745 | 0.8750 | 2.9412 | 2.9684 | 0.8333 | 2.6599 | 0.7917 | XLP | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.4225 | 2.1545 | 4.6997 | 0.6250 | 1.4225 | 0.6250 | 3.4309 | 1.2199 | 0.6250 | 0.9167 | 0.6250 | XLP | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.7087 | 2.8357 | 6.0341 | 0.6923 | 1.7087 | 0.6923 | 3.9328 | 1.5055 | 0.6154 | 1.2014 | 0.6154 | XLP | etf |
| baseline | development | 13 | 23 | sufficient_sample | 2.5737 | 1.9694 | 6.4594 | 0.6522 | 2.5737 | 0.6522 | 2.9507 | 2.3688 | 0.6522 | 2.0621 | 0.6087 | XLU | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 0.7840 | 1.0790 | 5.7184 | 0.6000 | 0.7840 | 0.6000 | 3.4889 | 0.5827 | 0.6000 | 0.2814 | 0.6000 | XLU | etf |
| baseline | validation | 13 | 11 | insufficient_sample | 2.5612 | 3.8881 | 5.7455 | 0.8182 | 2.5612 | 0.8182 | 3.7998 | 2.3563 | 0.8182 | 2.0497 | 0.8182 | XLU | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.3496 | 2.2626 | 4.8018 | 0.7083 | 2.3496 | 0.7083 | 2.8687 | 2.1451 | 0.7083 | 1.8391 | 0.6667 | XLU | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.6778 | 0.5975 | 7.1201 | 0.5625 | 1.6778 | 0.5625 | 2.8383 | 1.4747 | 0.5000 | 1.1707 | 0.5000 | XLU | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.5051 | 3.8881 | 8.6011 | 0.8462 | 1.5051 | 0.8462 | 3.9734 | 1.3023 | 0.8462 | 0.9988 | 0.8462 | XLU | etf |
| baseline | development | 13 | 22 | sufficient_sample | 3.1726 | 4.3756 | 6.1358 | 0.7727 | 3.1726 | 0.7727 | 2.7175 | 2.9664 | 0.7727 | 2.6580 | 0.7273 | XLV | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 0.7281 | -0.2496 | 6.7807 | 0.4667 | 0.7281 | 0.4667 | 2.1614 | 0.5269 | 0.4667 | 0.2258 | 0.4000 | XLV | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 3.3394 | 3.3090 | 5.8875 | 0.6923 | 3.3394 | 0.6923 | 4.0129 | 3.1329 | 0.6923 | 2.8240 | 0.6923 | XLV | etf |
| candidate | development | 13 | 23 | sufficient_sample | 2.6378 | 4.9019 | 6.8462 | 0.7391 | 2.6378 | 0.7391 | 2.0751 | 2.4327 | 0.7391 | 2.1258 | 0.7391 | XLV | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 0.4093 | 0.8360 | 4.3601 | 0.5625 | 0.4093 | 0.5625 | 3.3235 | 0.2086 | 0.5625 | -0.0915 | 0.5625 | XLV | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 3.0522 | 3.5228 | 5.4442 | 0.7692 | 3.0522 | 0.7692 | 4.0262 | 2.8463 | 0.7692 | 2.5382 | 0.7692 | XLV | etf |
| baseline | development | 13 | 23 | sufficient_sample | 4.0371 | 4.2400 | 6.1552 | 0.8261 | 4.0371 | 0.8261 | 2.9209 | 3.8293 | 0.8261 | 3.5182 | 0.7826 | XLY | etf |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.2745 | 3.8081 | 8.3609 | 0.8571 | 3.2745 | 0.8571 | 4.8581 | 3.0681 | 0.8571 | 2.7594 | 0.7857 | XLY | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 3.1602 | 4.2249 | 11.5240 | 0.8462 | 3.1602 | 0.8462 | 3.0493 | 2.9541 | 0.8462 | 2.6457 | 0.8462 | XLY | etf |
| candidate | development | 13 | 24 | sufficient_sample | 4.4204 | 4.9185 | 6.7141 | 0.7917 | 4.4204 | 0.7917 | 3.0684 | 4.2118 | 0.7917 | 3.8996 | 0.7917 | XLY | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 0.6558 | 2.3814 | 9.9546 | 0.6875 | 0.6558 | 0.6875 | 2.8528 | 0.4546 | 0.6875 | 0.1537 | 0.6875 | XLY | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 5.0346 | 4.2249 | 9.3876 | 0.7692 | 5.0346 | 0.7692 | 4.0429 | 4.8248 | 0.7692 | 4.5108 | 0.7692 | XLY | etf |
| baseline | development | 13 | 17 | insufficient_sample | 2.3233 | 1.9157 | 8.8622 | 0.5882 | 2.3233 | 0.5882 | 2.9176 | 2.1188 | 0.5882 | 1.8129 | 0.5882 | XOM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.7048 | 5.2978 | 12.2332 | 0.6667 | 7.7048 | 0.6667 | 3.6115 | 7.4896 | 0.6000 | 7.1677 | 0.6000 | XOM | stock |
| baseline | validation | 13 | 8 | insufficient_sample | -3.0003 | -3.3570 | 4.8647 | 0.2500 | -3.0003 | 0.2500 | 1.8908 | -3.1942 | 0.2500 | -3.4841 | 0.1250 | XOM | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.4006 | 0.6660 | 8.5412 | 0.5217 | 2.4006 | 0.5217 | 3.1399 | 2.1960 | 0.5217 | 1.8898 | 0.5217 | XOM | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 6.6186 | 3.0797 | 12.1599 | 0.7059 | 6.6186 | 0.7059 | 3.8807 | 6.4056 | 0.7059 | 6.0868 | 0.7059 | XOM | stock |
| candidate | validation | 13 | 11 | insufficient_sample | -5.9248 | -6.5552 | 9.0287 | 0.2727 | -5.9248 | 0.2727 | 2.1315 | -6.1127 | 0.2727 | -6.3940 | 0.2727 | XOM | stock |
| baseline | development | 26 | 18 | insufficient_sample | 13.1946 | 13.8697 | 18.3800 | 0.8333 | 13.1946 | 0.8333 | 5.2208 | 12.9684 | 0.8333 | 12.6300 | 0.8333 | AAPL | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 5.3900 | 9.0247 | 11.2891 | 0.6154 | 5.3900 | 0.6154 | 6.6981 | 5.1795 | 0.6154 | 4.8644 | 0.6154 | AAPL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 19.7860 | 17.4563 | 22.6298 | 0.8333 | 19.7860 | 0.8333 | 5.7057 | 19.5466 | 0.8333 | 19.1885 | 0.8333 | AAPL | stock |
| candidate | development | 26 | 21 | sufficient_sample | 13.8405 | 12.4010 | 22.0536 | 0.7143 | 13.8405 | 0.7143 | 6.2330 | 13.6131 | 0.7143 | 13.2727 | 0.7143 | AAPL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.7640 | 11.4583 | 12.9875 | 0.6667 | 9.7640 | 0.6667 | 8.5447 | 9.5447 | 0.6667 | 9.2166 | 0.6667 | AAPL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 19.0946 | 19.5615 | 21.4313 | 0.8333 | 19.0946 | 0.8333 | 5.7961 | 18.8566 | 0.8333 | 18.5006 | 0.8333 | AAPL | stock |
| baseline | development | 26 | 21 | sufficient_sample | 17.6462 | 20.0758 | 20.1520 | 0.7619 | 17.6462 | 0.7619 | 6.4156 | 17.4111 | 0.7619 | 17.0594 | 0.7619 | AMZN | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 4.9835 | 6.5715 | 17.3020 | 0.6667 | 4.9835 | 0.6667 | 6.1453 | 4.7737 | 0.6667 | 4.4599 | 0.6667 | AMZN | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 21.5329 | 25.5401 | 25.3069 | 0.6364 | 21.5329 | 0.6364 | 6.3795 | 21.2901 | 0.6364 | 20.9267 | 0.6364 | AMZN | stock |
| candidate | development | 26 | 22 | sufficient_sample | 15.5735 | 10.7194 | 20.1141 | 0.7273 | 15.5735 | 0.7273 | 6.5675 | 15.3426 | 0.7273 | 14.9971 | 0.7273 | AMZN | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 1.2372 | 3.1624 | 21.4885 | 0.6429 | 1.2372 | 0.6429 | 5.1679 | 1.0349 | 0.6429 | 0.7322 | 0.5714 | AMZN | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 22.9076 | 21.6421 | 24.6055 | 0.7692 | 22.9076 | 0.7692 | 10.3718 | 22.6621 | 0.7692 | 22.2946 | 0.7692 | AMZN | stock |
| baseline | development | 26 | 21 | sufficient_sample | 7.7955 | 5.5544 | 15.3247 | 0.6190 | 7.7955 | 0.6190 | 4.9492 | 7.5801 | 0.6190 | 7.2579 | 0.6190 | BA | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | 1.5717 | 7.0725 | 16.7932 | 0.6000 | 1.5717 | 0.6000 | 8.7984 | 1.3687 | 0.6000 | 1.0651 | 0.6000 | BA | stock |
| baseline | validation | 26 | 10 | insufficient_sample | 13.0664 | 7.5122 | 23.4670 | 0.7000 | 13.0664 | 0.7000 | 5.3897 | 12.8405 | 0.7000 | 12.5025 | 0.7000 | BA | stock |
| candidate | development | 26 | 21 | sufficient_sample | 10.6880 | 7.5433 | 14.8754 | 0.7143 | 10.6880 | 0.7143 | 6.6805 | 10.4668 | 0.7143 | 10.1359 | 0.7143 | BA | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | 1.6241 | 0.8963 | 19.3449 | 0.5000 | 1.6241 | 0.5000 | 7.8991 | 1.4211 | 0.5000 | 1.1173 | 0.5000 | BA | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 3.4499 | 4.6112 | 29.9404 | 0.6667 | 3.4499 | 0.6667 | 5.2667 | 3.2432 | 0.6667 | 2.9339 | 0.6667 | BA | stock |
| baseline | development | 26 | 16 | insufficient_sample | 2.5692 | 2.0291 | 19.8917 | 0.5000 | 2.5692 | 0.5000 | 5.8124 | 2.3643 | 0.5000 | 2.0576 | 0.5000 | BAC | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 3.7223 | 10.2859 | 19.8666 | 0.6429 | 3.7223 | 0.6429 | 4.9046 | 3.5151 | 0.6429 | 3.2050 | 0.6429 | BAC | stock |
| baseline | validation | 26 | 10 | insufficient_sample | -0.1616 | 7.7648 | 19.8276 | 0.6000 | -0.1616 | 0.6000 | 2.6774 | -0.3611 | 0.6000 | -0.6596 | 0.6000 | BAC | stock |
| candidate | development | 26 | 17 | insufficient_sample | 0.2990 | -4.6494 | 20.4781 | 0.4706 | 0.2990 | 0.4706 | 4.8273 | 0.0986 | 0.4706 | -0.2012 | 0.4706 | BAC | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 9.1941 | 15.8699 | 19.3017 | 0.7143 | 9.1941 | 0.7143 | 8.0996 | 8.9760 | 0.7143 | 8.6495 | 0.7143 | BAC | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -0.2832 | 3.3062 | 18.1021 | 0.5000 | -0.2832 | 0.5000 | 4.4120 | -0.4824 | 0.5000 | -0.7805 | 0.5000 | BAC | stock |
| baseline | development | 26 | 17 | insufficient_sample | 3.4568 | -3.4589 | 18.5794 | 0.4706 | 3.4568 | 0.4706 | 5.8580 | 3.2501 | 0.4706 | 2.9408 | 0.4706 | CAT | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 4.1188 | 6.4175 | 12.8647 | 0.6923 | 4.1188 | 0.6923 | 6.7185 | 3.9108 | 0.6923 | 3.5995 | 0.6923 | CAT | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 9.3231 | 9.8249 | 19.9552 | 0.5833 | 9.3231 | 0.5833 | 4.7394 | 9.1046 | 0.5833 | 8.7778 | 0.5833 | CAT | stock |
| candidate | development | 26 | 20 | sufficient_sample | 5.4997 | 6.9278 | 19.0023 | 0.6000 | 5.4997 | 0.6000 | 6.3878 | 5.2890 | 0.6000 | 4.9736 | 0.6000 | CAT | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 7.5595 | 7.8259 | 11.4418 | 0.7143 | 7.5595 | 0.7143 | 7.9355 | 7.3446 | 0.7143 | 7.0231 | 0.7143 | CAT | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 8.2956 | 5.7569 | 22.6021 | 0.5000 | 8.2956 | 0.5000 | 4.4120 | 8.0792 | 0.5000 | 7.7555 | 0.5000 | CAT | stock |
| baseline | development | 26 | 22 | sufficient_sample | 9.8234 | 9.9180 | 8.8925 | 0.8636 | 9.8234 | 0.8636 | 6.5239 | 9.6039 | 0.8636 | 9.2756 | 0.8636 | COST | stock |
| baseline | holdout | 26 | 16 | insufficient_sample | 10.0140 | 11.6045 | 15.2785 | 0.6875 | 10.0140 | 0.6875 | 7.1078 | 9.7942 | 0.6875 | 9.4653 | 0.6875 | COST | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 10.1277 | 11.0016 | 11.2304 | 0.7500 | 10.1277 | 0.7500 | 4.2947 | 9.9077 | 0.7500 | 9.5784 | 0.7500 | COST | stock |
| candidate | development | 26 | 23 | sufficient_sample | 10.2058 | 8.7577 | 9.9232 | 0.8261 | 10.2058 | 0.8261 | 6.1575 | 9.9856 | 0.8261 | 9.6562 | 0.8261 | COST | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 11.2512 | 11.4050 | 15.8264 | 0.6875 | 11.2512 | 0.6875 | 7.6079 | 11.0289 | 0.6875 | 10.6963 | 0.6875 | COST | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 13.5465 | 16.1890 | 12.1108 | 0.7692 | 13.5465 | 0.7692 | 8.4682 | 13.3197 | 0.7692 | 12.9802 | 0.7692 | COST | stock |
| baseline | development | 26 | 18 | insufficient_sample | 2.4399 | 3.3501 | 14.9326 | 0.6111 | 2.4399 | 0.6111 | 6.4740 | 2.2352 | 0.6111 | 1.9290 | 0.6111 | CSCO | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 4.8969 | 6.3556 | 13.7927 | 0.5385 | 4.8969 | 0.5385 | 7.7069 | 4.6873 | 0.5385 | 4.3737 | 0.5385 | CSCO | stock |
| baseline | validation | 26 | 10 | insufficient_sample | 9.4948 | 7.3429 | 12.3228 | 0.7000 | 9.4948 | 0.7000 | 7.2873 | 9.2761 | 0.7000 | 8.9487 | 0.7000 | CSCO | stock |
| candidate | development | 26 | 21 | sufficient_sample | 3.1057 | 1.8443 | 15.2141 | 0.5714 | 3.1057 | 0.5714 | 6.2881 | 2.8997 | 0.5714 | 2.5915 | 0.5714 | CSCO | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 5.0586 | 6.2851 | 13.2583 | 0.5714 | 5.0586 | 0.5714 | 7.4842 | 4.8487 | 0.5714 | 4.5346 | 0.5714 | CSCO | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 7.4810 | 5.6538 | 14.1384 | 0.5833 | 7.4810 | 0.5833 | 7.6779 | 7.2662 | 0.5833 | 6.9449 | 0.5833 | CSCO | stock |
| baseline | development | 26 | 18 | insufficient_sample | 5.6021 | 4.8298 | 10.3670 | 0.8333 | 5.6021 | 0.8333 | 6.1320 | 5.3911 | 0.8333 | 5.0754 | 0.8333 | CVX | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 10.1429 | 1.7833 | 20.1926 | 0.5385 | 10.1429 | 0.5385 | 6.4379 | 9.9228 | 0.5385 | 9.5935 | 0.5385 | CVX | stock |
| baseline | validation | 26 | 11 | insufficient_sample | -4.0290 | 0.5781 | 16.3868 | 0.5455 | -4.0290 | 0.5455 | 4.5158 | -4.2207 | 0.5455 | -4.5076 | 0.5455 | CVX | stock |
| candidate | development | 26 | 22 | sufficient_sample | 5.8541 | 5.1521 | 11.3760 | 0.7273 | 5.8541 | 0.7273 | 7.4271 | 5.6426 | 0.7273 | 5.3261 | 0.7273 | CVX | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 9.6997 | 7.6905 | 19.1030 | 0.5625 | 9.6997 | 0.5625 | 7.4326 | 9.4806 | 0.5625 | 9.1526 | 0.5625 | CVX | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -2.9077 | -0.6347 | 9.8819 | 0.5000 | -2.9077 | 0.5000 | 6.6696 | -3.1017 | 0.5000 | -3.3919 | 0.4167 | CVX | stock |
| baseline | development | 26 | 22 | sufficient_sample | 5.6100 | 6.1618 | 6.1189 | 0.8182 | 5.6100 | 0.8182 | 5.6991 | 5.3990 | 0.8182 | 5.0833 | 0.8182 | DIA | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.9020 | 5.8829 | 8.5488 | 0.7333 | 4.9020 | 0.7333 | 5.8471 | 4.6924 | 0.7333 | 4.3788 | 0.7333 | DIA | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 5.1087 | 7.2532 | 7.1335 | 0.7500 | 5.1087 | 0.7500 | 5.4022 | 4.8987 | 0.7500 | 4.5845 | 0.6667 | DIA | etf |
| candidate | development | 26 | 23 | sufficient_sample | 6.4728 | 7.4945 | 7.7037 | 0.8261 | 6.4728 | 0.8261 | 7.0065 | 6.2600 | 0.8261 | 5.9417 | 0.7826 | DIA | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 5.7857 | 5.8829 | 7.0229 | 0.7333 | 5.7857 | 0.7333 | 7.2899 | 5.5744 | 0.7333 | 5.2581 | 0.7333 | DIA | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 4.3491 | 5.0400 | 10.1028 | 0.6667 | 4.3491 | 0.6667 | 5.6313 | 4.1406 | 0.6667 | 3.8287 | 0.5833 | DIA | etf |
| baseline | development | 26 | 21 | sufficient_sample | 9.9834 | 10.8179 | 14.2536 | 0.7143 | 9.9834 | 0.7143 | 4.9226 | 9.7636 | 0.7143 | 9.4348 | 0.7143 | DIS | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | -4.4045 | -3.7294 | 10.5725 | 0.4000 | -4.4045 | 0.4000 | 9.9539 | -4.5955 | 0.4000 | -4.8812 | 0.4000 | DIS | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 0.7595 | -1.4948 | 11.7269 | 0.4545 | 0.7595 | 0.4545 | 5.0746 | 0.5582 | 0.4545 | 0.2570 | 0.4545 | DIS | stock |
| candidate | development | 26 | 22 | sufficient_sample | 9.0948 | 10.7724 | 14.4824 | 0.7727 | 9.0948 | 0.7727 | 4.8055 | 8.8769 | 0.7727 | 8.5507 | 0.7727 | DIS | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -5.3281 | -6.6518 | 15.2021 | 0.4167 | -5.3281 | 0.4167 | 7.5871 | -5.5173 | 0.4167 | -5.8003 | 0.4167 | DIS | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.9892 | 1.2235 | 15.3942 | 0.5000 | 2.9892 | 0.5000 | 6.6048 | 2.7834 | 0.5000 | 2.4755 | 0.5000 | DIS | stock |
| baseline | development | 26 | 20 | sufficient_sample | 9.6013 | 10.1199 | 14.4309 | 0.7500 | 9.6013 | 0.7500 | 6.0437 | 9.3823 | 0.7500 | 9.0547 | 0.7000 | GOOGL | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 14.4476 | 10.1144 | 29.4658 | 0.6429 | 14.4476 | 0.6429 | 5.9742 | 14.2189 | 0.6429 | 13.8768 | 0.6429 | GOOGL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 9.2562 | 6.9331 | 11.5144 | 0.8333 | 9.2562 | 0.8333 | 5.6966 | 9.0380 | 0.8333 | 8.7113 | 0.8333 | GOOGL | stock |
| candidate | development | 26 | 22 | sufficient_sample | 8.3795 | 7.5467 | 15.3224 | 0.6818 | 8.3795 | 0.6818 | 4.8800 | 8.1629 | 0.6818 | 7.8389 | 0.6818 | GOOGL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 14.9041 | 10.3653 | 26.3213 | 0.6667 | 14.9041 | 0.6667 | 7.5181 | 14.6745 | 0.6667 | 14.3310 | 0.6667 | GOOGL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 11.5169 | 11.1212 | 11.0855 | 0.8333 | 11.5169 | 0.8333 | 7.9673 | 11.2941 | 0.8333 | 10.9607 | 0.8333 | GOOGL | stock |
| baseline | development | 26 | 15 | insufficient_sample | 4.4819 | 2.0514 | 18.8121 | 0.6667 | 4.4819 | 0.6667 | 5.4140 | 4.2731 | 0.6667 | 3.9608 | 0.6000 | GS | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 12.3578 | 15.8993 | 19.6757 | 0.6429 | 12.3578 | 0.6429 | 6.1309 | 12.1333 | 0.6429 | 11.7974 | 0.6429 | GS | stock |
| baseline | validation | 26 | 10 | insufficient_sample | -0.0999 | 0.6411 | 9.7952 | 0.5000 | -0.0999 | 0.5000 | 7.0730 | -0.2995 | 0.5000 | -0.5982 | 0.5000 | GS | stock |
| candidate | development | 26 | 19 | insufficient_sample | 0.1113 | 3.3299 | 16.7432 | 0.5789 | 0.1113 | 0.5789 | 4.7458 | -0.0887 | 0.5789 | -0.3880 | 0.5789 | GS | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 14.3870 | 19.8363 | 21.1684 | 0.7333 | 14.3870 | 0.7333 | 9.5888 | 14.1584 | 0.7333 | 13.8165 | 0.7333 | GS | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -1.7842 | -2.2962 | 10.0703 | 0.4167 | -1.7842 | 0.4167 | 6.0239 | -1.9804 | 0.4167 | -2.2741 | 0.4167 | GS | stock |
| baseline | development | 26 | 22 | sufficient_sample | 13.9268 | 10.2712 | 13.2174 | 0.8636 | 13.9268 | 0.8636 | 6.4294 | 13.6991 | 0.8636 | 13.3585 | 0.8636 | HD | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 2.5906 | 5.4926 | 12.4633 | 0.6667 | 2.5906 | 0.6667 | 6.5002 | 2.3857 | 0.6667 | 2.0790 | 0.5833 | HD | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 8.6176 | 14.6402 | 17.4956 | 0.7500 | 8.6176 | 0.7500 | 4.0725 | 8.4006 | 0.7500 | 8.0759 | 0.7500 | HD | stock |
| candidate | development | 26 | 23 | sufficient_sample | 13.4006 | 11.1946 | 13.3101 | 0.7826 | 13.4006 | 0.7826 | 5.5977 | 13.1740 | 0.7826 | 12.8350 | 0.7826 | HD | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 6.0108 | 7.0318 | 13.1407 | 0.6429 | 6.0108 | 0.6429 | 6.6812 | 5.7990 | 0.6429 | 5.4821 | 0.6429 | HD | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 13.1681 | 15.5926 | 15.0052 | 0.8333 | 13.1681 | 0.8333 | 6.7610 | 12.9420 | 0.8333 | 12.6037 | 0.8333 | HD | stock |
| baseline | development | 26 | 23 | sufficient_sample | 7.3643 | 4.9645 | 11.2629 | 0.7826 | 7.3643 | 0.7826 | 5.0177 | 7.1498 | 0.7826 | 6.8288 | 0.7826 | HON | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | -0.4219 | -0.7025 | 8.5643 | 0.5000 | -0.4219 | 0.5000 | 7.2492 | -0.6208 | 0.5000 | -0.9185 | 0.5000 | HON | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 7.2540 | 6.2337 | 12.5253 | 0.8333 | 7.2540 | 0.8333 | 5.4022 | 7.0397 | 0.8333 | 6.7191 | 0.8333 | HON | stock |
| candidate | development | 26 | 23 | sufficient_sample | 8.4059 | 4.1941 | 11.9853 | 0.7826 | 8.4059 | 0.7826 | 5.2470 | 8.1894 | 0.7826 | 7.8653 | 0.7826 | HON | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | -0.3296 | 1.9599 | 8.7638 | 0.5714 | -0.3296 | 0.5714 | 6.1974 | -0.5287 | 0.5714 | -0.8267 | 0.5714 | HON | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 8.4537 | 7.7269 | 10.2304 | 0.8333 | 8.4537 | 0.8333 | 7.9673 | 8.2370 | 0.8333 | 7.9128 | 0.8333 | HON | stock |
| baseline | development | 26 | 18 | insufficient_sample | 3.3887 | 3.3665 | 11.9944 | 0.6111 | 3.3887 | 0.6111 | 6.8132 | 3.1821 | 0.6111 | 2.8731 | 0.6111 | IBM | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 11.6905 | 10.6578 | 14.7432 | 0.7333 | 11.6905 | 0.7333 | 5.8923 | 11.4673 | 0.6667 | 11.1334 | 0.6667 | IBM | stock |
| baseline | validation | 26 | 9 | insufficient_sample | -5.4126 | -5.4386 | 6.8429 | 0.2222 | -5.4126 | 0.2222 | 4.5537 | -5.6016 | 0.2222 | -5.8843 | 0.2222 | IBM | stock |
| candidate | development | 26 | 20 | sufficient_sample | 3.0670 | 5.6640 | 13.5368 | 0.6500 | 3.0670 | 0.6500 | 5.4520 | 2.8611 | 0.6500 | 2.5530 | 0.6500 | IBM | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 11.4364 | 10.2988 | 12.6406 | 0.7500 | 11.4364 | 0.7500 | 6.6730 | 11.2137 | 0.6875 | 10.8806 | 0.6875 | IBM | stock |
| candidate | validation | 26 | 10 | insufficient_sample | -2.6377 | -3.3404 | 7.1252 | 0.3000 | -2.6377 | 0.3000 | 6.0655 | -2.8322 | 0.3000 | -3.1233 | 0.3000 | IBM | stock |
| baseline | development | 26 | 20 | sufficient_sample | 4.7921 | 5.2824 | 12.1593 | 0.6000 | 4.7921 | 0.6000 | 5.1203 | 4.5827 | 0.6000 | 4.2694 | 0.6000 | IWM | etf |
| baseline | holdout | 26 | 12 | insufficient_sample | -0.3138 | 1.0966 | 9.2210 | 0.5833 | -0.3138 | 0.5833 | 7.4352 | -0.5129 | 0.5833 | -0.8109 | 0.5833 | IWM | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 0.1352 | 5.2391 | 15.1631 | 0.5833 | 0.1352 | 0.5833 | 3.8094 | -0.0649 | 0.5833 | -0.3642 | 0.5833 | IWM | etf |
| candidate | development | 26 | 22 | sufficient_sample | 4.2174 | 4.8727 | 11.5473 | 0.6818 | 4.2174 | 0.6818 | 5.0240 | 4.0091 | 0.6818 | 3.6976 | 0.6364 | IWM | etf |
| candidate | holdout | 26 | 14 | insufficient_sample | 4.0017 | 3.7954 | 10.2815 | 0.7143 | 4.0017 | 0.7143 | 8.1839 | 3.7939 | 0.6429 | 3.4830 | 0.6429 | IWM | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 0.4999 | 5.2391 | 17.1002 | 0.6667 | 0.4999 | 0.6667 | 4.2910 | 0.2991 | 0.6667 | -0.0014 | 0.5833 | IWM | etf |
| baseline | development | 26 | 20 | sufficient_sample | 7.9876 | 7.1447 | 9.2079 | 0.7500 | 7.9876 | 0.7500 | 7.1296 | 7.7718 | 0.7500 | 7.4490 | 0.7000 | JNJ | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 1.7472 | -1.8774 | 10.3070 | 0.3333 | 1.7472 | 0.3333 | 4.7208 | 1.5439 | 0.3333 | 1.2397 | 0.3333 | JNJ | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 2.3101 | 1.0216 | 8.0105 | 0.5455 | 2.3101 | 0.5455 | 6.2356 | 2.1057 | 0.5455 | 1.7998 | 0.5455 | JNJ | stock |
| candidate | development | 26 | 22 | sufficient_sample | 7.2436 | 7.1447 | 8.3858 | 0.7273 | 7.2436 | 0.7273 | 5.6402 | 7.0293 | 0.6818 | 6.7087 | 0.6818 | JNJ | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 3.6919 | -0.2404 | 10.1175 | 0.4000 | 3.6919 | 0.4000 | 6.8791 | 3.4847 | 0.4000 | 3.1747 | 0.4000 | JNJ | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.8063 | 2.0947 | 7.8440 | 0.5833 | 2.8063 | 0.5833 | 6.4106 | 2.6009 | 0.5833 | 2.2936 | 0.5833 | JNJ | stock |
| baseline | development | 26 | 19 | insufficient_sample | 4.4095 | 4.6603 | 13.9238 | 0.6842 | 4.4095 | 0.6842 | 4.3268 | 4.2009 | 0.6842 | 3.8887 | 0.6316 | JPM | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 13.0374 | 14.1012 | 12.1472 | 0.8571 | 13.0374 | 0.8571 | 8.2847 | 12.8115 | 0.8571 | 12.4736 | 0.8571 | JPM | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 1.7839 | 8.8188 | 16.2306 | 0.6364 | 1.7839 | 0.6364 | 3.9508 | 1.5805 | 0.6364 | 1.2762 | 0.6364 | JPM | stock |
| candidate | development | 26 | 22 | sufficient_sample | 5.7608 | 8.7762 | 14.2060 | 0.6364 | 5.7608 | 0.6364 | 6.0058 | 5.5495 | 0.6364 | 5.2333 | 0.6364 | JPM | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.9513 | 13.8000 | 17.5018 | 0.7333 | 7.9513 | 0.7333 | 5.6466 | 7.7356 | 0.7333 | 7.4129 | 0.7333 | JPM | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 7.3867 | 11.1898 | 12.2342 | 0.7500 | 7.3867 | 0.7500 | 7.9673 | 7.1721 | 0.7500 | 6.8511 | 0.6667 | JPM | stock |
| baseline | development | 26 | 22 | sufficient_sample | 4.7255 | 4.8817 | 7.0878 | 0.7273 | 4.7255 | 0.7273 | 5.7501 | 4.5162 | 0.6818 | 4.2031 | 0.6818 | KO | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 6.5027 | 6.4148 | 8.1872 | 0.7857 | 6.5027 | 0.7857 | 7.0370 | 6.2899 | 0.7143 | 5.9715 | 0.7143 | KO | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 4.7438 | 2.3313 | 7.4537 | 0.6364 | 4.7438 | 0.6364 | 6.3438 | 4.5345 | 0.6364 | 4.2214 | 0.6364 | KO | stock |
| candidate | development | 26 | 22 | sufficient_sample | 5.3936 | 7.0648 | 6.7462 | 0.6818 | 5.3936 | 0.6818 | 5.7976 | 5.1831 | 0.6364 | 4.8680 | 0.6364 | KO | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.2486 | 7.3684 | 7.2858 | 0.8000 | 7.2486 | 0.8000 | 8.0138 | 7.0343 | 0.8000 | 6.7137 | 0.8000 | KO | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 4.6529 | 7.5401 | 7.8059 | 0.6667 | 4.6529 | 0.6667 | 7.4404 | 4.4438 | 0.6667 | 4.1309 | 0.6667 | KO | stock |
| baseline | development | 26 | 22 | sufficient_sample | 6.8180 | 6.0302 | 11.1318 | 0.6364 | 6.8180 | 0.6364 | 6.0893 | 6.6046 | 0.6364 | 6.2852 | 0.6364 | MCD | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.2695 | 5.7415 | 5.8090 | 0.8667 | 4.2695 | 0.8667 | 6.3115 | 4.0612 | 0.8667 | 3.7495 | 0.8667 | MCD | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 9.2583 | 7.4292 | 10.4714 | 0.8182 | 9.2583 | 0.8182 | 7.3806 | 9.0400 | 0.8182 | 8.7134 | 0.7273 | MCD | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.8417 | 6.7679 | 8.7617 | 0.7391 | 6.8417 | 0.7391 | 6.0837 | 6.6282 | 0.7391 | 6.3088 | 0.7391 | MCD | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 5.8755 | 7.1154 | 5.9078 | 0.8750 | 5.8755 | 0.8750 | 7.1838 | 5.6640 | 0.8750 | 5.3474 | 0.8750 | MCD | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 12.4025 | 12.3651 | 10.8444 | 0.9091 | 12.4025 | 0.9091 | 7.2969 | 12.1780 | 0.9091 | 11.8419 | 0.8182 | MCD | stock |
| baseline | development | 26 | 21 | sufficient_sample | 7.3462 | 8.7383 | 11.6239 | 0.7143 | 7.3462 | 0.7143 | 6.1375 | 7.1317 | 0.7143 | 6.8108 | 0.7143 | MMM | stock |
| baseline | holdout | 26 | 11 | insufficient_sample | 7.4751 | -2.1218 | 22.3153 | 0.4545 | 7.4751 | 0.4545 | 9.0990 | 7.2604 | 0.4545 | 6.9391 | 0.4545 | MMM | stock |
| baseline | validation | 26 | 9 | insufficient_sample | 0.9655 | -2.2029 | 13.7426 | 0.4444 | 0.9655 | 0.4444 | 6.1635 | 0.7637 | 0.4444 | 0.4619 | 0.4444 | MMM | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.8733 | 8.7383 | 10.8109 | 0.7391 | 6.8733 | 0.7391 | 5.9981 | 6.6598 | 0.7391 | 6.3403 | 0.7391 | MMM | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | 6.5499 | 6.3979 | 23.1046 | 0.6667 | 6.5499 | 0.6667 | 5.3599 | 6.3370 | 0.6667 | 6.0185 | 0.6667 | MMM | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 1.4366 | 2.8157 | 14.5029 | 0.5455 | 1.4366 | 0.5455 | 5.8072 | 1.2339 | 0.5455 | 0.9307 | 0.5455 | MMM | stock |
| baseline | development | 26 | 21 | sufficient_sample | 5.1738 | 4.2643 | 10.2098 | 0.6667 | 5.1738 | 0.6667 | 5.9970 | 4.9637 | 0.6667 | 4.6493 | 0.6667 | MRK | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 4.6820 | 5.1131 | 13.3793 | 0.6667 | 4.6820 | 0.6667 | 4.3672 | 4.4729 | 0.6667 | 4.1599 | 0.6667 | MRK | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 4.9797 | 5.8904 | 11.0503 | 0.6364 | 4.9797 | 0.6364 | 4.9801 | 4.7699 | 0.6364 | 4.4561 | 0.6364 | MRK | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.4958 | 7.3077 | 10.1884 | 0.6957 | 6.4958 | 0.6957 | 6.2051 | 6.2830 | 0.6522 | 5.9646 | 0.6522 | MRK | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 8.2634 | 9.1367 | 16.3070 | 0.5714 | 8.2634 | 0.5714 | 7.9881 | 8.0471 | 0.5714 | 7.7235 | 0.5714 | MRK | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 4.8777 | 4.8235 | 10.5852 | 0.6667 | 4.8777 | 0.6667 | 6.4683 | 4.6682 | 0.6667 | 4.3547 | 0.6667 | MRK | stock |
| baseline | development | 26 | 20 | sufficient_sample | 3.4357 | 3.7819 | 12.5876 | 0.5500 | 3.4357 | 0.5500 | 3.6113 | 3.2290 | 0.5500 | 2.9198 | 0.5500 | MSFT | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 7.4800 | 8.6903 | 17.3181 | 0.6429 | 7.4800 | 0.6429 | 5.4152 | 7.2652 | 0.6429 | 6.9439 | 0.6429 | MSFT | stock |
| baseline | validation | 26 | 13 | insufficient_sample | 20.8046 | 20.4495 | 11.1459 | 0.9231 | 20.8046 | 0.9231 | 10.2597 | 20.5632 | 0.9231 | 20.2021 | 0.9231 | MSFT | stock |
| candidate | development | 26 | 22 | sufficient_sample | 7.1745 | 9.6595 | 13.4405 | 0.6364 | 7.1745 | 0.6364 | 5.2828 | 6.9603 | 0.6364 | 6.6399 | 0.6364 | MSFT | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.0828 | 7.7239 | 15.7602 | 0.6667 | 9.0828 | 0.6667 | 6.7064 | 8.8648 | 0.6667 | 8.5387 | 0.6667 | MSFT | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 20.3079 | 20.4495 | 10.9326 | 0.9231 | 20.3079 | 0.9231 | 8.4682 | 20.0675 | 0.9231 | 19.7078 | 0.9231 | MSFT | stock |
| baseline | development | 26 | 21 | sufficient_sample | 9.2375 | 8.1412 | 13.2611 | 0.7619 | 9.2375 | 0.7619 | 4.8436 | 9.0193 | 0.6667 | 8.6927 | 0.6667 | NKE | stock |
| baseline | holdout | 26 | 8 | insufficient_sample | -7.7812 | -10.2408 | 18.5249 | 0.2500 | -7.7812 | 0.2500 | 7.5182 | -7.9654 | 0.2500 | -8.2411 | 0.2500 | NKE | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 15.4078 | 15.3117 | 12.2364 | 0.9091 | 15.4078 | 0.9091 | 8.3534 | 15.1772 | 0.9091 | 14.8322 | 0.9091 | NKE | stock |
| candidate | development | 26 | 22 | sufficient_sample | 10.5200 | 12.1765 | 13.6746 | 0.7727 | 10.5200 | 0.7727 | 5.6894 | 10.2992 | 0.6818 | 9.9688 | 0.6818 | NKE | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -6.3558 | -6.8542 | 19.0612 | 0.2500 | -6.3558 | 0.2500 | 6.6721 | -6.5429 | 0.2500 | -6.8228 | 0.2500 | NKE | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 13.5004 | 8.9520 | 14.1574 | 0.9167 | 13.5004 | 0.9167 | 7.7198 | 13.2736 | 0.9167 | 12.9343 | 0.9167 | NKE | stock |
| baseline | development | 26 | 20 | sufficient_sample | 17.6414 | 13.7238 | 42.5526 | 0.6500 | 17.6414 | 0.6500 | 4.5560 | 17.4064 | 0.6500 | 17.0547 | 0.6500 | NVDA | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 39.6247 | 35.2756 | 57.1121 | 0.7857 | 39.6247 | 0.7857 | 5.8657 | 39.3457 | 0.7857 | 38.9283 | 0.7857 | NVDA | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 32.5901 | 38.0401 | 42.1436 | 0.8182 | 32.5901 | 0.8182 | 5.3033 | 32.3252 | 0.8182 | 31.9288 | 0.8182 | NVDA | stock |
| candidate | development | 26 | 21 | sufficient_sample | 15.0544 | 10.6993 | 40.6395 | 0.6190 | 15.0544 | 0.6190 | 5.2123 | 14.8245 | 0.6190 | 14.4805 | 0.6190 | NVDA | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 42.9319 | 36.8909 | 59.3230 | 0.7857 | 42.9319 | 0.7857 | 7.3725 | 42.6463 | 0.7857 | 42.2190 | 0.7857 | NVDA | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 31.3856 | 34.0532 | 47.7003 | 0.7273 | 31.3856 | 0.7273 | 4.8283 | 31.1230 | 0.7273 | 30.7303 | 0.7273 | NVDA | stock |
| baseline | development | 26 | 21 | sufficient_sample | 2.3926 | 0.8038 | 14.3001 | 0.5714 | 2.3926 | 0.5714 | 5.5640 | 2.1880 | 0.5714 | 1.8819 | 0.5714 | ORCL | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 19.3863 | 27.0692 | 22.6144 | 0.6923 | 19.3863 | 0.6923 | 8.5370 | 19.1477 | 0.6923 | 18.7908 | 0.6923 | ORCL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 4.8484 | 3.3829 | 9.5656 | 0.7500 | 4.8484 | 0.7500 | 5.8482 | 4.6389 | 0.7500 | 4.3255 | 0.7500 | ORCL | stock |
| candidate | development | 26 | 22 | sufficient_sample | 4.2117 | 4.3159 | 13.3791 | 0.6364 | 4.2117 | 0.6364 | 6.3493 | 4.0035 | 0.6364 | 3.6920 | 0.6364 | ORCL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 20.0410 | 28.8900 | 30.6287 | 0.6667 | 20.0410 | 0.6667 | 7.2839 | 19.8012 | 0.6667 | 19.4423 | 0.6667 | ORCL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 6.0377 | 5.5720 | 11.0392 | 0.7500 | 6.0377 | 0.7500 | 5.5800 | 5.8258 | 0.7500 | 5.5088 | 0.7500 | ORCL | stock |
| baseline | development | 26 | 20 | sufficient_sample | 6.2789 | 7.9938 | 11.2977 | 0.6500 | 6.2789 | 0.6500 | 5.1933 | 6.0666 | 0.6500 | 5.7489 | 0.6500 | PFE | stock |
| baseline | holdout | 26 | 9 | insufficient_sample | 1.7643 | 1.1658 | 10.9775 | 0.6667 | 1.7643 | 0.6667 | 3.8517 | 1.5610 | 0.6667 | 1.2567 | 0.6667 | PFE | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 3.1861 | 2.7758 | 10.0959 | 0.7273 | 3.1861 | 0.7273 | 6.6909 | 2.9799 | 0.7273 | 2.6714 | 0.7273 | PFE | stock |
| candidate | development | 26 | 22 | sufficient_sample | 7.2403 | 10.9042 | 11.1800 | 0.7273 | 7.2403 | 0.7273 | 5.4540 | 7.0260 | 0.7273 | 6.7054 | 0.7273 | PFE | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -1.4944 | 0.9502 | 12.9194 | 0.5833 | -1.4944 | 0.5833 | 6.5119 | -1.6912 | 0.5833 | -1.9857 | 0.5833 | PFE | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.1868 | 2.5350 | 10.4492 | 0.6667 | 2.1868 | 0.6667 | 4.5508 | 1.9826 | 0.6667 | 1.6771 | 0.6667 | PFE | stock |
| baseline | development | 26 | 20 | sufficient_sample | 4.3445 | 5.6265 | 8.2807 | 0.8500 | 4.3445 | 0.8500 | 6.5071 | 4.1360 | 0.8500 | 3.8240 | 0.8500 | PG | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 2.7976 | 3.3218 | 6.4465 | 0.7143 | 2.7976 | 0.7143 | 7.4047 | 2.5923 | 0.7143 | 2.2849 | 0.7143 | PG | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 6.6600 | 5.2374 | 13.4061 | 0.6364 | 6.6600 | 0.6364 | 5.2395 | 6.4469 | 0.6364 | 6.1280 | 0.6364 | PG | stock |
| candidate | development | 26 | 22 | sufficient_sample | 4.5010 | 5.4054 | 7.1834 | 0.8636 | 4.5010 | 0.8636 | 5.9780 | 4.2922 | 0.8636 | 3.9798 | 0.8636 | PG | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.3850 | 2.5311 | 6.4164 | 0.6667 | 2.3850 | 0.6667 | 6.6920 | 2.1805 | 0.6667 | 1.8744 | 0.6667 | PG | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 6.3248 | 5.2374 | 12.7520 | 0.6364 | 6.3248 | 0.6364 | 4.5947 | 6.1123 | 0.6364 | 5.7945 | 0.6364 | PG | stock |
| baseline | development | 26 | 22 | sufficient_sample | 6.2399 | 7.7029 | 8.7057 | 0.7273 | 6.2399 | 0.7273 | 4.7246 | 6.0276 | 0.7273 | 5.7100 | 0.6818 | QQQ | etf |
| baseline | holdout | 26 | 13 | insufficient_sample | 9.6165 | 13.4461 | 13.4862 | 0.7692 | 9.6165 | 0.7692 | 7.9917 | 9.3974 | 0.7692 | 9.0697 | 0.7692 | QQQ | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 10.1246 | 10.3057 | 14.7398 | 0.7500 | 10.1246 | 0.7500 | 4.1216 | 9.9046 | 0.7500 | 9.5753 | 0.7500 | QQQ | etf |
| candidate | development | 26 | 23 | sufficient_sample | 9.2008 | 9.8943 | 9.3871 | 0.8696 | 9.2008 | 0.8696 | 7.0585 | 8.9827 | 0.8696 | 8.6562 | 0.8261 | QQQ | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 6.0076 | 12.4879 | 13.7292 | 0.7333 | 6.0076 | 0.7333 | 6.0929 | 5.7958 | 0.7333 | 5.4789 | 0.7333 | QQQ | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 13.1827 | 11.9849 | 14.1287 | 0.8333 | 13.1827 | 0.8333 | 8.4083 | 12.9565 | 0.8333 | 12.6182 | 0.8333 | QQQ | etf |
| baseline | development | 26 | 22 | sufficient_sample | 12.7394 | 8.0165 | 12.2252 | 0.8182 | 12.7394 | 0.8182 | 6.4547 | 12.5141 | 0.8182 | 12.1771 | 0.8182 | UNH | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 2.5229 | 6.1639 | 15.4497 | 0.7857 | 2.5229 | 0.7857 | 6.7831 | 2.3181 | 0.7857 | 2.0116 | 0.7143 | UNH | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 12.1752 | 16.2527 | 10.3758 | 0.7500 | 12.1752 | 0.7500 | 6.3921 | 11.9511 | 0.7500 | 11.6157 | 0.7500 | UNH | stock |
| candidate | development | 26 | 23 | sufficient_sample | 14.1648 | 14.8432 | 12.1634 | 0.8261 | 14.1648 | 0.8261 | 6.3873 | 13.9367 | 0.8261 | 13.5954 | 0.8261 | UNH | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 0.4567 | 5.8846 | 18.0001 | 0.6000 | 0.4567 | 0.6000 | 10.5507 | 0.2560 | 0.6000 | -0.0443 | 0.6000 | UNH | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 12.3424 | 15.4591 | 9.4354 | 0.8462 | 12.3424 | 0.8462 | 8.4682 | 12.1180 | 0.8462 | 11.7821 | 0.8462 | UNH | stock |
| baseline | development | 26 | 22 | sufficient_sample | 4.1374 | 3.5944 | 7.3079 | 0.7273 | 4.1374 | 0.7273 | 5.3953 | 3.9293 | 0.6818 | 3.6180 | 0.6818 | UPS | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | -0.9962 | -6.2328 | 17.0670 | 0.3000 | -0.9962 | 0.3000 | 3.3367 | -1.1940 | 0.3000 | -1.4899 | 0.3000 | UPS | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 2.0370 | -5.5214 | 21.0505 | 0.3636 | 2.0370 | 0.3636 | 5.9574 | 1.8332 | 0.3636 | 1.5281 | 0.3636 | UPS | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.5603 | 7.5871 | 9.0841 | 0.7826 | 6.5603 | 0.7826 | 6.5369 | 6.3474 | 0.7391 | 6.0289 | 0.7391 | UPS | stock |
| candidate | holdout | 26 | 11 | insufficient_sample | -0.2676 | -4.2451 | 15.5347 | 0.3636 | -0.2676 | 0.3636 | 4.8568 | -0.4669 | 0.3636 | -0.7650 | 0.3636 | UPS | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 9.0784 | 5.0728 | 24.3185 | 0.5455 | 9.0784 | 0.5455 | 7.4756 | 8.8605 | 0.5455 | 8.5344 | 0.5455 | UPS | stock |
| baseline | development | 26 | 19 | insufficient_sample | 5.9279 | 6.1318 | 9.2989 | 0.7895 | 5.9279 | 0.7895 | 7.5072 | 5.7162 | 0.7895 | 5.3995 | 0.7368 | WMT | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 9.2324 | 4.9979 | 13.8750 | 0.6667 | 9.2324 | 0.6667 | 5.9663 | 9.0142 | 0.6667 | 8.6876 | 0.6667 | WMT | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 11.4474 | 11.2222 | 9.5689 | 0.9091 | 11.4474 | 0.9091 | 6.3849 | 11.2247 | 0.9091 | 10.8916 | 0.9091 | WMT | stock |
| candidate | development | 26 | 21 | sufficient_sample | 5.6590 | 6.9342 | 11.3765 | 0.8095 | 5.6590 | 0.8095 | 6.5764 | 5.4479 | 0.8095 | 5.1321 | 0.7143 | WMT | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.2324 | 4.9979 | 13.8750 | 0.6667 | 9.2324 | 0.6667 | 5.9663 | 9.0142 | 0.6667 | 8.6876 | 0.6667 | WMT | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 10.1180 | 11.9782 | 8.4625 | 0.9167 | 10.1180 | 0.9167 | 3.7210 | 9.8980 | 0.9167 | 9.5688 | 0.9167 | WMT | stock |
| baseline | development | 26 | 21 | sufficient_sample | 3.5178 | 5.1466 | 10.7860 | 0.6667 | 3.5178 | 0.6667 | 6.1675 | 3.3110 | 0.6667 | 3.0015 | 0.6667 | XLB | etf |
| baseline | holdout | 26 | 12 | insufficient_sample | 0.0065 | 1.9455 | 9.8047 | 0.5833 | 0.0065 | 0.5833 | 4.3504 | -0.1933 | 0.5833 | -0.4923 | 0.5833 | XLB | etf |
| baseline | validation | 26 | 11 | insufficient_sample | 2.9198 | 2.2592 | 13.6167 | 0.7273 | 2.9198 | 0.7273 | 4.8702 | 2.7141 | 0.7273 | 2.4064 | 0.7273 | XLB | etf |
| candidate | development | 26 | 22 | sufficient_sample | 4.1103 | 5.1513 | 9.8945 | 0.6818 | 4.1103 | 0.6818 | 6.8315 | 3.9023 | 0.6818 | 3.5911 | 0.6818 | XLB | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 1.2480 | 2.5287 | 7.0686 | 0.6667 | 1.2480 | 0.6667 | 5.4823 | 1.0457 | 0.6667 | 0.7430 | 0.6667 | XLB | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 5.6928 | 5.4432 | 11.2130 | 0.8333 | 5.6928 | 0.8333 | 7.7548 | 5.4816 | 0.8333 | 5.1656 | 0.7500 | XLB | etf |
| baseline | development | 26 | 16 | insufficient_sample | 6.0480 | 7.6897 | 14.5969 | 0.5625 | 6.0480 | 0.5625 | 7.6129 | 5.8361 | 0.5625 | 5.5191 | 0.5625 | XLE | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 14.1693 | 8.2535 | 19.0441 | 0.8000 | 14.1693 | 0.8000 | 8.0701 | 13.9411 | 0.8000 | 13.5998 | 0.8000 | XLE | etf |
| baseline | validation | 26 | 7 | insufficient_sample | -11.5086 | -10.5823 | 11.2428 | 0.1429 | -11.5086 | 0.1429 | 2.0005 | -11.6854 | 0.1429 | -11.9499 | 0.1429 | XLE | etf |
| candidate | development | 26 | 21 | sufficient_sample | 4.2480 | 7.6244 | 13.5864 | 0.6190 | 4.2480 | 0.6190 | 6.8464 | 4.0398 | 0.6190 | 3.7281 | 0.6190 | XLE | etf |
| candidate | holdout | 26 | 16 | insufficient_sample | 12.5480 | 10.2610 | 20.1613 | 0.6250 | 12.5480 | 0.6250 | 7.4326 | 12.3231 | 0.6250 | 11.9867 | 0.6250 | XLE | etf |
| candidate | validation | 26 | 11 | insufficient_sample | -12.2574 | -9.4523 | 18.1347 | 0.3636 | -12.2574 | 0.3636 | 3.2247 | -12.4327 | 0.3636 | -12.6950 | 0.3636 | XLE | etf |
| baseline | development | 26 | 19 | insufficient_sample | 3.8142 | 4.6066 | 11.4640 | 0.6842 | 3.8142 | 0.6842 | 4.8450 | 3.6068 | 0.6842 | 3.2965 | 0.6842 | XLF | etf |
| baseline | holdout | 26 | 14 | insufficient_sample | 7.6201 | 11.2708 | 12.3635 | 0.7143 | 7.6201 | 0.7143 | 7.8457 | 7.4051 | 0.7143 | 7.0834 | 0.7143 | XLF | etf |
| baseline | validation | 26 | 11 | insufficient_sample | -0.9237 | 3.5897 | 13.9534 | 0.6364 | -0.9237 | 0.6364 | 3.1237 | -1.1217 | 0.6364 | -1.4179 | 0.6364 | XLF | etf |
| candidate | development | 26 | 22 | sufficient_sample | 3.5258 | 6.5898 | 12.2391 | 0.6818 | 3.5258 | 0.6818 | 4.9131 | 3.3190 | 0.6818 | 3.0095 | 0.6818 | XLF | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.4153 | 9.3797 | 12.9327 | 0.8000 | 7.4153 | 0.8000 | 6.3156 | 7.2007 | 0.8000 | 6.8796 | 0.8000 | XLF | etf |
| candidate | validation | 26 | 12 | insufficient_sample | -0.2437 | 4.0551 | 12.7008 | 0.6667 | -0.2437 | 0.6667 | 3.7276 | -0.4430 | 0.6667 | -0.7413 | 0.5833 | XLF | etf |
| baseline | development | 26 | 22 | sufficient_sample | 5.6401 | 5.0757 | 10.0005 | 0.7273 | 5.6401 | 0.7273 | 5.4211 | 5.4291 | 0.7273 | 5.1133 | 0.7273 | XLI | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 5.9771 | 8.0237 | 10.1772 | 0.7333 | 5.9771 | 0.7333 | 6.7674 | 5.7654 | 0.7333 | 5.4485 | 0.7333 | XLI | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 1.8141 | 6.5171 | 11.9954 | 0.6667 | 1.8141 | 0.6667 | 4.0479 | 1.6107 | 0.6667 | 1.3063 | 0.6667 | XLI | etf |
| candidate | development | 26 | 23 | sufficient_sample | 5.9718 | 6.7749 | 10.8350 | 0.6957 | 5.9718 | 0.6957 | 5.6774 | 5.7600 | 0.6957 | 5.4432 | 0.6957 | XLI | etf |
| candidate | holdout | 26 | 16 | insufficient_sample | 7.4954 | 9.3243 | 8.4139 | 0.8125 | 7.4954 | 0.8125 | 8.9199 | 7.2806 | 0.8125 | 6.9593 | 0.8125 | XLI | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 3.5943 | 7.0569 | 9.8952 | 0.6667 | 3.5943 | 0.6667 | 5.4022 | 3.3873 | 0.6667 | 3.0776 | 0.6667 | XLI | etf |
| baseline | development | 26 | 23 | sufficient_sample | 6.4744 | 8.6048 | 7.9415 | 0.7826 | 6.4744 | 0.7826 | 5.5218 | 6.2616 | 0.7826 | 5.9433 | 0.7391 | XLK | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 7.5241 | 13.5627 | 15.6899 | 0.6667 | 7.5241 | 0.6667 | 5.3523 | 7.3092 | 0.6667 | 6.9878 | 0.6000 | XLK | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 11.0251 | 11.4874 | 14.6897 | 0.8333 | 11.0251 | 0.8333 | 4.1216 | 10.8033 | 0.8333 | 10.4714 | 0.8333 | XLK | etf |
| candidate | development | 26 | 23 | sufficient_sample | 7.7962 | 8.6048 | 9.0968 | 0.7826 | 7.7962 | 0.7826 | 6.9920 | 7.5808 | 0.7826 | 7.2585 | 0.7826 | XLK | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.0124 | 13.5627 | 13.5664 | 0.6667 | 9.0124 | 0.6667 | 6.6982 | 8.7945 | 0.6667 | 8.4687 | 0.6000 | XLK | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 15.9713 | 15.7935 | 11.4651 | 0.9167 | 15.9713 | 0.9167 | 8.4255 | 15.7396 | 0.9167 | 15.3929 | 0.9167 | XLK | etf |
| baseline | development | 26 | 23 | sufficient_sample | 6.7477 | 7.2667 | 4.5583 | 0.9130 | 6.7477 | 0.9130 | 5.7738 | 6.5344 | 0.9130 | 6.2153 | 0.9130 | XLP | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 3.5033 | 2.9993 | 4.1996 | 0.6667 | 3.5033 | 0.6667 | 7.1081 | 3.2965 | 0.6000 | 2.9870 | 0.6000 | XLP | etf |
| baseline | validation | 26 | 11 | insufficient_sample | 1.9964 | 1.5897 | 7.0653 | 0.5455 | 1.9964 | 0.5455 | 5.9030 | 1.7926 | 0.5455 | 1.4877 | 0.5455 | XLP | etf |
| candidate | development | 26 | 23 | sufficient_sample | 6.2871 | 6.1974 | 4.7293 | 0.9130 | 6.2871 | 0.9130 | 5.8146 | 6.0748 | 0.9130 | 5.7570 | 0.9130 | XLP | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 4.6597 | 5.1520 | 5.0589 | 0.8000 | 4.6597 | 0.8000 | 7.5971 | 4.4506 | 0.7333 | 4.1377 | 0.7333 | XLP | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 2.7135 | 2.1152 | 8.0054 | 0.5833 | 2.7135 | 0.5833 | 7.2983 | 2.5083 | 0.5833 | 2.2012 | 0.5833 | XLP | etf |
| baseline | development | 26 | 22 | sufficient_sample | 5.4917 | 5.5957 | 6.4774 | 0.7727 | 5.4917 | 0.7727 | 5.8351 | 5.2809 | 0.7273 | 4.9655 | 0.7273 | XLU | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.7216 | 5.6342 | 9.1124 | 0.8000 | 4.7216 | 0.8000 | 7.3357 | 4.5123 | 0.8000 | 4.1993 | 0.8000 | XLU | etf |
| baseline | validation | 26 | 10 | insufficient_sample | 3.4309 | 5.4457 | 7.7880 | 0.7000 | 3.4309 | 0.7000 | 5.8507 | 3.2242 | 0.7000 | 2.9150 | 0.7000 | XLU | etf |
| candidate | development | 26 | 23 | sufficient_sample | 5.3922 | 5.8281 | 5.4651 | 0.8261 | 5.3922 | 0.8261 | 6.1562 | 5.1816 | 0.7826 | 4.8665 | 0.7826 | XLU | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 6.5006 | 7.5014 | 9.3327 | 0.8000 | 6.5006 | 0.8000 | 6.2883 | 6.2878 | 0.8000 | 5.9694 | 0.8000 | XLU | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 4.6940 | 7.8020 | 7.7181 | 0.7500 | 4.6940 | 0.7500 | 8.1294 | 4.4848 | 0.7500 | 4.1719 | 0.7500 | XLU | etf |
| baseline | development | 26 | 21 | sufficient_sample | 7.1394 | 9.5711 | 8.4279 | 0.8571 | 7.1394 | 0.8571 | 5.1443 | 6.9253 | 0.8571 | 6.6050 | 0.8095 | XLV | etf |
| baseline | holdout | 26 | 14 | insufficient_sample | 1.1656 | 0.5865 | 6.3589 | 0.5000 | 1.1656 | 0.5000 | 5.1921 | 0.9634 | 0.5000 | 0.6610 | 0.5000 | XLV | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 7.3870 | 6.9731 | 5.9444 | 0.8333 | 7.3870 | 0.8333 | 8.1061 | 7.1724 | 0.8333 | 6.8514 | 0.8333 | XLV | etf |
| candidate | development | 26 | 22 | sufficient_sample | 7.6043 | 9.3258 | 9.4768 | 0.7727 | 7.6043 | 0.7727 | 5.8613 | 7.3893 | 0.7727 | 7.0676 | 0.7273 | XLV | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.7795 | 1.8866 | 5.9963 | 0.6667 | 2.7795 | 0.6667 | 6.7344 | 2.5742 | 0.6667 | 2.2669 | 0.6667 | XLV | etf |
| candidate | validation | 26 | 13 | insufficient_sample | 7.8946 | 7.4466 | 5.9572 | 0.8462 | 7.8946 | 0.8462 | 8.4682 | 7.6790 | 0.8462 | 7.3564 | 0.8462 | XLV | etf |
| baseline | development | 26 | 23 | sufficient_sample | 7.3329 | 6.4079 | 8.1701 | 0.8261 | 7.3329 | 0.8261 | 5.5486 | 7.1184 | 0.8261 | 6.7976 | 0.7826 | XLY | etf |
| baseline | holdout | 26 | 13 | insufficient_sample | 5.4973 | 7.0359 | 11.3492 | 0.6923 | 5.4973 | 0.6923 | 7.9917 | 5.2865 | 0.6923 | 4.9712 | 0.6923 | XLY | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 4.8161 | 7.9196 | 13.7614 | 0.8333 | 4.8161 | 0.8333 | 3.7129 | 4.6067 | 0.8333 | 4.2933 | 0.7500 | XLY | etf |
| candidate | development | 26 | 23 | sufficient_sample | 8.4423 | 8.1057 | 9.5328 | 0.7826 | 8.4423 | 0.7826 | 6.5431 | 8.2257 | 0.7826 | 7.9015 | 0.7826 | XLY | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.4490 | 6.8393 | 12.3827 | 0.6667 | 2.4490 | 0.6667 | 5.6083 | 2.2443 | 0.6667 | 1.9381 | 0.6667 | XLY | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 9.8228 | 10.1398 | 13.4620 | 0.9167 | 9.8228 | 0.9167 | 7.7548 | 9.6033 | 0.9167 | 9.2750 | 0.8333 | XLY | etf |
| baseline | development | 26 | 16 | insufficient_sample | 6.3500 | 6.1882 | 8.8261 | 0.7500 | 6.3500 | 0.7500 | 8.1492 | 6.1375 | 0.7500 | 5.8196 | 0.7500 | XOM | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 15.5665 | 12.1265 | 21.3152 | 0.6429 | 15.5665 | 0.6429 | 5.9033 | 15.3356 | 0.6429 | 14.9901 | 0.6429 | XOM | stock |
| baseline | validation | 26 | 8 | insufficient_sample | -4.0914 | -5.7167 | 4.4657 | 0.2500 | -4.0914 | 0.2500 | 4.9042 | -4.2830 | 0.2500 | -4.5698 | 0.2500 | XOM | stock |
| candidate | development | 26 | 22 | sufficient_sample | 3.5883 | 3.2407 | 11.8241 | 0.6364 | 3.5883 | 0.6364 | 6.8216 | 3.3814 | 0.6364 | 3.0717 | 0.5909 | XOM | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 14.3731 | 14.3535 | 20.9236 | 0.6875 | 14.3731 | 0.6875 | 7.4326 | 14.1446 | 0.6875 | 13.8027 | 0.6250 | XOM | stock |
| candidate | validation | 26 | 11 | insufficient_sample | -6.2704 | -6.1462 | 6.7317 | 0.1818 | -6.2704 | 0.1818 | 6.5732 | -6.4576 | 0.1818 | -6.7379 | 0.0909 | XOM | stock |

## downside

| rule | split | horizon_weeks | count | q10 | q25 | median | q75 | q90 | max_drawdown_pct |
|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 955 | -9.0542 | -2.1730 | 3.3099 | 9.4058 | 14.8872 | -56.4395 |
| candidate | validation | 13 | 530 | -10.7489 | -1.7576 | 4.2537 | 9.8189 | 15.8212 | -161.8953 |
| candidate | holdout | 13 | 642 | -12.0219 | -3.9351 | 2.7154 | 9.7018 | 18.5518 | -134.3971 |
| baseline | development | 13 | 875 | -8.5501 | -2.4581 | 3.0851 | 9.4509 | 14.1022 | -69.4846 |
| baseline | validation | 13 | 493 | -10.4458 | -2.1226 | 4.2249 | 9.7011 | 15.5137 | -99.5722 |
| baseline | holdout | 13 | 587 | -10.5184 | -3.5820 | 2.8636 | 10.1493 | 18.3222 | -83.5486 |
| candidate | development | 26 | 921 | -9.4765 | -0.9563 | 7.3963 | 14.3187 | 23.0885 | -101.0733 |
| candidate | validation | 26 | 500 | -12.0523 | -1.8443 | 7.3185 | 15.4826 | 24.4934 | -193.6437 |
| candidate | holdout | 26 | 609 | -12.2764 | -3.2207 | 6.3556 | 16.0075 | 27.6067 | -222.2300 |
| baseline | development | 26 | 850 | -8.6880 | -1.0224 | 6.5680 | 13.7873 | 23.3849 | -122.9852 |
| baseline | validation | 26 | 463 | -12.7569 | -2.5037 | 6.6476 | 15.0293 | 25.4085 | -144.6346 |
| baseline | holdout | 26 | 555 | -11.5325 | -2.9748 | 6.1801 | 15.1274 | 26.2439 | -188.3173 |

## cost_sensitivity

| rule | split | horizon_weeks | slippage_bps | count | mean_net_return_pct | median_net_return_pct | std_net_return_pct | win_rate |
|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 0.0000 | 955 | 3.3372 | 3.3099 | 10.3031 | 0.6628 |
| candidate | validation | 13 | 0.0000 | 530 | 3.4951 | 4.2537 | 13.0849 | 0.6811 |
| candidate | holdout | 13 | 0.0000 | 642 | 3.3743 | 2.7154 | 12.5271 | 0.6215 |
| baseline | development | 13 | 0.0000 | 875 | 3.4298 | 3.0851 | 10.0064 | 0.6640 |
| baseline | validation | 13 | 0.0000 | 493 | 3.5358 | 4.2249 | 12.5634 | 0.6917 |
| baseline | holdout | 13 | 0.0000 | 587 | 3.7183 | 2.8636 | 12.5843 | 0.6371 |
| candidate | development | 13 | 10.0000 | 955 | 3.1308 | 3.1035 | 10.2825 | 0.6524 |
| candidate | validation | 13 | 10.0000 | 530 | 3.2883 | 4.0454 | 13.0587 | 0.6755 |
| candidate | holdout | 13 | 10.0000 | 642 | 3.1677 | 2.5102 | 12.5021 | 0.6153 |
| baseline | development | 13 | 10.0000 | 875 | 3.2232 | 2.8792 | 9.9864 | 0.6571 |
| baseline | validation | 13 | 10.0000 | 493 | 3.3289 | 4.0166 | 12.5383 | 0.6876 |
| baseline | holdout | 13 | 10.0000 | 587 | 3.5110 | 2.6581 | 12.5592 | 0.6286 |
| candidate | development | 13 | 25.0000 | 955 | 2.8218 | 2.7947 | 10.2517 | 0.6408 |
| candidate | validation | 13 | 25.0000 | 530 | 2.9789 | 3.7338 | 13.0196 | 0.6717 |
| candidate | holdout | 13 | 25.0000 | 642 | 2.8587 | 2.2031 | 12.4646 | 0.6028 |
| baseline | development | 13 | 25.0000 | 875 | 2.9140 | 2.5710 | 9.9565 | 0.6343 |
| baseline | validation | 13 | 25.0000 | 493 | 3.0194 | 3.7050 | 12.5007 | 0.6815 |
| baseline | holdout | 13 | 25.0000 | 587 | 3.2010 | 2.3506 | 12.5215 | 0.6150 |
| candidate | development | 26 | 0.0000 | 921 | 7.1755 | 7.3963 | 14.2281 | 0.7242 |
| candidate | validation | 26 | 0.0000 | 500 | 7.2270 | 7.3185 | 17.4503 | 0.6900 |
| candidate | holdout | 26 | 0.0000 | 609 | 7.3069 | 6.3556 | 19.2396 | 0.6617 |
| baseline | development | 26 | 0.0000 | 850 | 6.9760 | 6.5680 | 14.0750 | 0.7224 |
| baseline | validation | 26 | 0.0000 | 463 | 6.7371 | 6.6476 | 16.9510 | 0.6739 |
| baseline | holdout | 26 | 0.0000 | 555 | 6.9471 | 6.1801 | 18.6579 | 0.6523 |
| candidate | development | 26 | 10.0000 | 921 | 6.9614 | 7.1818 | 14.1996 | 0.7166 |
| candidate | validation | 26 | 10.0000 | 500 | 7.0128 | 7.1041 | 17.4154 | 0.6900 |
| candidate | holdout | 26 | 10.0000 | 609 | 7.0925 | 6.1431 | 19.2011 | 0.6568 |
| baseline | development | 26 | 10.0000 | 850 | 6.7623 | 6.3551 | 14.0469 | 0.7165 |
| baseline | validation | 26 | 10.0000 | 463 | 6.5239 | 6.4345 | 16.9171 | 0.6739 |
| baseline | holdout | 26 | 10.0000 | 555 | 6.7334 | 5.9679 | 18.6206 | 0.6468 |
| candidate | development | 26 | 25.0000 | 921 | 6.6410 | 6.8607 | 14.1571 | 0.7090 |
| candidate | validation | 26 | 25.0000 | 500 | 6.6922 | 6.7833 | 17.3633 | 0.6720 |
| candidate | holdout | 26 | 25.0000 | 609 | 6.7717 | 5.8251 | 19.1436 | 0.6519 |
| baseline | development | 26 | 25.0000 | 850 | 6.4425 | 6.0365 | 14.0048 | 0.7059 |
| baseline | validation | 26 | 25.0000 | 463 | 6.2048 | 6.1157 | 16.8664 | 0.6674 |
| baseline | holdout | 26 | 25.0000 | 555 | 6.4137 | 5.6505 | 18.5649 | 0.6414 |

## exposure

| ticker | rule | split | trade_count | complete_count | weeks_in_market |
|---|---|---|---|---|---|
| AAPL | baseline | development | 27 | 19 | 247 |
| AAPL | baseline | holdout | 15 | 14 | 182 |
| AAPL | baseline | validation | 17 | 13 | 169 |
| AAPL | candidate | development | 30 | 22 | 286 |
| AAPL | candidate | holdout | 17 | 16 | 208 |
| AAPL | candidate | validation | 18 | 13 | 169 |
| AMZN | baseline | development | 29 | 22 | 286 |
| AMZN | baseline | holdout | 14 | 13 | 169 |
| AMZN | baseline | validation | 21 | 12 | 156 |
| AMZN | candidate | development | 34 | 23 | 299 |
| AMZN | candidate | holdout | 16 | 15 | 195 |
| AMZN | candidate | validation | 24 | 13 | 169 |
| BA | baseline | development | 28 | 22 | 286 |
| BA | baseline | holdout | 12 | 11 | 143 |
| BA | baseline | validation | 18 | 10 | 130 |
| BA | candidate | development | 33 | 22 | 286 |
| BA | candidate | holdout | 14 | 13 | 169 |
| BA | candidate | validation | 18 | 12 | 156 |
| BAC | baseline | development | 24 | 17 | 221 |
| BAC | baseline | holdout | 16 | 15 | 195 |
| BAC | baseline | validation | 18 | 10 | 130 |
| BAC | candidate | development | 28 | 18 | 234 |
| BAC | candidate | holdout | 16 | 15 | 195 |
| BAC | candidate | validation | 16 | 13 | 169 |
| CAT | baseline | development | 31 | 17 | 221 |
| CAT | baseline | holdout | 15 | 14 | 182 |
| CAT | baseline | validation | 14 | 13 | 169 |
| CAT | candidate | development | 34 | 20 | 260 |
| CAT | candidate | holdout | 16 | 15 | 195 |
| CAT | candidate | validation | 22 | 13 | 169 |
| COST | baseline | development | 26 | 22 | 286 |
| COST | baseline | holdout | 16 | 16 | 208 |
| COST | baseline | validation | 20 | 13 | 169 |
| COST | candidate | development | 29 | 23 | 299 |
| COST | candidate | holdout | 17 | 16 | 208 |
| COST | candidate | validation | 27 | 13 | 169 |
| CSCO | baseline | development | 32 | 18 | 234 |
| CSCO | baseline | holdout | 15 | 14 | 182 |
| CSCO | baseline | validation | 16 | 10 | 130 |
| CSCO | candidate | development | 24 | 22 | 286 |
| CSCO | candidate | holdout | 16 | 15 | 195 |
| CSCO | candidate | validation | 19 | 13 | 169 |
| CVX | baseline | development | 28 | 19 | 247 |
| CVX | baseline | holdout | 15 | 14 | 182 |
| CVX | baseline | validation | 18 | 11 | 143 |
| CVX | candidate | development | 24 | 23 | 299 |
| CVX | candidate | holdout | 18 | 17 | 221 |
| CVX | candidate | validation | 18 | 12 | 156 |
| DIA | baseline | development | 36 | 22 | 286 |
| DIA | baseline | holdout | 17 | 16 | 208 |
| DIA | baseline | validation | 14 | 13 | 169 |
| DIA | candidate | development | 28 | 24 | 312 |
| DIA | candidate | holdout | 17 | 16 | 208 |
| DIA | candidate | validation | 21 | 13 | 169 |
| DIS | baseline | development | 29 | 21 | 273 |
| DIS | baseline | holdout | 11 | 10 | 130 |
| DIS | baseline | validation | 19 | 12 | 156 |
| DIS | candidate | development | 30 | 22 | 286 |
| DIS | candidate | holdout | 14 | 13 | 169 |
| DIS | candidate | validation | 18 | 13 | 169 |
| GOOGL | baseline | development | 26 | 21 | 273 |
| GOOGL | baseline | holdout | 15 | 15 | 195 |
| GOOGL | baseline | validation | 17 | 13 | 169 |
| GOOGL | candidate | development | 31 | 23 | 299 |
| GOOGL | candidate | holdout | 16 | 15 | 195 |
| GOOGL | candidate | validation | 22 | 13 | 169 |
| GS | baseline | development | 23 | 16 | 208 |
| GS | baseline | holdout | 16 | 15 | 195 |
| GS | baseline | validation | 23 | 10 | 130 |
| GS | candidate | development | 31 | 20 | 260 |
| GS | candidate | holdout | 16 | 15 | 195 |
| GS | candidate | validation | 25 | 12 | 156 |
| HD | baseline | development | 29 | 22 | 286 |
| HD | baseline | holdout | 13 | 13 | 169 |
| HD | baseline | validation | 19 | 13 | 169 |
| HD | candidate | development | 24 | 24 | 312 |
| HD | candidate | holdout | 16 | 15 | 195 |
| HD | candidate | validation | 24 | 13 | 169 |
| HON | baseline | development | 32 | 23 | 299 |
| HON | baseline | holdout | 13 | 13 | 169 |
| HON | baseline | validation | 14 | 13 | 169 |
| HON | candidate | development | 24 | 24 | 312 |
| HON | candidate | holdout | 16 | 15 | 195 |
| HON | candidate | validation | 20 | 13 | 169 |
| IBM | baseline | development | 31 | 18 | 234 |
| IBM | baseline | holdout | 16 | 15 | 195 |
| IBM | baseline | validation | 17 | 9 | 117 |
| IBM | candidate | development | 22 | 21 | 273 |
| IBM | candidate | holdout | 17 | 17 | 221 |
| IBM | candidate | validation | 16 | 11 | 143 |
| IWM | baseline | development | 29 | 21 | 273 |
| IWM | baseline | holdout | 14 | 13 | 169 |
| IWM | baseline | validation | 14 | 13 | 169 |
| IWM | candidate | development | 31 | 23 | 299 |
| IWM | candidate | holdout | 16 | 15 | 195 |
| IWM | candidate | validation | 19 | 13 | 169 |
| JNJ | baseline | development | 23 | 21 | 273 |
| JNJ | baseline | holdout | 16 | 16 | 208 |
| JNJ | baseline | validation | 18 | 12 | 156 |
| JNJ | candidate | development | 33 | 23 | 299 |
| JNJ | candidate | holdout | 16 | 16 | 208 |
| JNJ | candidate | validation | 19 | 13 | 169 |
| JPM | baseline | development | 27 | 20 | 260 |
| JPM | baseline | holdout | 15 | 15 | 195 |
| JPM | baseline | validation | 22 | 11 | 143 |
| JPM | candidate | development | 35 | 23 | 299 |
| JPM | candidate | holdout | 16 | 16 | 208 |
| JPM | candidate | validation | 23 | 12 | 156 |
| KO | baseline | development | 22 | 22 | 286 |
| KO | baseline | holdout | 16 | 15 | 195 |
| KO | baseline | validation | 16 | 12 | 156 |
| KO | candidate | development | 27 | 23 | 299 |
| KO | candidate | holdout | 17 | 16 | 208 |
| KO | candidate | validation | 22 | 13 | 169 |
| MCD | baseline | development | 28 | 22 | 286 |
| MCD | baseline | holdout | 16 | 15 | 195 |
| MCD | baseline | validation | 13 | 12 | 156 |
| MCD | candidate | development | 24 | 24 | 312 |
| MCD | candidate | holdout | 17 | 16 | 208 |
| MCD | candidate | validation | 21 | 12 | 156 |
| MMM | baseline | development | 25 | 22 | 286 |
| MMM | baseline | holdout | 13 | 12 | 156 |
| MMM | baseline | validation | 11 | 10 | 130 |
| MMM | candidate | development | 27 | 24 | 312 |
| MMM | candidate | holdout | 14 | 13 | 169 |
| MMM | candidate | validation | 21 | 12 | 156 |
| MRK | baseline | development | 34 | 21 | 273 |
| MRK | baseline | holdout | 14 | 13 | 169 |
| MRK | baseline | validation | 19 | 12 | 156 |
| MRK | candidate | development | 37 | 23 | 299 |
| MRK | candidate | holdout | 15 | 14 | 182 |
| MRK | candidate | validation | 15 | 13 | 169 |
| MSFT | baseline | development | 32 | 21 | 273 |
| MSFT | baseline | holdout | 16 | 15 | 195 |
| MSFT | baseline | validation | 26 | 13 | 169 |
| MSFT | candidate | development | 36 | 22 | 286 |
| MSFT | candidate | holdout | 17 | 16 | 208 |
| MSFT | candidate | validation | 27 | 13 | 169 |
| NKE | baseline | development | 22 | 22 | 286 |
| NKE | baseline | holdout | 10 | 9 | 117 |
| NKE | baseline | validation | 15 | 12 | 156 |
| NKE | candidate | development | 23 | 23 | 299 |
| NKE | candidate | holdout | 13 | 13 | 169 |
| NKE | candidate | validation | 24 | 13 | 169 |
| NVDA | baseline | development | 33 | 20 | 260 |
| NVDA | baseline | holdout | 16 | 15 | 195 |
| NVDA | baseline | validation | 15 | 12 | 156 |
| NVDA | candidate | development | 34 | 21 | 273 |
| NVDA | candidate | holdout | 16 | 15 | 195 |
| NVDA | candidate | validation | 22 | 12 | 156 |
| ORCL | baseline | development | 25 | 21 | 273 |
| ORCL | baseline | holdout | 14 | 14 | 182 |
| ORCL | baseline | validation | 18 | 13 | 169 |
| ORCL | candidate | development | 28 | 22 | 286 |
| ORCL | candidate | holdout | 17 | 16 | 208 |
| ORCL | candidate | validation | 22 | 13 | 169 |
| PFE | baseline | development | 21 | 21 | 273 |
| PFE | baseline | holdout | 11 | 10 | 130 |
| PFE | baseline | validation | 20 | 12 | 156 |
| PFE | candidate | development | 31 | 23 | 299 |
| PFE | candidate | holdout | 14 | 13 | 169 |
| PFE | candidate | validation | 22 | 13 | 169 |
| PG | baseline | development | 31 | 21 | 273 |
| PG | baseline | holdout | 14 | 14 | 182 |
| PG | baseline | validation | 20 | 12 | 156 |
| PG | candidate | development | 34 | 23 | 299 |
| PG | candidate | holdout | 15 | 15 | 195 |
| PG | candidate | validation | 19 | 12 | 156 |
| QQQ | baseline | development | 35 | 23 | 299 |
| QQQ | baseline | holdout | 15 | 14 | 182 |
| QQQ | baseline | validation | 22 | 13 | 169 |
| QQQ | candidate | development | 27 | 24 | 312 |
| QQQ | candidate | holdout | 16 | 15 | 195 |
| QQQ | candidate | validation | 23 | 13 | 169 |
| UNH | baseline | development | 32 | 23 | 299 |
| UNH | baseline | holdout | 14 | 14 | 182 |
| UNH | baseline | validation | 17 | 13 | 169 |
| UNH | candidate | development | 25 | 24 | 312 |
| UNH | candidate | holdout | 16 | 16 | 208 |
| UNH | candidate | validation | 27 | 13 | 169 |
| UPS | baseline | development | 35 | 22 | 286 |
| UPS | baseline | holdout | 11 | 10 | 130 |
| UPS | baseline | validation | 24 | 11 | 143 |
| UPS | candidate | development | 36 | 23 | 299 |
| UPS | candidate | holdout | 12 | 11 | 143 |
| UPS | candidate | validation | 15 | 12 | 156 |
| WMT | baseline | development | 22 | 20 | 260 |
| WMT | baseline | holdout | 17 | 16 | 208 |
| WMT | baseline | validation | 17 | 12 | 156 |
| WMT | candidate | development | 30 | 22 | 286 |
| WMT | candidate | holdout | 17 | 16 | 208 |
| WMT | candidate | validation | 20 | 13 | 169 |
| XLB | baseline | development | 34 | 21 | 273 |
| XLB | baseline | holdout | 14 | 13 | 169 |
| XLB | baseline | validation | 14 | 12 | 156 |
| XLB | candidate | development | 23 | 23 | 299 |
| XLB | candidate | holdout | 17 | 16 | 208 |
| XLB | candidate | validation | 22 | 13 | 169 |
| XLE | baseline | development | 25 | 17 | 221 |
| XLE | baseline | holdout | 16 | 15 | 195 |
| XLE | baseline | validation | 14 | 7 | 91 |
| XLE | candidate | development | 22 | 22 | 286 |
| XLE | candidate | holdout | 18 | 17 | 221 |
| XLE | candidate | validation | 19 | 11 | 143 |
| XLF | baseline | development | 27 | 20 | 260 |
| XLF | baseline | holdout | 16 | 15 | 195 |
| XLF | baseline | validation | 23 | 11 | 143 |
| XLF | candidate | development | 34 | 23 | 299 |
| XLF | candidate | holdout | 17 | 16 | 208 |
| XLF | candidate | validation | 24 | 12 | 156 |
| XLI | baseline | development | 23 | 23 | 299 |
| XLI | baseline | holdout | 17 | 16 | 208 |
| XLI | baseline | validation | 14 | 13 | 169 |
| XLI | candidate | development | 24 | 24 | 312 |
| XLI | candidate | holdout | 17 | 16 | 208 |
| XLI | candidate | validation | 14 | 13 | 169 |
| XLK | baseline | development | 36 | 23 | 299 |
| XLK | baseline | holdout | 17 | 16 | 208 |
| XLK | baseline | validation | 22 | 13 | 169 |
| XLK | candidate | development | 29 | 24 | 312 |
| XLK | candidate | holdout | 17 | 16 | 208 |
| XLK | candidate | validation | 23 | 13 | 169 |
| XLP | baseline | development | 24 | 24 | 312 |
| XLP | baseline | holdout | 16 | 15 | 195 |
| XLP | baseline | validation | 20 | 12 | 156 |
| XLP | candidate | development | 26 | 24 | 312 |
| XLP | candidate | holdout | 17 | 16 | 208 |
| XLP | candidate | validation | 23 | 13 | 169 |
| XLU | baseline | development | 26 | 23 | 299 |
| XLU | baseline | holdout | 16 | 15 | 195 |
| XLU | baseline | validation | 19 | 11 | 143 |
| XLU | candidate | development | 26 | 24 | 312 |
| XLU | candidate | holdout | 17 | 16 | 208 |
| XLU | candidate | validation | 23 | 13 | 169 |
| XLV | baseline | development | 23 | 22 | 286 |
| XLV | baseline | holdout | 16 | 15 | 195 |
| XLV | baseline | validation | 22 | 13 | 169 |
| XLV | candidate | development | 30 | 23 | 299 |
| XLV | candidate | holdout | 17 | 16 | 208 |
| XLV | candidate | validation | 27 | 13 | 169 |
| XLY | baseline | development | 36 | 23 | 299 |
| XLY | baseline | holdout | 15 | 14 | 182 |
| XLY | baseline | validation | 16 | 13 | 169 |
| XLY | candidate | development | 28 | 24 | 312 |
| XLY | candidate | holdout | 17 | 16 | 208 |
| XLY | candidate | validation | 21 | 13 | 169 |
| XOM | baseline | development | 19 | 17 | 221 |
| XOM | baseline | holdout | 16 | 15 | 195 |
| XOM | baseline | validation | 14 | 8 | 104 |
| XOM | candidate | development | 27 | 23 | 299 |
| XOM | candidate | holdout | 18 | 17 | 221 |
| XOM | candidate | validation | 17 | 11 | 143 |

## Bootstrap (paired candidate-minus-baseline, ticker-year clusters)

| split | rule_pair | horizon_weeks | slippage_bps | count | cluster_count | mean_diff_pct | ci_lower | ci_upper |
|---|---|---|---|---|---|---|---|---|
| development | candidate_minus_baseline | 13 | 5.0000 | 1830 | 294 | 0.1333 | -0.3429 | 0.5920 |
| holdout | candidate_minus_baseline | 13 | 5.0000 | 1229 | 209 | 0.4899 | -0.3608 | 1.3366 |
| validation | candidate_minus_baseline | 13 | 5.0000 | 1023 | 168 | 1.1256 | 0.2100 | 2.1430 |

## Conclusion

**inconclusive**

This conclusion is based on the locked protocol, point-in-time scoring, cross-split exclusion, and non-overlapping per-ticker trade simulation. It does not authorize a production change.

## Limitations

- Events are weekly observations and may overlap within and across tickers in the event-study output.
- The non-overlapping trade policy uses the primary 13-week horizon for spacing and ignores capital allocation.
- Execution assumes fills at the next weekly open and exit at the weekly close; real intraday slippage and partial fills are not modeled.
- The study does not model stops, targets, position sizing, capital allocation, or capacity.
- Survivorship bias, delisting bias, and point-in-time index membership are not eliminated.
- Corporate actions and dividend reinvestment use the provider's default adjustment policy (auto_adjust=True).
- Reported metrics are research evidence, not proof of a durable edge or statistical significance.
- A positive result here would still require a separate Gary-approved production promotion PR.