# MVP-ARCH-001-R6-READINESS: Executable Journal Contract and Implementation Specification

**Task ID:** `MVP-ARCH-001-R6-READINESS`
**Classification:** design/readiness/governance only
**Production trading behavior changed:** no
**Schema changed:** no
**R6 implementation authorized:** no
**Strategy promoted:** no
**R7/R8 authorized:** no
**LONG-002C resumed:** no

**Base SHA:** `cba9ffc76d8aa1feadc47fb3743fb8a3835acbbc` (PR #63 / R5C merge)
**Prerequisite:** Step 5 complete (R5A PR #61, R5B PR #62, R5C PR #63 — all merged)

---

## Purpose

This document provides the implementation-ready executable Journal contract for MVP-ARCH-001 Step 6, so that after review and explicit Gary approval, a separate implementation agent can build R6 **without inventing missing product or data semantics**.

This is not authorization to implement R6. R6 implementation requires a separate Gary-approved PR.

---

## A. Current-State Evidence

This section documents the verified current implementation as of `cba9ffc`.

### A.1 Current Journal UI Behavior

The Signal Journal is rendered as Tab 5 in the transitional 8-surface navigation:

```
Today | Scanner | Confluence | Pre-Market | Signal Journal | Research Lab | Settings | Help
```

**Source:** `tradex/ui/tabs/signal_journal.py`

The Signal Journal tab:
1. Renders an evidence notice (`render_evidence_notice("signal_journal")`) identifying content as legacy signal telemetry.
2. Provides a "Refresh Outcomes Now" button that triggers `run_outcome_pass(verbose=False, provider=provider, settings=settings)` to evaluate unresolved signals whose forward price window has closed.
3. Fetches resolved signals via `store.get_signal_journal(timeframe=..., settings=settings)`.
4. Computes and displays metrics:
   - **Total Signals:** `len(journal)`
   - **Win Rate:** `(len(wins) / len(journal)) * 100` where `outcome_pct > 0`
   - **Avg Win / Avg Loss:** arithmetic means of positive/negative `outcome_pct`
   - **Legacy Expectancy:** `(win_rate * avg_win) + (loss_rate * avg_loss)` — explicitly annotated as descriptive arithmetic over legacy signals, not modeling execution, stops, targets, slippage, or fees.
5. Highlights provider provenance mismatches where `signal_provider != outcome_provider`.
6. Renders Plotly histogram of `outcome_pct` distribution and score-bucket performance stats.

### A.2 Source Tables

**Schema version:** `_SCHEMA_VERSION = 4` (in `tradex/tracker/store.py`)

Legacy signal/outcome data lives in:

| Table | Purpose |
|---|---|
| `signal_history` | One row per qualifying scanner signal: ticker, timeframe, scan_time (UTC ISO8601), score, last_close, volume_ratio, rsi, reasons, provider, outcome_close, outcome_pct, outcome_at, outcome_provider, scan_session_id, trading_date |
| `scan_runs` | Audit surface: run_time, timeframe, tickers_n, hits_n, provider, session_id, status, requested/actual_provider, counts_complete, source |
| `scan_sessions` | Canonical session provenance: session_id (PK), scan_time, trading_date, timeframe, requested/actual_provider, fallback_used, providers_attempted, status, source, observation counts |
| `scan_observations` | Per-ticker observation state: session_id (FK), ticker, status, score, indicators, provider, error info; unique on (session_id, ticker) |

Schema v4 candidate tables:

| Table | Purpose |
|---|---|
| `candidates` | CandidateSnapshot header: candidate_id (PK), contract_version, symbol, decision_timestamp, trading_date, security_identity_version/status, created_at |
| `candidate_evaluations` | Evaluator envelope: evaluation_id (PK), candidate_id (FK CASCADE), evaluator_id, evaluator_version, evidence_state, dimensions (JSON), created_at |
| `candidate_evidence` | Structured PIT provenance: evidence_id (PK), candidate_id (FK CASCADE), evidence_type, source_ref_type/id, provider, observed_at, metadata (JSON), created_at |
| `candidate_reasons` | Explainability: reason_id (PK), candidate_id (FK CASCADE), evaluation_id (FK CASCADE), dimension, reason_code, polarity, severity, human_text, source_evidence_id, created_at |
| `candidate_missing_data` | Missing input records: record_id (PK), candidate_id (FK CASCADE), input_name, data_family, status, evaluation_id, detail, provider, observed_at, created_at |

### A.3 Current Outcome Calculation

**Source:** `tradex/tracker/outcome_tracker.py`

Forward horizon windows (`OUTCOME_WINDOWS`):
- `intraday`: 1 trading session forward
- `short`: 3 trading sessions forward
- `long`: 5 trading sessions forward

Process:
1. `run_outcome_pass` fetches pending signals from `signal_history` where `outcome_close IS NULL AND last_close IS NOT NULL`.
2. For each eligible signal whose window has closed, fetches `outcome_close` via `fetch_daily_history`.
3. Outcome return: `pct = ((outcome_close - last_close) / last_close) * 100`.
4. Updates via `mark_outcome_by_id`.

**Critical limitation:** outcome uses signal `last_close` as reference price, not a next-bar executable entry fill. The 1/3/5-session horizon is generic, not strategy-specific.

### A.4 CandidateSnapshot Identifiers

**Source:** `tradex/candidates/models.py`, `tradex/candidates/aggregator.py`

- `candidate_id`: deterministic SHA-256 hash — `cand_<sha256(session_id\x1fSYMBOL)[:24]>`
- `evaluation_id`: `eval_<sha256(candidate_id\x1fevaluator_id\x1fevaluator_version)[:24]>`
- `evidence_id`: `evid_<sha256(candidate_id\x1fevidence_type)[:24]>`
- `reason_id`: `rsn_<sha256(evaluation_id\x1fdimension\x1freason_code)[:24]>`
- `record_id` (missing data): `miss_<sha256(candidate_id\x1finput_name)[:24]>`

These are **stable, deterministic, auditable identifiers** derived from immutable input tuples. The Journal record will reference `candidate_id` as a foreign key.

### A.5 Strategy-Authorization Registry/Gate

**Source:** `tradex/alerts/eligibility.py`

```python
APPROVED_ACTIONABLE_STRATEGIES: tuple[ApprovedActionableStrategy, ...] = ()
```

The `ApprovedActionableStrategy` dataclass carries `strategy_id`, `strategy_version`, and `description`.

`check_automatic_alert_eligibility` enforces fail-closed gating:
1. Rejects missing `strategy_id` or `strategy_version`.
2. Rejects `evidence_state != "production_approved"`.
3. Rejects `(strategy_id, strategy_version)` not in `APPROVED_ACTIONABLE_STRATEGIES`.

**Current state:** The registry is empty. All automatic alert triggers fail closed.

### A.6 Legacy Telemetry Semantics

The architecture classifies the current Signal Journal as `legacy_signal_telemetry` because:
1. Uses signal close as reference, not the next executable entry fill.
2. Measures later closes at generic 1/3/5-session horizons, not strategy-specific stop/target/expiration.
3. Does not evaluate invalidation, stop, target, or expiration.
4. Expectancy formula is signal telemetry, not executable strategy expectancy.
5. Encourages post-hoc threshold adjustment from uncontrolled observations.

**Source:** `docs/product/MVP-ARCH-001.json` → `journal_outcome_contract.why_current_invalid_for_strategy_proof`

### A.7 Tests Protecting Current Behavior

| Test File | Key Invariants |
|---|---|
| `tests/ui/test_signal_journal_tab.py` | Side-effect-free import; empty state shows "Legacy Signal Telemetry" notice; outcome pass triggered only on button click; metric labels include "Legacy Expectancy"; provider mismatch captions |
| `tests/candidates/test_hard_boundaries.py` | Schema version = 4; `APPROVED_ACTIONABLE_STRATEGIES == ()`; evaluator produces only `context` and `data_confidence` dimensions; no actionable candidate states in snapshot model |
| `tests/product/test_mvp_arch_001.py` | R5C authorization boundaries enforced; candidate contract separates layers; future strategy fields not in snapshot; governance invariants text verified; `r6_implementation_authorized: false` |
| `tests/candidates/test_candidate_queries.py` | Queries make zero provider calls; queries perform zero writes; deterministic tie-breaking; neutral ordering |
| `tests/ui/test_today_tab.py` | No trading CTAs; zero provider calls; zero writes; legacy score disclaimer; mandatory "no production-approved actionable strategy" notice |
| `tests/tracker/test_schema_v4_migration.py` | Fresh DB creates v4; v0→v4, v1→v4, v2→v4, v3→v4 migrations preserve legacy data; future schema version rejected; atomic rollback on failure |
| `tests/candidates/test_candidate_persistence.py` | Round-trip idempotency; immutable conflict detection; atomic child-insert rollback; legacy tables unaffected by candidate writes |

---

## B. Fail-Closed Behavior with No Approved Strategy

### B.1 Recommended Primary Journal Empty State

When `APPROVED_ACTIONABLE_STRATEGIES` is empty (current state and expected state at R6 deployment):

1. **No executable Journal trade record may be automatically created** from legacy Scanner output, shadow candidate evaluations, heuristic scores, or any other existing system.
2. **No legacy signal may be converted or backfilled** into an executable trade record.
3. **No fake plan, fill, stop, target, exit, return, or outcome may be synthesized.**
4. **No unapproved, shadow, or research evaluator may write production executable Journal records.**
5. The `journal_entries` table (proposed in Section K) exists but contains zero rows.

### B.2 Recommended UI Empty-State Message

When the primary Journal surface renders with zero approved strategies:

> **Executable Strategy Journal**
>
> No production-approved executable strategy is currently active. TradeX has no executable strategy Journal records.
>
> Legacy scanner outcomes remain available as descriptive telemetry in the Legacy Scanner Telemetry section and are not actual trade results.

### B.3 Fail-Closed Enforcement Points

The Journal write path must check strategy authorization at record creation time:

1. Validate `strategy_id` and `strategy_version` are non-null and non-empty.
2. Validate `(strategy_id, strategy_version)` exists in the production-approved strategy registry.
3. If validation fails, raise an explicit `JournalAuthorizationError` — do not silently drop the record.
4. Log the rejection with full context for audit.

This gate reuses the same `APPROVED_ACTIONABLE_STRATEGIES` registry and `ApprovedActionableStrategy` dataclass already defined in `tradex/alerts/eligibility.py`, extended to a shared domain boundary.

---

## C. Strategy Authorization Boundary

### C.1 Strategy Identity Representation

```python
strategy_id: str       # e.g., "swing_breakout_v1"
strategy_version: str  # e.g., "1.0.0" (semantic versioning recommended)
```

Both are required, non-null, non-empty strings. Together they form the composite strategy identity `(strategy_id, strategy_version)`.

**Recommendation:** Use semantic versioning (`MAJOR.MINOR.PATCH`) for `strategy_version`. A MAJOR version change indicates incompatible strategy logic changes; MINOR indicates backward-compatible parameter additions; PATCH indicates implementation-only fixes.

### C.2 Authorization Check

A Journal record may be created only when:

1. `strategy_id` and `strategy_version` are both provided and non-empty.
2. The tuple `(strategy_id, strategy_version)` exists in the production-approved strategy registry.
3. The strategy's `evidence_state` is `"production_approved"`.

### C.3 Behavior for Unknown Strategies

If a Journal create request specifies a `(strategy_id, strategy_version)` not present in the approved registry:
- **Reject** the record creation.
- Raise `JournalAuthorizationError` with message: `"Strategy '{strategy_id}:{strategy_version}' is not in the production-approved strategy registry"`.
- Do not create a partial or placeholder record.

### C.4 Behavior for Deprecated Strategy Versions

If a strategy version was previously approved but has been removed from the registry:
- **Existing Journal records** created under that version remain immutable and queryable. Their historical `strategy_id` and `strategy_version` are preserved.
- **New Journal records** cannot be created under the deprecated version.
- **Open Journal records** (state `planned` or `open`) under a deprecated version may still transition to `cancelled` or `closed` to properly resolve their lifecycle, but may not transition to `open` (no new fills).

### C.5 Behavior for Research/Shadow Strategies

Research or shadow strategies (those with `evidence_state != "production_approved"`) **cannot** write to the production `journal_entries` table. Research evaluation telemetry remains in the existing `candidate_evaluations` table with `evidence_state = "exploratory"` or equivalent.

### C.6 Authorization Check Timing

Authorization is checked:
- **At creation:** When a new Journal record enters `planned` state.
- **Not re-checked on lifecycle updates:** Once a record is validly created, state transitions (fill, close, cancel) do not re-validate strategy authorization. This prevents orphaned open records if a strategy is later deprecated.

### C.7 Audit Behavior

Every authorization check (pass or fail) should be logged at INFO level with:
- `strategy_id`, `strategy_version`
- `candidate_id`
- Result (authorized / rejected)
- Reason for rejection if applicable
- Timestamp (UTC)

---

## D. Journal Identity and Candidate Linkage

### D.1 Journal Record Primary Identifier

```
journal_id: TEXT PRIMARY KEY
```

Format: `jrnl_<uuid4_hex>` (e.g., `jrnl_a1b2c3d4e5f6...`)

**Rationale:** UUID-based identifiers are preferred over auto-increment integers for:
- Idempotent creation across distributed processes
- No implicit ordering assumptions from primary key
- Audit-friendly stable references

### D.2 Candidate Relationship

```
candidate_id: TEXT NOT NULL REFERENCES candidates(candidate_id)
```

Every executable Journal record **must** reference an existing, immutable `CandidateSnapshot`. This provides:
- Full point-in-time evidence provenance (what was known when the decision was made)
- Evaluator context (shadow evaluation dimensions, evidence, missing data)
- Provider provenance chain

### D.3 Candidate Decision Timestamp Relationship

The Journal record stores its own `plan_created_at` timestamp (when the plan was created) and carries the referenced candidate's `decision_timestamp` through the foreign key relationship. These are logically distinct:

- `candidates.decision_timestamp`: when the candidate observation was captured (point-in-time)
- `journal_entries.plan_created_at`: when the executable plan was created from that observation

`plan_created_at >= candidates.decision_timestamp` is always true. The gap between them represents deliberation or processing time.

### D.4 Strategy ID/Version Relationship

```
strategy_id: TEXT NOT NULL
strategy_version: TEXT NOT NULL
```

These are stored directly on the Journal record (not via FK to a strategy table) because:
- The approved strategy registry is currently a code-level constant, not a database table.
- Strategy identity must be immutable once persisted on a Journal record, even if the registry changes later.
- Denormalization is appropriate for audit integrity.

### D.5 Uniqueness and Idempotency

**Unique constraint:** `UNIQUE(candidate_id, strategy_id, strategy_version)`

This prevents duplicate Journal records for the same authorized strategy decision on the same candidate. If a create request is received for an existing `(candidate_id, strategy_id, strategy_version)` tuple:
- If the existing record matches materially (same planned prices, same state), return the existing record idempotently.
- If the existing record has different material fields, raise `JournalConflictError`.

This follows the same exact-replay idempotency pattern used by `record_candidate_dossier` in `tradex/candidates/store.py`.

---

## E. Lifecycle / State Machine

### E.1 States

| State | Description |
|---|---|
| `planned` | An executable trade plan has been recorded. Entry, stop, target, and expiration are defined. No fill has occurred. |
| `open` | A fill has been recorded. The position is active with defined stop/target/expiration. |
| `closed` | The position has been exited (stop hit, target hit, expiration, or manual exit). Terminal state. |
| `cancelled` | The plan was cancelled before any fill. Terminal state. |
| `expired` | The plan reached its expiration without being filled. Terminal state. |

### E.2 State Transition Matrix

| From | To | Trigger | Required Fields | Forbidden Mutations |
|---|---|---|---|---|
| `planned` | `open` | Fill recorded | `fill_price`, `fill_timestamp`, `fill_provenance` | Must not change `planned_entry`, `stop_price`, `target_price` |
| `planned` | `cancelled` | Manual cancellation | `cancelled_at`, `cancel_reason` | Must not set fill or exit fields |
| `planned` | `expired` | Expiration time reached without fill | `expired_at` | Must not set fill or exit fields |
| `open` | `closed` | Exit recorded | `exit_price`, `exit_timestamp`, `exit_reason`, `exit_provenance` | Must not change fill fields or planned fields |
| `open` | `cancelled` | Strategy deprecated or invalidated after fill | `cancelled_at`, `cancel_reason` | (emergency only — see E.4) |

### E.3 Forbidden Transitions

| From | To | Reason |
|---|---|---|
| `planned` | `closed` | Cannot close without first filling |
| `cancelled` | any | Terminal state — no transitions out |
| `closed` | any | Terminal state — no transitions out |
| `expired` | any | Terminal state — no transitions out |
| `open` | `planned` | Cannot reverse a fill |
| `open` | `expired` | Open positions are closed, not expired |

### E.4 Impossible History Prevention

1. **Exit before fill:** The `closed` state requires `fill_price IS NOT NULL AND fill_timestamp IS NOT NULL`. Database CHECK constraint enforces this.
2. **Multiple conflicting fills:** Each Journal record supports exactly one fill. If a strategy requires multiple entries (scaling), each must be a separate Journal record referencing the same candidate but with distinct `journal_id`.
3. **Closed without exit data:** `closed` state requires `exit_price IS NOT NULL AND exit_timestamp IS NOT NULL AND exit_reason IS NOT NULL`. CHECK constraint enforces this.
4. **Mutating the plan after execution:** Once a record transitions to `open`, the `planned_entry`, `stop_price`, `target_price`, and `expiration` fields are immutable. Plan amendments (if supported in the future) must create a separate audit record rather than overwriting.

### E.5 Idempotency

State transition requests are idempotent: if a transition request matches the current state and all provided fields match existing values, the operation succeeds without error. If the current state does not match the expected source state, the transition is rejected with `JournalStateError`.

### E.6 Timestamp Ordering Invariants

For any Journal record reaching `closed`:
```
candidates.decision_timestamp
  <= plan_created_at
  <= fill_timestamp (if filled)
  <= exit_timestamp (if closed)
```

These are enforced as validation checks, not database constraints, because timestamp comparison across TEXT columns requires application-level parsing.

---

## F. Planned Trade Contract

### F.1 `planned_entry`

- **Type:** `REAL NOT NULL`
- **Unit:** USD price per share
- **Semantics:** The price at which the strategy intends to enter. For a next-open entry strategy, this is the estimated next-bar open. For a limit entry strategy, this is the limit price.
- **Validation:** Must be positive (`> 0`).
- **Immutability:** Immutable once the record is created. Cannot be amended after creation.

### F.2 `stop_price`

- **Type:** `REAL` (nullable)
- **Unit:** USD price per share
- **Semantics:** The price at which the strategy exits with a loss. NULL if the strategy does not use a hard stop (e.g., time-only exit).
- **Validation:** If non-null, must be positive and less than `planned_entry` (for long-only strategies).
- **Immutability:** Immutable once set. If a strategy needs a trailing stop, the trailing logic is strategy-internal; the Journal records the initial stop and the actual exit.

### F.3 `target_price`

- **Type:** `REAL` (nullable)
- **Unit:** USD price per share
- **Semantics:** The price at which the strategy exits with a profit. NULL if the strategy does not use a hard target (e.g., time-only or trailing exit).
- **Validation:** If non-null, must be positive and greater than `planned_entry` (for long-only strategies).
- **Immutability:** Immutable once set.

### F.4 `expiration`

- **Type:** `TEXT` (nullable, ISO8601 UTC)
- **Unit:** UTC timestamp
- **Semantics:** The point in time after which the plan is no longer valid (for `planned` state) or the position must be exited (for `open` state). NULL if no time-based expiration applies.
- **Validation:** If non-null, must be a valid timezone-aware ISO8601 timestamp. Must be in the future relative to `plan_created_at`.
- **Immutability:** Immutable once set.

### F.5 `invalidation_rule`

- **Type:** `TEXT` (nullable)
- **Unit:** Human-readable rule description
- **Semantics:** A textual description of conditions under which the trade plan becomes invalid (e.g., "Close below 50-day MA", "Gap down >3% from planned entry"). This is a descriptive field, not an automatically evaluated rule.
- **Validation:** If non-null, must be non-empty string.
- **Immutability:** Immutable once set.

### F.6 Strategy-Specific vs. Generic Nullability

The database schema allows `stop_price`, `target_price`, `expiration`, and `invalidation_rule` to be NULL because not every future strategy necessarily uses all four concepts. However, each approved strategy's definition should specify which of these fields are required for that strategy. Strategy-level validation (which fields are required vs. optional) is enforced at the service layer, not by database constraints alone.

### F.7 Plan Amendments

**Recommendation:** Plan amendments are **not supported** in R6. Once a Journal record is created, its planned fields are immutable. If a strategy requires plan modification (e.g., adjusting a stop), the current record should be cancelled and a new record created.

**Rationale:** Immutable plans preserve audit integrity and prevent post-hoc rationalization of trade parameters. If plan amendments are needed in a future version, they should be implemented as a separate `journal_amendments` audit table recording the old and new values with timestamps, rather than overwriting fields on `journal_entries`.

---

## G. Actual Execution Contract

### G.1 `fill_price`

- **Type:** `REAL` (nullable — null until filled)
- **Unit:** USD price per share
- **Semantics:** The price at which the position was actually opened.
- **Validation:** Must be positive when set.
- **Immutability:** Immutable once set.

### G.2 `fill_timestamp`

- **Type:** `TEXT` (nullable — null until filled, ISO8601 UTC)
- **Semantics:** The UTC timestamp when the fill was observed or recorded.
- **Validation:** Must be timezone-aware ISO8601. Must be >= `plan_created_at`. Must be <= `expiration` if expiration is set and the record was not expired.
- **Immutability:** Immutable once set.

### G.3 `exit_price`

- **Type:** `REAL` (nullable — null until closed)
- **Unit:** USD price per share
- **Semantics:** The price at which the position was actually closed.
- **Validation:** Must be positive when set.
- **Immutability:** Immutable once set.

### G.4 `exit_timestamp`

- **Type:** `TEXT` (nullable — null until closed, ISO8601 UTC)
- **Semantics:** The UTC timestamp when the exit was observed or recorded.
- **Validation:** Must be timezone-aware ISO8601. Must be >= `fill_timestamp`.
- **Immutability:** Immutable once set.

### G.5 `exit_reason`

- **Type:** `TEXT` (nullable — null until closed)
- **Semantics:** Why the position was exited. Recommended enum values:
  - `stop_hit` — stop price was reached
  - `target_hit` — target price was reached
  - `expiration` — holding period expired
  - `invalidation` — invalidation rule triggered
  - `manual` — manually exited by user
  - `strategy_deprecated` — strategy version was deprecated while position was open
- **Validation:** Must be one of the recognized values when set.
- **Immutability:** Immutable once set.

### G.6 Execution Provenance

TradeX is **not currently a brokerage execution system**. The R6 contract does not assume fills are brokerage-confirmed.

```
fill_provenance: TEXT NOT NULL DEFAULT 'manual'
exit_provenance: TEXT NOT NULL DEFAULT 'manual'
```

Recommended provenance values:
- `manual` — manually recorded by user
- `simulated` — derived from market data observation (e.g., price crossed planned entry level)
- `broker_confirmed` — future: confirmed by brokerage API

**Critical design rule:** The Journal must never claim `broker_confirmed` provenance without actual brokerage integration delivering confirmation data. R6 does not authorize brokerage integration.

---

## H. Costs and Return Semantics

### H.1 `slippage_and_costs`

- **Type:** `REAL` (nullable — null until position is closed)
- **Unit:** USD total per share (positive value represents cost)
- **Semantics:** Combined slippage and transaction costs per share. Includes:
  - Entry slippage: `|fill_price - planned_entry|`
  - Exit slippage: estimated or actual
  - Commission costs: per-share or per-trade amortized
- **Formula:** `slippage_and_costs = entry_slippage + exit_slippage + commissions_per_share`
- **Sign convention:** Positive means cost (reduces return). A negative value would mean favorable slippage (fill better than planned).
- **When valid:** Only after `closed` state is reached.
- **Stored, not derived:** Stored at close time to preserve the exact calculation context. May reference strategy-specific slippage assumptions.

### H.2 `net_return`

- **Type:** `REAL` (nullable — null until position is closed)
- **Unit:** Percentage (e.g., `2.5` means +2.5%)
- **Formula:** `net_return = ((exit_price - fill_price) / fill_price) * 100 - (slippage_and_costs / fill_price) * 100`
- **Sign convention:** Positive is profit, negative is loss.
- **When valid:** Only after `closed` state is reached with valid `fill_price`, `exit_price`, and `slippage_and_costs`.
- **Stored, not derived:** Stored at close time. Can be recomputed for verification but the stored value is authoritative for the strategy version's cost model.

### H.3 `strategy_drawdown`

- **Type:** `REAL` (nullable — null until position is closed)
- **Unit:** Percentage
- **Semantics:** Maximum adverse excursion (MAE) during the holding period, expressed as percentage from fill price. Represents the worst-case intra-trade drawdown.
- **Formula:** `strategy_drawdown = ((fill_price - lowest_low_during_hold) / fill_price) * 100`
- **When valid:** Only after `closed` state. Requires intra-holding-period price data to compute.
- **Missing-data handling:** If intra-period OHLCV data is unavailable or incomplete, `strategy_drawdown` must be NULL rather than estimated. The `outcome_confidence` field (H.4) reflects this data gap.

### H.4 `outcome_confidence`

- **Type:** `TEXT NOT NULL DEFAULT 'unknown'`
- **Semantics:** Assessment of the data completeness and reliability of the outcome calculation. Recommended values:
  - `complete` — all required data (fill, exit, intra-period OHLCV, costs) was available
  - `partial` — some data was missing (e.g., no intra-period data for drawdown)
  - `estimated` — fill or exit prices were simulated, not broker-confirmed
  - `unknown` — insufficient data to assess confidence
- **When set:** Updated when the record reaches `closed` state.

### H.5 MFE, MAE, Holding Period, Benchmark, Regime

Per approved architecture review:

- **MFE (Maximum Favorable Excursion):** Not currently an approved R6 requirement. If intra-period OHLCV data is captured, MFE can be computed as: `((highest_high_during_hold - fill_price) / fill_price) * 100`. This is identified as a **future/non-R6 concept** that can be added to the schema additively when approved.
- **MAE (Maximum Adverse Excursion):** Captured via `strategy_drawdown` (Section H.3).
- **Holding period:** Can be derived from `fill_timestamp` and `exit_timestamp`. Not stored as a separate field because it is trivially computable and storing it would create a consistency risk.
- **Benchmark context (e.g., SPY return over same period):** Not currently an approved R6 requirement. Identified as a **future/non-R6 concept**.
- **Regime context (market regime during trade):** Not currently an approved R6 requirement. Identified as a **future/non-R6 concept**.

These future concepts can be added as nullable columns in a subsequent additive schema migration without modifying R6 schema.

---

## I. Provider and Data Provenance

### I.1 Minimum Provenance Requirements

Every Journal record carries provenance through two mechanisms:

**1. CandidateSnapshot provenance (via `candidate_id` FK):**
The referenced `CandidateSnapshot` already captures:
- `candidate_evidence` rows with `provider`, `evidence_type`, `source_ref_type`, `source_ref_id`, `observed_at`
- `candidate_missing_data` rows documenting what was unknown at decision time
- `candidate_evaluations` with `evaluator_id`, `evaluator_version`, `evidence_state`

This provides full provenance for the *decision* that led to the planned trade.

**2. Journal-level provenance fields:**

| Field | Provenance For |
|---|---|
| `fill_provenance` | How the fill was observed (`manual`, `simulated`, `broker_confirmed`) |
| `exit_provenance` | How the exit was observed (`manual`, `simulated`, `broker_confirmed`) |
| `outcome_provider` | Provider used for outcome price data (e.g., `schwab`, `yahoo`) |

### I.2 Raw Provider Identity Preservation

Provider identity must be the raw provider name (e.g., `schwab`, `yahoo`, `alpaca`), not a display decoration or fallback label. The display layer may format this (e.g., "schwab · Fallback") but the persisted value must be the raw provider string.

### I.3 Missing or Unknown Provenance

If provenance is unknown at write time:
- `fill_provenance` defaults to `'manual'` (the conservative assumption).
- `exit_provenance` defaults to `'manual'`.
- `outcome_provider` defaults to `'unknown'`.

Unknown provenance must **remain visibly unknown** in the UI rather than being silently displayed as confirmed.

---

## J. Timestamp, Timezone, and Market-Calendar Semantics

### J.1 UTC Persistence

All timestamps in `journal_entries` are persisted as **ISO8601 UTC strings** (e.g., `"2026-08-26T14:30:00+00:00"`). This matches the existing convention in `candidates`, `signal_history`, `scan_sessions`, and `scan_observations`.

### J.2 Timezone-Aware Validation

All timestamp fields reject naive datetimes. The Python domain layer must normalize to UTC via `_normalize_aware_dt()` (from `tradex/candidates/models.py`) or equivalent.

### J.3 America/New_York Display

For UI display, timestamps should be converted to `America/New_York` (ET) using `normalize_market_datetime()` from `tradex/market/hours.py`, consistent with the Today tab's `_format_market_time()` helper in `tradex/candidates/queries.py`.

Format: `"%b %d, %Y %I:%M %p ET"` (e.g., "Aug 26, 2026 10:30 AM ET")

### J.4 Specific Timestamp Fields

| Field | Timezone | Description |
|---|---|---|
| `plan_created_at` | UTC (persisted), ET (displayed) | When the executable plan was created |
| `fill_timestamp` | UTC (persisted), ET (displayed) | When the fill was observed |
| `exit_timestamp` | UTC (persisted), ET (displayed) | When the exit was observed |
| `cancelled_at` | UTC (persisted), ET (displayed) | When the plan/position was cancelled |
| `expired_at` | UTC (persisted), ET (displayed) | When the plan expired without fill |
| `updated_at` | UTC (persisted) | Last state-change timestamp |

### J.5 `trading_date` Derivation

The Journal record's `trading_date` is derived from `plan_created_at` using `derive_trading_date()` from `tradex/candidates/models.py`, which:
1. Converts to America/New_York.
2. Checks `is_trading_day()` via the XNYS exchange calendar.
3. Returns `YYYY-MM-DD` string or `None` for non-trading days.

Plans created on non-trading days have `trading_date = NULL`.

### J.6 Expiration Semantics

If `expiration` is set:
- For `planned` records: the plan automatically transitions to `expired` state when `expiration` is reached and no fill has occurred.
- For `open` records: the position must be exited by `expiration`. The exit reason is `"expiration"`.
- Expiration checks should account for market hours — an expiration of "end of next trading day" means 4:00 PM ET on the next XNYS trading day.

### J.7 Non-Trading Days and DST

- Plans and fills should only reference trading-day market hours for fill/exit timestamps.
- `plan_created_at` may fall on a non-trading day (e.g., Sunday planning), but `fill_timestamp` and `exit_timestamp` should fall within market hours on trading days.
- DST transitions are handled by the `America/New_York` timezone conversion — UTC persistence ensures no ambiguity.
- The `is_trading_day()` function from `tradex/market/hours.py` uses the `exchange_calendars` XNYS calendar, which accounts for holidays and half-days.

### J.8 Same-Bar / Same-Timestamp Ambiguity

If two Journal events have identical timestamps (e.g., fill and exit on the same bar due to gap-through-stop):
- Both are recorded with their actual timestamps.
- The `exit_reason` clarifies the sequence (e.g., `"stop_hit"` on gap open).
- Application logic determines event ordering by state machine rules, not timestamp comparison alone.

---

## K. Proposed Persistence Design

### K.1 Schema Version

**Proposed:** Schema v5 (additive migration from v4)

**Verification:** This is consistent with the existing migration pattern:
- v1→v2: added scan session/observation tables
- v2→v3: extended scan_runs audit surface
- v3→v4: added candidate tables (R5A)
- v4→v5: adds journal_entries table (R6)

Each migration is additive — no existing tables or columns are modified or deleted.

### K.2 Proposed Table: `journal_entries`

```sql
CREATE TABLE IF NOT EXISTS journal_entries (
    journal_id          TEXT    PRIMARY KEY,
    candidate_id        TEXT    NOT NULL REFERENCES candidates(candidate_id),
    strategy_id         TEXT    NOT NULL,
    strategy_version    TEXT    NOT NULL,
    symbol              TEXT    NOT NULL,
    trading_date        TEXT,

    -- Lifecycle
    state               TEXT    NOT NULL DEFAULT 'planned'
                        CHECK (state IN ('planned', 'open', 'closed', 'cancelled', 'expired')),

    -- Planned trade
    planned_entry       REAL    NOT NULL CHECK (planned_entry > 0),
    stop_price          REAL    CHECK (stop_price IS NULL OR stop_price > 0),
    target_price        REAL    CHECK (target_price IS NULL OR target_price > 0),
    expiration          TEXT,
    invalidation_rule   TEXT,

    -- Execution
    fill_price          REAL    CHECK (fill_price IS NULL OR fill_price > 0),
    fill_timestamp      TEXT,
    fill_provenance     TEXT    NOT NULL DEFAULT 'manual',
    exit_price          REAL    CHECK (exit_price IS NULL OR exit_price > 0),
    exit_timestamp      TEXT,
    exit_reason         TEXT    CHECK (exit_reason IS NULL OR exit_reason IN (
                            'stop_hit', 'target_hit', 'expiration',
                            'invalidation', 'manual', 'strategy_deprecated')),
    exit_provenance     TEXT    NOT NULL DEFAULT 'manual',

    -- Outcome
    slippage_and_costs  REAL,
    net_return          REAL,
    strategy_drawdown   REAL,
    outcome_confidence  TEXT    NOT NULL DEFAULT 'unknown'
                        CHECK (outcome_confidence IN ('complete', 'partial', 'estimated', 'unknown')),
    outcome_provider    TEXT,

    -- Timestamps
    plan_created_at     TEXT    NOT NULL,
    cancelled_at        TEXT,
    expired_at          TEXT,
    updated_at          TEXT    NOT NULL,

    -- Consistency constraints
    CHECK (
        (state != 'open' AND state != 'closed')
        OR (fill_price IS NOT NULL AND fill_timestamp IS NOT NULL)
    ),
    CHECK (
        state != 'closed'
        OR (exit_price IS NOT NULL AND exit_timestamp IS NOT NULL AND exit_reason IS NOT NULL)
    ),
    CHECK (
        state != 'cancelled'
        OR cancelled_at IS NOT NULL
    ),
    CHECK (
        state != 'expired'
        OR expired_at IS NOT NULL
    ),

    UNIQUE (candidate_id, strategy_id, strategy_version)
);
```

### K.3 Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_je_candidate ON journal_entries(candidate_id);
CREATE INDEX IF NOT EXISTS idx_je_strategy ON journal_entries(strategy_id, strategy_version);
CREATE INDEX IF NOT EXISTS idx_je_symbol ON journal_entries(symbol);
CREATE INDEX IF NOT EXISTS idx_je_state ON journal_entries(state);
CREATE INDEX IF NOT EXISTS idx_je_trading_date ON journal_entries(trading_date);
CREATE INDEX IF NOT EXISTS idx_je_plan_created ON journal_entries(plan_created_at);
```

### K.4 Migration from v4 to v5

```python
def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Additive v4→v5 migration: create journal_entries table."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS journal_entries ( ... );  -- full DDL from K.2
        CREATE INDEX IF NOT EXISTS idx_je_candidate ON journal_entries(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_je_strategy ON journal_entries(strategy_id, strategy_version);
        CREATE INDEX IF NOT EXISTS idx_je_symbol ON journal_entries(symbol);
        CREATE INDEX IF NOT EXISTS idx_je_state ON journal_entries(state);
        CREATE INDEX IF NOT EXISTS idx_je_trading_date ON journal_entries(trading_date);
        CREATE INDEX IF NOT EXISTS idx_je_plan_created ON journal_entries(plan_created_at);
        PRAGMA user_version = 5;
    """)
```

This migration:
- Creates a new table without modifying any existing tables.
- Preserves all legacy `signal_history`, `scan_sessions`, `scan_observations`, `scan_runs`, and `candidates` data untouched.
- Is idempotent via `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.

### K.5 Upgrade Path from v4

The migration is triggered by `store.init()` detecting `PRAGMA user_version = 4`:
1. Begin transaction.
2. Execute `_migrate_v4_to_v5`.
3. Set `PRAGMA user_version = 5`.
4. Commit.
5. On failure: rollback, leave at v4.

### K.6 Idempotent Initialization

A fresh database at v5 creates all tables (v1 through v5) in a single pass. The `journal_entries` table is empty on fresh initialization.

### K.7 Rollback Strategy

If R6 needs to be rolled back:
1. Revert the code to the pre-R6 version.
2. The `journal_entries` table remains in the database but is unused.
3. `_SCHEMA_VERSION` check in the reverted code: the existing v4 code rejects `user_version > 4`, so the reverted code would need a minor patch to accept v5 (with the `journal_entries` table dormant) or the database `user_version` would need to be set back to 4.

**Recommended rollback approach:** The reverted code should tolerate `user_version = 5` by checking `user_version <= 5` instead of `user_version <= 4`, but skip any journal-related logic. The `journal_entries` table remains empty and inert.

### K.8 Legacy Table Preservation

All existing tables and their data are preserved unchanged:
- `signal_history` — all rows remain, semantics unchanged
- `scan_runs` — all rows remain
- `scan_sessions` — all rows remain
- `scan_observations` — all rows remain
- `candidates` and child tables — all rows remain
- No columns are added, removed, or renamed on any existing table
- No data is backfilled, migrated, or reinterpreted

---

## L. Proposed Persistence/Service Interfaces

### L.1 `create_journal_entry`

```python
def create_journal_entry(
    *,
    candidate_id: str,
    strategy_id: str,
    strategy_version: str,
    planned_entry: float,
    stop_price: float | None = None,
    target_price: float | None = None,
    expiration: datetime | None = None,
    invalidation_rule: str | None = None,
    plan_created_at: datetime | None = None,  # defaults to utcnow
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry:
    """Create a new Journal entry in 'planned' state.

    Authorization:
        Validates (strategy_id, strategy_version) against the
        production-approved strategy registry. Raises
        JournalAuthorizationError if the strategy is not approved.

    Idempotency:
        If a record already exists for (candidate_id, strategy_id,
        strategy_version) with matching material fields, returns the
        existing record. If material fields conflict, raises
        JournalConflictError.

    Transactionality:
        The entire operation runs in a single SQLite transaction.
        On failure, the database is unchanged.

    Returns:
        The created (or existing idempotent) JournalEntry.

    Raises:
        JournalAuthorizationError: strategy not in approved registry
        JournalConflictError: duplicate with divergent fields
        JournalValidationError: invalid field values
        StoreError: database operational failure
    """
```

### L.2 `record_fill`

```python
def record_fill(
    *,
    journal_id: str,
    fill_price: float,
    fill_timestamp: datetime,
    fill_provenance: str = "manual",
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry:
    """Record a fill on an existing 'planned' Journal entry, transitioning to 'open'.

    Preconditions:
        - Entry must be in 'planned' state.
        - fill_price > 0
        - fill_timestamp >= plan_created_at

    Idempotency:
        If the record is already 'open' with matching fill fields,
        returns the existing record.

    Raises:
        JournalStateError: entry not in 'planned' state
        JournalValidationError: invalid field values
        StoreError: database failure
    """
```

### L.3 `record_cancellation`

```python
def record_cancellation(
    *,
    journal_id: str,
    cancel_reason: str,
    cancelled_at: datetime | None = None,  # defaults to utcnow
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry:
    """Cancel a Journal entry, transitioning from 'planned' or 'open' to 'cancelled'.

    Preconditions:
        - Entry must be in 'planned' or 'open' state.
        - cancel_reason must be non-empty.

    Idempotency:
        If already 'cancelled' with matching reason, returns existing.

    Raises:
        JournalStateError: entry in terminal state
        JournalValidationError: invalid fields
        StoreError: database failure
    """
```

### L.4 `record_expiration`

```python
def record_expiration(
    *,
    journal_id: str,
    expired_at: datetime | None = None,  # defaults to utcnow
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry:
    """Expire a 'planned' Journal entry that was not filled before expiration.

    Preconditions:
        - Entry must be in 'planned' state.
        - Entry must have a non-null expiration timestamp.

    Raises:
        JournalStateError: entry not in 'planned' state
        JournalValidationError: no expiration set
        StoreError: database failure
    """
```

### L.5 `record_exit`

```python
def record_exit(
    *,
    journal_id: str,
    exit_price: float,
    exit_timestamp: datetime,
    exit_reason: str,
    exit_provenance: str = "manual",
    slippage_and_costs: float | None = None,
    net_return: float | None = None,
    strategy_drawdown: float | None = None,
    outcome_confidence: str = "unknown",
    outcome_provider: str | None = None,
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry:
    """Record an exit on an 'open' Journal entry, transitioning to 'closed'.

    Preconditions:
        - Entry must be in 'open' state.
        - exit_price > 0
        - exit_timestamp >= fill_timestamp
        - exit_reason must be a recognized value

    Outcome calculation:
        If slippage_and_costs and net_return are not provided, they
        may be computed from fill_price, exit_price, and strategy-
        specific cost assumptions if available.

    Raises:
        JournalStateError: entry not in 'open' state
        JournalValidationError: invalid fields
        StoreError: database failure
    """
```

### L.6 `get_journal_entries`

```python
def get_journal_entries(
    *,
    state: str | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    trading_date: str | None = None,
    limit: int | None = None,
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> list[JournalEntry]:
    """Fetch Journal entries with optional filters.

    Ordering: plan_created_at DESC, journal_id ASC (neutral, non-ranked).

    Returns empty list if no entries match or no approved strategies exist.
    """
```

### L.7 `get_journal_entry`

```python
def get_journal_entry(
    journal_id: str,
    *,
    db_path: str | Path | None = None,
    settings: TradeXSettings | None = None,
) -> JournalEntry | None:
    """Fetch a single Journal entry by ID. Returns None if not found."""
```

### L.8 `validate_strategy_authorization`

```python
def validate_strategy_authorization(
    strategy_id: str,
    strategy_version: str,
) -> bool:
    """Check if (strategy_id, strategy_version) is in the approved registry.

    Returns True if authorized, False otherwise.
    Does not raise on unauthorized — callers choose error behavior.
    """
```

### L.9 Domain Model

```python
@dataclass(frozen=True)
class JournalEntry:
    """Immutable representation of an executable Journal record."""

    journal_id: str
    candidate_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    trading_date: str | None
    state: str  # planned | open | closed | cancelled | expired

    # Planned trade
    planned_entry: float
    stop_price: float | None
    target_price: float | None
    expiration: datetime | None
    invalidation_rule: str | None

    # Execution
    fill_price: float | None
    fill_timestamp: datetime | None
    fill_provenance: str
    exit_price: float | None
    exit_timestamp: datetime | None
    exit_reason: str | None
    exit_provenance: str

    # Outcome
    slippage_and_costs: float | None
    net_return: float | None
    strategy_drawdown: float | None
    outcome_confidence: str
    outcome_provider: str | None

    # Timestamps
    plan_created_at: datetime
    cancelled_at: datetime | None
    expired_at: datetime | None
    updated_at: datetime
```

### L.10 Error Types

```python
class JournalError(Exception):
    """Base exception for Journal operations."""

class JournalAuthorizationError(JournalError):
    """Strategy not in approved registry."""

class JournalConflictError(JournalError):
    """Duplicate entry with divergent material fields."""

class JournalStateError(JournalError):
    """Invalid state transition attempted."""

class JournalValidationError(JournalError):
    """Invalid field values."""
```

---

## M. Primary Journal UI Contract

### M.1 Page Title

**Primary tab label:** `"Journal"` (replaces `"Signal Journal"` as the primary journal surface)

**Subheader:** `"Executable Strategy Journal"`

### M.2 Truthful Explanatory Caption

> Records planned and executed trades from production-approved strategies. Each entry links to an immutable candidate snapshot capturing what was known at decision time.

### M.3 Empty State — No Approved Strategy

When `APPROVED_ACTIONABLE_STRATEGIES` is empty:

> **Executable Strategy Journal**
>
> No production-approved executable strategy is currently active. TradeX has no executable strategy Journal records.
>
> Legacy scanner outcomes remain available as descriptive telemetry in the Legacy Scanner Telemetry section and are not actual trade results.

This empty state must be rendered with an evidence notice (`render_evidence_notice("journal")`) consistent with the existing evidence-notice system.

### M.4 Empty State — Approved Strategy, No Records

When an approved strategy exists but no Journal records have been created:

> **Executable Strategy Journal**
>
> Strategy "{strategy_id} v{strategy_version}" is approved and active. No trade plans have been recorded yet.

### M.5 Table Columns — Overview

| Column | Source | Present for `planned` | Present for `open` | Present for `closed` |
|---|---|---|---|---|
| Symbol | `symbol` | ✓ | ✓ | ✓ |
| State | `state` badge | ✓ | ✓ | ✓ |
| Strategy | `strategy_id:strategy_version` | ✓ | ✓ | ✓ |
| Planned Entry | `planned_entry` | ✓ | ✓ | ✓ |
| Fill | `fill_price` | — | ✓ | ✓ |
| Stop | `stop_price` | ✓ | ✓ | ✓ |
| Target | `target_price` | ✓ | ✓ | ✓ |
| Exit | `exit_price` | — | — | ✓ |
| Exit Reason | `exit_reason` | — | — | ✓ |
| Net Return | `net_return` (%) | — | — | ✓ |
| Plan Date | `plan_created_at` (ET) | ✓ | ✓ | ✓ |

### M.6 Journal Detail Fields

Clicking a Journal row shows full detail:

- **Header:** Symbol, State badge, Strategy ID:Version
- **Plan:** Planned Entry, Stop, Target, Expiration, Invalidation Rule
- **Execution:** Fill Price, Fill Time (ET), Fill Provenance
- **Exit:** Exit Price, Exit Time (ET), Exit Reason, Exit Provenance
- **Outcome:** Net Return, Slippage & Costs, Strategy Drawdown, Outcome Confidence, Outcome Provider
- **Provenance:** Link to Candidate Detail (candidate_id), Plan Created (ET)
- **Audit:** Journal ID, Updated At (UTC)

### M.7 Status Presentation

State badges should use consistent visual styling:
- `planned` — neutral/blue
- `open` — active/amber
- `closed` — resolved (green for profit, red for loss, neutral for zero)
- `cancelled` — grey
- `expired` — grey

### M.8 Strategy ID/Version Visibility

Strategy identity must be visible on every Journal record. Format: `"{strategy_id} v{strategy_version}"`.

### M.9 Missing/Unknown Data Treatment

- Null numeric fields display as `"—"` (em-dash), never `0` or blank.
- Unknown provenance displays as `"Unknown"`, not as a provider name.
- `outcome_confidence = "estimated"` or `"partial"` should display a visible indicator (e.g., ⚠️) so users know the outcome is not fully confirmed.

### M.10 Realized vs. Planned Distinction

The UI must clearly distinguish between planned values and realized values:
- Planned Entry vs. Fill Price
- Target/Stop vs. actual Exit Price
- The visual layout should make it obvious when a fill differs significantly from the plan.

### M.11 Legacy Score Exclusion

The Journal UI must **not** display legacy heuristic Scanner scores, RSI, volume ratio, or coil counts as if they are validated trade rankings. The candidate detail drill-down (via candidate_id link) already displays these with appropriate disclaimers.

---

## N. Legacy Telemetry Disposition

### N.1 Where Legacy Signal Journal Goes

**Recommendation:** The current Signal Journal content moves to a secondary section within the **Research Lab** tab, labeled:

> **Legacy Scanner Telemetry**

### N.2 Implementation

The existing `render_signal_journal_tab()` function is preserved with minimal changes:
1. Rename the surface from "Signal Journal" to "Legacy Scanner Telemetry".
2. Add or strengthen the evidence notice to clearly state these are not executable trade results.
3. Move the render call from the primary Journal tab to a section within Research Lab.

The existing `tradex/ui/tabs/signal_journal.py` module is **not deleted** — it is reused in its new location.

### N.3 Existing Data Preservation

- `signal_history` table rows remain untouched.
- `scan_runs`, `scan_sessions`, `scan_observations` remain untouched.
- Outcome tracker code (`tradex/tracker/outcome_tracker.py`) remains functional for legacy telemetry refresh.
- The "Refresh Outcomes Now" button remains available in the Legacy Scanner Telemetry section.

### N.4 Legacy Labeling Requirements

- The heading must include "Legacy" to distinguish from the executable Journal.
- The evidence notice must state that legacy expectancy is descriptive arithmetic over generic forward returns, not executable strategy results.
- Win rate, avg win/loss, and expectancy metrics remain visible but clearly scoped as legacy telemetry.
- Legacy forward returns (1/3/5-session) are never relabeled as trade results.

### N.5 Legacy Expectancy Treatment

The existing expectancy calculation remains accessible but must be labeled:

> **Legacy Expectancy (Descriptive Only):** This metric is arithmetic over generic 1/3/5-session forward returns from legacy scanner signals. It does not model order execution, stops, profit targets, slippage, or transaction fees. It is not a validated measure of strategy edge.

### N.6 Primary Journal Dominance

After R6, the primary `"Journal"` tab shows only executable strategy records. Legacy telemetry does not appear in the primary Journal tab, its metrics, or its empty states.

### N.7 Navigation Change

The 8-tab navigation becomes:

```
Today | Scanner | Confluence | Pre-Market | Journal | Research Lab | Settings | Help
```

Note: `"Signal Journal"` is replaced by `"Journal"`. The tab label changes from `"Signal Journal"` to `"Journal"`.

Legacy Scanner Telemetry is accessible within Research Lab alongside other research tools (Coil Context, Pattern Similarity — Rejected, Options Activity — Exploratory).

---

## O. Failure and Edge Cases

### O.1 Duplicate Create Requests

If `create_journal_entry` is called with a `(candidate_id, strategy_id, strategy_version)` that already exists:
- **Matching material fields:** Return existing record (idempotent success).
- **Divergent material fields:** Raise `JournalConflictError`.

### O.2 Repeated Fill/Exit Updates

If `record_fill` is called on an already-open record with matching fill fields: idempotent success. With different fill fields: raise `JournalConflictError`. If called on a record not in `planned` state: raise `JournalStateError`.

Same pattern for `record_exit`: idempotent on matching, conflict on divergent, state error on wrong state.

### O.3 Partial Data

If a Journal record reaches `closed` but some outcome fields (e.g., `strategy_drawdown`) cannot be computed:
- Set the computable fields and leave others NULL.
- Set `outcome_confidence = "partial"`.
- Never synthesize missing data.

### O.4 Unknown Provider

If `outcome_provider` is unknown at close time:
- Store `"unknown"` explicitly.
- Display as "Unknown" in the UI with a visible indicator.

### O.5 Missing CandidateSnapshot

If `create_journal_entry` references a `candidate_id` that does not exist in the `candidates` table:
- Raise `JournalValidationError`: "Referenced candidate_id does not exist."
- The foreign key constraint (`REFERENCES candidates(candidate_id)`) also prevents insertion at the database level.

### O.6 Unknown Strategy

Handled by authorization check (Section C.3): raise `JournalAuthorizationError`.

### O.7 De-authorized Strategy Version

Handled by Section C.4: existing records preserved, new records blocked, open records may transition to cancelled/closed but not to open.

### O.8 Invalid State Transitions

Handled by state machine (Section E.3): raise `JournalStateError` with descriptive message indicating current state and attempted transition.

### O.9 Out-of-Order Timestamps

If `fill_timestamp < plan_created_at` or `exit_timestamp < fill_timestamp`:
- Raise `JournalValidationError`: "Timestamp ordering violation: {field} cannot precede {earlier_field}."

### O.10 Non-Trading Days

Plans may be created on non-trading days (`trading_date = NULL`). Fills and exits should occur on trading days during market hours, but this is validated at the service layer, not enforced by database constraints, because after-hours and pre-market scenarios may be valid for some future strategies.

### O.11 DST Transitions

Handled by UTC persistence. All timestamps are stored in UTC. America/New_York display conversion handles DST automatically via `normalize_market_datetime()`.

### O.12 Database Transaction Failure

All state-changing operations run within SQLite transactions. On failure:
- The transaction is rolled back.
- The database state is unchanged.
- `StoreError` is raised with the underlying error message.

### O.13 Process Crash During Update

SQLite's WAL journal mode provides crash recovery. Incomplete transactions are rolled back on next connection. The Journal record remains in its pre-transition state.

### O.14 Multiple App Processes

SQLite's file-level locking prevents concurrent writes. In a multi-process scenario:
- One process holds the write lock; others queue.
- Idempotency ensures that retries after lock timeouts produce correct results.
- The `busy_timeout` should be set to a reasonable value (e.g., 5000ms).

### O.15 Legacy v4 Database Upgrade

The v4→v5 migration runs automatically on `store.init()`. It is additive and does not modify any v4 data. If the migration fails:
- The database remains at v4.
- The Journal service is unavailable, but all other features continue to work.
- The failure is logged with full context.

### O.16 Fresh Database Initialization

A fresh database creates all tables (v1 through v5) in a single pass. The `journal_entries` table is empty. All other tables are empty. This is the expected state for new installations.

### O.17 Malformed Old Data

Legacy `signal_history` rows with NULL `scan_time`, empty `ticker`, or other data quality issues are **not touched** by the R6 migration. They remain in `signal_history` as-is. The Journal system does not read from `signal_history`.

### O.18 No Approved Strategies

The Journal tab renders the empty-state message (Section M.3). The `journal_entries` table is empty. No error is raised — this is the normal expected state until a strategy is approved.

### O.19 No Journal Rows (With Approved Strategy)

The Journal tab renders the "approved but no records" empty state (Section M.4). This is not an error condition.

### O.20 Closed Trades with Missing Outcome Context

If a trade is closed but intra-period OHLCV data is unavailable for drawdown calculation:
- `strategy_drawdown = NULL`
- `outcome_confidence = "partial"`
- `net_return` is still computed from fill and exit prices if available.

### O.21 Stale Provider Data

If the provider used for outcome resolution returns stale or delayed data:
- Record the `outcome_provider` as-is.
- Set `outcome_confidence = "estimated"` if the data staleness is detectable.
- Do not silently upgrade confidence.

---

## P. Research-Integrity Boundaries

### P.1 Explicit Statements

The following boundaries must be enforced and documented:

1. **Executable Journal data is not proof of strategy edge.** Recording trades in the Journal demonstrates execution tracking, not validation of the underlying strategy's alpha.

2. **Legacy scanner outcomes cannot be used as if they were actual fills.** The `signal_history` table contains generic forward returns from signal close prices at 1/3/5-session horizons. These are descriptive telemetry, not execution records.

3. **No holdout optimization is introduced by R6.** R6 does not optimize any parameters, thresholds, or weights based on Journal outcome data. The Journal is a recording system, not an optimization loop.

4. **No strategy is promoted by R6.** R6 creates the infrastructure for recording executable trades. It does not add any entry to `APPROVED_ACTIONABLE_STRATEGIES`. Strategy promotion requires a separate, explicitly Gary-approved PR with full research protocol compliance.

5. **No "best" strategy is selected.** R6 does not rank, compare, or recommend strategies. If multiple strategies are eventually approved, each operates independently in the Journal.

6. **No R6 outcome should retroactively alter the CandidateSnapshot.** Journal records reference candidates via immutable foreign key. The candidate's evidence, evaluations, reasons, and missing data remain frozen at their point-in-time values regardless of trade outcome.

7. **Research/shadow results remain separate from production executable Journal data.** Shadow evaluator output (`evidence_state = "exploratory"`) in `candidate_evaluations` is never mixed with Journal records. The Journal writes only for `production_approved` strategies.

8. **No saved user weights or legacy heuristic scores are treated as strategy configuration.** The `~/.tradex/weights.json` file and legacy 0–100 scores are unvalidated user preferences, not strategy parameters. They have no relationship to Journal records.

---

## Q. R7/R8 and LONG-002C Compatibility

### Q.1 R7 (Prospective PIT Data Capture) Extension Points

R6 does not implement R7. However, the R6 design leaves clean extension points:

- The `journal_entries.plan_created_at` timestamp can serve as a decision point for R7 PIT capture (e.g., "capture earnings schedule as known at plan creation time").
- The `candidate_id` FK provides access to existing PIT evidence via `candidate_evidence` table.
- Additional PIT capture fields (e.g., `earnings_at_decision`, `classification_at_decision`) can be added as nullable columns in a future additive migration without modifying the R6 schema.

### Q.2 R8 (LONG-002C Resumption) Extension Points

R6 does not implement R8 or resume LONG-002C. The R6 schema is compatible:

- A future LONG-002C evaluator can create `CandidateEvaluation` records with its own `evaluator_id` and `evaluator_version` using the existing candidate evaluation infrastructure.
- If LONG-002C produces a strategy that is eventually approved, it would use the same Journal infrastructure as any other approved strategy.
- No R6 schema or code depends on LONG-002C data families, so LONG-002C can be independently developed when approved.

### Q.3 What R6 Does NOT Implement

- R7 prospective PIT capture scheduling or storage
- R8/LONG-002C dataset construction or research logic
- New provider collection or integration
- Production strategy promotion (no entries added to `APPROVED_ACTIONABLE_STRATEGIES`)
- Actionable alerts beyond existing R4 boundaries
- Brokerage integration or order placement
- Account management or position tracking

---

## Proposed Future R6 Implementation Slice

> **This section is not authorization to execute R6.** It documents the recommended implementation scope for a future, separately Gary-approved R6 PR.

### Implementation Assessment: Single PR vs. Split

Based on repository evidence, R6 can be implemented as a **single bounded PR** because:

1. The schema change is a single additive table (`journal_entries`) with a straightforward v4→v5 migration.
2. The service layer is a self-contained module with clear interfaces.
3. The UI change is limited: rename one tab, move legacy content to Research Lab, add new Journal rendering.
4. The test scope is bounded and parallel to existing test patterns.
5. R5A/R5B/R5C provide a clear implementation template (domain model → persistence → queries → UI).

**Recommendation:** One PR, designated `MVP-ARCH-001-R6`.

If during implementation the PR exceeds ~1500 lines of non-test code, consider splitting into:
- **R6A:** Schema v5 migration + domain model + persistence + service interfaces + unit tests
- **R6B:** Journal UI + legacy telemetry relocation + UI tests

### Exact Likely Production Files to Create/Change

#### New Files

| File | Purpose |
|---|---|
| `tradex/journal/__init__.py` | Journal domain package exports |
| `tradex/journal/models.py` | `JournalEntry` dataclass, error types, state constants |
| `tradex/journal/store.py` | Persistence primitives: create, fill, cancel, expire, exit, get, list |
| `tradex/journal/service.py` | Authorization-checked service layer wrapping store operations |
| `tradex/journal/queries.py` | Read-only view models and queries for UI (following R5C pattern) |
| `tradex/ui/tabs/journal.py` | New Journal tab renderer |

#### Modified Files

| File | Change |
|---|---|
| `tradex/tracker/store.py` | Add `_migrate_v4_to_v5`, update `_SCHEMA_VERSION` to 5, add `journal_entries` DDL |
| `tradex/ui/dashboard.py` | Replace `"Signal Journal"` tab with `"Journal"`, move legacy telemetry to Research Lab |
| `tradex/ui/tabs/research_lab.py` | Add Legacy Scanner Telemetry section calling existing `render_signal_journal_tab` |
| `tradex/ui/evidence.py` | Add `"journal"` evidence notice text |
| `tradex/alerts/eligibility.py` | Potentially extract `APPROVED_ACTIONABLE_STRATEGIES` to a shared domain location (or import from existing location) |

#### Unchanged Files

| File | Reason |
|---|---|
| `tradex/ui/tabs/signal_journal.py` | Preserved as-is, relocated to Research Lab call site |
| `tradex/tracker/outcome_tracker.py` | Unchanged — continues to serve legacy telemetry refresh |
| `tradex/candidates/*` | Unchanged — Journal references candidates via FK |

### Exact Likely Tests to Create/Change

#### New Test Files

| File | Coverage |
|---|---|
| `tests/journal/test_journal_models.py` | Domain model validation, state constants, error types |
| `tests/journal/test_journal_store.py` | Persistence CRUD, idempotency, conflict detection, FK enforcement, atomic rollback |
| `tests/journal/test_journal_service.py` | Authorization checks, state machine transitions, fail-closed behavior |
| `tests/journal/test_journal_queries.py` | View model construction, query filters, neutral ordering, zero-write verification |
| `tests/tracker/test_schema_v5_migration.py` | v4→v5 migration, fresh DB at v5, legacy data preservation, future version rejection, atomic rollback |
| `tests/ui/test_journal_tab.py` | Empty states, populated states, detail rendering, legacy score exclusion, zero provider calls |

#### Modified Test Files

| File | Change |
|---|---|
| `tests/product/test_mvp_arch_001.py` | Add R6 readiness verification tests (if architecture JSON is updated with R6 authorization entry) |
| `tests/ui/test_dashboard.py` | Update tab count (8 tabs, but `"Journal"` replaces `"Signal Journal"`), verify Legacy Scanner Telemetry in Research Lab |
| `tests/ui/test_dashboard_router.py` | Update tab labels |
| `tests/candidates/test_hard_boundaries.py` | Verify schema version = 5 (update from 4) |

### Schema Migration Scope

- **One migration:** v4 → v5
- **One new table:** `journal_entries` (full DDL in Section K.2)
- **Six new indexes** (listed in Section K.3)
- **Zero modifications** to existing tables
- **Zero data migrations** from existing tables

### UI Scope

- **One new tab renderer:** `tradex/ui/tabs/journal.py`
- **One tab label change:** `"Signal Journal"` → `"Journal"` in `dashboard.py`
- **One content relocation:** legacy signal journal rendering moved to Research Lab section
- **One new evidence notice:** `"journal"` key in evidence notice system

### Compatibility Requirements

- Schema v5 databases must be accepted by the new code.
- Schema v4 databases must be automatically migrated to v5 on `store.init()`.
- The `journal_entries` table starts empty — no data is synthesized or backfilled.
- All existing tests must pass (legacy telemetry, candidate, alert, schema tests).
- Legacy Scanner Telemetry remains fully functional in its new Research Lab location.

### Rollback

1. Revert the R6 code PR.
2. The `journal_entries` table remains in the database but is unused (dormant).
3. `"Signal Journal"` tab label is restored as the primary journal surface.
4. No data is lost because `journal_entries` is either empty or contains only records that the reverted code ignores.

### Ordered Implementation Sequence

1. **Domain model:** `tradex/journal/models.py` — `JournalEntry` dataclass, state enum, error types
2. **Schema migration:** `tradex/tracker/store.py` — `_migrate_v4_to_v5`, update `_SCHEMA_VERSION` to 5
3. **Persistence layer:** `tradex/journal/store.py` — CRUD operations with idempotency
4. **Service layer:** `tradex/journal/service.py` — authorization-gated operations
5. **Query layer:** `tradex/journal/queries.py` — read-only view models for UI
6. **UI — Journal tab:** `tradex/ui/tabs/journal.py` — new executable Journal renderer
7. **UI — Dashboard wiring:** `tradex/ui/dashboard.py` — tab label change, Today tab unchanged
8. **UI — Legacy relocation:** `tradex/ui/tabs/research_lab.py` — add Legacy Scanner Telemetry section
9. **Tests:** all test files listed above, in parallel with implementation steps

### Acceptance Criteria for Future R6 Implementation

1. Schema v5 migration is additive and idempotent.
2. Legacy tables and data are completely preserved.
3. `journal_entries` table exists with correct DDL and constraints.
4. `create_journal_entry` validates strategy authorization against `APPROVED_ACTIONABLE_STRATEGIES`.
5. With empty `APPROVED_ACTIONABLE_STRATEGIES`, all Journal creation attempts are rejected.
6. State machine transitions are enforced: planned→open→closed, planned→cancelled, planned→expired.
7. Forbidden transitions raise `JournalStateError`.
8. Idempotent create/fill/exit operations work correctly.
9. Conflicting creates/fills raise `JournalConflictError`.
10. Journal UI renders correct empty states for zero strategies and zero records.
11. Legacy Scanner Telemetry is accessible in Research Lab.
12. Legacy expectancy and outcome metrics are clearly labeled as non-executable.
13. Tab label reads `"Journal"` not `"Signal Journal"`.
14. All existing tests pass.
15. All new tests pass.
16. `APPROVED_ACTIONABLE_STRATEGIES` remains empty.
17. No production trading behavior changes.

### Targeted Tests

- `uv run pytest tests/journal/ -q` — all new Journal tests
- `uv run pytest tests/tracker/test_schema_v5_migration.py -q` — schema migration
- `uv run pytest tests/ui/test_journal_tab.py -q` — Journal UI
- `uv run pytest tests/ui/test_dashboard.py -q` — dashboard wiring
- `uv run pytest tests/product/test_mvp_arch_001.py -q` — governance invariants

### Broader Verification

- `uv run pytest tests/ -q` — full suite
- `uv run ruff check tests scripts` — lint
- `git diff --check` — whitespace
- Streamlit smoke test (if UI changes warrant it per testing skill)

---

*This document is a versioned readiness/design specification. It does not implement R6, authorize R6 implementation, promote any strategy, change production trading behavior, modify the database schema, or alter `APPROVED_ACTIONABLE_STRATEGIES`. R6 implementation requires a separate, explicitly Gary-approved PR.*
