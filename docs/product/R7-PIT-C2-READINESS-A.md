# R7-PIT-C2-READINESS-A: Initial PIT Universe Capacity and C2 Activation Decision Packet

> **Task ID:** `MVP-ARCH-001-R7-PIT-001C2-READINESS-A`
> **Classification:** Research-only / design-readiness
> **Status:** `pending_gary_decision`
> **Authoritative Base SHA:** `e111c04107b929b0b2ae8896755d57ec9b114f95`
> **Author:** Antigravity

---

## 1. Executive Summary

With the merge of `MVP-ARCH-001-R7-PIT-001C1` (PR #71), TradeX established a deterministic, versioned operations runner (`tradex.pit.ops`), fail-closed universe drift protection, read-only slot health inspection, and a pure pacing-floor capacity calculator (`estimate_capacity`). However, C1 intentionally deferred the selection and activation of an operational symbol universe, leaving scheduling and C2 implementation unauthorized.

This document evaluates five candidate symbol universes derived deterministically from the repository's committed point-in-time watchlist presets (`tradex/watchlists/presets.py`) under the Massive free-tier rate-limiting constraint (`DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS = 12.1`).

All candidate universes have been frozen into non-operational research artifacts under `docs/product/artifacts/r7-pit-c2-readiness-a/` with a future effective date (`effective_from = "2099-01-01"`). Under C1 contract enforcement, this future date enables static contract validation (`validate-universe`) and capacity estimation (`estimate_capacity`) while causing any accidental execution attempt (`run-slot`) to fail closed without performing network calls or SQLite database writes.

**Key Findings:**
1. **Candidate C (Dow 30 + Sector ETFs, 45 symbols)** provides broad large-cap equity representation across major industries along with sector/macro regime context. Its worst-case reference pacing floor is **17.95 minutes**, placing its reference-provider pacing floor below a hypothetical 20-minute reference-floor budget.
2. **Candidate B (Dow 30, 30 symbols)** offers a narrower equity-only focus with a worst-case reference pacing floor of **11.90 minutes** (below a hypothetical 15-minute reference-floor budget), providing lower intra-slot reference observation spread if ETF regime context is deferred.
3. **Candidate D (S&P 100, 100 symbols)** and **Candidate E (S&P 100 + Sector ETFs, 115 symbols)** have worst-case reference pacing floors of **40.13 minutes** and **46.18 minutes**, respectively, creating materially larger intra-slot observation spread under the free-tier rate limit.
4. **End-to-end runtime distinction:** The reference pacing floor reflects only the sequential pacing of Massive requests ($\max(R-1, 0) \times 12.1\text{ s}$). It explicitly excludes preceding Yahoo earnings runtime, Massive network/HTTP latency, retries, startup, and SQLite overhead. It must not be equated with total slot completion time.

This study does NOT activate any universe, does NOT install any scheduler, and does NOT authorize C2 implementation. All operational activations remain strictly subject to Gary's review and approval.

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
| *Ref (S&P 500)* | 503 | 503 | 0 | `743955ad4d36808f88af3695f773ecd70115cf18b221d837619202ceb5617c94` | `2736709da6a97672238f69387de68ecc1a27ad3b3e1deaaea06e300f1c3759ba` |

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

## 11. Research-Integrity Considerations

1. **Prospective Capture Only:** This universe selection governs prospective observation going forward. Current constituent snapshot lists must NEVER be retroactively backfilled or treated as historical index constituents for earlier dates.
2. **Immutability of Historical Evidence:** Existing PIT audit runs and snapshots in `signals.db` must never be rewritten or modified when an active universe changes.
3. **Formal Universe Versioning:** Any future change to universe membership requires an explicit new manifest with an incremented `universe_version`, a new `manifest_hash`, and a distinct `effective_from` date.
4. **No Performance-Based Membership Optimization:** The active universe must never be tuned, pruned, or expanded based on downstream strategy returns, win rates, or scan scores.
5. **No Dynamic Unioning:** New candidates discovered by the scanner or watcher must never be silently injected into the active operational PIT universe. The universe contract is strictly static and file-backed.
6. **No Automatic Watchlist Refresh:** Operational capture must never dynamically invoke `refresh.refresh_all`.

---

## 12. Operational Limitations

> [!WARNING]
> **What This Study Does NOT Establish:**
> - **End-to-End Slot Completion Lag:** The capacity estimate calculates only the reference provider pacing floor. It does not measure the actual duration of the slot run.
> - **Preceding Yahoo Earnings Runtime:** `run_pit_slot` runs earnings capture before reference capture. The earnings family performs un-cached Yahoo queries for each symbol. Its runtime depends on network latency and Yahoo response characteristics.
> - **Massive Network Latency:** The pacing interval ($12.1\text{ s}$) is enforced between calls; each HTTP request also incurs round-trip network transit and processing time.
> - **Inactive Fallback Frequency:** If a symbol is active, 1 request is made. If inactive, a second request is made. The actual request count $R$ will fall in the interval $[N, 2N]$.
> - **Transient Failures and Retries:** Temporary HTTP disconnects or DNS delays will increase wall-clock time.
> - **OS Scheduler Context:** Unattended execution via Windows Task Scheduler or cron involves wake/sleep states, process startup overhead, and environment credential access that cannot be evaluated without live deployment evidence.

---

## 13. Candidate-by-Candidate Evaluation

### Candidate A: Sector ETFs (15 symbols)
- **Pros:** Fast pacing floor (2.82 to 5.85 minutes); zero risk of substantial capture spread; provides clean macro regime context across all 11 GICS sectors.
- **Cons:** Zero individual equities. Completely unsuited for individual stock earnings or security reference research.
- **Verdict:** Unsuitable as a primary standalone operational universe; useful only as a supplemental benchmark.

### Candidate B: Dow 30 (30 symbols)
- **Pros:** Worst-case reference pacing floor of 11.90 minutes; low intra-slot capture spread; transparent, highly liquid blue-chip equities with predictable corporate filings.
- **Cons:** Narrow coverage (30 equities); lacks broad-market and sector ETF regime context.
- **Verdict:** Strong **Latency-First** candidate if minimizing intra-slot capture spread is the top operational priority.

### Candidate C: Dow 30 + Sector ETFs (45 symbols)
- **Pros:** Balanced synthesis of 30 blue-chip equities and 15 macro/sector ETFs. Worst-case reference pacing floor of 17.95 minutes (below a hypothetical 20-minute reference-floor budget).
- **Cons:** Slightly larger pacing floor than Dow 30 alone; ETFs do not have company earnings.
- **Verdict:** Recommended **Coverage-First** candidate. Represents the best operational compromise between multi-asset market coverage and manageable pacing latency.

### Candidate D: S&P 100 (100 symbols)
- **Pros:** Broader representation of top 100 U.S. large-cap equities.
- **Cons:** Worst-case reference pacing floor is 40.13 minutes, creating substantial intra-slot observation spread across market open under the free-tier rate limit.
- **Verdict:** **Deferred** from initial deployment pending observed runtime evidence or future provider tier changes.

### Candidate E: S&P 100 + Sector ETFs (115 symbols)
- **Pros:** Comprehensive coverage of top large-caps plus full macro ETF regime suite.
- **Cons:** Worst-case reference pacing floor is 46.18 minutes, resulting in an extended capture spread across market open under the free-tier rate limit.
- **Verdict:** **Deferred** from initial deployment due to operational capture spread.

---

## 14. Primary Recommendation (Coverage-First)

**Candidate C (`candidate-dow30-sector-etfs`, 45 symbols)** is conditionally recommended for Gary's consideration as the **Coverage-First** prospective operational universe.

**Rationale:**
- Combines 30 large-cap corporate equities across major economic sectors with 15 broad-market and sector SPDR ETFs.
- Its worst-case reference pacing floor of **17.95 minutes** falls below a hypothetical 20-minute reference-floor budget.
- It provides a compact, reproducible foundation that tests both individual equity earnings/reference pipelines and ETF reference pipelines without overwhelming the free-tier rate limit.

---

## 15. Alternative Recommendation (Latency-First)

**Candidate B (`candidate-dow30`, 30 symbols)** is recommended as the **Latency-First** alternative if Gary prefers to minimize intra-slot observation spread.

**Rationale:**
- Worst-case reference pacing floor is **11.90 minutes** (below a hypothetical 15-minute budget).
- Restricts the capture strictly to 30 well-behaved, highly liquid corporate equities.
- Sacrifices macro/sector ETF regime context in exchange for tighter observation windows around the 09:00 morning slot.

---

## 16. Conditions That Would Change the Recommendation

The recommendation would be re-evaluated under any of the following conditions:
1. **Provider Rate Limits / Architecture:** A future validated provider contract or separately approved provider architecture that materially changes effective request pacing or runtime characteristics.
2. **Observed Earnings Latency:** If initial operational testing reveals that Yahoo earnings capture runtime for 30–45 symbols introduces unacceptable delay before reference capture begins.
3. **Excessive Fallback Rate:** If a substantial portion of symbols require inactive fallback lookups, consistently driving request counts toward $2N$.
4. **Gary's Risk Tolerance:** If Gary prioritizes market breadth over capture spread, warranting acceptance of a 40+ minute reference floor for S&P 100.

---

## 17. C2 Implementation Inputs

If Gary approves activation of a candidate universe, C2 implementation will require:
1. **Approved Operational Manifest:** Creation of an active production manifest file (e.g. `docs/product/manifests/universe-2026-09-v1.json`) with an approved, real `effective_from` date (e.g. current or target deployment date).
2. **Dedicated Environment Configuration:** Secure placement of Massive/Polygon credentials in the runtime `.env` without exposing them in logs or repository files.
3. **Scheduler Definition:** An explicit OS scheduling specification (e.g. Windows Task Scheduler XML or script) invoking `python -m tradex.pit.ops run-slot --slot morning|evening --universe-file <path>` at 09:00 ET and 20:30 ET.
4. **Audit and Health Monitoring:** Operational procedures for inspecting `python -m tradex.pit.ops health --universe-file <path>` on trading days.
5. **Gary Approval Gate:** Formal documented authorization before any scheduling task is installed or enabled.

---

## 18. Explicit Gary Decision Required

The following decisions remain exclusively with Gary:
- [ ] **Universe Selection:** Select Candidate C (Dow 30 + Sector ETFs), Candidate B (Dow 30), or another specified universe.
- [ ] **Effective Date:** Determine the operational `effective_from` date for initial capture.
- [ ] **C2 Authorization:** Authorize the start of task `MVP-ARCH-001-R7-PIT-001C2` (Scheduler and Operational Deployment).

---

## 19. Non-Authorization Statement

This task (`MVP-ARCH-001-R7-PIT-001C2-READINESS-A`) is strictly research and design readiness.
- **NO active universe has been selected or activated.**
- **NO scheduler has been installed or configured.**
- **NO C2 implementation work is authorized.**
- **NO changes have been made to production code (`tradex/`).**
- **NO live provider calls or database writes were performed.**
- **`APPROVED_PRODUCTION_STRATEGIES` remains strictly `()`.**
