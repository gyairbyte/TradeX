# DAYTRADE-003E: Explainable Research-Only ORB Candidate Preview

**Task ID:** `DAYTRADE-003E-ORB-PREVIEW-001`  
**Classification:** Research-Only Decision Support & Preview Service  
**Status:** Implemented on branch `antigravity/daytrade-003e-orb-preview-001`  
**Upstream Specs:** `docs/research/specs/DAYTRADE-003B-ORB-v1.json`, `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json`, `docs/research/specs/DAYTRADE-003D-CORR-003-v1.json`  
**Strategy Authority:** Zarattini, Barbon, Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market* (Swiss Finance Institute RP 24-98 / SSRN 4729284)

---

## 1. Executive Summary & Authorization

Gary Yang approved shifting DAYTRADE-003 toward faithful, useful implementation of the published Stocks-in-Play 5-minute Opening Range Breakout (ORB) methodology, rather than broad infrastructure or repeated failed pilots. This authorizes **one bounded research-only, read-only preview implementation** in TradeX **Research Lab**.

This task explicitly does **not** authorize:
- Production strategy promotion (`APPROVED_PRODUCTION_STRATEGIES == ()` remains strictly empty).
- Modifications to production signals, scorers, weights, rankings, or defaults.
- Historical data acquisition or provider calls (no full-year 2024 acquisition, no 2025 validation access, no 2026 holdout access).
- Rerunning the January 2, 2024 pilot (unrelated CORR-004 runner behavior remains deferred).
- Automated alerts, brokerage orders, live fills, or trade simulations.

---

## 2. Core Architecture & Reused Research Logic

The preview service reuses existing, audited technical calculations in `tradex.research.daytrade_orb`:

| Operation | Implementation Function | Source Specification |
|---|---|---|
| Average Daily Volume (ADV14) | `tradex.research.daytrade_orb.indicators.compute_adv14` | Arithmetic mean of daily volume over exact 14 completed XNYS sessions preceding session D (D strictly excluded). Threshold: $\ge 1,000,000$ shares. |
| Average True Range (ATR14) | `tradex.research.daytrade_orb.indicators.compute_atr14_wilder` | Welles Wilder 14-session ATR through session D-1 (requires 15 contiguous completed XNYS daily bars; session D strictly excluded). Threshold: $> \$0.50$. |
| Relative Volume (RV14) | `tradex.research.daytrade_orb.indicators.compute_relative_volume` | Opening Range Volume at session D divided by arithmetic mean of exact 14 immediately preceding completed XNYS sessions' opening range volumes (D-1 through D-14; CORR-003C-RV-LOOKBACK). Threshold: $\ge 1.0$. |
| Opening Range Evaluation | `tradex.research.daytrade_orb.ranking.evaluate_opening_range` | Aggregates 09:30–09:34 ET 1-minute bars under sparse-bar semantics (`require_five_bars=False`). Direction is LONG if close > open, SHORT if close < open, DOJI if close == open. |
| Candidate Eligibility Filtering | `tradex.research.daytrade_orb.ranking.evaluate_candidate` | Evaluates price $> \$5.00$, ADV14 $\ge 1,000,000$, ATR14 $> \$0.50$, RV14 $\ge 1.0$. |
| Top-20 Selection & Sizing | `tradex.research.daytrade_orb.ranking.rank_and_select_top_20` | Ranks eligible candidates by RV descending, symbol ascending tie-breaker. Selects top 20 max. Sizing uses 1% risk / 4x gross leverage ceiling (SSRN 4416622). |

---

## 3. Strict Rules & Research Governance Invariants

1. **09:35 ET Earliest Time Gate:**
   - Candidate ranking requires the complete 5-minute regular-session opening range (09:30–09:34 ET) and completed prior daily bars through D-1.
   - Any snapshot with an as-of time prior to 09:35:00 ET blocks candidate ranking with an explicit time-gate blocker.
   - Any minute bar timestamped at or after 09:35:00 ET inside opening range bars is flagged as `INTEGRITY_BLOCKED: Future-bar leakage`.

2. **Provided-Input Coverage Scope:**
   - Previews rank candidates **strictly within the uploaded or demo constituent set**.
   - It is never labeled the source paper's full-market Top-20 (~7,000 U.S. equities) unless full-market point-in-time universe data is verified.
   - A visible warning discloses the declared universe completeness status (`watchlist_only`, `unknown`, `declared_complete`), explicitly noting that even `declared_complete` is self-declared and unverified.

3. **Doji No-Order and No-Backfill Invariant:**
   - If a Doji opening range (OR close == open) qualifies among the Top 20 by RV, it produces `NO_ORDER_DOJI`.
   - In accordance with primary paper methodology and DAYTRADE-003C resolution, rank #21 is **not** backfilled to replace a Doji candidate.

4. **Theoretical Protective-Stop Offset:**
   - Prospective stop-entry triggers represent the opening-range breakout level: OR High for Long, OR Low for Short, None for Doji.
   - The protective-stop distance is $0.10 \times \text{ATR14}$ relative to the **future executed fill price** (`fill ± 0.10 × ATR14`), not a promised prefilled fill price.
   - No executed fills, simulated trades, win rates, or PnL are evaluated or claimed.

5. **Per-Symbol Error Isolation:**
   - Data unavailability or formatting errors in one constituent do not collapse the entire preview for valid constituents.
   - Corrupt entries are isolated and audited under `INTEGRITY_BLOCKED`. Missing observations are classified as `DATA_UNAVAILABLE`. Technical filter failures are classified as `TECHNICAL_FILTER`.

---

## 4. Snapshot JSON Ingestion Contract

The preview accepts an explicit in-memory JSON file (up to 5 MB) via `tradex.research.daytrade_orb.snapshot.parse_snapshot_json`:

```json
{
  "schema_version": "1.0",
  "session_date": "2024-01-02",
  "as_of_time": "2024-01-02T09:35:00-05:00",
  "source_type": "synthetic_demo",
  "source_label": "TradeX Research Synthetic Demo Universe",
  "completeness_status": "watchlist_only",
  "notes": "Research-only candidate preview snapshot.",
  "symbols": {
    "SYNTH_L01": {
      "primary_exchange": "XNAS",
      "daily_bars": [
        {
          "session_date": "2023-12-08",
          "open": 149.80,
          "high": 151.25,
          "low": 148.75,
          "close": 150.20,
          "volume": 2000000.0
        }
      ],
      "opening_range_bars": [
        {
          "timestamp": "2024-01-02T09:30:00-05:00",
          "open": 150.00,
          "high": 150.50,
          "low": 149.60,
          "close": 150.05,
          "volume": 90000.0
        }
      ],
      "prior_opening_range_volumes": [
        {
          "session_date": "2023-12-11",
          "volume": 100000.0
        }
      ]
    }
  }
}
```

### Safety & Ingestion Boundaries
- **Max file size:** 5,242,880 bytes (5 MB). Files exceeding this limit are rejected immediately.
- **Duplicate symbol policy:** Duplicate keys (differing only by whitespace or casing) fail closed during JSON validation.
- **Zero raw storage:** Uploaded files are processed in-memory. No raw OHLCV bars are saved to disk, logged, or retained.

---

## 5. User Interface (Research Lab)

The preview is exposed exclusively under:
```
Dashboard -> Tab 6 (Research Lab) -> Sub-tab 5 ("ORB Candidate Preview — Research Only")
```

Features:
1. **Governance & Literature Disclosure:** Clearly explains unvalidated status, external citation, and non-actionable boundary.
2. **Snapshot Selector:** Allows one-click loading of the built-in 33-symbol synthetic demo snapshot, or uploading custom in-memory JSON snapshots.
3. **Metadata & Coverage Summary:** Displays session date, as-of time (ET), source type, constituent count, and universe completeness warnings.
4. **Time-Gate Blocker:** Displays an error message and stops rendering if the snapshot is prior to 09:35 ET.
5. **Top-20 Candidate Table:**
   - Columns: `Rank`, `Symbol`, `Direction` (LONG/SHORT/DOJI), `OR Open`, `OR High`, `OR Low`, `OR Close`, `OR Volume`, `ADV14`, `ATR14`, `RV14`, `Stop-Entry Trigger`, `Theoretical Stop Offset` ($\pm 0.10 \times \text{ATR14}$), `Order Intent`, `Setup Explanation`.
6. **Exclusions Audit Expander:**
   - Lists excluded constituents categorized as `TECHNICAL_FILTER`, `DATA_UNAVAILABLE`, or `INTEGRITY_BLOCKED` with detailed reasons.
