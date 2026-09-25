# DAYTRADE-001A: Multi-Resolution Research MVP Foundation

**Task ID:** DAYTRADE-001A  
**Status:** Research Specification & Foundation Contract  
**Classification:** Research-only (Zero production impact)

---

## 1. Purpose of DAYTRADE-001

The `DAYTRADE-001` program represents TradeX's future real-time day-trading decision-support research stream. Its ultimate goal is to model Gary's multi-resolution intraday discretionary trading approach within a structured, deterministic research and execution framework.

`DAYTRADE-001A` establishes the minimum viable research foundation required to support multi-resolution data structures, strict point-in-time (PIT) information discipline, and explicit setup specifications without prematurely coupling to unvalidated providers or inventing unapproved trading rules.

---

## 2. Separation from INTRA-001

TradeX previously executed the `INTRA-001` research program (`INTRA-001A` through `INTRA-001D`):
- `INTRA-001` evaluated a specific opening-drive / VWAP-pullback continuation hypothesis using 5-minute bars.
- The locked study concluded with disposition **`inconclusive`** due to sample size minimums and missing-bar thresholds in private historical snapshots, without parsing the holdout partition.
- `INTRA-001` is **not production-promotion eligible** (`production_promotion_eligible = false`).
- `APPROVED_PRODUCTION_STRATEGIES` remains strictly empty (`()`).

`DAYTRADE-001` is **explicitly separate** from `INTRA-001`. It does not promote, revive, or depend on the `INTRA-001` opening-drive hypothesis.

---

## 3. Intended Multi-Resolution Workflow

The intended multi-resolution day-trading workflow consists of the following hierarchical funnel:

```
Daily / multi-year context
         ↓
  133-tick structure
         ↓
1-minute setup context
         ↓
  50-tick entry timing
         ↓
trigger / entry / invalidation / exit
```

The tiers serve the following roles in the research architecture:
1. **Daily / Multi-Year Context (`DAILY`):** Higher-timeframe macro and historical daily context.
2. **133-Tick Structure (`TICK_133`):** Intermediate tick-structure context.
3. **1-Minute Setup Context (`MINUTE_1`):** Calendar-minute setup context.
4. **50-Tick Entry Timing (`TICK_50`):** Fast tick-based entry timing.
5. **Trigger / Entry / Invalidation / Exit:** Explicit trade lifecycle rules including trigger condition, order entry, protective stop/invalidation, and target/exit logic.

DAYTRADE-001A models this multi-resolution structure purely as an architectural data and execution interface. It does not define, prescribe, or invent Gary's real strategy rules or any specific indicators or patterns.

---

## 4. Reusable Components from INTRA-001

The following conceptual patterns from `INTRA-001` are genuinely useful and adopted:
- **Point-in-Time (PIT) Discipline:** Absolute prohibition against lookahead leakage. An evaluator evaluated as of timestamp $T$ receives only data completed and available at or before $T$.
- **Bar Completion Semantics:** A bar is only available for signal generation once its closing boundary has arrived; in-flight or partial bars cannot trigger historical or backtest signals.
- **Fail-Closed Validation:** Missing required data or malformed inputs deterministically yield `invalid_input` rather than best-effort guesses.
- **Neutral Research Outputs:** Strategy evaluators return structured, immutable result records with human-readable reasons and machine-readable evidence fields.
- **Isolated Synthetic Testing:** Validation via deterministic synthetic data fixtures before any provider or live data integration.

---

## 5. Components NOT Appropriate to Reuse

The following components from `INTRA-001` are explicitly **excluded**:
- **Opening-Drive VWAP Reclaim Logic:** The specific 10:00–11:30 ET opening-drive rules from `tradex/research/intraday_engine/opening_drive.py` and `reclaim.py` belong solely to the inconclusive `INTRA-001` hypothesis and are not general day-trading primitives.
- **Fixed 5-Minute Calendar Grid:** `INTRA-001` hardcoded 5-minute NYSE regular-session calendar grids (`calendar.py`). Tick-based bars are volume/activity-driven and do not align to fixed clock intervals.
- **Coupled Engine Architecture:** `tradex/research/intraday_engine/` was tailored for a monolithic study comparison (Candidate vs. Baseline A vs. Baseline B). `DAYTRADE-001` requires a decoupled, setup-agnostic interface.
- **Legacy Intraday Heuristic Scorer:** `tradex/signals/intraday.py` computes an uncalibrated 0–100 indicator score without execution rules. It must not be entangled with `DAYTRADE-001`.

---

## 6. Current Known Data Gap: Tick Data Providers

A primary infrastructure gap exists in TradeX:
- TradeX's central fetcher (`tradex/data/fetcher.py`) and historical module (`tradex/data/history.py`) provide daily and standard fixed-time minute bars (1m, 5m, 15m).
- TradeX **does not currently possess a validated provider abstraction or historical storage layer for 133-tick and 50-tick series**.
- Tick bars require either:
  1. Aggregated trade-tick streaming / historical tick downloads with tick-count bar construction, or
  2. A provider that natively serves $N$-tick candles.

`DAYTRADE-001A` does **not** solve this provider acquisition gap. Instead, it creates the normalized container and interface capable of accepting tick bars once provider contracts are authorized in a future task.

---

## 7. Concrete Setup Specification Contract

Any future concrete day-trading setup proposed under `DAYTRADE-001` must formally define the following contract:

1. **Setup Identity & Version:** Unique immutable identifier (e.g. `setup_id="DAYTRADE-MOMENTUM-001"`, `version="0.1.0"`).
2. **Required Resolutions:** The exact subset of resolutions required (from `DAILY`, `TICK_133`, `MINUTE_1`, `TICK_50`).
3. **Signal / Trigger Condition:** Deterministic logic evaluating available bars at `as_of`.
4. **Information-Availability Timing:** Explicit statement of when each bar becomes available relative to clock time or tick arrival.
5. **Entry Rule:** Direction (Long/Short), order type (Market, Limit, Stop), and price anchoring (e.g., next bar open, breakout level).
6. **Invalidation / Stop Rule:** Exact stop-loss price calculation at time of entry.
7. **Exit / Target / Time-Exit Rule:** Profit targets, trailing stops, and mandatory end-of-session liquidation time.
8. **Transaction Cost & Slippage Assumptions:** Explicit round-trip commissions, exchange fees, and spread/slippage model (in basis points or cents).
9. **Max Position Duration:** Maximum bars or elapsed time allowed before forced exit.
10. **Overnight Holding Policy:** Explicit definition of whether overnight holding is permitted or prohibited (DAYTRADE-001A prescribes no default policy; each setup must define its policy explicitly).

---

## 8. Strategy Rule Governance

**No real trading rules are invented in DAYTRADE-001A.**

Because the repository does not contain an approved, documented set of day-trading entry rules for Gary, `DAYTRADE-001A` provides only:
1. The structural data models and multi-resolution container.
2. The setup protocol interface.
3. The deterministic PIT evaluator.
4. A clearly labeled synthetic example (`SYNTH-DAYTRADE-001`) used purely as an architectural test harness.

Formulating and approving concrete candidate setups (e.g. `DAYTRADE-001B`) is a separate product/research milestone requiring explicit user approval.
