# DAYTRADE-003D: Stocks-in-Play ORB Real-Data Feasibility & Acquisition Probe

## 1. Document & Task Metadata

- **Task ID:** `DAYTRADE-003D-ORB-DATA-FEASIBILITY-001`
- **Strategy ID:** `DAYTRADE-003B-ORB-SIP5M`
- **Classification:** Research-only real-data feasibility and bounded acquisition probe
- **Base / Starting Main SHA:** `faec0b096bd8fe7b1f7761557a1f74fbdac41ba1`
- **Locked DAYTRADE-003B Spec:** `docs/research/specs/DAYTRADE-003B-ORB-v1.json` (SHA-256: `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`)
- **Locked DAYTRADE-003C Resolution Spec:** `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` (SHA-256: `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`)
- **Machine-Readable Specification:** `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` (SHA-256: `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c`)

---

## 2. Research Protocol & Governance Boundaries

This assignment is strictly bounded to data feasibility and acquisition validation.

- **Real provider calls:** AUTHORIZED ONLY within the exact bounds of this probe.
- **Private local research data:** AUTHORIZED ONLY within the exact bounds of this probe.
- **Full 2024 development dataset construction:** NOT AUTHORIZED.
- **Strategy backtest / evaluator execution:** NOT AUTHORIZED.
- **Development performance evaluation:** NOT AUTHORIZED.
- **Validation partition (2025):** NOT AUTHORIZED.
- **Holdout partition (2026):** STRICTLY QUARANTINED AND UNOPENED.
- **Production trading behavior:** NO CHANGE. `APPROVED_PRODUCTION_STRATEGIES == ()`.

The sole question for DAYTRADE-003D is:
> *Can the currently available Massive/Polygon + Alpaca SIP provider path construct the data required by the locked DAYTRADE-003B/003C contracts truthfully enough to proceed with the 2024 development dataset?*

---

## 3. Fixed Probe Dates

All dates are locked prospectively and verified as full regular XNYS sessions (opens 09:30 ET, closes 16:00 ET, `is_early_close == False`):

1. **`2024-01-02`** (Session 1 of 2024 — End-to-end Stage A + Stage B pilot date)
2. **`2024-06-03`** (Mid-year reference-only snapshot)
3. **`2024-12-02`** (Late-year reference-only snapshot)

For all three dates, a complete historical active U.S. stock-market point-in-time reference snapshot is acquired from Massive (`/v3/reference/tickers`) to audit historical date sensitivity, pagination, symbol identity, and universe drift. Intraday bars are acquired ONLY for `2024-01-02`.

---

## 4. Exchange Mapping Policy

DAYTRADE-003C specifies point-in-time U.S. equity-market records whose primary exchange is **NYSE or Nasdaq**.
Massive / Polygon exposes ISO 10383 Market Identifier Codes (MIC):
- **NYSE:** `XNYS`
- **Nasdaq:** `XNAS`

Non-target exchanges (such as `ARCX` NYSE Arca, `XASE` NYSE American, `BATS` Cboe BZX, `XBOS` Nasdaq BX, and OTC/empty) are excluded from the target candidate universe.
No artificial security-type exclusions (e.g. against ETFs or warrants) are applied; provider `type` values are preserved for auditability.

---

## 5. Lean Two-Stage Acquisition Architecture & Strict No-Lookahead

1. **Stage A (09:30-09:34 ET candidate construction):**
   - Raw daily OHLCV from Alpaca SIP (`timeframe=1Day`, `adjustment=raw`, `asof=2024-01-02`) covering the 20 completed regular XNYS trading sessions in December 2023 (2023-12-01 through 2023-12-29). Target session 2024-01-02 is strictly excluded from ADV14 and ATR14 lookbacks.
   - Raw 1-minute bars from Alpaca SIP (`timeframe=1Min`, `adjustment=raw`) for 09:30..09:34 ET across the 14 prior completed XNYS sessions (2023-12-11 through 2023-12-29) for Relative Volume denominator baseline.
   - Raw 1-minute bars for 2024-01-02 09:30..09:34 ET for current opening range.
   - 100% candidate-pool computability gate: every active target-universe member must have computable indicators. Insufficient history due to IPO listing age is surfaced and classified explicitly.

2. **Strict No-Lookahead Freezing:**
   - Candidate ranking (RV desc, ticker asc) and Top-20 selection occurs strictly prior to requesting any post-09:35 market data.
   - The Top-20 selection artifact is serialized and hashed (`top_20_selection_artifact_hash`) before Stage-B acquisition begins.

3. **Stage B (09:35-15:59 ET trade path):**
   - Raw 1-minute SIP bars (`timeframe=1Min`, `adjustment=raw`) for the selected Top-20 symbols only.
   - Complete 385-minute path audited. Zero strategy backtesting or PnL evaluation executed.

---

## 6. Private Output Root & Artifact Safety

- **Private Output Root:** `C:\Users\Gary\.tradex\research\daytrade_003d_orb_probe`
  Contains raw bar files, full ticker rosters, and the complete private manifest `manifest.json`.
- **Public Repository Artifacts:** `docs/research/artifacts/DAYTRADE-003D/`
  Contains ONLY safe aggregates:
  - `probe_summary.json`
  - `resource_estimate.json`
  - `provider_evidence.json`
  Zero OHLC prices, zero ticker symbol lists, and zero credentials are committed.

---

## 7. Disposition Precedence Hierarchy

1. `FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD`
2. `BLOCKED_MASSIVE_ENTITLEMENT`
3. `BLOCKED_ALPACA_SIP_ENTITLEMENT`
4. `BLOCKED_REFERENCE_EXCHANGE_MAPPING`
5. `BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS`
6. `BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY`
7. `BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS`
8. `BLOCKED_STAGE_A_DATA_COMPLETENESS`
9. `BLOCKED_STAGE_B_PATH_COMPLETENESS`
10. `BLOCKED_RESOURCE_BOUND`
11. `INVALID_PROBE_IMPLEMENTATION_DEFECT`
12. `INVALID_PROVIDER_RESPONSE_INTEGRITY`
