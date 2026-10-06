# DAYTRADE-003A: Re-anchor TradeX Day Trading to the Original Multi-Resolution Thesis

**Task ID:** `DAYTRADE-003A-ORIGINAL-THESIS-REANCHOR-001`
**Title:** Original multi-resolution day-trading thesis gap analysis and implementation roadmap
**Repository:** `gyairbyte/TradeX`
**Classification:** Research / Design-Only (Zero production impact)
**Starting Base Commit SHA:** `58df7d468d7175264758a997a7a9c701c7f8d369`
**Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved
**Production Trading Behavior:** `NO CHANGE`
**Trading Logic Implementation:** `NO`
**Historical Empirical Execution:** `NO`
**Provider / Live Market-Data Acquisition:** `NO`
**Holdout Access:** `NO`

---

## Executive Summary & Product Decision

Gary Yang has explicitly selected **PATH B**:
**Return TradeX DAYTRADE research to the original multi-resolution decision-support thesis rather than continuing to make isolated 1-minute statistical anomalies the primary roadmap.**

The original `DAYTRADE-001A` thesis envisioned a hierarchical, multi-resolution funnel:
```text
Daily / multi-year context
           ↓
   133-tick structure
           ↓
 1-minute setup context
           ↓
   50-tick entry timing
           ↓
Trigger / entry / invalidation / exit
```

Following `DAYTRADE-001A`, TradeX investigated two single-timeframe statistical phenomena:
1. `DAYTRADE-001` (Extreme downside 1-minute reversal on Dow 30 equities);
2. `DAYTRADE-002` (Early-to-late intraday momentum on liquid ETFs across regular trading sessions).

While both programs produced valuable statistical infrastructure, data-quality frameworks, and cost lessons, neither represented Gary's actual multi-resolution discretionary trading workflow. Continuing to pursue isolated 1-minute statistical anomalies would drift TradeX away from its core mission: **empowering Gary with a structured, explainable, testable decision-support system that models his multi-timeframe chart reading process**.

This document establishes the comprehensive gap analysis, data-feasibility requirements, strategy elicitation contract, outcome evaluation architecture, and staged implementation roadmap required to turn the original multi-resolution discretionary workflow into a rigorous TradeX research program.

---

## 1. Verified Original Thesis: Hierarchy & Funnel Roles

The authoritative `DAYTRADE-001A` architecture establishes a strict five-tier hierarchical funnel. Each layer serves a fundamentally distinct purpose:

```text
+-----------------------------------------------------------------------------------+
| 1. Daily / Multi-Year Context (DAILY)                                            |
|    - Macro price trend, key higher-timeframe levels, volatility (ATR), volume    |
|    - Role: OPPORTUNITY DISCOVERY & CANDIDATE FILTERING (Not an entry trigger)     |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 2. 133-Tick Structure (TICK_133)                                                 |
|    - Activity-driven market structure, intraday trend, swing high/low progression |
|    - Role: INTRADAY STRUCTURAL QUALIFICATION (Filters out choppy/counter-trend)   |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 3. 1-Minute Setup Context (MINUTE_1)                                             |
|    - Calendar-time chart pattern (pullback, consolidation flag, VWAP relationship)|
|    - Role: CONCRETE SETUP IDENTIFICATION (Identifies the pattern opportunity)    |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 4. 50-Tick Entry Timing (TICK_50)                                                 |
|    - Ultra-fast micro-structure confirmation (micro-breakout, tick volume spike)  |
|    - Role: HIGH-RESOLUTION TIMING (Refines execution fill and entry trigger)     |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 5. Deterministic Execution Lifecycle                                              |
|    - Entry fill price, initial invalidation stop, profit target, trailing rules,  |
|      maximum holding duration, session-end liquidation, and slippage/fees         |
|    - Role: TRADE LIFECYCLE MANAGEMENT (Completely deterministic execution)        |
+-----------------------------------------------------------------------------------+
```

### Core Design Principle: Signal Discovery vs. Entry Timing

A fundamental lesson of quantitative trading architecture is to **never conflate candidate discovery with entry timing**:
* **Upstream filtering:** Daily context and 133-tick structure identify whether a security is in an eligible regime. If a stock fails daily or 133-tick criteria, it must never enter the intraday funnel.
* **Midstream setup:** 1-minute data identifies the specific opportunity in calendar time.
* **Downstream timing:** 50-tick data provides micro-structure execution precision.

A 50-tick pattern must **never independently trigger a trade** on a stock that failed upstream daily or 133-tick qualification, unless Gary's eventual strategy explicitly permits autonomous scalping. The funnel narrows from broad context down to precise execution.

---

## 2. Verified Existing Foundation: DAYTRADE-001A

Repository inspection confirms that `DAYTRADE-001A` successfully built and committed a clean in-memory multi-resolution foundation:

1. **`Resolution` Enum** ([`tradex/research/daytrade_mvp/models.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/models.py#L11-L18)):
   * Strongly typed enum supporting `DAILY`, `TICK_133`, `MINUTE_1`, and `TICK_50`.
2. **`CompletedBar` Model** ([`tradex/research/daytrade_mvp/models.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/models.py#L20-L51)):
   * Normalized bar model enforcing timezone-aware timestamps, valid OHLC boundaries ($H \ge L$, $O, H, L, C > 0$), positive volume ($V \ge 0$), strongly typed resolution, and optional `bar_start`.
3. **`MultiResolutionSeries` Container** ([`tradex/research/daytrade_mvp/models.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/models.py#L53-L143)):
   * Container managing independent chronological bar sequences across all four resolutions for a given ticker and session.
   * `get_bars(resolution, as_of=...)` enforces point-in-time querying ($bar.timestamp \le as\_of$).
   * `filter_as_of(as_of)` materializes a newly instantiated, completely isolated `MultiResolutionSeries` instance containing strictly bars completed at or before $as\_of$, with zero memory back-references or access paths to future bars.
4. **`DaytradeSetup` Protocol** ([`tradex/research/daytrade_mvp/setup.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/setup.py#L14-L64)):
   * Abstract interface defining `setup_id`, `version`, `required_resolutions`, `is_synthetic`, and `production_promotion_eligible` (defaulting to `False`).
   * Pure `evaluate(series, as_of)` method decoupled from data ingestion.
5. **Deterministic Evaluator `evaluate_setup()`** ([`tradex/research/daytrade_mvp/evaluator.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/evaluator.py#L14-L70)):
   * Enforces fail-closed validation: if any required resolution has zero bars available at $as\_of$, evaluation halts immediately with `SetupEvaluationStatus.INVALID_INPUT`.
   * Returns a neutral `SetupEvaluationResult` containing explicit reasons, evidence dictionaries, and optional `detected_entry`, `detected_stop`, `detected_target`.
6. **Synthetic 4-Resolution Test Harness** ([`tradex/research/daytrade_mvp/synthetic.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tradex/research/daytrade_mvp/synthetic.py#L29-L279)):
   * `SYNTH_DAYTRADE_001`: An architectural smoke setup proving four-tier alignment.
   * `generate_synthetic_multi_res_data()`: Generates deterministic test bars across Daily, 133-tick, 1-minute, and 50-tick resolutions, including future bars past $as\_of$ to verify leakage protection.
   * Validated by 9 passing unit tests in [`tests/research/daytrade_mvp/test_daytrade_mvp.py`](file:///C:/Users/Gary/.gemini/antigravity/worktrees/TradeX/daytrade_original_thesis_reanchor/tests/research/daytrade_mvp/test_daytrade_mvp.py) with zero provider calls and zero network access.

**Conclusion:** The in-memory data structures and PIT isolation logic from `DAYTRADE-001A` are mathematically sound, fully tested, and reusable.

---

## 3. Comprehensive Gap Analysis

Below is the evidence-based gap analysis comparing current TradeX capabilities against the requirements of Gary's multi-resolution day-trading workflow.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TRADEX MULTI-RESOLUTION GAP MATRIX                                  │
├─────────────────────┬───────────────────────────┬──────────────────────────────────────────────────────┤
│ Gap Identifier      │ Capability Area           │ Status in Repository                                 │
├─────────────────────┼───────────────────────────┼──────────────────────────────────────────────────────┤
│ DT3-GAP-DATA-001    │ Raw Trade-Tick Provider   │ NOT SUPPORTED (No trade endpoints in TradeX)         │
│ DT3-GAP-TICK-001    │ Tick Aggregation Engine   │ NOT SUPPORTED (Zero tick-bar grouping logic)         │
│ DT3-GAP-SYNC-001    │ Cross-Resolution PIT Sync │ PARTIALLY SUPPORTED (In-memory ok; lacks sync meta) │
│ DT3-GAP-SETUP-001   │ Concrete Strategy Rules   │ UNRESOLVED (Only synthetic rules; requires Gary)    │
│ DT3-GAP-EVAL-001    │ Full Lifecycle Simulator  │ NOT SUPPORTED (Only fixed-horizon event studies)     │
└─────────────────────┴───────────────────────────┴──────────────────────────────────────────────────────┘
```

---

### A. Opportunity Discovery & Universe Funnel

| Question | Repository Evidence & Architectural Finding |
|---|---|
| **How would a security enter the DAYTRADE funnel?** | Securities enter at the top of the funnel (Layer 1: Daily context). A candidate must meet daily liquidity (ADV > \$10M–\$50M, tight spread), average daily volatility (ATR > \$1.50 or > 1.5%), and structural interest (trend alignment, multi-day coil, or premarket catalyst) before intraday tick data is even processed. |
| **Does existing TradeX candidate discovery provide useful candidates?** | TradeX possesses candidate discovery tools: the Scanner (`tradex/screener/engine.py`), Coil Detector (`tradex/tracker/analyzer.py`), Premarket Gap Scanner (`tradex/premarket/gap_scanner.py`), and Today Candidates (`tradex/journal/`). However, existing scanner scores are uncalibrated heuristics. Premarket gap scanning and multi-day coil detection are conceptually aligned with Gary's workflow, but require formal qualification filters before serving as an automated day-trade funnel. |
| **Can LONG / SHORT / MVP candidate infrastructure be reused?** | **Partially, but with strict architectural separation.** `LONG-002` focuses on multi-day swing holding periods (5, 10, 21 sessions) for +10%/+20%/+30% moves. Direct coupling of DAYTRADE to LONG-002 would conflate multi-day swing mechanics with intraday session scalping/momentum. However, the PIT reference and security master data from `tradex/pit/ops.py` (e.g. market cap, corporate exclusions, shares outstanding) can be directly reused. |
| **What would be inappropriate coupling?** | Hard-coding DAYTRADE entry to depend on the uncalibrated `tradex/signals/intraday.py` 0–100 score, or forcing DAYTRADE to use the 15-ETF universe or Dow 30 universe solely because prior studies used them. |
| **Is a separate intraday opportunity universe needed?** | **YES.** Day trading with tick bars imposes strict liquidity constraints. A stock with low trading frequency (such as TRV or SHW in `DAYTRADE-001C2`) takes several minutes to complete a single 50-tick bar, distorting intraday timing. The DAYTRADE universe must be restricted to highly liquid, high-trade-velocity equities and ETFs. |

---

### B. Daily / Multi-Year Context Capabilities

| Capability | Status | Repository Evidence & Details |
|---|---|---|
| **Daily price history** | **SUPPORTED** | `tradex/data/fetcher.py` and `tradex/data/history.py` provide reliable, date-ranged daily OHLCV across Schwab, Alpaca, Yahoo, and IBKR. |
| **Price trend context** | **SUPPORTED** | `tradex/signals/indicators.py` computes standard moving averages (EMA 20, SMA 50, SMA 200) and MACD. |
| **Daily volume context** | **SUPPORTED** | Rolling 20-day average volume and volume ratios are computed in `tradex/signals/indicators.py` and `tradex/research/long_002d/`. |
| **Volatility context** | **SUPPORTED** | 14-day Average True Range (ATR) and ATR percentage are implemented in `tradex/signals/indicators.py`. |
| **Support / resistance levels** | **NOT SUPPORTED** | TradeX has no automated horizontal support/resistance, swing high/low, or pivot level extractor. |
| **Market / sector context** | **PARTIALLY SUPPORTED** | `SECTOR_ETFS` preset exists, and relative strength was explored in `SHORT-001`, but no normalized daily market-regime context vector is currently linked to setup evaluation. |
| **PIT security reference data** | **SUPPORTED** | `tradex/pit/store.py` (Schema v8) and `tradex/pit/ops.py` provide immutable prospective reference classification (common stock vs ETF vs CEF). |

**Gap Summary for Daily Context:** TradeX has the raw data and basic indicators, but lacks a formal `DailyContextContract` specifying the exact quantitative filters (e.g. $Close > EMA20$, $ATR > \$1.50$, $VolumeRatio > 1.2$) that qualify a security for Gary's day-trading funnel.

---

### C. 133-Tick Bars: Capability Inventory

Below is the definitive capability inventory for 133-tick bars based strictly on repository evidence:

| Capability Dimension | Repository Status | Evidence & Repository Finding |
|---|---|---|
| **Raw trades data model** | **NOT SUPPORTED** | No dataclass or model exists representing an individual trade execution (price, size, exchange, condition codes, timestamp). |
| **Historical trade-tick acquisition** | **NOT SUPPORTED** | Neither `tradex/data/fetcher.py` nor `intraday_dataset/alpaca_client.py` has any endpoint requesting trades (`/v2/stocks/trades`). They exclusively request aggregated bars (`/v2/stocks/bars`). |
| **Streaming trade acquisition** | **NOT SUPPORTED** | Zero websocket connections or real-time trade event streaming logic exist in TradeX. |
| **Native N-tick bars from provider** | **NOT SUPPORTED** | No integrated provider (Alpaca, Schwab, Yahoo, IBKR) provides native pre-aggregated 133-tick bars. |
| **Tick-bar aggregation logic** | **NOT SUPPORTED** | Zero code exists in TradeX to aggregate sequential trades into N-tick OHLCV bars. |
| **Tick-bar storage & layout** | **NOT SUPPORTED** | No database tables, Parquet schemas, or directory layouts exist for storing tick bars. |
| **Tick timestamp semantics** | **NOT SUPPORTED** | No policy exists defining whether bar completion equals final trade time, or how exchange vs receipt timestamps are reconciled. |
| **Trade corrections & cancellations** | **NOT SUPPORTED** | No logic exists to filter out corrected, cancelled, or late Form T trades. |
| **Session boundary filtering** | **NOT SUPPORTED** | Existing session filters (`XNYS` 09:30–16:00 ET) are built exclusively for fixed-time 1-minute bars in `intraday_study/`. |
| **In-memory PIT series container** | **SUPPORTED** | `Resolution.TICK_133` and `MultiResolutionSeries` can store and filter 133-tick `CompletedBar` instances once provided. |
| **External provider capability** | **UNKNOWN** | Whether our existing Alpaca subscription can reliably supply historical trade ticks without rate-limit or volume failures is unverified and requires empirical probing in `DAYTRADE-003B`. |

---

### D. 50-Tick Bars & Shared Tick Stream Architecture

The capability inventory for 50-tick bars is identical to 133-tick bars: in-memory representation is **SUPPORTED** via `Resolution.TICK_50`, but acquisition, aggregation, storage, and filtering are **NOT SUPPORTED**.

#### Architectural Imperative: A Single Underlying Tick Stream

Can and should the same underlying trade stream produce both 133-tick and 50-tick bars?

**YES. They MUST share one underlying tick stream rather than independent derived feeds for three critical architectural reasons:**

1. **Mathematical Determinism & Consistency:**
   If 50-tick bars and 133-tick bars were obtained from separate sources or disparate aggregators, timing and price discrepancies would emerge. A 50-tick bar might show a high that never existed in the corresponding 133-tick window. By constructing both series from the identical sequence of raw trades, cross-resolution price continuity is mathematically guaranteed.
2. **Bandwidth & Acquisition Efficiency:**
   Downloading raw trades once and running two parallel in-memory accumulators (one emitting every 50 trades, one emitting every 133 trades) requires half the bandwidth and storage of maintaining independent derived feeds.
3. **Point-in-Time Synchronization:**
   Using identical underlying trade timestamps ensures that an $as\_of$ decision cutoff at trade timestamp $T$ sees the exact same transaction reality across both resolutions.

---

### E. Tick-Bar Semantics: Policy Decisions Required

Before tick bars can be implemented in code, the following policy decisions must be formally locked:

1. **Trade Qualification ("What counts as one tick?"):**
   * *Option 1:* Every print on the consolidated tape.
   * *Option 2 (Recommended for research):* Every regular-session trade with volume $> 0$, excluding specified out-of-sequence condition codes (e.g. Form T, average price, derivatively priced, late trades).
   * *Odd Lots:* Determine whether odd-lot prints ($< 100$ shares) increment the tick counter. (In modern U.S. markets, odd lots represent $> 60\%$ of trades; excluding them would severely distort tick pacing).
2. **Session Boundary Behavior:**
   * *Policy:* Does the tick accumulator reset fresh to 0 at 09:30:00 ET?
     *Standard decision-support rule:* **YES.** Accumulators must reset at 09:30:00 ET so pre-market or previous-day trades never contaminate the regular session's opening bar.
3. **Incomplete Last Bar at Session Close:**
   * At 16:00:00 ET, an in-flight bar might have accumulated only 28 of 50 trades.
     *Rule:* The partial bar must be discarded or marked `incomplete`; it must never trigger an end-of-day signal as a completed bar.
4. **Timestamp Assignment:**
   * *Bar completion timestamp (`timestamp`):* Timestamp of the final (50th or 133rd) trade.
   * *Bar start timestamp (`bar_start`):* Timestamp of the first trade in the bar.
   * *Clock source:* Participant exchange timestamp (matching engine execution time) is preferred over SIP receipt timestamp.
5. **Premarket / After-Hours Policy:**
   * Strict regular market hours (09:30:00 to 16:00:00 ET) only. Premarket trades are excluded from regular session tick bars.
6. **Stock Splits & Corporate Actions:**
   * Raw trades must be stored unadjusted; split factors are applied deterministically to OHLC prices at bar generation or read time.

---

### F. Cross-Resolution Synchronization & PIT Contract

At decision timestamp $as\_of = T$, the valid point-in-time visibility contract across the four resolutions is:

```text
Decision Point (as_of = T)
══════════════════════════════════════════════════════════════════════════════════════════
Layer 1: DAILY       Completed daily bar from D-1 (yesterday close). Current day D is INCOMPLETE.
Layer 2: TICK_133    Completed 133-tick bars where trade_133_timestamp <= T.
Layer 3: MINUTE_1    Completed 1-minute bars where interval_close <= T (e.g., 09:35:00 at 09:35:30).
Layer 4: TICK_50     Completed 50-tick bars where trade_50_timestamp <= T.
══════════════════════════════════════════════════════════════════════════════════════════
```

#### Synchronization Risks & Safeguards:

1. **Current Incomplete Day Leakage:**
   If a daily bar for the current trading day is queried during the session, it contains end-of-day closing prices that do not yet exist at 10:00 ET.
   *Safeguard:* During session evaluation, the daily layer sees strictly completed historical daily bars through session $D-1$.
2. **In-Flight 1-Minute Bar Leakage:**
   At 09:35:20 ET, the 09:35:00–09:36:00 bar is actively forming.
   *Safeguard:* Only the bar completed at 09:35:00 is visible. The evaluator cannot access the in-flight minute.
3. **Tick Bar Completion Timestamping:**
   A 50-tick bar whose 50th trade arrives at 09:35:02 ET is NOT visible at 09:35:00 ET.
   *Safeguard:* `bar.timestamp` represents the exact timestamp of the 50th trade. `filter_as_of(T)` strictly rejects any bar whose 50th trade occurred at $> T$.
4. **Is `MultiResolutionSeries.filter_as_of()` Sufficient?**
   `filter_as_of()` is sufficient for in-memory timestamp filtering ($bar.timestamp \le T$), provided that:
   * Every bar's `timestamp` reflects its **completion** time, not its opening time;
   * Daily bars are timestamped at session close (e.g. 20:00 UTC / 16:00 ET), preventing morning queries from seeing that day's close.
   However, for real-world execution, explicit `available_at` metadata will be needed to account for network/SIP publication latency.

---

### G. Strategy Elicitation Contract (Gary's Real Setup)

`DAYTRADE-001A` and `daytrade_mvp/synthetic.py` intentionally implemented only a synthetic demonstration setup (`SYNTH-DAYTRADE-001`). To build a credible research implementation of Gary's actual workflow, Gary must define the following concrete strategy parameters:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY ELICITATION CONTRACT FOR GARY                         │
├──────────────────────────┬─────────────────────────────────────────────────────────────┤
│ Dimension                │ Specific Questions Gary Must Define                         │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 1. Context Variables     │ What makes a stock eligible on the Daily chart?             │
│    (Daily / Multi-Year)  │ - Trend: Price above 20 EMA / 50 SMA?                       │
│                          │ - Volatility: Minimum daily ATR ($ or %)?                   │
│                          │ - Volume: Relative volume (2-5 day volume buildup/coil)?    │
│                          │ - Catalysts: Earnings date distance, gap thresholds?        │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 2. Required Qualifiers   │ What market structure must the 133-tick chart display?      │
│    (133-Tick Structure)  │ - Higher highs and higher lows (HH/HL)?                     │
│                          │ - Breakout from 133-tick consolidation range?               │
│                          │ - Position relative to intraday VWAP or moving average?     │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 3. Setup Context         │ What pattern must appear on the 1-minute chart?             │
│    (1-Minute Chart)      │ - Bull/bear flag consolidation?                             │
│                          │ - Pullback to 1-min 20 EMA or VWAP reclaim?                 │
│                          │ - Minimum/maximum number of pullback bars?                  │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 4. Entry Trigger         │ What exact micro-event on the 50-tick chart fires entry?    │
│    (50-Tick Chart)       │ - 50-tick bar close breaking micro-consolidation high?      │
│                          │ - Consecutive advancing 50-tick bars with expanding volume? │
│                          │ - Micro double-bottom breakout?                             │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 5. Entry Mechanics       │ - Direction: Long only, Short only, or Bidirectional?       │
│                          │ - Order type: Market on 50-tick close, Limit, or Stop?      │
│                          │ - Price fill convention & slippage allowance?               │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 6. Invalidation / Stop   │ What is the exact initial stop-loss rule known at entry?    │
│                          │ - Low of the 50-tick trigger bar?                           │
│                          │ - Lowest low of the 1-minute setup pattern?                 │
│                          │ - Fixed dollar or ATR fraction buffer?                      │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 7. Exit / Targets        │ - Target: Fixed R-multiple (1R, 2R), daily level, pivot?    │
│                          │ - Trailing stop: Trailing on 133-tick swing lows, breakeven?│
│                          │ - Time exit: Max duration (e.g. 15, 30, 60 minutes)?        │
│                          │ - Session-end: Forced liquidation time (e.g. 15:55 ET)?     │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 8. No-Trade Conditions   │ - Time of day: Avoid 09:30–09:45 ET, 12:00–13:00 ET?       │
│                          │ - Macro news: FOMC release, CPI release days?               │
│                          │ - Spread limit: Maximum bid-ask spread permitted?           │
│                          │ - Low tick velocity: Suppress if 50 ticks takes > 5 min?    │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 9. Explainability        │ What exact reasons and metrics must TradeX display in the   │
│                          │ UI to explain why this setup triggered?                     │
└──────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

### H. Outcome Evaluation Architecture

To evaluate the full multi-resolution setup, TradeX requires an upgraded evaluation engine. Fixed-horizon event studies are insufficient.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Existing Event Study (DAYTRADE-001/002)     │ Full Multi-Resolution Lifecycle Needed  │
├─────────────────────────────────────────────┼──────────────────────────────────────────┤
│ Fixed clock horizon (1m, 2m, 5m, 30m)       │ Path-dependent simulation (tick-by-tick) │
│ Unconditional forward return distribution   │ First-touch between stop-loss and target │
│ Gross return minus fixed friction rate      │ Realistic slippage, spread, and fees     │
│ Ignores intraday path (MFE / MAE)           │ Tracks Max Favorable & Adverse Excursion │
│ Evaluates all events independently          │ Models concurrent positions & capital    │
│ No concept of in-flight position duration   │ Maximum holding duration & session exit  │
│ Single opportunity denominator              │ Funnel tracking: Candidate → Qualified   │
│                                             │ → Triggered → Filled → Closed            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

#### What Must Be Built for Outcome Evaluation:
1. **Intraday Path-Dependent Simulator:** Simulates the life of a trade across subsequent 50-tick and 1-minute bars, deterministically evaluating whether the stop-loss or profit target was touched first, handling intra-bar high/low ambiguity with conservative tie-break rules.
2. **Opportunity Funnel Metrics:** Tracks conversion rates at every level:
   $$\text{Universe} \longrightarrow \text{Daily Qualified} \longrightarrow \text{133-Tick Qualified} \longrightarrow \text{1-Min Setup} \longrightarrow \text{50-Tick Trigger} \longrightarrow \text{Trade}$$
3. **Execution Friction & Realism:** Fills priced at next bar open or stop price plus spread/slippage buffer, with exchange fees modeled.

---

### I. Research Methodology & Governance

Previous statistical studies (`DAYTRADE-001`, `DAYTRADE-002`) applied a rigid, binary 5-step disposition sequence where any single gate failure immediately branded the study as `rejected` or `inconclusive`, terminating research.

While strict gates are vital to prevent lookahead and overfitting, **a decision-support research program requires a richer research lifecycle** that clearly distinguishes:
$$\text{"Not yet proven enough for production"} \quad \neq \quad \text{"Not worth researching further"}$$

#### Proposed Multi-State Research Lifecycle:

```text
1. Hypothesis & Preregistration
               ↓
2. Data Feasibility Verification
               ↓
3. Foundation Implementation (Tick Aggregation & Simulator)
               ↓
4. Bounded Development Exploration (Parameter tuning on dev partition ONLY)
               ↓
5. Formal Validation Study (Preregistered gates on validation partition)
               │
      ┌────────┴────────────────────────┬──────────────────────┐
      ▼                                 ▼                      ▼
 [SUPPORTED]               [PROMISING_NOT_CONFIRMED]      [REJECTED / INVALID]
      │                                 │                      │
      │ All gates pass                  │ Positive edge, but   │ Directional failure,
      │ with statistical                │ CI crosses zero or   │ negative uplift,
      │ certainty                       │ minor DQ flaw        │ or design defect
      ▼                                 ▼                      ▼
6. Holdout Evaluation             Iterate / Refine        Archive Hypothesis
      ↓                           in Research Only        (Do not promote)
7. Prospective Shadow Replay      (Do NOT promote)
      ↓
8. Gary Production Review
```

#### Multi-State Research Taxonomy:
* **`supported`**: All preregistered statistical, economic, and breadth gates pass with 95% confidence on out-of-sample data. Authorizes progression to holdout.
* **`promising_not_confirmed`**: Point estimates show positive net edge, positive baseline uplift, and positive breadth, but confidence intervals cross zero or sample size requires expansion. **Authorizes continued research**, but **strictly prohibits production promotion**.
* **`inconclusive`**: Severe data insufficiency or ambiguous evidence that cannot establish direction.
* **`not_supported` / `rejected`**: Directional hypothesis failure, negative net return, or negative baseline uplift.
* **`invalid`**: Methodological, timestamp, or data integrity defect.

**Production Promotion Boundary Invariant:**
Even if a setup earns `supported` on holdout, **production promotion remains a separate, explicit governance decision requiring Gary's written approval**. `APPROVED_PRODUCTION_STRATEGIES == ()` remains the immutable default.

---

## 4. Carry-Forward Analysis: DAYTRADE-001 and DAYTRADE-002

`DAYTRADE-001` and `DAYTRADE-002` remain valid historical research. They must **not** be deleted or reinterpreted. Their role becomes reusable component infrastructure and empirical lessons:

### DAYTRADE-001 Carry-Forward

* **Hypothesis Tested:** Extreme downside 1-minute price drops on Dow 30 equities predict an immediate 1-minute positive bounce.
* **Empirical Outcome:**
  * Development: `REJECTED` (Mean net return $-5.45$ bps, only 2/30 tickers positive, negative uplift of $-1.50$ bps).
  * Validation: Formally `INCONCLUSIVE` (Step 2 data-quality failure: 7.83% of sessions excluded due to missing bars in 4 tickers: TRV, GS, SHW, AMGN).
* **Key Lessons:**
  1. *Micro-momentum vs. Reversal:* Extreme 1-minute drops in single stocks continue downward; order flow creates short-term momentum rather than an immediate liquidity bounce.
  2. *Fixed-Clock Limitation:* Fixed 1-minute bars on single stocks suffer from missing minutes during light trading volume. Activity-driven tick bars (133-tick, 50-tick) adapt to market activity and eliminate empty-time bar artifacts.
  3. *Friction Penalty:* 2 bps/side friction heavily penalizes ultra-short 1-minute holding periods. Strategy edges must target larger intraday moves to overcome transaction costs.
* **Reusable Assets:** Pre-registration specification structure, data-quality auditing module, and split boundary isolation guards.

### DAYTRADE-002 Carry-Forward

* **Hypothesis Tested:** An unusually strong first-half-hour directional move (09:30–10:00 ET) on 15 liquid ETFs predicts same-direction momentum in the final half-hour (15:30–16:00 ET).
* **Empirical Outcome:**
  * Development: `REJECTED` (Net return $-0.95$ bps, breadth 53.33%).
  * Validation: Formally `INCONCLUSIVE` due to primary net return 95% CI crossing zero ($-2.02$ bps lower bound), but produced:
    * Positive gross return (+7.46 bps, 67.97% win rate);
    * Positive net return (+3.46 bps at 2 bps/side friction);
    * Positive ETF breadth (10 of 15 ETFs positive = 66.67%);
    * Statistically significant positive baseline uplift (+6.44 bps, 95% CI $[+0.44\text{ bps}, +12.14\text{ bps}]$).
  * Exploratory Directional Asymmetry: Short momentum was substantially stronger (+9.77 bps net, 80.65% win rate, $+11.70$ bps uplift) than long momentum ($-0.84$ bps net, 59.34% win rate).
* **Key Lessons:**
  1. *Liquid ETF Efficiency:* Highly liquid ETFs completely eliminated data-quality missing-bar issues (0.0% exclusions vs 7.83% in Dow 30 equities).
  2. *Intraday Momentum Edge:* Intraday directional momentum on index/sector ETFs showed genuine positive edge over longer holding periods (30 minutes), but sample size and regime variance created confidence interval uncertainty.
* **Reusable Assets:** Session-date clustered bootstrap inference engine, matched non-event baseline architecture, multi-signal session tracking, and provider provenance tracking.
* **Integrity Guard:** DAYTRADE-002 observations are hypothesis-generating only and must not be used to secretly tune future multi-resolution setups.

---

## 5. Staged Implementation Roadmap

To turn the original multi-resolution thesis into an executable research system without high-risk monolithic builds, we recommend a staged, bounded sequence:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        RECOMMENDED IMPLEMENTATION ROADMAP                              │
├───────────────┬─────────────────────────────────────────────────┬──────────────────────┤
│ Phase         │ Title & Scope                                   │ Nature               │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003A │ Original Thesis Re-anchor & Gap Analysis        │ Research Design Only │
│               │ (This assignment: gap matrix, roadmap, answers) │ (Current)            │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003B │ Tick-Data Provider & Feasibility Study          │ Bounded Data Probe   │
│               │ - Verify Alpaca / Polygon / Schwab trade ticks  │ (Zero backtests)     │
│               │ - Measure volume, latency, pagination, fields   │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003C │ Tick-Bar Aggregation & Storage Foundation       │ Engineering Prims    │
│               │ - Build trade accumulator for 133 & 50 ticks    │ (Zero trading rules) │
│               │ - Lock session reset, trade filter, Parquet DB  │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003D │ Gary Strategy Elicitation & Preregistration     │ Strategy Definition  │
│               │ - Structured interview to lock Gary's rules     │ (Lock parameters)    │
│               │ - Formally preregister concrete candidate setup │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003E │ Synthetic Full-Lifecycle Simulator              │ Research Engine      │
│               │ - Path-dependent execution simulator            │ (Synthetic tests)    │
│               │ - First-touch stops/targets, trailing, MFE/MAE  │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003F │ Bounded Empirical Development Study             │ Empirical Study      │
│               │ - Run locked strategy on real dev partition     │ (Diagnostic only)    │
│               │ - Analyze execution distributions & uplift      │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003G │ Formal Validation & Evaluation Study            │ Formal Validation    │
│               │ - Out-of-sample evaluation under multi-state    │ (One-pass gate)      │
│               │   taxonomy (supported / promising / rejected)   │                      │
├───────────────┼─────────────────────────────────────────────────┼──────────────────────┤
│ DAYTRADE-003H │ Conditional Holdout & Prospective Shadow        │ Pre-Production       │
│               │ - Holdout unsealed only if validation passes    │ (Zero live capital)  │
│               │ - Prospective shadow execution before Gary review│                     │
└───────────────┴─────────────────────────────────────────────────┴──────────────────────┘
```

---

## 6. The Ten Required Canonical Answers

Section 16 of the task assignment requires explicit, definitive answers to ten core architectural questions:

### 1. What was the original DAYTRADE product/research thesis?
The original thesis was a multi-resolution decision-support workflow modeling Gary Yang's discretionary trading process:
$$\text{Daily Context} \longrightarrow \text{133-Tick Structure} \longrightarrow \text{1-Minute Setup} \longrightarrow \text{50-Tick Timing} \longrightarrow \text{Execution}$$
Its purpose was to combine macro context, activity-driven intraday structure, calendar-time setup patterns, and precision tick timing into an explainable, disciplined trading framework.

### 2. What portions of it are already implemented?
The core in-memory multi-resolution foundation is implemented and tested in `tradex/research/daytrade_mvp`:
* Strongly typed `Resolution` enum supporting all 4 timeframes;
* `CompletedBar` with strict validation and timezone awareness;
* `MultiResolutionSeries` with isolated point-in-time materialization (`filter_as_of`);
* `DaytradeSetup` abstract protocol and fail-closed `evaluate_setup()` orchestrator;
* Deterministic synthetic test harness with 9 passing regression tests.

### 3. What did DAYTRADE-001 and DAYTRADE-002 actually test?
* `DAYTRADE-001`: An isolated 1-minute mean-reversion hypothesis testing whether extreme downside 1-minute returns on Dow 30 equities bounced immediately over the next 1 minute.
* `DAYTRADE-002`: An isolated intraday momentum hypothesis testing whether strong first-half-hour moves (09:30–10:00 ET) on 15 liquid ETFs predicted same-direction returns in the final half-hour (15:30–16:00 ET).

### 4. Where did the program diverge from the original thesis?
The program diverged by abandoning the multi-resolution hierarchy (Daily $\rightarrow$ 133-tick $\rightarrow$ 1-minute $\rightarrow$ 50-tick) in favor of searching for standalone, single-timeframe statistical anomalies on 1-minute fixed-clock bars.

### 5. Which divergence was intentional and useful?
The divergence was intentional to test whether high-frequency statistical edges existed on 1-minute data before building complex tick infrastructure. It was extremely useful because it established:
* Reusable pre-registration and specification locking discipline;
* Clustered bootstrap inference and matched baseline methodologies;
* Rigorous data-quality auditing protocols;
* Empirical proof of transaction friction impacts on short-horizon day trades.

### 6. Which divergence should no longer drive the roadmap?
Continuing to make isolated 1-minute single-timeframe statistical anomalies the primary DAYTRADE roadmap should no longer drive TradeX. Searching for isolated micro-anomalies does not build Gary's multi-resolution decision-support tool.

### 7. What is the biggest technical blocker to returning to the original thesis?
The complete absence of raw trade-tick data infrastructure in TradeX:
* No provider client to download historical execution trades (`/v2/stocks/trades`);
* No streaming trade receiver;
* No aggregation engine to group raw trades into 133-tick and 50-tick bars;
* No storage layer for tick series.

### 8. What is the biggest research-definition blocker?
The absence of Gary Yang's concrete strategy rules. `DAYTRADE-001A` intentionally created only a synthetic test setup (`SYNTH-DAYTRADE-001`). Gary's real criteria for Daily context, 133-tick structure, 1-minute setups, 50-tick triggers, stops, and targets have never been elicited or preregistered.

### 9. What is the next smallest reversible task?
**`DAYTRADE-003B`: Tick-Data Provider & Data-Feasibility Study.**
A bounded empirical probe to determine whether our market data subscription (Alpaca or alternative) can reliably provide historical trade-level ticks for candidate equities and ETFs, measuring rate limits, latency, pagination, and fields. It involves zero strategy backtesting, zero trading rules, and zero production risk.

### 10. What must Gary personally define or approve before a real multi-resolution setup can be tested?
Gary must complete the Strategy Elicitation Contract (Section 3.G):
1. **Daily context criteria:** Technical/fundamental filters that qualify a stock.
2. **133-tick structure conditions:** What defines favorable intraday trend/structure.
3. **1-minute chart pattern:** The exact setup pattern required.
4. **50-tick entry trigger:** The precise micro-structure trigger event.
5. **Entry order & fill rules:** Market/limit/stop, direction, slippage allowance.
6. **Stop-loss invalidation rule:** Exact stop price calculation at entry.
7. **Profit target & exit logic:** R-multiples, trailing stops, max duration, session exit.
8. **No-trade conditions:** Time-of-day, macro events, spread limits.

---

## 7. Governance, Verification, and Boundaries

This assignment is strictly design and documentation only:

* **Production Code:** ZERO production files modified.
* **Production Strategies:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved in `tradex/strategies/registry.py`.
* **Trading Logic:** ZERO new trading strategies or indicators implemented.
* **Historical Evidence:** ZERO historical empirical results from `DAYTRADE-001` or `DAYTRADE-002` reinterpreted or modified.
* **Market Data Calls:** ZERO external provider calls made.
* **Private Datasets:** ZERO private historical datasets accessed or parsed.
* **Holdout Partitions:** ZERO holdout partitions unsealed or read.
* **Regression Tests:** All 9 tests in `tests/research/daytrade_mvp/test_daytrade_mvp.py` pass.
* **Contract Tests:** Design contract verified via `tests/research/test_daytrade_003a_contract.py`.
* **Linting:** `uv run ruff check tests scripts tradex/research/daytrade_mvp` passes with 0 errors.

---
*Document author: Antigravity Agentic Assistant*
*Date: 2026-10-06*
