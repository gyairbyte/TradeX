# ADR-0004: Market Timezone and Session Calendar

## Status

Accepted

## Date

2026-08-01

## Context

TradeX targets US-listed equities. Scheduled jobs, market-open checks, and timestamp displays must align with the NYSE regular session and avoid host-local time or DST drift.

## Decision

- The canonical market timezone is `America/New_York`.
- The canonical exchange calendar is the NYSE (`XNYS`) from the `exchange_calendars` package.
- Functions that accept `datetime` boundaries require timezone-aware input and reject naive datetimes with `ValueError`. These include `normalize_market_datetime`, `get_market_session` (when called with a datetime), `market_status`, `previous_trading_session`, `next_trading_session`, and any function that routes through `_as_market_timezone`.
- Functions that accept `date` arguments (e.g., `get_market_session(day: date)`) use the `date` directly against the XNYS calendar without converting to a datetime.
- A regular session is considered open between `session_open` and `session_close` returned by the XNYS calendar.
- An early close is detected when `session_close.time() < time(16, 0)`.
- The daily pre-market scan job is scheduled at 08:00 `America/New_York`.
- The daily outcome-resolution job is scheduled at 16:30 `America/New_York`.
- The `exchange_calendars` package version installed in the environment determines calendar data, including holiday and early-close schedules. TradeX does not maintain a separate holiday list.

## Consequences

- Watcher jobs align with actual NYSE sessions, including holidays and early closes.
- Naive datetimes are rejected at boundaries, preventing silent off-by-hours bugs.
- Logs and UI timestamps can be displayed in New York time consistently.
- Calendar correctness depends on the installed `exchange_calendars` dataset/version; updates may change observed holidays or early closes.

## Rejected alternatives

- Using host-local time: rejected because it would shift with DST and machine configuration.
- Maintaining a custom holiday list: rejected because `exchange_calendars` is a well-tested dependency and a custom list would drift.
- Accepting naive datetimes and assuming UTC: rejected because it would silently misinterpret caller intent.

## References

- `tradex/market/hours.py` (`MARKET_TIMEZONE`, `EXCHANGE_CALENDAR_KEY`, `MarketSession`, `MarketStatus`, `normalize_market_datetime`, `get_market_session`, `market_status`, `previous_trading_session`, `next_trading_session`, `_as_market_timezone`)
- `tests/market/`
- `tradex/tracker/watcher.py`
- `docs/PROJECT-TRACKER.md` (COR-005)

## Supersession

None.
