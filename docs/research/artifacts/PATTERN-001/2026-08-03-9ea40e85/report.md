# Pattern Similarity Validation Study Report

**Dataset:** `pattern-similarity-validation`  
**Provider:** `schwab`  
**Profile:** `standard`  
**Study range:** `2018-01-02` to `2026-07-31`  
**Study mode:** `locked PATTERN-001 contract`  
**Generated:** `2026-08-04T01:12:11.616408+00:00`  

## Hypothesis

For the fixed study cohort and unchanged standard-profile matcher, decision dates with
similarity at or above 75 have higher signed five-session returns than deterministic
frequency-matched controls after conservative execution costs.

- Run-up modeled as long; positive signed return means price rose.
- Decline modeled as short; positive signed return means price fell.

## Universe and Selection Bias

- **Universe:** fixed convenience cohort of 44 tickers.
- This is **not** a point-in-time S&P 500 or Nasdaq-100 universe.
- Survivorship and selection bias are present and disclosed.
- Universe hash: `554c6933750be1f10716ce45912e70ff6c963cc190157f730ef1d7ddbd850404`

## Methodology

Similarity is computed as a weighted Pearson correlation between the live pre-event
window and the stored fingerprint. Correlation measures shape resemblance, not
causality or expected return. A similarity of 75 is the existing fixed display cutoff
used in this study; it is not a validated trading threshold.

## Locked Study Parameters

- Similarity threshold: `75.0`
- Lookback days: `10`
- Move days / holding days: `5` / `5`
- Run-up threshold: `+15.0%`; decline threshold: `-12.0%`
- Series weights: `{'bb_width': 0.1, 'macd_diff': 0.1, 'price_pct': 0.35, 'rsi': 0.15, 'volume_ratio': 0.3}`
- Cost scenario for evidence decision: `10.0` bps per side
- Commission: `0.0` bps
- Bootstrap: `ticker-cluster`, 5000 resamples, seed `20260803`

## Data Snapshot

- Requested tickers: 44
- Successful: 44
- Failed: 0 (none)
- Request date range: `2018-01-02` to `2026-07-31`
- Provider adjustment policy: `provider_default` (provider-returned candles used as-is; no additional adjustment or independent corporate-action verification)

## Development Fingerprints

- `decline`: 322 events across 42 tickers
  - lookback: 10 days
  - config hash: `9c711ca56a2895121eeecf5a056c12bf300fd9d347d49d9e585807572189c1be`
  - fingerprint hash: `35c632dcb4b5f245851c111dfb05c3a8d1cf6633c07741f89a54e273ed3e3ba1`
- `runup`: 274 events across 41 tickers
  - lookback: 10 days
  - config hash: `9c711ca56a2895121eeecf5a056c12bf300fd9d347d49d9e585807572189c1be`
  - fingerprint hash: `dfda89180393330da667f005db90cb1d0b49e80b37ea6a4982b13ab9030661e9`

## Period Metrics

### Development — decline

- Eligible observations: 0
- Qualifying signals (≥ 75.0): 0
- Executed trades: 0
- Tickers represented: 0
- Date coverage: `None` to `None`
- Mean similarity: N/A
- Mean gross return: N/A
- Mean net return: N/A
- Median net return: N/A
- Win rate: N/A
- Mean net return (executable trades): N/A
- Win rate (executable trades): N/A
- Baseline mean return: N/A
- Lift over baseline: N/A
- Lift CI: N/A
- Mean return CI: N/A
- Max ticker concentration: N/A
- Max contribution concentration: N/A
- Overlapping signals: 0
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 0

#### Returns by slippage scenario

- 0 bps/side: N/A
- 10 bps/side: N/A
- 5 bps/side: N/A

### Development — runup

- Eligible observations: 0
- Qualifying signals (≥ 75.0): 0
- Executed trades: 0
- Tickers represented: 0
- Date coverage: `None` to `None`
- Mean similarity: N/A
- Mean gross return: N/A
- Mean net return: N/A
- Median net return: N/A
- Win rate: N/A
- Mean net return (executable trades): N/A
- Win rate (executable trades): N/A
- Baseline mean return: N/A
- Lift over baseline: N/A
- Lift CI: N/A
- Mean return CI: N/A
- Max ticker concentration: N/A
- Max contribution concentration: N/A
- Overlapping signals: 0
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 0

#### Returns by slippage scenario

- 0 bps/side: N/A
- 10 bps/side: N/A
- 5 bps/side: N/A

### Holdout — decline

- Eligible observations: 26620
- Qualifying signals (≥ 75.0): 2341
- Executed trades: 868
- Tickers represented: 44
- Date coverage: `2024-03-04` to `2026-07-24`
- Mean similarity: 80.65
- Mean gross return: -0.7777%
- Mean net return at 10.0 bps/side: -0.9794%
- Median net return: -0.8578%
- Win rate: 41.18%
- Mean net return (non-overlapping executable trades): -0.9428%
- Win rate (executable trades): 41.82%
- Baseline mean return: -0.7655%
- Lift over baseline: -21.393567 bps
- Lift CI (2.5%-97.5%): [-54.0786, 12.5567]
- Mean return CI (2.5%-97.5%): [-1.3043, -0.6688]
- Max ticker concentration: 3.16%
- Max contribution concentration: 7.30%
- Overlapping signals: 1631
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 220

#### Returns by slippage scenario

- 0 bps/side: mean=-0.7777%, median=-0.6562%, win_rate=43.02%
- 10 bps/side: mean=-0.9794%, median=-0.8578%, win_rate=41.18%
- 5 bps/side: mean=-0.8785%, median=-0.7570%, win_rate=42.20%

### Holdout — runup

- Eligible observations: 26620
- Qualifying signals (≥ 75.0): 234
- Executed trades: 203
- Tickers represented: 44
- Date coverage: `2024-03-05` to `2026-07-20`
- Mean similarity: 77.80
- Mean gross return: 0.4594%
- Mean net return at 10.0 bps/side: 0.2586%
- Median net return: -0.1478%
- Win rate: 49.15%
- Mean net return (non-overlapping executable trades): 0.2847%
- Win rate (executable trades): 49.26%
- Baseline mean return: 0.1563%
- Lift over baseline: 10.238333 bps
- Lift CI (2.5%-97.5%): [-103.2203, 124.5152]
- Mean return CI (2.5%-97.5%): [-0.8178, 1.3960]
- Max ticker concentration: 5.56%
- Max contribution concentration: 127.23%
- Overlapping signals: 31
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 220

#### Returns by slippage scenario

- 0 bps/side: mean=0.4594%, median=0.0521%, win_rate=51.28%
- 10 bps/side: mean=0.2586%, median=-0.1478%, win_rate=49.15%
- 5 bps/side: mean=0.3590%, median=-0.0479%, win_rate=49.57%

### Validation — decline

- Eligible observations: 19757
- Qualifying signals (≥ 75.0): 1816
- Executed trades: 651
- Tickers represented: 43
- Date coverage: `2022-03-04` to `2023-12-21`
- Mean similarity: 80.93
- Mean gross return: -1.1408%
- Mean net return at 10.0 bps/side: -1.3433%
- Median net return: -0.8539%
- Win rate: 41.52%
- Mean net return (non-overlapping executable trades): -0.9891%
- Win rate (executable trades): 44.39%
- Baseline mean return: -0.3569%
- Lift over baseline: -98.634383 bps
- Lift CI (2.5%-97.5%): [-151.2942, -45.9006]
- Mean return CI (2.5%-97.5%): [-1.8090, -0.8379]
- Max ticker concentration: 3.30%
- Max contribution concentration: 8.90%
- Overlapping signals: 1296
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 220

#### Returns by slippage scenario

- 0 bps/side: mean=-1.1408%, median=-0.6524%, win_rate=43.23%
- 10 bps/side: mean=-1.3433%, median=-0.8539%, win_rate=41.52%
- 5 bps/side: mean=-1.2420%, median=-0.7531%, win_rate=42.57%

### Validation — runup

- Eligible observations: 19757
- Qualifying signals (≥ 75.0): 170
- Executed trades: 150
- Tickers represented: 42
- Date coverage: `2022-03-04` to `2023-12-18`
- Mean similarity: 77.63
- Mean gross return: 0.1285%
- Mean net return at 10.0 bps/side: -0.0716%
- Median net return: -0.4218%
- Win rate: 45.29%
- Mean net return (non-overlapping executable trades): -0.1124%
- Win rate (executable trades): 44.67%
- Baseline mean return: -0.1423%
- Lift over baseline: 7.072294 bps
- Lift CI (2.5%-97.5%): [-95.6130, 123.8220]
- Mean return CI (2.5%-97.5%): [-0.9617, 0.8318]
- Max ticker concentration: 6.47%
- Max contribution concentration: 247.22%
- Overlapping signals: 20
- Frequency-matched controls underfilled: False
- Missing/insufficient data observations: 220

#### Returns by slippage scenario

- 0 bps/side: mean=0.1285%, median=-0.2225%, win_rate=47.65%
- 10 bps/side: mean=-0.0716%, median=-0.4218%, win_rate=45.29%
- 5 bps/side: mean=0.0284%, median=-0.3222%, win_rate=45.29%

## Promotion Decision

**Classification:** `rejected`
**Production promotion eligible:** `False`
**Reason:** runup/validation_mean_net_return_positive: validation mean net return not positive (-0.071576); runup/validation_mean_ci_above_zero: validation mean return CI lower bound not above zero (-0.961742); runup/holdout_mean_ci_above_zero: holdout mean return CI lower bound not above zero (-0.817804); runup/validation_lift_threshold: validation lift below 25.0 bps (7.072294); runup/holdout_lift_threshold: holdout lift below 25.0 bps (10.238333); runup/validation_lift_ci_above_zero: validation lift CI lower bound not above zero (-95.613019); runup/holdout_lift_ci_above_zero: holdout lift CI lower bound not above zero (-103.22027); runup/validation_pct_tickers_positive_lift: fewer than 55% of validation tickers have positive lift (0.52381); runup/holdout_pct_tickers_positive_lift: fewer than 55% of holdout tickers have positive lift (0.545455); runup/holdout_second_half_positive: holdout second-half mean net return not positive (-0.758034); decline/validation_mean_net_return_positive: validation mean net return not positive (-1.343259); decline/holdout_mean_net_return_positive: holdout mean net return not positive (-0.979449); decline/validation_mean_ci_above_zero: validation mean return CI lower bound not above zero (-1.80899); decline/holdout_mean_ci_above_zero: holdout mean return CI lower bound not above zero (-1.304289); decline/validation_lift_threshold: validation lift below 25.0 bps (-98.634383); decline/holdout_lift_threshold: holdout lift below 25.0 bps (-21.393567); decline/validation_lift_ci_above_zero: validation lift CI lower bound not above zero (-151.294198); decline/holdout_lift_ci_above_zero: holdout lift CI lower bound not above zero (-54.078555); decline/validation_median_ticker_lift_positive: validation median ticker-level lift not positive (-96.889); decline/holdout_median_ticker_lift_positive: holdout median ticker-level lift not positive (-39.37815); decline/validation_pct_tickers_positive_lift: fewer than 55% of validation tickers have positive lift (0.232558); decline/holdout_pct_tickers_positive_lift: fewer than 55% of holdout tickers have positive lift (0.386364); decline/holdout_first_half_positive: holdout first-half mean net return not positive (-1.007619); decline/holdout_second_half_positive: holdout second-half mean net return not positive (-0.939912)

## Limitations and Disclosures

- This is a research study, not a live-trading recommendation.
- The universe is a fixed convenience cohort and is not point-in-time; survivorship and selection bias are present.
- Execution assumptions use next-open entry and fifth-close exit with conservative slippage but no borrow fees or borrow-availability constraints for shorts.
- Results depend on the market-data provider's returned daily candles; no additional split or dividend adjustment is applied, and the provider's exact corporate-action methodology is not independently verified.

## Research Safeguards

- Development fingerprints were built only from the development split.
- Validation and holdout observations used the immutable development fingerprint.
- Point-in-time correctness was enforced: only bars available through the decision date were used for similarity.
- Forward returns did not cross split boundaries.
- The frequency-matched baseline was selected deterministically with the locked seed.
- Automatic pattern-match alerts were removed; the matcher output and dashboard tab are labeled experimental research only.
- No production scores, rankings, eligibility, thresholds, or weights were changed.
