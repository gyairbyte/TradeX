# R7-PIT-STATUS-DEC-001: Define PIT Observation Completeness and Operational Health Semantics

> **Task ID:** `MVP-ARCH-001-R7-PIT-STATUS-DEC-001` (Approval Task: `MVP-ARCH-001-R7-PIT-STATUS-DEC-001-APPROVAL`)
> **Classification:** Design-only / architecture decision
> **Status:** `gary_approved`
> **Approved Selection:** `option_2_plus_3` (Option 2 + Option 3)
> **Approved By:** Gary Yang (2026-09-09)
> **Approval Scope:** Architecture direction only (no production implementation authorized)
> **Authoritative Base SHA:** `93d2174fed72f325e4ea87199c2aac9045998cbb`
> **Prerequisite Decision Packet SHA:** `4680a13c140b8d93ff099b43cb818540f57a19c0` (PR #74 merge commit)
> **Author:** Antigravity

---

## 1. Executive Summary

This architecture decision packet resolves the fundamental design ambiguity exposed by `MVP-ARCH-001-R7-PIT-001C2-READINESS-A` (PR #73):

> **Core Question:** How should TradeX distinguish the successful, reliable operational execution of a point-in-time capture from the completeness, applicability, and reliability of the facts returned?

Under current C1 capture contracts (`tradex.pit.earnings`, `tradex.pit.reference`, `tradex.pit.ops`), capture status conflates two materially distinct dimensions:
1. **Operational execution health:** Did the scheduled capture process run reliably, contact providers, complete within time constraints, avoid crashes or swallowed failures, and faithfully record evidence?
2. **Research evidence completeness:** Are all requested domain facts known, applicable, and high-fidelity for downstream quantitative research and strategy models?

Current C1 enforces a strict all-known rule for family success and slot health:
$$\begin{cases}
\text{known\_n} == \text{requested\_n} & \implies \text{family SUCCEEDED} \\
0 < \text{known\_n} < \text{requested\_n} & \implies \text{family PARTIAL} \\
\text{known\_n} == 0 & \implies \text{family FAILED}
\end{cases}$$
$$\text{both families SUCCEEDED} \implies \text{slot HEALTHY (and operational status SUCCEEDED)}$$

Under these semantics, any single non-`KNOWN` observation prevents all-known family `SUCCEEDED`, but does not by itself determine whether the family terminates as `PARTIAL` or `FAILED` (which depends on whether at least one other observation is `KNOWN`). Likewise, exact slot/health status depends on both family run records and runner/health aggregation (where both families must `SUCCEED` for an operational `SUCCEEDED` or health `HEALTHY` slot).

While intentionally fail-closed, this conflates a wide spectrum of fundamentally different real-world conditions:
* successfully retrieving a known domain fact;
* successfully observing that no usable fact is currently available from the provider;
* a fact that may not conceptually apply to the instrument (e.g., corporate earnings for an ETF);
* ambiguous reference entity matches;
* provider-side omission or absence;
* unhandled parsing or normalization failures;
* transport, authentication, or rate-limiting errors;
* unexpected internal runtime crashes.

Crucially, deep code inspection of the earnings capture path reveals a **central provenance limitation in Schema v7**:
`tradex/earnings/calendar.py` catches all exceptions during Yahoo earnings retrieval (`get_earnings_dates()` and `.calendar`) and re-raises them as a generic `EarningsDataUnavailableError`. PIT earnings capture then maps this to `ObservationStatus.UNAVAILABLE`. Consequently:

> **Central Schema v7 Provenance Finding:** Schema v7 cannot reliably distinguish a provider/lookup failure that was swallowed upstream from a genuine no-usable-upcoming-date outcome.

Therefore, existing historical `UNAVAILABLE` observations in `signals.db` cannot safely be reinterpreted retroactively as successful observations of structural absence, nor does historical evidence prove structural ETF non-applicability. Furthermore, operational health cannot naively treat all current `UNAVAILABLE` rows as healthy capture execution without risking silently masking genuine provider failures.

This packet evaluates five architecture options, analyzes multiple mechanisms for applicability resolution, details historical and schema compatibility, establishes the role of empirical provider testing, and provides a clear, reasoned recommendation for Gary Yang's decision.

**This task is design-only. No production code changes, schema migrations, provider studies, universe selections, or scheduler installations are authorized.**

---

## 2. Decision Question

TradeX must formally decide:

> **Should TradeX define "healthy PIT capture" as "every domain fact is known," or as "the capture system executed reliably and truthfully recorded the resulting evidence state"?**

If TradeX adopts the latter (separating operational execution health from research evidence completeness), the secondary decision questions are:
1. What additional provenance, exception classification, and taxonomy must be introduced before operational health can be separated from completeness without masking provider outages?
2. How should instrument applicability (e.g., corporate earnings for ETFs) be determined without brittle hard-coded ticker lists or circular temporal dependencies?
3. How should Schema v7 compatibility be managed, and is Schema v8 required?
4. What role should live-provider empirical evidence play before design approval versus before implementation?
5. How does this decision unlock or constrain Candidates B (Dow 30) and C (Dow 30 + Sector ETFs)?

---

## 3. Current Repository Behavior

The repository currently defines capture execution and status derivation across five layers:

### A. Run Lifecycle States (`tradex/pit/models.py`)
```python
class CaptureRunStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
```

### B. Earnings Observation States (`tradex/pit/models.py`)
```python
class ObservationStatus(str, Enum):
    KNOWN = "known"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
```

### C. Reference Observation States (`tradex/pit/models.py`)
```python
class ReferenceObservationStatus(str, Enum):
    KNOWN = "known"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"
```

### D. Family-Level Terminal Derivation (`tradex/pit/earnings.py`, `tradex/pit/reference.py`)
Both earnings and reference capture finalize their run records using identical logic:
* If $\text{known\_n} == \text{requested\_n}$: run status $\rightarrow$ `SUCCEEDED`.
* If $0 < \text{known\_n} < \text{requested\_n}$: run status $\rightarrow$ `PARTIAL`.
* If $\text{known\_n} == 0$: run status $\rightarrow$ `FAILED`.

### E. Operational Slot Derivation (`tradex/pit/ops.py`)
In `_compute_operational_status` (run-slot CLI and runner):
* Both families absent ($\text{capture\_run\_id is None}$) $\rightarrow$ `PITOperationalStatus.FAILED`.
* Both families terminal `SUCCEEDED` $\rightarrow$ `PITOperationalStatus.SUCCEEDED`.
* Any other combination (including any family `PARTIAL`) $\rightarrow$ `PITOperationalStatus.DEGRADED`.

In `_derive_slot_health_status` (health CLI and inspector):
* Non-trading day or before slot time $\rightarrow$ `PITSlotHealthStatus.NOT_DUE`.
* Any run with different `universe_hash` $\rightarrow$ `PITSlotHealthStatus.UNIVERSE_CONFLICT`.
* Missing run for either family $\rightarrow$ `PITSlotHealthStatus.MISSING`.
* Any run in `STARTED` state $\rightarrow$ `PITSlotHealthStatus.INCOMPLETE`.
* Both families have $\ge 1$ terminal `SUCCEEDED` run $\rightarrow$ `PITSlotHealthStatus.HEALTHY`.
* Both families have terminal runs but not both `SUCCEEDED` $\rightarrow$ `PITSlotHealthStatus.DEGRADED`.

---

## 4. Why READINESS-A Exposed the Issue

Task `MVP-ARCH-001-R7-PIT-001C2-READINESS-A` evaluated five frozen candidate universes under Massive free-tier rate limits (`DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS = 12.1` s).

While the mathematical pacing analysis proved capacity feasibility:
* **Candidate B (Dow 30, 30 symbols):** Worst-case reference pacing floor of 11.90 min (fits a hypothetical 15-min budget).
* **Candidate C (Dow 30 + Sector ETFs, 45 symbols):** Worst-case reference pacing floor of 17.95 min (fits a hypothetical 20-min budget).

Operational readiness was forced to stop at:
```json
"operational_readiness_status": "blocked_pending_capture_status_compatibility_decision"
```

### The Root Conflict
1. **The ETF Earnings Compatibility Risk:**
   Candidate C contains 15 Sector SPDR ETFs (`SPY`, `XLK`, `XLF`, etc.) alongside 30 corporate equities. ETFs are pooled investment vehicles and generally do not report corporate quarterly earnings comparable to operating companies. Under current C1 contracts, when Yahoo yields no usable upcoming earnings date for an ETF, `capture_earnings_snapshot` records `ObservationStatus.UNAVAILABLE`. Because C1 requires all requested facts to be `KNOWN` for family success, any `UNAVAILABLE` observation prevents an all-known `SUCCEEDED` result (yielding `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`) and prevents an all-`SUCCEEDED` slot.
2. **The Equity All-Known Fragility:**
   Even for Candidate B (pure corporate equities), if Yahoo yields no usable upcoming earnings date for a requested equity, or if Massive produces an ambiguous ticker match, `known_n < requested_n`, preventing an all-known `SUCCEEDED` result.
3. **The Alerting Consequence:**
   If scheduled automation degraded on every single run containing ETFs or whenever Yahoo yielded no usable upcoming date, operational health monitoring would generate perpetual alerts, destroying operator signal and creating alert fatigue.

READINESS-A concluded that TradeX cannot responsibly activate any operational universe until the semantics of capture success and health are resolved.

---

## 5. Observation-State Inventory

To understand how individual observation outcomes aggregate into run and slot states, we must first separate **preflight validation failures** (which occur before capture-run or snapshot creation) from **per-symbol observation outcomes** (which execute inside the symbol lookup loop and persist snapshots to the database).

### Preflight Source Validation (Zero Snapshots Created)
Before creating a `PITCaptureRun` record or entering the symbol iteration loop, `capture_earnings_snapshot()` performs pure configuration and environment validation:
* **Unsupported Configured Earnings Source:**
  `_resolve_earnings_source(source, settings=settings)` validates the requested source against supported providers (currently only `"yahoo"`). If an unsupported source (e.g. `"schwab"`, `"alpaca"`) is configured or passed, it immediately raises `ProviderCapabilityError`.
  * **Capture Impact:** The exception aborts execution immediately before run creation.
  * **Database Impact:** Zero `PITCaptureRun` rows and zero `PITEarningsSnapshot` rows are created.
  * **Slot Impact:** The slot runner catches the error and marks the slot `FAILED`.

### Per-Symbol Observation Inventory
Inside the symbol lookup loop, every requested symbol produces exactly one persisted observation snapshot. An individual non-`KNOWN` observation only proves that an all-known family `SUCCEEDED` result is prevented; the final family status (`PARTIAL` vs `FAILED`) depends on all observations in the run.

* **Family aggregation rule:**
  $$\begin{cases}
  \text{known\_n} = \text{requested\_n} & \longrightarrow \text{SUCCEEDED} \\
  \text{known\_n} > 0 \text{ and } \text{known\_n} < \text{requested\_n} & \longrightarrow \text{PARTIAL} \\
  \text{known\_n} = 0 & \longrightarrow \text{FAILED}
  \end{cases}$$

The table below catalogs every currently reachable observation outcome across both capture families based strictly on repository code evidence:

| Family | Observation Status | Triggering Code Path | Error Category / Reason Evidence | Terminal Run Impact | Provider Call Occurred? | Fact Known? | Applicability Knowable? | Current Family Effect | Current Slot Effect |
|---|---|---|---|---|---|---|---|---|---|
| **Earnings** | `KNOWN` | `_fetch_from_yahoo` returns valid `date` | None (`error_category=None`) | Increments `known_n` | Yes | Yes (date stored) | Yes (positive proof) | Contributes toward family `SUCCEEDED` (requires all requested observations `KNOWN`) | Contributes toward an all-`SUCCEEDED` slot (requires both family runs to `SUCCEED`) |
| **Earnings** | `UNAVAILABLE` | `_fetch_from_yahoo` raises `EarningsDataUnavailableError` (no usable upcoming date) | `"EarningsDataUnavailableError"` | Increments `unavailable_n` | Yes | No | No (cannot prove why date is absent) | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Earnings** | `UNAVAILABLE` | `_fetch_from_yahoo` swallows provider exception; raises `EarningsDataUnavailableError` | `"EarningsDataUnavailableError"` | Increments `unavailable_n` | Yes | No | No (hidden technical failure) | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Earnings** | `UNAVAILABLE` | Per-symbol lookup raises `ProviderDataUnavailableError` | `"ProviderDataUnavailableError"` | Increments `unavailable_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Earnings** | `UNAVAILABLE` | Per-symbol injected/custom `earnings_lookup` raises `ProviderCapabilityError` inside loop | `"ProviderCapabilityError"` | Increments `unavailable_n` | Injected call | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Earnings** | `UNAVAILABLE` | Lookup returns `None` or non-date | `"EarningsDataUnavailableError"` | Increments `unavailable_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Earnings** | `ERROR` | Unexpected unhandled exception in per-symbol loop | Exception class name (e.g. `RuntimeError`) | Increments `error_n` | Attempted/Failed | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `KNOWN` | Active or inactive query returns exactly 1 exact match | None (`error_category=None`) | Increments `known_n` | Yes (1 or 2 calls) | Yes (record stored) | Yes (proven in master) | Contributes toward family `SUCCEEDED` (requires all requested observations `KNOWN`) | Contributes toward an all-`SUCCEEDED` slot (requires both family runs to `SUCCEED`) |
| **Reference** | `UNAVAILABLE` | Active and inactive queries both return 0 exact matches | `"MassiveDataUnavailableError"` | Increments `unavailable_n` | Yes (2 calls) | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `AMBIGUOUS` | Active or inactive query returns $>1$ exact matches | `"MassiveAmbiguousIdentityError"` | Increments `ambiguous_n` | Yes (1 or 2 calls) | No (candidates logged) | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Provider auth failure (HTTP 401) | `"MassiveAuthError"` | Increments `error_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Provider entitlement denied (HTTP 403) | `"MassiveEntitlementError"` | Increments `error_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Rate limit exceeded (HTTP 429) | `"MassiveRateLimitError"` | Increments `error_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Server error or timeout (HTTP 5xx, network drop) | `"MassiveTransientError"` | Increments `error_n` | Yes/Failed | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Malformed JSON or 404 response | `"MassiveResponseError"` | Increments `error_n` | Yes | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |
| **Reference** | `ERROR` | Unexpected unhandled exception in reference capture | Exception class name | Increments `error_n` | Attempted/Failed | No | No | Prevents family `SUCCEEDED`. Final family status is `PARTIAL` if $\ge 1$ other observation is `KNOWN`, otherwise `FAILED`. | Prevents an all-`SUCCEEDED` slot for this attempt. Exact slot/health state depends on both family run records and runner/health aggregation. |

---

## 6. Earnings-Path Inventory

Inspecting `tradex/earnings/calendar.py` (`_fetch_from_yahoo()`, lines 138–181) reveals the exact mechanism of data retrieval:

```python
def _fetch_from_yahoo(ticker: str) -> date:
    t = yf.Ticker(ticker)
    today = date.today()

    try:
        df = t.get_earnings_dates(limit=12)
        if isinstance(df, pd.DataFrame) and not df.empty:
            idx = pd.to_datetime(df.index, errors="coerce", utc=True).tz_convert(None)
            future = [d.date() for d in idx if pd.notna(d) and d.date() >= today]
            if future:
                return min(future)
    except Exception:  # noqa: BLE001
        pass

    try:
        cal = t.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
            future = [d for d in dates if ... >= today]
            if future:
                return ...
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            val = cal.iloc[0, 0]
            if ... >= today:
                return val.date()
    except Exception:  # noqa: BLE001
        pass

    raise EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")
```

### Critical Findings on the Yahoo Path
1. **Swallowed Exceptions in yfinance:**
   Both `t.get_earnings_dates()` and `t.calendar` wrap all calls in broad `except Exception: pass` blocks. If Yahoo returns an HTTP 500 Internal Server Error, an HTTP 429 Rate Limit, a socket timeout, an unparseable HTML error page, or a malformed JSON payload, the exception is silently discarded.
2. **Fallthrough to Generic Unavailable:**
   When exceptions are swallowed, execution falls through to `raise EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")`.
3. **Capture Mapping in `capture_earnings_snapshot`:**
   In `tradex/pit/earnings.py` (lines 263–272), `EarningsDataUnavailableError` is caught and mapped to `ObservationStatus.UNAVAILABLE` with `error_category="EarningsDataUnavailableError"`.
4. **Conclusion on Earnings Path:**
   A catastrophic Yahoo outage or unparseable response collapses into the exact same persisted status (`ObservationStatus.UNAVAILABLE`), error category (`"EarningsDataUnavailableError"`), and fact payload (`{"error_category":"EarningsDataUnavailableError","error_message":"Upcoming earnings date unavailable for {sym}","next_earnings_date":null}`) as a symbol for which Yahoo legitimately had no future date on file.

---

## 7. Reference-Path Inventory

Inspecting `tradex/pit/massive_reference.py` (`MassiveReferenceClient`) and `tradex/pit/reference.py` (`capture_reference_snapshot`) reveals a much more structured error taxonomy:

1. **Two-Stage Lookup:**
   * Stage 1: Active query (`/v3/reference/tickers?ticker={sym}&date={date}&active=true`).
   * If exactly 1 match $\rightarrow$ `ReferenceObservationStatus.KNOWN`.
   * If $>1$ matches $\rightarrow$ `ReferenceObservationStatus.AMBIGUOUS` (all candidate records serialized into `fact_json`).
   * If 0 matches $\rightarrow$ Fall back to Stage 2: Inactive query (`active=false`).
   * If Stage 2 returns 1 match $\rightarrow$ `ReferenceObservationStatus.KNOWN` (delisted/inactive).
   * If Stage 2 returns $>1$ matches $\rightarrow$ `ReferenceObservationStatus.AMBIGUOUS`.
   * If Stage 2 returns 0 matches $\rightarrow$ `ReferenceObservationStatus.UNAVAILABLE` (`"MassiveDataUnavailableError"`).
2. **Typed Transport and API Error Classification:**
   * HTTP 401 $\rightarrow$ `MassiveAuthError` $\rightarrow$ `ReferenceObservationStatus.ERROR`.
   * HTTP 403 $\rightarrow$ `MassiveEntitlementError` $\rightarrow$ `ReferenceObservationStatus.ERROR`.
   * HTTP 429 $\rightarrow$ `MassiveRateLimitError` $\rightarrow$ `ReferenceObservationStatus.ERROR`.
   * HTTP 5xx / Network $\rightarrow$ `MassiveTransientError` $\rightarrow$ `ReferenceObservationStatus.ERROR`.
   * HTTP 404 / Malformed $\rightarrow$ `MassiveResponseError` $\rightarrow$ `ReferenceObservationStatus.ERROR`.
3. **Request ID Tracking:**
   Every request extracts `x-request-id` headers and body request IDs, persisting them into `provider_request_ids_json` on every snapshot (even on errors).

### Reference Limitations
While reference capture clearly distinguishes technical/provider errors (`ERROR`) from empty results (`UNAVAILABLE`) and ambiguity (`AMBIGUOUS`), it still cannot determine domain applicability. An invalid ticker string and a legitimate non-existent instrument both produce `UNAVAILABLE`.

---

## 8. Current Provenance Limitations

Comparing the two capture implementations establishes the repository's current provenance constraints:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Schema v7 Provenance Boundary                         │
├────────────────────────────────┬─────────────────────────────────────────────┤
│ Dimension                      │ Current Repository Capability               │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ Reference Provider Error       │ High: Typed exception categories, HTTP      │
│ Classification                 │ codes, and request IDs persisted.           │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ Reference Ambiguity            │ High: Preserves all candidate records in    │
│ Identification                 │ fact_json for deterministic audit.          │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ Reference Absence              │ Moderate: Proves active + inactive queries  │
│ Verification                   │ yielded 0 results, but not why.             │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ Earnings Technical vs.         │ None: Swallowed exceptions collapse         │
│ Domain Absence Distinction     │ outages and empty results into UNAVAILABLE. │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ Structural Instrument          │ None: No persisted field or contract        │
│ Applicability                  │ distinguishes ETF from equity earnings.     │
└────────────────────────────────┴─────────────────────────────────────────────┘
```

> **Direct Answer to Core Technical Question:**
> **Schema v7 cannot reliably distinguish a provider/lookup failure that was swallowed upstream from a genuine no-usable-upcoming-date outcome.**
> Old `UNAVAILABLE` rows cannot safely be reinterpreted as successful structural absence, nor does historical evidence prove `ETF -> not_applicable`.

---

## 9. Operational Health vs. Evidence Completeness

The core design principle evaluated is whether operational health and research evidence completeness should be separate dimensions.

### The Conceptual Distinction
* **Operational Execution Health:** Measures whether the scheduled data-acquisition machine functioned correctly:
  * Was the slot due?
  * Did the runner start on schedule?
  * Did requests reach the provider?
  * Did the transport layer succeed without 401/403/429/5xx errors?
  * Did parsing complete without unhandled crashes?
  * Were observations durably written to SQLite?
  * Were universe hashes consistent across families?
* **Research Evidence Completeness:** Measures whether downstream quant research or production trading models have the data they require:
  * Is the upcoming earnings date known?
  * Is the reference master record unambiguous and complete?
  * Are required fields populated?
  * Does the missing fact prevent model scoring?

### Why Separating Them Is Desirable
Equating these dimensions (as C1 currently does) creates false coupling:
* If a domain fact is missing (e.g. Yahoo yields no usable upcoming earnings date for an equity), the operational capture pipeline is declared `DEGRADED`. The scheduler alerts the engineer to fix a system that performed its job flawlessly.
* Conversely, if an operational status is relaxed without fine-grained provenance, technical provider outages are masked as "healthy absence."

### The Blocker to Immediate Separation
Operational health cannot treat all `UNAVAILABLE` observations as "healthy capture execution" today because Schema v7 earnings capture swallows provider errors into `UNAVAILABLE`. Doing so would cause a total Yahoo network failure to be reported as an operationally `HEALTHY` slot.

---

## 10. Applicability Analysis

A central issue is whether TradeX can distinguish when a fact conceptually applies to an instrument (e.g. operating-company earnings for corporate equities vs. pooled investment ETFs).

### Strict Design Constraint
> **No Hard-Coded Ticker Lists:** TradeX must NOT implement logic equivalent to `if symbol in ETF_LIST: unavailable_is_success = True`. Such static lists are brittle, un-versioned, non-point-in-time, and fail to scale.

### Evaluation of Applicability Mechanisms

| Mechanism | Description | Point-in-Time Correctness | Circularity / Ordering | Lookahead Risk | Versioning & Auditability | Operational Complexity | Schema v7 Historical Classification |
|---|---|---|---|---|---|---|---|
| **A. Explicit Manifest Eligibility / Metadata** | Manifest specifies per-symbol family eligibility (e.g. `symbols: [{"ticker": "SPY", "families": ["reference"]}]`). | High (explicitly declared per manifest version) | None (manifest is static input to runner) | None (frozen before run) | High (manifest_hash captures exact rules) | Low (pure static loader check) | Not supported (historical v7 manifests lack metadata) |
| **B. Prior PIT Reference Evidence** | Use security type (`provider_type_code`) from the most recent prior valid PIT reference run. | High (strictly uses past point-in-time audit evidence) | Moderate (cold-start problem on slot 1; cross-family temporal coupling) | None if strictly prior to current slot | High (traceable to specific capture_run_id) | High (requires DB lookup before capture) | Supported if historical reference runs exist |
| **C. Additive Reason Taxonomy Only** | Do not declare applicability; record provider-returned reasons; evaluate downstream in research layer. | High (truthfully records provider evidence) | None | None | High | Lowest (keeps capture layer simple) | Partially supported (cannot disambiguate old earnings) |
| **D. Separate Static Instrument Contract** | Dedicated versioned JSON file defining security master properties across symbols. | High (versioned file contract) | Low | None if dated | High | Moderate (requires managing two manifest files) | Not supported historically |
| **E. Retain Unresolved Applicability** | Treat applicability as unknown until richer provider evidence exists; accept strict or degraded semantics. | Complete (makes zero unproven assumptions) | None | None | Absolute audit integrity | None | Supported (reflects reality of v7 data) |

### Analysis of Findings
* **Mechanism A (Manifest Declaration):** Offers the cleanest operational design for forward-looking scheduled capture, completely avoiding runtime database lookups and cross-family slot ordering dependencies.
* **Mechanism B (Prior Reference):** Faces a severe operational ordering problem: in C1, earnings capture runs *before* reference capture in the same slot. Using prior-day reference data introduces cross-slot state dependencies and fails on initial deployment (cold start).
* **Mechanism C (Additive Reason Taxonomy):** Is necessary regardless of which applicability mechanism is chosen, because operational health must distinguish provider errors from domain absence.

---

## 11. Option 1 — Retain Strict All-Known Semantics

### Description
Retain current C1 rules: family `SUCCEEDED` requires every requested observation to be `KNOWN`. Slot `HEALTHY` requires both families to be `SUCCEEDED`.

### Benefits
* Strongly fail-closed: impossible to accidentally trade on missing or incomplete data.
* Simple and auditable: zero ambiguity about what `HEALTHY` means.
* Zero schema or code changes required.

### Risks & Limitations
* **Elevated Operational Noise:** Strict all-known semantics can make operational health noisy whenever any requested symbol lacks a usable upcoming earnings date or reference fact, regardless of whether the cause is ordinary domain absence, provider incompleteness, or technical failure.
* **Elevated/Structural Risk for ETFs:** For universes containing ETFs (Candidates A, C, E), there is an elevated structural risk of routine slot degradation whenever Yahoo returns no earnings dates for ETF symbols.
* **Alert Fatigue:** Operators will learn to ignore `DEGRADED` notifications, rendering alerts ineffective for detecting genuine infrastructure outages.

---

## 12. Option 2 — Separate Operational Health From Evidence Completeness

### Description
Maintain two independent, orthogonal status dimensions:
1. `capture_execution_health`: `HEALTHY` | `DEGRADED` | `FAILED`
2. `evidence_completeness`: `COMPLETE` | `PARTIAL` | `SPARSE`

An observation where a provider was successfully queried without error but yielded no usable upcoming date counts as **healthy execution** (100% execution fidelity), but results in **partial evidence completeness** (e.g. 95% data completeness).

### Benefits
* Truthful operations: OS scheduler alerts trigger only when the capture machinery breaks (HTTP 5xx, timeouts, 429 rate limits, unhandled exceptions, database locked).
* Truthful research: Downstream models and research pipelines filter explicitly on evidence completeness thresholds suitable for each strategy.
* Scales across universe sizes without arbitrary distortion.

### Risks & Blockers
* **The Provenance Blocker:** As proven in Section 6, current Schema v7 earnings code swallows provider exceptions into `ObservationStatus.UNAVAILABLE`. Option 2 **cannot be safely implemented** until `tradex/earnings/calendar.py` is hardened to distinguish technical failures (`ERROR`) from legitimate absence.

---

## 13. Option 3 — Applicability-Aware Semantics

### Description
Enrich observation outcomes to distinguish:
* `KNOWN`: domain fact obtained.
* `NOT_APPLICABLE`: domain fact does not conceptually apply to this instrument class.
* `UNAVAILABLE`: domain fact applies, but provider yields no usable upcoming date.
* `AMBIGUOUS`: provider returned conflicting/multiple records.
* `ERROR`: provider transport, authentication, rate limit, or parsing failure.

Under this model, `NOT_APPLICABLE` counts as both healthy execution and complete expected evidence.

### Benefits
* Eliminates structural distortion for multi-asset universes (equities + ETFs).
* Accurately models the financial reality of different instrument types.

### Risks & Limitations
* Requires a principled, deterministic mechanism to establish applicability point-in-time (Section 10).
* Requires evolving SQLite database schema constraints (Schema v8), as Schema v7 table constraints reject statuses outside `('known', 'unavailable', 'error')` and `('known', 'unavailable', 'ambiguous', 'error')`.

---

## 14. Option 4 — Threshold-Based Family Success

### Description
Define family success via an empirical percentage threshold, such as:
$$\frac{\text{usable\_observations}}{\text{requested\_n}} \ge X\% \implies \text{family SUCCEEDED}$$

### Analysis & Rejection
Antigravity explicitly evaluates and **rejects** Option 4 based on the following failure modes:
1. **Arbitrary Threshold Problem:** Any cutoff (e.g. 90%, 95%) is an ungrounded heuristic with no mathematical or trading justification.
2. **Masking Provider Degradation:** A provider experiencing partial outages on 5% of a universe would be masked as `SUCCEEDED`.
3. **Severe Universe-Size Distortion:**
   * In Candidate B (30 symbols), a 95% threshold allows 1 missing symbol ($1/30 = 3.3\%$).
   * In Candidate C (45 symbols), 15 missing ETF earnings represent 33.3% of the universe, causing failure unless the threshold is set to an absurdly permissive 65%.
   * In Candidate D (100 symbols), 5 completely failed symbols would be treated as `SUCCEEDED`.
4. **Targeted Failure Risk:** If the 1 missing stock in a 30-symbol basket happens to be the primary focus of an active trade, declaring the run "successful" compromises research integrity.

Option 4 conflates operational health with evidence completeness and masks failures. It is not recommended.

---

## 15. Option 5 — Require Empirical Provider Study Before Semantics Change

### Description
Perform a live-provider compatibility study on target symbols before adopting a final status policy.

### Analysis of the Two Decision Gates
It is essential to separate two distinct questions:
1. **Gate A: Architectural Concept Gate (Can we decide the architecture now?)**
   **YES.** Repository code inspection and contract analysis provide 100% conclusive evidence that operational health and evidence completeness are conceptually separate, and that current Schema v7 swallows Yahoo exceptions. No live provider calls are required to make this architectural decision.
2. **Gate B: Implementation & Mapping Gate (Can we implement the new policy now?)**
   **NO.** Before implementing specific provider error mappings and activating operational candidate universes (Candidates B or C), TradeX must verify actual provider behavior under live conditions.

### Recommended Scope of Empirical Validation
When authorized by Gary, the empirical study should be:
* **Scope:** A separately Gary-authorized, bounded live-provider compatibility study using the minimum necessary provider access and credentials, with no credentials committed or exposed.
* **Target Symbols:** Minimal representative subsets (e.g. 5 Dow equities + 3 Sector ETFs).
* **Objective:** Record TradeX-observable behavior (returned dates, empty/no-usable results, exception classes visible to TradeX, timing, and sanitized returned structures where available) from Yahoo and Massive for both equities and ETFs, proving empirically how no-usable-upcoming-date outcomes, ETF queries, and active/inactive ticker queries resolve in practice.
* **Boundary:** Zero trading decisions, zero database writes, zero model tuning.

---

## 16. Comparative Decision Matrix

| Evaluation Dimension | Option 1: Strict All-Known | Option 2: Separate Health/Completeness | Option 3: Applicability-Aware | Option 4: Threshold-Based | Option 5: Empirical Study First |
|---|---|---|---|---|---|
| **Truthful Operational Health** | Partially supported (noisy) | **Supported** | **Supported** | Not supported (masks failures) | **Supported** |
| **Research Completeness Fidelity** | **Supported** (fail-closed) | **Supported** | **Supported** | Not supported (arbitrary loss) | **Supported** |
| **Provider Outage Visibility** | **Supported** | **Supported** (with hardening) | **Supported** (with hardening) | Not supported (masked below threshold) | **Supported** |
| **Structural / ETF Fact Handling** | Not supported (elevated risk) | Partially supported | **Supported** | Partially supported (crude) | **Supported** |
| **Backward Compatibility** | **Supported** (current code) | Supported prospectively | Supported prospectively | Partially supported | **Supported** |
| **Schema v7 Feasibility** | **Supported** | Partially supported | Not supported (requires v8) | Supported | **Supported** |
| **Historical Reinterpretation Risk** | None | High if retroactively applied | High if retroactively applied | Moderate | None |
| **Implementation Complexity** | Lowest (zero changes) | Moderate | Moderate to High | Low | Low (study only) |
| **Alert Usefulness** | Not supported (high noise) | **Supported** (high signal) | **Supported** (high signal) | Partially supported | **Supported** |
| **Deterministic & Auditable** | **Supported** | **Supported** | **Supported** | Not supported | **Supported** |
| **Risk of Masking Failures** | None | High without hardening; None with hardening | None with hardening | **High** | None |
| **Empirical Evidence Prerequisite** | Not required | Required before implementation | Required before implementation | Not required | **Required by definition** |

---

## 17. Recommended Design Direction

Antigravity recommends that TradeX adopt **Option 2 (Separate Operational Health from Evidence Completeness)** combined with **Option 3 (Applicability-Aware Semantics via Manifest Declaration)**, executed through a **strict phased sequence**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Phased Status Semantics Implementation                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 1: Architecture Decision (THIS TASK)                                 │
│  • Gary approves orthogonal health vs. completeness model.                  │
│  • Production semantics remain unchanged (C1 strict all-known).             │
│  • All operational authorizations remain FALSE.                             │
│                                                                             │
│  Phase 2: Provider Hardening & Provenance Slice (PREREQUISITE)              │
│  • Eliminate swallowed exceptions in tradex/earnings/calendar.py.          │
│  • Map HTTP/network/parse errors explicitly to ProviderTransientError /     │
│    ProviderResponseError, producing ObservationStatus.ERROR.                │
│  • Define manifest contract v2 supporting family-applicability metadata.    │
│  • Determine Schema v8 migration requirements.                              │
│                                                                             │
│  Phase 3: Bounded Live Provider Compatibility Study (VERIFICATION)         │
│  • Execute separately Gary-authorized empirical probe on minimal symbols.   │
│  • Verify real-world return distributions for Yahoo and Massive.            │
│                                                                             │
│  Phase 4: C1 Status Refinement Implementation & Universe Activation         │
│  • Implement derived two-dimensional health/completeness inspector.         │
│  • Activate selected universe (Candidate C or Candidate B).                 │
│  • Authorize C2 scheduler deployment.                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Answers to Required Recommendation Questions
1. **What should operational health mean?**
   Operational health means that scheduled data-acquisition executed reliably: providers were contacted, no unhandled transport/auth/rate-limit/parse errors occurred, evidence was durably persisted, and slot timing and universe constraints were met.
2. **What should evidence completeness mean?**
   Evidence completeness means that downstream research models have all required domain facts for the requested universe.
3. **Are current persisted statuses sufficient?**
   **No.** Current Schema v7 earnings observations collapse swallowed provider errors into `UNAVAILABLE`.
4. **What additional information is necessary?**
   Explicit error categories distinguishing technical failure from domain absence, and explicit instrument applicability metadata.
5. **Can implementation safely be additive?**
   Yes, prospectively. Historical records remain immutable.
6. **Is Schema v8 likely required?**
   **Likely required.** SQLite table CHECK constraints on `observation_status` and `status` in Schema v7 reject any new enum values at the database level.
7. **Is live provider research required before implementation?**
   **Yes.** A bounded empirical study is required before implementing specific error mappings, but is **not** required to decide the architectural direction.
8. **Should universe selection remain blocked?**
   **Yes.** Universe selection must remain blocked until the status contract is hardened.

---

## 18. What Evidence Supports the Recommendation

1. **Repository Source Evidence:**
   * `tradex/earnings/calendar.py` (lines 156, 175) explicitly proves broad `except Exception: pass` exception swallowing.
   * `tradex/pit/earnings.py` (lines 263–272) explicitly proves `EarningsDataUnavailableError` is caught and mapped to `ObservationStatus.UNAVAILABLE`.
   * `tradex/pit/massive_reference.py` proves that reference capture already successfully distinguishes `ERROR`, `UNAVAILABLE`, and `AMBIGUOUS`.
   * `tradex/tracker/store.py` (lines 755, 771, 817, 833) proves that SQLite tables have hardcoded `CHECK` constraints on status enums.
2. **Mathematical Capacity Evidence:**
   * READINESS-A proved that Candidate C (45 symbols) and Candidate B (30 symbols) comfortably satisfy free-tier pacing budgets (17.95 min and 11.90 min worst-case). Pacing capacity is not the blocker; status semantics are.

---

## 19. What Remains Uncertain

1. **Live Yahoo ETF Response Characteristics:** While ETFs generally lack operating-company earnings dates, exact live Yahoo behavior across all 15 Sector ETFs has not been measured under production code.
2. **Massive Inactive Fallback Frequency:** The exact rate at which live symbols trigger the secondary inactive query in production remains unmeasured.
3. **Provider Taxonomy Drift:** Whether Yahoo or Massive alter their JSON keys or error formats over time without bumping API versions.

---

## 20. Schema-v7 / Historical Compatibility

> [!CAUTION]
> **Strict Immutability Rule:** Historical PIT records in `signals.db` must NEVER be modified, backfilled, or retroactively reinterpreted.

1. **Can existing v7 observations be reclassified?**
   **No.** Historical earnings `UNAVAILABLE` rows cannot prove whether they were caused by a swallowed network failure, an unannounced date, an absent record, or an ETF.
2. **Which states can be derived safely?**
   * `ObservationStatus.KNOWN` is safe and authoritative.
   * `ReferenceObservationStatus.KNOWN`, `AMBIGUOUS`, and `ERROR` are safe and authoritative.
3. **Which cannot be inferred retrospectively?**
   Historical `ObservationStatus.UNAVAILABLE` in earnings cannot be reclassified as `not_applicable` or `healthy_absence`.
4. **Is Schema v8 required?**
   **Likely required** if new status codes (`not_applicable`) or run states (`healthy_incomplete`) are persisted to SQLite tables due to existing `CHECK` constraints.
5. **Effective Date Boundary:**
   Any future status semantics must take effect prospectively at a defined contract version boundary (`contract_version = 2`) and effective date.

---

## 21. Future Status and Reason Taxonomy

When Phase 2 hardening is authorized, the conceptual observation taxonomy should evolve to:

```
Observation Outcome
├── KNOWN (Fact acquired and validated)
├── NOT_APPLICABLE (Fact conceptually inapplicable to instrument class)
├── UNAVAILABLE (Fact applicable, provider queried successfully, no fact exists)
│     ├── NOT_ANNOUNCED (Conceptual / requires authoritative source; not derivable from current Schema v7 evidence)
│     └── NOT_FOUND (Provider security master has no record; supported in reference)
├── AMBIGUOUS (Provider returned conflicting candidate matches)
└── ERROR (Technical capture failure)
      ├── TRANSPORT_FAILURE (HTTP 5xx, timeout, network disconnect)
      ├── AUTH_FAILURE (HTTP 401, missing credentials)
      ├── RATE_LIMIT_EXCEEDED (HTTP 429)
      ├── PARSE_FAILURE (Malformed JSON/HTML, schema drift)
      └── INTERNAL_ERROR (Unexpected runtime exception)
```

### Distinction Between Repository-Supported and Proposed Future Categories

1. **Repository-Supported Technical Categories:**
   Categories demonstrably supported by current TradeX reference/provider integration code:
   * `AUTH_FAILURE`: Supported in reference adapter via `MassiveAuthError` (HTTP 401).
   * `ENTITLEMENT_DENIED`: Supported in reference adapter via `MassiveEntitlementError` (HTTP 403).
   * `RATE_LIMIT_EXCEEDED`: Supported in reference adapter via `MassiveRateLimitError` (HTTP 429).
   * `TRANSPORT_FAILURE`: Supported in reference adapter via `MassiveTransientError` (HTTP 5xx, network drops, timeouts).
   * `PARSE_FAILURE`: Supported in reference adapter via `MassiveResponseError` (malformed JSON / unexpected schema).
   * `NOT_FOUND` (Reference): Supported in reference adapter when both active and inactive ticker queries return 0 matches (`MassiveDataUnavailableError`).
   * `AMBIGUOUS`: Supported in reference adapter when queries return $>1$ candidate matches (`MassiveAmbiguousIdentityError`).
   * `INTERNAL_ERROR`: Supported across both capture families via caught unhandled runtime exceptions mapped to `ERROR`.

2. **Proposed Future Categories (Conceptual / Domain-Dependent):**
   Categories that require provider-contract evidence, domain-source evidence, or new explicit manifest/instrument metadata:
   * `NOT_APPLICABLE`: Conceptual category. Requires explicit instrument metadata or manifest-level eligibility declaration (`eligibility: {earnings: false, reference: true}`). Current providers and tables do not persist or verify asset-class applicability.
   * `NOT_ANNOUNCED`: Conceptual category. Requires an authoritative provider or domain source that explicitly distinguishes "issuer has not yet scheduled an earnings announcement" from lookup failure, data omission, or parsing failure. **This is not derivable from current Schema v7 evidence or Yahoo absence.**
   * `NOT_FOUND` (Earnings): Conceptual category for earnings. Current Yahoo code cannot distinguish a ticker unknown to Yahoo from a ticker known to Yahoo with no upcoming date.

---

## 22. Health and Alert Semantics

Future operational monitoring in C2 should distinguish alert severities:

1. **Operational Error (High Severity — Immediate Pager Alert):**
   * Slot failed to start or did not run.
   * Runner crashed with unhandled internal error.
   * Universe hash conflict detected (drift guard).
   * Transport/auth/rate-limit errors occurred on $\ge 1$ symbols.
2. **Operational Warning (Medium Severity — Operator Ticket):**
   * Pacing delay exceeded scheduled budget.
   * Retries were consumed during provider calls.
3. **Research Completeness Warning (Low Severity — Research Log / Daily Summary):**
   * Scheduled capture succeeded, but domain completeness fell below research threshold.
   * Reference record resolved to `AMBIGUOUS`.
   * Yahoo yields no usable upcoming earnings date for an equity.
4. **Informational (No Alert):**
   * Slot not due (weekend, holiday, pre-slot).
   * Fact validly not applicable (ETF earnings).

---

## 23. CLI and Exit-Code Implications

Current C1 exit codes:
* `run-slot`: 0 = succeeded/not_due; 2 = degraded; 1 = failed.
* `health`: 0 = healthy/not_due; 2 = degraded/missing/incomplete; 1 = universe_conflict/error.

Under the future two-dimensional model:
* **Exit code 0:** Operational capture pipeline succeeded completely (`capture_execution_health == HEALTHY`), regardless of whether some domain facts yielded no upcoming date or were inapplicable.
* **Exit code 2:** Operational degradation (e.g. transient retries exhausted, partial provider failure).
* **Exit code 1:** Operational failure (drift conflict, auth failure, fatal crash).
* Research completeness metrics should be surfaced in JSON stdout (`"evidence_completeness": "partial"`, `"completeness_pct": 93.3`) without corrupting process exit codes.

---

## 24. Candidate B and Candidate C Implications

Tying the status decision back to `MVP-ARCH-001-R7-PIT-001C2-READINESS-A`:

### Candidate B (Dow 30, 30 Equities)
* **Under Current C1:** Operational compatibility is `unresolved`. Any single requested equity for which Yahoo yields no usable upcoming earnings date, or where Massive produces an ambiguous match, prevents family `SUCCEEDED` and degrades the operational slot.
* **Under Recommended Model:** Operational compatibility is **conditionally resolvable under the recommended architecture, but remains unresolved until the selected status policy, provenance requirements, and applicability/domain-absence rules are approved and implemented.** Exception hardening will separate technical transport/auth/rate-limit failures from clean empty results, but establishing that an equity's absence is benign operational behavior requires Gary's policy approval and defined domain-absence rules.

### Candidate C (Dow 30 + Sector ETFs, 45 Symbols)
* **Under Current C1:** Operational compatibility is `unresolved` with elevated structural degradation risk due to 15 ETF symbols lacking corporate earnings dates.
* **Under Recommended Model:** Operational compatibility is **conditionally resolvable under the recommended architecture, but remains unresolved until the selected status policy, provenance requirements, and applicability/domain-absence rules are approved and implemented.** Resolving Candidate C requires not only provider exception hardening but also an approved applicability mechanism (such as manifest-level eligibility declarations) to truthfully classify ETF earnings as non-applicable rather than operational capture failures.

---

## 25. Implementation Boundary and Sequencing

Future implementation must be sliced into bounded PRs:

1. **PR 1 (Contract & Hardening):**
   * Harden `tradex/earnings/calendar.py` (stop swallowing exceptions; raise typed errors).
   * Add typed error categories to `PITEarningsSnapshot`.
   * Evaluate and introduce Schema v8 if persisting new enums.
2. **PR 2 (Operational Health Read Model):**
   * Update `tradex/pit/ops.py` to derive two-dimensional health.
   * Update CLI subcommands and JSON outputs.
3. **PR 3 (Universe Activation & C2):**
   * Select operational universe (Candidate C or B).
   * Create production manifest with real `effective_from` date.
   * Install and authorize OS scheduler.

---

## 26. Empirical-Study Specification

If Gary authorizes a live-provider study prior to Phase 2/3 implementation, it should conform to this specification:
* **Authorization:** Bounded, read-only live probe authorized by Gary.
* **Credentials:** Read from local environment (`.env`); never committed or printed.
* **Symbol Set:** Exactly 8 symbols:
  * 5 Corporate Equities: `AAPL`, `MSFT`, `JNJ`, `XOM`, `JPM` (Dow 30 sample across sectors).
  * 3 ETFs: `SPY` (broad market), `XLK` (tech sector), `XLF` (financial sector).
* **Endpoints Probed:**
  * Yahoo: `get_earnings_dates()`, `.calendar` (invoked via `tradex/earnings/calendar.py` or direct production-equivalent calls).
  * Massive: `/v3/reference/tickers` (active=true and active=false).
* **Evidence Hierarchy & Observability:**
  1. **Guaranteed Observable Behavior (Production Path):**
     * Returned dates and datetimes.
     * Empty / no-usable upcoming date results.
     * Specific exception classes visible to TradeX (e.g. `EarningsDataUnavailableError`, `MassiveRateLimitError`, `MassiveTransientError`, etc.).
     * Call durations and pacing.
     * Sanitized return structures and dataframes where exposed by the integration layer.
  2. **Raw Transport Evidence (Conditional / Out-of-Band):**
     * Raw HTTP status codes (e.g. 200, 401, 404, 429, 500) and response bodies are directly observable for Massive via the existing HTTP adapter.
     * For Yahoo (`yfinance`), raw HTTP status codes and response bodies must NOT be assumed to be exposed through the standard library interface; raw transport evidence should only be collected if a separately reviewed study implementation can safely instrument it without modifying production behavior, exposing credentials, violating provider boundaries, or bypassing the real integration path being evaluated. The study should test TradeX-visible behavior first.
* **Metrics Recorded:** Observable dates, failure classifications, exception types, timing, and (for Massive) raw HTTP status and request IDs.
* **Artifact:** Versioned, sanitized research report in `docs/research/`.

---

## 27. Risks and Failure Modes

1. **Risk of Masking Failures:** Separating health without hardening Yahoo exception handling would report provider outages as healthy absence. (Mitigated by mandatory Phase 2 hardening).
2. **Lookahead Risk:** Attempting to determine applicability by looking at same-day reference data creates ordering bugs; using future data creates lookahead bias. (Mitigated by manifest-level static declarations).
3. **Alert Fatigue:** Failing to fix C1 strict semantics leads to routine `DEGRADED` slots and ignored alerts. (Mitigated by Option 2 separation).
4. **History Rewriting:** Attempting to "fix" past Schema v7 audit logs corrupts audit integrity. (Mitigated by strict immutability rule).

---

## 28. Gary Decision and Approval Record

Gary Yang formally approved the recommended architectural direction on **2026-09-09**:

> **Approved Policy:** `option_2_plus_3` — **Option 2 (Separate Operational Health From Evidence Completeness) + Option 3 (Applicability-Aware Semantics)**

### Approval Record Details
* **Approved By:** Gary Yang
* **Approved On:** 2026-09-09
* **Approval Scope:** Architecture direction only. Does **not** authorize production status-semantics implementation, Schema v8 migration, provider exception hardening, live provider testing, active-universe selection, C2 implementation, scheduler installation, or any trading behavior change.
* **Approval Source:** TradeX ChatGPT workflow on 2026-09-09 following review and merge of PR #74 (`4680a13c140b8d93ff099b43cb818540f57a19c0`). Gary Yang explicitly gave the architecture decision:
  > `Yea, I approve option 2 and 3. If there are certain data we can't get, that shouldn't be a failure. We work with whatever data we have.`
  *Interpretation Boundary:* "Work with whatever data we have" confirms Option 2's core principle that missing observations do not automatically make capture execution an operational failure; it does **not** authorize fabricating or imputing missing facts, treating missing mandatory evidence as present, or relaxing future strategy-specific actionability gates.
* **Machine-Readable Audit Records:**
  * `docs/product/artifacts/r7-pit-status-dec-001/decision.json` (`selected_status_policy: "option_2_plus_3"`, `status: "gary_approved"`)
  * `docs/product/artifacts/r7-pit-status-dec-001/approval.json`

### Architecture Options Disposition
* **Option 1 (Retain Strict All-Known Semantics):** **Not selected as future architecture.** Current production behavior nevertheless remains strict all-known Schema v7 until separately authorized implementation changes occur. (Do not confuse "not selected for future architecture" with "removed from current production.")
* **Option 2 (Separate Operational Health From Evidence Completeness):** **Selected / Gary-approved as a conceptual architecture component.** Operational execution health (healthy / degraded / failed) and research evidence completeness (complete / partial / sparse) are separate, orthogonal dimensions.
* **Option 3 (Applicability-Aware Semantics):** **Selected / Gary-approved as a conceptual architecture component.** Point-in-time observation semantics must distinguish applicable, unavailable, ambiguous, technically failed, and genuinely not-applicable observations. Applicability must be determined via a principled, point-in-time, versioned, auditable mechanism (manifest/instrument eligibility metadata), **not** hard-coded ticker lists.
* **Option 4 (Threshold-Based Family Success):** **Rejected.** Percentage thresholds (e.g. 90%, 95%) are rejected.
* **Option 5 (Empirical Provider Study First):** **Not selected as the architecture decision policy.** However, bounded live provider evidence remains required before implementation/mapping and operational activation, subject to separate Gary authorization.

### Critical Boundary: Approved Future Architecture vs. Current Production Contract
* **Current Production Behavior:** Schema remains v7; capture contract remains v1; strict all-known family success remains the active production behavior. Zero production code (`tradex/`) changes are introduced by this approval.
* **Approved Future Architecture:** Option 2 + Option 3 conceptual separation and applicability-aware semantics are established as the target architectural direction.
* **Historical Evidence Safeguard:** Historical Schema v7 `UNAVAILABLE` observations in `signals.db` cannot safely be reinterpreted retroactively as successful observations of structural absence or provider success.
* **Next Prerequisites:** Production implementation requires separate future Gary authorizations for Phase 2 (provider exception hardening & explicit provenance taxonomy) and Phase 3 (bounded live-provider compatibility study) before Phase 4 (implementation & universe activation).

---

## 29. Non-Authorization Statement

This document records Gary Yang's architectural-direction approval.
* **`selected_status_policy` is `option_2_plus_3` (architecture direction only).**
* **NO production PIT behavior changes are authorized (`tradex/`).**
* **NO database schema migration is authorized (Schema remains v7).**
* **NO provider study is authorized or executed (`provider_study_authorized = false`).**
* **NO operational universe is selected (`selected_universe = null`, `active_universe_authorized = false`).**
* **NO C2 scheduler installation is authorized (`scheduler_authorized = false`).**
* **`production_status_semantics_change_authorized` remains `false`.**
* **`c2_implementation_authorized` remains `false`.**
* **`APPROVED_PRODUCTION_STRATEGIES` remains strictly `()`.**
* **LONG-002C remains paused.**
* **R8 remains unauthorized.**
* **DAYTRADE-001 remains deferred.**
