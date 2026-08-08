# INTRA-001B-DATASET-V1 Amendment: 1Day Liquidity-Ranking Inputs

## Amendment summary

- **Original preregistered plan:** `docs/research/specs/INTRA-001B-dataset-v1-30Min-attempt.json`
- **Amended locked plan:** `docs/research/specs/INTRA-001B-dataset-v1.json`
- **Date:** 2026-08-08
- **Approved by:** Gary Yang

## What changed

The liquidity-ranking input was changed from Alpaca SIP 30Min intraday bars to Alpaca SIP 1Day bars.

| Item | Before | After |
|---|---|---|
| Ranking timeframe | 30Min (aggregated to daily regular-session values) | 1Day |
| Session-dollar-volume formula | `regular_session_final_close * sum(regular_session_volume)` | `Alpaca SIP 1Day close * Alpaca SIP 1Day volume` |
| Prior-close requirement | Regular-session final close | Alpaca SIP 1Day close of the prior session |
| Median window | Prior 20 complete XNYS sessions | Prior 20 complete XNYS sessions (unchanged) |
| Top-50 selection | Deterministic, ticker ascending tie-break | Deterministic, ticker ascending tie-break (unchanged) |
| Candidate population | All eligible PIT common stocks | All eligible PIT common stocks (unchanged) |

## Why the change was necessary

A live 30Min ranking probe showed that Alpaca paginates 30Min multi-symbol responses at roughly 750-800 rows per HTTP page. With roughly 5,150 eligible common stocks per PIT date, 20 prior sessions, and 13 bars per session, each month required approximately 1,675 HTTP pages for ranking alone. At ~1 second per page, that implied 5-6 hours for the full 12-month build and created a reproducibility/scheduling risk. Alpaca SIP 1Day multi-symbol responses paginate at ~10,000 rows per page, reducing ranking pages by roughly 30x.

## What was inspected

Only provider-call behavior and liquidity-ranking inputs were inspected:

- A bounded 1Day-vs-5Min regular-session parity check on `SPY`, `AAPL`, and `JPM` for the first 20 complete XNYS sessions of January 2025.
- A 60-symbol sensitivity check using the first 60 eligible common-stock symbols from the 2024-12-31 Massive active snapshot.

## Findings

- 1Day close is within ~0.1% of the regular-session final close.
- 1Day volume is 15-60% larger than regular-session 5Min volume because Alpaca 1Day bars include pre-market and after-hours activity.
- In the 60-symbol sensitivity sample, the top-50 set produced by 1Day dollar-volume ranking was identical to the top-50 set produced by 5Min regular-session dollar-volume ranking. Absolute dollar-volume values differed by ~30-60%.

## Accepted limitation

Alpaca SIP 1Day volume is a **total-liquidity proxy**, not an exact regular-session-only volume. It includes pre-market and after-hours trading activity. The amended ranking formula is therefore:

```
session_dollar_volume = Alpaca SIP 1Day close * Alpaca SIP 1Day volume
median over the prior 20 complete XNYS sessions
```

This is described as a total-liquidity proxy in all artifacts and reports. It must not be described as exact regular-session volume.

## What did not change

- `INTRA-001-v1.json` and its SHA-256.
- `INTRA-001-data-sufficiency-amendment-v3.json` and its SHA-256.
- Frozen V4 reference-probe artifacts.
- Monthly PIT dates, dataset/development/validation/holdout splits, fixed 13-ETF stratum, exchange allowlist, security-type controls, duplicate-symbol policy, top-50 selection, ticker tie-break, prior-20-session rule, $5.00 prior-close minimum, and $50M median-dollar-volume minimum.
- No VWAP strategy, signals, entries, exits, returns, trade metrics, or holdout performance were calculated or viewed.

## Retrieval allocation after amendment

- **Liquidity ranking:** Alpaca SIP 1Day bars for all eligible PIT common stocks.
- **Final OHLCV dataset:** Alpaca SIP 5Min bars for the selected monthly top-50 stocks plus the fixed 13-ETF stratum.

## What was not inspected

- Session VWAP strategy features.
- Candidate or baseline signals.
- Entries, exits, returns, or trade metrics.
- Holdout performance.
- Strategy comparisons.
