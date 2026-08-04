# TradeX — Stock Market Opportunity Scanner

TradeX identifies trading opportunities across three timeframes: **intraday**, **short-term (days/weeks)**, and **long-term (weeks/months)**. It is especially tuned to detect intraday setups preceded by multi-day volume and volatility accumulation ("coiling" patterns that resolve into big intraday swings).

> **Setting up on a new machine?** See [`SETUP.md`](SETUP.md) — a single end-to-end install guide written so an AI agent (Claude, ChatGPT, etc.) can execute it directly. Tell it "read SETUP.md and set this up" and it will handle Mac or Windows install, venv creation, `.env` setup, and the desktop launcher.

---

## Project Structure

```
tradex/
├── tradex/
│   ├── data/fetcher.py            # Multi-provider OHLCV fetcher (Yahoo, Alpaca, IBKR, Schwab)
│   ├── market/
│   │   ├── context.py             # Point-in-time regime and relative-strength context
│   │   └── models.py              # ShortContextPolicy, ShortTermMarketContext
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
│   ├── research/
│   │   ├── pattern_validation/    # PATTERN-001 point-in-time pattern-similarity validation
│   │   ├── score_validation/      # VAL-002 reproducible score-validation study
│   │   └── short_context/         # SHORT-001 market-context research pipeline
│   ├── premarket/
│   │   ├── gap_scanner.py         # Public scan orchestrator + compat wrappers
│   │   ├── models.py              # PremarketSnapshot, GapScanReport, catalyst/spread models
│   │   ├── sources.py             # Pre-market OHLCV, liquidity baseline, spread snapshots
│   │   ├── catalysts.py           # Earnings + headline context (explicitly sourced, non-causal)
│   │   ├── config.py              # Validated GapScanConfig
│   │   ├── cli.py                 # `python -m tradex.premarket scan ...`
│   │   └── __main__.py            # CLI entry point
│   ├── options/
│   │   ├── models.py              # Typed options source, capability, and scan report models
│   │   └── flow.py                # True-flow scanning, chain-snapshot scanning, put/call balance
│   ├── alerts/
│   │   ├── models.py              # AlertKey, AlertCooldownConfig, AlertDispatchResult
│   │   ├── notifier.py            # Discord bot + email alerting helpers
│   │   ├── policy.py              # Persistent cooldown, atomic claim, deduplication
│   │   └── store.py               # Isolated SQLite alert cooldown state
│   ├── earnings/calendar.py       # Next-earnings lookup + 24h SQLite cache
│   ├── watchlists/store.py        # Named watchlist persistence
│   └── ui/dashboard.py            # Streamlit dashboard (10 tabs)
├── docs/
│   ├── PROJECT-TRACKER.md
│   ├── AI-DEVELOPMENT-WORKFLOW.md
│   ├── RESEARCH-PROTOCOL.md
│   └── decisions/            # Architecture Decision Records (ADRs)
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
| **Confluence** | Stocks scoring well across intraday + short + long simultaneously; coverage (0/3–3/3) is now explicit |
| **Pattern Similarity** | Experimental research: compare current 10-day windows against historical run-up/decline fingerprints. Not used in production scoring or automatic alerts. |
| **Pre-Market** | Gap-up/down detection vs. previous close using pre-market quotes |
| **Options Activity** | True options-flow events (Unusual Whales) and options-chain snapshots (Tradier/Yahoo), with non-directional put/call volume balance |
| **Alerts** | Configure Discord/email push and view persistent cooldown state for coil, confluence, and gap alerts. Pattern matching is quarantined from automatic alerts. |
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

### Backtesting (VAL-001)

Run a deterministic, point-in-time backtest for the short-term scorer from an offline CSV. The CSV must contain `datetime` (or `date`), `open`, `high`, `low`, `close`, and `volume`. Use `--ticker` to identify the security; `--csv` only supplies the price history.

```bash
uv run python -m tradex.backtest \
  --csv data/spy_daily.csv \
  --ticker SPY \
  --min-score 40 \
  --warmup-bars 60 \
  --holding-bars 3 \
  --stop-loss-pct 5 \
  --take-profit-pct 10 \
  --json-output result.json \
  --trades-output trades.csv \
  --equity-output equity.csv
```

Provider-backed daily history is also supported (requires credentials for Schwab):

```bash
uv run python -m tradex.backtest \
  --ticker SPY \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --provider yahoo
```

Programmatic usage:

```python
from tradex.backtest.engine import run_short_term_backtest
from tradex.backtest.io import load_csv
from tradex.backtest.models import BacktestConfig

bars = load_csv("data/spy_daily.csv", timezone="America/New_York")
config = BacktestConfig(min_score=40, max_holding_bars=3)
result = run_short_term_backtest("SPY", bars, config=config)
print(result.metrics)
print(result.to_json())
```

**Execution model (research only, not trading advice)**

- Long-only, one position at a time, 100% of available capital per trade, fractional shares.
- Signals are generated point-in-time: the scorer sees only `bars.iloc[:i+1]` at bar `i`.
- Entry is always at the next bar's open.
- Stop and target levels are anchored to the **entry fill** (`open * (1 + slippage_bps / 10_000)`), not the signal bar close. This means entry gaps and entry slippage affect the risk levels.
- Cost model:
  - `entry_fill = open * (1 + slippage_bps / 10_000)`
  - `cash_per_share = entry_fill * (1 + commission_bps / 10_000)`
  - `quantity = capital / cash_per_share`
  - `exit_fill = raw_exit * (1 - slippage_bps / 10_000)`
  - `ending_cash = quantity * exit_fill * (1 - commission_bps / 10_000)`
- Exit priority for each holding bar:
  1. Opening gap through stop or target (`gap_stop` / `gap_target`) — exit at the open.
  2. Intraday stop or target touch. If both are touched in the same bar and `intrabar_policy=stop_first` (the default), the stop is elected; with `target_first`, the target is elected.
  3. `time_exit` at the close of the last allowed bar (`max_holding_bars`).
- The equity curve marks every bar as exposed (`position_open=True`) if a position is held at any point during that bar, including the entry and exit bars. The `position_ticker` column records the active ticker.
- Max drawdown is the largest peak-to-trough decline of the equity curve, expressed as a negative percentage.
- The buy-and-hold benchmark uses the same cost model applied once over the evaluation window.

**Output schemas**

- `result.to_json()` returns a JSON-safe dict with no `NaN` or `Infinity`; `equity_curve` rows include `timestamp`, `equity`, `cash`, `position_quantity`, `position_open`, `position_ticker`, `close`, `daily_return`, `running_peak`, and `drawdown_pct`.
- `result.to_trades_df()` always returns the stable trade ledger columns, even when no trades occur.
- `result.to_signals_df()` always returns the stable signal ledger columns.

**Known limitations and biases**

- This is a research harness, not a live-trading system.
- It does not eliminate survivorship bias, delisting bias, or point-in-time index membership.
- Corporate actions, provider adjustments, retroactive splits, and liquidity capacity are not modeled.
- Execution uses daily bars; real intraday order placement, slippage timing, and partial fills are not simulated.
- Reported metrics are research evidence, not proof of a durable edge or statistical significance.

### Score validation study (VAL-002)

Run a reproducible, point-in-time event study that calls the production `tradex.signals.short_term.score` with an explicit fresh `ShortWeights()` and records 1-, 3-, and 5-bar forward returns. The study separates an **event study** (overlapping observations allowed) from the **executable backtest** in `tradex/backtest`.

```bash
# 1) Build an offline, versioned dataset (network allowed; credentials optional)
uv run python -m tradex.research.score_validation snapshot \
  --tickers AAPL,MSFT,SPY \
  --start 2020-01-01 \
  --end 2023-12-31 \
  --provider yahoo \
  --output-dir data/score_validation_snapshot \
  --development-split 2018-01-01,2022-12-31 \
  --validation-split 2023-01-01,2024-12-31 \
  --holdout-split 2025-01-01,2025-12-31

# 2) Evaluate offline (no network, no credentials, no ~/.tradex/weights.json)
uv run python -m tradex.research.score_validation evaluate \
  --manifest data/score_validation_snapshot/manifest.json \
  --output-dir results/score_validation \
  --warmup-bars 60 \
  --horizons 1,3,5 \
  --slippage-bps 0.0,5.0,10.0
```

Outputs (`results/score_validation/`):

- `study.json` — deterministic, JSON-safe full result.
- `events.csv` — one row per point-in-time score observation.
- `score_buckets.csv`, `thresholds.csv`, `components.csv` — pooled and per-ticker summaries.
- `score_distribution.csv`, `component_frequency.csv`, `ticker_summary.csv`, `data_quality.csv`.
- `report.md` — 20-section human-readable report with a production-change disclaimer.
- `manifest.lock.json` — locked manifest used for the run.

Key design choices:

- Scores are computed on `bars.iloc[:i+1]`; entry is the next bar's open; exit is the horizon-bar close.
- Splits (`development`, `validation`, `holdout`) are enforced so events and their forward returns do not cross boundaries.
- Default cost model uses `entry_fill = open * (1 + slippage_bps / 10_000)`, `exit_fill = close * (1 - slippage_bps / 10_000)`, and `commission_bps` on both legs.
- The scorer always receives a fresh `ShortWeights()` instance; no saved `~/.tradex/weights.json` is loaded silently.
- Studies are deterministic: the same manifest and configuration produce byte-identical CSVs, JSON, and Markdown reports, including `study.json`, `report.md`, and `manifest.lock.json`.

**Valid outcome:** A study may conclude `insufficient evidence to change the production score`. The tool does not automatically select, promote, or mutate production thresholds.

### Pattern similarity validation (PATTERN-001)

`tradex/research/pattern_validation` runs a locked, point-in-time study of the existing `tradex/patterns/matcher` using Pearson shape similarity weighted by `SERIES_WEIGHTS`. It evaluates whether decision dates with similarity ≥ 75 produce higher signed five-session returns than frequency-matched controls after conservative execution costs.

```powershell
# Windows PowerShell workflow for the locked PATTERN-001 Schwab study.
# Run from the repository root after placing your Schwab token at the documented path.

# 1) Verify the token exists (do not print token contents).
Test-Path "$env:USERPROFILE\.tradex_schwab_token.json"
Get-Item "$env:USERPROFILE\.tradex_schwab_token.json" | Select-Object FullName, Length, LastWriteTime

# 2) Optional read-only Schwab smoke test.
uv --system-certs run python scripts/schwab_smoke_test.py

# 3) Build the locked offline snapshot. Use the exact ordered MINING_UNIVERSE and dates.
$SnapshotDir = "$env:USERPROFILE\.tradex\research\pattern-validation\snapshot"
uv --system-certs run python -m tradex.research.pattern_validation snapshot `
  --universe current-mining-universe `
  --start 2018-01-02 `
  --end 2026-07-31 `
  --provider schwab `
  --output $SnapshotDir

# 4) Evaluate offline (no network, no credentials, no ~/.tradex/fingerprints.db)
$ResultsDir = "$env:USERPROFILE\.tradex\research\pattern-validation\results"
uv --system-certs run python -m tradex.research.pattern_validation evaluate `
  --manifest "$SnapshotDir\manifest.lock.json" `
  --output $ResultsDir
```

The locked study uses the full `MINING_UNIVERSE` from `tradex/patterns/miner.py`. Raw OHLCV, `.env`, OAuth tokens, credentials, and HTTP responses must never be committed; the handoff bundle is described in `docs/research/PATTERN-001.md`.

Outputs (`$ResultsDir`):

- `study.json`, `study_spec.lock.json`, `manifest.lock.json`, `development_fingerprints.json`
- `observations.csv`, `qualifying_signals.csv`, `frequency_matched_controls.csv`, `event_study.csv`, `executable_trades.csv`
- `baseline_comparison.csv`, `ticker_summary.csv`, `period_summary.csv`, `data_quality.csv`
- `promotion_decision.json`, `report.md`, `artifact_manifest.json`

Key design choices:

- One immutable fingerprint is built per event type from the **development split only**; no read/write to `~/.tradex/fingerprints.db`.
- Validation/holdout use the same development fingerprint; no threshold, weight, lookback, profile, or universe tuning is allowed.
- Splits are fixed: development 2018-01-02–2021-12-31, validation 2022-01-03–2023-12-29, holdout 2024-01-02–2026-07-31.
- Execution: signal known after decision-date close, entry at next open, exit at close of the fifth session; cost scenarios 0/5/10 bps per side.
- The `MINING_UNIVERSE` from `tradex/patterns/miner.py` is copied into the study spec and hashed; the universe is described as a fixed convenience cohort, not a point-in-time index.
- `production_promotion_eligible` is always `false` because the universe is not point-in-time.
- For Schwab, the adjustment policy is `provider_default`: the provider-returned daily candles are used as-is, the study does not apply additional split or dividend adjustment, and the exact corporate-action methodology is not independently verified beyond the provider contract.

**Completed local Schwab study:** The locked PATTERN-001 study was run on the full `MINING_UNIVERSE` using Schwab daily candles. The result was **`rejected`** for both run-up and decline at the 10 bps/side decision cost, with `production_promotion_eligible=false`. The sanitized aggregate safe-handoff bundle is preserved at `docs/research/artifacts/PATTERN-001/2026-08-03-9ea40e85/` and summarized in `docs/research/PATTERN-001.md`. No matcher parameters were changed, and pattern matching remains quarantined from production scoring, ranking, eligibility, and automatic alerts.

### Short-term market context research (SHORT-001)

`tradex/research/short_context` evaluates whether adding market-regime and relative-strength context improves the short-term scorer. It reuses the VAL-002 snapshot/evaluation design and adds point-in-time context computation in `tradex/market/context.py`.

Candidate context policies:

- `off` — baseline short-term score, no proxy fetches.
- `market_rs` — requires the broad market to be in a bullish regime and have positive relative strength.
- `market_sector_rs` — also requires the sector proxy to be bullish and relatively strong.

The research scorer `short_term.score(df, context=..., context_policy=...)` keeps the numeric `score` unchanged and adds `base_score`, `context_eligible`, `context_status`, `context_reasons`, and `market_context`. A candidate context policy is only promoted to production when both the event-study and paired-backtest holdout gates pass; until then, the production screener does not expose context filtering.

```bash
# CLI
uv run python -m tradex.research.short_context --help
uv run python -m tradex.research.short_context snapshot --help
uv run python -m tradex.research.short_context evaluate --help
```

A failed or inconclusive study leaves the existing short-term score, weights, thresholds, and production behavior unchanged.

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

### Runtime configuration

All runtime configuration lives in `tradex/config.py`. The public boundary is:

- `settings_from_mapping(values)` — build a `TradeXSettings` from a plain dict without reading `.env` or `os.environ`.
- `load_runtime_settings(dotenv_path=None)` — call-time loader that reads `.env` once, then applies `os.environ` overrides, but never mutates the process environment.

Every public entry point accepts an optional `settings: TradeXSettings | None = None` keyword argument. When `settings` is omitted, the function calls `load_runtime_settings()` at call time, so modules can be imported safely without a `.env` file or credentials.

### Specialized sources

These are independent of `DATA_PROVIDER` and use their own env vars / dashboard selectors:

- **Options activity**: `OPTIONS_DATA_SOURCE` (`auto`, `unusual_whales`, `tradier`, `yahoo`). Unusual Whales supplies true transaction-level flow; Tradier and Yahoo supply chain snapshots only.
- **Earnings calendar**: `EARNINGS_DATA_SOURCE` (`yahoo` only in this release)
- **Market-cap ranking**: `MARKET_CAP_DATA_SOURCE` (`yahoo`, `schwab`)
- **Index constituents**: Wikipedia (no env var required)

---

## Signal State Tracking

The tracker module is what separates TradeX from standard screeners. Rather than showing you a snapshot, it builds a history of every ticker observed in every scan session and detects patterns across distinct NYSE trading sessions. `scan_sessions` and `scan_observations` are the canonical tables; `scan_runs` is the backward-compatible audit surface that stores requested/observed/hit counts, provider, status, and source for each run.

1. Run the **Scanner** tab (or `watcher.py` on a schedule) — every ticker requested is saved as an observation in `~/.tradex/signals.db`; qualifying signals are also written to `signal_history`
2. As history accumulates, the **Coil Detector** surfaces stocks scoring well for multiple distinct NYSE sessions *without breaking out yet*
3. The **Fading Setups** detector surfaces stocks that previously coiled but have started to deteriorate
4. The **Confluence** tab shows stocks scoring well across all three timeframes simultaneously; missing timeframes contribute zero and are shown in coverage metadata
5. The **Outcome Tracker** fetches prices 1d/3d/5d after each signal and writes `outcome_pct` and `outcome_provider` back to the DB
6. The **Signal Journal** rolls those outcomes up into win rate / expectancy by score bucket and shows both the signal and outcome provider

### Coil detection logic
A "coil" is a stock that:
- Has appeared in scans on at least N distinct NYSE trading sessions over the look-back window
- Has a current score above threshold (default: 45)
- Has NOT already made a large price move (not already broken out)
- Has a score that is stable or trending upward

Coil appearances count distinct NYSE trading sessions, not scan rows, so running the watcher more often inside the same session does not mechanically create a coil.

### Confluence scoring

The **Confluence** tab and `run_confluence_screen()` combine the intraday (30%), short-term (40%), and long-term (30%) scores using a **fixed denominator**. Missing or failed timeframes contribute zero; the score is never renormalized across whichever timeframes happen to be available. Coverage is reported as `0/3`, `1/3`, `2/3`, or `3/3` so you can see exactly how much data contributed.

Tiers use both the corrected score and the number of contributing/active timeframes:
- `all timeframes aligned` requires **3/3** coverage, all three timeframes active (score ≥ 50), and a confluence score ≥ 90.
- `strong confluence` requires at least two active timeframes and a score ≥ 70.
- `moderate confluence` requires at least two active timeframes and a score ≥ 50.
- `weak / single timeframe`, `weak / incomplete timeframes`, `weak confluence`, or `no data` describe everything else.

This is a heuristic confluence model, not proof of higher returns. Confluence scores feed the existing Scanner, dashboard, and alert thresholds unchanged.

### Running the watcher
```bash
# Run once — manual scans are allowed regardless of market status
python -m tradex.tracker.watcher --timeframe intraday

# Poll every 5 minutes and only scan during the NYSE regular session
python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only

# With retries and an explicit whole-scan fallback chain
python -m tradex.tracker.watcher --timeframe intraday --interval 5 \
  --max-retries 2 --fallback-order "schwab,yahoo" --market-hours-only

# Override alert cooldown duration, disable it, or use a custom state database
python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-cooldown-minutes 120
python -m tradex.tracker.watcher --timeframe intraday --interval 5 --disable-alert-cooldown
python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-state-path /path/to/alerts.db
```

The watcher uses a persistent SQLite alert state database (default `~/.tradex/alerts.db`). Each alert is identified by `(ticker, alert_type, timeframe)` and suppressed during the configured cooldown. The first eligible alert is sent; repeats are blocked. Manual test alerts from the dashboard bypass cooldown. State is only mutated when at least one channel successfully receives the alert.

**Market-hours behavior**
- TradeX models the NYSE regular session in the `America/New_York` timezone using the `exchange-calendars` XNYS calendar.
- Scheduled interval scans can be gated with `--market-hours-only` so they skip weekends, NYSE holidays (including Good Friday), early closes, and pre/post-market hours.
- Manual one-off scans (`--interval 0`, the default) still run at any time unless `--market-hours-only` is also supplied.
- The daily pre-market gap scan is scheduled for `08:00 America/New_York`; the outcome resolution pass is scheduled for `16:30 America/New_York`. Both remain at the same New York wall-clock time across DST changes and skip non-trading days.
- Pre-market gap filtering uses the actual regular-session open from the exchange calendar and keeps only bars from `04:00` ET up to (but not including) the open on the intended session date. It excludes bars after the injected `as_of` timestamp, so historical/replay scans are point-in-time.

---

## Architecture Decision Records

Major architectural and policy decisions are recorded in [`docs/decisions/`](docs/decisions/). The index at [`docs/decisions/README.md`](docs/decisions/README.md) lists accepted ADRs for coil detection, confluence scoring, the OHLCV provider contract, and market-timezone handling. New ADRs follow the template at [`docs/decisions/0000-template.md`](docs/decisions/0000-template.md).

---

## Pre-Market Gap Scanner

The scanner in `tradex/premarket/` finds stocks that have gapped from their prior regular-session close during the pre-market window (04:00 ET up to the regular open). It is built around a typed, validated `GapScanConfig` and returns a structured `GapScanReport`.

**Quality controls (all opt-in, default is only the 2% minimum absolute gap):**
- Minimum absolute gap, minimum price, and pre-market share/dollar volume thresholds
- Pre-market volume as a multiple of recent average daily volume (configurable lookback)
- Data-age freshness limit for the latest 1-minute bar
- Optional spread filter (only real bid/ask quotes; never inferred from the candle range)
- Optional catalyst requirement (earnings and/or recent Yahoo headline, explicitly sourced, no causal claims)
- Optional `allow_after_open` for retrospective scans

**Public API:**
```python
from tradex.premarket import GapScanConfig, scan_gaps_with_report

report = scan_gaps_with_report(
    ["AAPL", "TSLA"],
    config=GapScanConfig(min_abs_gap_pct=4.0, min_premarket_volume_ratio=0.5),
    provider="yahoo",
)
print(report.counts())
print(report.results)
```

**CLI:**
```bash
python -m tradex.premarket scan --tickers AAPL,TSLA --min-gap 4.0 --min-premarket-volume 10000
```

The scheduled watcher uses `scan_gaps_with_report` so it logs requested, qualified, filtered, failed, and outside-window counts and only fires alerts on `large`/`massive` qualified gaps.

---

## Options Activity

The Options Activity dashboard tab and `tradex/options/flow.py` distinguish two kinds of options data:

- **True options flow** — transaction-level events such as sweeps, reported premium, side, and event timestamps. Only Unusual Whales (`UNUSUAL_WHALES_API_KEY`) can supply this. The true-flow scan is disabled when no key is configured.
- **Options-chain snapshots** — delayed or provider-defined listings of contracts with volume, open interest, bid, ask, and last. Tradier (`TRADIER_API_KEY`) and Yahoo provide snapshots, not individual trades.

**Key usage rules:**
- Chain volume/OI is never presented as "unusual options flow" or as a directional/institutional signal.
- `vol_oi_ratio` is `volume / open_interest` only when both values are finite, non-negative volume, and strictly positive open interest; otherwise it is `null`.
- True-flow events from Unusual Whales that lack a valid `open_interest` value receive `vol_oi_ratio=None` and are excluded from `min_vol_oi` filtering.
- Put/call volume balance is explicitly non-directional. Values are `call_heavy`, `put_heavy`, `balanced`, `call_only`, `put_only`, `unknown`, or `unavailable`.
- `directional_inference` is always `false` for aggregate chain volume.

**Public API:**
```python
from tradex.options.flow import (
    scan_unusual_flow_with_report,
    scan_chain_activity_with_report,
    get_put_call_activity,
    resolve_flow_source,
    resolve_chain_source,
)

# True flow (requires Unusual Whales)
report = scan_unusual_flow_with_report(["AAPL"], min_vol_oi=3.0, source="auto")

# Chain snapshot (Tradier or Yahoo)
report = scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0, source="auto")

# Non-directional put/call balance from a chain source
balance = get_put_call_activity("AAPL", source="auto")
```

Legacy wrappers `scan_unusual_flow(...)` and `get_put_call_sentiment(...)` remain importable for backward compatibility.

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
- [x] Alert system (Discord bot + email when coil / confluence / pattern / gap thresholds crossed)
- [x] Persistent alert cooldown, deduplication, and audit state
- [x] Pre-market gap scanner
- [x] Quality-aware pre-market gap scanner with structured reports, liquidity metrics, spread/catalyst filters, and point-in-time replay (GAP-001)
- [x] Options activity gating (OPT-001) — true options flow (Unusual Whales) separated from chain snapshots (Tradier/Yahoo); put/call volume balance is non-directional
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
- [x] Backtesting module to validate signal quality historically (VAL-001)
- [x] Reproducible, point-in-time score validation study (VAL-002)
- [x] Short-term market context research pipeline and holdout gates (SHORT-001 — research infrastructure complete; production integration blocked pending real-data gates)
- [ ] Portfolio-level risk view

### Nice-to-have enhancements
- [ ] Sector/industry grouping — show signals rolled up by sector to spot rotations
- [ ] Correlation-aware confluence — penalize confluence across highly correlated tickers
- [x] Live alerts triggered by the watcher with persistent cooldown and deduplication
- [ ] Mobile-friendly dashboard view
- [ ] Export scan results to CSV / Notion
- [ ] Walk-forward optimization for signal weights (once backtesting exists)
- [ ] News sentiment overlay on the drill-down chart
- [ ] Multiple Discord channels per alert type
