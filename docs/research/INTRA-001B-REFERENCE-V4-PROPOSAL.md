# INTRA-001B-REFERENCE-V4 Proposal — Bounded recent-horizon Massive validation

## Status

**Executed.** The V4 live probe completed and the formal disposition is
`unsupported`. See `docs/research/INTRA-001B-REFERENCE-V4.md` and the safe
artifact bundle at `docs/research/artifacts/INTRA-001B-REFERENCE-V4/2026-08-08-062051/`.
No V5 probe is begun without explicit approval.

`INTRA-001B-REFERENCE-V3` has been executed and its safe artifact bundle is now
marked **invalid as a decision-grade capability assessment**. The V3 bundle
records `live_run_head=03e61700dbf2fd072fc36bb63764dc7fa3876281` (the exact SHA
whose code performed the live provider calls) and an authoritative
disposition of `invalid`.

Two code defects were discovered in V3 live evidence:

1. **`MassiveReferenceClient._validate_next_url` did not decode the base64url
   `cursor` parameter.** Massive encodes `active`, `date`, `market`, `sort`,
   `limit`, etc. inside a single `cursor`. The V3 validator looked for those
   parameters as plaintext query values and rejected every `next_url` with
   `invalid next_url: date parameter drift`.
2. **`run_reference_probe` did not propagate top-level `*_probe_executed` and
   `*_disposition` fields from `candidate_dispositions` when no provider was
   selected.** This left `decision.json` internally inconsistent.

Both defects are fixed in this branch.

## Data-horizon decision

Gary explicitly decided that 1–2 years of point-in-time-correct reference data
may be sufficient for `INTRA-001` production consideration and that lack of
2022–2023 coverage must not block the study. Massive's current free Stocks
Basic offering advertises a rolling two-year history, so the originally
approved fallback start of `2024-01-02` is already outside the advertised window.

Therefore V4 probes a recent, entitlement-valid window instead of the original
2022–2025 dates:

- **Original V4 dataset:** `2025-08-01` through `2026-07-31` (12 months)
- **Monthly PIT snapshots:** `2025-08-31`, `2025-09-30`, `2025-10-31`,
  `2025-11-30`, `2025-12-31`, `2026-01-31`, `2026-02-28`, `2026-03-31`,
  `2026-04-30`, `2026-05-31`, `2026-06-30`, `2026-07-31`
- **Entitlement-valid two-year fallback:** `2024-09-01` through `2026-07-31`
  (23 monthly PIT snapshots)

The fallback is used only for historical-depth / entitlement limitations and
never to bypass a structural gate.

## Gate adjustments for the approved data horizon

The 22 mandatory V3 gates are retained, but two gates are explicitly
**not required** for V4 because of the data-horizon decision:

- `historical_2022_entitlement_under_current_plan`
- `feasible_for_all_48_monthly_pit_snapshots`

A new required gate is added:

- `feasible_for_all_probe_monthly_pit_snapshots` — the probe must prove it can
  construct all monthly PIT snapshots in the V4 probe window under the current
  free entitlement.

The not-required gates are still recorded in the decision matrix with
`supported=false` and documented reason, but they do not block an overall
`supported` outcome.

## V4 changes (bounded and pre-registered)

1. `MassiveReferenceClient._validate_next_url` decodes the base64url `cursor`
   before comparing `active`, `date`, and `market` to the original request,
   while preserving HTTPS / expected-host / expected-endpoint / role checks.
2. `run_reference_probe` derives top-level `alpha_vantage_*` and `massive_*`
   probe flags from `candidate_dispositions` and supports `not_required_gates`.
3. New `docs/research/specs/INTRA-001B-reference-probe-v4.json` locks the
   recent 1-year dataset, fallback dataset, candidate order, and gate contract.
4. Alpha Vantage evidence from the V3 run is reused; V4 only makes live
   Massive/Polygon calls.

No V3 spec change, no paid upgrade, no composite provider, no production or
OHLCV change.

## Pre-registration and live-call plan

1. Create a new `pre-registration: INTRA-001B-REFERENCE-V4` commit containing
   the fixes above, the V4 spec, and credential-free tests.
2. Run the V4 reference probe for the 12 monthly PIT snapshots under the current
   free Massive entitlement.
3. If the original 1-year dataset fails only for historical-depth / entitlement,
   run the approved two-year fallback (`2024-09-01` through `2026-07-31`).
4. Generate a new safe artifact bundle and `decision.json` from the V4 run.
5. If V4 outcome is `supported`, update
   `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` to
   `status=locked_ready_for_snapshot_implementation` and
   `reference_provider=massive`; otherwise document the limitation and stop
   provider probing.

## Outcome expectations

- `supported` means Massive/Polygon can serve as the locked `INTRA-001`
  reference/security-master provider under Gary's current free entitlement for
  the approved 1–2 year horizon.
- `not_supported` or any structural failure means we stop provider probing and
  proceed with an explicitly documented limitation/product decision rather than
  a V5 loop.
