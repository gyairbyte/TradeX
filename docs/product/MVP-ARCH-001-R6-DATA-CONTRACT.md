# MVP-ARCH-001-R6-READINESS-A: Executable Journal Data, Lifecycle, and Persistence Contract

**Task ID:** `MVP-ARCH-001-R6-READINESS-A`
**Classification:** `research-design-governance-only`
**Repository base:** `main` @ `cba9ffc76d8aa1feadc47fb3743fb8a3835acbbc`
**Production trading behavior changed:** No
**R6 implementation authorized:** No
**Schema implementation authorized:** No — the persisted schema remains **v4** in this PR
**Strategy promotion authorized:** No — `APPROVED_ACTIONABLE_STRATEGIES == ()` is unchanged
**R7 / R8 authorized:** No
**LONG-002C:** Remains paused; not resumed by this document

This document defines the proposed data, lifecycle, and persistence contract for the
future executable-strategy Journal (MVP-ARCH-001 rollout step 6, "Journal/outcome
replacement"). It is a design contract only. Nothing in this document creates tables,
migrations, domain models, services, UI, alerts, provider calls, or strategy
authorizations. A later, separately Gary-approved R6 implementation task must treat
this contract as its specification.

Throughout this document:

- **[FACT]** marks verified current-repository behavior at the base SHA above.
- **[PROPOSED]** marks future R6 design that is *not* implemented and *not* authorized
  for implementation by this PR.

---

## A. Current persistence and outcome evidence [FACT]

### A.1 Schema version

- SQLite persistence is managed by `tradex/tracker/store.py`.
- `_SCHEMA_VERSION = 4`, tracked via `PRAGMA user_version`.
- `init()` migrates forward additively (`_migrate_v0`, `_migrate_v1_to_v2`,
  `_migrate_v2_to_v3`, `_migrate_v3_to_v4`) inside explicit transactions and **rejects**
  databases whose `user_version` is newer than the supported version.
- Database default path: `~/.tradex/signals.db` (overridable via `TradeXSettings`).

### A.2 Current tables

| Table | Introduced | Role |
|---|---|---|
| `signal_history` | v1 (migrated from v0 legacy) | Legacy per-signal telemetry rows, including outcome columns |
| `scan_sessions` | v3 | Canonical scan session headers |
| `scan_observations` | v3 | Canonical full-universe scan observations |
| `scan_runs` | v2 | Scan audit surface |
| `candidates` | v4 | Immutable point-in-time CandidateSnapshot headers |
| `candidate_evaluations` | v4 | Versioned evaluator envelopes |
| `candidate_evidence` | v4 | Structured PIT provenance |
| `candidate_reasons` | v4 | Structured explainability reasons |
| `candidate_missing_data` | v4 | Explicit 8-state missing-data records |

### A.3 CandidateSnapshot identity

- `candidates.candidate_id` is a `TEXT PRIMARY KEY`; the domain model
  (`tradex/candidates/models.py`) is a frozen dataclass with a non-empty unique
  `candidate_id`, uppercase `symbol`, timezone-aware UTC-normalized
  `decision_timestamp`, `contract_version`, optional XNYS-derived `trading_date`
  (NULL on non-trading days), `security_identity_version`/`security_identity_status`,
  and a UTC `created_at` audit timestamp.
- `record_candidate_dossier()` (`tradex/candidates/store.py`) is atomic; exact material
  replay of the same dossier is idempotent (returns the stored dossier), and reuse of a
  `candidate_id` with divergent material content raises `StoreError`. Snapshots are
  never overwritten.
- Candidate evidence observed after the candidate `decision_timestamp` is rejected by
  dossier integrity checks (point-in-time enforcement).

### A.4 Legacy signal and outcome storage

- `signal_history` stores `ticker`, `timeframe`, `scan_time`, `score`, `last_close`,
  `volume_ratio`, `rsi`, `reasons`, `provider` (default `'unknown'`), the outcome
  columns `outcome_close`, `outcome_pct`, `outcome_at`, `outcome_provider`, plus
  `scan_session_id` and `trading_date`.
- `get_signal_journal()` returns rows where `outcome_close IS NOT NULL`. The Signal
  Journal UI (`tradex/ui/tabs/signal_journal.py`) explicitly labels this surface
  "Signal Journal — Historical Outcomes" and "Descriptive telemetry only."

### A.5 Current outcome-window semantics

- `tradex/tracker/outcome_tracker.py` defines
  `OUTCOME_WINDOWS = {"intraday": 1, "short": 3, "long": 5}` (trading sessions after
  the signal).
- Outcomes compare a later close to the signal's `last_close`:
  `pct = ((outcome_close - last_close) / last_close) * 100`.
- These outcomes do **not** model entry fills, stops, targets, expiration,
  invalidation, slippage, or fees. MVP-ARCH-001 classifies this data as
  `legacy_signal_telemetry` and documents why it cannot prove an edge.

### A.6 Provider provenance

- Signal provider and outcome provider are stored separately
  (`provider`, `outcome_provider`); missing values are normalized to the literal
  `'unknown'` (`_resolve_signal_provider`, `_normalize_outcome_provider`) — never
  inferred or substituted.
- `candidate_evidence` stores `provider`, `source_ref_type`/`source_ref_id`,
  `observed_at`, and `metadata_json`; `candidate_missing_data` records explicit
  missing states.

### A.7 Current strategy authorization mechanism

- `tradex/alerts/eligibility.py` defines the authoritative registry:

  ```python
  APPROVED_ACTIONABLE_STRATEGIES: tuple[ApprovedActionableStrategy, ...] = ()
  ```

- `check_automatic_alert_eligibility()` fails closed: it requires a valid `AlertKey`,
  non-empty `strategy_id` and `strategy_version`,
  `evidence_state == "production_approved"`, and an exact
  `(strategy_id, strategy_version)` match in the registry. The registry is **empty**.

### A.8 Timestamp / calendar behavior

- Canonical market module: `tradex/market/hours.py` with
  `MARKET_TIMEZONE = ZoneInfo("America/New_York")` and
  `EXCHANGE_CALENDAR_KEY = "XNYS"` (`exchange_calendars`).
- Persisted timestamps are UTC ISO-8601. Naive datetimes are rejected by
  `record_scan()`, candidate models, and market-hours APIs. Trading dates derive from
  New-York-local time and the XNYS calendar; weekends/holidays yield no trading date.

Everything below this line is **[PROPOSED]** R6 design unless explicitly marked [FACT].

---

## B. Strategy authorization contract [PROPOSED]

### B.1 Identity representation

- `strategy_id`: non-empty `str`, trimmed, no surrounding whitespace, case-sensitive,
  recommended pattern `^[a-z0-9][a-z0-9_-]{0,63}$`. Validation error → reject.
- `strategy_version`: non-empty `str`, trimmed, case-sensitive, recommended pattern
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$` (e.g. `v1`, `2026.08.1`). Validation error → reject.
- The pair `(strategy_id, strategy_version)` is the only strategy identity the Journal
  recognizes. Free-text names, evaluator ids, heuristic scorer names, and saved weight
  profiles are **not** strategy identities.

### B.2 Registry: one neutral production-strategy authorization contract

`APPROVED_ACTIONABLE_STRATEGIES` in `tradex/alerts/eligibility.py` is, by its own
definition, the registry of strategies authorized for **automatic external alert
delivery** [FACT]. The Journal must not silently inherit alert-delivery authorization
as its system of record. This contract therefore recommends **one** central, neutral
production-strategy registry as the future system of record for all production
authorization decisions:

- **Location:** a new domain module, `tradex/strategies/registry.py` (no dependency on
  alerts or UI).
- **Shape (capability model):**

  ```python
  @dataclass(frozen=True, slots=True)
  class ApprovedProductionStrategy:
      strategy_id: str
      strategy_version: str
      description: str
      capabilities: frozenset[str]  # subset of {"journal_execution", "automatic_alerts"}

  APPROVED_PRODUCTION_STRATEGIES: tuple[ApprovedProductionStrategy, ...] = ()
  ```

- **Lookup:** exact `(strategy_id, strategy_version)` membership **and** the required
  capability for the consuming surface: the Journal requires `"journal_execution"`;
  automatic alerts require `"automatic_alerts"`. A strategy may hold either or both
  capabilities; each grant is an explicit Gary-approved registry entry.
- **Alert consumption:** `check_automatic_alert_eligibility()` migrates to consume the
  central registry's `"automatic_alerts"` capability. With the registry empty this is
  behavior-preserving (everything remains fail-closed); the migration is part of the
  future R6 implementation, not this PR, and `APPROVED_ACTIONABLE_STRATEGIES == ()`
  is unchanged here.
- **Governance:** the registry is code-reviewed, versioned, and Gary-approved; it is
  never database-editable or UI-editable. It starts — and stays — empty until a
  separately Gary-approved strategy promotion PR.

This is the single recommended contract; registry choice is **not** left as an
implementation decision.

### B.3 Authorization outcomes

| Input | Behavior |
|---|---|
| Unknown `(strategy_id, strategy_version)` | Reject with `StrategyNotAuthorizedError`; no row written; rejection is auditable (log/exception message includes both values) |
| Research / shadow / exploratory strategy (e.g. R5B shadow evaluator identities) | Same rejection — evaluator identity is not production approval |
| Deprecated / withdrawn strategy or version | Not in registry → same rejection for **new** record creation |
| Empty / whitespace / malformed id or version | `ValueError` before any registry lookup |

### B.4 Authorization at creation vs. later lifecycle updates

- **Creation** of an executable Journal record requires the strategy to be approved at
  the moment of creation. This is the hard gate.
- **Later lifecycle updates** (fill, cancel, invalidate, expire, close) on an existing
  record remain permitted even if the strategy was subsequently de-authorized: an
  already-planned or open trade must be closable and auditable. De-authorization only
  blocks *new* record creation. Lifecycle updates never re-check the registry silently;
  they record the event as-is against the immutable `(strategy_id, strategy_version)`
  captured at creation.

### B.5 Fail-closed boundary

> **No executable Journal record may be created while there is no
> production-approved actionable strategy.**

Because `APPROVED_ACTIONABLE_STRATEGIES == ()` [FACT], every create call fails closed
today. The Journal tables (if later created under an approved migration) remain empty
until a separately Gary-approved strategy promotion PR adds a registry entry.

---

## C. Journal record identity [PROPOSED]

- **Primary identifier:** `journal_id` — non-empty unique `TEXT`, generated as a UUIDv4
  hex string by the service layer at creation. Timestamps are never identity.
- **Linkage (all captured immutably at creation):**
  - `candidate_id` → `candidates.candidate_id` (FK). Every executable Journal record
    must reference an existing CandidateSnapshot; the snapshot's `decision_timestamp`
    is the point-in-time anchor of the decision evidence.
  - `strategy_id`, `strategy_version` — the approved identity under which the decision
    was made.
  - `decision_timestamp` — timezone-aware UTC timestamp of the executable decision
    (must be ≥ the candidate's `decision_timestamp`; a plan cannot predate its
    evidence).
- **Uniqueness / idempotency:**
  - `UNIQUE (candidate_id, strategy_id, strategy_version)` — at most one executable
    decision per strategy version per candidate snapshot. Distinct decisions require
    distinct candidate snapshots (which are themselves PIT-unique).
  - `idempotency_key` — required non-empty caller-supplied `TEXT`, `UNIQUE`. Retry or
    replay of the same create call with the same key and materially identical payload
    returns the existing record (idempotent success); the same key with a divergent
    payload raises a conflict error (mirroring `record_candidate_dossier` semantics).
- Duplicate executable decisions from retries/replays are therefore impossible at the
  database level, not merely discouraged at the service level.

---

## D. Lifecycle / state machine [PROPOSED]

### D.1 Recommended state set

`planned`, `open`, `closed`, `cancelled`, `expired`, `invalidated`

- `planned` — decision recorded, plan captured, no fill yet.
- `open` — exactly one entry fill recorded ("filled"). Multiple/partial fills are
  **not** supported in this contract version (see §L.2); a future amendment may add
  them explicitly.
- `closed` — exit fill recorded with an exit reason. Terminal.
- `cancelled` — deliberately withdrawn before any fill. Terminal.
- `expired` — plan expiration passed with no fill. Terminal.
- `invalidated` — invalidation rule triggered. Terminal. Permitted from `planned`
  (setup broke before entry) and from `open` **only** when the strategy's invalidation
  is the exit mechanism, in which case an exit fill and exit reason
  `invalidation` are still required and the terminal state is `closed` with
  `exit_reason='invalidation'` — i.e. `open → invalidated` without an exit fill is
  rejected; an open position always exits through `closed`.

### D.2 Transition matrix

| From | To | Trigger | Required fields | Prohibited | Required timestamps | Idempotent repeat | 
|---|---|---|---|---|---|---|
| (none) | `planned` | create | plan contract (§E), authorization (§B), idempotency_key | any execution fields | `decision_timestamp`, `plan_created_at` | same key + same payload → return existing |
| `planned` | `open` | record_fill | `fill_price`, `fill_provenance` | exit fields | `fill_timestamp` ≥ `plan_created_at` | same fill payload → no-op success; divergent → conflict |
| `planned` | `cancelled` | cancel | `cancel_reason` | fill/exit fields | `cancelled_at` ≥ `plan_created_at` | repeat cancel → no-op success |
| `planned` | `expired` | expire | — | fill/exit fields | `expired_at` ≥ `expiration` | repeat expire → no-op success |
| `planned` | `invalidated` | invalidate | `invalidation_reason` | fill/exit fields | `invalidated_at` ≥ `plan_created_at` | repeat with same reason → no-op success |
| `open` | `closed` | record_exit | `exit_price`, `exit_reason`, `exit_provenance` | — | `exit_timestamp` ≥ `fill_timestamp` | same exit payload → no-op success; divergent → conflict |

### D.3 Rejected transitions (always errors)

- Exit before fill: `planned → closed`, or any `record_exit` on a non-`open` record.
- `closed` without exit price/timestamp/reason (enforced by CHECK constraints, §J).
- Any transition out of a terminal state (`closed`, `cancelled`, `expired`,
  `invalidated`).
- A second, divergent fill on an `open` record (conflicting fills unsupported).
- Rewriting plan fields (`planned_entry`, `stop_price`, `target_price`, `expiration`,
  `invalidation_rule`) at **any** point after creation — plan fields are immutable
  from creation (§E). There is no plan-amendment operation in this contract version:
  a changed plan means the old `planned` record is cancelled
  (`cancel_reason='superseded_by_new_plan'`) and a new executable decision is created
  against a new point-in-time CandidateSnapshot reflecting the evidence behind the
  new plan.
- Any lifecycle event whose timestamp precedes the prior event's timestamp
  (out-of-order events rejected; §I.5 covers same-timestamp ties).

---

## E. Planned trade contract [PROPOSED]

All prices are USD per share, positive `REAL` (finite, > 0). All timestamps are
timezone-aware, persisted UTC. "DB-nullable" is the storage-level rule; a strategy's
own definition may impose stricter per-strategy requirements at the service layer.
Do **not** assume every future strategy defines both a hard stop and a target: the
database permits NULLs; the strategy contract decides what is mandatory for records
created under it, and that check runs at creation.

| Field | Type / units | DB-nullable | Validation | Point-in-time timestamp | Mutability |
|---|---|---|---|---|---|
| `planned_entry` | REAL, USD/share | NOT NULL | finite, > 0 | `plan_created_at` | Immutable from creation |
| `stop_price` | REAL, USD/share | NULL | finite, > 0; for long-only plans `< planned_entry` when both present | `plan_created_at` | Immutable from creation |
| `target_price` | REAL, USD/share | NULL | finite, > 0; for long-only plans `> planned_entry` when both present | `plan_created_at` | Immutable from creation |
| `expiration` | TEXT, UTC ISO-8601 | NULL | timezone-aware; > `plan_created_at` | `plan_created_at` | Immutable from creation |
| `invalidation_rule` | TEXT (structured JSON: `{"rule_id": str, "rule_version": str, "params": {...}}`) | NULL | non-empty `rule_id`/`rule_version` when present; params JSON-serializable | `plan_created_at` | Immutable from creation |
| `plan_created_at` | TEXT, UTC ISO-8601 | NOT NULL | timezone-aware; ≥ `decision_timestamp` | self | Immutable |

Plan amendment: **not supported** in this contract version. All plan fields are
immutable from record creation, not merely from fill. To change a plan, cancel the
`planned` record (`cancel_reason='superseded_by_new_plan'`) and create a new Journal
decision against a new PIT CandidateSnapshot. This keeps every plan a point-in-time
artifact with a single audit trail and removes any amendment/versioning semantics
from v1. A future contract amendment may introduce plan amendments, but must then
fully specify the amendment operation, its transition/idempotency contract, and its
audit/version rules.

Long/short direction: this contract covers the approved long-only product scope; a
`side TEXT NOT NULL CHECK (side IN ('long'))` column keeps the constraint explicit and
extensible without implying short support.

---

## F. Execution contract [PROPOSED]

TradeX is **not** a brokerage execution system today [FACT: no brokerage order/fill
integration exists in the repository; IBKR is archived/manual]. No price in the
Journal may be described as broker-confirmed unless its provenance record supports it.
This contract does **not** authorize brokerage integration.

Every execution observation carries an explicit `execution_provenance`:

- `manual` — Gary-entered fill/exit observation (expected default for R6).
- `simulated` — derived from market data by a documented simulation rule; the rule id
  and data provider must be recorded in the event provenance.
- `broker_confirmed` — permitted **only** if a future separately approved brokerage
  integration supplies verifiable confirmation identifiers; until then the service
  layer rejects this value.

| Field | Type / units | Required when | Validation |
|---|---|---|---|
| `fill_price` | REAL, USD/share | state ≥ `open` | finite, > 0 |
| `quantity` | REAL, shares | state ≥ `open` (**mandatory at fill**) | finite, > 0 |
| `fill_timestamp` | TEXT UTC ISO-8601 | state ≥ `open` | aware; ≥ `plan_created_at`; ≤ `expiration` when set |
| `fill_provenance` | TEXT enum above + provider + observer | with fill | provider preserved verbatim or `'unknown'` |
| `exit_price` | REAL, USD/share | state = `closed` | finite, > 0 |
| `exit_timestamp` | TEXT UTC ISO-8601 | state = `closed` | aware; ≥ `fill_timestamp` |
| `exit_reason` | TEXT enum: `stop`, `target`, `expiration`, `invalidation`, `discretionary` | state = `closed` | must be one of the enum values |
| `exit_provenance` | as `fill_provenance` | with exit | as above |
| `cancel_reason` / `invalidation_reason` | TEXT non-empty | on cancel / invalidate | free text plus optional rule reference |

---

## G. Cost and outcome calculations [PROPOSED]

Approved-field scoping [FACT]: MVP-ARCH-001's future Journal contract fields are
exactly `strategy_id_and_version`, `candidate_id`, `planned_entry`, `realized_fill`,
`stop_price`, `target_price`, `expiration`, `invalidation_rule`, `exit_reason`,
`exit_fill`, `slippage_and_costs`, `net_return`, `strategy_drawdown`,
`provider_provenance`, `outcome_confidence`. MFE, MAE, holding period, benchmark
context, and regime context appear only in research/backtest modules
(`tradex/research/*`, `tradex/backtest/*`) and are **not** approved Journal
requirements — they are deliberately **excluded** from this contract rather than
silently added.

All calculations are computed only for `closed` records, after `exit_timestamp`,
from persisted fields — never from data unavailable at the time of the events used.

| Quantity | Definition | Units / sign | Stored vs derived | Missing data |
|---|---|---|---|---|
| `entry_slippage` | `fill_price - planned_entry` | USD/share; positive = worse (paid more) for long entries | Derived, then stored on outcome row with computation audit | NULL if `planned_entry` or fill absent |
| `costs` | Explicit per-trade costs (commission/fees), caller-supplied observation | USD, ≥ 0 | Stored input (not inferred) | NULL = unknown; **never** defaulted to 0 silently — a NULL cost makes `net_return` NULL |
| `gross_return_pct` | `((exit_price - fill_price) / fill_price) * 100` | percent; positive = gain (long) | Derived + stored | NULL unless closed |
| `net_return_pct` | `((exit_price - fill_price - costs / quantity) / fill_price) * 100`. `quantity` is mandatory at fill (§F), so `costs / quantity` is always well-defined whenever `costs` is known | percent, sign as above | Derived + stored | NULL **only** when `costs` is unknown (NULL); never silently treated as 0 |
| `strategy_drawdown` | **Fail-closed: NULL/unknown in this contract version.** Per-trade percent returns cannot be truthfully aggregated into a strategy drawdown without an explicit capital, position-sizing, and compounding model — including treatment of overlapping open trades — and no such model is approved. No drawdown value is stored or displayed until a separately Gary-approved strategy-specific aggregation model defines the equity-curve convention | n/a (always NULL/unknown in v1) | Not stored; not derived in v1 | Always NULL/unknown until an aggregation model is approved |
| `outcome_confidence` | Categorical enum `confirmed` / `provisional` / `unknown`, computed by the deterministic mapping below | enum | Derived + stored with the outcome row | see mapping |

`outcome_confidence` deterministic mapping — evaluate these rules in order against the
fill and exit provenance records; the first match wins:

1. If either provenance record is missing, has a missing/empty `execution_provenance`,
   or has `provider == 'unknown'` → `unknown`.
2. If both fill and exit have `execution_provenance == 'broker_confirmed'` (only
   possible under a future separately approved brokerage integration, §F) →
   `confirmed`.
3. Otherwise (any complete combination of `manual` / `simulated`, including mixed with
   `broker_confirmed`) → `provisional`.

Recomputation: stored derived values are recomputed only via the explicit
`recompute_outcomes` operation (§K), which writes a new outcome row version with a
`computed_at` audit timestamp, the `source_event_seq` it consumed, and a
deterministic `inputs_hash` (§J.1) — never an in-place silent update. Legacy `signal_history.outcome_pct` values are **never** represented as
realized strategy returns.

---

## H. Provenance contract [PROPOSED]

Minimum persisted provenance, per artifact:

| Artifact | Minimum provenance |
|---|---|
| CandidateSnapshot link | `candidate_id` FK (snapshot itself already carries PIT evidence provenance) [FACT] |
| Strategy decision | `strategy_id`, `strategy_version`, `decision_timestamp`, `decided_by` (e.g. `gary_manual`) |
| Planned prices | `plan_created_at`, plan source (`manual` / rule id), data provider for any price references used, verbatim or `'unknown'` |
| Fill observation | `execution_provenance` enum, `provider` (verbatim or `'unknown'`), `observed_at`, observer identity |
| Exit observation | same as fill observation |
| Outcome calculation | `computation_version` (formula identifier), `computed_at`, `source_event_seq` (highest lifecycle event consumed), deterministic `inputs_hash`, provider fields carried through from fill/exit |

Rules (mirroring current store behavior [FACT]):

- Raw provider identity is preserved exactly as supplied.
- Missing provenance is persisted as the literal `'unknown'` — never inferred, never
  replaced by a display fallback, never backfilled from a different provider.

---

## I. Timestamp, timezone, and calendar contract [PROPOSED]

1. **Persistence:** all timestamps stored as UTC ISO-8601 `TEXT`; naive datetimes are
   rejected at the service boundary (same rule as candidates/market-hours [FACT]).
2. **Display:** New York (`America/New_York`) is the display timezone; conversion is a
   presentation concern only and never alters stored values.
3. **Defined timestamps:** `decision_timestamp` (executable decision),
   `plan_created_at` (plan persisted), `fill_timestamp`, `exit_timestamp`,
   `expiration`, `cancelled_at` / `expired_at` / `invalidated_at`, `created_at` /
   event `recorded_at` audit stamps. Ordering invariants:
   `candidate.decision_timestamp ≤ journal.decision_timestamp ≤ plan_created_at ≤
   fill_timestamp ≤ exit_timestamp`, and each terminal timestamp ≥ its predecessor.
4. **Trading dates:** derived — never caller-invented — from the event timestamp
   converted to New York local time and validated against the XNYS calendar via
   `tradex/market/hours.py`. Non-trading days (weekends/holidays) yield NULL trading
   dates; events themselves may still occur (e.g. a weekend cancellation) and are
   stored with their true UTC timestamps. DST is handled entirely by timezone-aware
   conversion plus the XNYS calendar; no fixed UTC offsets anywhere.
5. **Same-bar / same-timestamp ambiguity:** events with equal timestamps are ordered by
   their append-only event sequence number (§J.3); a fill and exit at the identical
   timestamp are permitted only when the event sequence shows fill before exit.
   Point-in-time correctness: no Journal field may embed information observed after
   the timestamp it is stamped with; outcome rows record `computed_at` separately from
   the event timestamps they consume.

---

## J. Proposed persistence design [PROPOSED — NOT IMPLEMENTED]

The schema remains **v4** in this PR [FACT]. The recommendation below is a future
**additive schema v5** migration (`_migrate_v4_to_v5`), following the existing
`PRAGMA user_version` chain, to be implemented only under a separate Gary-approved R6
task.

### J.1 Proposed DDL

```sql
CREATE TABLE IF NOT EXISTS journal_trades (
    journal_id          TEXT PRIMARY KEY,
    contract_version    INTEGER NOT NULL DEFAULT 1,
    idempotency_key     TEXT    NOT NULL UNIQUE,
    candidate_id        TEXT    NOT NULL REFERENCES candidates(candidate_id),
    strategy_id         TEXT    NOT NULL,
    strategy_version    TEXT    NOT NULL,
    side                TEXT    NOT NULL CHECK (side IN ('long')),
    state               TEXT    NOT NULL CHECK (state IN
                          ('planned','open','closed','cancelled','expired','invalidated')),
    decision_timestamp  TEXT    NOT NULL,
    plan_created_at     TEXT    NOT NULL,
    planned_entry       REAL    NOT NULL CHECK (planned_entry > 0),
    stop_price          REAL    CHECK (stop_price IS NULL OR stop_price > 0),
    target_price        REAL    CHECK (target_price IS NULL OR target_price > 0),
    expiration          TEXT,
    invalidation_rule   TEXT,                 -- structured JSON or NULL
    quantity            REAL    CHECK (quantity IS NULL OR quantity > 0),  -- mandatory at fill (see CHECKs)
    fill_price          REAL    CHECK (fill_price IS NULL OR fill_price > 0),
    fill_timestamp      TEXT,
    fill_provenance     TEXT,                 -- JSON: {execution_provenance, provider, observed_at, observer}
    exit_price          REAL    CHECK (exit_price IS NULL OR exit_price > 0),
    exit_timestamp      TEXT,
    exit_reason         TEXT    CHECK (exit_reason IS NULL OR exit_reason IN
                          ('stop','target','expiration','invalidation','discretionary')),
    exit_provenance     TEXT,
    terminal_reason     TEXT,                 -- cancel/invalidation reason text
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    UNIQUE (candidate_id, strategy_id, strategy_version),
    CHECK (state != 'open'   OR (fill_price IS NOT NULL AND fill_timestamp IS NOT NULL
                                 AND quantity IS NOT NULL)),
    CHECK (state != 'closed' OR (fill_price IS NOT NULL AND quantity IS NOT NULL
                                 AND exit_price IS NOT NULL
                                 AND exit_timestamp IS NOT NULL AND exit_reason IS NOT NULL)),
    CHECK (state NOT IN ('planned','cancelled','expired','invalidated')
           OR (fill_price IS NULL AND exit_price IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_journal_trades_state
    ON journal_trades(state);
CREATE INDEX IF NOT EXISTS idx_journal_trades_strategy
    ON journal_trades(strategy_id, strategy_version);
CREATE INDEX IF NOT EXISTS idx_journal_trades_candidate
    ON journal_trades(candidate_id);

CREATE TABLE IF NOT EXISTS journal_events (
    event_id       TEXT    PRIMARY KEY,
    journal_id     TEXT    NOT NULL REFERENCES journal_trades(journal_id),
    seq            INTEGER NOT NULL,
    event_type     TEXT    NOT NULL CHECK (event_type IN
                     ('created','filled','cancelled',
                      'expired','invalidated','exited')),
    event_timestamp TEXT   NOT NULL,          -- domain time of the event (UTC)
    recorded_at    TEXT    NOT NULL,          -- audit time the row was written (UTC)
    payload_json   TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (journal_id, seq)
);

CREATE TABLE IF NOT EXISTS journal_outcomes (
    outcome_id        TEXT    PRIMARY KEY,
    journal_id        TEXT    NOT NULL REFERENCES journal_trades(journal_id),
    computation_version TEXT  NOT NULL,
    computed_at       TEXT    NOT NULL,
    source_event_seq  INTEGER NOT NULL,      -- highest journal_events.seq consumed
    inputs_hash       TEXT    NOT NULL,      -- SHA-256 of canonical inputs_json
    entry_slippage    REAL,
    costs             REAL    CHECK (costs IS NULL OR costs >= 0),
    gross_return_pct  REAL,
    net_return_pct    REAL,
    outcome_confidence TEXT   NOT NULL CHECK (outcome_confidence IN
                          ('confirmed','provisional','unknown')),
    inputs_json       TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (journal_id, computation_version, computed_at)
);
```

`journal_events` is append-only: no UPDATE or DELETE ever. `journal_trades` mutable
columns are limited to execution/terminal fields, `state`, and `updated_at`; plan
columns are immutable from creation (§E; enforced at the service layer, with the
append-only event log as the audit trail).

Outcome reproducibility: each `journal_outcomes` row records the exact lifecycle
state it consumed — `source_event_seq` is the highest `journal_events.seq` included
in the computation, and `inputs_hash` is the SHA-256 hash of the canonical (sorted
keys, compact separators) `inputs_json`, which itself contains the exact input field
values (`fill_price`, `quantity`, `exit_price`, `costs`, provenance fields). A stored
outcome can therefore be recomputed and byte-compared against the precise event range
it consumed, without needing a mutation row-version column on `journal_trades`.

### J.2 Migration behavior

- **v4 → v5:** additive only — `CREATE TABLE IF NOT EXISTS` for the three tables plus
  indexes, then `PRAGMA user_version = 5`, inside one transaction (rollback = the
  transaction aborts and the DB stays v4). No existing table is altered, rewritten, or
  dropped. `signal_history`, its outcome columns, and all candidate tables are
  untouched and preserved verbatim as `legacy_signal_telemetry` / R5 surfaces.
- **Fresh database:** `init()` creates the full v5 schema directly (same pattern as
  today's fresh-DB path) and sets `user_version = 5`.
- **Idempotent initialization:** re-running `init()` on a v5 DB is a no-op;
  `user_version > supported` continues to raise.
- **No backfill:** legacy `signal_history` rows are never converted into
  `journal_trades` rows; there is no data migration between the legacy telemetry
  tables and the executable Journal.

---

## K. Proposed service interfaces [PROPOSED — NOT IMPLEMENTED]

Likely home: `tradex/journal/service.py` (+ `models.py`, `store.py`). Signatures are
design pseudocode; all take `settings: TradeXSettings | None = None` and use one
explicit transaction per operation (the `_transaction` pattern in
`tradex/tracker/store.py` [FACT]).

```python
def validate_strategy_authorization(strategy_id: str, strategy_version: str) -> None:
    """Raise StrategyNotAuthorizedError unless (id, version) is in
    APPROVED_PRODUCTION_STRATEGIES with the "journal_execution" capability (§B.2).
    Pure check; no I/O beyond the in-code registry."""

# There is deliberately NO amend_plan operation (§E): plan fields are immutable
# from creation; a changed plan = cancel + new decision on a new snapshot.

def create_planned_trade(
    *, candidate_id: str, strategy_id: str, strategy_version: str,
    decision_timestamp: datetime, plan: TradePlan, idempotency_key: str,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Authorization check -> candidate existence check -> plan validation ->
    INSERT trade + 'created' event, one transaction.
    Errors: StrategyNotAuthorizedError, CandidateNotFoundError, ValueError,
    IdempotencyConflictError. Idempotent: same key + same material payload
    returns the existing record."""

def record_fill(
    *, journal_id: str, fill_price: float, fill_timestamp: datetime,
    fill_provenance: ExecutionProvenance, quantity: float,  # mandatory (§F, §G)
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """planned -> open. Errors: JournalNotFoundError, InvalidTransitionError,
    ValueError (naive/ordering/price), ConflictingFillError.
    Idempotent: identical repeat is a no-op returning current state."""

def cancel_trade(*, journal_id: str, cancel_reason: str, cancelled_at: datetime, ...) -> JournalTrade: ...
def invalidate_trade(*, journal_id: str, invalidation_reason: str, invalidated_at: datetime, ...) -> JournalTrade: ...
def expire_trade(*, journal_id: str, expired_at: datetime, ...) -> JournalTrade: ...
    # planned -> cancelled / invalidated / expired. Same error and idempotency model.

def record_exit(
    *, journal_id: str, exit_price: float, exit_timestamp: datetime,
    exit_reason: ExitReason, exit_provenance: ExecutionProvenance,
    costs: float | None = None, settings: TradeXSettings | None = None,
) -> JournalTrade:
    """open -> closed; writes 'exited' event; computes + stores the initial
    journal_outcomes row in the same transaction."""

def get_journal_trade(journal_id: str, ...) -> JournalTrade | None: ...
def list_journal_trades(
    *, state: str | None = None, strategy_id: str | None = None,
    candidate_id: str | None = None, limit: int = 100, ...
) -> list[JournalTrade]: ...
def get_journal_history(journal_id: str, ...) -> list[JournalEvent]:
    """Append-only event log ordered by seq."""

def recompute_outcomes(*, journal_id: str, computation_version: str, ...) -> JournalOutcome:
    """Permitted only for closed records; writes a NEW journal_outcomes row
    (versioned, audited); never mutates prior outcome rows."""
```

All mutations: single-transaction, ROLLBACK on any exception, no partial writes.
All reads: no side effects.

---

## L. Failure and concurrency cases [PROPOSED]

1. **Duplicate create (retry/replay):** same `idempotency_key` + same payload →
   existing record returned; divergent payload → `IdempotencyConflictError`. Same
   `(candidate_id, strategy_id, strategy_version)` under a new key → UNIQUE violation
   → conflict error.
2. **Duplicate / conflicting fill:** identical repeat is a no-op; any divergent second
   fill → `ConflictingFillError`. Partial fills are out of scope for this contract
   version and require an explicit future amendment.
3. **Duplicate / conflicting exit:** same model as fills.
4. **Conflicting concurrent updates:** SQLite serializes writers; each transition
   re-reads state inside its transaction, so the loser of a race gets
   `InvalidTransitionError` rather than silently overwriting.
5. **Missing CandidateSnapshot:** create fails with `CandidateNotFoundError`; the
   Journal never fabricates candidates. FK enforcement (`PRAGMA foreign_keys = ON`
   [FACT]) prevents dangling references; candidate deletion is not a supported
   operation, and the FK (without CASCADE) blocks it once Journal rows reference it.
6. **Unknown strategy / later-deauthorized version:** creation rejected (§B.3);
   existing records remain updatable through their lifecycle (§B.4).
7. **Malformed timestamps:** naive or unparsable datetimes rejected at the service
   boundary with `ValueError` before any write.
8. **Out-of-order events:** any event timestamp earlier than its predecessor is
   rejected; ties resolved by event `seq` (§I.5).
9. **Non-trading days / DST:** events are stored with true UTC timestamps; trading
   dates are NULL on non-trading days; DST handled by tz-aware conversion + XNYS
   calendar — never fixed offsets.
10. **Unknown provider / incomplete data:** provenance stored as `'unknown'`; derived
    values that need the missing input become NULL (and `outcome_confidence`
    degrades) rather than being guessed.
11. **Transaction failure / process crash:** every operation is one atomic
    transaction; a crash mid-operation leaves the previous consistent state. The
    append-only event log plus state CHECKs make partial states detectable.
12. **Multiple TradeX processes:** SQLite locking serializes writes; busy/locked
    errors surface to callers rather than being retried into duplicate writes (the
    idempotency keys make caller-level retry safe).
13. **Fresh database / v4 migration:** §J.2. Existing v4 data is untouched; a fresh DB
    gets the full schema; `user_version` newer than supported still raises.
14. **Malformed legacy rows:** legacy `signal_history` rows never participate in
    Journal logic, so malformed legacy telemetry cannot corrupt executable records.

---

## M. Fail-closed zero-strategy state

Current fact [FACT]:

```text
APPROVED_ACTIONABLE_STRATEGIES == ()
```

Therefore, under this contract:

- No executable Journal trade may be automatically (or manually) created today —
  every create call fails closed at §B.5.
- Scanner rows are not trades.
- CandidateSnapshot rows are not trades.
- R5B shadow candidates and shadow evaluator outputs are not trades.
- Heuristic scores (intraday/short/long scorers, coil, confluence) are not trades.
- Research evaluator output is not a production strategy.
- Legacy `signal_history` rows may not be backfilled as trades.
- Legacy forward returns (`outcome_pct`) may not be represented as realized strategy
  returns.

---

## N. Research-integrity boundaries

- Executable Journal records do not prove strategy edge; they are an audit trail of
  decisions and results, not a validation study.
- R6 does not promote any strategy; promotion remains a separate Gary-approved PR
  that edits the registry.
- No holdout optimization is introduced; Journal data must not be used to tune
  thresholds/weights outside the research protocol (`docs/RESEARCH-PROTOCOL.md`).
- Research/shadow results remain segregated in research artifacts and candidate
  evaluation envelopes; they never enter `journal_trades`.
- CandidateSnapshot history remains immutable [FACT]; Journal outcomes must never
  retroactively modify point-in-time candidate evidence (no writes from
  `tradex/journal/` into candidate tables).
- Saved user weights and legacy scores cannot silently become strategy configuration;
  strategy parameters exist only as versioned, registry-linked strategy definitions.

---

## O. Future implementation mapping (planning only)

| Concern | Likely future location |
|---|---|
| Migration `_migrate_v4_to_v5` + fresh-DB schema | `tradex/tracker/store.py` (existing migration chain) |
| Domain models (`JournalTrade`, `TradePlan`, `JournalEvent`, `JournalOutcome`, enums) | `tradex/journal/models.py` |
| Persistence primitives | `tradex/journal/store.py` |
| Service layer (§K operations) | `tradex/journal/service.py` |
| Outcome calculations (§G) | `tradex/journal/outcomes.py` |
| Tests | `tests/journal/test_journal_models.py`, `test_journal_service.py`, `test_journal_lifecycle.py`, `test_journal_outcomes.py`; `tests/tracker/test_schema_v5_migration.py` |

Proposed acceptance criteria for the future R6 implementation (verification plan, not
implemented here):

1. Create fails closed with the empty registry (no row written; auditable error).
2. v4 → v5 migration is additive, idempotent, transactional, and preserves all legacy
   rows byte-for-byte; fresh DB initializes to v5.
3. Full transition matrix (§D.2) covered by tests, including all rejected transitions
   (§D.3) and idempotent repeats.
4. Timestamp ordering, naive-rejection, non-trading-day, and DST cases covered.
5. Provenance persisted verbatim with `'unknown'` for missing values; no fallback.
6. Outcome formulas (§G) tested including NULL-cost → NULL net return, the
   deterministic `outcome_confidence` mapping, mandatory quantity at fill, and
   outcome reproducibility from `source_event_seq` + `inputs_hash`.
7. No import path from `tradex/journal/` mutates candidate or legacy tables.
8. All tests deterministic, credential-free, and network-free.

---

## R. Deferred scope boundaries (resolved for v1; future amendments only)

All core semantics are resolved in this contract: authorization uses the single
neutral capability registry (§B.2); `quantity` is mandatory at fill (§F/§G);
`strategy_drawdown` fails closed to NULL/unknown until an approved aggregation model
(§G); `outcome_confidence` has a deterministic mapping (§G); plan fields are immutable
from creation with no amendment operation (§D.3/§E); outcomes are reproducible via
`source_event_seq` + `inputs_hash` (§J.1). The only concepts explicitly deferred to
future contract amendments are:

1. **Partial/multiple fills:** unsupported in v1; a future amendment must add a fill
   child table and weighted-average semantics before they can exist.
2. **Plan amendments:** unsupported in v1 (§E); a future amendment must fully specify
   the operation, transition/idempotency contract, and audit/version rules.
3. **Strategy drawdown aggregation model:** requires a separately Gary-approved
   capital/position-sizing/compounding convention before any value is computed.

---

*This document is a versioned design contract. It does not implement any schema,
migration, model, service, UI, alert, provider, or strategy change, and it does not
authorize R6, R7, R8, LONG-002C, or any strategy promotion.*
