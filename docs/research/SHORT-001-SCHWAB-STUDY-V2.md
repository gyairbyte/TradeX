# Short-Term Market Context Study

## 1. Study identity
- Study: SHORT-001 Schwab real-data panel v2
- Artifact: docs/research/artifacts/SHORT-001/2026-08-07-e5b64b56
- Manifest: docs/research/artifacts/SHORT-001/2026-08-07-e5b64b56/snapshot/manifest.json
- Generated: 2026-08-07T01:13:42.300026+00:00

## 2. Dataset provenance
The study used manifest-locked offline OHLCV snapshots. Every input CSV was verified by SHA-256 before analysis.

## 3. Manifest checksum
- Manifest SHA-256: `e5b64b56328c4de588ff7b126f8aedd73c81951b61bde915b7e410afb1f6813b`

## 4. Context-spec checksum
- Context-spec SHA-256: `5ae8a420be97d3665c48ed82401cb4d9b0f0d71610898b7036f72453755acb45`

## 5. Ingestion policy and cleaning audit
- Ingestion policy ID: `short-001-hard-invalid-row-exclusion-v2`
- Ingestion-spec SHA-256: `f9a3f473fe14620984caca34cd6386000b87fea47a44e32d83bd05852c3ef23e`
- Provider: `schwab`
- Price repair: `False`
- Raw total rows: `82035`
- Cleaned total rows: `82012`
- Invalid rows removed: `23`
- Total invalid row rate (%): `0.028037`
- Affected symbols: `19`
- Max invalid rows per symbol: `4`
- Max consecutive invalid rows: `1`
- Threshold result: `passed`
- Removed-row reason summary:
  - `high_below_open`: 11
  - `low_above_close`: 5
  - `low_above_open`: 7

## 6. Target universe
- Targets: AAPL, MSFT, NVDA, GOOGL, META, VZ, AMZN, HD, MCD, WMT, COST, PG, JPM, BAC, GS, JNJ, UNH, MRK, CAT, HON, UPS, XOM, CVX, COP, NEE, DUK, SO, LIN, APD, NEM, AMT, PLD, SPG
- Target count: 33

## 7. Proxy mappings
- AAPL: market=SPY, sector=XLK
- MSFT: market=SPY, sector=XLK
- NVDA: market=SPY, sector=XLK
- GOOGL: market=SPY, sector=XLC
- META: market=SPY, sector=XLC
- VZ: market=SPY, sector=XLC
- AMZN: market=SPY, sector=XLY
- HD: market=SPY, sector=XLY
- MCD: market=SPY, sector=XLY
- WMT: market=SPY, sector=XLP
- COST: market=SPY, sector=XLP
- PG: market=SPY, sector=XLP
- JPM: market=SPY, sector=XLF
- BAC: market=SPY, sector=XLF
- GS: market=SPY, sector=XLF
- JNJ: market=SPY, sector=XLV
- UNH: market=SPY, sector=XLV
- MRK: market=SPY, sector=XLV
- CAT: market=SPY, sector=XLI
- HON: market=SPY, sector=XLI
- UPS: market=SPY, sector=XLI
- XOM: market=SPY, sector=XLE
- CVX: market=SPY, sector=XLE
- COP: market=SPY, sector=XLE
- NEE: market=SPY, sector=XLU
- DUK: market=SPY, sector=XLU
- SO: market=SPY, sector=XLU
- LIN: market=SPY, sector=XLB
- APD: market=SPY, sector=XLB
- NEM: market=SPY, sector=XLB
- AMT: market=SPY, sector=XLRE
- PLD: market=SPY, sector=XLRE
- SPG: market=SPY, sector=XLRE

## 8. Existing baseline score
The existing short-term component score and weights were not changed.
- Baseline score threshold: 40
- Weight snapshot: {
  "short_term": {
    "source": "explicit ShortWeights() default",
    "weights": {
      "ema_structure": 25,
      "volume_confirmation": 20,
      "rsi_momentum": 20,
      "macd_positive": 20,
      "pullback_ema": 15
    }
  }
}

## 9. Context formulas
- Bullish market regime: close > EMA20, EMA20 > EMA50, EMA20 today > EMA20 five bars earlier.
- Bullish sector regime: same rule on the sector proxy.
- Market relative strength: ticker_close / market_close; positive when ratio > EMA20(ratio) and 20-bar change > 0.
- Sector relative strength: ticker_close / sector_close; same rule.

## 10. Point-in-time alignment
- Context is computed from the most recent market/sector bar <= signal time.
- Context is rejected as stale when it is more than one expected trading session behind.
- Future market, sector, or ticker rows cannot influence an earlier context.

## 11. Candidate policies
- Candidate policies: ['market_rs', 'market_sector_rs']

## 12. Development results
| split | policy | event_count | baseline_event_count | retention_pct | unique_tickers | baseline_unique_tickers | coverage_pct | mean_net_return_pct | median_net_return_pct | positive_return_rate_pct | mean_ticker_event_return_pct | median_ticker_event_return_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development | baseline | 13948 | 13948 | 100.0000 | 33 | 33 | 100.0000 | 0.0434 | 0.0668 | 51.2690 | 0.0267 | 0.0254 |
| development | market_rs | 6163 | 13948 | 44.1855 | 33 | 33 | 100.0000 | 0.0376 | 0.0769 | 51.6794 | 0.0049 | -0.0305 |
| development | market_sector_rs | 5158 | 13948 | 36.9802 | 33 | 33 | 100.0000 | -0.0053 | 0.0338 | 50.5622 | -0.0613 | -0.1246 |

## 13. Validation results
| split | policy | event_count | baseline_event_count | retention_pct | unique_tickers | baseline_unique_tickers | coverage_pct | mean_net_return_pct | median_net_return_pct | positive_return_rate_pct | mean_ticker_event_return_pct | median_ticker_event_return_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation | baseline | 7142 | 7142 | 100.0000 | 33 | 33 | 100.0000 | 0.0516 | 0.0896 | 51.5542 | 0.0338 | -0.0614 |
| validation | market_rs | 2163 | 7142 | 30.2856 | 33 | 33 | 100.0000 | 0.1232 | 0.0529 | 51.2714 | 0.0470 | 0.0579 |
| validation | market_sector_rs | 1519 | 7142 | 21.2686 | 33 | 33 | 100.0000 | 0.1304 | -0.0006 | 49.9671 | -0.0402 | 0.0289 |

## 14. Candidate selection
- Selected policy: none
- Selection reason: no policy passed development and validation criteria

## 15. Holdout event-study results
No holdout evaluation performed.
Failed criteria:
- no candidate selected

## 16. Holdout paired-backtest results
| ticker | total_trades_baseline | expectancy_pct_baseline | total_return_pct_baseline | profit_factor_baseline | max_drawdown_pct_baseline | sharpe_ratio_baseline | total_trades_candidate | expectancy_pct_candidate | total_return_pct_candidate | profit_factor_candidate | max_drawdown_pct_candidate | sharpe_ratio_candidate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | 93 | -0.2487 | -23.3935 | 0.7514 | -31.5266 | -0.7167 |  |  |  |  |  |  |
| AMT | 74 | -0.0381 | -5.2948 | 0.9366 | -20.8332 | -0.1080 |  |  |  |  |  |  |
| AMZN | 107 | -0.0662 | -10.5825 | 0.9150 | -30.0576 | -0.1534 |  |  |  |  |  |  |
| APD | 81 | -0.2661 | -21.2535 | 0.7450 | -27.5853 | -0.8401 |  |  |  |  |  |  |
| BAC | 120 | 0.1203 | 12.4738 | 1.1187 | -16.9348 | 0.4483 |  |  |  |  |  |  |
| CAT | 112 | 0.0002 | -4.4051 | 0.9626 | -41.1003 | 0.0037 |  |  |  |  |  |  |
| COP | 64 | -0.8303 | -42.4974 | 0.4451 | -45.8303 | -1.8221 |  |  |  |  |  |  |
| COST | 91 | 0.1124 | 8.5292 | 1.1041 | -18.0568 | 0.3531 |  |  |  |  |  |  |
| CVX | 90 | -0.3608 | -29.2214 | 0.6276 | -30.5612 | -1.1918 |  |  |  |  |  |  |
| DUK | 100 | -0.0085 | -2.2635 | 0.9663 | -12.6558 | -0.0350 |  |  |  |  |  |  |
| GOOGL | 118 | 0.5180 | 75.0248 | 1.5738 | -18.8707 | 1.3092 |  |  |  |  |  |  |
| GS | 134 | 0.2080 | 27.9198 | 1.2317 | -11.3826 | 0.7553 |  |  |  |  |  |  |
| HD | 85 | 0.0202 | -0.3469 | 0.9953 | -17.1959 | 0.0551 |  |  |  |  |  |  |
| HON | 80 | -0.3768 | -27.3837 | 0.6006 | -27.3837 | -1.1714 |  |  |  |  |  |  |
| JNJ | 95 | 0.1574 | 14.5827 | 1.2609 | -11.9703 | 0.6128 |  |  |  |  |  |  |
| JPM | 130 | 0.1911 | 24.5471 | 1.2231 | -10.5439 | 0.7422 |  |  |  |  |  |  |
| LIN | 93 | -0.0454 | -5.1277 | 0.9103 | -19.3532 | -0.1990 |  |  |  |  |  |  |
| MCD | 87 | -0.2350 | -20.0056 | 0.7101 | -22.5123 | -0.7267 |  |  |  |  |  |  |
| META | 105 | -0.1008 | -13.7598 | 0.8939 | -34.1884 | -0.2317 |  |  |  |  |  |  |
| MRK | 73 | -0.2780 | -20.5488 | 0.7355 | -38.7541 | -0.6719 |  |  |  |  |  |  |
| MSFT | 85 | 0.1284 | 9.1372 | 1.1295 | -18.1216 | 0.3668 |  |  |  |  |  |  |
| NEE | 87 | 0.0158 | -1.3157 | 0.9854 | -24.3937 | 0.0561 |  |  |  |  |  |  |
| NEM | 122 | 0.6668 | 110.2322 | 1.5824 | -16.1893 | 1.5103 |  |  |  |  |  |  |
| NVDA | 112 | 0.4438 | 46.1124 | 1.1571 | -44.8074 | 0.7577 |  |  |  |  |  |  |
| PG | 81 | -0.1771 | -14.2126 | 0.7425 | -20.5530 | -0.6284 |  |  |  |  |  |  |
| PLD | 93 | -0.1521 | -15.0537 | 0.8027 | -24.3797 | -0.4685 |  |  |  |  |  |  |
| SO | 101 | 0.0831 | 6.9471 | 1.0908 | -16.2658 | 0.3175 |  |  |  |  |  |  |
| SPG | 114 | -0.1175 | -14.3809 | 0.8268 | -23.2299 | -0.3937 |  |  |  |  |  |  |
| UNH | 72 | -0.4359 | -29.5411 | 0.6602 | -32.7278 | -0.9495 |  |  |  |  |  |  |
| UPS | 59 | -0.9049 | -43.2923 | 0.3787 | -48.7380 | -1.5750 |  |  |  |  |  |  |
| VZ | 92 | -0.1727 | -16.9054 | 0.8143 | -29.8015 | -0.5195 |  |  |  |  |  |  |
| WMT | 128 | 0.3196 | 46.2884 | 1.4098 | -14.1917 | 1.2530 |  |  |  |  |  |  |
| XOM | 96 | -0.2382 | -21.9766 | 0.7123 | -33.0577 | -0.7895 |  |  |  |  |  |  |
Failed executable-backtest criteria:
- no candidate backtest results

## 17. Event retention

## 18. Ticker coverage

## 19. Per-ticker robustness
No per-ticker comparison available.

## 20. Data-quality warnings
| ticker | data_source | sha256 | manifest_rows | validated_rows | data_start | data_end | duplicate_timestamps | missing_required_values | invalid_ohlc_rows | complete_1_bar_outcomes | complete_3_bar_outcomes | complete_5_bar_outcomes | warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | schwab | a6ece596957849348abaff49baace0c406cd4be9c5db2056db90a76498ab8d90 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| MSFT | schwab | a99c1d58bd9e7e48be479c95cc22878bc00ad9ad3a3b8d242cb31f99e38a8781 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| NVDA | schwab | b388c737906db743f0f1d917033fffc7ab66874af2e62c226b1e2b9fd1e13266 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| GOOGL | schwab | 4a2f6bc515129d5ff3ff3e7c2f8d9f808d94184ff65153f7507d7207c8c41b81 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| META | schwab | 674c975ae53cb034436f423b6f35a73513f63235ca48d903970dfeb024bd9f0d | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| VZ | schwab | bac5b6d4d9acb033caafd2470bf4963fa1c6e019e6be38754c6f084fc900525e | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| AMZN | schwab | f55b22a8efe45fdeb2f01c22949cd8c75e4c99d79f8a929423dc5c546161151d | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| HD | schwab | f57d91e777f965ecd72457e5ce807fc635fe1bf4d53f7e929b3e2c8315a9c711 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| MCD | schwab | 228683e708cf16ff09500bf8383141210ea2c05da89e8d69b1a04b30008a0fba | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| WMT | schwab | b37e9e908a1b7ce7078e1b490dc634b25070da81dc0730f01cbce4b8d5aa2b82 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| COST | schwab | 35630f0af607034ccdda0a80e3842851bb1904eaf0af93f40901175b3eb22062 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| PG | schwab | 1092bc70a93968c85abed55a3de7081031460b975b2fe92571cd014b3677fa03 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| JPM | schwab | 3f4f111a5e8c07157f425acaac6f765ff109e46c26b0b485210704fa02e13eb9 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| BAC | schwab | 8129d0dc41c034d3857149afd0904df21cc1454c6563a918feadbe48ad3fbf4b | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| GS | schwab | 20190bb738b24535c9bd330b8c96444fd1a5f1c329ce05814f199ccd47c5d21a | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| JNJ | schwab | 99364d14da535fa8ad22c28ebfdcd8aeffba5188ebcd8f4babd4ff5d8834881c | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| UNH | schwab | 1dad1dfaa41c892167548225611dccf077b8154f0d0ca39f75edd849c9566ec6 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| MRK | schwab | efe0a595f488ccd68f83c843fdc0e317133687a392fbf72202a5ff6719c6ce45 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| CAT | schwab | 380e14a9e9cf075b92f1f36e1a05930868c82e9614fd6cbb888b7803aac42754 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| HON | schwab | b1d444ad7bf0dd55dad63dd04ad3aedacc178dba1cd014cbb9f0440527ea6d3c | 1819 | 1819 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1754 | 1748 | 1742 | [] |
| UPS | schwab | ab730aab3b599b59351c9e81dd640ffa79a77d5dc5cd790159ccf1e7c5faed2d | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| XOM | schwab | 87c86009e1be1bc2161046f638b31c7122542e2c17ae3adadd0d6c7722aadb40 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| CVX | schwab | 6a9753068d800fdd2ff03234ba8035b2e60bdc7970c3e7602e98dae318809ec5 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| COP | schwab | 109a967f61b7ac9bbad71c8118da45edd361247fb31f37edb1598bb396d07226 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| NEE | schwab | 2fff50e9048920199e7210633726fc164eb8eb19d955a9be934e6b764cc06148 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| DUK | schwab | a6175c4f15d1d3514b17b9abebdd2bef5f3e0a2ac994376e612952dd9963e890 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| SO | schwab | b77af375d4f0885e18bf2d55736b24ae79e56d19afdb20f83fc73509c2538874 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| LIN | schwab | 3c972dd67e196d4c023daebe4705abd6deca9a962ff04312f3b2dbb424cb2451 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| APD | schwab | 07c6b80ee734bd3477e0bbf288aafd55c0f82c30f37362872e14579a8c667c79 | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| NEM | schwab | 28f5642a8e3f418c362fc0e0f902a885416938bfdaa6b82994cbf39bd2a00d4f | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| AMT | schwab | da3ed427d4e868c8ee9f17e82667a2a284557f8e02944b3045ef348bd1bc854d | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |
| PLD | schwab | afa1d5a988b5271abde49dc5568a64451d737cd8eda1a54f3468f836267e4a1c | 1822 | 1822 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1756 | 1750 | 1744 | [] |
| SPG | schwab | a6b4f8b4c7a0f36c04d0dcdfecce1d2d52d0f8da2594f2701a55c0af1d73b038 | 1823 | 1823 | 2018-10-01T05:00:00+00:00 | 2025-12-31T06:00:00+00:00 | 0 | 0 | 0 | 1757 | 1751 | 1745 | [] |

## 21. Survivorship and provider limitations
- The dataset does not eliminate survivorship bias, delisting bias, or point-in-time index membership.
- Corporate actions, provider adjustments, retroactive splits, and liquidity capacity are not modeled.
- Sector mappings are provided by the context specification, not inferred dynamically.

## 22. Promotion criteria
Event-study gate:
- Holdout events >= minimum, tickers >= minimum, retention >= minimum, coverage >= minimum.
- Candidate mean, equal-weighted per-ticker mean, median, and positive rate must meet baseline comparisons.
- Improvement must not be produced by only one ticker; at least half of represented tickers must improve.
Executable-backtest gate:
- Median and mean expectancy must exceed baseline; median total return not lower; drawdown not worse by >2pp.

## 23. Promotion decision
The context policy did not pass the predefined promotion gate and was not exposed to production.
- Event-study holdout gate failed.
- Executable-backtest holdout gate failed.

## 24. Production behavior
- The production default remains `off`.
- No short-term component condition, weight, or threshold was changed.

## 25. Research limitations
- Events may overlap and are not independent.
- Event-study averages are not portfolio returns.
- Results are descriptive evidence, not proof of a durable edge, statistical significance, or profitability.
