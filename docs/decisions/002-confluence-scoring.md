# ADR 002: Cross-Timeframe Confluence Scoring

## Status

Accepted

## Context

A setup that scores well on multiple timeframes is higher conviction than one that only looks good on a single timeframe. TradeX combines intraday, short-term, and long-term scores into a single confluence score.

## Decision

Confluence uses fixed absolute weights with a fixed denominator (the sum of all three weights):

- intraday: 30%
- short: 40%
- long: 30%

Missing timeframes contribute zero and are recorded explicitly. The score is capped at 0–100.

Tiers reflect both the confluence value and how many timeframes are active (score >= 50):

- "all timeframes aligned" when all three are active and confluence >= 90
- "strong confluence" when at least two are active and confluence >= 70
- "moderate confluence" when at least two are active and confluence >= 50
- "weak / single timeframe" when only one timeframe is available
- "weak / incomplete timeframes" when two are available but not active
- "weak confluence" otherwise
- "no data" when no timeframe produced a score

Each timeframe requires at least 30 bars of data to contribute.

## Consequences

- Missing data penalizes the score because the denominator is fixed.
- Tier labels make coverage transparent to the user.
- The 30/40/30 split emphasizes short-term momentum while still requiring intraday and long-term context.
