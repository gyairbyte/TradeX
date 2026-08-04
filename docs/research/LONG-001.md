# LONG-001: Long-Term Scorer Research Protocol

This file records the approved, machine-readable research protocol for the
LONG-001 evaluation. The canonical locked protocol is stored in
[`LONG-001.json`](./LONG-001.json). Any research artifact must reference the
SHA-256 and lock commit of that file.

## Pre-registration authority

Approved in **PR #25 comment `5182648133`**.

## Objective

Compare the current production `tradex/signals/long_term.score` (using a fresh
`LongWeights()` instance and the default threshold of 40) against a simple
`close > 40-week simple moving average` baseline on weekly OHLCV bars.

This is a **research-only** evaluation. It does not authorize production changes.

## Falsifiable hypothesis

On the locked universe and weekly dataset defined below, the production long-term
score produces better out-of-sample 13-week net outcomes than the simple 40-week
MA baseline, without materially worse downside or narrow ticker dependence.

## Locked study design

### Universe

**Large-cap equity cohort (30):**

`AAPL, MSFT, AMZN, GOOGL, NVDA, JPM, BAC, GS, XOM, CVX, JNJ, MRK, PFE, UNH, PG, KO, WMT, COST, HD, CAT, HON, IBM, CSCO, ORCL, MCD, NKE, DIS, BA, MMM, UPS`

**Equity-ETF robustness cohort (12):**

`QQQ, IWM, DIA, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY`

**Benchmark (not a candidate):** `SPY`

The fixed large-cap cohort has survivorship and selection bias and cannot by
itself support production promotion.

### Data source

- Provider: Yahoo Finance through `fetch_daily_history(..., provider='yahoo')`
- Adjustment: `auto_adjust=True` (provider-adjusted close)
- Raw requested daily range: `2007-01-01` through `2025-12-19`, inclusive
- No 2026 data
- Weekly bars are built from completed XNYS trading weeks only:
  - open: first session open
  - high: maximum session high
  - low: minimum session low
  - close: final session close
  - volume: sum of session volume
  - label: actual final XNYS session timestamp for that week
  - holiday-shortened weeks handled correctly
  - incomplete trailing weeks dropped
  - no forward-fill or zero substitution

### Temporal periods

Signal dates define the split:

| Split | Start | End |
|---|---|---|
| Warm-up | `2007-01-01` | `2009-12-31` |
| Development | `2010-01-01` | `2016-12-31` |
| Validation | `2017-01-01` | `2020-12-31` |
| Untouched holdout | `2021-01-01` | `2025-12-19` |

No event or trade may enter or exit across split boundaries.

### Candidate and baseline definitions

**Candidate (production long-term score):**

- Call `long_term.score()` with an explicit fresh `LongWeights()` instance.
- Do not load saved user weights.
- Eligibility: `score >= 40`.
- At least 60 weekly bars of history before the first scored bar.

**Baseline (40-week simple moving average):**

- At the same weekly decision point, compute a 40-week simple moving average
  using only bars available through that week.
- Eligibility: `close > SMA40`.
- Require 40 observed weekly closes; no backfill or future data.

### Execution timing

- Signal is known after the completed weekly close.
- Entry is the next completed week’s open.
- Primary exit is the close of the 13th held week.
- Secondary exit is the close of the 26th held week (sensitivity only).

### Costs

- Commission: `0` bps
- Entry slippage: `5` bps per side
- Exit slippage: `5` bps per side
- Predefined cost sensitivity: `0`, `10`, and `25` bps per side

### Two analyses

1. **Overlapping event study**: every eligible candidate and baseline observation
   is recorded. Entry at next-week open, exit at horizon close. Events may
   overlap.
2. **Non-overlapping per-ticker policy simulation**: one active position per
   ticker. Enter at next-week open, ignore additional signals while active, exit
   at the primary 13-week close. Repeat for the 26-week sensitivity.

## Outcome criteria

Valid classifications: `supports_further_research`, `reject_or_deprioritize`,
`inconclusive`.

### Supports further research

On the untouched holdout, all of the following must be true:

1. At least 200 non-overlapping candidate trades and 200 baseline trades across
   at least 20 stock tickers and 8 ETF tickers.
2. Candidate 13-week net expectancy exceeds baseline by at least
   `0.50` percentage points.
3. The 95% cluster-bootstrap CI lower bound for candidate-minus-baseline
   expectancy is above zero.
4. Candidate 10th-percentile net return is not worse than baseline by more than
   `1.00` percentage point.
5. Candidate-minus-baseline expectancy is positive for at least 60% of
   sufficiently sampled stock tickers and 60% of ETF tickers.
6. Pooled candidate-minus-baseline expectancy remains positive at 25 bps per
   side.
7. Validation-period direction is also positive.

This classification authorizes only a broader, point-in-time constituent
study.

### Reject or deprioritize

Either:

- Holdout 95% CI upper bound is at or below zero; or
- Holdout point estimate is at least `0.50` percentage points worse than
  baseline; or
- Downside is more than `2.00` percentage points worse with no compensating
  expectancy improvement.

### Inconclusive

All other cases, including inadequate sample size, unstable cohort results,
material data-quality limitations, or a confidence interval crossing zero.

## Machine-readable protocol

See [`LONG-001.json`](./LONG-001.json). It contains the exact universe, dates,
splits, thresholds, buckets, costs, bootstrap settings, weight snapshot, and
conclusion boundaries. Study artifacts must record its SHA-256 and the commit
that first added it.

## Limitations

- Weekly events may overlap.
- The non-overlapping policy does not model capital allocation or position
  sizing.
- Execution assumes next-week open / horizon close; intraday slippage and
  partial fills are not modeled.
- No stops, targets, or capacity assumptions.
- Survivorship, delisting, and index-membership biases are not eliminated.
- Provider-adjusted data uses Yahoo's default corporate-action handling.
- A positive result does not authorize production promotion without a separate
  Gary-approved PR.
