# LONG-001 Research Protocol

## Hypothesis

The current production `tradex.signals.long_term.score` (weekly-bar, 0-100)
contains information that produces higher 13-week net returns than a simple
`close > 40-week simple moving average` baseline on a large-cap U.S. equity
universe, after explicit transaction costs.

## Study design

| Item | Value |
|---|---|
| Candidate signal | `long_term.score` using a fresh `LongWeights()` default instance |
| Candidate threshold | `score >= 40` |
| Baseline | `close > 40-week simple moving average` of the same ticker |
| Benchmark/reference | SPY (S&P 500 ETF), used for SPY-relative alignment only; not a candidate |
| Candidate universe | 30 large-cap equities + 12 equity ETFs (listed below) |
| Data provider | Yahoo Finance (default); `fetch_daily_history` with `auto_adjust=True` |
| Source frequency | Daily adjusted OHLCV |
| Study frequency | Weekly, XNYS Friday-close aggregation (`W-FRI`) |
| Source window | 2007-01-01 through 2025-12-19 inclusive |
| Warm-up period | 2007-01-01 through 2009-12-31 (not used for events) |
| Development period | 2010-01-01 through 2016-12-31 |
| Validation period | 2017-01-01 through 2020-12-31 |
| Holdout period | 2021-01-01 through 2025-12-19 |
| Primary horizon | 13 weeks (net return at 10 bps per side is the decision metric) |
| Secondary horizon | 26 weeks (sensitivity) |
| Entry | End-of-week signal; executable entry at the open of the next weekly bar |
| Exit | Close of the week `horizon` weeks after entry |
| Costs | Slippage 0 / 5 / 10 / 25 bps per side; commission 0 bps |
| Execution model | No stops, no targets, no position sizing, full capital reallocated |
| Overlap policy | Two policies are reported separately: an overlapping event study and a non-overlapping per-ticker trade policy |

## Universe

### Large-cap equities (30)

AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META, JPM, V, MA, HD, UNH, PG, JNJ,
XOM, CVX, LLY, ABBV, MRK, PEP, KO, BAC, WFC, CSCO, ADBE, NFLX, CRM, ACN,
COST, DIS.

### Equity ETFs (12)

QQQ, IWM, DIA, XLF, XLK, XLE, XLU, XLI, XLP, XLB, XRT, VTI.

### Reference benchmark

SPY.

## Required outputs

- Locked manifest with per-ticker SHA-256 hashes and provider/adjustment metadata.
- Per-ticker data-quality audit (duplicates, missing values, invalid OHLC rows, date coverage).
- Both overlapping and non-overlapping event records.
- Cross-split exclusion log (events whose signal/entry/exit cross a split boundary are excluded and counted).
- Aggregates by split, cohort (`stock` vs `etf`), horizon, cost level, and `candidate_only` / `baseline_only` / `baseline_and_candidate` groups.
- Non-overlapping counts, exposure/frequency summary, 10th and 25th percentiles.
- SPY-relative mean and median returns.
- Ticker-year cluster-bootstrap 95% confidence intervals (5,000 resamples, seed 20260805).
- Predefined `supported` / `rejected` / `inconclusive` classification using the evidence gates below.

## Evidence gates

Classification uses the 13-week net return at 10 bps per side.

`supported` only when all of the following hold:

1. At least 100 validation signals.
2. At least 100 holdout signals.
3. At least 15 tickers represented in each split.
4. No ticker contributes more than 20% of signals in any split.
5. Validation mean signed net return is positive.
6. Holdout mean signed net return is positive.
7. Validation bootstrap lower 95% confidence bound is above zero.
8. Holdout bootstrap lower 95% confidence bound is above zero.
9. Validation mean lift over the frequency-matched baseline is at least 0.25 percentage points.
10. Holdout mean lift over the frequency-matched baseline is at least 0.25 percentage points.
11. Baseline-lift lower 95% confidence bounds are above zero in both splits.
12. Median ticker-level lift is positive in both splits.
13. At least 55% of represented tickers have positive lift in both splits.
14. Mean net return is positive in both halves of the holdout.
15. No leakage or manifest-integrity test fails.

`rejected` when sample-size gates pass but any return/lift gate fails.

`inconclusive` when data or sample requirements are insufficient.

`production_promotion_eligible` is always `false`.

## Limitations to report

- Survivorship, delisting, and look-ahead bias are not eliminated.
- Index/sector membership is not point-in-time.
- Weekly bars abstract intraday execution; slippage is modeled as a per-side bps penalty.
- No stops, targets, position sizing, capital allocation, capacity, or liquidity modeling.
- Pooled results can be dominated by tickers with longer histories or stronger trends.
- Events may overlap in the event-study output; the non-overlapping policy is the executable approximation.
- A positive research result would still require a separate Gary-approved promotion PR.
