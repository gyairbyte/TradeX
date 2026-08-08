# INTRA-001 Data-Sufficiency Amendment v3

**Amendment ID:** `INTRA-001-data-sufficiency-amendment-v3`  
**Status:** `approved_best_available_data_ready_for_snapshot_implementation`  
**Evidence label:** `limited_but_usable_evidence`  
**Supersedes:** `INTRA-001-data-contract-amendment-v2` for prospective dataset construction only.

This amendment codifies Gary's product decision to stop provider hunting and proceed with the best reliable data reasonably available for `INTRA-001`. It is a methodology and data-contract amendment only. It does not change `INTRA-001-v1.json`, any trading rule, cost, threshold, sample minimum, validation gate, or holdout discipline.

## What does not change

* `docs/research/specs/INTRA-001-v1.json` and its SHA-256 (`09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`) remain untouched.
* Amendment v2 (`docs/research/specs/INTRA-001-data-contract-amendment-v2.json`) and all V3/V4 reference-provider probe evidence remain preserved as historical audit records.
* V4's strict-contract disposition remains `unsupported`. The V4 probe honestly proved that Massive/Polygon did not meet the original idealized reference-provider contract under the pre-registered gates.
* No V5 reference-provider probe is authorized.
* No production signal, score, weight, threshold, ranking, eligibility, screener, alert, dashboard, brokerage, or order behavior changes.
* `INTRA-001C` strategy implementation and `INTRA-001D` real-data evaluation are still out of scope; they begin only on separate branches after snapshot infrastructure is built.

## What changes

### Provider contract

| Role | Provider | Status |
|---|---|---|
| Authoritative OHLCV | Alpaca SIP | Accepted and locked |
| Reference/security-master input | Massive / Polygon `GET /v3/reference/tickers` | Accepted **with documented limitations** |

* Alpaca SIP remains the sole source for five-minute OHLCV, prior closes, prior 20-session dollar-volume baselines, session VWAP inputs, opening-drive volume, and execution prices.
* Massive becomes the `best_available_reference_input` for monthly point-in-time stock listings, security-type classification, and exchange provenance. It is **not** relabeled as strict-contract `supported`.

### Accepted limitations

* **No explicit OTC marker:** Massive's US `stocks` taxonomy and exchange set do not surface an explicit OTC marker. Conservative exclusion is performed through the listed-exchange allowlist and security-type allowlist.
* **Duplicate symbols in inactive snapshots:** Some historical inactive tickers map to multiple records without a consistent `cik`, `figi`, or `composite_figi`. Any ticker with more than one record in a PIT snapshot is excluded.
* **Limited history:** The available free-entitlement window is shorter than the original 2022-2025 contract. The 2025-only dataset is a documented limitation, not a validity blocker.
* **Security-type and exchange provenance as-provided:** Unknown or unmapped values are conservatively excluded.

### Conservative universe controls

* Build each month's candidate stock universe from the completely paginated Massive active-listing snapshot as of the prior calendar month-end.
* Monthly PIT snapshots cover `2024-12-31` through `2025-11-30` for effective months `2025-01` through `2025-12`.
* Preserve inactive snapshot provenance for lifecycle and survivorship auditing.
* Stock stratum allows only mapped `common_stock` records.
* ETF stratum remains the fixed list from `INTRA-001-v1.json` (`SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, SMH`).
* Listed-exchange allowlist based on V4 evidence: `XNYS, XNAS, ARCX, BATS, XASE, XBOS`.
* Exclude missing, unknown, unmapped, or non-allowlisted exchanges.
* Exclude any ticker with more than one reference record in the same PIT snapshot.
* Exclude missing or unmapped security types.
* Do not add manual ticker exceptions.
* Record every exclusion reason and the monthly exclusion count.
* Do not construct historical universes from today's active listings.
* Do not silently substitute providers or fields.
* If complete pagination or required PIT provenance is unavailable for a month, surface it explicitly; do not turn the failure into an empty successful snapshot.

### Locked 2025 dataset and splits

| Split | Start | End |
|---|---|---|
| Dataset | `2025-01-02` | `2025-12-31` |
| Development | `2025-01-02` | `2025-06-30` |
| Validation | `2025-07-01` | `2025-09-30` |
| Holdout | `2025-10-01` | `2025-12-31` |

* Splits are chronological and non-overlapping.
* The holdout must not be inspected during implementation or candidate debugging.
* A shorter history does **not** reduce the existing `INTRA-001-v1.json` sample minimums or validation/holdout gates.
* Any change to sample minimums, gates, costs, thresholds, or execution rules must be pre-registered before validation or holdout results are viewed.

## Why V4's `unsupported` disposition is preserved

`docs/research/INTRA-001B-REFERENCE-V4.md` records the honest result that Massive/Polygon did not satisfy the pre-registered V4 strict contract. This amendment explicitly accepts Massive **despite** that strict-contract failure, because:

* The Massive data is the best reasonably available reference input under the current free entitlement.
* The V4 failures (no explicit OTC marker, duplicate symbols) can be controlled through conservative exclusion rules rather than invalidating the entire study.
* No better free reference source has been identified after bounded, documented provider exploration.

## Evidence label

This amendment and the 2025 snapshot plan are labeled `limited_but_usable_evidence`. That communicates reduced confidence relative to the original four-year ideal contract. It does **not** authorize production promotion.

## Next step

The next approved branch is `devin/intra-001b-one-year-snapshot`, which will build the 2025 dataset and monthly universe manifests under this amendment. No live provider calls, V5 provider exploration, strategy implementation, or production changes occur in this governance PR.
