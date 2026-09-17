# R7 PIT Status & Applicability Implementation Readiness (MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001)

## 1. Executive Summary & Objective

This document defines the final, implementation-ready normative contract for TradeX's Gary-approved **Option 2 + Option 3 point-in-time (PIT) architecture** (`selected_status_policy: "option_2_plus_3"`) following the successful completion of the empirical provider study (`MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001`).

### Task Classification
**Design-only / Implementation-Readiness Architecture.**
- **Production trading behavior changed:** No.
- **Production PIT runtime behavior changed:** No.
- **Database schema migrated:** No.
- **Scheduler installed:** No.
- **Candidate universe selected:** No.

This is a readiness specification and contract lock only. It establishes the exact mathematical, architectural, schema, provenance, and migration requirements for subsequent bounded implementation pull requests.

---

## 2. Relationship to Upstream Packets

This readiness contract builds upon and synthesizes the sequential evidence produced across the R7 point-in-time workstream:

1. **`MVP-ARCH-001-R7-PIT-STATUS-DEC-001` (Gary approved 2026-09-09)**:
   - Approved the architectural direction to separate operational execution health from evidence completeness (Option 2) and introduce applicability-aware observation semantics (Option 3).
   - Established that missing data by itself must not automatically mean the capture pipeline failed.
   - Identified that Schema v7 could not reliably distinguish swallowed provider technical errors from clean domain absence.
   - Mandated that historical Schema v7 evidence must not be retroactively reinterpreted.
   - *Note on packet preservation*: The historical `R7-PIT-STATUS-DEC-001` decision packet is strictly preserved and not retroactively edited. This document supersedes only its tentative implementation assumptions where subsequent empirical evidence completed the picture.

2. **`MVP-ARCH-001-R7-PIT-STATUS-HARDEN-001` (Merged)**:
   - Hardened the Yahoo Finance lookup path with single-inheritance typed exceptions (`EarningsProviderLookupError`, `EarningsProviderResponseError`).
   - Established deterministic classification precedence: valid date $\to$ response error $\to$ technical error $\to$ clean unavailable.
   - Proved that technical provider errors no longer collapse into clean domain absence.

3. **`MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001` (Completed from SHA `5731baacf73197a15eb9c72c1d6eb2e16a09962b`)**:
   - Authorized and executed a bounded, single live study across all 45 Candidate C symbols.
   - Study disposition: `completed_evidence_sufficient_for_next_decision`.
   - **Yahoo Finance findings**: 30/30 Candidate B equities returned `KNOWN` upcoming dates; 15/15 sector ETFs cleanly raised `EarningsDataUnavailableError` (`CLEAN_NO_USABLE_UPCOMING_DATE`); zero technical or response errors.
   - **Massive reference findings**: 45/45 symbols returned `KNOWN` active reference records (30 provider type code `CS`, 15 provider type code `ETF`); zero error categories; `delisted_utc` missing on 100% of active records as expected.
   - **Governance guard**: While this empirical observation confirms that sector ETFs lacked upcoming earnings dates on Yahoo at observation time, this evidence is **never converted into a hardcoded application rule** such as `if type == "ETF"` or `if symbol in ETF_LIST`. Applicability must remain manifest-declared, versioned, and auditable.

---

## 3. Verified Starting State & Governance Invariants

At base SHA `024dfc2659cd64bb96aff91ae8d312b9c049ac52`:
- Database Schema is **v7**.
- `PIT_CAPTURE_CONTRACT_VERSION = 1`.
- Universe manifest contract is **v1** (material fields: `contract_version`, `universe_id`, `universe_version`, `effective_from`, `symbols`).
- `universe_hash` represents the SHA-256 hash of the normalized sorted symbol set.
- `manifest_hash` represents material manifest content but is not persisted on capture runs.
- Persisted earnings statuses: `KNOWN`, `UNAVAILABLE`, `ERROR`.
- Persisted reference statuses: `KNOWN`, `UNAVAILABLE`, `AMBIGUOUS`, `ERROR`.
- No persisted `NOT_APPLICABLE` observation status exists in the database.
- Capture run status remains strict all-known (`known_n == requested_n` $\implies$ `SUCCEEDED`).
- Operational status `PITOperationalStatus.SUCCEEDED` requires both family runs to be `SUCCEEDED`.
- Slot health `PITSlotHealthStatus.HEALTHY` requires successful terminal runs for both families.
- Candidate B and Candidate C remain unselected (`selected_universe = null`).
- No OS scheduler is installed or authorized.
- Option 2 + 3 production semantics are not implemented in application code.
- `APPROVED_PRODUCTION_STRATEGIES == ()`.
- Rollout Step 7 (R7) remains incomplete.

---

## 4. Core Contract 1: Manifest Applicability Contract (v2)

### 4.1 Specification
Point-in-time applicability must be declared in the versioned universe manifest, completely eliminating hardcoded ticker lists or runtime classification heuristics.

The manifest contract is bumped to `contract_version: 2`:
```json
{
  "contract_version": 2,
  "universe_id": "candidate-dow30-sector-etfs",
  "universe_version": "v2",
  "effective_from": "2026-09-17",
  "symbols": [
    "AAPL",
    "AMGN",
    "DIA",
    "SPY"
  ],
  "applicability": {
    "AAPL": {
      "earnings": "required",
      "reference": "required"
    },
    "AMGN": {
      "earnings": "required",
      "reference": "required"
    },
    "DIA": {
      "earnings": "not_applicable",
      "reference": "required"
    },
    "SPY": {
      "earnings": "not_applicable",
      "reference": "required"
    }
  },
  "description": "Candidate C 45-symbol universe with explicit PIT applicability."
}
```

### 4.2 Field Requirements & Enums
- `contract_version`: Must be integer `2`.
- `universe_id`: String matching `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`.
- `universe_version`: Non-empty string.
- `effective_from`: ISO date string `YYYY-MM-DD`.
- `symbols`: Non-empty array of valid ticker strings. Normalized at load time (trimmed, uppercased, deduplicated, sorted).
- `applicability`: Object mapping every normalized symbol in `symbols` to a family applicability dictionary:
  * `earnings`: Must be either `"required"` or `"not_applicable"`.
  * `reference`: Must be `"required"`.
- `description`: Optional human-readable description (non-material).

### 4.3 Reference Family Universality (Minimal Schema Surface Area)
Reference data (ticker identity, legal name, security type, exchange, active status) is fundamental to every tradable security in TradeX. There is no domain concept of a security that belongs to an operational universe yet has "not applicable" reference metadata.
Therefore:
- `reference` applicability is locked to `"required"` for all symbols.
- Reference observations do not require `NOT_APPLICABLE` persistence or origin columns, minimizing Schema v8 surface area.

### 4.4 Deterministic Validation & Backward Compatibility
- **v2 Missing Declaration Policy (Fail-Closed)**:
  Every symbol in `symbols` must have an exact key in `applicability`, and every supported family (`earnings`, `reference`) must be explicitly declared. Any missing symbol, extra symbol, missing family, or unapproved enum value raises a hard `ValueError` on load.
- **v1 Backward Compatibility Policy**:
  When loading a legacy `contract_version: 1` manifest, TradeX synthesizes `{ "earnings": "required", "reference": "required" }` for all symbols in the in-memory representation. However, this synthesized structure **MUST NOT** alter the historical v1 `manifest_hash`.

---

## 5. Core Contract 2: Audit Identity and Drift Detection

### 5.1 Identity Definitions
1. **`universe_hash` (Symbol-Set Identity)**:
   Retains its exact historical definition and meaning:
   $$\text{universe\_hash} = \text{SHA-256}\left(\text{join}(\text{sorted}(\text{normalized\_symbols}), \text{","})\right)$$
2. **`manifest_hash` (Material Manifest Identity)**:
   Cryptographically commits to all material manifest fields:
   - For **v1 manifests** (`contract_version == 1`):
     ```python
     payload = {
         "contract_version": 1,
         "effective_from": manifest.effective_from.isoformat(),
         "symbols": list(manifest.symbols),
         "universe_id": manifest.universe_id,
         "universe_version": manifest.universe_version,
     }
     manifest_hash = sha256(canonical_json(payload))
     ```
     Preserved identically with base commit `024dfc2659cd64bb96aff91ae8d312b9c049ac52`.
   - For **v2 manifests** (`contract_version == 2`):
     ```python
     payload = {
         "applicability": {
             sym: {
                 fam: manifest.applicability[sym][fam]
                 for fam in sorted(manifest.applicability[sym].keys())
             }
             for sym in sorted(manifest.symbols)
         },
         "contract_version": 2,
         "effective_from": manifest.effective_from.isoformat(),
         "symbols": list(manifest.symbols),
         "universe_id": manifest.universe_id,
         "universe_version": manifest.universe_version,
     }
     manifest_hash = sha256(canonical_json(payload))
     ```
     If symbols remain identical but applicability rules change, `manifest_hash` changes deterministically.

### 5.2 Persisted Identity
In Schema v8:
- `pit_capture_runs` and `pit_reference_capture_runs` persist both `universe_hash` and `manifest_hash`.
- To preserve historical truthfulness without backfilling synthetic sentinels:
  * For historical v1 rows: `manifest_hash IS NULL`.
  * For prospective v2 rows: `manifest_hash IS NOT NULL`.

### 5.3 Request Fingerprint and Idempotency Key
- For **contract v2 runs**, the request fingerprint incorporates `manifest_hash`:
  ```python
  canonical_dict = {
      "capture_date": capture_date,
      "capture_kind": capture_kind,  # "earnings" or "reference"
      "capture_slot": capture_slot,
      "contract_version": 2,
      "manifest_hash": manifest_hash,
      "requested_provider": requested_provider,
      "scheduled_for": scheduled_for_iso,
      "symbols": list(normalized_symbols),
  }
  request_fingerprint = sha256(canonical_json(canonical_dict))
  ```
  Because `manifest_hash` already cryptographically commits to applicability and universe metadata, raw applicability dictionaries are not redundantly duplicated.
- **Idempotency keys**:
  * Earnings: `f"pit-earnings-{capture_date}-{slot.value}-{request_fingerprint[:16]}"`
  * Reference: `f"pit-reference-{capture_date}-{slot.value}-{request_fingerprint[:16]}"`

### 5.4 Manifest Drift Guard
Before executing any capture or recording slot health for `(capture_date, slot)`:
1. **Symbol Drift**: If any existing run has `existing_run.universe_hash != manifest.universe_hash` $\implies$ raise `PITOperationalUniverseConflictError`.
2. **Manifest Drift**: If any existing contract v2 run has `existing_run.manifest_hash != manifest.manifest_hash` $\implies$ raise `PITOperationalManifestConflictError`.
3. **Cross-Version Conflict**: If an existing run is contract v1 and the current manifest is v2 (or vice versa) $\implies$ raise `PITOperationalManifestConflictError`.

---

## 6. Core Contract 3: Schema v8 Specification

### 6.1 Version Constants
- `_SCHEMA_VERSION = 8` (in `tradex/tracker/store.py`).
- `PIT_CAPTURE_CONTRACT_VERSION = 2` (in `tradex/pit/models.py`).

### 6.2 Table DDL Specifications

#### 1. `pit_capture_runs`
```sql
CREATE TABLE pit_capture_runs (
    capture_run_id      TEXT PRIMARY KEY,
    contract_version    INTEGER NOT NULL DEFAULT 2 CHECK (contract_version IN (1, 2)),
    idempotency_key     TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    capture_kind        TEXT NOT NULL CHECK (capture_kind IN ('earnings')),
    capture_slot        TEXT NOT NULL CHECK (capture_slot IN ('evening', 'morning')),
    capture_date        TEXT NOT NULL,
    scheduled_for       TEXT NOT NULL,
    requested_at        TEXT NOT NULL,
    completed_at        TEXT,
    requested_provider  TEXT NOT NULL,
    universe_hash       TEXT NOT NULL,
    manifest_hash       TEXT,
    requested_n         INTEGER NOT NULL CHECK (requested_n >= 1),
    known_n             INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
    not_applicable_n    INTEGER NOT NULL DEFAULT 0 CHECK (not_applicable_n >= 0),
    unavailable_n       INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
    error_n             INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
    status              TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK ((contract_version = 1 AND manifest_hash IS NULL) OR (contract_version = 2 AND manifest_hash IS NOT NULL)),
    CHECK (status = 'started' OR completed_at IS NOT NULL),
    CHECK (status = 'started' OR requested_n = (known_n + not_applicable_n + unavailable_n + error_n))
);

CREATE INDEX idx_pit_runs_date_slot ON pit_capture_runs(capture_date, capture_slot);
CREATE INDEX idx_pit_runs_status    ON pit_capture_runs(status);
CREATE INDEX idx_pit_runs_requested ON pit_capture_runs(requested_at);
```

#### 2. `pit_earnings_snapshots`
```sql
CREATE TABLE pit_earnings_snapshots (
    snapshot_id             TEXT PRIMARY KEY,
    contract_version        INTEGER NOT NULL DEFAULT 2 CHECK (contract_version IN (1, 2)),
    capture_run_id          TEXT NOT NULL REFERENCES pit_capture_runs(capture_run_id) ON DELETE CASCADE,
    symbol                  TEXT NOT NULL,
    observation_status      TEXT NOT NULL CHECK (observation_status IN ('known', 'not_applicable', 'unavailable', 'error')),
    observation_origin      TEXT NOT NULL DEFAULT 'provider' CHECK (observation_origin IN ('provider', 'manifest')),
    applicability_source    TEXT CHECK (applicability_source IS NULL OR applicability_source IN ('manifest')),
    provider_call_attempted INTEGER NOT NULL DEFAULT 1 CHECK (provider_call_attempted IN (0, 1)),
    next_earnings_date      TEXT,
    provider                TEXT,
    provider_observed_at    TEXT,
    request_started_at      TEXT,
    response_received_at    TEXT,
    fact_hash               TEXT NOT NULL,
    fact_json               TEXT NOT NULL,
    error_category          TEXT,
    error_message           TEXT,
    created_at              TEXT NOT NULL,
    UNIQUE (capture_run_id, symbol),
    CHECK ((observation_status = 'known' AND next_earnings_date IS NOT NULL) OR (observation_status != 'known' AND next_earnings_date IS NULL)),
    CHECK (
        (observation_origin = 'manifest'
         AND observation_status = 'not_applicable'
         AND provider IS NULL
         AND provider_observed_at IS NULL
         AND request_started_at IS NULL
         AND response_received_at IS NULL
         AND provider_call_attempted = 0
         AND applicability_source = 'manifest')
        OR
        (observation_origin = 'provider'
         AND observation_status != 'not_applicable'
         AND provider IS NOT NULL
         AND request_started_at IS NOT NULL
         AND response_received_at IS NOT NULL
         AND provider_call_attempted = 1
         AND applicability_source IS NULL
         AND request_started_at <= response_received_at)
    )
);

CREATE INDEX idx_pit_snaps_run_id    ON pit_earnings_snapshots(capture_run_id);
CREATE INDEX idx_pit_snaps_symbol    ON pit_earnings_snapshots(symbol);
CREATE INDEX idx_pit_snaps_next_date ON pit_earnings_snapshots(next_earnings_date);
CREATE INDEX idx_pit_snaps_status    ON pit_earnings_snapshots(observation_status);
```

#### 3. `pit_reference_capture_runs`
```sql
CREATE TABLE pit_reference_capture_runs (
    capture_run_id      TEXT PRIMARY KEY,
    contract_version    INTEGER NOT NULL DEFAULT 2 CHECK (contract_version IN (1, 2)),
    idempotency_key     TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    capture_slot        TEXT NOT NULL CHECK (capture_slot IN ('evening', 'morning')),
    capture_date        TEXT NOT NULL,
    scheduled_for       TEXT NOT NULL,
    requested_at        TEXT NOT NULL,
    completed_at        TEXT,
    requested_provider  TEXT NOT NULL,
    universe_hash       TEXT NOT NULL,
    manifest_hash       TEXT,
    requested_n         INTEGER NOT NULL CHECK (requested_n >= 1),
    known_n             INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
    unavailable_n       INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
    ambiguous_n         INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_n >= 0),
    error_n             INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
    status              TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK ((contract_version = 1 AND manifest_hash IS NULL) OR (contract_version = 2 AND manifest_hash IS NOT NULL)),
    CHECK (status = 'started' OR completed_at IS NOT NULL),
    CHECK (status = 'started' OR requested_n = (known_n + unavailable_n + ambiguous_n + error_n))
);

CREATE INDEX idx_pit_ref_runs_date_slot ON pit_reference_capture_runs(capture_date, capture_slot);
CREATE INDEX idx_pit_ref_runs_status    ON pit_reference_capture_runs(status);
CREATE INDEX idx_pit_ref_runs_requested ON pit_reference_capture_runs(requested_at);
```

#### 4. `pit_reference_snapshots`
```sql
CREATE TABLE pit_reference_snapshots (
    snapshot_id                TEXT PRIMARY KEY,
    contract_version           INTEGER NOT NULL DEFAULT 2 CHECK (contract_version IN (1, 2)),
    capture_run_id             TEXT NOT NULL REFERENCES pit_reference_capture_runs(capture_run_id) ON DELETE CASCADE,
    symbol                     TEXT NOT NULL,
    observation_status         TEXT NOT NULL CHECK (observation_status IN ('known', 'unavailable', 'ambiguous', 'error')),
    provider                   TEXT NOT NULL,
    provider_query_date        TEXT NOT NULL,
    provider_request_ids_json  TEXT NOT NULL DEFAULT '[]',
    provider_ticker            TEXT,
    provider_name              TEXT,
    provider_market            TEXT,
    provider_locale            TEXT,
    provider_active            INTEGER CHECK (provider_active IS NULL OR provider_active IN (0, 1)),
    provider_type_code         TEXT,
    provider_primary_exchange  TEXT,
    provider_cik               TEXT,
    provider_composite_figi    TEXT,
    provider_share_class_figi  TEXT,
    provider_last_updated_at   TEXT,
    provider_delisted_at       TEXT,
    missing_fields_json        TEXT NOT NULL DEFAULT '[]',
    request_started_at         TEXT NOT NULL,
    response_received_at       TEXT NOT NULL,
    fact_hash                  TEXT NOT NULL,
    fact_json                  TEXT NOT NULL,
    error_category             TEXT,
    error_message              TEXT,
    created_at                 TEXT NOT NULL,
    UNIQUE (capture_run_id, symbol),
    CHECK (request_started_at <= response_received_at)
);

CREATE INDEX idx_pit_ref_snaps_run_id ON pit_reference_snapshots(capture_run_id);
CREATE INDEX idx_pit_ref_snaps_symbol ON pit_reference_snapshots(symbol);
CREATE INDEX idx_pit_ref_snaps_status ON pit_reference_snapshots(observation_status);
```

---

## 7. Core Contract 4: Historical Semantics (Versioned Bifurcation)

### 7.1 Policy: Zero Historical Reinterpretation
TradeX enforces strict versioned bifurcation:
1. **Historical contract-v1 rows** (`contract_version == 1`):
   - Preserved verbatim. Historical `UNAVAILABLE` observations remain `UNAVAILABLE`.
   - `manifest_hash` remains strictly `NULL`. No synthetic manifest hash is fabricated.
   - Adding nullable columns with default values during migration is purely schema evolution and does not constitute retrospective semantic rewriting.
   - Historical slot health evaluation uses the historical strict all-known evaluation rules.
2. **Prospective contract-v2 rows** (`contract_version == 2`):
   - Evaluated under the new two-dimensional model: operational health vs. evidence completeness.
   - `manifest_hash` is mandatory and auditable.

---

## 8. Core Contract 5: Operational Execution Health

Operational health answers:
> **Did TradeX execute reliably and truthfully record provider/domain evidence?**

It does **not** answer:
> **Did TradeX obtain every desired fact?**

### 8.1 Observation-Level Health Contribution
| Outcome | Operational Meaning | Health Impact |
|---|---|---|
| `KNOWN` | Provider returned valid fact | Healthy |
| `NOT_APPLICABLE` | Manifest applicability recorded; provider skipped | Healthy |
| `UNAVAILABLE` (clean) | Provider contacted; clean domain absence truthfully recorded | Healthy |
| `AMBIGUOUS` (reference) | Provider contacted; ambiguous candidate set truthfully audited | Healthy |
| `ERROR` | Network, transport, auth, rate-limit, or response failure | Degraded / Failed |

### 8.2 Operational Health Truth Table
| Slot Condition | Overall Operational Health | Exit Code |
|---|---|---|
| Non-trading day OR current time before slot scheduled time | `NOT_DUE` | `0` |
| Slot due; zero conflicts; both families have terminal `SUCCEEDED` runs (`error_n == 0`) | `HEALTHY` | `0` |
| Slot due; at least one family run remains in `STARTED` state | `DEGRADED` | `2` |
| Slot due; at least one family has terminal `PARTIAL` run (`0 < error_n < requested_n`) and neither has failed | `DEGRADED` | `2` |
| Slot due; expected family has zero runs (`MISSING`) | `FAILED` | `1` |
| Manifest or symbol hash conflict with existing runs | `FAILED` (`UNIVERSE_CONFLICT`) | `1` |
| Total provider failure in either family (`error_n == requested_n`) | `FAILED` | `1` |
| Preflight abort, authentication error, entitlement failure, or unhandled exception | `FAILED` | `1` |
| Database corruption or SQLite write failure | `FAILED` | `1` |
| Future-dated manifest (`manifest.effective_from > current_date`) | `FAILED` | `1` |

*Note on Stale Runs*: Arbitrary timeouts for "hung" runs are explicitly deferred. Any unfinalized `STARTED` run is deterministically classified as `DEGRADED` (incomplete).

---

## 9. Core Contract 6: Evidence Completeness

Evidence completeness is an **independent read-model dimension** designed for downstream research, backtesting, and strategy modeling. It **never** alters operational execution health or CLI exit codes.

### 9.1 Family-Level Derivation
For each capture family:
1. **Applicable Denominator ($D$)**:
   - Earnings: $D = \text{applicable\_n} = \text{requested\_n} - \text{not\_applicable\_n}$
   - Reference: $D = \text{applicable\_n} = \text{requested\_n}$ ($\text{not\_applicable\_n} = 0$ logically)
2. **Known Numerator ($N$)**:
   - $N = \text{known\_n}$
3. **Completeness Ratio ($C$)**:
   - If $D > 0$: $C = N / D$
   - If $D == 0$: $C = 1.0$ (with `all_not_applicable = true`)
4. **Deterministic Categorical Tiers (No Arbitrary Percentage Thresholds)**:
   - If $D == 0$: `COMPLETE` (trivially complete; zero missing applicable facts)
   - Else if $N == D$: `COMPLETE` (100% of applicable facts known)
   - Else if $N > 0$: `PARTIAL` (some applicable facts known)
   - Else ($N == 0$): `SPARSE` (zero applicable facts known)

`UNAVAILABLE`, `AMBIGUOUS`, and `ERROR` are non-known outcomes and remain in the applicable denominator.

### 9.2 Slot-Level Aggregation
- **`COMPLETE`**: Every expected family is `COMPLETE`.
- **`SPARSE`**: At least one expected family has $D > 0$ and $N == 0$.
- **`PARTIAL`**: Otherwise (e.g. one family is `COMPLETE` and the other is `PARTIAL`, or both are `PARTIAL`).
- **Pooled Ratio (Informational Only)**:
  $$C_{\text{slot}} = \frac{N_{\text{earnings}} + N_{\text{reference}}}{D_{\text{earnings}} + D_{\text{reference}}}$$
  The pooled ratio is displayed for informational purposes only and **never masks a sparse family**.

---

## 10. Core Contract 7: Provider-Call Behavior for NOT_APPLICABLE

### 10.1 Decision: Skip Provider Call
TradeX explicitly selects the **Skip Provider Call** model for manifest-declared `not_applicable` facts.

### 10.2 Truthful Provenance Contract
The manifest is **not a provider**. TradeX truthfully records:
- `observation_origin`: `"manifest"`
- `applicability_source`: `"manifest"`
- `provider_call_attempted`: `0` (false)
- `provider`: `NULL`
- `provider_observed_at`: `NULL`
- `request_started_at`: `NULL`
- `response_received_at`: `NULL`
- `next_earnings_date`: `NULL`
- `error_category`: `NULL`
- `error_message`: `NULL`
- `fact_json`:
  ```json
  {"applicability_source":"manifest","error_category":null,"error_message":null,"next_earnings_date":null,"status_reason":"manifest_not_applicable"}
  ```
- `fact_hash`: SHA-256 hex digest of the canonical `fact_json` string.

Zero network traffic occurs, zero latency is fabricated, and provider response variations cannot contaminate domain applicability.

---

## 11. Core Contract 8: Capture-Run Lifecycle Compatibility

`CaptureRunStatus` remains strictly:
$$\text{STARTED} \longrightarrow \text{SUCCEEDED} \mid \text{PARTIAL} \mid \text{FAILED}$$

It represents the **operational execution lifecycle of the run**, completely distinct from evidence completeness:
- `STARTED`: Capture run initialized in database; execution in progress.
- `SUCCEEDED`: 100% of symbols resolved with zero technical or provider errors ($\text{error\_n} == 0$). Clean `UNAVAILABLE`, legitimate `NOT_APPLICABLE`, and reference `AMBIGUOUS` records do **not** prevent `SUCCEEDED`.
- `PARTIAL`: Some but not all requested symbols suffered technical/provider errors ($0 < \text{error\_n} < \text{requested\_n}$).
- `FAILED`: All requested symbols suffered technical/provider errors ($\text{error\_n} == \text{requested\_n}$), or an unhandled fatal run-level exception occurred.

---

## 12. Core Contract 9: CLI Contract

### 12.1 Exit Codes
Process exit codes are governed strictly by **operational execution health**:
- **Exit `0`**: Operationally `HEALTHY` or `NOT_DUE`.
- **Exit `2`**: Operational `DEGRADED` (incomplete run or partial provider errors).
- **Exit `1`**: Operational `FAILED` (missing run, manifest conflict, total provider failure, fatal exception).

Evidence completeness is surfaced in JSON read models but **never alters process exit codes**.

### 12.2 Structured JSON Output
#### `run-slot` JSON Output Shape
```json
{
  "contract_version": 2,
  "capture_date": "2026-09-17",
  "slot": "evening",
  "scheduled_for": "2026-09-17T20:30:00-04:00",
  "requested_at": "2026-09-17T20:30:02.123456+00:00",
  "universe_id": "candidate-dow30-sector-etfs",
  "universe_version": "v2",
  "manifest_hash": "a1b2c3...",
  "universe_hash": "d4e5f6...",
  "symbol_count": 45,
  "operational_status": "succeeded",
  "evidence_completeness": {
    "overall_tier": "complete",
    "pooled_ratio": 1.0,
    "pooled_pct": 100.0,
    "total_applicable_n": 75,
    "total_known_n": 75
  },
  "earnings": {
    "capture_run_id": "run-earnings-123",
    "status": "succeeded",
    "requested_n": 45,
    "known_n": 30,
    "not_applicable_n": 15,
    "unavailable_n": 0,
    "error_n": 0,
    "error_detail": null,
    "completeness": {
      "tier": "complete",
      "ratio": 1.0,
      "pct": 100.0,
      "applicable_n": 30,
      "all_not_applicable": false
    }
  },
  "reference": {
    "capture_run_id": "run-ref-123",
    "status": "succeeded",
    "requested_n": 45,
    "known_n": 45,
    "unavailable_n": 0,
    "ambiguous_n": 0,
    "error_n": 0,
    "error_detail": null,
    "completeness": {
      "tier": "complete",
      "ratio": 1.0,
      "pct": 100.0,
      "applicable_n": 45,
      "all_not_applicable": false
    }
  }
}
```

---

## 13. Core Contract 10: Migration Safety & 12-Step Rebuild Procedure

Because SQLite does not support modifying existing table `CHECK` constraints in place, Schema v7 $\to$ v8 uses SQLite's canonical 12-step table rebuild inside a single atomic transaction:

1. `PRAGMA foreign_keys = OFF;` (disabled temporarily for table swaps).
2. `BEGIN TRANSACTION;`
3. Verify current `PRAGMA user_version == 7`.
4. Capture source row counts from all 4 PIT tables:
   ```sql
   SELECT count(*) FROM pit_capture_runs;
   SELECT count(*) FROM pit_earnings_snapshots;
   SELECT count(*) FROM pit_reference_capture_runs;
   SELECT count(*) FROM pit_reference_snapshots;
   ```
5. Create temporary Schema v8 tables (`pit_capture_runs_v8`, `pit_earnings_snapshots_v8`, `pit_reference_capture_runs_v8`, `pit_reference_snapshots_v8`).
6. Copy data verbatim:
   - For `pit_capture_runs`: copy all columns verbatim, setting `manifest_hash = NULL`, `not_applicable_n = 0`.
   - For `pit_earnings_snapshots`: copy all columns verbatim, setting `observation_origin = 'provider'`, `applicability_source = NULL`, `provider_call_attempted = 1`.
   - For `pit_reference_capture_runs`: copy all columns verbatim, setting `manifest_hash = NULL`.
   - For `pit_reference_snapshots`: copy all columns verbatim.
7. Verify destination row counts equal source row counts exactly.
8. Drop old tables (`DROP TABLE pit_earnings_snapshots;`, `DROP TABLE pit_capture_runs;`, etc.).
9. Rename `_v8` tables to canonical table names.
10. Recreate all original indexes.
11. Run `PRAGMA foreign_key_check;` and assert zero violations.
12. Set `PRAGMA user_version = 8;`
13. `COMMIT;`
14. `PRAGMA foreign_keys = ON;` (re-enabled).

**Rollback Guarantee**: If any step raises an error or row counts mismatch, `ROLLBACK` reverts all operations completely, leaving the database at Schema v7.
**Idempotency**: Running on a database with `PRAGMA user_version == 8` is a no-op. Databases with `user_version > 8` raise `StoreError` rejecting downgrades.

---

## 14. Candidate B and Candidate C Dispositions

Consistent with all governance boundaries, **Candidate B and Candidate C remain unselected**:
- **Candidate B** (`candidate-dow30`, 30 equities): Resolves structural earnings risk by excluding ETFs, but lacks sector context. Status: `unselected`.
- **Candidate C** (`candidate-dow30-sector-etfs`, 30 equities + 15 sector ETFs): Fully supported by the Option 2 + 3 architecture via manifest-declared earnings `not_applicable` for ETFs, preserving operational health. Status: `unselected`.

Selection of Candidate B or Candidate C requires a **separate Gary decision** and is not authorized by this PR.

---

## 15. Bounded Future Implementation PR Decomposition

Implementation of this readiness contract must be partitioned into three independently reviewable, bounded PRs:

### Implementation PR A — Versioned Applicability & Persistence Primitives
- **Scope**:
  * Manifest contract v2 loader, parser, and validator.
  * Versioned manifest hashing (v1 exact preservation, v2 applicability hashing).
  * Request fingerprint v2 and idempotency key derivation.
  * Schema v8 migration script, table rebuild procedure, and store tests.
  * Domain models (`PITEarningsSnapshot`, `PITCaptureRun`, etc.) updated with contract v2 fields.
- **Boundaries**: No operational health policy changes; no CLI exit code changes; no scheduler.

### Implementation PR B — Two-Dimensional Operational & Read-Model Semantics
- **Scope**:
  * Operational slot runner updated for two-dimensional status evaluation.
  * Skip-provider-call behavior for `not_applicable` earnings facts.
  * Evidence completeness read model (family and slot-level count aggregation).
  * CLI `run-slot` and `health` subcommands updated with exit codes `0/2/1` and structured JSON.
  * Versioned bifurcation reader preserving strict legacy semantics for historical v1 runs.
- **Boundaries**: No universe selection; no scheduler installation; Candidate B/C remain unselected.

### Implementation PR C — Universe Selection & C2 Operational Activation
- **Scope**:
  * Formal Gary decision recording selection of Candidate B vs Candidate C.
  * Production universe manifest placed in canonical location with locked `effective_from`.
  * Scheduler installation and automation documentation.
- **Boundaries**: Separate Gary authorization required.

---

## 16. Non-Authorizations & Governance Invariants

This readiness packet explicitly affirms:
- `production_status_semantics_change_authorized`: `false`
- `schema_migration_authorized`: `false`
- `provider_study_authorized`: `false`
- `active_universe_authorized`: `false`
- `c2_implementation_authorized`: `false`
- `scheduler_authorized`: `false`
- `approved_production_strategies`: `[]`
- `r7_status`: `"incomplete"`
- `candidate_b_status`: `"unselected"`
- `candidate_c_status`: `"unselected"`
- `selected_universe`: `null`
- `tradex/` modifications: `0`
- `APPROVED_PRODUCTION_STRATEGIES == ()` remains true.
