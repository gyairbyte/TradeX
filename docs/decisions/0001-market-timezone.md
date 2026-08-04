# ADR-0001: Market Timezone and Session Calendar

## Status

Accepted

## Recorded

2026-08-04

## Decision owners

TradeX maintainers; final product decisions by Gary Yang. Code-level ownership follows `docs/AI-DEVELOPMENT-WORKFLOW.md`.

## Context

TradeX targets US-listed equities. Scheduled jobs, market-open checks, and timestamp displays must use a single canonical timezone and exchange calendar to avoid DST drift, host-local time bugs, and off-market scans.

## Decision

- The canonical market timezone is `America/New_York`.
- The canonical exchange calendar is the NYSE (`XNYS`) from the `exchange_calendars` package.
- The following public functions take `datetime` arguments and reject naive inputs by routing through `_as_market_timezone`, which raises `ValueError`:
  - `normalize_market_datetime(value: datetime)`
  - `market_status(at: datetime)`
  - `is_regular_market_open(at: datetime)` (delegates to `market_status`)
  - `next_trading_session(at: datetime)`
- The following public functions take `date` arguments and consume the calendar directly; they do not route through `_as_market_timezone` and do not reject naive datetimes:
  - `get_market_session(day: date)`
  - `is_trading_day(day: date)`
  - `previous_trading_session(day: date)`
- A regular session is considered open on the half-open interval `[session_open, session_close)` returned by the XNYS calendar.
- An early close is detected when `session_close.time() < time(16, 0)`.
- The daily pre-market scan job is scheduled at 08:00 `America/New_York`.
- The daily outcome-resolution job is scheduled at 16:30 `America/New_York`.
- The `exchange_calendars` package version installed in the environment determines calendar data, including holiday and early-close schedules. TradeX does not maintain a separate holiday list.

## Consequences

- Watcher and scheduled jobs align with actual NYSE sessions, including holidays and early closes.
- Naive datetimes are rejected at `datetime` boundaries, preventing silent off-by-hours bugs.
- Logs and UI timestamps can be displayed in New York time consistently.
- Calendar correctness depends on the installed `exchange_calendars` dataset/version; updates may change observed holidays or early closes.

## Non-goals

- Supporting non-US equity markets or multiple exchange calendars.
- Validating the `exchange_calendars` dataset independently; TradeX relies on that package for holidays and early closes.
- Providing real-time market data or tick-level timestamps.
- Inferring timezone for naive datetimes; they are rejected.

## Risks and limitations

- Calendar correctness, including holidays and early closes, depends on the installed `exchange_calendars` version. A package update may change observed schedules.
- The early-close heuristic (`session_close.time() < time(16, 0)`) is a convention; `exchange_calendars` also reports early-close flags, but the ADR/code uses the time comparison.
- Callers must pass timezone-aware datetimes to boundary functions; passing naive datetimes raises `ValueError`.
- `date`-oriented functions do not validate that the input is a calendar date distinct from a naive `datetime`.

## Change control and supersession

This ADR is immutable once Accepted. Any change to the canonical timezone, exchange calendar, session-open/close semantics, or scheduled job times requires a new ADR that supersedes this one. Changes that affect production trading behavior require separate approval per `docs/AI-DEVELOPMENT-WORKFLOW.md` and, if they alter signal logic, validation per `docs/RESEARCH-PROTOCOL.md`.

## Rejected alternatives

- Using host-local time: rejected because it would shift with DST and machine configuration.
- Maintaining a custom holiday list: rejected because `exchange_calendars` is a well-tested dependency and a custom list would drift.
- Accepting naive datetimes and assuming UTC: rejected because it would silently misinterpret caller intent.

## References

- `tradex/market/hours.py` (`MARKET_TIMEZONE`, `EXCHANGE_CALENDAR_KEY`, `MarketSession`, `MarketStatus`, `normalize_market_datetime`, `get_market_session`, `is_trading_day`, `market_status`, `previous_trading_session`, `next_trading_session`, `is_regular_market_open`, `_as_market_timezone`)
- `tests/market/`
- `tradex/tracker/watcher.py`
- `docs/PROJECT-TRACKER.md` (COR-005)

## Revision history

| Version | Date | Change | Owner |
|---|---|---|---|
| 1.0 | 2026-08-04 | Initial recorded version | TradeX maintainers |
