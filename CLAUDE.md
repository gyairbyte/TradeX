# CLAUDE.md — TradeX Project Context

> **Setting up the app on this machine?** See [`SETUP.md`](SETUP.md) — it's the canonical install procedure (Mac + Windows, venv, `.env`, launchers, verification). If the user asks to "set up TradeX" or "install this", execute SETUP.md rather than improvising.
>
> **AI agents and contributors:** Before significant implementation or research work, read the canonical governance documents: [`docs/AI-DEVELOPMENT-WORKFLOW.md`](docs/AI-DEVELOPMENT-WORKFLOW.md) for the ChatGPT–Devin–Codex workflow, [`docs/RESEARCH-PROTOCOL.md`](docs/RESEARCH-PROTOCOL.md) for trading-research safeguards, and [`docs/PROJECT-TRACKER.md`](docs/PROJECT-TRACKER.md) for the current backlog.

## What This Project Is

TradeX is a personal stock market opportunity identifier built for Gary Yang. It scans stocks across three timeframes and scores them based on technical signals. The goal is to surface actionable trade setups — especially intraday swing opportunities that are preceded by detectable multi-day volume/volatility buildup.

Gary is particularly interested in:
- **Intraday setups**: Stocks that have shown unusual volume and price compression over 2–5 days, then resolve into big intraday swings
- **Short-term momentum plays**: Days to weeks, trend + volume confirmation
- **Long-term accumulation**: Weeks to months, secular uptrends with healthy consolidation

---

## Architecture Philosophy

- **Keep it simple and readable** — this is a tool for understanding the market, not just black-box outputs. Every signal should have a human-readable reason.
- **Score-based ranking** — all signals produce a 0–100 score so results are comparable across tickers and timeframes
- **Modular signal logic** — each timeframe has its own scorer in `tradex/signals/`. Adding a new signal means editing one file.
- **Pluggable data providers** — `fetcher.py` supports Yahoo (default), Alpaca, IBKR, and Schwab. Switching is one env var (`DATA_PROVIDER`). All providers return the same normalized DataFrame so signal code never knows which provider is active.

---

## Key Architecture: Signal State Tracking

The `tradex/tracker/` module is the core differentiator. Standard screeners give you a snapshot. TradeX builds a history of every signal fired across time and uses that history to detect coiling patterns before they resolve into moves.

**Data flow:**
```
Scanner runs → results DataFrame
    → store.record_signals()     persists to SQLite (~/.tradex/signals.db)
    → analyzer.detect_coils()   reads history, returns pre-breakout candidates
    → confluence.score_confluence() scores across all 3 timeframes simultaneously
    → store.get_signal_journal() shows outcomes after signals fired
```

**Coil definition:** a stock is "coiling" when it has appeared in scans N+ times, is still scoring above threshold, has NOT yet made a large price move, and its score is stable or rising. This is the pre-signal detection layer.

---

## File Map

| File | Purpose |
|---|---|
| `tradex/data/fetcher.py` | Multi-provider OHLCV fetcher. Providers: `yahoo`, `alpaca`, `ibkr`, `schwab`. Three timeframe presets: `intraday` (5m/5d), `short` (1d/60d), `long` (1wk/2yr). Provider selected via `DATA_PROVIDER` env var. |
| `tradex/signals/indicators.py` | Shared indicator computation: RSI, MACD, EMA20/50, Bollinger Bands, ATR, volume ratio |
| `tradex/signals/intraday.py` | Intraday swing scorer — volume surge, BB expansion, MACD crossover, RSI momentum |
| `tradex/signals/short_term.py` | Short-term scorer — EMA structure, volume confirmation, MACD, pullback-to-EMA setups |
| `tradex/signals/long_term.py` | Long-term scorer — secular trend, volume accumulation, weekly MACD, BB coiling |
| `tradex/screener/engine.py` | Runs a scorer over a watchlist, filters by min_score, returns sorted DataFrame |
| `tradex/tracker/store.py` | SQLite persistence for signal history and canonical scan sessions/observations. Tables: `signal_history`, `scan_sessions`, `scan_observations`, `scan_runs`. DB at `~/.tradex/signals.db`. |
| `tradex/tracker/analyzer.py` | Coil detector — reads history, finds stocks building pressure without breaking out. Returns coil strength score. |
| `tradex/tracker/confluence.py` | Scores a ticker across all 3 timeframes simultaneously. Coverage-aware weighted score (intraday 30%, short 40%, long 30%). |
| `tradex/tracker/outcome_tracker.py` | Automated outcome marking. Fetches price at 1d/3d/5d after signal fires, writes outcome_pct back to DB. Also exposes `get_outcome_stats()` for win rate by score bucket. |
| `tradex/tracker/watcher.py` | Scheduled scan runner. Runs screener on interval, persists results, triggers outcome pass daily at 4:30pm ET. `python -m tradex.tracker.watcher --interval 5` |
| `tradex/patterns/config.py` | PatternConfig dataclass + 3 profiles: `conservative`, `standard`, `volatile`. All thresholds configurable. |
| `tradex/patterns/miner.py` | Mines 3yr daily history, finds run-up/decline events, extracts normalized pre-event windows. Universe: ~40 stocks. |
| `tradex/patterns/fingerprint.py` | Averages mined windows into fingerprints (mean ± std per series). Persists to `~/.tradex/fingerprints.db`. |
| `tradex/patterns/matcher.py` | Compares live 10-day window against fingerprint using weighted Pearson correlation. Returns 0–100 similarity score. |
| `tradex/premarket/config.py` | Validated `GapScanConfig` dataclass for the pre-market gap scanner. |
| `tradex/premarket/models.py` | Typed dataclasses: `PremarketSnapshot`, `DailyLiquidityBaseline`, `SpreadSnapshot`, `GapCatalystContext`, `GapObservation`, `GapScanReport`. |
| `tradex/premarket/sources.py` | Pre-market OHLCV source adapter, daily liquidity baseline, and spread snapshots. |
| `tradex/premarket/catalysts.py` | Earnings + headline context (explicitly sourced, no causal inference). |
| `tradex/premarket/gap_scanner.py` | Public orchestration layer (`scan_gaps_with_report`) and backward-compatible `scan_gaps` wrapper. |
| `tradex/premarket/cli.py` | Pre-market scanner CLI (`python -m tradex.premarket scan ...`). |
| `tradex/options/models.py` | Typed options source/capability and scan report models (`OptionsDataKind`, `OptionsSourceStatus`, `OptionsActivityReport`). |
| `tradex/options/flow.py` | Capability-aware options source resolution, true-flow scanning, chain-snapshot scanning, and non-directional put/call balance. |
| `tradex/ui/dashboard.py` | Streamlit UI: Scanner, Coil Detector, Confluence, Pattern Match, Pre-Market, Signal Journal, Weights, Alerts, Options Activity, Help |
| `pyproject.toml` | Python 3.11+ project, deps: yfinance, pandas, ta, streamlit, plotly |
| `.env.example` | Template for all provider credentials (Yahoo needs none; Alpaca needs API keys; IBKR needs TWS running; Schwab needs OAuth app + token file) |

---

## How to Run

```bash
# Dashboard (recommended)
streamlit run tradex/ui/dashboard.py

# Programmatic
from tradex.screener.engine import run
df = run(["AAPL", "NVDA", "AMD"], timeframe="intraday", min_score=40)
```

---

## Development Guidelines

1. **Signal scores must sum to 100 max** — use `min(sum(signals), 100)` in each scorer
2. **Always return `reasons` list** from scorers — these surface in the UI and must be human-readable
3. **No silent failures in screener** — print `[skip] {ticker}: {error}` and continue
4. **Prefer `ta` library for indicators** — don't reimplement RSI/MACD by hand
5. **Test with a small watchlist first** before running 100+ tickers (yfinance rate limits)

---

## Next Features to Build (in priority order)

1. **Alert system** — push notification or Slack webhook when coil or confluence threshold is crossed
2. **Earnings awareness** — flag or filter stocks with earnings within N days
3. **Options activity dashboard** — true options-flow events (Unusual Whales) and chain-snapshot activity (Tradier/Yahoo) are displayed separately, not mixed as directional signals
4. **Watchlist persistence** — save/load named watchlists to disk or DB
5. **Scoring weight customization** — let user tune signal weights in UI
6. **Long-term score validation** — compare the long-term scorer to a simple 40-week MA benchmark

---

## Key Decisions Made

- **yfinance as default, four providers supported** — Yahoo requires no setup and works for short/long. For real intraday scanning, Alpaca (free) or Schwab (if you have an account) are the right upgrades. IBKR is most powerful but requires running TWS locally.
- **TD Ameritrade is dead** — shut down Sept 2024. `schwab-py` is the direct replacement using the Schwab Developer API. Do not reference `tda-api`.
- **Schwab provider is validated and hardened** — `tradex/data/fetcher.py` normalizes Schwab candles to the canonical OHLCV contract (sorted, de-duplicated, UTC-indexed DataFrame with columns `open`, `high`, `low`, `close`, `volume`). The contract is enforced by deterministic, credential-free tests in `tests/data/test_schwab_provider.py`.
- **Provider abstraction in fetcher.py only** — signal code receives a plain DataFrame and never knows which provider supplied it. Keep it that way.
- **OAuth token safety** — Schwab tokens live outside the repo. `scripts/schwab_oauth.py` refuses to write a token inside the project and sets restrictive file permissions.
- **Provider propagation** — `screener/engine.py`, `tracker/watcher.py`, and `ui/dashboard.py` now thread `provider` through to `fetch()` for all OHLCV workflows.
- **Pre-market gap scanner is source-aware** — `tradex/premarket/sources.py` resolves the OHLCV provider once and rejects unsupported providers with `ProviderCapabilityError`. Spread and catalyst sources are explicit and never silently fall back.
- **Options activity is separated from directional signals** — `tradex/options/flow.py` distinguishes true transaction-level flow (Unusual Whales) from delayed/aggregate options-chain snapshots (Tradier/Yahoo). Chain volume/OI is labeled `chain_snapshot`, is never presented as "unusual options flow," and the put/call volume balance is explicitly non-directional.
- **Streamlit for UI** — fastest to iterate on, no frontend knowledge needed. Can replace with React later if needed.
- **Score-based not rule-based** — a pure rule-based "buy/sell" signal is brittle; scores let Gary apply judgment.
- **Three separate scorers vs. one unified** — timeframes have fundamentally different signal logic; keeping them separate avoids messy conditionals.
