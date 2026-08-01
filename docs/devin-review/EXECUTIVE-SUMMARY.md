# TradeX Review — Executive Summary

This audit covers the `gyairbyte/TradeX` repository as of the current `main` branch. TradeX is a personal stock-market scanning application with a Streamlit dashboard, three signal timeframes, signal-history tracking, pattern matching, pre-market gap scanning, options-flow analysis, and alerting.

The codebase is well organized at a package level and many architectural intentions are reasonable, but several correctness issues, missing tests, and documentation drift mean the app is not yet reliable enough to base trading decisions on. The most promising pieces are the *idea* of a signal journal and the multi-provider data abstraction; the most risky pieces are the coil/confluence scoring and the unvalidated pattern-matching and options-flow features.

---

## What TradeX currently does well

| Area | Strength |
|---|---|
| **Package layout** | Domain modules (`data`, `signals`, `screener`, `tracker`, `patterns`, `options`, `alerts`, `watchlists`, `ui`) have clear names and mostly sensible boundaries. |
| **Provider abstraction** | `tradex.data.fetcher` exposes a single `fetch(ticker, timeframe, provider)` interface over Yahoo, Alpaca, IBKR, and Schwab; signal code receives a normalized DataFrame. |
| **Signal modularity** | Each timeframe has its own scorer (`intraday`, `short_term`, `long_term`) and a shared `indicators.py`. Adding a new signal means editing one file. |
| **Persistence concept** | SQLite is used for signal history (`~/.tradex/signals.db`), fingerprints, watchlists, and earnings cache — no infrastructure required. |
| **UI speed** | A single-file Streamlit dashboard lets a non-front-end developer iterate quickly and exposes most features in one place. |
| **User-tunable weights** | `tradex/signals/weights.py` persists custom scoring weights to JSON and provides per-component help text. |
| **Preset watchlists** | `tradex/watchlists/presets.py` ships with index, sector, and broad-market lists, plus a web-refresh utility. |

## What is unreliable

| Area | Concern |
|---|---|
| **Data quality** | The default Yahoo provider is delayed ~15 min, rate-limited, and can return MultiIndex columns that downstream modules do not always handle. |
| **Correctness bugs** | Outcome tracking has a MultiIndex-column crash, the watcher does not propagate the `--provider` argument, confluence produces a `KeyError` on empty results, and the confluence score can report "all timeframes aligned" when only one timeframe is present. |
| **Signal history design** | The store only records signals that pass `min_score`. A stock whose score deteriorates disappears, so the coil detector cannot observe fading setups. |
| **Coil detector** | It counts scan executions, not distinct trading days, and scan frequency mechanically increases coil strength. |
| **Time and scheduling** | The watcher does not check market hours, and scheduled job times (`20:30`, `12:00`) assume the host is running in UTC/ET without explicit timezone handling. |
| **Alerts** | There is no deduplication or cooldown; a coil that stays above threshold will alert on every scan cycle. |
| **Outcome tracking** | The outcome window uses daily bars for all timeframes, waits longer than the intended holding period before fetching, and does not model slippage, stops, or transaction costs. |
| **Test coverage** | There were no automated tests before this audit. This audit introduces an initial characterization suite with 1 passing test and 7 strict xfails representing confirmed bugs. CI is still missing. |
| **Documentation drift** | `README.md` and `CLAUDE.md` disagree on dashboard tabs, completed features, and next priorities; `SETUP.md` references a wrong Discord env variable name. |

## What is potentially valuable

- **Signal journal / outcome tracking** — If fixed, this is the highest-value feature. Knowing whether a signal actually produced a move is the only way to calibrate thresholds.
- **Multi-timeframe confluence** — The concept is sound, but the implementation needs missing-timeframe handling, weight transparency, and validation.
- **Coil detector** — A pre-breakout pressure metric is valuable, but it needs a proper "signal episode" model (distinct sessions, no scan-frequency bias) and validation before it can be trusted.
- **Preset watchlists and sector groupings** — Useful for narrowing a scan universe and controlling correlation.
- **Configurable scoring weights** — Good for user experimentation, provided there is a backtesting layer to test the changes.

## What may not be worth keeping in its current form

| Feature | Problem | Suggested disposition |
|---|---|---|
| **Options flow scanner** | Without a paid Unusual Whales or Tradier key it falls back to free yfinance option-chain volume/OI, which is delayed and not "flow." It is easy to misread as unusual directional activity. | **Deprioritize / quarantine** until a real flow data source is wired in and validated. |
| **Pattern matcher** | Mines historical run-ups, builds a fingerprint, and scores current windows by Pearson correlation. It has not been validated; correlation to a pre-event average does not imply predictive value, and the fingerprint uses a tiny universe (~40 stocks) with survivorship bias. | **Keep for experimentation only**; do not present similarity as a trade signal until backtested. |
| **Pre-market gap scanner** | Uses yfinance pre/post bars and a simple `%` threshold. It does not model pre-market liquidity, spread, volume, or catalyst, and can be misleading outside 7–9:30am ET. | **Keep as context only**, with clear warnings; do not alert on it alone. |
| **Current 0–100 score** | The score is a sum of loosely related bullish conditions. It has not been calibrated; a score of 70 has no empirically defined meaning and the weights are not validated. | **Keep as a screen**, but treat it as a rank, not a probability. |

## The five most important next steps

1. **Fix correctness and data-integrity bugs** (confluence empty DataFrame, outcome MultiIndex crash, watcher provider propagation, signal-history redesign). These block any serious use of the journal or coil features.
2. **Complete the test foundation and add CI** so future changes can be reviewed with confidence. The initial characterization suite exists; CI, provider-contract tests, and broader coverage are still needed. Every PR that changes scoring, persistence, or scheduling must include regression tests.
3. **Redesign signal history** to store all scan observations (or at least all tickers scanned) with session IDs and distinct trading-day semantics, enabling the coil detector to see deterioration and removing scan-frequency bias.
4. **Validate one trading hypothesis end-to-end** before adding new indicators. Pick one timeframe, define entry/exit rules, run a walk-forward backtest with costs and slippage, and decide whether the score has edge.
5. **Adopt architectural decision records** and continue using the project tracker so that the rationale for scores, coils, confluence, and data-provider choices is recorded and future work stays reviewable and small.
