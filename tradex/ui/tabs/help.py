"""Help Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st

from tradex.ui.evidence import render_evidence_notice


def render_help_tab() -> None:
    """Render the TradeX Help & Documentation tab."""
    st.subheader("TradeX — Help & Documentation")
    render_evidence_notice("help", st_module=st)
    st.caption("Canonical guidance and evidence disclosures for all TradeX features and settings.")

    st.markdown("---")

    # ── Quick start ───────────────────────────────────────────────────────────
    st.markdown("## Getting Started")
    st.markdown("""
**Recommended initial workflow:**

1. **Scanner tab** → Run Scan to evaluate additive technical indicators across your watchlist.
2. **Confluence tab** → Run Confluence Scan to inspect multi-timeframe score alignment.
3. **Start the watcher** in a terminal so scan telemetry accumulates over time:
   ```bash
   cd /Users/gary.yang/tradex
   .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
   ```
4. After several scan sessions → **Coil Detector** becomes useful as historical persistence data builds.
5. After signals resolve → **Signal Journal** displays descriptive outcome telemetry across historical signals.
    """)

    st.markdown("---")

    # ── Global settings ───────────────────────────────────────────────────────
    st.markdown("## Global Settings (Sidebar)")

    with st.expander("Timeframe", expanded=False):
        st.markdown("""
Controls which time window the Scanner and Coil Detector operate on.

| Option | Bars | Window | Focus |
|---|---|---|---|
| **Intraday** | 5-minute | Last 5 trading days | Intraday momentum and shorter-term price action |
| **Short** | Daily | Last 60 trading days | Daily swing structure and intermediate technical conditions |
| **Long** | Weekly | Last 2 years | Multi-week to multi-month trend context |

**Usage:** Select `intraday` for short-horizon monitoring, `short` for daily swing evaluation, or `long` for broader macro trend context.
        """)

    with st.expander("Min Score (0–100)", expanded=False):
        st.markdown("""
Filters out stocks below this additive signal score. Each stock is scored 0–100 based on how many
simultaneous technical conditions are met.

| Range | Meaning | Use when |
|---|---|---|
| 0–39 | Few conditions met | Broad exploration / baseline monitoring |
| 40–59 | Moderate condition alignment | Casting a wider net across discovery heuristics |
| 60–79 | Multiple conditions met | Balanced default for candidate discovery |
| 80–100 | Most conditions met simultaneously | Narrow filtering across simultaneous conditions |

**Evidence note:** Technical scores are unvalidated discovery heuristics. A higher score reflects more
simultaneous indicator conditions, not trade probability, conviction, or executable edge.
        """)

    with st.expander("Watchlist", expanded=False):
        st.markdown("""
The default watchlist covers 20 actively traded stocks and ETFs across mega-cap tech,
high-growth names, and leveraged ETFs.

**Default tickers:** AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, PLTR, MSTR,
SPY, QQQ, SOXL, TQQQ, SMCI, ARM, AVGO, MU, CRWD, NET

**Adding tickers:** Type comma-separated symbols in the "Add tickers" box (e.g. `COIN, HOOD, RKLB`).
They will be appended to the watchlist for the current session.

**Tip:** Fewer tickers result in faster scans. When scanning frequently on intraday intervals,
keeping the watchlist under 30 avoids rate limits.
        """)

    st.markdown("---")

    # ── Scanner ───────────────────────────────────────────────────────────────
    st.markdown("## Scanner")

    with st.expander("What the Scanner does", expanded=False):
        st.markdown("""
The Scanner fetches market data for every ticker in your watchlist and computes an additive
technical score (0–100) based on how many conditions are met simultaneously.

**Signals checked per timeframe:**

| Signal | What it checks | Max Points |
|---|---|---|
| **Volume surge** | Current volume vs. 20-bar average (>2x indicates elevated turnover) | Up to 30 pts |
| **RSI momentum** | RSI between 55–75 (upward momentum zone) | Up to 20 pts |
| **MACD crossover** | MACD line crossing above signal line (momentum shift) | Up to 30 pts |
| **EMA structure** | Price above EMA20 which is above EMA50 (uptrend structure) | Up to 25 pts |
| **BB expansion** | Bollinger Bands tightening then expanding (volatility expansion) | Up to 20 pts |
| **EMA pullback** | Price dipping back to EMA20 in an uptrend (moving average test) | Up to 15 pts |

**Results columns:**
- **Score** — 0–100 additive technical score
- **Vol Ratio** — volume relative to 20-bar average (2.0 = twice normal)
- **RSI** — Relative Strength Index (30 = oversold, 50 = neutral, 70 = overbought)
- **Reasons** — descriptive summary of the conditions that triggered points

**Chart indicators:**
- 🟠 **EMA20** — 20-period exponential moving average (short-term trend)
- 🔵 **EMA50** — 50-period EMA (medium-term trend)
- **Shaded band** — Bollinger Bands (±2 std dev)
- **Volume bars** — green when close > open, red when close < open (white line = 20-bar average)

**Evidence classification:** Legacy heuristic — discovery only. Scores do not guarantee trade quality or executable edge.
        """)

    st.markdown("---")

    # ── Coil Detector ─────────────────────────────────────────────────────────
    st.markdown("## Coil Detector")

    with st.expander("What a coil is and how to use it", expanded=False):
        st.markdown("""
The Coil Detector identifies stocks that have appeared across multiple scan sessions over several days
while maintaining score stability without a large price breakout (≥3%).

**How it is detected:**
1. Scan results are recorded to the local SQLite database on each run.
2. The Coil Detector evaluates scan records within the look-back window.
3. It checks: Has the stock appeared in at least N sessions? Is the score at or above threshold? Has price moved <3%?
4. Stocks meeting these criteria are surfaced with their persistence duration and trend slope.

**Controls:**

| Control | What it does |
|---|---|
| **Look-back window** | Number of calendar days of scan history to search (default: 7 days). |
| **Min appearances** | Minimum number of distinct scan sessions required (default: 2). |

**Score trend directions:**
- 🟢 **Building** — technical score has risen across recorded scans.
- 🟡 **Stable** — holding steady at or above threshold.
- 🔴 **Fading** — technical score declining relative to prior scans.

**Evidence classification:** Exploratory context. Coil metrics summarize historical persistence but do not predict upcoming breakouts or guarantee executable trading edge.
        """)

    st.markdown("---")

    # ── Confluence ────────────────────────────────────────────────────────────
    st.markdown("## Confluence Scanner")

    with st.expander("Multi-timeframe alignment explained", expanded=False):
        st.markdown("""
The Confluence Scanner scores each stock across intraday, short-term, and long-term timeframes simultaneously
and combines them into a weighted score with a fixed denominator.

**Weighting (missing timeframes contribute 0):**
| Timeframe | Weight | Description |
|---|---|---|
| Intraday (5m) | 30% | Shorter-term technical momentum |
| Short-term (1d) | 40% | Daily timeframe swing structure |
| Long-term (1wk) | 30% | Weekly broader trend structure |

**Confluence tiers:**
| Score | Tier | Meaning |
|---|---|---|
| 90–100 (3/3 active) | All timeframes aligned | High scores across all three timeframes |
| 70–89 (≥2 active) | Strong confluence | Strong score alignment across at least two timeframes |
| 50–69 (≥2 active) | Moderate confluence | Partial score alignment across at least two timeframes |
| < 50 or <2 active | Weak | Single timeframe only or low score alignment |

**Evidence classification:** Exploratory context. Multi-timeframe alignment describes score agreement across heuristic models but does not prove trade conviction, probability, or expected return.
        """)

    st.markdown("---")

    # ── Pattern Match ─────────────────────────────────────────────────────────
    st.markdown("## Pattern Match")

    with st.expander("Fingerprinting and similarity scoring explained", expanded=False):
        st.markdown("""
Pattern Match compares a stock's current 10-day price, volume, and indicator shape against an averaged
historical profile leading up to large historical moves (run-ups or declines).

**Mechanism:**
- Mines 3 years of history for large price moves (+15% run-up or -12% decline in 5 days).
- Averages normalized pre-event windows into a composite fingerprint.
- Compares current watchlist tickers to the fingerprint using Pearson correlation across 5 series.

**Research status — Rejected on Holdout:**
Under PATTERN-001, pattern similarity was evaluated across split datasets and formally rejected on holdout data.
It has not demonstrated predictive value and is retained for experimental research only.
It is strictly excluded from production scoring, ranking, candidate eligibility, and automatic alerts.
        """)

    st.markdown("---")

    # ── Pre-Market ────────────────────────────────────────────────────────────
    st.markdown("## Pre-Market Gap Scanner")

    with st.expander("Gaps explained", expanded=False):
        st.markdown("""
A gap is the percentage difference between a stock's pre-market price and its previous regular-session close,
reflecting overnight price adjustments before the regular market opens.

**Best time to use:** 7:00am – 9:25am ET, before regular trading hours.

**Gap tiers:**
| Tier | Size | Description |
|---|---|---|
| 🔴 Massive | ≥ 8% | Major overnight price displacement |
| 🟠 Large | 4–8% | Significant overnight move |
| 🟡 Moderate | 2–4% | Moderate pre-market change |

**Context fields:**
- **Pre-Market Volume & Dollar Volume** — trading activity during the pre-market session.
- **Spread (bps)** — bid/ask spread shown when real quotes are available.
- **Catalyst Context** — earnings and headline summaries for informational reference (no causality claims).

**Evidence classification:** Exploratory event context — non-actionable by itself. Gaps describe overnight price changes and do not independently constitute trade recommendations.
        """)

    st.markdown("---")

    # ── Options Flow ──────────────────────────────────────────────────────────
    st.markdown("## Options Flow")

    with st.expander("Options basics and how to read flow", expanded=False):
        st.markdown("""
Options activity surfaces derivatives turnover and positioning context.

**Data sources:**
- **Unusual Whales** — transaction-level flow events (sweeps, block trades, reported side) when `UNUSUAL_WHALES_API_KEY` is configured.
- **Tradier** — options-chain snapshots when `TRADIER_API_KEY` is configured.
- **Yahoo** — delayed options-chain snapshots (no credentials required).

**True flow vs. chain snapshots:**
- Chain snapshots report aggregate volume and open interest. They do not report transaction side, sweeps, or execution intent.
- True flow requires a dedicated flow provider.

**Call/Put volume balance:**
Aggregate call and put volume is a non-directional summary of activity. A high call/put volume ratio indicates that more call contracts traded than puts, but does not identify whether contracts were bought or sold, opening or closing.

**Evidence classification:** Exploratory context. There is no approved executable TradeX strategy using options activity.
        """)

    st.markdown("---")

    # ── Alerts ────────────────────────────────────────────────────────────────
    st.markdown("## Alerts")

    with st.expander("Setting up Discord and email alerts", expanded=False):
        st.markdown("""
Alerts provide delivery infrastructure when the background watcher is running and configured thresholds are met.

**Discord setup:**
1. Create a Discord application and bot at [discord.com/developers/applications](https://discord.com/developers/applications).
2. Configure permissions (`Send Messages`, `Embed Links`) and invite the bot to your server.
3. Set environment variables in `.env`:
   ```bash
   ALERT_DISCORD_TOKEN=your-token-here
   ALERT_DISCORD_CHANNEL_ID=your-channel-id-here
   ```

**Email setup:**
Set SMTP parameters in `.env`:
```bash
ALERT_EMAIL_TO=you@example.com
ALERT_EMAIL_FROM=your-email@example.com
ALERT_EMAIL_HOST=smtp.example.com
ALERT_EMAIL_PORT=587
ALERT_EMAIL_USER=your-email@example.com
ALERT_EMAIL_PASS=your-password
```

**Trigger criteria:**
- Automatic alerts trigger on legacy heuristic scores and exploratory thresholds (coil strength, confluence, gap size).
- Pattern similarity is quarantined and does not trigger automatic alerts.

**Evidence classification:** Delivery infrastructure. Current automatic alerts are based on unvalidated legacy/exploratory outputs, not production-approved actionable strategies.
        """)

    st.markdown("---")

    # ── Signal Journal ────────────────────────────────────────────────────────
    st.markdown("## Signal Journal")

    with st.expander("Understanding your signal history and outcomes", expanded=False):
        st.markdown("""
The Signal Journal tracks price outcomes at generic horizons following recorded scan signals.

**Outcome windows:**
| Timeframe | Outcome window |
|---|---|
| Intraday | Price 1 trading day after signal |
| Short | Price 3 trading days after signal |
| Long | Price 5 trading days after signal |

**Telemetry metrics:**
- **Win Rate** — % of recorded signals where the stock price increased at the outcome horizon.
- **Avg Win / Avg Loss** — average % return on positive and negative outcomes.
- **Legacy Expectancy Metric** — arithmetic calculation: `(win rate × avg win) + (loss rate × avg loss)`. This metric describes average fixed-horizon price change across legacy signals. It does not reflect executable trading performance because it does not model trade entry execution, stops, profit targets, expirations, invalidations, slippage, or transaction fees.

**Evidence classification:** Legacy signal telemetry. Descriptive telemetry over generic horizons cannot establish mathematical edge or executable strategy performance.
        """)

    st.markdown("---")

    # ── Indicators glossary ───────────────────────────────────────────────────
    st.markdown("## Indicator Glossary")

    with st.expander("RSI — Relative Strength Index", expanded=False):
        st.markdown("""
Measures price momentum by comparing the magnitude of recent gains vs. recent losses over 14 periods.

| Value | Interpretation |
|---|---|
| < 30 | Oversold zone |
| 30–50 | Below neutral momentum |
| 50–70 | Bullish momentum zone |
| > 70 | Overbought zone |

TradeX heuristic awards points when RSI is in the 55–75 zone.
        """)

    with st.expander("MACD — Moving Average Convergence Divergence", expanded=False):
        st.markdown("""
Compares 12-period and 26-period exponential moving averages relative to a 9-period signal line.

**Key conditions:**
- **MACD line crosses above signal line** — bullish crossover.
- **MACD histogram positive and expanding** — upward momentum acceleration.
        """)

    with st.expander("EMA — Exponential Moving Average", expanded=False):
        st.markdown("""
A moving average that gives greater weight to recent price observations.

TradeX evaluates two EMAs:
- **EMA20** — 20-period exponential moving average (short-term trend).
- **EMA50** — 50-period exponential moving average (medium-term trend).

**Key structure:** Price > EMA20 > EMA50 reflects standard uptrend alignment.
        """)

    with st.expander("Bollinger Bands", expanded=False):
        st.markdown("""
Bands placed ±2 standard deviations around a 20-period moving average that expand and contract with volatility.

**Key conditions:**
- **Band compression (squeeze)** — low volatility period.
- **Band expansion** — volatility expansion following a squeeze.
        """)

    with st.expander("Volume Ratio", expanded=False):
        st.markdown("""
Volume ratio = bar volume ÷ 20-period average volume.

| Ratio | Description |
|---|---|
| < 0.5 | Below average volume |
| 0.5–1.5 | Typical volume range |
| 1.5–2.0 | Elevated volume |
| > 2.0 | High volume turnover (>2x average) |
        """)

    with st.expander("ATR — Average True Range", expanded=False):
        st.markdown("""
Measures average price volatility over 14 periods in dollar terms.
Used internally to normalize volatility across instruments.
        """)

    st.markdown("---")
    st.markdown("## Running the Background Watcher")
    st.code("""# Run in a terminal during market hours (9:30am–4pm ET)
cd /Users/gary.yang/tradex
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5

# Options:
# --timeframe   intraday | short | long
# --interval    poll interval in minutes (0 = run once and exit)
# --min-score   minimum score to record (default: 35)
# --provider    yahoo | alpaca | ibkr | schwab (default: yahoo)""", language="bash")

    st.markdown("""
The background watcher:
- Runs the Scanner every N minutes and logs results to `~/.tradex/signals.db`.
- Builds historical scan persistence for the Coil Detector.
- Evaluates alert thresholds and dispatches configured notifications.
- Executes pre-market gap scans at 8:00am ET and outcome resolution passes at 4:30pm ET.
    """)
