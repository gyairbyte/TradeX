# R7-PIT-C2-READINESS-A: Initial PIT Universe Capacity and C2 Activation Decision Packet

> **Task ID:** `MVP-ARCH-001-R7-PIT-001C2-READINESS-A`
> **Classification:** Research-only / design-readiness
> **Status:** `pending_gary_decision`
> **Capacity Analysis Status:** `complete`
> **Operational Readiness Status:** `blocked_pending_capture_status_compatibility_decision`
> **Authoritative Base SHA:** `e111c04107b929b0b2ae8896755d57ec9b114f95`
> **Author:** Antigravity

---

## 1. Executive Summary

With the merge of `MVP-ARCH-001-R7-PIT-001C1` (PR #71), TradeX established a deterministic, versioned operations runner (`tradex.pit.ops`), fail-closed universe drift protection, read-only slot health inspection, and a pure pacing-floor capacity calculator (`estimate_capacity`). However, C1 intentionally deferred the selection and activation of an operational symbol universe, leaving scheduling and C2 implementation unauthorized.

This document evaluates five candidate symbol universes derived deterministically from the repository's committed point-in-time watchlist presets (`tradex/watchlists/presets.py`) under the Massive free-tier rate-limiting constraint (`DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS = 12.1`).

All candidate universes have been frozen into non-operational research artifacts under `docs/product/artifacts/r7-pit-c2-readiness-a/` with a future effective date (`effective_from = "2099-01-01"`). Under C1 contract enforcement, this future date enables static contract validation (`validate-universe`) and capacity estimation (`estimate_capacity`) while causing any accidental execution attempt (`run-slot`) to fail closed without performing network calls or SQLite database writes.

### Key Pacing Findings (Capacity Analysis: Complete)
1. **Coverage-First Pacing Candidate — Candidate C (Dow 30 + Sector ETFs, 45 symbols):** Combines 30 large-cap corporate equities across major economic sectors with 15 broad-market and sector SPDR ETFs. Its worst-case reference pacing floor is **17.95 minutes** (1,076.9 s), placing its reference-provider pacing floor below a hypothetical 20-minute reference-floor budget.
2. **Latency-First Pacing Candidate — Candidate B (Dow 30, 30 symbols):** Offers a narrower equity-only focus with a worst-case reference pacing floor of **11.90 minutes** (713.9 s), placing its reference pacing floor below a hypothetical 15-minute reference-floor budget and providing lower intra-slot reference observation spread if ETF regime context is deferred.
3. **Deferred Pacing Candidates — Candidate D (S&P 100, 100 symbols) and Candidate E (S&P 100 + Sector ETFs, 115 symbols):** Worst-case reference pacing floors of **40.13 minutes** (2,407.9 s) and **46.18 minutes** (2,770.9 s), respectively, creating materially larger intra-slot observation spread under free-tier pacing.
4. **Reference Pacing Floor vs. Total Runtime:** The reference pacing floor reflects solely the sequential inter-request sleep time for Massive requests ($\max(R-1, 0) \times 12.1\text{ s}$). It explicitly excludes preceding Yahoo earnings runtime, Massive network/HTTP latency, retries, startup overhead, and SQLite transaction time.

### Material Review Finding (Operational Readiness: Blocked)
**Operational activation is BLOCKED for all candidates (`operational_activation_recommendation: null`).**
The pacing calculations confirm mathematical capacity feasibility under free-tier rate limits, but the repository's current C1 capture-status contract creates an operational compatibility blocker:
- In `tradex.pit.earnings` and `tradex.pit.reference`, terminal family status is derived as:
  - all requested symbols `KNOWN` $\rightarrow$ `SUCCEEDED`
  - some `KNOWN` with $\ge 1$ `UNAVAILABLE` / `AMBIGUOUS` / `ERROR` $\rightarrow$ `PARTIAL`
  - zero `KNOWN` $\rightarrow$ `FAILED`
- In `tradex.pit.ops._compute_operational_status`, overall slot operational status requires **both** families to achieve `SUCCEEDED`. Any `PARTIAL` family automatically degrades the entire slot to `DEGRADED`.
- **Zero Live Provider Calls:** READINESS-A performed zero live provider calls. The compatibility blocker is established from C1 status semantics, not from measured Yahoo or Massive completeness.
- **ETF Earnings Structural Risk:** ETFs generally do not have operating-company earnings dates comparable to corporate equities. READINESS-A performed no live Yahoo calls and therefore does not establish how Yahoo will resolve these specific ETF symbols. Under the current C1 contract, if Yahoo produces no usable upcoming earnings date for a requested ETF, that observation is recorded as `UNAVAILABLE`. Any such `UNAVAILABLE` observation prevents the earnings family from achieving all-known `SUCCEEDED` status and therefore causes the overall slot to be `DEGRADED`. Candidates containing ETFs (A, C, E) face this unresolved structural risk.
- **Equity All-Known Contract:** For pure equity candidates (B and D), every single stock must return `KNOWN` for both earnings and reference data. Any single unavailable or error observation would degrade the family to `PARTIAL` and the slot to `DEGRADED`. Actual provider completeness has not been measured in this study.

Therefore, **no candidate can be claimed operationally ready or recommended for activation** until Gary reviews and resolves the C1 capture-status contract disposition.

---

## 2. Question Being Decided

> **Research Question:**
> What explicitly frozen prospective PIT universe provides a reasonable initial balance between market coverage, stocks/ETF representation, reproducibility, and operational capture latency under the current Massive free-tier pacing contract?

This question is addressed strictly as an operational data-capture feasibility and research-integrity study. It does NOT evaluate trading strategy returns, win rates, signal distributions, or model score performance.

---

## 3. Current Architecture and State

Following the completion of `MVP-ARCH-001-R7-PIT-001C1`:
- **Operational Runner:** `run_pit_slot` executes capture families deterministically: earnings capture first (Family 1, Yahoo), followed by reference capture (Family 2, Massive).
- **Same-Universe Invariant:** Both families receive the exact same normalized symbol list, enforcing identical `universe_hash` across families.
- **Universe Drift Guard:** `run_pit_slot` checks existing database records for the target `(capture_date, slot)`. Any existing run with a differing `universe_hash` causes an immediate fail-closed error with zero provider calls.
- **Read-Only Health Inspector:** `get_pit_slot_health` inspects slot audit records and returns structured health states without provider calls or database writes.
- **Capture-Status Derivation Contract:**
  - Family level: All symbols `KNOWN` $\rightarrow$ `SUCCEEDED`; partial known $\rightarrow$ `PARTIAL`; 0 known $\rightarrow$ `FAILED`.
  - Slot level: Both families `SUCCEEDED` $\rightarrow$ `SUCCEEDED`; both absent $\rightarrow$ `FAILED`; any `PARTIAL` or mismatched family $\rightarrow$ `DEGRADED`.
- **CLI Subcommands:** `validate-universe`, `run-slot`, and `health` are exposed via `tradex.pit.ops`.
- **Database Schema:** Schema version remains `v7`.
- **Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()`.
- **Pacing Constant:** `DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS = 12.1` (~5 requests per minute free tier).
- **Reference Pacing Formulas:**
  $$\text{minimum\_reference\_requests} = N$$
  $$\text{maximum\_reference\_requests} = 2N$$
  $$\text{minimum\_reference\_pacing\_floor} = \max(N - 1, 0) \times 12.1\text{ s}$$
  $$\text{maximum\_reference\_pacing\_floor} = \max(2N - 1, 0) \times 12.1\text{ s}$$

---

## 4. Source-of-Truth Commit and Provenance

All candidate universes are derived deterministically from the committed source preset code at:
- **Base Commit:** `e111c04107b929b0b2ae8896755d57ec9b114f95`
- **Source File:** `tradex/watchlists/presets.py`
- **Source Snapshot Date:** Approximately `2026-05` (as documented in `presets.py`)

**Strict Provenance Invariants:**
- `refresh.refresh_all` was NOT called.
- No live index constituent lookups were performed.
- No dynamic scanner results, CandidateSnapshots, Journals, scores, or user watchlists were used.
- Security classification is strictly deterministic based on source preset membership:
  - Symbols from `SECTOR_ETFS` $\rightarrow$ classified as **ETF**.
  - Symbols from `DOW30` $\rightarrow$ classified as **equity**.
  - Symbols from `SP100` $\rightarrow$ classified as **equity**.
- Overlap verification: The intersection of `DOW30` and `SECTOR_ETFS` is empty ($\emptyset$). The intersection of `SP100` and `SECTOR_ETFS` is empty ($\emptyset$).

---

## 5. Candidate Construction Rules

The five candidate universes and broad-scale reference preset are defined as follows:

| Candidate | Name | Construction Rule | Source Preset(s) |
|---|---|---|---|
| **Candidate A** | Sector ETFs | `normalize_symbols(SECTOR_ETFS)` | `SECTOR_ETFS` |
| **Candidate B** | Dow 30 | `normalize_symbols(DOW30)` | `DOW30` |
| **Candidate C** | Dow 30 + Sector ETFs | `normalize_symbols(DOW30 + SECTOR_ETFS)` | `DOW30`, `SECTOR_ETFS` |
| **Candidate D** | S&P 100 | `normalize_symbols(SP100)` | `SP100` |
| **Candidate E** | S&P 100 + Sector ETFs | `normalize_symbols(SP100 + SECTOR_ETFS)` | `SP100`, `SECTOR_ETFS` |
| *Reference* | S&P 500 | `normalize_symbols(SP500)` | `SP500` |

*Note on S&P 500:* The committed `SP500` preset contains 503 raw entries due to dual-share class equity listings (e.g. `GOOG`/`GOOGL`, `FOX`/`FOXA`, `NWSA`/`NWS`). All 503 are unique upon normalization. It is analyzed as a capacity reference only and is not committed as a prospective C2 manifest.

---

## 6. Candidate Manifest Artifacts

The candidates are frozen as standalone JSON manifests under `docs/product/artifacts/r7-pit-c2-readiness-a/`:

1. [`candidate-sector-etfs.json`](artifacts/r7-pit-c2-readiness-a/candidate-sector-etfs.json)
2. [`candidate-dow30.json`](artifacts/r7-pit-c2-readiness-a/candidate-dow30.json)
3. [`candidate-dow30-sector-etfs.json`](artifacts/r7-pit-c2-readiness-a/candidate-dow30-sector-etfs.json)
4. [`candidate-sp100.json`](artifacts/r7-pit-c2-readiness-a/candidate-sp100.json)
5. [`candidate-sp100-sector-etfs.json`](artifacts/r7-pit-c2-readiness-a/candidate-sp100-sector-etfs.json)
6. [`decision.json`](artifacts/r7-pit-c2-readiness-a/decision.json)

All manifests specify `contract_version = 1`, `universe_version = "2026-09-08-v1"`, and `effective_from = "2099-01-01"`.

---

## 7. Exact Hashes and Constituent Counts

The following table documents the exact normalized symbol counts, security breakdown, and SHA-256 hashes generated through the C1 contracts:

| Candidate | Total Symbols | Equities | ETFs | Universe Hash (`universe_hash`) | Material Manifest Hash (`manifest_hash`) |
|---|---|---|---|---|---|
| **A (Sector ETFs)** | 15 | 0 | 15 | `315dc68c54c9a5cd3d5634babd4f81629647b978114907ce84d73c4cc9f50df6` | `fe66cbde81a97147efd2bbd12f98c93b72231b8735c0ddec946088beb47c2752` |
| **B (Dow 30)** | 30 | 30 | 0 | `173411d5854450294821e4dedbe5147278ccf248d8a21fc1973d81a41b9465b4` | `323f753d3a50c44d985d1c1f214c64bab62388712573927ad70e7d1475cadc43` |
| **C (Dow 30 + ETFs)** | 45 | 30 | 15 | `83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29` | `211fc10c82d71889db16364ce2df33cd73aae5952f25efe9a2cd7e59c81fa1d9` |
| **D (S&P 100)** | 100 | 100 | 0 | `ee9f48232b60ecd4c9f905b9eee1d5a3a2dcc9be705e18f85b3edd68d6d4b67f` | `21c05c6289c639133afa3b966da92eb7de1549e43227a7defe61f56314318711` |
| **E (S&P 100 + ETFs)** | 115 | 100 | 15 | `e44345b7fdb2845cc3b3b75b86fdabc35428266c03697e9048dba77626090d55` | `612483ef7fc7d6ce80d3e67268c0d8db3d7198649a018292080a98f2b294ea38` |
| *Ref (S&P 500)* | 503 | 503 | 0 | `743955ad4d36808f88af3695f773ecd70115cf18b221d837619202ceb5617c94` | *N/A (Reference preset only; no manifest file)* |

---

## 8. Capacity Table

Using the real C1 `estimate_capacity` implementation at $12.1\text{ s}$ per request:

| Candidate | Symbols ($N$) | Min Requests ($N$) | Max Requests ($2N$) | Min Reference Pacing Floor | Max Reference Pacing Floor |
|---|---|---|---|---|---|
| **A (Sector ETFs)** | 15 | 15 | 30 | 169.4 s (2.82 min) | 350.9 s (5.85 min) |
| **B (Dow 30)** | 30 | 30 | 60 | 350.9 s (5.85 min) | 713.9 s (11.90 min) |
| **C (Dow 30 + ETFs)** | 45 | 45 | 90 | 532.4 s (8.87 min) | 1076.9 s (17.95 min) |
| **D (S&P 100)** | 100 | 100 | 200 | 1197.9 s (19.96 min) | 2407.9 s (40.13 min) |
| **E (S&P 100 + ETFs)** | 115 | 115 | 230 | 1379.4 s (22.99 min) | 2770.9 s (46.18 min) |
| *Ref (S&P 500)* | 503 | 503 | 1006 | 6074.2 s (101.24 min) | 12160.5 s (202.68 min) |

---

## 9. Conditional Latency Matrix

> [!NOTE]
> The thresholds below represent **hypothetical reference-pacing-floor budgets**, NOT approved total runtime SLAs. A value of "YES" indicates that the candidate's worst-case reference-provider pacing floor ($\max(2N - 1, 0) \times 12.1\text{ s}$) is strictly less than or equal to that hypothetical budget.

| Candidate | Worst-Case Ref Floor | Budget: 10 min (600 s) | Budget: 15 min (900 s) | Budget: 20 min (1200 s) | Budget: 30 min (1800 s) | Budget: 45 min (2700 s) | Budget: 60 min (3600 s) |
|---|---|---|---|---|---|---|---|
| **A (Sector ETFs)** | 5.85 min (350.9 s) | **YES** | **YES** | **YES** | **YES** | **YES** | **YES** |
| **B (Dow 30)** | 11.90 min (713.9 s) | NO | **YES** | **YES** | **YES** | **YES** | **YES** |
| **C (Dow 30 + ETFs)** | 17.95 min (1076.9 s) | NO | NO | **YES** | **YES** | **YES** | **YES** |
| **D (S&P 100)** | 40.13 min (2407.9 s) | NO | NO | NO | NO | **YES** | **YES** |
| **E (S&P 100 + ETFs)** | 46.18 min (2770.9 s) | NO | NO | NO | NO | NO | **YES** |
| *Ref (S&P 500)* | 202.68 min (12160.5 s) | NO | NO | NO | NO | NO | NO |

**Observations from the Matrix:**
- Candidate A is the only candidate whose worst-case reference pacing floor is below the hypothetical 10-minute budget.
- Candidate B's worst-case reference floor (11.90 min) is below the hypothetical 15-minute budget.
- Candidate C's worst-case reference floor (17.95 min) is below the hypothetical 20-minute budget.
- Candidates D and E require hypothetical budgets of 45 minutes and 60 minutes, respectively, to accommodate their worst-case reference pacing floors.
- S&P 500 exceeds even a 60-minute reference pacing budget by more than a factor of three (requiring ~3.38 hours of pacing alone).

---

## 10. Coverage Analysis

The table below summarizes market coverage using dimensions strictly supported by repository artifacts without external enrichment:

| Candidate | Total Symbols | Equity Symbols | ETF Symbols | Source Preset(s) | Broad-Market ETFs | Sector ETFs | Relative Breadth | Known Qualitative Concentration Limitations |
|---|---|---|---|---|---|---|---|---|
| **A (Sector ETFs)** | 15 | 0 | 15 | `SECTOR_ETFS` | Yes (`SPY`, `QQQ`, `IWM`, `DIA`) | Yes (11 SPDR ETFs) | Macro/Regime only | Zero individual corporate equities; cannot provide company earnings evidence. |
| **B (Dow 30)** | 30 | 30 | 0 | `DOW30` | No | No | Blue-chip equities | Only 30 large-cap names; excludes broader market tiers, mid-caps, and ETF sector context. |
| **C (Dow 30 + ETFs)** | 45 | 30 | 15 | `DOW30`, `SECTOR_ETFS` | Yes (4 broad ETFs) | Yes (11 sector ETFs) | Blue-chip + Macro | Compact sample of equities; excludes broader universe of non-Dow equities. |
| **D (S&P 100)** | 100 | 100 | 0 | `SP100` | No | No | Large-cap equities | 100 major U.S. equities; lacks sector ETF macro instruments. |
| **E (S&P 100 + ETFs)** | 115 | 100 | 15 | `SP100`, `SECTOR_ETFS` | Yes (4 broad ETFs) | Yes (11 sector ETFs) | Broad large-cap + Macro | Comprehensive large-cap coverage, but creates largest intra-slot observation spread. |
| *Ref (S&P 500)* | 503 | 503 | 0 | `SP500` | No | No | Benchmark equities | Unusable under current single-threaded free-tier pacing. |

---

## 11. Current C1 Capture-Status Compatibility

> [!WARNING]
> **Material Merge-Gate Finding: Current C1 Status Contract Blocks Operational Activation**
> The mathematical pacing calculations in Sections 8 and 9 establish rate-limit feasibility. However, operational health is governed by the C1 capture-status contract. Under current C1 semantics, operational slot status degrades whenever any symbol is unavailable, meaning no candidate can currently be claimed operationally ready.

### Current Repository Contract Behavior
Under the merged C1 implementation (`tradex.pit.earnings`, `tradex.pit.reference`, `tradex.pit.ops`):
1. **Earnings Family Status (`capture_earnings_snapshot`):**
   - Terminal status is derived as `SUCCEEDED` **if and only if** `known_n == requested_n`.
   - If some symbols are `KNOWN` but $\ge 1$ symbol is `UNAVAILABLE` or `ERROR`, status is `PARTIAL`.
   - If zero symbols are `KNOWN`, status is `FAILED`.
   - An unavailable earnings date is therefore **NOT** operationally equivalent to family success under current code.
2. **Reference Family Status (`capture_reference_snapshot`):**
   - Terminal status is derived as `SUCCEEDED` **if and only if** `known_n == requested_n`.
   - If some symbols are `KNOWN` but $\ge 1$ symbol is `UNAVAILABLE`, `AMBIGUOUS`, or `ERROR`, status is `PARTIAL`.
   - If zero symbols are `KNOWN`, status is `FAILED`.
3. **Slot Operational Status (`_compute_operational_status`):**
   - Derived as `SUCCEEDED` **if and only if** both `earnings_status == SUCCEEDED` and `ref_status == SUCCEEDED`.
   - Derived as `FAILED` if both family runs are absent (`capture_run_id is None`).
   - Derived as `DEGRADED` for **any other combination**.
   - **Crucial Invariant:** Any `PARTIAL` family terminal status automatically degrades the entire slot run to `DEGRADED`.

### The ETF Corporate Earnings Structural Risk
- ETFs (e.g., `SPY`, `QQQ`, `XLK`, `XLF`) are pooled investment funds, not operating corporations, and generally lack operating-company earnings dates comparable to corporate equities.
- **Zero Live Calls Conducted:** READINESS-A performed no live Yahoo calls and therefore does not establish how Yahoo will resolve these specific ETF symbols.
- **Contract Consequence:** Under the current C1 contract, if Yahoo produces no usable upcoming earnings date for a requested ETF, that observation is recorded as `UNAVAILABLE`. Any such `UNAVAILABLE` observation drops `known_n` below `requested_n`, preventing an all-known `SUCCEEDED` family status and causing the overall slot operational status to be `DEGRADED`.
- Candidates containing ETFs (A, C, E) face this unresolved structural compatibility risk.

### The Equity All-Known Contract
- Even for pure-equity universes (Candidate B: 30 symbols, Candidate D: 100 symbols), every single constituent must return `KNOWN` for both earnings and reference capture to achieve family `SUCCEEDED`.
- If a single equity has no announced earnings date on Yahoo, or Massive produces an unmapped ticker or unexpected error, that observation is recorded as `UNAVAILABLE` or `ERROR`, dropping the family to `PARTIAL` and degrading the slot.
- A larger basket creates more opportunities for at least one requested observation to be `UNAVAILABLE`, `AMBIGUOUS`, or `ERROR` under the current all-known success contract. The actual incidence rate is unmeasured.
- This offline study intentionally executed zero live provider calls, so actual provider availability distributions have not been measured.

### Candidate Status Compatibility Matrix

| Candidate | Composition | Current C1 Compatibility | Operational Compatibility Assessment & Risk |
|---|---|---|---|
| **A (Sector ETFs)** | 15 ETFs, 0 Equities | **UNRESOLVED** | Contains ETF symbols, creating a structural compatibility risk because these instruments generally do not have operating-company earnings dates. Actual Yahoo behavior for the frozen ETF symbols was not measured. If Yahoo produces no usable upcoming earnings date for one or more ETFs, C1 records those observations as `UNAVAILABLE`, preventing an all-known earnings `SUCCEEDED` result. |
| **B (Dow 30)** | 30 Equities, 0 ETFs | **UNRESOLVED** | Avoids ETF earnings structural risk. However, under current C1 code, any single unavailable or error observation degrades the family to `PARTIAL` and the slot to `DEGRADED`. Actual provider completeness has not been measured in this study. |
| **C (Dow 30 + ETFs)** | 30 Equities, 15 ETFs | **UNRESOLVED** | Contains 15 ETF symbols, creating an unresolved structural compatibility risk. If Yahoo produces no usable upcoming earnings date for one or more ETFs, C1 records `UNAVAILABLE`, preventing an all-known earnings `SUCCEEDED` result. For equities, any single missing observation also degrades the family; actual provider completeness is unmeasured. |
| **D (S&P 100)** | 100 Equities, 0 ETFs | **UNRESOLVED** | A 100-equity basket creates more opportunities for at least one requested observation to be `UNAVAILABLE`, `AMBIGUOUS`, or `ERROR` under the current all-known contract. Any single omission degrades the family and slot. Actual provider completeness has not been measured in this study. |
| **E (S&P 100 + ETFs)** | 100 Equities, 15 ETFs | **UNRESOLVED** | Combines ETF earnings structural risk with the increased opportunities for omission in a 100-equity basket. If Yahoo produces no usable earnings date for ETFs or any equity is missing data, the slot is degraded. Actual provider completeness is unmeasured. |

### Operational Readiness Conclusion
- **Operational readiness status:** `blocked_pending_capture_status_compatibility_decision`.
- **Operational activation recommendation:** `null` (None).
- Candidate C remains the **Coverage-First Pacing Candidate** from a pure capacity standpoint.
- Candidate B remains the **Latency-First Pacing Candidate** from a pure capacity standpoint.
- However, **no candidate can be activated** until Gary decides how TradeX should handle the C1 all-known capture-success criterion.

---

## 12. Research-Integrity Considerations

1. **Prospective Capture Only:** Universe selection governs prospective observation going forward. Current constituent snapshot lists must NEVER be retroactively backfilled or treated as historical index constituents for earlier dates.
2. **Immutability of Historical Evidence:** Existing PIT audit runs and snapshots in `signals.db` must never be rewritten or modified when an active universe changes.
3. **Formal Universe Versioning:** Any future change to universe membership requires an explicit new manifest with an incremented `universe_version`, a new `manifest_hash`, and a distinct `effective_from` date.
4. **No Performance-Based Membership Optimization:** The active universe must never be tuned, pruned, or expanded based on downstream strategy returns, win rates, or scan scores.
5. **No Dynamic Unioning:** New candidates discovered by the scanner or watcher must never be silently injected into the active operational PIT universe. The universe contract is strictly static and file-backed.
6. **No Automatic Watchlist Refresh:** Operational capture must never dynamically invoke `refresh.refresh_all`.

---

## 13. Operational Limitations

> [!WARNING]
> **What This Study Does NOT Establish:**
> - **End-to-End Slot Completion Lag:** The capacity estimate calculates only the reference provider pacing floor. It does not measure the actual duration of the slot run.
> - **Preceding Yahoo Earnings Runtime:** `run_pit_slot` runs earnings capture before reference capture. The earnings family performs un-cached Yahoo queries for each symbol. Its runtime depends on network latency and Yahoo response characteristics.
> - **Massive Network Latency:** The pacing interval ($12.1\text{ s}$) is enforced between calls; each HTTP request also incurs round-trip network transit and processing time.
> - **Inactive Fallback Frequency:** If a symbol is active, 1 request is made. If inactive, a second request is made. The actual request count $R$ will fall in the interval $[N, 2N]$.
> - **Transient Failures and Retries:** Temporary HTTP disconnects or DNS delays will increase wall-clock time.
> - **OS Scheduler Context:** Unattended execution via Windows Task Scheduler or cron involves wake/sleep states, process startup overhead, and environment credential access that cannot be evaluated without live deployment evidence.

---

## 14. Candidate-by-Candidate Evaluation

### Candidate A: Sector ETFs (15 symbols)
- **Pros:** Fast pacing floor (2.82 to 5.85 minutes); zero risk of substantial capture spread; provides clean macro regime context across all 11 GICS sectors.
- **Cons:** Zero individual equities. Completely unsuited for individual stock earnings or security reference research. ETFs generally lack corporate earnings; if Yahoo produces no usable earnings date for ETFs, C1 records `UNAVAILABLE`, preventing an all-known earnings `SUCCEEDED` result.
- **Verdict:** Unsuitable as a primary standalone operational universe; status compatibility unresolved.

### Candidate B: Dow 30 (30 symbols)
- **Pros:** Worst-case reference pacing floor of 11.90 minutes; low intra-slot capture spread; transparent, highly liquid blue-chip equities with predictable corporate filings; avoids ETF corporate earnings structural risk.
- **Cons:** Narrow coverage (30 equities); lacks broad-market and sector ETF regime context; any single equity missing earnings or reference data degrades slot under current C1 code.
- **Verdict:** Recommended **Latency-First Pacing Candidate** if minimizing intra-slot capture spread is the top priority; operational activation blocked pending Gary's C1 status decision.

### Candidate C: Dow 30 + Sector ETFs (45 symbols)
- **Pros:** Balanced synthesis of 30 blue-chip equities and 15 macro/sector ETFs. Worst-case reference pacing floor of 17.95 minutes (below a hypothetical 20-minute reference-floor budget).
- **Cons:** Slightly larger pacing floor than Dow 30 alone; structural compatibility risk for ETF earnings under current C1 code if Yahoo produces no usable earnings dates.
- **Verdict:** Recommended **Coverage-First Pacing Candidate** for balanced market representation; operational activation blocked pending Gary's C1 status decision.

### Candidate D: S&P 100 (100 symbols)
- **Pros:** Broader representation of top 100 U.S. large-cap equities.
- **Cons:** Worst-case reference pacing floor is 40.13 minutes, creating substantial intra-slot observation spread across market open under free-tier pacing; a 100-equity basket creates more opportunities for at least one requested observation to degrade the family under current all-known rules.
- **Verdict:** **Deferred** from initial deployment due to pacing spread and operational degradation risk under current status rules.

### Candidate E: S&P 100 + Sector ETFs (115 symbols)
- **Pros:** Comprehensive coverage of top large-caps plus full macro ETF regime suite.
- **Cons:** Worst-case reference pacing floor is 46.18 minutes, resulting in an extended capture spread across market open under free-tier pacing; combines ETF earnings structural risk with 100-equity basket omission opportunities under current all-known rules.
- **Verdict:** **Deferred** from initial deployment due to pacing spread and operational degradation risk under current status rules.

---

## 15. Coverage-First Pacing Candidate (Candidate C)

**Candidate C (`candidate-dow30-sector-etfs`, 45 symbols)** is identified as the **Coverage-First Pacing Candidate** from a pure capacity and market-representation standpoint.

**Pacing Rationale:**
- Combines 30 large-cap corporate equities across major economic sectors with 15 broad-market and sector SPDR ETFs.
- Its worst-case reference pacing floor of **17.95 minutes** falls below a hypothetical 20-minute reference-floor budget.
- It provides a compact, reproducible foundation that covers both corporate equities and macro regime instruments under the free-tier pacing contract.

*Operational Status Caveat:* Activation is blocked until Gary resolves the C1 capture-status contract regarding ETF earnings `UNAVAILABLE` observations.

---

## 16. Latency-First Pacing Candidate (Candidate B)

**Candidate B (`candidate-dow30`, 30 symbols)** is identified as the **Latency-First Pacing Candidate** if Gary prefers to minimize intra-slot observation spread.

**Pacing Rationale:**
- Worst-case reference pacing floor is **11.90 minutes** (below a hypothetical 15-minute budget).
- Restricts capture strictly to 30 well-behaved, highly liquid corporate equities.
- Avoids the ETF earnings structural risk entirely.
- Sacrifices macro/sector ETF regime context in exchange for tighter observation windows around the 09:00 morning slot.

*Operational Status Caveat:* Activation is blocked until Gary resolves the C1 capture-status contract regarding single-equity `UNAVAILABLE` observation degradation.

---

## 17. Operational Activation Recommendation: None / Blocked

> [!IMPORTANT]
> **Operational Activation Recommendation: `null` (None)**
> - `operational_activation_recommendation`: `null`
> - `operational_readiness_status`: `blocked_pending_capture_status_compatibility_decision`
> - `selected_universe`: `null`
> - `active_universe_authorized`: `false`
> - `c2_implementation_authorized`: `false`
> - `scheduler_authorized`: `false`

While the capacity study confirms that Candidate C (45 symbols) and Candidate B (30 symbols) satisfy hypothetical reference pacing budgets of 20 minutes and 15 minutes respectively, **no candidate can be recommended for live operational activation at this time**.

Operational activation cannot proceed responsibly without first addressing the C1 all-known capture-success criterion.

---

## 18. Conditions That Would Change the Recommendation

The recommendation and operational readiness status would be re-evaluated under any of the following conditions:
1. **Gary Design Decision on Status Semantics:** Gary approving a refined C1 capture-status contract that distinguishes structurally unavailable facts (e.g., ETF earnings) from operational capture failures.
2. **Provider Rate Limits / Architecture:** A future validated provider contract or separately approved provider architecture that materially changes effective request pacing or runtime characteristics.
3. **Observed Earnings Latency:** Live measurement showing actual Yahoo earnings capture duration for 30–45 symbols.
4. **Empirical Provider Study:** Live capture evidence establishing real-world `KNOWN` vs. `UNAVAILABLE` rates on target constituents.
5. **Gary's Risk Tolerance:** If Gary decides to accept frequent `DEGRADED` slot audit records under current strict semantics.

---

## 19. C2 Implementation Inputs

If Gary resolves the status contract issue and approves activation of a candidate universe, C2 implementation will require:
1. **Approved Operational Manifest:** Creation of an active production manifest file (e.g. `docs/product/manifests/universe-2026-09-v1.json`) with an approved, real `effective_from` date (e.g. current or target deployment date).
2. **Dedicated Environment Configuration:** Secure placement of Massive/Polygon credentials in the runtime `.env` without exposing them in logs or repository files.
3. **Scheduler Definition:** An explicit OS scheduling specification (e.g. Windows Task Scheduler XML or script) invoking `python -m tradex.pit.ops run-slot --slot morning|evening --universe-file <path>` at 09:00 ET and 20:30 ET.
4. **Audit and Health Monitoring:** Operational procedures for inspecting `python -m tradex.pit.ops health --universe-file <path>` on trading days.
5. **Gary Approval Gate:** Formal documented authorization before any scheduling task is installed or enabled.

---

## 20. Explicit Gary Decision Required

The following decisions remain exclusively with Gary in strict sequence:

### Step 1: C1 Capture-Status Contract Disposition (Prerequisite)
Gary must decide how TradeX should handle the C1 all-known capture-success criterion before any operational universe is activated:
- [ ] **Option A (Accept Strict Semantics):** Proceed with current C1 code; accept that if Yahoo produces no earnings date for ETFs or any equity data is missing, slot operational status will be `DEGRADED`.
- [ ] **Option B (Refine Status Contract):** Authorize a focused follow-up slice to refine status derivation (e.g., treat ETF earnings unavailability as a valid neutral observation, or permit an acceptable observation threshold for `SUCCEEDED`).
- [ ] **Option C (Empirical Provider Study):** Authorize an empirical live-provider test on a minimal symbol set to measure actual Yahoo and Massive return distributions before deciding.

### Step 2: Operational Universe and Activation Decisions (Contingent on Step 1)
- [ ] **Universe Selection:** Select Candidate C (Coverage-First pacing), Candidate B (Latency-First pacing), or another specified universe.
- [ ] **Effective Date:** Determine the operational `effective_from` date for initial capture.
- [ ] **C2 Authorization:** Authorize the start of task `MVP-ARCH-001-R7-PIT-001C2` (Scheduler and Operational Deployment).

---

## 21. Non-Authorization Statement

This task (`MVP-ARCH-001-R7-PIT-001C2-READINESS-A`) is strictly research and design readiness.
- **NO active universe has been selected or activated (`selected_universe = null`).**
- **NO scheduler has been installed or configured (`scheduler_authorized = false`).**
- **NO C2 implementation work is authorized (`c2_implementation_authorized = false`).**
- **NO active universe is authorized (`active_universe_authorized = false`).**
- **NO changes have been made to production code (`tradex/`).**
- **NO live provider calls or database writes were performed.**
- **`APPROVED_PRODUCTION_STRATEGIES` remains strictly `()`.**
