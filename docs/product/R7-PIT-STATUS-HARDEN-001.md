# MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001: R7 PIT Earnings Provider / Provenance Hardening

> **Task ID:** `MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001`
>
> **Classification:** Production-facing reliability and data-provenance hardening without trading-logic changes
>
> **Affects Trading Behavior:** **No**
>
> **Approved By:** Gary Yang (2026-09-09)
>
> **Base SHA:** `ae2b4603a6de7bf2663a563431118a51b8f840d7`
>
> **Branch:** `antigravity/mvp-arch-001-r7-pit-status-harden-001`
>
> **Author:** Antigravity

---

## 1. Executive Summary & Purpose

This bounded engineering assignment resolves the central provenance limitation in Schema v7 point-in-time (PIT) earnings capture identified during the `R7-PIT-STATUS-DEC-001` architecture evaluation:

> **Central Provenance Problem:** Prior to this change, `tradex/earnings/calendar.py` caught all exceptions during Yahoo/yfinance earnings retrieval (`get_earnings_dates()` and `.calendar`) and re-raised them as a generic `EarningsDataUnavailableError`. Upstream PIT capture (`tradex/pit/earnings.py`) caught `EarningsDataUnavailableError` and recorded `ObservationStatus.UNAVAILABLE` with `error_category=type(exc).__name__` (normally `"EarningsDataUnavailableError"`) and `error_message=f"Upcoming earnings date unavailable for {sym}"`. Consequently, real provider technical failures (network outages, rate limits, HTTP 429/500 errors, response corruption, unexpected schema changes) were swallowed and conflated with clean provider execution where no usable upcoming earnings date was returned.

This change prospectively hardens the provider and PIT capture layers so that:
1. **Technical failures are typed and separated** from clean no-usable-upcoming-date results via explicit single-inheritance exceptions (`EarningsProviderLookupError` and `EarningsProviderResponseError`).
2. **Outcome precedence is deterministic** across the two Yahoo retrieval strategies.
3. **PIT observations record `ObservationStatus.ERROR`** for technical/malformed failures while preserving `ObservationStatus.UNAVAILABLE` for clean no-usable-upcoming-date results.
4. **All persisted messages and payloads remain strictly sanitized**, preventing secret leakage or path disclosure.
5. **Schema v7 and contract version 1 are preserved** with zero database migrations.
6. **Strict all-known run and slot health semantics remain unchanged**, maintaining the fail-closed operational invariant in `tradex/pit/ops.py`.

> [!NOTE]
> **Evidence Boundary:** This change establishes that a provider executed cleanly and returned no usable upcoming earnings date. It does **not** establish "structural absence", that "no earnings date is scheduled", or that an ETF definitively has no corporate earnings based on Yahoo absence alone. Per `R7-PIT-STATUS-DEC-001`, instrument applicability and `NOT_ANNOUNCED` semantics remain evidence-dependent and require separate empirical studies.

---

## 2. Verified Old Behavior vs. New Prospective Behavior

### Old Swallowed-Failure Behavior
* When querying upcoming earnings through Yahoo (`calendar.get_next_earnings(symbol, source="yahoo")`), `calendar._fetch_from_yahoo(ticker)` tried `ticker.get_earnings_dates()` inside a broad `try...except Exception: pass`, followed by `ticker.calendar` inside another broad `try...except Exception: pass`.
* If no future date was found (whether because the provider was unreachable, timed out, returned malformed data, or returned a clean empty DataFrame), the function raised `EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")`.
* `tradex/pit/earnings.py:capture_earnings_snapshot()` caught `EarningsDataUnavailableError` and mapped it to:
  * `observation_status = ObservationStatus.UNAVAILABLE`
  * `error_category = type(exc).__name__` (normally `"EarningsDataUnavailableError"`)
  * `error_message = f"Upcoming earnings date unavailable for {sym}"`
  * `fact_json = serialize_canonical_fact_json(build_unavailable_fact_payload(error_cat, error_msg))` (i.e. `{"error_category": "EarningsDataUnavailableError", "error_message": "Upcoming earnings date unavailable for ...", "next_earnings_date": null}`)
* **Result:** Operational health could not distinguish a transport/parse failure from a clean provider execution where no usable upcoming earnings date was returned. A total network outage or provider ban on the Yahoo endpoint would appear as a clean data absence (`UNAVAILABLE` with `error_category="EarningsDataUnavailableError"`) rather than an operational provider failure (`ERROR`).

### New Prospective Behavior
* Explicit typed exceptions:
  * `EarningsProviderLookupError(ProviderError)`: Base technical failure for provider transport, timeout, HTTP, or unexpected exceptions.
  * `EarningsProviderResponseError(EarningsProviderLookupError)`: Specific sub-error for unexpected payload shapes, missing required structures (such as non-empty calendar dicts or DataFrames missing `"Earnings Date"`), or unparseable responses.
  * `EarningsDataUnavailableError(ProviderDataUnavailableError)`: Preserved strictly for clean provider execution where no usable upcoming earnings date was returned (clean empty response or only historical dates).
* In `tradex/pit/earnings.py:capture_earnings_snapshot()`:
  * `EarningsProviderLookupError` (including `EarningsProviderResponseError`) is caught and mapped to:
    * `observation_status = ObservationStatus.ERROR`
    * `error_category = type(exc).__name__` (e.g. `"EarningsProviderLookupError"` or `"EarningsProviderResponseError"`)
    * `error_message = f"Earnings provider lookup failed for {sym}"`
    * `fact_json = serialize_canonical_fact_json(build_unavailable_fact_payload(error_cat, error_msg))` (i.e. `{"error_category": "EarningsProviderLookupError", "error_message": "Earnings provider lookup failed for ...", "next_earnings_date": null}`)
  * `EarningsDataUnavailableError` remains mapped to:
    * `observation_status = ObservationStatus.UNAVAILABLE`
    * `error_category = type(exc).__name__` (normally `"EarningsDataUnavailableError"`)
    * `error_message = f"Upcoming earnings date unavailable for {sym}"`
    * `fact_json = serialize_canonical_fact_json(build_unavailable_fact_payload(error_cat, error_msg))` (i.e. `{"error_category": "EarningsDataUnavailableError", "error_message": "Upcoming earnings date unavailable for ...", "next_earnings_date": null}`)

---

## 3. Provider Outcome & Fallback Precedence Matrix

In `tradex/earnings/calendar.py`, `_fetch_from_yahoo` queries up to two strategies:
1. Primary: `ticker.get_earnings_dates()`
2. Fallback: `ticker.calendar`

Each strategy's outcome is classified into one of four states:
* **FOUND:** Valid upcoming date discovered.
* **CLEAN_EMPTY:** Call succeeded without error, but returned no usable future dates (e.g. empty DataFrame, empty dict, `None`, or only past dates).
* **MALFORMED:** Response structure was corrupted or unexpected (e.g. `ValueError`, `TypeError`, non-empty dict missing `"Earnings Date"`, non-empty DataFrame missing `"Earnings Date"`, or non-DataFrame/non-dict payload).
* **TECHNICAL:** Transport/network/lookup exception raised (e.g. `ConnectionError`, `HTTPError`, `Timeout`, generic `Exception`).

When evaluating both strategies, the precedence order is strictly deterministic:

| Strategy 1 (`get_earnings_dates`) | Strategy 2 (`ticker.calendar`) | Final Outcome | Exception Raised | PIT Observation Status |
|---|---|---|---|---|
| **FOUND** | *(Not queried)* | Valid Date | None | `KNOWN` |
| **CLEAN_EMPTY** | **FOUND** | Valid Date | None | `KNOWN` |
| **TECHNICAL** | **FOUND** | Valid Date | None | `KNOWN` |
| **MALFORMED** | **FOUND** | Valid Date | None | `KNOWN` |
| **MALFORMED** | **CLEAN_EMPTY** | Failure | `EarningsProviderResponseError` | `ERROR` |
| **CLEAN_EMPTY** | **MALFORMED** | Failure | `EarningsProviderResponseError` | `ERROR` |
| **MALFORMED** | **TECHNICAL** | Failure | `EarningsProviderResponseError` | `ERROR` |
| **MALFORMED** | **MALFORMED** | Failure | `EarningsProviderResponseError` | `ERROR` |
| **TECHNICAL** | **CLEAN_EMPTY** | Failure | `EarningsProviderLookupError` | `ERROR` |
| **CLEAN_EMPTY** | **TECHNICAL** | Failure | `EarningsProviderLookupError` | `ERROR` |
| **TECHNICAL** | **TECHNICAL** | Failure | `EarningsProviderLookupError` | `ERROR` |
| **CLEAN_EMPTY** | **CLEAN_EMPTY** | No Usable Upcoming Date | `EarningsDataUnavailableError` | `UNAVAILABLE` |

### Precedence Summary Rule:
1. **Valid upcoming date from either path** $\implies$ Return date (`ObservationStatus.KNOWN`).
2. **No date + at least one malformed/response failure** $\implies$ Raise `EarningsProviderResponseError` (`ObservationStatus.ERROR`).
3. **No date + at least one technical lookup failure** $\implies$ Raise `EarningsProviderLookupError` (`ObservationStatus.ERROR`).
4. **Both paths clean with no usable upcoming date** $\implies$ Raise `EarningsDataUnavailableError` (`ObservationStatus.UNAVAILABLE`).

---

## 4. Sanitization and Secret-Leakage Boundary

Under no circumstances may raw provider exception strings, stack traces, HTTP request headers, query tokens, or local environment paths be stored into `error_message`, `fact_json`, or SQLite tables.

### Boundary Enforcement:
1. **Exception Message Boundary:** `_fetch_from_yahoo` and `get_next_earnings` construct clean, templated exception messages:
   - `f"Earnings provider lookup failed for {ticker}"`
   - `f"Earnings provider response malformed for {ticker}"`
   - `f"Upcoming earnings date unavailable for {ticker}"`
   The original exception is chained internally (`from cause`) for local debugging/logging, but the exception string itself does not incorporate `str(cause)`.
2. **PIT Error Message Boundary:** In `tradex/pit/earnings.py`, `error_message` is strictly set to:
   - `f"Earnings provider lookup failed for {sym}"` for technical/response errors (`ObservationStatus.ERROR`)
   - `f"Upcoming earnings date unavailable for {sym}"` for clean unavailable outcomes (`ObservationStatus.UNAVAILABLE`)
   The `error_category` is populated solely with the Python class name `type(exc).__name__` (e.g. `"EarningsProviderLookupError"`, `"EarningsProviderResponseError"`, or `"EarningsDataUnavailableError"`).
3. **`fact_json` Boundary:** Constructed solely via `build_unavailable_fact_payload(error_category, error_message)` from `tradex.pit.models` and serialized via `serialize_canonical_fact_json()`, producing a deterministic canonical JSON payload:
   ```json
   {
     "error_category": "EarningsProviderLookupError",
     "error_message": "Earnings provider lookup failed for AAPL",
     "next_earnings_date": null
   }
   ```
   For clean no-usable-upcoming-date observations (`EarningsDataUnavailableError`), the canonical payload is:
   ```json
   {
     "error_category": "EarningsDataUnavailableError",
     "error_message": "Upcoming earnings date unavailable for AAPL",
     "next_earnings_date": null
   }
   ```
   The Schema v7 PIT earnings fact payload contains strictly `error_category`, `error_message`, and `next_earnings_date` (which is `null` for unavailable or error observations).
4. **Verification:** Test `test_earnings_capture_sanitization_underlying_secrets` proves that even when an underlying exception contains raw API tokens (`SECRET_AUTH_TOKEN`), passwords, and local Windows user paths, zero sensitive substrings appear in `error_message`, `fact_json`, or any SQLite database column.

---

## 5. Schema v7 and Contract Preservation

* **Schema Version:** Stays strictly at **`v7`**.
* **Contract Version:** Stays strictly at **`1`** (`PIT_CAPTURE_CONTRACT_VERSION == 1` from `tradex.pit.models`).
* **Database DDL:** Table `pit_earnings_snapshots` already contains columns `observation_status`, `error_category`, `error_message`, and `fact_json`. No DDL changes, column additions, or database migrations are performed.
* **Backward Compatibility:**
  * Historical records in `signals.db` remain untouched.
  * Prospective captures will write `ObservationStatus.ERROR` (or `ObservationStatus.UNAVAILABLE`) depending on the true provider condition.

---

## 6. Point-in-Time (PIT) Operational Impact

* **Fail-Closed Semantics Maintained:** `tradex/pit/ops.py` was **not touched**.
  The strict all-known aggregation rules remain in full effect:
  $$\text{known\_n} == \text{requested\_n} \implies \text{family SUCCEEDED}$$
  $$0 < \text{known\_n} < \text{requested\_n} \implies \text{family PARTIAL}$$
  $$\text{known\_n} == 0 \implies \text{family FAILED}$$
  $$\text{both families SUCCEEDED} \implies \text{slot HEALTHY}$$
* Any observation that is `ERROR` or `UNAVAILABLE` prevents the family from reaching `SUCCEEDED`.
* **Immediate Operational Benefit:** While slot health aggregation is unchanged, run inspection and operational observability now truthfully show *why* an earnings observation was missing: whether Yahoo failed technically (`ERROR` with `EarningsProviderLookupError`), returned an unparseable response (`ERROR` with `EarningsProviderResponseError`), or cleanly returned no usable upcoming earnings date (`UNAVAILABLE`).

---

## 7. Status and Prerequisite Sequence

1. **`MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001` (This PR):** **Complete.** Provider and PIT earnings failure paths are hardened, typed, deterministic, and sanitized.
2. **Next Prerequisite:** Live-provider empirical compatibility study for candidate universes (Dow 30, Sector ETFs) requires separate Gary authorization.
3. **Candidate Universe Activation (Candidate B / C):** Blocked pending the empirical study results and Gary's universe activation decision.
4. **Operational Implementation of Options 2 & 3:** Architectural direction approved in `R7-PIT-STATUS-DEC-001`; production implementation of status semantics separation remains unauthorized until a separate assignment is approved.
5. **Scheduler & Automation:** Automated cron/scheduled capture remains unauthorized.
6. **Trading Promotion:** `APPROVED_PRODUCTION_STRATEGIES == ()` is strictly preserved.
