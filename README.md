# TradeX — Stock Market Opportunity Scanner

TradeX identifies trading opportunities across three timeframes: **intraday**, **short-term (days/weeks)**, and **long-term (weeks/months)**. It is especially tuned to detect intraday setups preceded by multi-day volume and volatility accumulation ("coiling" patterns that resolve into big intraday swings).

---

## Project Structure

```
tradex/
├── tradex/
│   ├── data/
│   │   └── fetcher.py          # Multi-provider OHLCV fetcher (Yahoo, Alpaca, IBKR, Schwab)
│   ├── signals/
│   │   ├── indicators.py       # Computes RSI, MACD, EMA, Bollinger Bands, ATR, volume ratios
│   │   ├── intraday.py         # Intraday swing signal scorer (5m bars, 5-day window)
│   │   ├── short_term.py       # Short-term momentum scorer (daily bars, 60-day window)
│   │   └── long_term.py        # Long-term trend scorer (weekly bars, 2-year window)
│   ├── screener/
│   │   └── engine.py           # Runs all scorers across a watchlist, returns ranked DataFrame
│   └── ui/
│       └── dashboard.py        # Streamlit dashboard with candlestick charts and drill-down
├── pyproject.toml              # Dependencies and project metadata
├── .env.example                # API keys and provider config (Yahoo/Alpaca/IBKR/Schwab)
├── README.md                   # This file
└── CLAUDE.md                   # AI assistant context and build guidance
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
1. **Volume is accumulating** (multi-day volume above average) — indicates institutional interest building
2. **Bollinger Bands are squeezing then expanding** — volatility contracting before a breakout
3. **MACD crosses bullish** on the 5-minute chart
4. **RSI is in momentum zone** (55–75) without being overextended

These conditions together suggest a stock that has been "coiling" and is ready for a significant intraday swing.

---

## Quickstart

```bash
# Install base dependencies (requires Python 3.11+)
pip install uv
uv pip install -e .

# Install optional provider extras (pick what you need)
uv pip install -e ".[alpaca]"   # Alpaca real-time
uv pip install -e ".[ibkr]"     # Interactive Brokers
uv pip install -e ".[schwab]"   # Charles Schwab
uv pip install -e ".[all]"      # All providers

# Copy and fill in your credentials
cp .env.example .env

# Launch the dashboard
streamlit run tradex/ui/dashboard.py

# Or run the screener from Python
from tradex.screener.engine import run
results = run(["AAPL", "NVDA", "TSLA"], timeframe="intraday", min_score=40)
print(results)
```

## Data Providers

Set `DATA_PROVIDER` in your `.env` to switch sources:

| Provider | `DATA_PROVIDER` value | Cost | Real-time | Setup |
|---|---|---|---|---|
| Yahoo Finance | `yahoo` (default) | Free | No (15-min delay) | None |
| Alpaca | `alpaca` | Free tier | Yes (IEX feed) | API key at alpaca.markets |
| Interactive Brokers | `ibkr` | Free (need IB account) | Yes | TWS/Gateway running locally |
| Charles Schwab | `schwab` | Free (need Schwab account) | Yes | OAuth app at developer.schwab.com |

> **Note:** TD Ameritrade's API was shut down in September 2024. Use `schwab` instead.

---

## Signal State Tracking

The tracker module is what separates TradeX from standard screeners. Rather than showing you a snapshot, it builds a history of every signal fired and detects patterns across time.

### How it works
1. Run the **Scanner** tab (or `watcher.py` on a schedule) — each result is saved to a local SQLite database at `~/.tradex/signals.db`
2. As history accumulates, the **Coil Detector** tab surfaces stocks that have been scoring well for multiple days *without breaking out yet* — these are pre-signal candidates
3. The **Confluence** tab shows stocks scoring well across all three timeframes simultaneously
4. The **Signal Journal** tracks what happened after each signal fired

### Coil detection logic
A "coil" is a stock that:
- Has appeared in scans at least N times over the look-back window
- Has a current score above threshold (default: 45)
- Has NOT already made a large price move (not already broken out)
- Has a score that is stable or trending upward

### Running the watcher
```bash
# Run once
python -m tradex.tracker.watcher --timeframe intraday

# Poll every 5 minutes (run during market hours)
python -m tradex.tracker.watcher --timeframe intraday --interval 5
```

---

## Roadmap

- [ ] Alert system (email/Slack webhook when score crosses threshold)
- [ ] Pre-market gap scanner
- [ ] Earnings event filter (avoid/target earnings plays)
- [ ] Backtesting module to validate signal quality historically
- [x] Multi-provider data fetcher (Yahoo, Alpaca, IBKR, Schwab)
- [x] Signal state tracking (SQLite history, coil detection, confluence scoring)
- [x] Automated outcome tracking (1d/3d/5d price fetch, win rate, expectancy by score bucket)
- [x] Signal journal with quality breakdown by score range and timeframe
- [x] Historical pattern fingerprinting (mine run-ups/declines, average pre-event windows, match live stocks)
- [ ] Alert system (Slack/email when pattern match or coil threshold crossed)
- [ ] Pre-market gap scanner
- [ ] Options flow integration
- [ ] Watchlist persistence and custom scoring weights
- [ ] Portfolio-level risk view
