# ADR-0002: Cross-Timeframe Confluence Scoring

## Status

Accepted

## Date

2026-08-01

## Context

`tradex/tracker/confluence.py` combines intraday, short-term, and long-term scores into one score so a user can see when a ticker looks strong across multiple timeframes. The score must be coverage-aware: a missing timeframe should penalize the result rather than being silently ignored.

## Decision

Confluence uses fixed absolute weights with a fixed denominator (sum of all three weights):

- intraday: 0.30
- short: 0.40
- long: 0.30

The raw weighted sum is rounded to the nearest integer and capped at 0–100. Each timeframe requires at least 30 bars of data to contribute; missing or data-insufficient timeframes contribute zero and are recorded in `errors` and `coverage_fields`.

Tier labels (from `_select_tier`) are assigned in the following order:

1. `all timeframes aligned` — all three timeframes are **available** and **active** (`score >= 50`) and confluence >= 90.
2. `strong confluence` — at least two timeframes are active and confluence >= 70.
3. `moderate confluence` — at least two timeframes are active and confluence >= 50.
4. `weak / single timeframe` — exactly one timeframe is available.
5. `weak / incomplete timeframes` — exactly two timeframes are available, and neither the strong nor moderate condition is met.
6. `weak confluence` — any other case with at least one available timeframe.
7. `no data` — no timeframe produced a score.

`available` means the timeframe produced a score after passing the 30-bar minimum. `active` means `score >= 50`. Only `all timeframes aligned` requires all three to be active; `strong` and `moderate` explicitly require at least two active timeframes, not all three.

## Consequences

- Missing data penalizes the score because the denominator is fixed.
- Tier labels make both coverage and strength explicit.
- The 30/40/30 split emphasizes short-term momentum while still requiring intraday and long-term context.
- Confluence is a coverage-aware aggregation, not a recommendation or trade signal.

## Rejected alternatives

- Normalizing by available weights: rejected because it would hide missing timeframes.
- Equal 1/3 weights: rejected because short-term is the primary actionable horizon.
- A single threshold for all coverage levels: rejected because a two-active-timeframe setup is materially different from a three-active-timeframe setup.

## References

- `tradex/tracker/confluence.py` (`_WEIGHTS`, `_compute_confluence`, `_select_tier`, `_coverage_fields`, `score_confluence`)
- `tests/tracker/test_confluence.py`
- `docs/PROJECT-TRACKER.md` (COR-006)

## Supersession

None.
