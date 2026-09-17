# R7 PIT Live Provider Compatibility Study (MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001)

## Study Disposition
**`completed_evidence_sufficient_for_next_decision`**

The single authorized live provider study completed successfully from the exact preregistered protocol commit `5731baacf73197a15eb9c72c1d6eb2e16a09962b`. All 45 Candidate C symbols were queried prospectively across both Yahoo Finance and Massive reference providers with zero network or contract errors.

> This is one point-in-time provider compatibility observation. It does not establish long-term availability, provider reliability, instrument applicability, or a durable trading edge.

---

## Study Scope & Execution Metadata
- **Task ID:** `MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001`
- **Protocol Commit SHA:** `5731baacf73197a15eb9c72c1d6eb2e16a09962b`
- **Starting Main SHA:** `d86f0b6322e13e6801e06fd5b8eda6cf57a1faca`
- **Market Date:** `2026-09-17`
- **Timezone:** `America/New_York`
- **Study Start UTC:** `2026-09-17T14:41:31.316658+00:00`
- **Study End UTC:** `2026-09-17T14:50:24.994278+00:00`
- **Python Version:** `3.11.15`
- **yfinance Version:** `1.7.0`
- **Provider Adapters:**
  - `tradex.earnings.calendar._fetch_from_yahoo`
  - `tradex.pit.massive_reference.MassiveReferenceClient`
- **Candidate B (`candidate-dow30`) Hash:** `173411d5854450294821e4dedbe5147278ccf248d8a21fc1973d81a41b9465b4` (30 equities)
- **Candidate C (`candidate-dow30-sector-etfs`) Hash:** `83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29` (45 symbols: 30 equities + 15 ETFs)
- **Total Unique Symbols Evaluated:** 45

---

## Empirical Results Summary

### Population & Attempted Observations
- **Candidate C Total Symbols:** 45
- **Yahoo Attempted:** 45 / 45 (100.0%)
- **Massive Attempted:** 45 / 45 (100.0%)
- **Abort Events:** None. Zero auth, entitlement, rate-limit, or date-mismatch aborts occurred.
- **Market-Date Rollover:** None. The study started and concluded on market date `2026-09-17`.

### 1. Yahoo Finance Earnings Calendar Compatibility

| Population | Count | `KNOWN` | `CLEAN_NO_USABLE_UPCOMING_DATE` | `RESPONSE_ERROR` | `TECHNICAL_ERROR` |
|---|---|---|---|---|---|
| **Candidate B (Equities)** | 30 | 30 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **Sector ETF Subset** | 15 | 0 (0.0%) | 15 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| **Candidate C Overall** | 45 | 30 (66.67%) | 15 (33.33%) | 0 (0.0%) | 0 (0.0%) |

**Empirical Observation:**
The observed 30 Yahoo `KNOWN` and 15 `CLEAN_NO_USABLE_UPCOMING_DATE` outcomes align exactly with the 30 equity / 15 ETF population split. All 30 equities returned a usable upcoming earnings date, whereas all 15 sector ETFs cleanly raised `EarningsDataUnavailableError` (classified as `CLEAN_NO_USABLE_UPCOMING_DATE`) with zero response or technical errors. This empirical observation informs status architecture Option 2 + 3 policy decisions but is not converted into a universal hard-coded rule that all ETFs are `NOT_APPLICABLE`.

### 2. Massive Ticker Reference Compatibility

| Population | Count | `KNOWN` | `ERROR` | Provider Type Code (`CS` / `ETF`) | Provider Active (`True` / `False`) |
|---|---|---|---|---|---|
| **Candidate B (Equities)** | 30 | 30 (100.0%) | 0 (0.0%) | 30 `CS` / 0 `ETF` | 30 `True` / 0 `False` |
| **Sector ETF Subset** | 15 | 15 (100.0%) | 0 (0.0%) | 0 `CS` / 15 `ETF` | 15 `True` / 0 `False` |
| **Candidate C Overall** | 45 | 45 (100.0%) | 0 (0.0%) | 30 `CS` / 15 `ETF` | 45 `True` / 0 `False` |

**Empirical Observation:**
Massive returned valid, active ticker reference metadata for all 45 symbols (100% `KNOWN`), correctly identifying all 30 equities with provider type `CS` (Common Stock) and all 15 ETFs with provider type `ETF`. Zero error categories were reported (`massive_error_category: null` for all 45 symbols).

### 3. Missing-Field Frequencies
- **`delisted_utc`:** Missing on 45 / 45 observations (100.0%). This is the expected behavior for active, non-delisted instruments.
- **Other Reference Fields:** 0 missing. All other fields (`ticker`, `name`, `market`, `locale`, `primary_exchange`, `type`, `active`, `currency_name`, `cik`, `composite_figi`, `share_class_figi`) were fully populated across all 45 observations.

### 4. Latency Summary

| Provider / Segment | Min (ms) | Max (ms) | Mean (ms) | Median (ms) |
|---|---|---|---|---|
| **Yahoo Finance (Overall)** | 359.00 | 1016.00 | 552.09 | 500.00 |
| Yahoo Finance (Equities, 30) | 359.00 | 1016.00 | 482.90 | 476.50 |
| Yahoo Finance (ETFs, 15) | 578.00 | 844.00 | 690.47 | 688.00 |
| **Massive Reference (Overall)** | 140.00 | 11844.00 | 11305.20 | 11609.00 |
| Massive Reference (Equities, 30) | 140.00 | 11844.00 | 11252.57 | 11609.00 |
| Massive Reference (ETFs, 15) | 11110.00 | 11609.00 | 11410.47 | 11484.00 |

*Note on Massive latency:* The initial Massive request completed in 140.00 ms. Subsequent requests were paced deterministically according to the adapter's minimum interval pacing rule (~12.1 seconds) to respect provider rate limits, yielding the observed mean latency of ~11.3 seconds.

### 5. Errors & Anomalies
- **Yahoo Technical/Response Errors:** 0
- **Massive Error Categories:** None (`null` across all 45 observations)
- **Authentication Errors:** None
- **Entitlement Errors:** None
- **Rate-Limit Errors:** None
- **Timezone/Rollover Events:** None

---

## Historical Context
A prior missing-credential preflight run was executed on 2026-09-11 from protocol commit `5731baacf73197a15eb9c72c1d6eb2e16a09962b`. That preflight verified the safety abort mechanism: execution was blocked prior to network calls when Massive credentials were absent, producing a blocked `results.json` artifact with all 45 symbols recorded as `yahoo_attempted: false` and `massive_attempted: false`. Following credential configuration, the authorized single live study was executed cleanly from the identical protocol commit.

---

## Conclusion & Governance Boundaries
1. **Study Disposition:** `completed_evidence_sufficient_for_next_decision`. The empirical study completed with high integrity and provides sufficient empirical evidence for the subsequent architecture decision on Option 2 + 3 status semantics.
2. **Production Code & Semantics:** Unchanged. Production status semantics remain strictly governed by Schema v7 and contract v1. Option 2 + 3 production semantics are Gary-approved in principle but remain not implemented.
3. **Universe Selection:** Candidate B and Candidate C remain unselected. No universe selection is made by this study.
4. **Authorizations:** C2 implementation, scheduler installation, strategy promotion, and subsequent slices (such as R7 scheduler/universe wiring and R8) remain unauthorized until separately approved by Gary.
5. **Production Strategies:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains empty.

