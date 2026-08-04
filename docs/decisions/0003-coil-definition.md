# ADR-0003: Coil Definition and Detection

## Status

Accepted

## Recorded

2026-08-04

## Decision owners

TradeX maintainers; final product decisions by Gary Yang. Code-level ownership follows `docs/AI-DEVELOPMENT-WORKFLOW.md`.

## Context

The coil detector in `tradex/tracker/analyzer.py` reads `signal_history`/`scan_observations` and ranks setups that show repeated scanner appearances before a price breakout. The decision boundaries and the coil-strength formula must be precise because the coil output is a heuristic ranking aid, not a validated trade signal.

## Decision

A ticker is considered actively coiling for a timeframe when all of the following hold over the looked-back window (`days` default 7, `min_appearances` default `MIN_COIL_DAYS = 2`):

1. `appearances >= min_appearances` — at least two distinct XNYS trading sessions have a recorded score observation.
2. `latest_score >= COIL_SCORE_THRESHOLD` (45).
3. `_price_broke_out(closes)` is `False` — the absolute first-to-last close percentage change is strictly less than `BREAKOUT_PCT` (3.0%).
4. `score_trend >= -0.5` — the slope from `np.polyfit` over session scores is not below -0.5.

`active_sessions` (sessions with `score >= COIL_SCORE_THRESHOLD`) is recorded but only contributes to `coil_strength`, not to the base eligibility. `latest_score`, `appearances`, `active_sessions`, and `trend` feed a bounded 0–100 `coil_strength` heuristic computed by `_coil_strength`.

The current `coil_strength` formula is:

```
persistence      = min(appearances / 5, 1.0) * 20
frequency        = (active_sessions / appearances * 20) if appearances > 0 else 0
trend_component  = max(min(trend * 10, 20), 0)
coil_strength    = round(min(100.0, latest_score * 0.4 + persistence + frequency + trend_component), 1)
```

`detect_fading_setups()` is a related but distinct query. A fading setup requires `peak_score >= 45`, `appearances >= 2`, and either `latest_score < 45` or (`trend < -0.5` and `latest_score < peak_score`). Fading is not the mirror case of coiling.

The coil output is a pre-signal ranking aid. It is not a validated breakout edge, not a trade instruction, and not proof of future profitability. Changing the coil eligibility rules or the `coil_strength` formula requires a separately approved production trading-logic change and follow-on validation per `docs/RESEARCH-PROTOCOL.md`.

## Consequences

- At least two observed sessions are required, preventing intraday scan frequency from creating spurious coils.
- A flat or mildly declining trend (-0.5 <= slope < 0) can still be flagged as coiling; a steeper decline is excluded.
- The price breakout guard prevents relabeling a move that already happened.
- `coil_strength` rewards persistence and active-session ratio but is capped at 100.
- The output must be presented as a heuristic, not a recommendation.

## Non-goals

- Predicting the direction or magnitude of a future breakout.
- Setting stops, targets, position sizing, or trade execution rules.
- Validating the profitability or edge of the coil heuristic.
- Changing the underlying intraday/short/long signal scoring formulas.

## Risks and limitations

- Coil strength is a heuristic and has not been validated as a trading edge.
- Coil and fade detection depend on the quality and session aggregation of `signal_history`/`scan_observations`; missing sessions change results.
- The breakout guard uses first-to-last close prices, not intraday highs/lows, so an intraday spike above the threshold without a close beyond it is ignored.
- The `np.polyfit` trend can be sensitive to a small number of sessions.
- Changing the formula or eligibility boundaries changes which tickers appear in the Coil Detector tab.

## Change control and supersession

This ADR is immutable once Accepted. Any change to the coil eligibility rules, `coil_strength` formula, `COIL_SCORE_THRESHOLD`, `MIN_COIL_DAYS`, or `BREAKOUT_PCT` requires a new ADR that supersedes this one. Because coil output is exposed in production dashboards and can inform trading decisions, changing these values is a production trading-logic change that requires separate approval per `docs/AI-DEVELOPMENT-WORKFLOW.md` and validation per `docs/RESEARCH-PROTOCOL.md`.

## Rejected alternatives

- Requiring every session to be above threshold: rejected because a setup can build pressure while having an off day.
- Using raw scan rows instead of distinct sessions: rejected in favor of `scan_sessions` aggregation to remove scan-frequency bias (see DATA-001 and COIL-001 in `docs/PROJECT-TRACKER.md`).
- Treating coil and fade as a single binary classifier: rejected because a ticker can be neither coiling nor fading (e.g., not enough sessions, or already broken out).
- A raw `appearances * 5` or other unbounded scan-frequency term in `coil_strength`: rejected because it would mechanically increase coil strength with watcher polling frequency. The accepted formula caps persistence and uses the `active_sessions / appearances` ratio.

## References

- `tradex/tracker/analyzer.py` (`MIN_COIL_DAYS`, `COIL_SCORE_THRESHOLD`, `BREAKOUT_PCT`, `detect_coils`, `detect_fading_setups`, `_coil_strength`, `_fading_strength`, `_price_broke_out`, `_score_trend`)
- `tests/tracker/test_analyzer.py`
- `docs/PROJECT-TRACKER.md` (DATA-001, COIL-001, COIL-002)
- `docs/RESEARCH-PROTOCOL.md`

## Revision history

| Version | Date | Change | Owner |
|---|---|---|---|
| 1.0 | 2026-08-04 | Initial recorded version | TradeX maintainers |
