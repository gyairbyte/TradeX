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
- Manifest SHA-256: `77dfbac2c6724513e817d06e482efd891e76bcad27299e30f32d1386f52533e5`

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
| AAPL | yahoo | ec08dd47158b6ab22ed24765851cfe3667dcb2a08bf3c938d18711d2fd634c20 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| MSFT | yahoo | 76f58856bb1410a0e27eb6381be713b92d678751d7186d30f6064f0568043a93 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| AMZN | yahoo | 835c2a76092471fb1977d8f21432d14a53d2ea500978013baeccfe16fdc5d07e | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| GOOGL | yahoo | 06ba01a2d0606ca849578ba7a638d1d06e8b4bb1bcde9f6018f2133287dfcbcc | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| NVDA | yahoo | 3e1725289cd940c4e16338701ebf3a1c78aef0d665c72646c32b86b0ada4e2e3 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| JPM | yahoo | e602f390a0be2297e5b21d0d351ab1a37d506b9b9fcdfc025a6901cb133be7c8 | 4770 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| BAC | yahoo | 9a90b1247ecd32dd124268a7399b428250ea4b36c8e482e2fc6b9d003be39596 | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| GS | yahoo | 36da0e752419887817986f558e9ccbde3eddb60b8f36a13022689e0f8dd5c5c9 | 4770 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XOM | yahoo | da32496daf7322373f28a1a2b7fddf44c6469281ab2fcc6863d9235ab77f326e | 4756 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 17 | {'warmup': 157, 'development': 363, 'validation': 208, 'holdout': 259} | {} | [] |
| CVX | yahoo | 05025066096a3a86eede7359098a1cbaa7a524ed4bd0ffc42f275269234ff376 | 4765 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 8 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| JNJ | yahoo | 74102a3ed553b8627715860c96215f02591c86fb2e30474d5c8cee55a340e320 | 4770 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| MRK | yahoo | 0452859fc7d82fdf45018f0449e70bfd11f7cab7707364f403dd45558f05991f | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| PFE | yahoo | 8d790e10a2d9751eef7e2b06a03b65cb9f34a18ba92e8a7597422b656fcf1fa3 | 4762 | 985 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 11 | {'warmup': 157, 'development': 361, 'validation': 208, 'holdout': 259} | {} | [] |
| UNH | yahoo | c67b896d167cef6930b3a4f0c6c06c7c31bdf964bda785a91f4f84d5c188ab63 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| PG | yahoo | b2f124b9856e984ca2b34f1fcad0a485d412a5643f4a5f1af00381acd9f3e61a | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| KO | yahoo | 2bc15bcf3bd29fa332b9f8f3d3468496660f8a867eb97c426ccf51f45b9cb068 | 4763 | 985 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 10 | {'warmup': 155, 'development': 362, 'validation': 209, 'holdout': 259} | {} | [] |
| WMT | yahoo | 954e47be1f2857c0cc71a7ad33770835c6eef8c39f4e9fe67f677797a9b391c3 | 4770 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| COST | yahoo | ce39032d3734a681d66aa478ef721cfca2a48e8f8d5a7bd758d4710c10b2c30b | 4771 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| HD | yahoo | 43030413bd27497f63e75ed0a7c1bc09904dd2321d536e3f142a62d073e62e45 | 4770 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 3 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 258} | {} | [] |
| CAT | yahoo | b23cbf4f1dd2656731bdef838392da037aaf456129376ed9b33a0cd5f95f277e | 4771 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| HON | yahoo | c88930c8c8afcd09892da196b1b4692395f768ef8781b68bd03614db541fff31 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| IBM | yahoo | debb0f7f433f45512b643df3a5dcfab5258a016023c8da8fe2af7835361df578 | 4760 | 985 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 13 | {'warmup': 156, 'development': 362, 'validation': 208, 'holdout': 259} | {} | [] |
| CSCO | yahoo | 64986c8b6fcb69e35ecc99c0006deaf64077fa913cf770d58d2357b01df08cc1 | 4767 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 6 | {'warmup': 155, 'development': 365, 'validation': 208, 'holdout': 259} | {} | [] |
| ORCL | yahoo | 74c6ef7a1d0f0a4aaf4473db9a8f2507b045435d9325251814b3116e2a1c2266 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| MCD | yahoo | 1dd00be172d2f0ba5fc13ce79aec816addcea98f2bf7983adb9a92bc20eabbe3 | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| NKE | yahoo | aa78c3fe5440f3e355c6c3910c1bf323d86d7101e300d1384d1845b6cdba9399 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| DIS | yahoo | 35ece39776b2fda6c254708cadc01b57e2e01183fdc9f8acd9a07d2fb8a0017a | 4772 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 208, 'holdout': 259} | {} | [] |
| BA | yahoo | 4765f99c3795cfc6081aeff21fa51efce2299699c5a28936527a15fb4100613b | 4773 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 0 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| MMM | yahoo | 397ac4c49c80c6dfb9b53334ed9e419218606f53639582ba4e3d5fb88c1772a4 | 4766 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 7 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| UPS | yahoo | ddd82b0b0068f8454a78f8ca4ecb2b401d4cc351480c9dfd5e22bcc7a995e842 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| QQQ | yahoo | dd7e42905a217c55803c50f5fc2c625b50c553192d122605195497beb3cee16c | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| IWM | yahoo | b9620f90405dc742b073b332dcfeec7dddf611f2b97ac368b14e3951e16ef58e | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| DIA | yahoo | faaec48f4b558208c625b97559e37ae52972a36ad22e3c08e0232109c37f9a84 | 4771 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| XLB | yahoo | 9371bd02185d18a3eb7e117f1a8ed9145350623d7dc51ac3fe5eec841b3316fd | 4765 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 8 | {'warmup': 155, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLE | yahoo | d58d4b8eace4f41c1e47a8c2e6fa407d7d2373025e5fe9a3dc7df4f387be05a7 | 4768 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLF | yahoo | da5558bee6b4ee0976bdc263b1869ec87838d8fba322bb808bb22aa053e53596 | 4769 | 988 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 156, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| XLI | yahoo | 7c9bcc1e0558c5932398d7a354c81dd4ecc1111d21637bbde68f8eef9ac3e1f5 | 4768 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 5 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLK | yahoo | d04046aece3d9a43426ea07493f7ce735dc4072b1ee23b2bbe96d193e64bd56a | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLP | yahoo | 031bf79863a393cb68ed8b4aed49668419f2ee78b7124bde27437cd4b1bafed5 | 4772 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 1 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLU | yahoo | 154f6cf2be986079547ee1cdb65ba68c49dca6a956ad51ea15f4e0dc9e838da1 | 4766 | 987 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 7 | {'warmup': 155, 'development': 364, 'validation': 209, 'holdout': 259} | {} | [] |
| XLV | yahoo | 7f86cfde776bfd6147c55dcd3bcf738aa9dfba749e14862fc78136883de076c2 | 4771 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| XLY | yahoo | 64bb0b72fa20de6cec0e8d8f7a07cbc8cf906e29be9e24e3790c08040f5039c1 | 4769 | 990 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 4 | {'warmup': 157, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |
| SPY | yahoo | 4e52abd7eac4c314b2deccee12cdd39dee9e22ef17a5430175a82f4ec6ca38fc | 4771 | 989 | 2007-01-05T21:00:00+00:00 | 2025-12-19T21:00:00+00:00 | 0 | 0 | 2 | {'warmup': 156, 'development': 365, 'validation': 209, 'holdout': 259} | {} | [] |

## Events and trades

Total overlapping events: `53857`
Total non-overlapping trades: `5327`
Events by rule:
| rule | count |
|---|---|
| candidate | 28441 |
| baseline | 25416 |

## Split summary

- **development**:
  - candidate: count=955, mean_net=3.2393, win_rate=0.6597, tickers=42
  - baseline: count=877, mean_net=3.3337, win_rate=0.6591, tickers=42
  - pooled lift (pct): -0.0944, median lift at 25.0bps per side (pct): -0.0940, q10 lift (pct): -0.9992
  - positive lift fraction stock: 0.5667, positive lift fraction etf: 0.5000
- **validation**:
  - candidate: count=530, mean_net=3.3797, win_rate=0.6868, tickers=42
  - baseline: count=493, mean_net=3.4393, win_rate=0.6876, tickers=42
  - pooled lift (pct): -0.0596, median lift at 25.0bps per side (pct): -0.0594, q10 lift (pct): -0.1435
  - positive lift fraction stock: 0.5000, positive lift fraction etf: 0.5833
- **holdout**:
  - candidate: count=642, mean_net=3.2786, win_rate=0.6184, tickers=42
  - baseline: count=587, mean_net=3.6333, win_rate=0.6320, tickers=42
  - pooled lift (pct): -0.3547, median lift at 25.0bps per side (pct): -0.3533, q10 lift (pct): -1.5854
  - positive lift fraction stock: 0.5000, positive lift fraction etf: 0.5000

## thresholds

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 12527 | sufficient_sample | 3.6049 | 3.4508 | 9.9413 | 0.6650 | 3.6049 | 0.6650 | 3.1343 | 3.3979 | 0.6559 | 3.0882 | 0.6425 |
| candidate | validation | 13 | 6671 | sufficient_sample | 3.5185 | 4.0408 | 12.0460 | 0.6671 | 3.5185 | 0.6671 | 3.0413 | 3.3117 | 0.6597 | 3.0022 | 0.6479 |
| candidate | holdout | 13 | 7755 | sufficient_sample | 3.7445 | 2.9230 | 12.3171 | 0.6134 | 3.7445 | 0.6134 | 3.7971 | 3.5372 | 0.6061 | 3.2271 | 0.5932 |
| baseline | development | 13 | 11078 | sufficient_sample | 3.3231 | 3.2341 | 9.7006 | 0.6572 | 3.3231 | 0.6572 | 2.9298 | 3.1167 | 0.6479 | 2.8078 | 0.6334 |
| baseline | validation | 13 | 5890 | sufficient_sample | 3.3999 | 3.8517 | 11.8951 | 0.6603 | 3.3999 | 0.6603 | 2.5845 | 3.1933 | 0.6523 | 2.8842 | 0.6406 |
| baseline | holdout | 13 | 7004 | sufficient_sample | 3.8560 | 2.9252 | 12.1396 | 0.6156 | 3.8560 | 0.6156 | 3.8757 | 3.6485 | 0.6079 | 3.3380 | 0.5949 |
| candidate | development | 26 | 12017 | sufficient_sample | 7.3437 | 7.0141 | 13.6461 | 0.7358 | 7.3437 | 0.7358 | 6.4666 | 7.1292 | 0.7311 | 6.8083 | 0.7238 |
| candidate | validation | 26 | 6258 | sufficient_sample | 7.1882 | 6.5795 | 16.8100 | 0.6852 | 7.1882 | 0.6852 | 6.2208 | 6.9740 | 0.6810 | 6.6536 | 0.6711 |
| candidate | holdout | 26 | 7287 | sufficient_sample | 6.9642 | 5.5557 | 18.2117 | 0.6580 | 6.9642 | 0.6580 | 6.7523 | 6.7505 | 0.6512 | 6.4307 | 0.6422 |
| baseline | development | 26 | 10599 | sufficient_sample | 6.9250 | 6.5601 | 13.6463 | 0.7290 | 6.9250 | 0.7290 | 6.0236 | 6.7114 | 0.7245 | 6.3917 | 0.7167 |
| baseline | validation | 26 | 5510 | sufficient_sample | 6.8624 | 6.0725 | 16.7759 | 0.6728 | 6.8624 | 0.6728 | 5.5245 | 6.6489 | 0.6688 | 6.3295 | 0.6586 |
| baseline | holdout | 26 | 6579 | sufficient_sample | 7.2044 | 5.9407 | 17.9145 | 0.6680 | 7.2044 | 0.6680 | 6.7867 | 6.9902 | 0.6610 | 6.6697 | 0.6519 |

## cohorts

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | cohort |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 8753 | sufficient_sample | 3.8618 | 3.3408 | 10.9769 | 0.6454 | 3.8618 | 0.6454 | 3.1604 | 3.6543 | 0.6358 | 3.3438 | 0.6242 | stock |
| baseline | development | 13 | 7669 | sufficient_sample | 3.5536 | 3.1343 | 10.7746 | 0.6352 | 3.5536 | 0.6352 | 2.9735 | 3.3467 | 0.6255 | 3.0371 | 0.6132 | stock |
| candidate | development | 13 | 3774 | sufficient_sample | 3.0091 | 3.6207 | 6.9343 | 0.7104 | 3.0091 | 0.7104 | 3.0739 | 2.8033 | 0.7027 | 2.4953 | 0.6847 | etf |
| baseline | development | 13 | 3409 | sufficient_sample | 2.8048 | 3.3772 | 6.6513 | 0.7067 | 2.8048 | 0.7067 | 2.8315 | 2.5993 | 0.6982 | 2.2920 | 0.6788 | etf |
| candidate | validation | 13 | 4690 | sufficient_sample | 3.9660 | 4.2181 | 12.9599 | 0.6520 | 3.9660 | 0.6520 | 3.1100 | 3.7582 | 0.6443 | 3.4474 | 0.6337 | stock |
| baseline | validation | 13 | 4127 | sufficient_sample | 3.9777 | 4.0604 | 12.8168 | 0.6445 | 3.9777 | 0.6445 | 2.6906 | 3.7699 | 0.6361 | 3.4591 | 0.6252 | stock |
| candidate | validation | 13 | 1981 | sufficient_sample | 2.4592 | 3.8174 | 9.4557 | 0.7027 | 2.4592 | 0.7027 | 2.8788 | 2.2545 | 0.6961 | 1.9481 | 0.6815 | etf |
| baseline | validation | 13 | 1763 | sufficient_sample | 2.0473 | 3.6526 | 9.2499 | 0.6971 | 2.0473 | 0.6971 | 2.3362 | 1.8434 | 0.6903 | 1.5383 | 0.6767 | etf |
| candidate | holdout | 13 | 5360 | sufficient_sample | 4.1440 | 3.1138 | 13.7174 | 0.5996 | 4.1440 | 0.5996 | 3.8203 | 3.9359 | 0.5931 | 3.6246 | 0.5819 | stock |
| baseline | holdout | 13 | 4836 | sufficient_sample | 4.2586 | 3.1138 | 13.5774 | 0.6003 | 4.2586 | 0.6003 | 3.8786 | 4.0503 | 0.5935 | 3.7386 | 0.5823 | stock |
| candidate | holdout | 13 | 2395 | sufficient_sample | 2.8504 | 2.7299 | 8.3049 | 0.6443 | 2.8504 | 0.6443 | 3.7454 | 2.6450 | 0.6351 | 2.3375 | 0.6184 | etf |
| baseline | holdout | 13 | 2168 | sufficient_sample | 2.9577 | 2.7670 | 7.9826 | 0.6499 | 2.9577 | 0.6499 | 3.8692 | 2.7520 | 0.6402 | 2.4442 | 0.6232 | etf |
| candidate | development | 26 | 8398 | sufficient_sample | 7.7919 | 7.1533 | 15.1814 | 0.7118 | 7.7919 | 0.7118 | 6.5033 | 7.5765 | 0.7073 | 7.2542 | 0.7006 | stock |
| baseline | development | 26 | 7346 | sufficient_sample | 7.4037 | 6.6284 | 15.3191 | 0.7035 | 7.4037 | 0.7035 | 6.1125 | 7.1891 | 0.6992 | 6.8681 | 0.6919 | stock |
| candidate | development | 26 | 3619 | sufficient_sample | 6.3037 | 6.8371 | 9.0537 | 0.7914 | 6.3037 | 0.7914 | 6.3817 | 6.0913 | 0.7864 | 5.7735 | 0.7776 | etf |
| baseline | development | 26 | 3253 | sufficient_sample | 5.8439 | 6.4741 | 8.6672 | 0.7867 | 5.8439 | 0.7867 | 5.8227 | 5.6324 | 0.7817 | 5.3160 | 0.7725 | etf |
| candidate | validation | 26 | 4401 | sufficient_sample | 8.2140 | 6.8528 | 18.5070 | 0.6773 | 8.2140 | 0.6773 | 6.4233 | 7.9978 | 0.6730 | 7.6743 | 0.6648 | stock |
| baseline | validation | 26 | 3858 | sufficient_sample | 7.9417 | 6.2143 | 18.6330 | 0.6641 | 7.9417 | 0.6641 | 5.6797 | 7.7260 | 0.6597 | 7.4033 | 0.6509 | stock |
| candidate | validation | 26 | 1857 | sufficient_sample | 4.7570 | 6.1178 | 11.4949 | 0.7038 | 4.7570 | 0.7038 | 5.7407 | 4.5477 | 0.7001 | 4.2345 | 0.6861 | etf |
| baseline | validation | 26 | 1652 | sufficient_sample | 4.3421 | 5.8816 | 10.8991 | 0.6931 | 4.3421 | 0.6931 | 5.1620 | 4.1336 | 0.6901 | 3.8217 | 0.6768 | etf |
| candidate | holdout | 26 | 5042 | sufficient_sample | 7.8577 | 6.0063 | 20.4511 | 0.6434 | 7.8577 | 0.6434 | 6.8228 | 7.6422 | 0.6372 | 7.3197 | 0.6307 | stock |
| baseline | holdout | 26 | 4548 | sufficient_sample | 8.0812 | 6.1674 | 20.1489 | 0.6508 | 8.0812 | 0.6508 | 6.8098 | 7.8652 | 0.6447 | 7.5421 | 0.6376 | stock |
| candidate | holdout | 26 | 2245 | sufficient_sample | 4.9576 | 4.9332 | 11.4627 | 0.6909 | 4.9576 | 0.6909 | 6.5940 | 4.7479 | 0.6824 | 4.4341 | 0.6682 | etf |
| baseline | holdout | 26 | 2031 | sufficient_sample | 5.2411 | 5.4680 | 11.1757 | 0.7065 | 5.2411 | 0.7065 | 6.7349 | 5.0308 | 0.6977 | 4.7162 | 0.6839 | etf |

## groups

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | group |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 10872 | sufficient_sample | 3.3405 | 3.2408 | 9.6852 | 0.6576 | 3.3405 | 0.6576 | 2.9383 | 3.1340 | 0.6484 | 2.8251 | 0.6337 | baseline_and_candidate |
| baseline | development | 13 | 10872 | sufficient_sample | 3.3405 | 3.2408 | 9.6852 | 0.6576 | 3.3405 | 0.6576 | 2.9383 | 3.1340 | 0.6484 | 2.8251 | 0.6337 | baseline_and_candidate |
| candidate | development | 13 | 1655 | sufficient_sample | 5.3422 | 5.3370 | 11.3302 | 0.7136 | 5.3422 | 0.7136 | 4.4223 | 5.1318 | 0.7057 | 4.8168 | 0.6997 | candidate_only |
| baseline | development | 13 | 206 | sufficient_sample | 2.4087 | 3.0435 | 10.4383 | 0.6359 | 2.4087 | 0.6359 | 2.4842 | 2.2041 | 0.6214 | 1.8979 | 0.6165 | baseline_only |
| candidate | validation | 13 | 5768 | sufficient_sample | 3.3022 | 3.7713 | 11.8089 | 0.6581 | 3.3022 | 0.6581 | 2.5559 | 3.0958 | 0.6500 | 2.7870 | 0.6380 | baseline_and_candidate |
| baseline | validation | 13 | 5768 | sufficient_sample | 3.3022 | 3.7713 | 11.8089 | 0.6581 | 3.3022 | 0.6581 | 2.5559 | 3.0958 | 0.6500 | 2.7870 | 0.6380 | baseline_and_candidate |
| candidate | validation | 13 | 903 | sufficient_sample | 4.9000 | 5.5161 | 13.3804 | 0.7243 | 4.9000 | 0.7243 | 6.1424 | 4.6904 | 0.7220 | 4.3768 | 0.7110 | candidate_only |
| baseline | validation | 13 | 122 | sufficient_sample | 8.0158 | 7.5430 | 14.7099 | 0.7623 | 8.0158 | 0.7623 | 3.9409 | 7.8000 | 0.7623 | 7.4770 | 0.7623 | baseline_only |
| candidate | holdout | 13 | 6789 | sufficient_sample | 3.8632 | 2.9272 | 12.1356 | 0.6153 | 3.8632 | 0.6153 | 3.8538 | 3.6556 | 0.6076 | 3.3451 | 0.5945 | baseline_and_candidate |
| baseline | holdout | 13 | 6789 | sufficient_sample | 3.8632 | 2.9272 | 12.1356 | 0.6153 | 3.8632 | 0.6153 | 3.8538 | 3.6556 | 0.6076 | 3.3451 | 0.5945 | baseline_and_candidate |
| candidate | holdout | 13 | 966 | sufficient_sample | 2.9107 | 2.8487 | 13.4952 | 0.6004 | 2.9107 | 0.6004 | 3.3987 | 2.7051 | 0.5952 | 2.3975 | 0.5839 | candidate_only |
| baseline | holdout | 13 | 215 | sufficient_sample | 3.6286 | 2.7936 | 12.2642 | 0.6279 | 3.6286 | 0.6279 | 4.5651 | 3.4215 | 0.6186 | 3.1117 | 0.6093 | baseline_only |
| candidate | development | 26 | 10398 | sufficient_sample | 6.9353 | 6.5411 | 13.5726 | 0.7298 | 6.9353 | 0.7298 | 6.0563 | 6.7216 | 0.7251 | 6.4019 | 0.7172 | baseline_and_candidate |
| baseline | development | 26 | 10398 | sufficient_sample | 6.9353 | 6.5411 | 13.5726 | 0.7298 | 6.9353 | 0.7298 | 6.0563 | 6.7216 | 0.7251 | 6.4019 | 0.7172 | baseline_and_candidate |
| candidate | development | 26 | 1619 | sufficient_sample | 9.9667 | 10.1199 | 13.8244 | 0.7746 | 9.9667 | 0.7746 | 9.1017 | 9.7470 | 0.7696 | 9.4182 | 0.7665 | candidate_only |
| baseline | development | 26 | 201 | sufficient_sample | 6.3935 | 8.0702 | 17.0210 | 0.6915 | 6.3935 | 0.6915 | 4.3293 | 6.1809 | 0.6915 | 5.8629 | 0.6915 | baseline_only |
| candidate | validation | 26 | 5391 | sufficient_sample | 6.7074 | 6.0702 | 16.6135 | 0.6717 | 6.7074 | 0.6717 | 5.5086 | 6.4942 | 0.6678 | 6.1752 | 0.6578 | baseline_and_candidate |
| baseline | validation | 26 | 5391 | sufficient_sample | 6.7074 | 6.0702 | 16.6135 | 0.6717 | 6.7074 | 0.6717 | 5.5086 | 6.4942 | 0.6678 | 6.1752 | 0.6578 | baseline_and_candidate |
| candidate | validation | 26 | 867 | sufficient_sample | 10.1775 | 9.0240 | 17.6933 | 0.7693 | 10.1775 | 0.7693 | 10.6490 | 9.9573 | 0.7636 | 9.6280 | 0.7543 | candidate_only |
| baseline | validation | 26 | 119 | sufficient_sample | 13.8848 | 7.6949 | 21.8343 | 0.7227 | 13.8848 | 0.7227 | 6.2452 | 13.6573 | 0.7143 | 13.3168 | 0.6975 | baseline_only |
| candidate | holdout | 26 | 6366 | sufficient_sample | 7.1886 | 5.9518 | 17.8038 | 0.6687 | 7.1886 | 0.6687 | 6.7287 | 6.9745 | 0.6618 | 6.6540 | 0.6527 | baseline_and_candidate |
| baseline | holdout | 26 | 6366 | sufficient_sample | 7.1886 | 5.9518 | 17.8038 | 0.6687 | 7.1886 | 0.6687 | 6.7287 | 6.9745 | 0.6618 | 6.6540 | 0.6527 | baseline_and_candidate |
| candidate | holdout | 26 | 921 | sufficient_sample | 5.4132 | 3.3443 | 20.7472 | 0.5841 | 5.4132 | 0.5841 | 6.9150 | 5.2026 | 0.5776 | 4.8875 | 0.5700 | candidate_only |
| baseline | holdout | 26 | 213 | sufficient_sample | 7.6769 | 5.1975 | 20.9475 | 0.6479 | 7.6769 | 0.6479 | 8.5193 | 7.4618 | 0.6385 | 7.1399 | 0.6291 | baseline_only |

## score_buckets

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | score_bucket |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 4687 | sufficient_sample | 3.4358 | 3.1719 | 10.0203 | 0.6477 | 3.4358 | 0.6477 | 3.0052 | 3.2291 | 0.6399 | 2.9199 | 0.6247 | 40-59 |
| candidate | development | 13 | 7021 | sufficient_sample | 3.8129 | 3.6556 | 9.9719 | 0.6744 | 3.8129 | 0.6744 | 3.2589 | 3.6055 | 0.6647 | 3.2952 | 0.6528 | 60-79 |
| candidate | development | 13 | 819 | sufficient_sample | 2.7900 | 3.3225 | 9.1321 | 0.6825 | 2.7900 | 0.6825 | 2.8053 | 2.5846 | 0.6728 | 2.2774 | 0.6557 | 80-100 |
| candidate | validation | 13 | 2945 | sufficient_sample | 3.3921 | 4.1066 | 11.9829 | 0.6710 | 3.3921 | 0.6710 | 2.7605 | 3.1856 | 0.6652 | 2.8765 | 0.6533 | 40-59 |
| candidate | validation | 13 | 3449 | sufficient_sample | 3.6179 | 4.0321 | 12.0932 | 0.6651 | 3.6179 | 0.6651 | 3.1548 | 3.4109 | 0.6570 | 3.1011 | 0.6457 | 60-79 |
| candidate | validation | 13 | 277 | sufficient_sample | 3.6244 | 2.9315 | 12.1138 | 0.6498 | 3.6244 | 0.6498 | 4.6148 | 3.4173 | 0.6354 | 3.1075 | 0.6173 | 80-100 |
| candidate | holdout | 13 | 3597 | sufficient_sample | 4.1883 | 3.1332 | 12.5344 | 0.6239 | 4.1883 | 0.6239 | 3.6967 | 3.9801 | 0.6163 | 3.6686 | 0.6024 | 40-59 |
| candidate | holdout | 13 | 3775 | sufficient_sample | 3.3941 | 2.8487 | 12.1522 | 0.6066 | 3.3941 | 0.6066 | 3.8654 | 3.1875 | 0.5995 | 2.8784 | 0.5873 | 60-79 |
| candidate | holdout | 13 | 383 | sufficient_sample | 3.0309 | 2.0161 | 11.7137 | 0.5822 | 3.0309 | 0.5822 | 4.0679 | 2.8251 | 0.5744 | 2.5171 | 0.5640 | 80-100 |
| candidate | development | 26 | 4449 | sufficient_sample | 7.1205 | 6.6348 | 14.1034 | 0.7175 | 7.1205 | 0.7175 | 6.4604 | 6.9065 | 0.7123 | 6.5862 | 0.7060 | 40-59 |
| candidate | development | 26 | 6750 | sufficient_sample | 7.4065 | 7.1449 | 13.5191 | 0.7409 | 7.4065 | 0.7409 | 6.4259 | 7.1919 | 0.7364 | 6.8708 | 0.7283 | 60-79 |
| candidate | development | 26 | 818 | sufficient_sample | 8.0393 | 7.4007 | 12.0368 | 0.7934 | 8.0393 | 0.7934 | 6.8372 | 7.8235 | 0.7897 | 7.5005 | 0.7836 | 80-100 |
| candidate | validation | 26 | 2816 | sufficient_sample | 7.4611 | 6.8367 | 16.3795 | 0.6999 | 7.4611 | 0.6999 | 6.2436 | 7.2464 | 0.6964 | 6.9251 | 0.6861 | 40-59 |
| candidate | validation | 26 | 3171 | sufficient_sample | 6.7075 | 6.0729 | 17.0574 | 0.6673 | 6.7075 | 0.6673 | 5.9651 | 6.4943 | 0.6623 | 6.1753 | 0.6522 | 60-79 |
| candidate | validation | 26 | 271 | sufficient_sample | 9.9766 | 9.2495 | 17.9374 | 0.7417 | 9.9766 | 0.7417 | 8.9753 | 9.7568 | 0.7417 | 9.4280 | 0.7380 | 80-100 |
| candidate | holdout | 26 | 3443 | sufficient_sample | 7.6734 | 6.5283 | 17.6534 | 0.6904 | 7.6734 | 0.6904 | 6.7435 | 7.4582 | 0.6823 | 7.1363 | 0.6744 | 40-59 |
| candidate | holdout | 26 | 3477 | sufficient_sample | 6.4847 | 4.6800 | 18.7738 | 0.6347 | 6.4847 | 0.6347 | 6.8247 | 6.2719 | 0.6293 | 5.9536 | 0.6198 | 60-79 |
| candidate | holdout | 26 | 367 | sufficient_sample | 4.8544 | 3.2947 | 17.6408 | 0.5749 | 4.8544 | 0.5749 | 6.1489 | 4.6449 | 0.5668 | 4.3315 | 0.5531 | 80-100 |

## ticker_summary

| rule | split | horizon_weeks | count | sample_status | mean_gross_return_pct | median_gross_return_pct | std_gross_return_pct | win_rate | mean_net_return_pct_0bps | win_rate_net_0bps | mean_spy_return_pct | mean_net_return_pct_10bps | win_rate_net_10bps | mean_net_return_pct_25bps | win_rate_net_25bps | ticker | cohort |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | development | 13 | 19 | insufficient_sample | 5.3608 | 5.3457 | 11.6407 | 0.6316 | 5.3608 | 0.6316 | 2.5715 | 5.1503 | 0.6316 | 4.8353 | 0.6316 | AAPL | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 2.6404 | 2.7710 | 10.4736 | 0.7857 | 2.6404 | 0.7857 | 2.2470 | 2.4354 | 0.7857 | 2.1285 | 0.7857 | AAPL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 11.1846 | 9.8335 | 20.6966 | 0.8462 | 11.1846 | 0.8462 | 3.5720 | 10.9625 | 0.8462 | 10.6301 | 0.8462 | AAPL | stock |
| candidate | development | 13 | 22 | sufficient_sample | 5.2343 | 7.8577 | 14.7796 | 0.5909 | 5.2343 | 0.5909 | 1.9628 | 5.0241 | 0.5909 | 4.7095 | 0.5909 | AAPL | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1102 | 2.4163 | 9.4171 | 0.7500 | 4.1102 | 0.7500 | 4.1334 | 3.9021 | 0.7500 | 3.5909 | 0.7500 | AAPL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 9.3004 | 9.8335 | 19.8162 | 0.7692 | 9.3004 | 0.7692 | 3.5093 | 9.0820 | 0.7692 | 8.7552 | 0.7692 | AAPL | stock |
| baseline | development | 13 | 22 | sufficient_sample | 8.3693 | 9.6507 | 15.1433 | 0.7727 | 8.3693 | 0.7727 | 2.8096 | 8.1527 | 0.7727 | 7.8288 | 0.7727 | AMZN | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 5.0451 | 4.9748 | 12.4992 | 0.7692 | 5.0451 | 0.7692 | 4.7921 | 4.8352 | 0.7692 | 4.5212 | 0.7692 | AMZN | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 9.6410 | 11.5476 | 16.8958 | 0.7500 | 9.6410 | 0.7500 | 1.5510 | 9.4220 | 0.7500 | 9.0942 | 0.7500 | AMZN | stock |
| candidate | development | 13 | 23 | sufficient_sample | 7.3608 | 7.8337 | 14.1907 | 0.7826 | 7.3608 | 0.7826 | 3.1785 | 7.1463 | 0.7826 | 6.8254 | 0.7826 | AMZN | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.7117 | 5.4295 | 17.0971 | 0.6000 | 0.7117 | 0.6000 | 3.1311 | 0.5105 | 0.6000 | 0.2094 | 0.6000 | AMZN | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 12.4997 | 12.2551 | 19.2826 | 0.7692 | 12.4997 | 0.7692 | 5.7010 | 12.2749 | 0.7692 | 11.9386 | 0.7692 | AMZN | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.1554 | 2.2916 | 11.7515 | 0.5714 | 3.1554 | 0.5714 | 3.0340 | 2.9493 | 0.5714 | 2.6409 | 0.5714 | BA | stock |
| baseline | holdout | 13 | 11 | insufficient_sample | 1.7311 | -2.7004 | 15.6591 | 0.2727 | 1.7311 | 0.2727 | 5.3562 | 1.5278 | 0.2727 | 1.2237 | 0.2727 | BA | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 9.6355 | 9.7830 | 15.0200 | 0.8000 | 9.6355 | 0.8000 | 3.9438 | 9.4164 | 0.8000 | 9.0887 | 0.8000 | BA | stock |
| candidate | development | 13 | 23 | sufficient_sample | 4.8284 | 2.8786 | 13.2586 | 0.5652 | 4.8284 | 0.5652 | 3.1156 | 4.6190 | 0.5652 | 4.3056 | 0.5652 | BA | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | 0.1631 | -3.5109 | 12.7524 | 0.3077 | 0.1631 | 0.3077 | 4.6860 | -0.0370 | 0.3077 | -0.3365 | 0.3077 | BA | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -1.5088 | 1.8575 | 23.9467 | 0.6667 | -1.5088 | 0.6667 | 1.8377 | -1.7055 | 0.5833 | -2.0000 | 0.5833 | BA | stock |
| baseline | development | 13 | 17 | insufficient_sample | 2.9601 | 0.2547 | 14.9456 | 0.5294 | 2.9601 | 0.5294 | 1.9852 | 2.7543 | 0.5294 | 2.4465 | 0.4118 | BAC | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 1.3006 | 3.6903 | 15.4136 | 0.5333 | 1.3006 | 0.5333 | 2.7447 | 1.0982 | 0.5333 | 0.7953 | 0.5333 | BAC | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 0.8939 | 4.5005 | 16.7626 | 0.6000 | 0.8939 | 0.6000 | 2.7965 | 0.6923 | 0.6000 | 0.3907 | 0.6000 | BAC | stock |
| candidate | development | 13 | 18 | insufficient_sample | 1.7363 | 5.6272 | 13.8406 | 0.6667 | 1.7363 | 0.6667 | 1.6755 | 1.5331 | 0.6667 | 1.2289 | 0.6667 | BAC | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 2.0688 | 1.7861 | 15.9452 | 0.5333 | 2.0688 | 0.5333 | 2.6364 | 1.8649 | 0.5333 | 1.5598 | 0.5333 | BAC | stock |
| candidate | validation | 13 | 13 | insufficient_sample | -0.0045 | 3.7389 | 15.5092 | 0.5385 | -0.0045 | 0.5385 | 3.1302 | -0.2043 | 0.5385 | -0.5032 | 0.5385 | BAC | stock |
| baseline | development | 13 | 17 | insufficient_sample | 0.8624 | 1.8109 | 12.1461 | 0.5294 | 0.8624 | 0.5294 | 3.2165 | 0.6608 | 0.5294 | 0.3593 | 0.5294 | CAT | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 6.6907 | 3.1749 | 14.8131 | 0.6429 | 6.6907 | 0.6429 | 5.1389 | 6.4775 | 0.6429 | 6.1586 | 0.6429 | CAT | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.3763 | 7.1351 | 13.3190 | 0.6923 | 5.3763 | 0.6923 | 2.8012 | 5.1657 | 0.6923 | 4.8507 | 0.6923 | CAT | stock |
| candidate | development | 13 | 20 | sufficient_sample | 1.5105 | 0.9893 | 13.9384 | 0.5500 | 1.5105 | 0.5500 | 2.5939 | 1.3077 | 0.5000 | 1.0042 | 0.5000 | CAT | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 7.1644 | 4.5870 | 14.2701 | 0.6667 | 7.1644 | 0.6667 | 4.5843 | 6.9503 | 0.6667 | 6.6299 | 0.6667 | CAT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 5.5200 | 7.5453 | 13.5388 | 0.7692 | 5.5200 | 0.7692 | 2.5694 | 5.3092 | 0.7692 | 4.9937 | 0.7692 | CAT | stock |
| baseline | development | 13 | 22 | sufficient_sample | 5.1304 | 3.8003 | 7.1701 | 0.7727 | 5.1304 | 0.7727 | 3.8524 | 4.9204 | 0.7273 | 4.6061 | 0.6818 | COST | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 4.9813 | 3.3573 | 10.3037 | 0.6250 | 4.9813 | 0.6250 | 3.7871 | 4.7716 | 0.6250 | 4.4577 | 0.6250 | COST | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.6239 | 5.3375 | 7.7615 | 0.7692 | 5.6239 | 0.7692 | 3.2482 | 5.4128 | 0.7692 | 5.0971 | 0.7692 | COST | stock |
| candidate | development | 13 | 23 | sufficient_sample | 5.1719 | 4.3581 | 6.5582 | 0.8696 | 5.1719 | 0.8696 | 2.8848 | 4.9618 | 0.8696 | 4.6474 | 0.8261 | COST | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 5.9182 | 4.0749 | 9.5575 | 0.6250 | 5.9182 | 0.6250 | 4.5551 | 5.7066 | 0.6250 | 5.3899 | 0.6250 | COST | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.0401 | 9.8453 | 9.0715 | 0.7692 | 6.0401 | 0.7692 | 4.0262 | 5.8282 | 0.7692 | 5.5112 | 0.7692 | COST | stock |
| baseline | development | 13 | 18 | insufficient_sample | 0.9172 | 0.3289 | 11.7961 | 0.5000 | 0.9172 | 0.5000 | 2.9058 | 0.7155 | 0.5000 | 0.4138 | 0.5000 | CSCO | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.2888 | 3.2806 | 10.0930 | 0.7143 | 3.2888 | 0.7143 | 3.2932 | 3.0825 | 0.7143 | 2.7737 | 0.7143 | CSCO | stock |
| baseline | validation | 13 | 10 | insufficient_sample | 5.5753 | 2.9072 | 11.7595 | 0.5000 | 5.5753 | 0.5000 | 4.3965 | 5.3644 | 0.5000 | 5.0488 | 0.5000 | CSCO | stock |
| candidate | development | 13 | 22 | sufficient_sample | 1.1613 | 3.4006 | 10.9504 | 0.6364 | 1.1613 | 0.6364 | 2.7326 | 0.9592 | 0.5909 | 0.6568 | 0.5909 | CSCO | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 4.5536 | 3.9203 | 10.1902 | 0.8000 | 4.5536 | 0.8000 | 3.2856 | 4.3447 | 0.8000 | 4.0322 | 0.8000 | CSCO | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.6533 | -2.0300 | 14.0590 | 0.4615 | 2.6533 | 0.4615 | 2.3972 | 2.4482 | 0.4615 | 2.1414 | 0.4615 | CSCO | stock |
| baseline | development | 13 | 19 | insufficient_sample | 2.8921 | 1.6874 | 8.8985 | 0.6316 | 2.8921 | 0.6316 | 2.6794 | 2.6865 | 0.5789 | 2.3789 | 0.5789 | CVX | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.8453 | 4.4742 | 11.4853 | 0.6429 | 3.8453 | 0.6429 | 3.0362 | 3.6378 | 0.6429 | 3.3273 | 0.6429 | CVX | stock |
| baseline | validation | 13 | 11 | insufficient_sample | -2.4515 | -1.6711 | 10.1918 | 0.4545 | -2.4515 | 0.4545 | 1.3625 | -2.6464 | 0.4545 | -2.9380 | 0.3636 | CVX | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.5029 | 0.9338 | 10.9491 | 0.6087 | 2.5029 | 0.6087 | 2.9552 | 2.2981 | 0.6087 | 1.9916 | 0.5652 | CVX | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 4.3145 | 2.1137 | 10.9201 | 0.5882 | 4.3145 | 0.5882 | 3.6687 | 4.1061 | 0.5882 | 3.7943 | 0.5882 | CVX | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -3.0125 | 1.0768 | 15.1346 | 0.5000 | -3.0125 | 0.5000 | 1.4463 | -3.2063 | 0.5000 | -3.4962 | 0.5000 | CVX | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.1280 | 3.0628 | 5.0946 | 0.6818 | 2.1280 | 0.6818 | 2.5096 | 1.9240 | 0.6818 | 1.6187 | 0.6818 | DIA | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 2.3940 | 3.0246 | 6.4261 | 0.7500 | 2.3940 | 0.7500 | 2.5514 | 2.1894 | 0.7500 | 1.8833 | 0.6875 | DIA | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.5694 | 4.4065 | 10.9669 | 0.8462 | 1.5694 | 0.8462 | 1.9042 | 1.3664 | 0.8462 | 1.0628 | 0.8462 | DIA | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.9505 | 4.4875 | 5.7978 | 0.6250 | 2.9505 | 0.6250 | 3.0558 | 2.7448 | 0.6250 | 2.4370 | 0.6250 | DIA | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 2.1942 | 2.3209 | 6.0877 | 0.6875 | 2.1942 | 0.6875 | 2.6874 | 1.9900 | 0.6875 | 1.6845 | 0.6875 | DIA | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.7395 | 2.9244 | 8.5677 | 0.8462 | 1.7395 | 0.8462 | 2.2314 | 1.5363 | 0.8462 | 1.2321 | 0.8462 | DIA | etf |
| baseline | development | 13 | 21 | sufficient_sample | 4.3500 | 7.2543 | 10.8255 | 0.6667 | 4.3500 | 0.6667 | 2.4925 | 4.1415 | 0.6667 | 3.8296 | 0.6667 | DIS | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -1.8183 | -3.4472 | 7.0947 | 0.2000 | -1.8183 | 0.2000 | 6.5317 | -2.0144 | 0.2000 | -2.3080 | 0.2000 | DIS | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 1.6835 | 0.0335 | 9.2541 | 0.5000 | 1.6835 | 0.5000 | 3.6718 | 1.4803 | 0.5000 | 1.1763 | 0.5000 | DIS | stock |
| candidate | development | 13 | 22 | sufficient_sample | 4.4391 | 7.3039 | 10.9612 | 0.6818 | 4.4391 | 0.6818 | 2.3530 | 4.2304 | 0.6818 | 3.9182 | 0.6818 | DIS | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -1.4840 | -4.8585 | 12.0696 | 0.3846 | -1.4840 | 0.3846 | 4.8893 | -1.6808 | 0.3077 | -1.9754 | 0.3077 | DIS | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 4.8996 | 4.5376 | 13.2725 | 0.6923 | 4.8996 | 0.6923 | 3.6095 | 4.6900 | 0.6923 | 4.3764 | 0.6923 | DIS | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.5176 | 0.7537 | 9.4935 | 0.5714 | 3.5176 | 0.5714 | 2.9327 | 3.3108 | 0.5714 | 3.0013 | 0.5238 | GOOGL | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 9.7660 | 13.6771 | 17.3043 | 0.6667 | 9.7660 | 0.6667 | 3.1321 | 9.5467 | 0.6667 | 9.2185 | 0.6667 | GOOGL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 5.0811 | 7.9796 | 8.4463 | 0.7692 | 5.0811 | 0.7692 | 3.3428 | 4.8711 | 0.7692 | 4.5570 | 0.7692 | GOOGL | stock |
| candidate | development | 13 | 23 | sufficient_sample | 4.2679 | 0.7537 | 9.5322 | 0.5217 | 4.2679 | 0.5217 | 2.9405 | 4.0596 | 0.5217 | 3.7479 | 0.5217 | GOOGL | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 8.5477 | 9.3683 | 15.3016 | 0.7333 | 8.5477 | 0.7333 | 3.7373 | 8.3308 | 0.7333 | 8.0063 | 0.7333 | GOOGL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.5994 | 6.7966 | 8.6086 | 0.8462 | 6.5994 | 0.8462 | 3.8496 | 6.3865 | 0.8462 | 6.0678 | 0.8462 | GOOGL | stock |
| baseline | development | 13 | 16 | insufficient_sample | 5.3658 | 4.1646 | 11.8947 | 0.6875 | 5.3658 | 0.6875 | 3.9226 | 5.1553 | 0.6875 | 4.8403 | 0.6875 | GS | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.5687 | 8.8498 | 11.5097 | 0.7333 | 7.5687 | 0.7333 | 3.7429 | 7.3538 | 0.7333 | 7.0322 | 0.7333 | GS | stock |
| baseline | validation | 13 | 10 | insufficient_sample | -0.5274 | 0.2114 | 7.6256 | 0.5000 | -0.5274 | 0.5000 | 3.8243 | -0.7261 | 0.5000 | -1.0235 | 0.5000 | GS | stock |
| candidate | development | 13 | 20 | sufficient_sample | -0.4545 | -0.3926 | 10.4953 | 0.5000 | -0.4545 | 0.5000 | 2.0917 | -0.6534 | 0.4500 | -0.9510 | 0.4500 | GS | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 8.0212 | 5.7153 | 13.9441 | 0.6667 | 8.0212 | 0.6667 | 5.3895 | 7.8054 | 0.6667 | 7.4825 | 0.6667 | GS | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -0.9118 | -1.7557 | 7.0154 | 0.4167 | -0.9118 | 0.4167 | 3.1742 | -1.1097 | 0.4167 | -1.4060 | 0.4167 | GS | stock |
| baseline | development | 13 | 22 | sufficient_sample | 7.4238 | 11.2858 | 10.8954 | 0.7727 | 7.4238 | 0.7727 | 2.8996 | 7.2091 | 0.7273 | 6.8880 | 0.7273 | HD | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 3.1759 | 1.6212 | 13.8666 | 0.5385 | 3.1759 | 0.5385 | 4.1079 | 2.9697 | 0.5385 | 2.6613 | 0.5385 | HD | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 4.4059 | 7.3081 | 12.9323 | 0.6154 | 4.4059 | 0.6154 | 3.0046 | 4.1973 | 0.6154 | 3.8852 | 0.6154 | HD | stock |
| candidate | development | 13 | 24 | sufficient_sample | 6.7538 | 5.7546 | 9.5522 | 0.8333 | 6.7538 | 0.8333 | 3.4447 | 6.5405 | 0.7917 | 6.2214 | 0.7917 | HD | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 3.6084 | 4.5903 | 11.5965 | 0.7333 | 3.6084 | 0.7333 | 2.9198 | 3.4014 | 0.7333 | 3.0916 | 0.7333 | HD | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 5.1823 | 8.0158 | 14.5106 | 0.6923 | 5.1823 | 0.6923 | 2.9046 | 4.9722 | 0.6923 | 4.6577 | 0.6923 | HD | stock |
| baseline | development | 13 | 24 | sufficient_sample | 3.5114 | 2.9780 | 8.8329 | 0.7500 | 3.5114 | 0.7500 | 2.3265 | 3.3046 | 0.7500 | 2.9952 | 0.7500 | HON | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 1.6937 | 4.0748 | 6.8999 | 0.6154 | 1.6937 | 0.6154 | 5.1278 | 1.4905 | 0.6154 | 1.1865 | 0.6154 | HON | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 2.9298 | 4.4567 | 15.2570 | 0.7692 | 2.9298 | 0.7692 | 1.9042 | 2.7242 | 0.7692 | 2.4165 | 0.7692 | HON | stock |
| candidate | development | 13 | 24 | sufficient_sample | 4.1745 | 3.4651 | 9.1392 | 0.7917 | 4.1745 | 0.7917 | 2.6231 | 3.9664 | 0.7917 | 3.6550 | 0.7500 | HON | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.8423 | 1.9705 | 9.5139 | 0.5333 | 0.8423 | 0.5333 | 3.2565 | 0.6408 | 0.5333 | 0.3394 | 0.5333 | HON | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 6.3621 | 6.2549 | 11.5113 | 0.7692 | 6.3621 | 0.7692 | 4.2628 | 6.1495 | 0.7692 | 5.8316 | 0.7692 | HON | stock |
| baseline | development | 13 | 18 | insufficient_sample | 1.2549 | 0.1744 | 7.1514 | 0.5556 | 1.2549 | 0.5556 | 2.8464 | 1.0526 | 0.5000 | 0.7499 | 0.3889 | IBM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 5.1271 | 5.8032 | 8.9344 | 0.6667 | 5.1271 | 0.6667 | 2.9877 | 4.9170 | 0.6000 | 4.6027 | 0.6000 | IBM | stock |
| baseline | validation | 13 | 9 | insufficient_sample | -4.8475 | -3.4105 | 8.0094 | 0.3333 | -4.8475 | 0.3333 | 0.7420 | -5.0376 | 0.3333 | -5.3220 | 0.3333 | IBM | stock |
| candidate | development | 13 | 21 | sufficient_sample | 2.1886 | 2.0977 | 8.4054 | 0.6190 | 2.1886 | 0.6190 | 3.1078 | 1.9844 | 0.5714 | 1.6789 | 0.5714 | IBM | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 5.4204 | 5.0696 | 10.8438 | 0.6471 | 5.4204 | 0.6471 | 3.5550 | 5.2098 | 0.5882 | 4.8946 | 0.5882 | IBM | stock |
| candidate | validation | 13 | 11 | insufficient_sample | -0.9318 | 0.8264 | 9.0436 | 0.6364 | -0.9318 | 0.6364 | 3.0170 | -1.1298 | 0.6364 | -1.4259 | 0.6364 | IBM | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.0828 | 1.5397 | 8.2886 | 0.6190 | 2.0828 | 0.6190 | 2.1732 | 1.8789 | 0.6190 | 1.5737 | 0.6190 | IWM | etf |
| baseline | holdout | 13 | 13 | insufficient_sample | 2.2399 | 2.7929 | 7.7281 | 0.6154 | 2.2399 | 0.6154 | 4.2444 | 2.0356 | 0.6154 | 1.7300 | 0.6154 | IWM | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.0526 | 2.4238 | 13.7217 | 0.6154 | 1.0526 | 0.6154 | 2.7572 | 0.8507 | 0.6154 | 0.5486 | 0.6154 | IWM | etf |
| candidate | development | 13 | 23 | sufficient_sample | 2.0129 | 4.2558 | 8.7471 | 0.5217 | 2.0129 | 0.5217 | 2.1040 | 1.8091 | 0.5217 | 1.5041 | 0.5217 | IWM | etf |
| candidate | holdout | 13 | 15 | insufficient_sample | 0.6350 | 2.6230 | 8.7868 | 0.6000 | 0.6350 | 0.6000 | 3.2886 | 0.4339 | 0.6000 | 0.1331 | 0.5333 | IWM | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.4704 | 3.9012 | 14.8012 | 0.6923 | 1.4704 | 0.6923 | 3.1641 | 1.2677 | 0.6923 | 0.9643 | 0.6923 | IWM | etf |
| baseline | development | 13 | 22 | sufficient_sample | 2.8273 | 1.5137 | 6.3849 | 0.6364 | 2.8273 | 0.6364 | 3.5407 | 2.6219 | 0.6364 | 2.3145 | 0.5909 | JNJ | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 1.4170 | 1.7025 | 7.3780 | 0.5625 | 1.4170 | 0.5625 | 2.9124 | 1.2143 | 0.5625 | 0.9111 | 0.5625 | JNJ | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.2276 | 2.7347 | 5.4751 | 0.5833 | 2.2276 | 0.5833 | 3.5679 | 2.0233 | 0.5833 | 1.7177 | 0.5833 | JNJ | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.1386 | 1.1853 | 6.3978 | 0.6522 | 3.1386 | 0.6522 | 2.9824 | 2.9326 | 0.6522 | 2.6242 | 0.6522 | JNJ | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.2804 | 0.6927 | 7.4135 | 0.5000 | 1.2804 | 0.5000 | 3.4070 | 1.0780 | 0.5000 | 0.7752 | 0.5000 | JNJ | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 1.8379 | 0.5782 | 5.4307 | 0.5385 | 1.8379 | 0.5385 | 3.6260 | 1.6345 | 0.5385 | 1.3300 | 0.5385 | JNJ | stock |
| baseline | development | 13 | 20 | sufficient_sample | 4.0092 | 2.9191 | 10.2926 | 0.7000 | 4.0092 | 0.7000 | 2.7584 | 3.8014 | 0.7000 | 3.4904 | 0.6500 | JPM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.6598 | 6.5677 | 8.9240 | 0.8000 | 7.6598 | 0.8000 | 5.1325 | 7.4447 | 0.8000 | 7.1229 | 0.8000 | JPM | stock |
| baseline | validation | 13 | 11 | insufficient_sample | 2.2590 | 4.4627 | 11.2878 | 0.6364 | 2.2590 | 0.6364 | 2.4399 | 2.0547 | 0.6364 | 1.7490 | 0.6364 | JPM | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.0716 | 2.2840 | 9.6372 | 0.6087 | 3.0716 | 0.6087 | 2.8502 | 2.8656 | 0.6087 | 2.5575 | 0.6087 | JPM | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.9788 | 5.2783 | 11.2691 | 0.6250 | 4.9788 | 0.6250 | 3.7610 | 4.7691 | 0.6250 | 4.4552 | 0.6250 | JPM | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 3.0737 | 2.0633 | 10.9369 | 0.5000 | 3.0737 | 0.5000 | 4.0093 | 2.8677 | 0.5000 | 2.5596 | 0.5000 | JPM | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.2491 | 3.0122 | 4.6208 | 0.6818 | 2.2491 | 0.6818 | 2.3531 | 2.0448 | 0.6818 | 1.7391 | 0.6364 | KO | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 2.3248 | 0.1292 | 6.4444 | 0.5333 | 2.3248 | 0.5333 | 3.1399 | 2.1204 | 0.4667 | 1.8145 | 0.4000 | KO | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.4435 | 2.2333 | 5.7330 | 0.7500 | 2.4435 | 0.7500 | 3.2083 | 2.2388 | 0.7500 | 1.9326 | 0.7500 | KO | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.5999 | 2.9189 | 4.1877 | 0.8261 | 2.5999 | 0.8261 | 2.8914 | 2.3949 | 0.8261 | 2.0882 | 0.6957 | KO | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 3.0838 | 1.1110 | 6.8339 | 0.6250 | 3.0838 | 0.6250 | 3.8390 | 2.8779 | 0.6250 | 2.5697 | 0.5625 | KO | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.0210 | 1.7626 | 4.9398 | 0.7692 | 2.0210 | 0.7692 | 3.6240 | 1.8172 | 0.7692 | 1.5122 | 0.7692 | KO | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.1482 | -0.8177 | 8.3342 | 0.4545 | 3.1482 | 0.4545 | 3.0897 | 2.9421 | 0.4545 | 2.6337 | 0.4545 | MCD | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 3.2242 | 3.1823 | 4.4958 | 0.8000 | 3.2242 | 0.8000 | 4.2506 | 3.0180 | 0.7333 | 2.7094 | 0.5333 | MCD | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 5.0642 | 5.4550 | 7.6903 | 0.6667 | 5.0642 | 0.6667 | 2.6666 | 4.8543 | 0.6667 | 4.5402 | 0.6667 | MCD | stock |
| candidate | development | 13 | 24 | sufficient_sample | 3.2742 | 3.3481 | 6.7206 | 0.6667 | 3.2742 | 0.6667 | 3.0676 | 3.0678 | 0.6667 | 2.7591 | 0.6250 | MCD | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 2.4107 | 3.0848 | 5.9099 | 0.6875 | 2.4107 | 0.6875 | 4.1786 | 2.2061 | 0.6875 | 1.8999 | 0.5625 | MCD | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 6.4858 | 6.5779 | 6.0675 | 0.7500 | 6.4858 | 0.7500 | 3.4308 | 6.2731 | 0.7500 | 5.9547 | 0.7500 | MCD | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.3763 | 2.8782 | 7.6845 | 0.5909 | 3.3763 | 0.5909 | 3.0545 | 3.1698 | 0.5909 | 2.8607 | 0.5909 | MMM | stock |
| baseline | holdout | 13 | 12 | insufficient_sample | 3.3535 | 1.5290 | 14.2554 | 0.5000 | 3.3535 | 0.5000 | 5.1533 | 3.1470 | 0.5000 | 2.8380 | 0.5000 | MMM | stock |
| baseline | validation | 13 | 10 | insufficient_sample | -2.9009 | 2.2243 | 10.7605 | 0.6000 | -2.9009 | 0.6000 | 1.2832 | -3.0949 | 0.6000 | -3.3852 | 0.5000 | MMM | stock |
| candidate | development | 13 | 24 | sufficient_sample | 3.6196 | 3.6897 | 7.5523 | 0.5833 | 3.6196 | 0.5833 | 3.2694 | 3.4125 | 0.5833 | 3.1028 | 0.5833 | MMM | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | 3.5838 | 2.9354 | 13.8631 | 0.5385 | 3.5838 | 0.5385 | 3.6398 | 3.3769 | 0.5385 | 3.0672 | 0.5385 | MMM | stock |
| candidate | validation | 13 | 12 | insufficient_sample | -1.9568 | 2.6411 | 10.8920 | 0.5833 | -1.9568 | 0.5833 | 1.5310 | -2.1527 | 0.5833 | -2.4458 | 0.5833 | MMM | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.2578 | 1.5887 | 7.5198 | 0.6190 | 3.2578 | 0.6190 | 3.7888 | 3.0515 | 0.6190 | 2.7428 | 0.6190 | MRK | stock |
| baseline | holdout | 13 | 13 | insufficient_sample | 4.0377 | 1.6241 | 10.4762 | 0.7692 | 4.0377 | 0.7692 | 4.1398 | 3.8298 | 0.7692 | 3.5188 | 0.6923 | MRK | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 2.3736 | 2.3669 | 7.9699 | 0.6667 | 2.3736 | 0.6667 | 2.5652 | 2.1691 | 0.6667 | 1.8630 | 0.6667 | MRK | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.3455 | 0.9159 | 8.2444 | 0.5652 | 2.3455 | 0.5652 | 2.8272 | 2.1410 | 0.5217 | 1.8351 | 0.5217 | MRK | stock |
| candidate | holdout | 13 | 14 | insufficient_sample | 2.5635 | 1.0163 | 12.5318 | 0.5714 | 2.5635 | 0.5714 | 3.8394 | 2.3585 | 0.5714 | 2.0519 | 0.5000 | MRK | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.3086 | 2.8513 | 8.0102 | 0.6154 | 2.3086 | 0.6154 | 3.6230 | 2.1042 | 0.6154 | 1.7983 | 0.6154 | MRK | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.1091 | 1.5860 | 9.4159 | 0.6667 | 2.1091 | 0.6667 | 1.6171 | 1.9051 | 0.6667 | 1.5998 | 0.6190 | MSFT | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 4.2327 | 9.1370 | 13.4566 | 0.6000 | 4.2327 | 0.6000 | 2.9409 | 4.0244 | 0.6000 | 3.7128 | 0.6000 | MSFT | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 11.5720 | 9.3597 | 11.0305 | 0.9231 | 11.5720 | 0.9231 | 5.5391 | 11.3490 | 0.9231 | 11.0155 | 0.9231 | MSFT | stock |
| candidate | development | 13 | 22 | sufficient_sample | 3.7253 | 3.2785 | 10.6559 | 0.7273 | 3.7253 | 0.7273 | 2.6405 | 3.5181 | 0.7273 | 3.2080 | 0.6818 | MSFT | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1681 | 1.3988 | 14.1060 | 0.6875 | 4.1681 | 0.6875 | 3.5358 | 3.9600 | 0.6875 | 3.6486 | 0.5625 | MSFT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 10.3417 | 9.7756 | 8.4491 | 0.9231 | 10.3417 | 0.9231 | 4.0262 | 10.1212 | 0.9231 | 9.7914 | 0.9231 | MSFT | stock |
| baseline | development | 13 | 22 | sufficient_sample | 3.8101 | 5.3284 | 10.4633 | 0.6364 | 3.8101 | 0.6364 | 2.6677 | 3.6027 | 0.6364 | 3.2923 | 0.6364 | NKE | stock |
| baseline | holdout | 13 | 9 | insufficient_sample | -4.0403 | -7.8198 | 14.3979 | 0.3333 | -4.0403 | 0.3333 | 4.9913 | -4.2320 | 0.3333 | -4.5189 | 0.3333 | NKE | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 7.5323 | 11.5335 | 12.0757 | 0.6667 | 7.5323 | 0.6667 | 4.9356 | 7.3175 | 0.6667 | 6.9960 | 0.6667 | NKE | stock |
| candidate | development | 13 | 23 | sufficient_sample | 5.3634 | 6.8811 | 10.4743 | 0.6957 | 5.3634 | 0.6957 | 2.9566 | 5.1529 | 0.6957 | 4.8379 | 0.6957 | NKE | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -5.3128 | -7.8198 | 16.3751 | 0.3077 | -5.3128 | 0.3077 | 4.3596 | -5.5020 | 0.3077 | -5.7851 | 0.3077 | NKE | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 7.0634 | 10.2168 | 14.1997 | 0.7692 | 7.0634 | 0.7692 | 3.1362 | 6.8495 | 0.7692 | 6.5295 | 0.6923 | NKE | stock |
| baseline | development | 13 | 20 | sufficient_sample | 9.1776 | 5.6208 | 29.3876 | 0.6500 | 9.1776 | 0.6500 | 2.5345 | 8.9594 | 0.6500 | 8.6330 | 0.6000 | NVDA | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 21.9178 | 21.7756 | 32.5008 | 0.7333 | 21.9178 | 0.7333 | 3.6083 | 21.6742 | 0.7333 | 21.3097 | 0.7333 | NVDA | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 14.4849 | 13.9394 | 26.8504 | 0.8333 | 14.4849 | 0.8333 | 2.9920 | 14.2561 | 0.7500 | 13.9139 | 0.7500 | NVDA | stock |
| candidate | development | 13 | 21 | sufficient_sample | 8.0031 | 3.0844 | 31.3222 | 0.6667 | 8.0031 | 0.6667 | 3.3609 | 7.7873 | 0.6190 | 7.4644 | 0.6190 | NVDA | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 19.7312 | 18.6250 | 31.5106 | 0.7333 | 19.7312 | 0.7333 | 4.1143 | 19.4920 | 0.7333 | 19.1340 | 0.7333 | NVDA | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 14.2977 | 14.0369 | 30.3438 | 0.7500 | 14.2977 | 0.7500 | 3.2837 | 14.0694 | 0.6667 | 13.7277 | 0.6667 | NVDA | stock |
| baseline | development | 13 | 21 | sufficient_sample | 0.9507 | 1.0941 | 9.3220 | 0.6190 | 0.9507 | 0.6190 | 2.6207 | 0.7490 | 0.6190 | 0.4472 | 0.5714 | ORCL | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 8.0113 | 14.7641 | 22.2087 | 0.7143 | 8.0113 | 0.7143 | 4.6698 | 7.7954 | 0.7143 | 7.4725 | 0.7143 | ORCL | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 2.4443 | 2.9649 | 6.3438 | 0.8462 | 2.4443 | 0.8462 | 4.0007 | 2.2397 | 0.8462 | 1.9334 | 0.8462 | ORCL | stock |
| candidate | development | 13 | 22 | sufficient_sample | 0.9045 | 0.9231 | 8.9848 | 0.5455 | 0.9045 | 0.5455 | 2.5901 | 0.7028 | 0.5455 | 0.4012 | 0.5000 | ORCL | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 10.9615 | 10.6895 | 18.4956 | 0.6250 | 10.9615 | 0.6250 | 3.4439 | 10.7398 | 0.6250 | 10.4081 | 0.6250 | ORCL | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 2.2190 | 2.9649 | 6.6123 | 0.7692 | 2.2190 | 0.7692 | 2.4754 | 2.0147 | 0.7692 | 1.7091 | 0.7692 | ORCL | stock |
| baseline | development | 13 | 21 | sufficient_sample | 3.2238 | 3.4496 | 9.7680 | 0.5714 | 3.2238 | 0.5714 | 2.7913 | 3.0175 | 0.5238 | 2.7089 | 0.5238 | PFE | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -0.9945 | 0.7749 | 9.3934 | 0.5000 | -0.9945 | 0.5000 | 2.2448 | -1.1924 | 0.5000 | -1.4883 | 0.5000 | PFE | stock |
| baseline | validation | 13 | 12 | insufficient_sample | -0.4067 | 0.4402 | 10.3529 | 0.5000 | -0.4067 | 0.5000 | 2.7677 | -0.6057 | 0.5000 | -0.9034 | 0.5000 | PFE | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.8027 | 3.3843 | 9.3531 | 0.6522 | 2.8027 | 0.6522 | 2.8953 | 2.5973 | 0.6522 | 2.2900 | 0.6522 | PFE | stock |
| candidate | holdout | 13 | 13 | insufficient_sample | -1.6151 | -4.1796 | 8.2204 | 0.3846 | -1.6151 | 0.3846 | 2.4180 | -1.8117 | 0.3846 | -2.1058 | 0.3846 | PFE | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 1.0211 | 1.8111 | 8.6599 | 0.5385 | 1.0211 | 0.5385 | 2.5694 | 0.8192 | 0.5385 | 0.5172 | 0.5385 | PFE | stock |
| baseline | development | 13 | 21 | sufficient_sample | 2.9922 | 2.5127 | 5.3763 | 0.6667 | 2.9922 | 0.6667 | 3.8520 | 2.7865 | 0.6667 | 2.4786 | 0.6190 | PG | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | 1.3078 | 1.9015 | 4.7631 | 0.5714 | 1.3078 | 0.5714 | 4.4146 | 1.1053 | 0.5714 | 0.8025 | 0.5714 | PG | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 3.9176 | 4.4445 | 7.2678 | 0.7500 | 3.9176 | 0.7500 | 2.9803 | 3.7100 | 0.7500 | 3.3993 | 0.7500 | PG | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.2069 | 2.5949 | 5.0242 | 0.6522 | 2.2069 | 0.6522 | 2.6776 | 2.0027 | 0.6522 | 1.6972 | 0.6522 | PG | stock |
| candidate | holdout | 13 | 15 | insufficient_sample | 1.0713 | 1.5741 | 4.6858 | 0.5333 | 1.0713 | 0.5333 | 3.6948 | 0.8694 | 0.5333 | 0.5672 | 0.5333 | PG | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 4.5356 | 5.4546 | 5.9762 | 0.7500 | 4.5356 | 0.7500 | 3.2986 | 4.3267 | 0.7500 | 4.0142 | 0.7500 | PG | stock |
| baseline | development | 13 | 23 | sufficient_sample | 3.2756 | 5.4386 | 7.0813 | 0.7391 | 3.2756 | 0.7391 | 2.2786 | 3.0692 | 0.7391 | 2.7605 | 0.6957 | QQQ | etf |
| baseline | holdout | 13 | 14 | insufficient_sample | 5.6977 | 7.8688 | 7.1831 | 0.7857 | 5.6977 | 0.7857 | 4.8581 | 5.4866 | 0.7857 | 5.1706 | 0.7857 | QQQ | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 5.5237 | 7.0227 | 10.8387 | 0.8462 | 5.5237 | 0.8462 | 2.4864 | 5.3128 | 0.8462 | 4.9974 | 0.8462 | QQQ | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.7821 | 4.5354 | 6.6514 | 0.7083 | 3.7821 | 0.7083 | 2.9714 | 3.5747 | 0.7083 | 3.2645 | 0.7083 | QQQ | etf |
| candidate | holdout | 13 | 15 | insufficient_sample | 2.5388 | 7.2562 | 8.9703 | 0.7333 | 2.5388 | 0.7333 | 2.7760 | 2.3340 | 0.7333 | 2.0274 | 0.7333 | QQQ | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 7.2302 | 7.0812 | 10.7577 | 0.8462 | 7.2302 | 0.8462 | 4.8522 | 7.0159 | 0.8462 | 6.6954 | 0.8462 | QQQ | etf |
| baseline | development | 13 | 23 | sufficient_sample | 5.6784 | 3.3653 | 8.3572 | 0.7391 | 5.6784 | 0.7391 | 2.8790 | 5.4672 | 0.7391 | 5.1513 | 0.7391 | UNH | stock |
| baseline | holdout | 13 | 14 | insufficient_sample | -2.0211 | 0.3046 | 15.8435 | 0.5000 | -2.0211 | 0.5000 | 3.9994 | -2.2169 | 0.5000 | -2.5098 | 0.5000 | UNH | stock |
| baseline | validation | 13 | 13 | insufficient_sample | 4.5031 | 5.6998 | 9.6879 | 0.7692 | 4.5031 | 0.7692 | 4.0606 | 4.2943 | 0.7692 | 3.9819 | 0.7692 | UNH | stock |
| candidate | development | 13 | 24 | sufficient_sample | 6.7045 | 8.4597 | 8.4888 | 0.7083 | 6.7045 | 0.7083 | 2.9190 | 6.4913 | 0.6667 | 6.1723 | 0.6667 | UNH | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | -1.3417 | 2.8059 | 13.5363 | 0.6250 | -1.3417 | 0.6250 | 6.2322 | -1.5388 | 0.6250 | -1.8338 | 0.6250 | UNH | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 3.9211 | 5.7950 | 7.6947 | 0.7692 | 3.9211 | 0.7692 | 4.0262 | 3.7135 | 0.7692 | 3.4028 | 0.7692 | UNH | stock |
| baseline | development | 13 | 22 | sufficient_sample | 2.7681 | 2.8393 | 7.2890 | 0.6818 | 2.7681 | 0.6818 | 3.0006 | 2.5628 | 0.6818 | 2.2555 | 0.6818 | UPS | stock |
| baseline | holdout | 13 | 10 | insufficient_sample | -2.2825 | -5.4246 | 9.9179 | 0.4000 | -2.2825 | 0.4000 | 0.2780 | -2.4778 | 0.4000 | -2.7699 | 0.4000 | UPS | stock |
| baseline | validation | 13 | 11 | insufficient_sample | 2.7125 | -5.8444 | 19.0656 | 0.4545 | 2.7125 | 0.4545 | 2.8392 | 2.5073 | 0.4545 | 2.2002 | 0.4545 | UPS | stock |
| candidate | development | 13 | 23 | sufficient_sample | 3.1140 | 2.9892 | 7.6909 | 0.6522 | 3.1140 | 0.6522 | 2.8686 | 2.9080 | 0.6522 | 2.5998 | 0.6522 | UPS | stock |
| candidate | holdout | 13 | 11 | insufficient_sample | -2.0985 | 0.6845 | 10.1882 | 0.5455 | -2.0985 | 0.5455 | 1.2140 | -2.2941 | 0.5455 | -2.5868 | 0.5455 | UPS | stock |
| candidate | validation | 13 | 12 | insufficient_sample | 3.9003 | 3.6882 | 13.3632 | 0.6667 | 3.9003 | 0.6667 | 4.1708 | 3.6927 | 0.6667 | 3.3820 | 0.6667 | UPS | stock |
| baseline | development | 13 | 20 | sufficient_sample | 2.9794 | 2.1660 | 7.6995 | 0.5500 | 2.9794 | 0.5500 | 4.7101 | 2.7737 | 0.5500 | 2.4658 | 0.5500 | WMT | stock |
| baseline | holdout | 13 | 16 | insufficient_sample | 3.6152 | 1.9638 | 10.3336 | 0.6875 | 3.6152 | 0.6875 | 2.7511 | 3.4081 | 0.6250 | 3.0984 | 0.6250 | WMT | stock |
| baseline | validation | 13 | 12 | insufficient_sample | 5.9804 | 7.4495 | 9.9113 | 0.7500 | 5.9804 | 0.7500 | 2.6603 | 5.7687 | 0.6667 | 5.4518 | 0.6667 | WMT | stock |
| candidate | development | 13 | 21 | sufficient_sample | 3.2327 | 3.3925 | 6.3456 | 0.6667 | 3.2327 | 0.6667 | 3.8025 | 3.0264 | 0.6667 | 2.7178 | 0.6667 | WMT | stock |
| candidate | holdout | 13 | 16 | insufficient_sample | 3.6152 | 1.9638 | 10.3336 | 0.6875 | 3.6152 | 0.6875 | 2.7511 | 3.4081 | 0.6250 | 3.0984 | 0.6250 | WMT | stock |
| candidate | validation | 13 | 13 | insufficient_sample | 7.1590 | 7.7308 | 9.9173 | 0.6923 | 7.1590 | 0.6923 | 3.3387 | 6.9449 | 0.6923 | 6.6246 | 0.6923 | WMT | stock |
| baseline | development | 13 | 21 | sufficient_sample | 0.9075 | 1.9527 | 8.1770 | 0.6667 | 0.9075 | 0.6667 | 2.6688 | 0.7059 | 0.6667 | 0.4042 | 0.6190 | XLB | etf |
| baseline | holdout | 13 | 13 | insufficient_sample | 1.0067 | 2.3308 | 6.9643 | 0.6923 | 1.0067 | 0.6923 | 4.1455 | 0.8049 | 0.6923 | 0.5029 | 0.6923 | XLB | etf |
| baseline | validation | 13 | 12 | insufficient_sample | 3.6421 | 4.4353 | 7.1346 | 0.8333 | 3.6421 | 0.8333 | 4.4249 | 3.4350 | 0.8333 | 3.1251 | 0.8333 | XLB | etf |
| candidate | development | 13 | 23 | sufficient_sample | 0.7705 | 4.3726 | 8.9005 | 0.6087 | 0.7705 | 0.6087 | 2.4831 | 0.5692 | 0.6087 | 0.2679 | 0.6087 | XLB | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.1176 | 1.8530 | 6.3299 | 0.6250 | 1.1176 | 0.6250 | 2.8575 | 0.9155 | 0.6250 | 0.6133 | 0.5625 | XLB | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 3.4859 | 4.0423 | 7.9668 | 0.8462 | 3.4859 | 0.8462 | 4.0429 | 3.2791 | 0.8462 | 2.9697 | 0.8462 | XLB | etf |
| baseline | development | 13 | 17 | insufficient_sample | 3.1086 | 2.0806 | 9.1262 | 0.7059 | 3.1086 | 0.7059 | 3.3920 | 2.9026 | 0.7059 | 2.5943 | 0.7059 | XLE | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 5.0719 | 1.5708 | 11.4244 | 0.6000 | 5.0719 | 0.6000 | 2.9487 | 4.8620 | 0.6000 | 4.5478 | 0.6000 | XLE | etf |
| baseline | validation | 13 | 7 | insufficient_sample | -9.0700 | -4.8687 | 18.4857 | 0.2857 | -9.0700 | 0.2857 | -0.6097 | -9.2517 | 0.2857 | -9.5235 | 0.2857 | XLE | etf |
| candidate | development | 13 | 22 | sufficient_sample | 1.4418 | 2.0410 | 11.9625 | 0.5909 | 1.4418 | 0.5909 | 3.0735 | 1.2391 | 0.5909 | 0.9359 | 0.5909 | XLE | etf |
| candidate | holdout | 13 | 17 | insufficient_sample | 5.6537 | 4.1271 | 10.9152 | 0.6471 | 5.6537 | 0.6471 | 3.8807 | 5.4426 | 0.6471 | 5.1268 | 0.6471 | XLE | etf |
| candidate | validation | 13 | 11 | insufficient_sample | -6.4326 | -3.2355 | 14.7255 | 0.2727 | -6.4326 | 0.2727 | 1.9748 | -6.6196 | 0.2727 | -6.8993 | 0.1818 | XLE | etf |
| baseline | development | 13 | 20 | sufficient_sample | 2.7722 | 3.0108 | 7.1207 | 0.7000 | 2.7722 | 0.7000 | 2.6148 | 2.5668 | 0.7000 | 2.2596 | 0.6500 | XLF | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 2.8315 | 3.2516 | 8.5082 | 0.7333 | 2.8315 | 0.7333 | 3.2358 | 2.6260 | 0.7333 | 2.3186 | 0.7333 | XLF | etf |
| baseline | validation | 13 | 11 | insufficient_sample | 0.1498 | 3.1460 | 10.3479 | 0.6364 | 0.1498 | 0.6364 | 2.2943 | -0.0503 | 0.6364 | -0.3497 | 0.6364 | XLF | etf |
| candidate | development | 13 | 23 | sufficient_sample | 1.4570 | 3.4120 | 9.4741 | 0.7391 | 1.4570 | 0.7391 | 1.9723 | 1.2543 | 0.7391 | 0.9510 | 0.7391 | XLF | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.2994 | 3.0221 | 9.2444 | 0.7500 | 4.2994 | 0.7500 | 3.6593 | 4.0910 | 0.7500 | 3.7792 | 0.7500 | XLF | etf |
| candidate | validation | 13 | 12 | insufficient_sample | 0.0838 | 2.8983 | 9.4142 | 0.5833 | 0.0838 | 0.5833 | 2.1173 | -0.1162 | 0.5833 | -0.4154 | 0.5833 | XLF | etf |
| baseline | development | 13 | 23 | sufficient_sample | 2.3692 | 3.1554 | 7.5182 | 0.6957 | 2.3692 | 0.6957 | 2.7800 | 2.1647 | 0.6957 | 1.8586 | 0.6957 | XLI | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 2.8905 | 2.4031 | 7.4715 | 0.6875 | 2.8905 | 0.6875 | 3.0721 | 2.6849 | 0.6875 | 2.3773 | 0.6875 | XLI | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 1.1605 | 3.0045 | 10.8723 | 0.8462 | 1.1605 | 0.8462 | 2.3884 | 0.9583 | 0.8462 | 0.6559 | 0.8462 | XLI | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.9479 | 3.0302 | 7.5000 | 0.6667 | 2.9479 | 0.6667 | 2.7864 | 2.7422 | 0.6250 | 2.4344 | 0.6250 | XLI | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.3801 | 4.1777 | 7.1073 | 0.7500 | 4.3801 | 0.7500 | 4.6771 | 4.1716 | 0.7500 | 3.8595 | 0.7500 | XLI | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 0.6006 | 3.6400 | 13.0801 | 0.7692 | 0.6006 | 0.7692 | 1.9042 | 0.3996 | 0.7692 | 0.0988 | 0.7692 | XLI | etf |
| baseline | development | 13 | 23 | sufficient_sample | 3.4941 | 5.0230 | 5.9356 | 0.7391 | 3.4941 | 0.7391 | 2.9447 | 3.2873 | 0.7391 | 2.9779 | 0.7391 | XLK | etf |
| baseline | holdout | 13 | 16 | insufficient_sample | 3.9875 | 8.5505 | 9.7227 | 0.6875 | 3.9875 | 0.6875 | 2.8955 | 3.7798 | 0.6875 | 3.4689 | 0.6875 | XLK | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 5.7183 | 6.7462 | 11.1740 | 0.8462 | 5.7183 | 0.8462 | 2.4864 | 5.5071 | 0.8462 | 5.1910 | 0.8462 | XLK | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.0670 | 3.2623 | 6.2304 | 0.6667 | 3.0670 | 0.6667 | 2.9819 | 2.8610 | 0.6667 | 2.5529 | 0.6667 | XLK | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 4.1913 | 8.5505 | 9.2532 | 0.6875 | 4.1913 | 0.6875 | 3.1863 | 3.9831 | 0.6875 | 3.6716 | 0.6875 | XLK | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 6.6663 | 6.3559 | 11.6246 | 0.7692 | 6.6663 | 0.7692 | 3.1428 | 6.4532 | 0.7692 | 6.1343 | 0.7692 | XLK | etf |
| baseline | development | 13 | 24 | sufficient_sample | 3.0804 | 4.0015 | 4.0947 | 0.7917 | 3.0804 | 0.7917 | 2.9718 | 2.8745 | 0.7500 | 2.5663 | 0.6667 | XLP | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 1.8381 | 1.7334 | 3.0506 | 0.7333 | 1.8381 | 0.7333 | 2.9786 | 1.6346 | 0.7333 | 1.3302 | 0.7333 | XLP | etf |
| baseline | validation | 13 | 12 | insufficient_sample | 1.6557 | 3.3820 | 3.7831 | 0.6667 | 1.6557 | 0.6667 | 3.2543 | 1.4526 | 0.6667 | 1.1487 | 0.6667 | XLP | etf |
| candidate | development | 13 | 24 | sufficient_sample | 3.4844 | 3.6798 | 3.9014 | 0.8333 | 3.4844 | 0.8333 | 3.5051 | 3.2776 | 0.8333 | 2.9683 | 0.8333 | XLP | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.4225 | 2.1544 | 4.6997 | 0.6250 | 1.4225 | 0.6250 | 3.4308 | 1.2199 | 0.6250 | 0.9167 | 0.6250 | XLP | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.7087 | 2.8357 | 6.0341 | 0.6923 | 1.7087 | 0.6923 | 3.9328 | 1.5055 | 0.6154 | 1.2015 | 0.6154 | XLP | etf |
| baseline | development | 13 | 23 | sufficient_sample | 2.6666 | 2.0203 | 6.5324 | 0.6957 | 2.6666 | 0.6957 | 2.7808 | 2.4615 | 0.6957 | 2.1546 | 0.6522 | XLU | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 0.7840 | 1.0791 | 5.7184 | 0.6000 | 0.7840 | 0.6000 | 3.4889 | 0.5827 | 0.6000 | 0.2814 | 0.6000 | XLU | etf |
| baseline | validation | 13 | 11 | insufficient_sample | 2.5612 | 3.8881 | 5.7455 | 0.8182 | 2.5612 | 0.8182 | 3.7998 | 2.3563 | 0.8182 | 2.0497 | 0.8182 | XLU | etf |
| candidate | development | 13 | 24 | sufficient_sample | 2.8233 | 2.5968 | 4.0079 | 0.7917 | 2.8233 | 0.7917 | 2.9936 | 2.6178 | 0.7917 | 2.3104 | 0.7083 | XLU | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 1.6778 | 0.5975 | 7.1201 | 0.5625 | 1.6778 | 0.5625 | 2.8383 | 1.4747 | 0.5000 | 1.1707 | 0.5000 | XLU | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 1.5051 | 3.8881 | 8.6011 | 0.8462 | 1.5051 | 0.8462 | 3.9734 | 1.3023 | 0.8462 | 0.9988 | 0.8462 | XLU | etf |
| baseline | development | 13 | 22 | sufficient_sample | 3.1726 | 4.3756 | 6.1358 | 0.7727 | 3.1726 | 0.7727 | 2.7175 | 2.9664 | 0.7727 | 2.6580 | 0.7273 | XLV | etf |
| baseline | holdout | 13 | 15 | insufficient_sample | 0.7281 | -0.2496 | 6.7807 | 0.4667 | 0.7281 | 0.4667 | 2.1614 | 0.5269 | 0.4667 | 0.2258 | 0.4000 | XLV | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 3.3394 | 3.3089 | 5.8875 | 0.6923 | 3.3394 | 0.6923 | 4.0129 | 3.1329 | 0.6923 | 2.8240 | 0.6923 | XLV | etf |
| candidate | development | 13 | 23 | sufficient_sample | 2.6377 | 4.9018 | 6.8462 | 0.7391 | 2.6377 | 0.7391 | 2.0751 | 2.4327 | 0.7391 | 2.1258 | 0.7391 | XLV | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 0.4093 | 0.8360 | 4.3601 | 0.5625 | 0.4093 | 0.5625 | 3.3235 | 0.2086 | 0.5625 | -0.0915 | 0.5625 | XLV | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 3.0522 | 3.5228 | 5.4442 | 0.7692 | 3.0522 | 0.7692 | 4.0262 | 2.8463 | 0.7692 | 2.5382 | 0.7692 | XLV | etf |
| baseline | development | 13 | 23 | sufficient_sample | 4.0371 | 4.2401 | 6.1552 | 0.8261 | 4.0371 | 0.8261 | 2.9209 | 3.8293 | 0.8261 | 3.5182 | 0.7826 | XLY | etf |
| baseline | holdout | 13 | 14 | insufficient_sample | 3.2745 | 3.8081 | 8.3609 | 0.8571 | 3.2745 | 0.8571 | 4.8581 | 3.0681 | 0.8571 | 2.7594 | 0.7857 | XLY | etf |
| baseline | validation | 13 | 13 | insufficient_sample | 3.1602 | 4.2249 | 11.5240 | 0.8462 | 3.1602 | 0.8462 | 3.0493 | 2.9541 | 0.8462 | 2.6457 | 0.8462 | XLY | etf |
| candidate | development | 13 | 24 | sufficient_sample | 4.4204 | 4.9184 | 6.7141 | 0.7917 | 4.4204 | 0.7917 | 3.0684 | 4.2118 | 0.7917 | 3.8996 | 0.7917 | XLY | etf |
| candidate | holdout | 13 | 16 | insufficient_sample | 0.6558 | 2.3814 | 9.9546 | 0.6875 | 0.6558 | 0.6875 | 2.8528 | 0.4547 | 0.6875 | 0.1537 | 0.6875 | XLY | etf |
| candidate | validation | 13 | 13 | insufficient_sample | 5.0346 | 4.2249 | 9.3876 | 0.7692 | 5.0346 | 0.7692 | 4.0429 | 4.8248 | 0.7692 | 4.5108 | 0.7692 | XLY | etf |
| baseline | development | 13 | 18 | insufficient_sample | 2.6918 | 3.0639 | 8.9062 | 0.6111 | 2.6918 | 0.6111 | 3.6121 | 2.4866 | 0.6111 | 2.1796 | 0.6111 | XOM | stock |
| baseline | holdout | 13 | 15 | insufficient_sample | 7.7048 | 5.2978 | 12.2332 | 0.6667 | 7.7048 | 0.6667 | 3.6115 | 7.4896 | 0.6000 | 7.1677 | 0.6000 | XOM | stock |
| baseline | validation | 13 | 8 | insufficient_sample | -2.9818 | -3.3571 | 5.2569 | 0.2500 | -2.9818 | 0.2500 | 2.0783 | -3.1757 | 0.2500 | -3.4657 | 0.1250 | XOM | stock |
| candidate | development | 13 | 23 | sufficient_sample | 2.3435 | 0.6659 | 8.6302 | 0.5217 | 2.3435 | 0.5217 | 3.2478 | 2.1391 | 0.5217 | 1.8331 | 0.5217 | XOM | stock |
| candidate | holdout | 13 | 17 | insufficient_sample | 6.6186 | 3.0797 | 12.1599 | 0.7059 | 6.6186 | 0.7059 | 3.8807 | 6.4056 | 0.7059 | 6.0868 | 0.7059 | XOM | stock |
| candidate | validation | 13 | 11 | insufficient_sample | -5.0449 | -5.9885 | 9.2631 | 0.3636 | -5.0449 | 0.3636 | 2.8804 | -5.2346 | 0.3636 | -5.5185 | 0.3636 | XOM | stock |
| baseline | development | 26 | 18 | insufficient_sample | 13.1946 | 13.8697 | 18.3801 | 0.8333 | 13.1946 | 0.8333 | 5.2208 | 12.9684 | 0.8333 | 12.6300 | 0.8333 | AAPL | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 5.3900 | 9.0246 | 11.2891 | 0.6154 | 5.3900 | 0.6154 | 6.6981 | 5.1795 | 0.6154 | 4.8644 | 0.6154 | AAPL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 19.7860 | 17.4563 | 22.6298 | 0.8333 | 19.7860 | 0.8333 | 5.7057 | 19.5466 | 0.8333 | 19.1885 | 0.8333 | AAPL | stock |
| candidate | development | 26 | 21 | sufficient_sample | 13.8405 | 12.4009 | 22.0536 | 0.7143 | 13.8405 | 0.7143 | 6.2330 | 13.6131 | 0.7143 | 13.2727 | 0.7143 | AAPL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.7640 | 11.4583 | 12.9875 | 0.6667 | 9.7640 | 0.6667 | 8.5447 | 9.5447 | 0.6667 | 9.2166 | 0.6667 | AAPL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 19.0946 | 19.5615 | 21.4313 | 0.8333 | 19.0946 | 0.8333 | 5.7961 | 18.8566 | 0.8333 | 18.5006 | 0.8333 | AAPL | stock |
| baseline | development | 26 | 21 | sufficient_sample | 17.6462 | 20.0758 | 20.1520 | 0.7619 | 17.6462 | 0.7619 | 6.4156 | 17.4111 | 0.7619 | 17.0594 | 0.7619 | AMZN | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 4.9835 | 6.5715 | 17.3020 | 0.6667 | 4.9835 | 0.6667 | 6.1452 | 4.7737 | 0.6667 | 4.4599 | 0.6667 | AMZN | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 21.5329 | 25.5401 | 25.3069 | 0.6364 | 21.5329 | 0.6364 | 6.3795 | 21.2901 | 0.6364 | 20.9267 | 0.6364 | AMZN | stock |
| candidate | development | 26 | 22 | sufficient_sample | 15.5735 | 10.7194 | 20.1141 | 0.7273 | 15.5735 | 0.7273 | 6.5675 | 15.3426 | 0.7273 | 14.9971 | 0.7273 | AMZN | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 1.2372 | 3.1624 | 21.4885 | 0.6429 | 1.2372 | 0.6429 | 5.1679 | 1.0349 | 0.6429 | 0.7322 | 0.5714 | AMZN | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 22.9076 | 21.6421 | 24.6055 | 0.7692 | 22.9076 | 0.7692 | 10.3718 | 22.6621 | 0.7692 | 22.2946 | 0.7692 | AMZN | stock |
| baseline | development | 26 | 20 | sufficient_sample | 7.0358 | 2.8992 | 15.3005 | 0.6000 | 7.0358 | 0.6000 | 5.0888 | 6.8219 | 0.6000 | 6.5020 | 0.6000 | BA | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | 1.5717 | 7.0725 | 16.7932 | 0.6000 | 1.5717 | 0.6000 | 8.7983 | 1.3687 | 0.6000 | 1.0651 | 0.6000 | BA | stock |
| baseline | validation | 26 | 10 | insufficient_sample | 13.0664 | 7.5122 | 23.4670 | 0.7000 | 13.0664 | 0.7000 | 5.3897 | 12.8405 | 0.7000 | 12.5025 | 0.7000 | BA | stock |
| candidate | development | 26 | 22 | sufficient_sample | 8.1907 | 3.3581 | 16.1497 | 0.6364 | 8.1907 | 0.6364 | 6.2076 | 7.9745 | 0.6364 | 7.6511 | 0.6364 | BA | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | 1.6241 | 0.8963 | 19.3449 | 0.5000 | 1.6241 | 0.5000 | 7.8991 | 1.4211 | 0.5000 | 1.1173 | 0.5000 | BA | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 3.4499 | 4.6112 | 29.9404 | 0.6667 | 3.4499 | 0.6667 | 5.2667 | 3.2432 | 0.6667 | 2.9339 | 0.6667 | BA | stock |
| baseline | development | 26 | 16 | insufficient_sample | 2.4480 | 1.9207 | 19.9194 | 0.5000 | 2.4480 | 0.5000 | 5.8436 | 2.2433 | 0.5000 | 1.9370 | 0.5000 | BAC | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 3.7223 | 10.2859 | 19.8666 | 0.6429 | 3.7223 | 0.6429 | 4.9046 | 3.5151 | 0.6429 | 3.2050 | 0.6429 | BAC | stock |
| baseline | validation | 26 | 10 | insufficient_sample | -0.1616 | 7.7649 | 19.8276 | 0.6000 | -0.1616 | 0.6000 | 2.6774 | -0.3611 | 0.6000 | -0.6596 | 0.6000 | BAC | stock |
| candidate | development | 26 | 17 | insufficient_sample | 0.4679 | -4.6495 | 20.4085 | 0.4706 | 0.4679 | 0.4706 | 4.9079 | 0.2671 | 0.4706 | -0.0332 | 0.4706 | BAC | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 9.1941 | 15.8699 | 19.3017 | 0.7143 | 9.1941 | 0.7143 | 8.0996 | 8.9760 | 0.7143 | 8.6495 | 0.7143 | BAC | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -0.2832 | 3.3062 | 18.1021 | 0.5000 | -0.2832 | 0.5000 | 4.4120 | -0.4824 | 0.5000 | -0.7805 | 0.5000 | BAC | stock |
| baseline | development | 26 | 17 | insufficient_sample | 3.4568 | -3.4589 | 18.5794 | 0.4706 | 3.4568 | 0.4706 | 5.8580 | 3.2501 | 0.4706 | 2.9408 | 0.4706 | CAT | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 4.1188 | 6.4176 | 12.8647 | 0.6923 | 4.1188 | 0.6923 | 6.7185 | 3.9108 | 0.6923 | 3.5995 | 0.6923 | CAT | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 9.3231 | 9.8249 | 19.9552 | 0.5833 | 9.3231 | 0.5833 | 4.7394 | 9.1046 | 0.5833 | 8.7778 | 0.5833 | CAT | stock |
| candidate | development | 26 | 20 | sufficient_sample | 5.4997 | 6.9278 | 19.0023 | 0.6000 | 5.4997 | 0.6000 | 6.3878 | 5.2889 | 0.6000 | 4.9735 | 0.6000 | CAT | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 7.5595 | 7.8259 | 11.4418 | 0.7143 | 7.5595 | 0.7143 | 7.9355 | 7.3446 | 0.7143 | 7.0231 | 0.7143 | CAT | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 8.2956 | 5.7569 | 22.6021 | 0.5000 | 8.2956 | 0.5000 | 4.4120 | 8.0792 | 0.5000 | 7.7555 | 0.5000 | CAT | stock |
| baseline | development | 26 | 22 | sufficient_sample | 10.0486 | 10.1013 | 8.9891 | 0.8636 | 10.0486 | 0.8636 | 6.9446 | 9.8288 | 0.8636 | 9.4998 | 0.8636 | COST | stock |
| baseline | holdout | 26 | 16 | insufficient_sample | 10.0140 | 11.6045 | 15.2785 | 0.6875 | 10.0140 | 0.6875 | 7.1078 | 9.7942 | 0.6875 | 9.4653 | 0.6875 | COST | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 10.1277 | 11.0016 | 11.2304 | 0.7500 | 10.1277 | 0.7500 | 4.2947 | 9.9077 | 0.7500 | 9.5784 | 0.7500 | COST | stock |
| candidate | development | 26 | 23 | sufficient_sample | 10.6692 | 11.8085 | 9.9358 | 0.8261 | 10.6692 | 0.8261 | 6.2114 | 10.4481 | 0.8261 | 10.1172 | 0.8261 | COST | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 11.2512 | 11.4050 | 15.8264 | 0.6875 | 11.2512 | 0.6875 | 7.6079 | 11.0289 | 0.6875 | 10.6963 | 0.6875 | COST | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 13.5465 | 16.1890 | 12.1108 | 0.7692 | 13.5465 | 0.7692 | 8.4682 | 13.3196 | 0.7692 | 12.9802 | 0.7692 | COST | stock |
| baseline | development | 26 | 18 | insufficient_sample | 2.4399 | 3.3501 | 14.9327 | 0.6111 | 2.4399 | 0.6111 | 6.5762 | 2.2352 | 0.6111 | 1.9290 | 0.6111 | CSCO | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 4.8969 | 6.3556 | 13.7927 | 0.5385 | 4.8969 | 0.5385 | 7.7069 | 4.6873 | 0.5385 | 4.3737 | 0.5385 | CSCO | stock |
| baseline | validation | 26 | 10 | insufficient_sample | 11.7305 | 5.8092 | 14.9238 | 0.8000 | 11.7305 | 0.8000 | 8.0498 | 11.5073 | 0.8000 | 11.1732 | 0.8000 | CSCO | stock |
| candidate | development | 26 | 21 | sufficient_sample | 2.8896 | 1.8443 | 15.5660 | 0.5714 | 2.8896 | 0.5714 | 6.1495 | 2.6840 | 0.5714 | 2.3764 | 0.5714 | CSCO | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 5.0586 | 6.2851 | 13.2583 | 0.5714 | 5.0586 | 0.5714 | 7.4842 | 4.8487 | 0.5714 | 4.5346 | 0.5714 | CSCO | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 7.7054 | 5.6066 | 17.3735 | 0.6667 | 7.7054 | 0.6667 | 5.0474 | 7.4902 | 0.6667 | 7.1682 | 0.6667 | CSCO | stock |
| baseline | development | 26 | 18 | insufficient_sample | 5.2180 | 4.7310 | 10.4786 | 0.7778 | 5.2180 | 0.7778 | 5.9365 | 5.0078 | 0.7778 | 4.6932 | 0.7778 | CVX | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 10.1429 | 1.7833 | 20.1926 | 0.5385 | 10.1429 | 0.5385 | 6.4379 | 9.9228 | 0.5385 | 9.5935 | 0.5385 | CVX | stock |
| baseline | validation | 26 | 11 | insufficient_sample | -4.0290 | 0.5781 | 16.3868 | 0.5455 | -4.0290 | 0.5455 | 4.5158 | -4.2207 | 0.5455 | -4.5076 | 0.5455 | CVX | stock |
| candidate | development | 26 | 22 | sufficient_sample | 5.7893 | 6.8602 | 11.7310 | 0.7273 | 5.7893 | 0.7273 | 7.5295 | 5.5780 | 0.7273 | 5.2617 | 0.7273 | CVX | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 9.6997 | 7.6905 | 19.1030 | 0.5625 | 9.6997 | 0.5625 | 7.4326 | 9.4806 | 0.5625 | 9.1526 | 0.5625 | CVX | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -2.9077 | -0.6347 | 9.8819 | 0.5000 | -2.9077 | 0.5000 | 6.6696 | -3.1017 | 0.5000 | -3.3919 | 0.4167 | CVX | stock |
| baseline | development | 26 | 22 | sufficient_sample | 5.3380 | 4.8084 | 5.8863 | 0.8636 | 5.3380 | 0.8636 | 5.5240 | 5.1276 | 0.8636 | 4.8127 | 0.8636 | DIA | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.9020 | 5.8828 | 8.5488 | 0.7333 | 4.9020 | 0.7333 | 5.8471 | 4.6924 | 0.7333 | 4.3788 | 0.7333 | DIA | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 5.1087 | 7.2531 | 7.1335 | 0.7500 | 5.1087 | 0.7500 | 5.4022 | 4.8987 | 0.7500 | 4.5845 | 0.6667 | DIA | etf |
| candidate | development | 26 | 23 | sufficient_sample | 6.1889 | 7.0742 | 8.1415 | 0.8261 | 6.1889 | 0.8261 | 6.6443 | 5.9767 | 0.8261 | 5.6593 | 0.7826 | DIA | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 5.7857 | 5.8828 | 7.0229 | 0.7333 | 5.7857 | 0.7333 | 7.2899 | 5.5744 | 0.7333 | 5.2581 | 0.7333 | DIA | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 5.9737 | 8.7994 | 10.0901 | 0.7500 | 5.9737 | 0.7500 | 6.9783 | 5.7619 | 0.6667 | 5.4451 | 0.6667 | DIA | etf |
| baseline | development | 26 | 21 | sufficient_sample | 9.5706 | 11.0651 | 14.0642 | 0.7143 | 9.5706 | 0.7143 | 5.1240 | 9.3517 | 0.7143 | 9.0241 | 0.7143 | DIS | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | -4.4045 | -3.7294 | 10.5725 | 0.4000 | -4.4045 | 0.4000 | 9.9539 | -4.5955 | 0.4000 | -4.8812 | 0.4000 | DIS | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 0.7595 | -1.4948 | 11.7269 | 0.4545 | 0.7595 | 0.4545 | 5.0746 | 0.5582 | 0.4545 | 0.2570 | 0.4545 | DIS | stock |
| candidate | development | 26 | 22 | sufficient_sample | 9.2731 | 10.9753 | 14.6886 | 0.7727 | 9.2731 | 0.7727 | 4.7457 | 9.0548 | 0.7727 | 8.7281 | 0.7727 | DIS | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -5.3281 | -6.6518 | 15.2021 | 0.4167 | -5.3281 | 0.4167 | 7.5871 | -5.5173 | 0.4167 | -5.8003 | 0.4167 | DIS | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.9892 | 1.2234 | 15.3942 | 0.5000 | 2.9892 | 0.5000 | 6.6048 | 2.7834 | 0.5000 | 2.4755 | 0.5000 | DIS | stock |
| baseline | development | 26 | 20 | sufficient_sample | 9.6013 | 10.1199 | 14.4309 | 0.7500 | 9.6013 | 0.7500 | 6.2625 | 9.3823 | 0.7500 | 9.0547 | 0.7000 | GOOGL | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 14.4476 | 10.1144 | 29.4658 | 0.6429 | 14.4476 | 0.6429 | 5.9742 | 14.2189 | 0.6429 | 13.8768 | 0.6429 | GOOGL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 9.2562 | 6.9331 | 11.5144 | 0.8333 | 9.2562 | 0.8333 | 5.6966 | 9.0379 | 0.8333 | 8.7113 | 0.8333 | GOOGL | stock |
| candidate | development | 26 | 22 | sufficient_sample | 8.3795 | 7.5467 | 15.3224 | 0.6818 | 8.3795 | 0.6818 | 5.1318 | 8.1629 | 0.6818 | 7.8389 | 0.6818 | GOOGL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 14.9041 | 10.3653 | 26.3213 | 0.6667 | 14.9041 | 0.6667 | 7.5181 | 14.6745 | 0.6667 | 14.3310 | 0.6667 | GOOGL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 11.5169 | 11.1212 | 11.0855 | 0.8333 | 11.5169 | 0.8333 | 7.9673 | 11.2941 | 0.8333 | 10.9607 | 0.8333 | GOOGL | stock |
| baseline | development | 26 | 15 | insufficient_sample | 4.4819 | 2.0514 | 18.8121 | 0.6667 | 4.4819 | 0.6667 | 5.4140 | 4.2732 | 0.6667 | 3.9608 | 0.6000 | GS | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 12.3578 | 15.8993 | 19.6757 | 0.6429 | 12.3578 | 0.6429 | 6.1309 | 12.1333 | 0.6429 | 11.7974 | 0.6429 | GS | stock |
| baseline | validation | 26 | 10 | insufficient_sample | -0.0999 | 0.6411 | 9.7952 | 0.5000 | -0.0999 | 0.5000 | 7.0730 | -0.2995 | 0.5000 | -0.5982 | 0.5000 | GS | stock |
| candidate | development | 26 | 19 | insufficient_sample | 0.1113 | 3.3298 | 16.7432 | 0.5789 | 0.1113 | 0.5789 | 4.7458 | -0.0887 | 0.5789 | -0.3880 | 0.5789 | GS | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 14.3870 | 19.8363 | 21.1684 | 0.7333 | 14.3870 | 0.7333 | 9.5888 | 14.1584 | 0.7333 | 13.8165 | 0.7333 | GS | stock |
| candidate | validation | 26 | 12 | insufficient_sample | -1.7842 | -2.2962 | 10.0703 | 0.4167 | -1.7842 | 0.4167 | 6.0239 | -1.9804 | 0.4167 | -2.2740 | 0.4167 | GS | stock |
| baseline | development | 26 | 22 | sufficient_sample | 13.4877 | 10.2712 | 13.9167 | 0.8636 | 13.4877 | 0.8636 | 6.0249 | 13.2610 | 0.8636 | 12.9217 | 0.8636 | HD | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 2.6716 | 4.7305 | 12.8257 | 0.6667 | 2.6716 | 0.6667 | 6.6998 | 2.4665 | 0.6667 | 2.1595 | 0.5833 | HD | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 8.6176 | 14.6402 | 17.4955 | 0.7500 | 8.6176 | 0.7500 | 4.0725 | 8.4006 | 0.7500 | 8.0759 | 0.7500 | HD | stock |
| candidate | development | 26 | 23 | sufficient_sample | 12.9807 | 11.1946 | 13.9598 | 0.7826 | 12.9807 | 0.7826 | 5.2108 | 12.7549 | 0.7826 | 12.4172 | 0.7826 | HD | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 5.1502 | 6.2697 | 14.6081 | 0.6429 | 5.1502 | 0.6429 | 6.0371 | 4.9401 | 0.6429 | 4.6257 | 0.6429 | HD | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 13.1681 | 15.5926 | 15.0052 | 0.8333 | 13.1681 | 0.8333 | 6.7610 | 12.9420 | 0.8333 | 12.6037 | 0.8333 | HD | stock |
| baseline | development | 26 | 23 | sufficient_sample | 8.0032 | 7.7277 | 11.5022 | 0.7826 | 8.0032 | 0.7826 | 5.3386 | 7.7875 | 0.7826 | 7.4646 | 0.7826 | HON | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | -0.4219 | -0.7025 | 8.5643 | 0.5000 | -0.4219 | 0.5000 | 7.2492 | -0.6208 | 0.5000 | -0.9185 | 0.5000 | HON | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 7.2540 | 6.2336 | 12.5253 | 0.8333 | 7.2540 | 0.8333 | 5.4022 | 7.0397 | 0.8333 | 6.7190 | 0.8333 | HON | stock |
| candidate | development | 26 | 23 | sufficient_sample | 8.4320 | 7.6076 | 12.0661 | 0.7826 | 8.4320 | 0.7826 | 5.6040 | 8.2153 | 0.7826 | 7.8911 | 0.7826 | HON | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | -0.3296 | 1.9599 | 8.7638 | 0.5714 | -0.3296 | 0.5714 | 6.1974 | -0.5287 | 0.5714 | -0.8267 | 0.5714 | HON | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 8.4537 | 7.7268 | 10.2304 | 0.8333 | 8.4537 | 0.8333 | 7.9673 | 8.2370 | 0.8333 | 7.9128 | 0.8333 | HON | stock |
| baseline | development | 26 | 18 | insufficient_sample | 3.3487 | 4.3550 | 11.7073 | 0.6111 | 3.3487 | 0.6111 | 6.8624 | 3.1422 | 0.6111 | 2.8332 | 0.6111 | IBM | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 11.6904 | 10.6578 | 14.7432 | 0.7333 | 11.6904 | 0.7333 | 5.8923 | 11.4673 | 0.6667 | 11.1334 | 0.6667 | IBM | stock |
| baseline | validation | 26 | 9 | insufficient_sample | -5.0944 | -3.7513 | 7.0684 | 0.2222 | -5.0944 | 0.2222 | 5.0340 | -5.2840 | 0.2222 | -5.5677 | 0.2222 | IBM | stock |
| candidate | development | 26 | 20 | sufficient_sample | 2.9550 | 5.7584 | 13.3481 | 0.6500 | 2.9550 | 0.6500 | 5.4394 | 2.7493 | 0.6500 | 2.4415 | 0.6500 | IBM | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 11.4364 | 10.2988 | 12.6406 | 0.7500 | 11.4364 | 0.7500 | 6.6730 | 11.2137 | 0.6875 | 10.8806 | 0.6875 | IBM | stock |
| candidate | validation | 26 | 10 | insufficient_sample | -2.9462 | -3.3404 | 6.9445 | 0.3000 | -2.9462 | 0.3000 | 5.7067 | -3.1401 | 0.3000 | -3.4303 | 0.3000 | IBM | stock |
| baseline | development | 26 | 20 | sufficient_sample | 4.7921 | 5.2824 | 12.1593 | 0.6000 | 4.7921 | 0.6000 | 5.1203 | 4.5827 | 0.6000 | 4.2694 | 0.6000 | IWM | etf |
| baseline | holdout | 26 | 12 | insufficient_sample | -0.3138 | 1.0966 | 9.2210 | 0.5833 | -0.3138 | 0.5833 | 7.4352 | -0.5129 | 0.5833 | -0.8109 | 0.5833 | IWM | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 0.1352 | 5.2392 | 15.1631 | 0.5833 | 0.1352 | 0.5833 | 3.8094 | -0.0649 | 0.5833 | -0.3642 | 0.5833 | IWM | etf |
| candidate | development | 26 | 22 | sufficient_sample | 4.2174 | 4.8727 | 11.5473 | 0.6818 | 4.2174 | 0.6818 | 5.0240 | 4.0091 | 0.6818 | 3.6976 | 0.6364 | IWM | etf |
| candidate | holdout | 26 | 14 | insufficient_sample | 4.0017 | 3.7953 | 10.2815 | 0.7143 | 4.0017 | 0.7143 | 8.1839 | 3.7939 | 0.6429 | 3.4830 | 0.6429 | IWM | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 0.4999 | 5.2392 | 17.1002 | 0.6667 | 0.4999 | 0.6667 | 4.2910 | 0.2991 | 0.6667 | -0.0014 | 0.5833 | IWM | etf |
| baseline | development | 26 | 21 | sufficient_sample | 7.2165 | 6.9174 | 8.9947 | 0.7143 | 7.2165 | 0.7143 | 6.6697 | 7.0023 | 0.7143 | 6.6818 | 0.7143 | JNJ | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 1.7472 | -1.8774 | 10.3070 | 0.3333 | 1.7472 | 0.3333 | 4.7208 | 1.5439 | 0.3333 | 1.2397 | 0.3333 | JNJ | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 2.3101 | 1.0216 | 8.0104 | 0.5455 | 2.3101 | 0.5455 | 6.2356 | 2.1057 | 0.5455 | 1.7999 | 0.5455 | JNJ | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.1318 | 4.3269 | 8.4427 | 0.6957 | 6.1318 | 0.6957 | 5.2208 | 5.9198 | 0.6957 | 5.6025 | 0.6957 | JNJ | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 3.6919 | -0.2404 | 10.1175 | 0.4000 | 3.6919 | 0.4000 | 6.8791 | 3.4847 | 0.4000 | 3.1747 | 0.4000 | JNJ | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.8063 | 2.0947 | 7.8440 | 0.5833 | 2.8063 | 0.5833 | 6.4106 | 2.6009 | 0.5833 | 2.2936 | 0.5833 | JNJ | stock |
| baseline | development | 26 | 19 | insufficient_sample | 4.0194 | 4.6604 | 14.3719 | 0.6842 | 4.0194 | 0.6842 | 4.3520 | 3.8116 | 0.6842 | 3.5006 | 0.6316 | JPM | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 13.0374 | 14.1012 | 12.1472 | 0.8571 | 13.0374 | 0.8571 | 8.2847 | 12.8115 | 0.8571 | 12.4736 | 0.8571 | JPM | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 1.7839 | 8.8188 | 16.2306 | 0.6364 | 1.7839 | 0.6364 | 3.9508 | 1.5805 | 0.6364 | 1.2762 | 0.6364 | JPM | stock |
| candidate | development | 26 | 22 | sufficient_sample | 4.5818 | 8.7762 | 14.1874 | 0.6364 | 4.5818 | 0.6364 | 5.2765 | 4.3729 | 0.6364 | 4.0602 | 0.6364 | JPM | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.9513 | 13.8000 | 17.5018 | 0.7333 | 7.9513 | 0.7333 | 5.6466 | 7.7356 | 0.7333 | 7.4129 | 0.7333 | JPM | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 7.3867 | 11.1898 | 12.2342 | 0.7500 | 7.3867 | 0.7500 | 7.9673 | 7.1721 | 0.7500 | 6.8511 | 0.6667 | JPM | stock |
| baseline | development | 26 | 22 | sufficient_sample | 5.2113 | 4.9220 | 6.6255 | 0.7273 | 5.2113 | 0.7273 | 5.9814 | 5.0010 | 0.7273 | 4.6865 | 0.7273 | KO | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 6.5027 | 6.4148 | 8.1872 | 0.7857 | 6.5027 | 0.7857 | 7.0370 | 6.2899 | 0.7143 | 5.9715 | 0.7143 | KO | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 4.7438 | 2.3313 | 7.4537 | 0.6364 | 4.7438 | 0.6364 | 6.3438 | 4.5345 | 0.6364 | 4.2214 | 0.6364 | KO | stock |
| candidate | development | 26 | 22 | sufficient_sample | 5.0074 | 5.2837 | 6.3525 | 0.7273 | 5.0074 | 0.7273 | 5.9893 | 4.7976 | 0.7273 | 4.4837 | 0.7273 | KO | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.2486 | 7.3684 | 7.2858 | 0.8000 | 7.2486 | 0.8000 | 8.0138 | 7.0344 | 0.8000 | 6.7137 | 0.8000 | KO | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 4.6528 | 7.5401 | 7.8059 | 0.6667 | 4.6528 | 0.6667 | 7.4404 | 4.4437 | 0.6667 | 4.1309 | 0.6667 | KO | stock |
| baseline | development | 26 | 22 | sufficient_sample | 6.8180 | 6.0302 | 11.1319 | 0.6364 | 6.8180 | 0.6364 | 6.0893 | 6.6046 | 0.6364 | 6.2852 | 0.6364 | MCD | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.2695 | 5.7415 | 5.8090 | 0.8667 | 4.2695 | 0.8667 | 6.3115 | 4.0612 | 0.8667 | 3.7495 | 0.8667 | MCD | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 9.2583 | 7.4292 | 10.4714 | 0.8182 | 9.2583 | 0.8182 | 7.3806 | 9.0400 | 0.8182 | 8.7134 | 0.7273 | MCD | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.8417 | 6.7679 | 8.7617 | 0.7391 | 6.8417 | 0.7391 | 6.0837 | 6.6282 | 0.7391 | 6.3088 | 0.7391 | MCD | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 5.8755 | 7.1154 | 5.9078 | 0.8750 | 5.8755 | 0.8750 | 7.1838 | 5.6640 | 0.8750 | 5.3474 | 0.8750 | MCD | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 12.4025 | 12.3651 | 10.8444 | 0.9091 | 12.4025 | 0.9091 | 7.2970 | 12.1780 | 0.9091 | 11.8419 | 0.8182 | MCD | stock |
| baseline | development | 26 | 21 | sufficient_sample | 7.3462 | 8.7383 | 11.6239 | 0.7143 | 7.3462 | 0.7143 | 6.2411 | 7.1317 | 0.7143 | 6.8108 | 0.7143 | MMM | stock |
| baseline | holdout | 26 | 11 | insufficient_sample | 7.4751 | -2.1218 | 22.3153 | 0.4545 | 7.4751 | 0.4545 | 9.0990 | 7.2603 | 0.4545 | 6.9390 | 0.4545 | MMM | stock |
| baseline | validation | 26 | 9 | insufficient_sample | 0.9655 | -2.2028 | 13.7426 | 0.4444 | 0.9655 | 0.4444 | 6.1635 | 0.7638 | 0.4444 | 0.4619 | 0.4444 | MMM | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.8733 | 8.7383 | 10.8109 | 0.7391 | 6.8733 | 0.7391 | 5.9981 | 6.6598 | 0.7391 | 6.3403 | 0.7391 | MMM | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | 6.5499 | 6.3979 | 23.1046 | 0.6667 | 6.5499 | 0.6667 | 5.3599 | 6.3370 | 0.6667 | 6.0185 | 0.6667 | MMM | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 1.4366 | 2.8157 | 14.5029 | 0.5455 | 1.4366 | 0.5455 | 5.8072 | 1.2339 | 0.5455 | 0.9307 | 0.5455 | MMM | stock |
| baseline | development | 26 | 21 | sufficient_sample | 6.0619 | 7.6747 | 10.9700 | 0.7143 | 6.0619 | 0.7143 | 6.2651 | 5.8500 | 0.7143 | 5.5329 | 0.6667 | MRK | stock |
| baseline | holdout | 26 | 12 | insufficient_sample | 4.6820 | 5.1131 | 13.3793 | 0.6667 | 4.6820 | 0.6667 | 4.3672 | 4.4729 | 0.6667 | 4.1599 | 0.6667 | MRK | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 4.9797 | 5.8903 | 11.0503 | 0.6364 | 4.9797 | 0.6364 | 4.9801 | 4.7699 | 0.6364 | 4.4561 | 0.6364 | MRK | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.2706 | 5.9788 | 9.8655 | 0.6957 | 6.2706 | 0.6957 | 6.2838 | 6.0582 | 0.6957 | 5.7405 | 0.6957 | MRK | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 8.2635 | 9.1367 | 16.3070 | 0.5714 | 8.2635 | 0.5714 | 7.9881 | 8.0471 | 0.5714 | 7.7235 | 0.5714 | MRK | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 4.8777 | 4.8235 | 10.5852 | 0.6667 | 4.8777 | 0.6667 | 6.4683 | 4.6682 | 0.6667 | 4.3547 | 0.6667 | MRK | stock |
| baseline | development | 26 | 20 | sufficient_sample | 3.4357 | 3.7819 | 12.5876 | 0.5500 | 3.4357 | 0.5500 | 3.6113 | 3.2290 | 0.5500 | 2.9198 | 0.5500 | MSFT | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 7.4800 | 8.6903 | 17.3180 | 0.6429 | 7.4800 | 0.6429 | 5.4152 | 7.2652 | 0.6429 | 6.9439 | 0.6429 | MSFT | stock |
| baseline | validation | 26 | 13 | insufficient_sample | 20.8046 | 20.4495 | 11.1459 | 0.9231 | 20.8046 | 0.9231 | 10.2597 | 20.5632 | 0.9231 | 20.2021 | 0.9231 | MSFT | stock |
| candidate | development | 26 | 22 | sufficient_sample | 7.1745 | 9.6595 | 13.4405 | 0.6364 | 7.1745 | 0.6364 | 5.2828 | 6.9603 | 0.6364 | 6.6399 | 0.6364 | MSFT | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.0828 | 7.7239 | 15.7601 | 0.6667 | 9.0828 | 0.6667 | 6.7064 | 8.8648 | 0.6667 | 8.5387 | 0.6667 | MSFT | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 20.3079 | 20.4495 | 10.9326 | 0.9231 | 20.3079 | 0.9231 | 8.4682 | 20.0675 | 0.9231 | 19.7078 | 0.9231 | MSFT | stock |
| baseline | development | 26 | 21 | sufficient_sample | 9.2375 | 8.1412 | 13.2611 | 0.7619 | 9.2375 | 0.7619 | 4.8436 | 9.0193 | 0.6667 | 8.6927 | 0.6667 | NKE | stock |
| baseline | holdout | 26 | 8 | insufficient_sample | -7.7812 | -10.2408 | 18.5249 | 0.2500 | -7.7812 | 0.2500 | 7.5182 | -7.9654 | 0.2500 | -8.2411 | 0.2500 | NKE | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 15.4078 | 15.3117 | 12.2364 | 0.9091 | 15.4078 | 0.9091 | 8.3534 | 15.1772 | 0.9091 | 14.8322 | 0.9091 | NKE | stock |
| candidate | development | 26 | 22 | sufficient_sample | 10.5200 | 12.1765 | 13.6746 | 0.7727 | 10.5200 | 0.7727 | 5.6894 | 10.2992 | 0.6818 | 9.9688 | 0.6818 | NKE | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -6.3558 | -6.8542 | 19.0612 | 0.2500 | -6.3558 | 0.2500 | 6.6721 | -6.5429 | 0.2500 | -6.8228 | 0.2500 | NKE | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 13.5004 | 8.9520 | 14.1575 | 0.9167 | 13.5004 | 0.9167 | 7.7198 | 13.2736 | 0.9167 | 12.9343 | 0.9167 | NKE | stock |
| baseline | development | 26 | 20 | sufficient_sample | 17.6414 | 13.7239 | 42.5526 | 0.6500 | 17.6414 | 0.6500 | 4.5560 | 17.4064 | 0.6500 | 17.0547 | 0.6500 | NVDA | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 39.6246 | 35.2755 | 57.1120 | 0.7857 | 39.6246 | 0.7857 | 5.8657 | 39.3457 | 0.7857 | 38.9283 | 0.7857 | NVDA | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 32.5901 | 38.0400 | 42.1437 | 0.8182 | 32.5901 | 0.8182 | 5.3033 | 32.3252 | 0.8182 | 31.9288 | 0.8182 | NVDA | stock |
| candidate | development | 26 | 21 | sufficient_sample | 15.0544 | 10.6993 | 40.6395 | 0.6190 | 15.0544 | 0.6190 | 5.2123 | 14.8245 | 0.6190 | 14.4805 | 0.6190 | NVDA | stock |
| candidate | holdout | 26 | 14 | insufficient_sample | 42.9319 | 36.8909 | 59.3230 | 0.7857 | 42.9319 | 0.7857 | 7.3726 | 42.6463 | 0.7857 | 42.2190 | 0.7857 | NVDA | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 31.3856 | 34.0533 | 47.7003 | 0.7273 | 31.3856 | 0.7273 | 4.8283 | 31.1231 | 0.7273 | 30.7303 | 0.7273 | NVDA | stock |
| baseline | development | 26 | 21 | sufficient_sample | 2.4797 | 3.6243 | 14.3297 | 0.5714 | 2.4797 | 0.5714 | 5.7085 | 2.2749 | 0.5714 | 1.9685 | 0.5714 | ORCL | stock |
| baseline | holdout | 26 | 13 | insufficient_sample | 19.3863 | 27.0692 | 22.6144 | 0.6923 | 19.3863 | 0.6923 | 8.5370 | 19.1477 | 0.6923 | 18.7908 | 0.6923 | ORCL | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 4.8484 | 3.3828 | 9.5656 | 0.7500 | 4.8484 | 0.7500 | 5.8482 | 4.6389 | 0.7500 | 4.3254 | 0.7500 | ORCL | stock |
| candidate | development | 26 | 22 | sufficient_sample | 3.5624 | 4.1775 | 13.3109 | 0.6364 | 3.5624 | 0.6364 | 6.1773 | 3.3554 | 0.6364 | 3.0458 | 0.6364 | ORCL | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 20.0410 | 28.8901 | 30.6287 | 0.6667 | 20.0410 | 0.6667 | 7.2839 | 19.8012 | 0.6667 | 19.4423 | 0.6667 | ORCL | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 6.0377 | 5.5720 | 11.0391 | 0.7500 | 6.0377 | 0.7500 | 5.5800 | 5.8258 | 0.7500 | 5.5088 | 0.7500 | ORCL | stock |
| baseline | development | 26 | 20 | sufficient_sample | 7.1699 | 11.0227 | 11.6500 | 0.6500 | 7.1699 | 0.6500 | 5.6830 | 6.9557 | 0.6500 | 6.6353 | 0.6500 | PFE | stock |
| baseline | holdout | 26 | 9 | insufficient_sample | 1.7643 | 1.1658 | 10.9775 | 0.6667 | 1.7643 | 0.6667 | 3.8517 | 1.5610 | 0.6667 | 1.2567 | 0.6667 | PFE | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 3.0179 | 3.3998 | 10.2342 | 0.7273 | 3.0179 | 0.7273 | 6.5895 | 2.8121 | 0.7273 | 2.5041 | 0.7273 | PFE | stock |
| candidate | development | 26 | 22 | sufficient_sample | 6.8035 | 9.3546 | 11.9658 | 0.7273 | 6.8035 | 0.7273 | 5.1329 | 6.5901 | 0.7273 | 6.2708 | 0.7273 | PFE | stock |
| candidate | holdout | 26 | 12 | insufficient_sample | -1.4943 | 0.9501 | 12.9194 | 0.5833 | -1.4943 | 0.5833 | 6.5119 | -1.6912 | 0.5833 | -1.9856 | 0.5833 | PFE | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 2.0327 | 3.0878 | 10.5574 | 0.6667 | 2.0327 | 0.6667 | 4.4578 | 1.8288 | 0.6667 | 1.5238 | 0.6667 | PFE | stock |
| baseline | development | 26 | 20 | sufficient_sample | 4.3550 | 5.6265 | 8.2520 | 0.8500 | 4.3550 | 0.8500 | 6.5071 | 4.1465 | 0.8500 | 3.8346 | 0.8500 | PG | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 2.7977 | 3.3218 | 6.4465 | 0.7143 | 2.7977 | 0.7143 | 7.4047 | 2.5923 | 0.7143 | 2.2849 | 0.7143 | PG | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 6.6600 | 5.2374 | 13.4061 | 0.6364 | 6.6600 | 0.6364 | 5.2395 | 6.4469 | 0.6364 | 6.1280 | 0.6364 | PG | stock |
| candidate | development | 26 | 22 | sufficient_sample | 4.5010 | 5.4055 | 7.1834 | 0.8636 | 4.5010 | 0.8636 | 5.9780 | 4.2922 | 0.8636 | 3.9798 | 0.8636 | PG | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.3850 | 2.5311 | 6.4164 | 0.6667 | 2.3850 | 0.6667 | 6.6920 | 2.1805 | 0.6667 | 1.8744 | 0.6667 | PG | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 6.3248 | 5.2374 | 12.7520 | 0.6364 | 6.3248 | 0.6364 | 4.5947 | 6.1123 | 0.6364 | 5.7945 | 0.6364 | PG | stock |
| baseline | development | 26 | 22 | sufficient_sample | 6.2399 | 7.7030 | 8.7057 | 0.7273 | 6.2399 | 0.7273 | 4.7246 | 6.0276 | 0.7273 | 5.7100 | 0.6818 | QQQ | etf |
| baseline | holdout | 26 | 13 | insufficient_sample | 9.6165 | 13.4461 | 13.4862 | 0.7692 | 9.6165 | 0.7692 | 7.9917 | 9.3975 | 0.7692 | 9.0698 | 0.7692 | QQQ | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 10.1246 | 10.3056 | 14.7398 | 0.7500 | 10.1246 | 0.7500 | 4.1216 | 9.9046 | 0.7500 | 9.5753 | 0.7500 | QQQ | etf |
| candidate | development | 26 | 23 | sufficient_sample | 9.2009 | 9.8942 | 9.3871 | 0.8696 | 9.2009 | 0.8696 | 7.0585 | 8.9827 | 0.8696 | 8.6562 | 0.8261 | QQQ | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 6.0076 | 12.4879 | 13.7292 | 0.7333 | 6.0076 | 0.7333 | 6.0929 | 5.7958 | 0.7333 | 5.4789 | 0.7333 | QQQ | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 13.1827 | 11.9849 | 14.1287 | 0.8333 | 13.1827 | 0.8333 | 8.4083 | 12.9565 | 0.8333 | 12.6182 | 0.8333 | QQQ | etf |
| baseline | development | 26 | 22 | sufficient_sample | 12.7394 | 8.0164 | 12.2252 | 0.8182 | 12.7394 | 0.8182 | 6.4547 | 12.5141 | 0.8182 | 12.1771 | 0.8182 | UNH | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 2.5229 | 6.1639 | 15.4497 | 0.7857 | 2.5229 | 0.7857 | 6.7831 | 2.3181 | 0.7857 | 2.0116 | 0.7143 | UNH | stock |
| baseline | validation | 26 | 12 | insufficient_sample | 12.1752 | 16.2527 | 10.3758 | 0.7500 | 12.1752 | 0.7500 | 6.3921 | 11.9510 | 0.7500 | 11.6157 | 0.7500 | UNH | stock |
| candidate | development | 26 | 23 | sufficient_sample | 14.1648 | 14.8432 | 12.1634 | 0.8261 | 14.1648 | 0.8261 | 6.3873 | 13.9367 | 0.8261 | 13.5954 | 0.8261 | UNH | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 0.4567 | 5.8846 | 18.0001 | 0.6000 | 0.4567 | 0.6000 | 10.5507 | 0.2560 | 0.6000 | -0.0443 | 0.6000 | UNH | stock |
| candidate | validation | 26 | 13 | insufficient_sample | 12.3424 | 15.4591 | 9.4354 | 0.8462 | 12.3424 | 0.8462 | 8.4682 | 12.1180 | 0.8462 | 11.7821 | 0.8462 | UNH | stock |
| baseline | development | 26 | 22 | sufficient_sample | 4.1374 | 3.5944 | 7.3079 | 0.7273 | 4.1374 | 0.7273 | 5.3953 | 3.9293 | 0.6818 | 3.6180 | 0.6818 | UPS | stock |
| baseline | holdout | 26 | 10 | insufficient_sample | -0.9962 | -6.2328 | 17.0670 | 0.3000 | -0.9962 | 0.3000 | 3.3367 | -1.1940 | 0.3000 | -1.4900 | 0.3000 | UPS | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 2.3628 | -5.5214 | 21.9417 | 0.3636 | 2.3628 | 0.3636 | 5.8122 | 2.1583 | 0.3636 | 1.8523 | 0.3636 | UPS | stock |
| candidate | development | 26 | 23 | sufficient_sample | 6.5604 | 7.5871 | 9.0841 | 0.7826 | 6.5604 | 0.7826 | 6.5369 | 6.3474 | 0.7391 | 6.0289 | 0.7391 | UPS | stock |
| candidate | holdout | 26 | 11 | insufficient_sample | -0.2676 | -4.2451 | 15.5347 | 0.3636 | -0.2676 | 0.3636 | 4.8568 | -0.4669 | 0.3636 | -0.7650 | 0.3636 | UPS | stock |
| candidate | validation | 26 | 11 | insufficient_sample | 9.3166 | 5.0728 | 24.9894 | 0.5455 | 9.3166 | 0.5455 | 7.5256 | 9.0982 | 0.5455 | 8.7714 | 0.5455 | UPS | stock |
| baseline | development | 26 | 19 | insufficient_sample | 6.2931 | 6.1318 | 9.0075 | 0.7895 | 6.2931 | 0.7895 | 8.0180 | 6.0807 | 0.7895 | 5.7630 | 0.7895 | WMT | stock |
| baseline | holdout | 26 | 15 | insufficient_sample | 9.2324 | 4.9978 | 13.8750 | 0.6667 | 9.2324 | 0.6667 | 5.9663 | 9.0142 | 0.6667 | 8.6876 | 0.6667 | WMT | stock |
| baseline | validation | 26 | 11 | insufficient_sample | 11.4474 | 11.2222 | 9.5689 | 0.9091 | 11.4474 | 0.9091 | 6.3849 | 11.2247 | 0.9091 | 10.8916 | 0.9091 | WMT | stock |
| candidate | development | 26 | 20 | sufficient_sample | 5.8781 | 5.7092 | 10.0683 | 0.7500 | 5.8781 | 0.7500 | 6.6195 | 5.6665 | 0.7500 | 5.3500 | 0.7000 | WMT | stock |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.2324 | 4.9978 | 13.8750 | 0.6667 | 9.2324 | 0.6667 | 5.9663 | 9.0142 | 0.6667 | 8.6876 | 0.6667 | WMT | stock |
| candidate | validation | 26 | 12 | insufficient_sample | 10.1180 | 11.9782 | 8.4625 | 0.9167 | 10.1180 | 0.9167 | 3.7210 | 9.8979 | 0.9167 | 9.5687 | 0.9167 | WMT | stock |
| baseline | development | 26 | 21 | sufficient_sample | 3.5042 | 5.1466 | 11.1874 | 0.6667 | 3.5042 | 0.6667 | 6.0663 | 3.2974 | 0.6667 | 2.9880 | 0.6667 | XLB | etf |
| baseline | holdout | 26 | 12 | insufficient_sample | 0.0065 | 1.9455 | 9.8047 | 0.5833 | 0.0065 | 0.5833 | 4.3504 | -0.1933 | 0.5833 | -0.4923 | 0.5833 | XLB | etf |
| baseline | validation | 26 | 11 | insufficient_sample | 2.9198 | 2.2592 | 13.6167 | 0.7273 | 2.9198 | 0.7273 | 4.8702 | 2.7141 | 0.7273 | 2.4064 | 0.7273 | XLB | etf |
| candidate | development | 26 | 22 | sufficient_sample | 4.2444 | 5.1513 | 10.1453 | 0.6818 | 4.2444 | 0.6818 | 6.7769 | 4.0361 | 0.6818 | 3.7244 | 0.6818 | XLB | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 1.2480 | 2.5286 | 7.0686 | 0.6667 | 1.2480 | 0.6667 | 5.4823 | 1.0457 | 0.6667 | 0.7430 | 0.6667 | XLB | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 5.6928 | 5.4432 | 11.2130 | 0.8333 | 5.6928 | 0.8333 | 7.7548 | 5.4816 | 0.8333 | 5.1656 | 0.7500 | XLB | etf |
| baseline | development | 26 | 16 | insufficient_sample | 6.0480 | 7.6897 | 14.5969 | 0.5625 | 6.0480 | 0.5625 | 7.6129 | 5.8361 | 0.5625 | 5.5191 | 0.5625 | XLE | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 14.1692 | 8.2535 | 19.0441 | 0.8000 | 14.1692 | 0.8000 | 8.0701 | 13.9411 | 0.8000 | 13.5998 | 0.8000 | XLE | etf |
| baseline | validation | 26 | 7 | insufficient_sample | -11.5085 | -10.5823 | 11.2428 | 0.1429 | -11.5085 | 0.1429 | 2.0005 | -11.6853 | 0.1429 | -11.9499 | 0.1429 | XLE | etf |
| candidate | development | 26 | 21 | sufficient_sample | 4.2481 | 7.6244 | 13.5864 | 0.6190 | 4.2481 | 0.6190 | 6.8464 | 4.0398 | 0.6190 | 3.7281 | 0.6190 | XLE | etf |
| candidate | holdout | 26 | 16 | insufficient_sample | 12.5480 | 10.2610 | 20.1613 | 0.6250 | 12.5480 | 0.6250 | 7.4326 | 12.3231 | 0.6250 | 11.9867 | 0.6250 | XLE | etf |
| candidate | validation | 26 | 11 | insufficient_sample | -12.2574 | -9.4523 | 18.1347 | 0.3636 | -12.2574 | 0.3636 | 3.2247 | -12.4327 | 0.3636 | -12.6950 | 0.3636 | XLE | etf |
| baseline | development | 26 | 19 | insufficient_sample | 3.4730 | 4.6066 | 11.7382 | 0.6842 | 3.4730 | 0.6842 | 4.4722 | 3.2663 | 0.6842 | 2.9569 | 0.6842 | XLF | etf |
| baseline | holdout | 26 | 14 | insufficient_sample | 7.6201 | 11.2708 | 12.3635 | 0.7143 | 7.6201 | 0.7143 | 7.8457 | 7.4051 | 0.7143 | 7.0834 | 0.7143 | XLF | etf |
| baseline | validation | 26 | 11 | insufficient_sample | -0.9237 | 3.5897 | 13.9534 | 0.6364 | -0.9237 | 0.6364 | 3.1237 | -1.1217 | 0.6364 | -1.4179 | 0.6364 | XLF | etf |
| candidate | development | 26 | 22 | sufficient_sample | 3.5079 | 6.5898 | 12.2038 | 0.6818 | 3.5079 | 0.6818 | 4.9831 | 3.3011 | 0.6818 | 2.9916 | 0.6818 | XLF | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 7.4153 | 9.3797 | 12.9327 | 0.8000 | 7.4153 | 0.8000 | 6.3156 | 7.2007 | 0.8000 | 6.8796 | 0.8000 | XLF | etf |
| candidate | validation | 26 | 12 | insufficient_sample | -0.2437 | 4.0551 | 12.7008 | 0.6667 | -0.2437 | 0.6667 | 3.7276 | -0.4430 | 0.6667 | -0.7413 | 0.5833 | XLF | etf |
| baseline | development | 26 | 22 | sufficient_sample | 5.6401 | 5.0757 | 10.0006 | 0.7273 | 5.6401 | 0.7273 | 5.6484 | 5.4291 | 0.7273 | 5.1133 | 0.7273 | XLI | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 5.9771 | 8.0237 | 10.1772 | 0.7333 | 5.9771 | 0.7333 | 6.7674 | 5.7654 | 0.7333 | 5.4485 | 0.7333 | XLI | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 1.8141 | 6.5171 | 11.9954 | 0.6667 | 1.8141 | 0.6667 | 4.0479 | 1.6107 | 0.6667 | 1.3063 | 0.6667 | XLI | etf |
| candidate | development | 26 | 23 | sufficient_sample | 5.9718 | 6.7749 | 10.8350 | 0.6957 | 5.9718 | 0.6957 | 5.7921 | 5.7600 | 0.6957 | 5.4432 | 0.6957 | XLI | etf |
| candidate | holdout | 26 | 16 | insufficient_sample | 7.4954 | 9.3242 | 8.4139 | 0.8125 | 7.4954 | 0.8125 | 8.9199 | 7.2806 | 0.8125 | 6.9592 | 0.8125 | XLI | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 3.5943 | 7.0569 | 9.8952 | 0.6667 | 3.5943 | 0.6667 | 5.4022 | 3.3873 | 0.6667 | 3.0776 | 0.6667 | XLI | etf |
| baseline | development | 26 | 23 | sufficient_sample | 6.4743 | 8.6048 | 7.9415 | 0.7826 | 6.4743 | 0.7826 | 5.5218 | 6.2616 | 0.7826 | 5.9433 | 0.7391 | XLK | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 7.5241 | 13.5627 | 15.6899 | 0.6667 | 7.5241 | 0.6667 | 5.3523 | 7.3092 | 0.6667 | 6.9878 | 0.6000 | XLK | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 11.0251 | 11.4874 | 14.6898 | 0.8333 | 11.0251 | 0.8333 | 4.1216 | 10.8033 | 0.8333 | 10.4714 | 0.8333 | XLK | etf |
| candidate | development | 26 | 23 | sufficient_sample | 7.7961 | 8.6048 | 9.0968 | 0.7826 | 7.7961 | 0.7826 | 6.9920 | 7.5808 | 0.7826 | 7.2585 | 0.7826 | XLK | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 9.0124 | 13.5627 | 13.5664 | 0.6667 | 9.0124 | 0.6667 | 6.6982 | 8.7945 | 0.6667 | 8.4686 | 0.6000 | XLK | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 15.9713 | 15.7936 | 11.4650 | 0.9167 | 15.9713 | 0.9167 | 8.4255 | 15.7396 | 0.9167 | 15.3929 | 0.9167 | XLK | etf |
| baseline | development | 26 | 23 | sufficient_sample | 6.7008 | 7.6474 | 4.8771 | 0.8696 | 6.7008 | 0.8696 | 6.1458 | 6.4876 | 0.8696 | 6.1686 | 0.8696 | XLP | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 3.5032 | 2.9993 | 4.1996 | 0.6667 | 3.5032 | 0.6667 | 7.1081 | 3.2964 | 0.6000 | 2.9870 | 0.6000 | XLP | etf |
| baseline | validation | 26 | 11 | insufficient_sample | 1.9964 | 1.5897 | 7.0653 | 0.5455 | 1.9964 | 0.5455 | 5.9030 | 1.7926 | 0.5455 | 1.4877 | 0.5455 | XLP | etf |
| candidate | development | 26 | 23 | sufficient_sample | 6.6993 | 7.0408 | 4.6789 | 0.8696 | 6.6993 | 0.8696 | 6.3171 | 6.4861 | 0.8696 | 6.1671 | 0.8696 | XLP | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 4.6597 | 5.1520 | 5.0589 | 0.8000 | 4.6597 | 0.8000 | 7.5971 | 4.4506 | 0.7333 | 4.1377 | 0.7333 | XLP | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 2.7135 | 2.1152 | 8.0054 | 0.5833 | 2.7135 | 0.5833 | 7.2983 | 2.5083 | 0.5833 | 2.2012 | 0.5833 | XLP | etf |
| baseline | development | 26 | 22 | sufficient_sample | 5.6314 | 5.6620 | 7.2236 | 0.7727 | 5.6314 | 0.7727 | 5.9210 | 5.4204 | 0.7273 | 5.1046 | 0.7273 | XLU | etf |
| baseline | holdout | 26 | 15 | insufficient_sample | 4.7216 | 5.6342 | 9.1124 | 0.8000 | 4.7216 | 0.8000 | 7.3357 | 4.5123 | 0.8000 | 4.1993 | 0.8000 | XLU | etf |
| baseline | validation | 26 | 10 | insufficient_sample | 3.4309 | 5.4457 | 7.7880 | 0.7000 | 3.4309 | 0.7000 | 5.8507 | 3.2242 | 0.7000 | 2.9150 | 0.7000 | XLU | etf |
| candidate | development | 26 | 23 | sufficient_sample | 5.6435 | 5.3747 | 5.2310 | 0.8696 | 5.6435 | 0.8696 | 6.1797 | 5.4324 | 0.7826 | 5.1166 | 0.7826 | XLU | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 6.5006 | 7.5014 | 9.3327 | 0.8000 | 6.5006 | 0.8000 | 6.2883 | 6.2878 | 0.8000 | 5.9695 | 0.8000 | XLU | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 4.6940 | 7.8019 | 7.7181 | 0.7500 | 4.6940 | 0.7500 | 8.1294 | 4.4848 | 0.7500 | 4.1718 | 0.7500 | XLU | etf |
| baseline | development | 26 | 21 | sufficient_sample | 7.1394 | 9.5711 | 8.4279 | 0.8571 | 7.1394 | 0.8571 | 5.1443 | 6.9253 | 0.8571 | 6.6050 | 0.8095 | XLV | etf |
| baseline | holdout | 26 | 14 | insufficient_sample | 1.1656 | 0.5864 | 6.3589 | 0.5000 | 1.1656 | 0.5000 | 5.1921 | 0.9634 | 0.5000 | 0.6610 | 0.5000 | XLV | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 7.3870 | 6.9731 | 5.9444 | 0.8333 | 7.3870 | 0.8333 | 8.1061 | 7.1724 | 0.8333 | 6.8514 | 0.8333 | XLV | etf |
| candidate | development | 26 | 22 | sufficient_sample | 7.6043 | 9.3258 | 9.4768 | 0.7727 | 7.6043 | 0.7727 | 5.8613 | 7.3893 | 0.7727 | 7.0676 | 0.7273 | XLV | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.7795 | 1.8866 | 5.9963 | 0.6667 | 2.7795 | 0.6667 | 6.7344 | 2.5742 | 0.6667 | 2.2669 | 0.6667 | XLV | etf |
| candidate | validation | 26 | 13 | insufficient_sample | 7.8946 | 7.4467 | 5.9572 | 0.8462 | 7.8946 | 0.8462 | 8.4682 | 7.6790 | 0.8462 | 7.3564 | 0.8462 | XLV | etf |
| baseline | development | 26 | 23 | sufficient_sample | 7.3329 | 6.4079 | 8.1702 | 0.8261 | 7.3329 | 0.8261 | 5.5486 | 7.1184 | 0.8261 | 6.7976 | 0.7826 | XLY | etf |
| baseline | holdout | 26 | 13 | insufficient_sample | 5.4973 | 7.0359 | 11.3492 | 0.6923 | 5.4973 | 0.6923 | 7.9917 | 5.2865 | 0.6923 | 4.9712 | 0.6923 | XLY | etf |
| baseline | validation | 26 | 12 | insufficient_sample | 4.8161 | 7.9196 | 13.7614 | 0.8333 | 4.8161 | 0.8333 | 3.7129 | 4.6067 | 0.8333 | 4.2933 | 0.7500 | XLY | etf |
| candidate | development | 26 | 23 | sufficient_sample | 8.4423 | 8.1057 | 9.5328 | 0.7826 | 8.4423 | 0.7826 | 6.5431 | 8.2257 | 0.7826 | 7.9015 | 0.7826 | XLY | etf |
| candidate | holdout | 26 | 15 | insufficient_sample | 2.4490 | 6.8394 | 12.3827 | 0.6667 | 2.4490 | 0.6667 | 5.6083 | 2.2443 | 0.6667 | 1.9381 | 0.6667 | XLY | etf |
| candidate | validation | 26 | 12 | insufficient_sample | 9.8228 | 10.1398 | 13.4620 | 0.9167 | 9.8228 | 0.9167 | 7.7548 | 9.6033 | 0.9167 | 9.2750 | 0.8333 | XLY | etf |
| baseline | development | 26 | 17 | insufficient_sample | 5.9293 | 5.0800 | 8.7763 | 0.7059 | 5.9293 | 0.7059 | 8.3752 | 5.7177 | 0.7059 | 5.4010 | 0.7059 | XOM | stock |
| baseline | holdout | 26 | 14 | insufficient_sample | 15.5665 | 12.1265 | 21.3152 | 0.6429 | 15.5665 | 0.6429 | 5.9033 | 15.3356 | 0.6429 | 14.9901 | 0.6429 | XOM | stock |
| baseline | validation | 26 | 8 | insufficient_sample | -3.4724 | -3.2405 | 4.3848 | 0.2500 | -3.4724 | 0.2500 | 5.2179 | -3.6652 | 0.2500 | -3.9538 | 0.2500 | XOM | stock |
| candidate | development | 26 | 22 | sufficient_sample | 3.3904 | 2.2079 | 11.9417 | 0.5909 | 3.3904 | 0.5909 | 6.6174 | 3.1838 | 0.5909 | 2.8748 | 0.5909 | XOM | stock |
| candidate | holdout | 26 | 16 | insufficient_sample | 14.3731 | 14.3535 | 20.9236 | 0.6875 | 14.3731 | 0.6875 | 7.4326 | 14.1446 | 0.6875 | 13.8027 | 0.6250 | XOM | stock |
| candidate | validation | 26 | 11 | insufficient_sample | -6.5786 | -4.8735 | 5.5592 | 0.0909 | -6.5786 | 0.0909 | 6.4686 | -6.7652 | 0.0909 | -7.0445 | 0.0000 | XOM | stock |

## downside

| rule | split | horizon_weeks | count | q10 | q25 | median | q75 | q90 | max_drawdown_pct |
|---|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 955 | -9.3288 | -2.0945 | 3.3247 | 9.3420 | 14.9877 | -56.4395 |
| candidate | validation | 13 | 530 | -10.4979 | -1.7615 | 4.2060 | 9.8423 | 15.8212 | -152.2163 |
| candidate | holdout | 13 | 642 | -12.1054 | -3.9351 | 2.7154 | 9.7018 | 18.6191 | -134.3972 |
| baseline | development | 13 | 877 | -8.3286 | -2.6174 | 3.2363 | 9.4931 | 14.1006 | -69.4845 |
| baseline | validation | 13 | 493 | -10.3543 | -2.1226 | 4.1754 | 9.7011 | 15.5137 | -99.4239 |
| baseline | holdout | 13 | 587 | -10.5184 | -3.5820 | 2.8635 | 10.1493 | 18.4205 | -83.5486 |
| candidate | development | 26 | 922 | -9.9314 | -1.0442 | 7.2541 | 14.2725 | 23.0949 | -106.5905 |
| candidate | validation | 26 | 500 | -12.0523 | -1.8705 | 7.3185 | 15.5842 | 24.4935 | -197.0339 |
| candidate | holdout | 26 | 609 | -13.4241 | -3.2208 | 6.2147 | 16.0013 | 27.6067 | -222.2300 |
| baseline | development | 26 | 851 | -9.0097 | -1.0569 | 6.5759 | 13.7005 | 23.5811 | -122.9851 |
| baseline | validation | 26 | 463 | -12.7569 | -2.2923 | 6.6186 | 15.0310 | 25.4085 | -139.6821 |
| baseline | holdout | 26 | 555 | -11.5325 | -2.9749 | 6.1519 | 15.0448 | 26.2647 | -188.3173 |

## cost_sensitivity

| rule | split | horizon_weeks | slippage_bps | count | mean_net_return_pct | median_net_return_pct | std_net_return_pct | win_rate |
|---|---|---|---|---|---|---|---|---|
| candidate | development | 13 | 0.0000 | 955 | 3.3426 | 3.3247 | 10.3219 | 0.6660 |
| candidate | validation | 13 | 0.0000 | 530 | 3.4831 | 4.2060 | 13.0328 | 0.6887 |
| candidate | holdout | 13 | 0.0000 | 642 | 3.3820 | 2.7154 | 12.5483 | 0.6215 |
| baseline | development | 13 | 0.0000 | 877 | 3.4371 | 3.2363 | 10.0038 | 0.6625 |
| baseline | validation | 13 | 0.0000 | 493 | 3.5428 | 4.1754 | 12.5548 | 0.6897 |
| baseline | holdout | 13 | 0.0000 | 587 | 3.7370 | 2.8635 | 12.5937 | 0.6371 |
| candidate | development | 13 | 10.0000 | 955 | 3.1361 | 3.1183 | 10.3013 | 0.6565 |
| candidate | validation | 13 | 10.0000 | 530 | 3.2763 | 3.9978 | 13.0068 | 0.6830 |
| candidate | holdout | 13 | 10.0000 | 642 | 3.1754 | 2.5102 | 12.5233 | 0.6153 |
| baseline | development | 13 | 10.0000 | 877 | 3.2304 | 3.0300 | 9.9838 | 0.6556 |
| baseline | validation | 13 | 10.0000 | 493 | 3.3359 | 3.9673 | 12.5297 | 0.6856 |
| baseline | holdout | 13 | 10.0000 | 587 | 3.5297 | 2.6580 | 12.5686 | 0.6286 |
| candidate | development | 13 | 25.0000 | 955 | 2.8272 | 2.8094 | 10.2704 | 0.6450 |
| candidate | validation | 13 | 25.0000 | 530 | 2.9670 | 3.6862 | 12.9678 | 0.6792 |
| candidate | holdout | 13 | 25.0000 | 642 | 2.8664 | 2.2031 | 12.4858 | 0.6028 |
| baseline | development | 13 | 25.0000 | 877 | 2.9212 | 2.7214 | 9.9539 | 0.6317 |
| baseline | validation | 13 | 25.0000 | 493 | 3.0264 | 3.6558 | 12.4921 | 0.6795 |
| baseline | holdout | 13 | 25.0000 | 587 | 3.2196 | 2.3505 | 12.5309 | 0.6150 |
| candidate | development | 26 | 0.0000 | 922 | 7.0373 | 7.2541 | 14.2835 | 0.7202 |
| candidate | validation | 26 | 0.0000 | 500 | 7.2600 | 7.3185 | 17.5379 | 0.6920 |
| candidate | holdout | 26 | 0.0000 | 609 | 7.2871 | 6.2147 | 19.2657 | 0.6617 |
| baseline | development | 26 | 0.0000 | 851 | 6.9651 | 6.5759 | 14.1138 | 0.7203 |
| baseline | validation | 26 | 0.0000 | 463 | 6.8061 | 6.6186 | 17.0249 | 0.6760 |
| baseline | holdout | 26 | 0.0000 | 555 | 6.9488 | 6.1519 | 18.6628 | 0.6523 |
| candidate | development | 26 | 10.0000 | 922 | 6.8235 | 7.0398 | 14.2549 | 0.7148 |
| candidate | validation | 26 | 10.0000 | 500 | 7.0457 | 7.1041 | 17.5028 | 0.6900 |
| candidate | holdout | 26 | 10.0000 | 609 | 7.0728 | 6.0025 | 19.2272 | 0.6568 |
| baseline | development | 26 | 10.0000 | 851 | 6.7514 | 6.3629 | 14.0856 | 0.7156 |
| baseline | validation | 26 | 10.0000 | 463 | 6.5927 | 6.4056 | 16.9909 | 0.6760 |
| baseline | holdout | 26 | 10.0000 | 555 | 6.7351 | 5.9399 | 18.6255 | 0.6468 |
| candidate | development | 26 | 25.0000 | 922 | 6.5035 | 6.7191 | 14.2122 | 0.7093 |
| candidate | validation | 26 | 25.0000 | 500 | 6.7250 | 6.7832 | 17.4504 | 0.6740 |
| candidate | holdout | 26 | 25.0000 | 609 | 6.7520 | 5.6850 | 19.1696 | 0.6519 |
| baseline | development | 26 | 25.0000 | 851 | 6.4316 | 6.0443 | 14.0434 | 0.7062 |
| baseline | validation | 26 | 25.0000 | 463 | 6.2734 | 6.0869 | 16.9400 | 0.6695 |
| baseline | holdout | 26 | 25.0000 | 555 | 6.4154 | 5.6225 | 18.5697 | 0.6414 |

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
| BA | baseline | development | 27 | 21 | 273 |
| BA | baseline | holdout | 12 | 11 | 143 |
| BA | baseline | validation | 18 | 10 | 130 |
| BA | candidate | development | 34 | 23 | 299 |
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
| DIA | candidate | validation | 22 | 13 | 169 |
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
| HON | baseline | development | 25 | 24 | 312 |
| HON | baseline | holdout | 13 | 13 | 169 |
| HON | baseline | validation | 14 | 13 | 169 |
| HON | candidate | development | 25 | 24 | 312 |
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
| JNJ | baseline | development | 24 | 22 | 286 |
| JNJ | baseline | holdout | 16 | 16 | 208 |
| JNJ | baseline | validation | 18 | 12 | 156 |
| JNJ | candidate | development | 37 | 23 | 299 |
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
| KO | candidate | development | 28 | 23 | 299 |
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
| UPS | baseline | validation | 25 | 11 | 143 |
| UPS | candidate | development | 36 | 23 | 299 |
| UPS | candidate | holdout | 12 | 11 | 143 |
| UPS | candidate | validation | 16 | 12 | 156 |
| WMT | baseline | development | 22 | 20 | 260 |
| WMT | baseline | holdout | 17 | 16 | 208 |
| WMT | baseline | validation | 17 | 12 | 156 |
| WMT | candidate | development | 29 | 21 | 273 |
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
| XLP | candidate | development | 27 | 24 | 312 |
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
| XOM | baseline | development | 20 | 18 | 234 |
| XOM | baseline | holdout | 16 | 15 | 195 |
| XOM | baseline | validation | 14 | 8 | 104 |
| XOM | candidate | development | 27 | 23 | 299 |
| XOM | candidate | holdout | 18 | 17 | 221 |
| XOM | candidate | validation | 17 | 11 | 143 |

## Bootstrap (paired candidate-minus-baseline, ticker-year clusters)

| split | rule_pair | horizon_weeks | slippage_bps | count | cluster_count | mean_diff_pct | ci_lower | ci_upper |
|---|---|---|---|---|---|---|---|---|
| development | candidate_minus_baseline | 13 | 5.0000 | 1832 | 294 | 0.1807 | -0.3049 | 0.6630 |
| holdout | candidate_minus_baseline | 13 | 5.0000 | 1229 | 209 | 0.4797 | -0.3737 | 1.3293 |
| validation | candidate_minus_baseline | 13 | 5.0000 | 1023 | 168 | 1.1199 | 0.2140 | 2.1294 |

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