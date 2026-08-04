# ADR 004: Market Timezone and Session Calendar

## Status

Accepted

## Context

TradeX targets US-listed equities. All scheduled jobs, timestamps, and market-open checks must use a single canonical timezone to avoid DST drift and host-local time bugs.

## Decision

- The canonical market timezone is `America/New_York`.
- The canonical exchange calendar is `XNYS` (NYSE) via `exchange_calendars`.
- All public functions accept timezone-aware `datetime` values; naive datetimes raise `ValueError`.
- Datetimes are converted to `America/New_York` before market-status checks.
- The regular session is considered open between `session_open` and `session_close` from the XNYS calendar.
- Early closes are detected when the session close is before 4:00 PM ET.
- The daily pre-market scan job is scheduled at 08:00 `America/New_York`.
- The daily outcome-resolution job is scheduled at 16:30 `America/New_York`.

## Consequences

- Watcher and scheduled jobs align with actual NYSE hours, including holidays and early closes.
- Naive datetimes are rejected at boundaries, preventing silent off-by-hours bugs.
- All logs and UI timestamps can be displayed in New York time with a consistent abbreviation.
