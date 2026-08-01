# TradeX Correctness Findings

This document lists suspected correctness issues that were verified during the audit. Each item includes severity, evidence, files, reproduction steps, user impact, and a recommended fix.

## Severity legend

- **High** — can crash, corrupt data, or produce materially misleading trading information.
- **Medium** — can cause missed signals, stale results, or poor user experience.
- **Low** — documentation, minor edge cases, or hygiene issues.

---

## 1. Signal history only stores passing signals

**Severity:** High

**Files:** `tradex/screener/engine.py`, `tradex/tracker/store.py`

**Finding:** `screener.engine.run` filters by `min_score` and `exclude_earnings_within`, then calls `store.record_signals` only with the resulting DataFrame. `record_signals` writes those rows to `signal_history`. There is no record of tickers that were scanned but did not pass the threshold.

**Why it matters:** The coil detector cannot see a setup that was strong yesterday and weak today. It only sees the positive subset, so "fading" setups are invisible.

**Reproduction:**
```python
from tradex.tracker import store
import pandas as pd
store.init()
results = pd.DataFrame([{'ticker': 'A', 'score': 75, ...}])
store.record_signals(results, 'intraday')
# No API exists to record that 'B' was scanned and scored 30.
```

**Recommended correction:**
- Change `record_signals` to accept a `scan_run` object containing `(run_time, timeframe, tickers_scanned, tickers_found)`.
- Write one row per ticker/score to `signal_history`, or add a separate `scan_observations` table for all observations.
- Update `analyzer.detect_coils` to query distinct sessions, not only passing rows.

**Regression tests:** `tests/tracker/test_store.py::test_all_scans_are_audited`.

---

## 2. Coil appearances count scan executions, not distinct trading sessions

**Severity:** High

**Files:** `tradex/tracker/analyzer.py`, `tradex/tracker/store.py`

**Finding:** `analyzer.detect_coils` calls `store.get_recent_appearances`, which executes `COUNT(*) ... GROUP BY ticker`. Each row in `signal_history` is one scan execution. If the watcher runs three times in one day, the same day contributes three appearances.

**Why it matters:** A "coil" is supposed to represent multi-day pressure. Counting scans makes coil strength a function of how often the watcher is running, not market behavior.

**Reproduction:**
```python
import pandas as pd
from tradex.tracker import store, analyzer
store.init()
for _ in range(3):
    store.record_signals(pd.DataFrame([{'ticker':'COIL','score':60,'last_close':100,'volume_ratio':2.0,'rsi':60,'reasons':'vol'}]), 'intraday')
print(analyzer.detect_coils('intraday', days=7, min_appearances=2))
# appearances = 3 from a single day
```

**Recommended correction:**
- Record scan `session_id` or `trading_date` alongside each signal.
- In `get_recent_appearances`, count `COUNT(DISTINCT DATE(scan_time))` or group by `session_id`/`trading_date`.

**Regression tests:** `tests/tracker/test_analyzer.py::test_coil_appearances_count_distinct_days`.

---

## 3. Frequent scanning mechanically increases coil strength

**Severity:** High

**Files:** `tradex/tracker/analyzer.py`

**Finding:** `coil_strength = round((latest_score * 0.4) + (row["appearances"] * 5) + max(trend * 10, 0), 1)`. Because `appearances` counts scans, running the watcher every minute instead of every hour inflates coil strength.

**Why it matters:** Users can manipulate the "strength" of a coil by changing the watcher interval.

**Recommended correction:**
- Remove the linear `appearances * 5` term, or replace it with a capped/distinct-day count.
- Base strength on the *fraction of recent sessions* the ticker appeared in, not the raw count.

**Regression tests:** `tests/tracker/test_analyzer.py::test_coil_strength_invariant_to_scan_frequency`.

---

## 4. Outcome tracker waits longer than the intended holding period

**Severity:** High

**Files:** `tradex/tracker/outcome_tracker.py`

**Finding:** In `_fetch_close_after`, `end = after_date + timedelta(days=days_forward + 7)`. The function returns `None` if `end > datetime.now(timezone.utc)`. For an intraday signal (`days_forward=1`), it waits approximately 8 days before attempting to resolve the outcome; for short (`days_forward=3`) it waits ~10 days; for long (`days_forward=5`) ~12 days.

**Why it matters:** Outcomes are stale by the time they are recorded, defeating the purpose of the signal journal.

**Reproduction:**
```python
from datetime import datetime, timezone, timedelta
from tradex.tracker.outcome_tracker import _fetch_close_after
print(_fetch_close_after('AAPL', datetime.now(timezone.utc) - timedelta(days=2), 1))
# Returns None for several more days
```

**Recommended correction:**
- Compute the earliest possible resolution time from the intended holding period (e.g., `N` trading days after signal, not `N+7` calendar days).
- Fetch up to `now`; if at least `days_forward` trading days exist in the data, resolve the outcome.

**Regression tests:** `tests/tracker/test_outcome_tracker.py::test_outcome_resolves_at_earliest_valid_date`.

---

## 5. Outcome tracker mishandles yfinance MultiIndex columns

**Severity:** High

**Files:** `tradex/tracker/outcome_tracker.py`

**Finding:** `_fetch_close_after` does:
```python
return float(df["Close"].iloc[days_forward - 1])
```
`yfinance.download` can return a MultiIndex `('Close', 'AAPL')` for a single ticker. In that case `df["Close"]` is a DataFrame, and `float(...)` raises `TypeError`.

**Reproduction:**
```python
import pandas as pd
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from tradex.tracker.outcome_tracker import _fetch_close_after
dates = pd.date_range('2024-01-02', periods=5, freq='B')
df = pd.DataFrame({('Close','AAPL'): [100,101,102,103,104]}, index=dates)
with patch('tradex.tracker.outcome_tracker.yf.download', return_value=df):
    _fetch_close_after('AAPL', datetime(2024,1,1,tzinfo=timezone.utc), 3)
# TypeError: float() argument must be a string or a real number, not 'Series'
```

**Recommended correction:**
- Apply the same normalization used in `data/fetcher.py` (`isinstance(df.columns, pd.MultiIndex)`).
- Prefer lower-case `close` after normalization.

**Regression tests:** `tests/tracker/test_outcome_tracker.py::test_fetch_close_with_multiindex_columns`.

---

## 6. The watcher’s provider argument is not propagated to the screener

**Severity:** Medium

**Files:** `tradex/tracker/watcher.py`

**Finding:** `run_once(tickers, timeframe, min_score, provider)` accepts a `provider` argument but calls `screener_run(tickers, timeframe=timeframe, min_score=min_score)`, omitting `provider`. `start_loop` passes `provider` to `run_once` and `schedule.every().minutes.do(...)`, but it is lost at the screener call.

**Why it matters:** Users who run `python -m tradex.tracker.watcher --provider alpaca` silently get the default Yahoo provider.

**Reproduction:**
```python
from unittest.mock import patch, MagicMock
from tradex.tracker.watcher import run_once
captured = {}
def fake_run(*args, **kwargs):
    captured['kwargs'] = kwargs
    return MagicMock(empty=True)
with patch('tradex.tracker.watcher.screener_run', side_effect=fake_run):
    run_once(['AAPL'], timeframe='intraday', min_score=30, provider='alpaca')
print(captured['kwargs'])
# {'timeframe': 'intraday', 'min_score': 30}  -- provider missing
```

**Recommended correction:**
- Pass `provider=provider` from `run_once` to `screener_run`.
- Also propagate `provider` to `run_confluence_screen` in `_check_alerts`.

**Regression tests:** `tests/tracker/test_watcher.py::test_run_once_passes_provider_to_screener`.

---

## 7. Scheduled jobs use host-local time, not market time

**Severity:** Medium

**Files:** `tradex/tracker/watcher.py`

**Finding:** `schedule.every().day.at("20:30")` and `schedule.every().day.at("12:00")` are interpreted in the host machine's local time by the `schedule` library. The comments say "4:30pm ET" and "8am ET." On a machine not in ET/UTC, the jobs run at the wrong times.

**Recommended correction:**
- Convert desired ET times to a known timezone (e.g., `pytz.timezone("America/New_York")`) before scheduling, or use a scheduler that is timezone-aware.
- Add explicit market-hours checks rather than relying on clock time alone.

**Regression tests:** `tests/tracker/test_watcher.py::test_scheduled_times_are_market_timezone`.

---

## 8. The watcher runs scans outside market hours

**Severity:** Medium

**Files:** `tradex/tracker/watcher.py`

**Finding:** `start_loop` runs `run_once` immediately and then every `interval_minutes` with no check for US equity market hours. Running at night or on weekends repeatedly fetches stale data and wastes API calls.

**Recommended correction:**
- Add a `market_hours.is_open()` guard before scanning.
- Optionally allow an `--ignore-market-hours` flag for backfills.

**Regression tests:** `tests/tracker/test_watcher.py::test_watcher_skips_outside_market_hours`.

---

## 9. Alerts have no persistent deduplication or cooldown

**Severity:** High

**Files:** `tradex/tracker/watcher.py`, `tradex/alerts/notifier.py`

**Finding:** `_check_alerts` calls `alert_coil`, `alert_confluence`, and `alert_pattern_match` on every scan cycle. The notifier functions send alerts whenever the threshold is met. There is no record of the last alert time/ticker/condition, so a coil that remains above threshold for an hour produces one alert every scan interval.

**Recommended correction:**
- Introduce an `AlertState` store (SQLite or in-memory with persistence) keyed by `(ticker, alert_type, timeframe)`.
- Enforce a configurable cooldown (e.g., 1 hour for coils, 4 hours for confluence).

**Regression tests:** `tests/alerts/test_notifier.py::test_alerts_respect_cooldown`.

---

## 10. Confluence scores highly and reports "all timeframes aligned" when timeframes are missing

**Severity:** High

**Files:** `tradex/tracker/confluence.py`

**Finding:** `score_confluence` renormalizes weights over the available timeframes. If only intraday data is available and scores 95, the confluence score is also 95 and the tier becomes `"all timeframes aligned"` even though short and long are missing.

**Reproduction:**
```python
from unittest.mock import patch
import pandas as pd
from tradex.tracker.confluence import score_confluence

def fake_fetch(t, tf, provider=None):
    if tf == 'intraday':
        return pd.DataFrame({'open':[1]*30,'high':[2]*30,'low':[0.5]*30,'close':[1.5]*30,'volume':[10]*30})
    raise Exception('no data')

def fake_score(df):
    return {'score':95, 'reasons':['bullish'], 'last_close':100, 'volume_ratio':2.0, 'rsi':60}

with patch('tradex.tracker.confluence.fetch', side_effect=fake_fetch), \
     patch('tradex.tracker.confluence.intraday.score', side_effect=fake_score), \
     patch('tradex.tracker.confluence.short_term.score', side_effect=fake_score), \
     patch('tradex.tracker.confluence.long_term.score', side_effect=fake_score):
    print(score_confluence('TEST'))
# confluence_score=95, tier='all timeframes aligned', active_timeframes=['intraday']
```

**Recommended correction:**
- Require all requested timeframes to be present for a confluence score, or expose a separate "available timeframes" metric.
- Do not renormalize weights; either fail on missing data or report a missing-timeframe penalty.
- Never label a single-timeframe result as "all timeframes aligned."

**Regression tests:** `tests/tracker/test_confluence.py::test_confluence_does_not_claim_all_timeframes_when_one_is_missing`.

---

## 11. Empty confluence results raise `KeyError`

**Severity:** High

**Files:** `tradex/tracker/confluence.py`

**Finding:** `run_confluence_screen` returns `pd.DataFrame(rows).sort_values("confluence_score", ...).reset_index(drop=True)`. When `rows` is empty, `pd.DataFrame([])` has no columns, and `sort_values("confluence_score")` raises `KeyError: 'confluence_score'`.

**Reproduction:**
```python
from tradex.tracker.confluence import run_confluence_screen
run_confluence_screen([], min_confluence=50)
# KeyError: 'confluence_score'
```

**Recommended correction:**
- Construct the DataFrame with explicit columns when `rows` is empty:
  ```python
  columns = ["ticker", "confluence_score", "tier", ...]
  df = pd.DataFrame(rows, columns=columns)
  ```

**Regression tests:** `tests/tracker/test_confluence.py::test_empty_confluence_returns_empty_dataframe`.

---

## 12. Scan audit records cannot distinguish tickers scanned from signals found

**Severity:** Medium

**Files:** `tradex/tracker/store.py`, `tradex/tracker/watcher.py`

**Finding:** `store.record_signals` inserts into `scan_runs` with `tickers_n = len(results)` and `hits_n = len(results)`. The number of tickers *scanned* is not passed in, so `tickers_n` is always equal to `hits_n`.

**Why it matters:** The audit table is intended to distinguish "we scanned 500 and found 12" from "we scanned 12 and found 12." It currently cannot.

**Recommended correction:**
- Add a `tickers_scanned` parameter to `record_signals` and to the `scan_runs` table.
- Update the watcher to pass `len(tickers)` as `tickers_scanned`.

**Regression tests:** `tests/tracker/test_store.py::test_scan_audit_records_ticker_count`.

---

## 13. Provider failures appear to the user as "no opportunities"

**Severity:** Medium

**Files:** `tradex/screener/engine.py`, `tradex/ui/dashboard.py`

**Finding:** `engine.run` catches all exceptions in `_score_one`, prints `[skip] <ticker>: <error>`, and returns `None`. If every fetch fails, `run` returns an empty DataFrame. The dashboard then displays "No opportunities found. Lower the min score or add more tickers."

**Why it matters:** A user cannot tell whether the scan produced no signals or whether all data fetches failed (rate limit, network, bad ticker).

**Reproduction:**
```python
from unittest.mock import patch
from tradex.screener.engine import run
with patch('tradex.screener.engine.fetch', side_effect=Exception('network')):
    df = run(['AAPL','MSFT'], timeframe='intraday')
print(df.empty)  # True
```

**Recommended correction:**
- Return a separate `errors` or `summary` dict alongside the results DataFrame.
- Distinguish "0 signals" from "N fetch errors" in the dashboard UI.

**Regression tests:** `tests/screener/test_engine.py::test_engine_reports_provider_failures`.

---

## 14. Automated test coverage is insufficient

**Severity:** High

**Files:** entire repository

**Finding:** There was no `tests/` directory and no CI configuration before this audit. The only verification was manual launch of the Streamlit dashboard. This audit introduces an initial characterization suite; CI configuration and broader coverage are still missing.

**Why it matters:** Without tests, every future change risks introducing regressions in trading logic, data handling, and scheduling.

**Recommended correction:**
- Complete the `tests/` tree with provider-contract and broader unit/integration tests.
- Add a GitHub Actions workflow that installs dependencies, runs `ruff check tests`, and runs `pytest`.

**Regression tests:** N/A (infrastructure).

---

## 15. Documentation has drifted from the implementation

**Severity:** Low (but confusing)

**Files:** `README.md`, `CLAUDE.md`, `SETUP.md`

**Finding:**
- `README.md` says the dashboard has 10 tabs; `CLAUDE.md` says 5.
- `README.md` lists features as "completed" that `CLAUDE.md` still lists as "Next features to build" (e.g., alert system, pre-market gap scanner, options flow, watchlist persistence).
- `SETUP.md` section 2 references `DISCORD_BOT_TOKEN` but the code uses `ALERT_DISCORD_TOKEN`.
- `CLAUDE.md` says "Add alerts, pre-market gap scanner, and options flow" is next, but they are implemented.

**Recommended correction:**
- Designate one canonical doc per topic (see `REPOSITORY-ORGANIZATION.md`).
- Sync `CLAUDE.md` with `main` and remove stale TODOs.
- Fix env variable names in `SETUP.md`.

**Regression tests:** Optional doc lint checks or a `docs/` review checklist in PR template.

---

## Summary table

| ID | Finding | Severity | Files |
|---|---|---|---|
| 1 | Signal history only stores passing signals | High | `screener/engine.py`, `tracker/store.py` |
| 2 | Coil appearances count scans, not sessions | High | `tracker/analyzer.py`, `tracker/store.py` |
| 3 | Frequent scanning inflates coil strength | High | `tracker/analyzer.py` |
| 4 | Outcome tracker waits longer than intended | High | `tracker/outcome_tracker.py` |
| 5 | Outcome tracker crashes on MultiIndex columns | High | `tracker/outcome_tracker.py` |
| 6 | Watcher provider argument not propagated | Medium | `tracker/watcher.py` |
| 7 | Scheduled jobs use host-local time | Medium | `tracker/watcher.py` |
| 8 | Watcher scans outside market hours | Medium | `tracker/watcher.py` |
| 9 | No alert deduplication or cooldown | High | `watcher.py`, `alerts/notifier.py` |
| 10 | Confluence mislabels missing timeframes | High | `tracker/confluence.py` |
| 11 | Empty confluence results raise `KeyError` | High | `tracker/confluence.py` |
| 12 | Scan audit cannot distinguish scanned vs found | Medium | `tracker/store.py`, `tracker/watcher.py` |
| 13 | Provider failures look like no opportunities | Medium | `screener/engine.py`, `ui/dashboard.py` |
| 14 | Test coverage was missing before the audit; CI and broader tests still needed | High | all |
| 15 | Documentation drift | Low | `README.md`, `CLAUDE.md`, `SETUP.md` |
