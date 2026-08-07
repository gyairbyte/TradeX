# INTRA-001B Reference Provider Decision

**Formal v2 disposition:** `invalid` / not decision-grade. The v2 pre-registration, safe artifact bundle, and provider first-page evidence at `docs/research/artifacts/INTRA-001B-REFERENCE/2026-08-07-222404/` are preserved as an audit record. Massive/Polygon is **not** yet locked as the authoritative reference provider. A bounded v3 proposal is in preparation.

## Why v2 is not decision-grade

The v2 live probe collected only the first `limit=1000` page per PIT date/state from `/v3/reference/tickers`. Every Massive observation in the v2 bundle has `row_count=1000`, which does not prove complete active membership, inactive/delisted coverage, duplicate behavior, full type/exchange coverage, or feasibility of all 48 monthly PIT snapshots. The v2 artifact generator and decision schema were also incomplete relative to the approved mandatory gates. No strategy rules, `INTRA-001-v1.json`, or production trading logic change as a result of this disposition.

## v2 audit lock points

- **v1 pre-registration commit:** `e4d123e5ecca80ab8ba1fa09ff397d4f0a3d67dc`
- **v2 pre-registration commit:** `d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299`
- **v2 live run head:** `d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299`
- **v2 PR head:** `f6f63f3b337d48e4e65144260c4cb24f50b22089`
- **v2 safe artifact bundle:** `docs/research/artifacts/INTRA-001B-REFERENCE/2026-08-07-222404/` (frozen, not modified)
- **Original strategy spec:** `docs/research/specs/INTRA-001-v1.json` (SHA-256 unchanged)
- **Original strategy spec SHA-256:** `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- **Alpaca v2 OHLCV decision:** `docs/research/artifacts/INTRA-001B-ALPACA-V2/2026-08-07-175845/decision.json`

## v2 provider evidence summary

- Alpha Vantage `LISTING_STATUS` was attempted first. The configured free API key exhausted its daily request limit and returned empty `{}` for every PIT date; it was not selected.
- Massive `/v3/reference/tickers` returned repeatable first-page samples for active and inactive states across all four original PIT dates, with a `type` field containing values such as `CS`, `ETF`, `PFD`, `RIGHT`, `UNIT`, and `WARRANT`, and a `primary_exchange` field with `XNYS`, `XNAS`, `ARCX`, `BATS`, and `XASE`.
- The first-page evidence makes Massive a strong v3 candidate, but it does **not** prove complete PIT universe reconstruction.

## v3 direction

A bounded `INTRA-001B-REFERENCE-V3` proposal is in `docs/research/INTRA-001B-REFERENCE-V3-PROPOSAL.md` and `docs/research/specs/INTRA-001B-reference-probe-v3.json` (draft, not yet pre-registered for live use). It will:

1. Exhaust pagination to terminal `next_url=null` for each PIT snapshot, recording provider `count`, page count, per-page counts/hashes, and pagination completeness.
2. Make pagination completeness an approval gate; a safety max may only trigger failure, not successful truncation.
3. Query the Massive Ticker Types endpoint and lock the documented code-to-category taxonomy.
4. Prove each required security-type exclusion individually: OTC, warrant, right, unit, and preferred stock; default unmapped types to ineligible.
5. Keep common stock (`CS`) and ETF as separate allowlist strata.
6. Preserve every attempted provider/date/state in the audit trail, including Alpha Vantage failures.
7. Use unambiguous provenance fields (`v1_pre_registration_commit`, `v2_pre_registration_commit`, `v3_pre_registration_commit`, `live_run_head`, `final_pr_head`).
8. Satisfy the full machine-readable decision schema with provenance, boundary, and blocker fields.
9. Enforce the locked safe-bundle contract against `expected_safe_artifacts`.
10. Expand focused tests to cover pagination, cycle/repeated-cursor handling, all mandatory gates, candidate-order audit, exact-date semantics, duplicate symbols, taxonomy mapping, each security exclusion/OTC, provenance fields, artifact-spec conformance, and decision branching.

## Amendment status

- `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` remains the active amendment but its status returns to `approved_mixed_model_reference_provider_pending` until a valid v3 reference-provider decision.
- `reference_provider` is not locked to `massive` until v3 passes.

## What does not change

- `INTRA-001-v1.json` and its SHA-256 are untouched.
- No production provider behavior, `SUPPORTED_OHLCV_PROVIDERS`, `tradex/data/fetcher.py`, scores, weights, thresholds, rankings, screeners, alerts, or dashboards change.
- No paid upgrade or Alpha Vantage + Massive composite stack is introduced.
