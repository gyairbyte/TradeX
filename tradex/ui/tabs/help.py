"""Help Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st


def render_help_tab() -> None:
        """Render the TradeX Help & Documentation tab."""
        st.subheader("TradeX — Help & Documentation")
        st.caption("Everything you need to understand what each feature does, how to tune it, and how to get started.")
    
        st.markdown("---")
    
        # ── Quick start ───────────────────────────────────────────────────────────
        st.markdown("## Getting Started")
        st.markdown("""
    **Recommended first session:**
    
    1. **Scanner tab** → Run Scan. See which stocks are signaling right now.
    2. **Confluence tab** → Run Confluence Scan. Find stocks where multiple timeframes agree.
    3. **Pattern Match tab** → Build Fingerprints (standard profile, ~2 min) → Run Pattern Screen.
    4. **Start the watcher** in a terminal so signal history starts building:
       ```bash
       cd /Users/gary.yang/tradex
       .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
       ```
    5. After a few days → **Coil Detector** becomes useful as history accumulates.
    6. After signals resolve → **Signal Journal** shows your win rate and lets you calibrate.
        """)
    
        st.markdown("---")
    
        # ── Global settings ───────────────────────────────────────────────────────
        st.markdown("## Global Settings (Sidebar)")
    
        with st.expander("Timeframe", expanded=False):
            st.markdown("""
    Controls which time window the Scanner and Coil Detector use.
    
    | Option | Bars | Window | Best for |
    |---|---|---|---|
    | **Intraday** | 5-minute | Last 5 trading days | Same-day swings, momentum plays |
    | **Short** | Daily | Last 60 trading days | Multi-day to multi-week swing trades |
    | **Long** | Weekly | Last 2 years | Position trades, trend following |
    
    **Tuning:** Start with `intraday` for active trading. Switch to `short` for swing trades
    you plan to hold 3–10 days. Use `long` to filter out stocks that are in long-term downtrends.
            """)
    
        with st.expander("Min Score (0–100)", expanded=False):
            st.markdown("""
    Filters out stocks below this signal strength. Each stock is scored by how many technical
    conditions are simultaneously met — more conditions = higher score.
    
    | Range | Meaning | Use when |
    |---|---|---|
    | 0–39 | No clear setup | Research / exploration only |
    | 40–59 | Weak to moderate signal | Casting a wide net |
    | 60–79 | Strong signal | Good default for active scanning |
    | 80–100 | Multiple conditions aligned | Highest conviction — fewer but better setups |
    
    **Tuning:** Start at 40. After you've built Signal Journal history, look at the
    "Signal Quality by Score Bucket" chart to see what threshold actually produces moves for you.
    Lower = more noise. Higher = fewer opportunities but higher win rate.
            """)
    
        with st.expander("Watchlist", expanded=False):
            st.markdown("""
    The default watchlist covers 20 actively traded stocks and ETFs across mega-cap tech,
    high-growth names, and leveraged ETFs.
    
    **Default tickers:** AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, PLTR, MSTR,
    SPY, QQQ, SOXL, TQQQ, SMCI, ARM, AVGO, MU, CRWD, NET
    
    **Adding tickers:** Type comma-separated symbols in the "Add tickers" box (e.g. `COIN, HOOD, RKLB`).
    They'll be appended to the watchlist for this session.
    
    **Tip:** Fewer tickers = faster scans. If you're running the intraday scanner every 5 minutes,
    keep the watchlist under 30 to avoid rate limiting from Yahoo Finance.
            """)
    
        st.markdown("---")
    
        # ── Scanner ───────────────────────────────────────────────────────────────
        st.markdown("## Scanner")
    
        with st.expander("What the Scanner does", expanded=False):
            st.markdown("""
    The Scanner fetches live price data for every ticker in your watchlist and scores each one
    0–100 based on how many technical conditions are met simultaneously.
    
    **Signals checked per timeframe:**
    
    | Signal | What it detects | Weight |
    |---|---|---|
    | **Volume surge** | Current volume > 2x the 20-bar average. Indicates unusual interest — often institutional. | Up to 30 pts |
    | **RSI momentum** | RSI between 55–75 (bullish momentum without being overbought). | Up to 20 pts |
    | **MACD crossover** | MACD line crossing above signal line. Trend direction shifting bullish. | Up to 30 pts |
    | **EMA structure** | Price above EMA20, which is above EMA50. Classic uptrend structure. | Up to 25 pts |
    | **BB expansion** | Bollinger Bands tightening then expanding. Volatility building for a breakout. | Up to 20 pts |
    | **EMA pullback** | Price dipping back to EMA20 in an uptrend. Potential buy-the-dip entry. | Up to 15 pts |
    
    **Results columns:**
    - **Score** — 0–100 signal strength
    - **Vol Ratio** — how unusual today's volume is vs. the 20-bar average (2.0 = twice normal)
    - **RSI** — momentum indicator. 30=oversold, 50=neutral, 70=overbought
    - **Reasons** — plain-English explanation of exactly why this stock scored what it did
    
    **Chart indicators:**
    - 🟠 **EMA20** — 20-period exponential moving average. Short-term trend.
    - 🔵 **EMA50** — 50-period EMA. Medium-term trend.
    - **Shaded band** — Bollinger Bands (±2 std dev). Wide = high volatility, narrow = compression.
    - **Volume bars** — green when close > open, red when close < open. White line = 20-bar average.
            """)
    
        st.markdown("---")
    
        # ── Coil Detector ─────────────────────────────────────────────────────────
        st.markdown("## Coil Detector")
    
        with st.expander("What a coil is and how to use it", expanded=False):
            st.markdown("""
    A **coil** is a stock that has been quietly building technical pressure across multiple scan
    sessions without yet making a large price move. The idea is to identify stocks *before* the
    obvious move — not after.
    
    **How it's detected:**
    1. Every scan result is saved to a local database
    2. The Coil Detector looks back over N days and finds stocks that appeared in multiple sessions
    3. It checks: is the score still high? Has the price not already broken out (>3% move)?
    4. If yes — it's a coil candidate. The longer and stronger the coil, the higher the Coil Strength.
    
    **Controls:**
    
    | Control | What it does |
    |---|---|
    | **Look-back window** | How many days of history to search. 7 days = one trading week. |
    | **Min appearances** | How many scan sessions the stock must have appeared in. More = longer coil. |
    
    **Tuning look-back:**
    - **3–5 days** — only catches recent, fast-building setups
    - **7 days (default)** — one week, best balance
    - **14–21 days** — longer accumulation patterns, more reliable but slower to develop
    
    **Tuning min appearances:**
    - **2 (default)** — appeared at least twice. Catches early coils.
    - **3–5** — appeared repeatedly. More reliable.
    - **6–10** — very persistent. Usually means the stock is about to resolve soon.
    
    **Score History chart:** shows how the signal score evolved across scan sessions.
    A rising score line = the setup is getting stronger. A flat line = holding steady.
    A falling line = watch out, the setup may be fading.
    
    **Status labels:**
    - 🟢 **Coiling — building pressure** — score rising, no breakout yet. Best setups.
    - 🟡 **Coiling — stable** — holding at signal level, not accelerating yet.
    - 🔴 **Fading** — score declining. Setup may be breaking down.
    - ⚪ **Watching** — appeared but hasn't met full coil criteria yet.
            """)
    
        st.markdown("---")
    
        # ── Confluence ────────────────────────────────────────────────────────────
        st.markdown("## Confluence Scanner")
    
        with st.expander("Multi-timeframe alignment explained", expanded=False):
            st.markdown("""
    The Confluence Scanner scores each stock across all three timeframes simultaneously and
    combines them into a single weighted score.
    
    **Why it matters:** A stock can look great on a 5-minute chart but be in a daily downtrend.
    Trading against the larger trend is fighting an uphill battle. When intraday, short-term, and
    long-term all point the same direction — that's a genuinely high-conviction setup.
    
    **Weighting:**
    | Timeframe | Weight | Reasoning |
    |---|---|---|
    | Intraday (5m) | 30% | Noisiest signal — good confirmation, not the driver |
    | Short (1d) | 40% | Most actionable for swing trades |
    | Long (1wk) | 30% | Establishes macro trend direction |
    
    **Confluence score tiers:**
    | Score | Tier | Meaning |
    |---|---|---|
    | 90–100 | All timeframes aligned | Rare. Very high conviction. |
    | 70–89 | Strong confluence | Two or more timeframes strongly aligned. |
    | 50–69 | Moderate confluence | Partial alignment. Use additional confirmation. |
    | < 50 | Weak | Single timeframe only. Lower conviction. |
    
    **Min confluence slider:** raise it to see only the strongest setups. Lower it if nothing
    appears (may be a weak market environment where setups are rarer).
    
    **Bar chart (drill-down):** shows the individual score per timeframe so you can see exactly
    which timeframes are contributing to the confluence score.
            """)
    
        st.markdown("---")
    
        # ── Pattern Match ─────────────────────────────────────────────────────────
        st.markdown("## Pattern Match")
    
        with st.expander("Fingerprinting and similarity scoring explained", expanded=False):
            st.markdown("""
    Pattern Match mines 3 years of historical data to find what stocks looked like in the days
    *before* a major move — then compares your current watchlist against that historical shape.
    
    **Step 1 — Build Fingerprints (one-time setup, ~2 min):**
    - Scans 40+ stocks over 3 years
    - Finds every event where a stock moved ≥15% in 5 days (run-up) or ≥12% down (decline)
    - Extracts the 10 trading days *before* each event
    - Normalizes everything (so NVDA at $800 and AMD at $100 are comparable — uses % changes and ratios)
    - Averages all pre-event windows into a "fingerprint" with a mean and ±1 std deviation band
    - Saves to a local database — doesn't recompute unless you click Build again
    
    **Step 2 — Run Pattern Screen:**
    - Extracts the last 10 trading days for each stock in your watchlist
    - Compares it to the fingerprint using Pearson correlation across 5 series
    - Returns a similarity score 0–100
    
    **Series weights:**
    | Series | Weight |
    |---|---|
    | Price % change shape | 35% |
    | Volume ratio shape | 30% |
    | RSI trajectory | 15% |
    | MACD diff trajectory | 10% |
    | Bollinger Band width | 10% |
    
    **Profiles:**
    | Profile | Run-up threshold | Best for |
    |---|---|---|
    | Conservative | +20% / -16% | AAPL, MSFT, GOOGL, SPY |
    | Standard | +15% / -12% | Most mid/large cap stocks |
    | Volatile | +30% / -25% | SOXL, TQQQ, MSTR, NVDA, TSLA |
    
    **Similarity score guide:**
    | Score | Meaning |
    |---|---|
    | 90–100% | Near-perfect match — very strong setup |
    | 75–89% | Strong match — alert threshold |
    | 60–74% | Moderate — watch but don't act alone |
    | < 60% | Low similarity / noise |
    
    **Overlay chart:** white line = your stock now. Orange dashed = historical average.
    Shaded band = the range most historical events fell within (±1 std dev).
    The closer your stock tracks the orange line, the higher the similarity.
            """)
    
        st.markdown("---")
    
        # ── Pre-Market ────────────────────────────────────────────────────────────
        st.markdown("## Pre-Market Gap Scanner")
    
        with st.expander("Gaps explained", expanded=False):
            st.markdown("""
    A gap occurs when a stock's pre-market price is significantly different from the previous
    regular-session closing price. Gaps happen because news, earnings, or macro events move
    the price while the market is closed.
    
    **Best time to use:** 7:00am – 9:25am ET, before market open.
    
    **Min gap % slider:**
    - **1–2%** — catches all notable pre-market moves. Many results, some noise.
    - **4%** — meaningful gaps with real catalysts. Used for automatic alerts.
    - **8%+** — major events only (earnings, M&A).
    
    **Gap tiers:**
    | Tier | Size | Typical cause |
    |---|---|---|
    | 🔴 Massive | ≥ 8% | Earnings surprise, M&A, FDA event |
    | 🟠 Large | 4–8% | Analyst action, sector news |
    | 🟡 Moderate | 2–4% | General pre-market sentiment |
    
    **How to trade gaps:**
    - **Continuation** — stock gaps up on volume and keeps going. Common after strong earnings.
    - **Gap fill** — stock gaps up then reverses back to the prior close before resuming. Watch for this.
    - **Cross-check with Scanner** — a gap-up stock that also has high technical signal score is stronger.
    
    **Data source:** Yahoo Finance (free, ~15min delayed). Add Alpaca or Polygon for real-time.
            """)
    
        st.markdown("---")
    
        # ── Options Flow ──────────────────────────────────────────────────────────
        st.markdown("## Options Flow")
    
        with st.expander("Options basics and how to read flow", expanded=False):
            st.markdown("""
    Options give traders the right (but not obligation) to buy or sell a stock at a set price
    by a set date. They're often used by institutions to make large directional bets.
    
    **Key terms:**
    - **Call** — right to buy. Buying calls = bullish bet.
    - **Put** — right to sell. Buying puts = bearish bet or hedge.
    - **Strike** — the price at which the option can be exercised.
    - **Expiry** — the date the option expires.
    - **Volume** — contracts traded today.
    - **Open Interest (OI)** — total contracts currently outstanding.
    - **Vol/OI ratio** — today's volume ÷ existing open interest. High ratio = unusual activity.
    
    **Min Vol/OI ratio slider:**
    - **1–2x** — slightly elevated, lots of noise
    - **3x (default)** — meaningful. Catches most unusual activity.
    - **10x+** — extremely unusual. Very likely institutional or a sweep.
    
    **Put/Call Ratio:**
    - **< 0.7** — heavy call buying relative to puts → bullish
    - **0.7–1.2** — balanced → neutral
    - **> 1.2** — heavy put buying → bearish or hedging
    
    **Data sources:**
    - **Unusual Whales** ($50/mo) — real-time, sweep detection, best signal quality. Set `UNUSUAL_WHALES_API_KEY` in .env.
    - **Tradier** (free with brokerage account) — real-time chains. Set `TRADIER_API_KEY` in .env.
    - **yfinance** (default, free) — delayed chains, volume/OI ratio analysis only.
            """)
    
        st.markdown("---")
    
        # ── Alerts ────────────────────────────────────────────────────────────────
        st.markdown("## Alerts")
    
        with st.expander("Setting up Discord and email alerts", expanded=False):
            st.markdown("""
    Alerts fire automatically when the background watcher detects a threshold crossing.
    
    **Discord bot setup (one-time):**
    1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
    2. Click **New Application** → give it a name (e.g. "TradeX")
    3. Go to **Bot** tab → **Add Bot** → copy the **Token**
    4. Go to **OAuth2** → **URL Generator** → check `bot` scope → check `Send Messages` + `Embed Links` permissions
    5. Open the generated URL → invite the bot to your Discord server
    6. Right-click the channel you want alerts in → **Copy Channel ID** (requires Developer Mode: Settings → Advanced → Developer Mode)
    7. Add to `.env`:
       ```
       ALERT_DISCORD_TOKEN=your-token-here
       ALERT_DISCORD_CHANNEL_ID=your-channel-id-here
       ```
    
    **Email setup:**
    For Gmail, use an [App Password](https://myaccount.google.com/apppasswords) — not your regular password.
    ```
    ALERT_EMAIL_TO=you@example.com
    ALERT_EMAIL_FROM=your-gmail@gmail.com
    ALERT_EMAIL_HOST=smtp.gmail.com
    ALERT_EMAIL_PORT=587
    ALERT_EMAIL_USER=your-gmail@gmail.com
    ALERT_EMAIL_PASS=your-app-password
    ```
    
    **Threshold tuning:**
    | Setting | Default | Effect of lowering | Effect of raising |
    |---|---|---|---|
    | `ALERT_COIL_THRESHOLD` | 60 | More coil alerts, more noise | Fewer but stronger coil alerts |
    | `ALERT_PATTERN_THRESHOLD` | 75% | More pattern alerts | Only near-perfect pattern matches |
    | `ALERT_CONFLUENCE_THRESHOLD` | 70 | More confluence alerts | Only strong multi-timeframe setups |
            """)
    
        st.markdown("---")
    
        # ── Signal Journal ────────────────────────────────────────────────────────
        st.markdown("## Signal Journal")
    
        with st.expander("Understanding your signal history and outcomes", expanded=False):
            st.markdown("""
    The Signal Journal automatically tracks what happened after every signal fired.
    
    **How outcomes are measured:**
    | Timeframe | Outcome window |
    |---|---|
    | Intraday | Price 1 trading day after signal |
    | Short | Price 3 trading days after signal |
    | Long | Price 5 trading days after signal |
    
    **Key metrics:**
    - **Win Rate** — % of signals where the stock moved up. >50% = positive directional bias.
    - **Avg Win** — average % gain on winning signals.
    - **Avg Loss** — average % loss on losing signals.
    - **Expectancy** — `(win rate × avg win) + (loss rate × avg loss)`. The single most important number.
      Positive expectancy means the strategy has mathematical edge over time, even if individual trades lose.
    
    **Signal Quality by Score Bucket:**
    Shows win rate and avg return broken down by score range (40–59, 60–79, 80–100).
    Use this to find your optimal min score threshold:
    - If 80+ signals have 65% win rate but 40–59 signals have 44%, raise your min score to 80.
    - Don't guess at thresholds — let the data tell you.
    
    **Refresh Outcomes:** manually triggers the outcome fetcher. Also runs automatically
    at 4:30pm ET when the watcher is running.
            """)
    
        st.markdown("---")
    
        # ── Indicators glossary ───────────────────────────────────────────────────
        st.markdown("## Indicator Glossary")
    
        with st.expander("RSI — Relative Strength Index", expanded=False):
            st.markdown("""
    Measures momentum by comparing the magnitude of recent gains vs. recent losses over 14 periods.
    
    | Value | Interpretation |
    |---|---|
    | < 30 | Oversold — potential bounce setup |
    | 30–50 | Weak / recovering |
    | 50–70 | Momentum zone — trending stock |
    | > 70 | Overbought — potential reversal risk |
    
    TradeX uses RSI 55–75 as the bullish momentum zone. Above 75 = overextended, below 55 = not enough momentum.
            """)
    
        with st.expander("MACD — Moving Average Convergence Divergence", expanded=False):
            st.markdown("""
    Compares two exponential moving averages (12-period and 26-period) to detect trend direction and shifts.
    
    **Key signals:**
    - **MACD line crosses above signal line** → bullish crossover. TradeX awards points for this.
    - **MACD positive and expanding** → established uptrend with momentum.
    - **MACD negative and falling** → downtrend in progress.
    
    **MACD diff** (histogram) = MACD minus signal line. Positive and growing = accelerating uptrend.
            """)
    
        with st.expander("EMA — Exponential Moving Average", expanded=False):
            st.markdown("""
    A moving average that gives more weight to recent prices, making it more responsive than a simple average.
    
    TradeX uses two EMAs:
    - **EMA20** (orange) — short-term trend. If price is above this, the short-term trend is up.
    - **EMA50** (blue) — medium-term trend. The "bigger" trend.
    
    **Key patterns:**
    - **Price > EMA20 > EMA50** → classic uptrend structure. TradeX awards points for this.
    - **Pullback to EMA20 in uptrend** → price dips back to the 20 but holds. Entry opportunity.
    - **EMA20 crosses below EMA50** → "death cross" — bearish trend change.
            """)
    
        with st.expander("Bollinger Bands", expanded=False):
            st.markdown("""
    Bands placed ±2 standard deviations around a 20-period moving average. They expand and contract
    with volatility.
    
    **Key patterns:**
    - **Narrow bands (squeeze)** — volatility is low. The stock is coiling. A big move is often coming.
    - **Band expansion after squeeze** — volatility returning. Breakout underway. TradeX detects this.
    - **Price at upper band** — either strong momentum or overextended.
    - **Price at lower band** — either bearish or oversold bounce setup.
    
    TradeX uses **BB Width** (band width as % of the middle band) to detect squeezes and expansions.
            """)
    
        with st.expander("Volume Ratio", expanded=False):
            st.markdown("""
    Volume ratio = today's volume ÷ the 20-period average volume.
    
    | Ratio | Interpretation |
    |---|---|
    | < 0.5 | Very light volume — low conviction in price movement |
    | 0.5–1.0 | Below average — quiet day |
    | 1.0–1.5 | Normal |
    | 1.5–2.0 | Elevated — increased interest |
    | 2.0–3.0 | High volume — likely institutional activity |
    | > 3.0 | Unusually high — major event, earnings, or news |
    
    High volume on an up day = institutional buying. High volume on a down day = institutional selling.
    Volume confirms price moves — a breakout on low volume is suspect. On high volume, it's real.
            """)
    
        with st.expander("ATR — Average True Range", expanded=False):
            st.markdown("""
    Measures average daily volatility in price terms over 14 periods. Unlike % moves, ATR is in dollars.
    
    **How TradeX uses it:**
    - Used internally in the pattern fingerprinter to normalize volatility across different stocks.
    - Not displayed directly in the scanner results.
    
    **Practical use:** A stock with ATR of $5 moves $5/day on average. If you're setting a stop loss,
    placing it 1–2 ATR below your entry gives the stock room to breathe without triggering prematurely.
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
    The watcher:
    - Runs the Scanner every N minutes
    - Saves results to `~/.tradex/signals.db` (builds Coil Detector history)
    - Checks alert thresholds and fires Discord/email alerts on every scan cycle
    - Runs a gap scan automatically at 8am ET
    - Runs the outcome pass automatically at 4:30pm ET
        """)
