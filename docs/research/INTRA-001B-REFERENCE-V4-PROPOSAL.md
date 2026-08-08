# INTRA-001B-REFERENCE-V4 Proposal — Fix Massive cursor validation and rerun

## Status

`INTRA-001B-REFERENCE-V3` executed on the approved original PIT dates
(2022-01-31, 2023-07-31, 2024-05-31, 2025-11-30). The v3 probe is **invalid
as a decision-grade capability assessment** because the pre-registered Massive
client rejected every provider-supplied `next_url` as a security violation,
which caused the probe to conclude Massive pagination failed. The rejected
`next_url`s are in fact legitimate cursor-based pagination URLs returned by
the Massive `/v3/reference/tickers` endpoint.

## Defect discovered in V3 live evidence

1. **Cursor validation bug in `tradex/research/intraday_reference_probe/massive.py`**
   - Massive encodes all query parameters (`active`, `date`, `market`, `sort`,
     `limit`, etc.) inside a single base64url `cursor` parameter.
   - The v3 validator required those parameters to appear as plaintext query
     parameters on the `next_url` and therefore raised `date parameter drift`
     for every paginated request.
   - Evidence: the safe artifact bundle for the V3 run contains eight
     observations, each with `error = "invalid next_url: date parameter drift"`,
     and `pagination_exhausted_to_terminal = false`.

2. **Disposition reporting bug in `tradex/research/intraday_reference_probe/probe.py`**
   - When no provider is selected, the final `ReferenceProbeDecision` sets
     `alpha_vantage_probe_executed`, `massive_probe_executed`, and the
     corresponding `*_disposition` fields from the candidate dispositions list,
     but the current V3 code leaves the top-level `*_probe_executed` booleans
     as `false` and `*_disposition` strings as `"not_attempted"` even though
     the `candidate_dispositions` list is correct.
   - This is a provenance/metadata defect, not a data-contract defect, but it
     makes the JSON decision inconsistent.

## Bounded V4 changes (only these two code fixes)

1. Update `MassiveReferenceClient._validate_next_url` to:
   - Decode the base64url `cursor` parameter when present.
   - Compare the decoded `active`, `date`, and `market` values to the original
     `base_params`.
   - Preserve the existing HTTPS / expected-host / expected-endpoint / role
     checks.
   - Continue to re-attach `apiKey` via `_authenticated_next_url`.

2. Update `run_reference_probe` (no-provider-selected path) to derive the
   top-level `alpha_vantage_probe_executed`, `massive_probe_executed`,
   `alpha_vantage_disposition`, and `massive_disposition` fields from the
   `candidate_dispositions` list instead of leaving them at defaults.

No V3 spec change, no provider order change, no dataset change, no paid
upgrade, no composite provider, no production change, no OHLCV change.

## V4 pre-registration and live-call plan

1. Create a new `pre-registration: INTRA-001B-REFERENCE-V4` commit that
   contains only the two fixes above plus any V4-safe tests.
2. Re-run the reference probe under the same original PIT dates with the same
   Alpha Vantage + Massive candidate order.
3. Alpha Vantage evidence from the V3 run may be reused because the V3 call
   completed; if a fresh Alpha Vantage run is required, it will respect the
   free-tier 25-call daily limit and 5-call-per-minute rate limit.
4. Generate a new safe artifact bundle and `decision.json` from the V4 run.
5. If V4 outcome is `supported`, update
   `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` to
   `status=locked_ready_for_snapshot_implementation` and
   `reference_provider=<selected>`; otherwise keep the amendment pending.

## Fallback discipline

The approved two-year fallback (2024-01-02 through 2025-12-31) remains locked
and will be used only if the V4 Massive probe cannot reach 2022 or 2023 under
the current free entitlement. It will not be used to bypass any structural gate.
