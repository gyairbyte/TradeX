# TradeX — Stock Market Opportunity Scanner

TradeX identifies trading opportunities across three timeframes: **intraday**, **short-term (days/weeks)**, and **long-term (weeks/months)**. It is especially tuned to detect intraday setups preceded by multi-day volume and volatility accumulation ("coiling" patterns that resolve into big intraday swings).

> **Setting up on a new machine?** See [`SETUP.md`](SETUP.md) — a single end-to-end install guide written so an AI agent (Claude, ChatGPT, etc.) can execute it directly. Tell it "read SETUP.md and set this up" and it will handle Mac or Windows install, venv creation, `.env` setup, and the desktop launcher.

---

## Project Structure

```
tradex/
├── tradex/
│   ├── data/fetcher.py            # Multi-provider OHLCV fetcher (Yahoo, Alpaca, IBKR, Schwab)
│   ├── signals/
│   │   ├── indicators.py          # RSI, MACD, EMA, Bollinger Bands, ATR, volume ratios
│   │   ├── intraday.py            # 5m bars / 5-day window scorer
│   │   ├── short_term.py          # Daily bars / 60-day window scorer
│   │   ├── long_term.py           # Weekly bars / 2-year window scorer
│   │   └── weights.py             # User-tunable per-signal weights, persisted to JSON
│   ├── screener/engine.py         # Runs scorers across a watchlist, returns ranked DataFrame
│   ├── tracker/
│   │   ├── store.py               # SQLite canonical scan sessions + observations and `scan_runs` audit surface
│   │   ├── analyzer.py            # Coil detector — pre-breakout pressure detection
│   │   ├── confluence.py          # Multi-timeframe alignment scoring
│   │   ├── outcome_tracker.py     # 1d/3d/5d price follow-up, win rate by score bucket
│   │   └── watcher.py             # Scheduled scan runner
│   ├── patterns/
│   │   ├── config.py              # PatternConfig + conservative/standard/volatile profiles
│   │   ├── miner.py               # Mines 3yr daily history for run-up / decline events
│   │   ├── fingerprint.py         # Averages mined windows into fingerprints
│   │   └── matcher.py             # Weighted Pearson similarity vs. live 10-day windows
│   ├── premarket/gap_scanner.py   # Pre-market gap-up/down detector
│   ├── options/flow.py            # Unusual options activity, put/call sentiment
│   ├── alerts/notifier.py         # Discord bot + email alerting
│   ├── earnings/calendar.py       # Next-earnings lookup + 24h SQLite cache
│   ├── watchlists/store.py        # Named watchlist persistence
│   └── ui/dashboard.py            # Streamlit dashboard (10 tabs)
├── pyproject.toml
├── .env.example
├── README.md
└── CLAUDE.md
```

---

## How It Works

### Signal Scoring
Each timeframe has its own scorer that returns a **score from 0–100** plus human-readable reasons. The score is built from weighted signals:

| Signal | Intraday | Short | Long |
|---|---|---|---|
| Volume surge (>2x avg) | +30 | +20 | +25 |
| RSI momentum zone | +20 | +20 | +20 |
| MACD crossover/direction | +30 | +20 | +15 |
| EMA structure (price > EMA20 > EMA50) | — | +25 | +25 |
| BB squeeze/expansion | +20 | — | +15 |
| Pullback to EMA20 in uptrend | — | +15 | — |

### Intraday Setup Logic
The intraday scorer specifically targets stocks where:
1. **Volume is accumulating** — institutional interest building
2. **Bollinger Bands are squeezing then expanding** — volatility contracting before a breakout
3. **MACD crosses bullish** on the 5-minute chart
4. **RSI is in momentum zone** (55–75) without being overextended

These conditions together suggest a stock that has been "coiling" and is ready for a significant intraday swing.

---

## Dashboard Tabs

| Tab | What it does |
|---|---|
| **Scanner** | Score every ticker in the active watchlist, drill into candlestick + volume chart |
| **Coil Detector** | Stocks that have scored well across multiple scans without breaking out yet |
| **Confluence** | Stocks scoring well across intraday + short + long simultaneously |
| **Pattern Match** | Compare current 10-day windows against historical run-up/decline fingerprints |
| **Pre-Market** | Gap-up/down detection vs. previous close using pre-market quotes |
| **Options Flow** | Unusual options volume vs. open interest, put/call sentiment |
| **Alerts** | Configure Discord/email push for coil, confluence, and pattern thresholds |
| **Signal Journal** | Historical outcomes: did the move happen? Win rate by score bucket |
| **Weights** | Tune per-signal point values for each timeframe; persisted across restarts |
| **Help** | In-app documentation for every feature |

---

## Quickstart

```bash
# Install base dependencies (requires Python 3.11+)
pip install uv
uv pip install -e .

# Install optional provider extras
uv pip install -e ".[alpaca]"   # Alpaca real-time
uv pip install -e ".[ibkr]"     # Interactive Brokers
uv pip install -e ".[schwab]"   # Charles Schwab
uv pip install -e ".[all]"      # All providers

# For development + all providers (used by CI)
uv sync --extra dev --extra all

# Copy and fill in your credentials
cp .env.example .env

# Launch the dashboard
streamlit run tradex/ui/dashboard.py
```

```python
# Or run the screener programmatically
from tradex.screener.engine import run
results = run(
    ["AAPL", "NVDA", "TSLA"],
    timeframe="intraday",
    min_score=40,
    exclude_earnings_within=5,   # optional: skip stocks with earnings within 5 days
)
print(results)
```

---

## Data Providers

`DATA_PROVIDER` in your `.env` controls **OHLCV data** only (the central `fetch()` / `fetch_multi_report()` and the date-ranged daily-history abstraction). It does not change options, earnings, or market-cap sources. Every recorded signal stores the OHLCV provider that produced it in `signal_history.provider`, and every resolved outcome stores `outcome_provider`. Pre-existing rows are labeled `unknown`.

| Provider | `DATA_PROVIDER` value | Cost | Real-time | Setup |
|---|---|---|---|---|
| Yahoo Finance | `yahoo` (default) | Free | No (15-min delay) | None |
| Alpaca | `alpaca` | Free tier | Yes (IEX feed) | API key at alpaca.markets |
| Interactive Brokers | `ibkr` | Free (need IB account) | Yes | TWS/Gateway running locally |
| Charles Schwab | `schwab` | Free (need Schwab account) | Yes | OAuth app at developer.schwab.com; see `scripts/schwab_oauth.py` |

Optional retry/fallback configuration (all disabled by default):

- `OHLCV_MAX_RETRIES` — extra retry attempts per ticker for transient failures only (default `0`, max `3`).
- `OHLCV_FALLBACK_ORDER` — comma-separated whole-scan fallback provider chain (e.g. `schwab,yahoo`). No provider is inserted automatically; an empty/missing value means fallback is disabled.

These settings may also be passed programmatically as `FetchPolicy(max_retries=..., fallback_order=...)` or via `engine.run_with_report(..., policy=...)`.

> **Note:** TD Ameritrade's API was shut down in September 2024. Use `schwab` instead.
> Schwab output is normalized to a canonical OHLCV DataFrame (sorted, de-duplicated, UTC-indexed). Validate a local token with `scripts/schwab_smoke_test.py`.

### Specialized sources

These are independent of `DATA_PROVIDER` and use their own env vars / dashboard selectors:

- **Options flow**: `OPTIONS_DATA_SOURCE` (`auto`, `unusual_whales`, `tradier`, `yahoo`)
- **Earnings calendar**: `EARNINGS_DATA_SOURCE` (`yahoo` only in this release)
- **Market-cap ranking**: `MARKET_CAP_DATA_SOURCE` (`yahoo`, `schwab`)
- **Index constituents**: Wikipedia (no env var required)

---

## Signal State Tracking

The tracker module is what separates TradeX from standard screeners. Rather than showing you a snapshot, it builds a history of every ticker observed in every scan session and detects patterns across distinct NYSE trading sessions. `scan_sessions` and `scan_observations` are the canonical tables; `scan_runs` is the backward-compatible audit surface that stores requested/observed/hit counts, provider, status, and source for each run.

1. Run the **Scanner** tab (or `watcher.py` on a schedule) — every ticker requested is saved as an observation in `~/.tradex/signals.db`; qualifying signals are also written to `signal_history`
2. As history accumulates, the **Coil Detector** surfaces stocks scoring well for multiple distinct NYSE sessions *without breaking out yet*
3. The **Fading Setups** detector surfaces stocks that previously coiled but have started to deteriorate
4. The **Confluence** tab shows stocks scoring well across all three timeframes simultaneously
5. The **Outcome Tracker** fetches prices 1d/3d/5d after each signal and writes `outcome_pct` and `outcome_provider` back to the DB
6. The **Signal Journal** rolls those outcomes up into win rate / expectancy by score bucket and shows both the signal and outcome provider

### Coil detection logic
A "coil" is a stock that:
- Has appeared in scans on at least N distinct NYSE trading sessions over the look-back window
- Has a current score above threshold (default: 45)
- Has NOT already made a large price move (not already broken out)
- Has a score that is stable or trending upward

Coil appearances count distinct NYSE trading sessions, not scan rows, so running the watcher more often inside the same session does not mechanically create a coil.

### Running the watcher
```bash
# Run once — manual scans are allowed regardless of market status
python -m tradex.tracker.watcher --timeframe intraday

# Poll every 5 minutes and only scan during the NYSE regular session
python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only

# With retries and an explicit whole-scan fallback chain
python -m tradex.tracker.watcher --timeframe intraday --interval 5 \
  --max-retries 2 --fallback-order "schwab,yahoo" --market-hours-only
```

**Market-hours behavior**
- TradeX models the NYSE regular session in the `America/New_York` timezone using the `exchange-calendars` XNYS calendar.
- Scheduled interval scans can be gated with `--market-hours-only` so they skip weekends, NYSE holidays (including Good Friday), early closes, and pre/post-market hours.
- Manual one-off scans (`--interval 0`, the default) still run at any time unless `--market-hours-only` is also supplied.
- The daily pre-market gap scan is scheduled for `08:00 America/New_York`; the outcome resolution pass is scheduled for `16:30 America/New_York`. Both remain at the same New York wall-clock time across DST changes and skip non-trading days.
- Pre-market gap filtering uses the actual regular-session open from the exchange calendar and keeps only bars from `04:00` ET up to (but not including) the open on the intended session date.

---

## Earnings Awareness

A technically-clean setup that resolves *into* an earnings print is no longer a technical trade — it's a binary event bet. TradeX fetches the next earnings date per ticker via yfinance (cached 24h in `~/.tradex/earnings_cache.db`) and exposes:

- **Sidebar slider** — "Exclude earnings within N days" filters Scanner + Confluence results
- **"Earnings In" column** — always shown in result tables so you can see proximity at a glance even with the filter off

---

## Watchlist Persistence

Save and switch between named ticker lists (e.g. "Semis", "Crypto-adjacent", "Earnings plays") from the sidebar. Persisted to `~/.tradex/watchlists.db`. The built-in **Default** list of 20 mega-cap and high-volume tickers cannot be deleted; everything else is fully editable.

---

## Roadmap

### Completed
- [x] Multi-provider data fetcher (Yahoo, Alpaca, IBKR, Schwab)
- [x] Validated and hardened Schwab provider with credential-free contract tests
- [x] Signal state tracking (SQLite history, coil detection, confluence scoring)
- [x] Automated outcome tracking (1d/3d/5d price fetch, win rate, expectancy by score bucket)
- [x] Signal journal with quality breakdown by score range and timeframe
- [x] Historical pattern fingerprinting (mine run-ups/declines, average pre-event windows, match live stocks)
- [x] Alert system (Discord bot + email when coil / confluence / pattern thresholds crossed)
- [x] Pre-market gap scanner
- [x] Options flow integration (unusual vol/OI, put/call sentiment)
- [x] In-app Help tab + tooltips throughout dashboard
- [x] Earnings awareness — filter + flag stocks with earnings within N days
- [x] Watchlist persistence — save/load/delete named watchlists
- [x] Scoring weight customization — per-signal sliders in the Weights tab, persisted to ~/.tradex/weights.json

### Still on the list
- [x] Add provider/source provenance persistence to signal history and outcomes (PROVIDER-004)
- [x] Define provider failure and fallback policy (PROVIDER-005)
- [x] Add market-hours and timezone handling (COR-005)
- [x] Redesign signal-history storage and access patterns (DATA-001)
- [x] Fix scan audit to accurately distinguish requested, observed, qualifying, and failed scans (COR-012)
- [ ] Backtesting module to validate signal quality historically (VAL-001)
- [ ] Portfolio-level risk view

### Nice-to-have enhancements
- [ ] Sector/industry grouping — show signals rolled up by sector to spot rotations
- [ ] Correlation-aware confluence — penalize confluence across highly correlated tickers
- [ ] Live alerts triggered by the watcher (currently alerts must be checked from the dashboard)
- [ ] Mobile-friendly dashboard view
- [ ] Export scan results to CSV / Notion
- [ ] Walk-forward optimization for signal weights (once backtesting exists)
- [ ] News sentiment overlay on the drill-down chart
- [ ] Multiple Discord channels per alert type
