# ADR 001: Coil Definition and Detection

## Status

Accepted

## Context

TradeX tracks signal history to detect "coiling" patterns before they resolve into moves. A coil is not a raw signal; it is a pre-breakout state inferred from repeated scans.

## Decision

A ticker is considered coiling for a single timeframe when all of the following hold:

- It has scored at or above `COIL_SCORE_THRESHOLD` (45) on at least `MIN_COIL_DAYS` (2) distinct XNYS trading sessions.
- Its score is stable or rising, measured by the linear slope of session-end scores.
- It has not yet made a large price move: the absolute percentage change between the first and last session close in the window is less than `BREAKOUT_PCT` (3.0%).

Coil strength is bounded 0–100 and computed from:

- 40% latest score,
- up to 20% persistence (capped at 5 appearances),
- up to 20% session-to-appearance ratio,
- up to 20% positive score trend.

A "fade" is the mirror case: a previously active setup has declined measurably from its peak score.

## Consequences

- Coil detection requires at least two distinct trading sessions, so intraday scan frequency does not create spurious coils.
- The bounded strength formula prevents runaway scores when the watcher runs more often.
- Breakout detection is price-based, so a move that already happened is not relabeled as a coil.
