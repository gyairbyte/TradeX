# INTRA-001B-REFERENCE-V3 Proposal

## Scope

A bounded v3 reference-provider probe that corrects the v2 first-page defects and proves **complete point-in-time universe reconstruction** for the `INTRA-001` mixed-provider data contract. No live provider calls are made until Gary explicitly approves this proposal.

## What is preserved

- `docs/research/specs/INTRA-001B-reference-probe-v2.json` — frozen v2 pre-registration.
- `docs/research/artifacts/INTRA-001B-REFERENCE/2026-08-07-222404/` — frozen v2 first-page evidence (not modified).
- `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` — active amendment, status remains `approved_mixed_model_reference_provider_pending`.
- `docs/research/specs/INTRA-001-v1.json` and its SHA-256 remain untouched.
- `tradex/data/fetcher.py`, `tradex/data/history.py`, `SUPPORTED_OHLCV_PROVIDERS`, and production trading behavior remain untouched.

## What changed from v2 to v3

| Area | v2 limitation | v3 correction |
|------|---------------|---------------|
| Pagination | `max_pages=1` truncated every PIT snapshot to ~1000 rows | Exhaust `/v3/reference/tickers` to terminal `next_url=null`; record provider `count`, page count, per-page counts/hashes, and declare pagination completeness an approval gate. A `safety_max_pages` limit only triggers failure, never success. |
| Audit trail | Failed Alpha Vantage attempts were summarized in prose but not machine-captured; `candidate_dispositions` was empty | Every attempted provider/date/state (including Alpha Vantage failures) is stored as a `ProviderDisposition` and serialized in `decision.json` and `request_audit.csv`. |
| Mandatory gates | 9 coarse capability booleans | 20 explicit, individually named gates covering PIT dates, active/inactive states, pagination semantics, exact date semantics, security-type taxonomy, OTC, warrant/right/unit/preferred exclusions, provenance, duplicates, repeatability, 2022 entitlement, and 48-month feasibility. |
| Taxonomy | `security_type_field` observed but not mapped; OTC unproven | Query `/v3/reference/tickers/types`, lock code→category mapping, treat unmapped codes as ineligible, and keep common stock (`CS`) and ETF as separate allowlist strata. |
| Provenance | `probe_version=1` hard-coded, `v1_pre_registration_commit` held the v2 SHA, `final_head` was ambiguous | Use `v1_pre_registration_commit`, `v2_pre_registration_commit`, `v3_pre_registration_commit`, `live_run_head`, `final_pr_head`, plus starting `main` SHA, strategy SHA, Alpaca v2 decision SHA, amendment SHA/status, and credential availability per provider. |
| Safe bundle | `provider_capability_matrix.csv` generated, not `capability_matrix.csv`; extra files allowed | Lock `expected_safe_artifacts` exactly in `INTRA-001B-reference-probe-v3.json`, enforce manifest equality in `report.py`, and test conformance. |
| Decision schema | Missing provenance/boundary fields | `ReferenceProbeDecision` carries all mandatory gate booleans, candidate dispositions, pagination audit, blocker list, limitations, and recommended next assignment. |

## V3 pre-registration

- **New spec:** `docs/research/specs/INTRA-001B-reference-probe-v3.json`
- **Candidate order:** Alpha Vantage `LISTING_STATUS` first, then Massive `/v3/reference/tickers`.
- **PIT dates (original):** `2022-01-31`, `2023-07-31`, `2024-05-31`, `2025-11-30`.
- **PIT dates (fallback):** `2024-01-31`, `2024-07-31`, `2025-01-31`, `2025-11-30`.
- **Fallback dataset:** `2024-01-02` through `2025-12-31`, unchanged from amendment v2.

## Implementation plan

1. Update `tradex/research/intraday_reference_probe/` models to carry the 20 gate booleans, pagination audit rows, and provider dispositions.
2. Update `MassiveReferenceClient` to follow `next_url` to terminal `null`, with repeated-cursor and simple cycle detection, `safety_max_pages` as failure-only, and per-page count/hash capture.
3. Add `fetch_ticker_types()` and a deterministic code-to-category allowlist that maps Massive codes to `common_stock`, `etf`, `preferred_stock`, `warrant`, `right`, `unit`, `otc`, `unknown`.
4. Update `_evaluate_candidate` to test each exclusion individually and require explicit evidence for OTC.
5. Update `ReferenceProbeSpec` to load v3, support fallback dates, and expose `expected_safe_artifacts`.
6. Update `run_reference_probe` to append failed-provider dispositions, preserve the candidate order audit, and evaluate original then fallback.
7. Update `report.py` to generate `provider_capability_matrix.csv`, `security_type_taxonomy.csv`, `pagination_audit.csv`, and enforce exact safe-artifact equality.
8. Update CLI to accept `--probe-spec docs/research/specs/INTRA-001B-reference-probe-v3.json`.
9. Fix `_strip_text(None)` in `tradex/config.py` (already done) and add `ALPHA_VANTAGE_API_KEY` / `MASSIVE_API_KEY` / `POLYGON_API_KEY` precedence tests.
10. Add focused tests: pagination exhaustion, repeated-cursor handling, missing credentials, 20 gate matrix, candidate-disposition preservation, safe-artifact conformance, decision provenance fields, and security-type taxonomy mapping.

## Success criteria

- V3 pre-registration commit exists before any live call.
- `INTRA-001B-reference-probe-v3.json` validates against `json.tool`.
- `INTRA-001-v1.json` SHA-256 remains `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`.
- `git diff --check` and `ruff` clean for the changed package and tests.
- All focused and full isolated tests pass.
- No live provider calls until after approval.

## Approval gate

Gary must approve this proposal before the v3 live probe runs. If approved, the next commits will be:

1. v3 pre-registration commit on `devin/intra-001b-reference-source`.
2. Live Alpha Vantage probe under current free entitlement.
3. If Alpha Vantage fails any mandatory gate, live Massive probe under current free entitlement.
4. Safe artifact bundle, `decision.json`, and `INTRA-001B-REFERENCE-SOURCE-DECISION.md` update.

If the v3 probe passes, the amendment moves to `locked_ready_for_snapshot_implementation` and the next assignment is `devin/intra-001b-intraday-snapshot` (the `INTRA-001B` data and manifest infrastructure phase per `INTRA-001-v1.json`).
