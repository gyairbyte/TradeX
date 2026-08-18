# LONG-002B-AMEND-002: Option 2 — Fail-closed unknown policy selection

**Amendment:** `LONG-002B-AMEND-002`
**Selection source:** Gary/ChatGPT selection from `LONG-002B-DEC-001`
**PR #51 merge commit:** `f6413a2ba66859a78c536242fa787d1cdf204eb2`
**Starting `main` SHA:** `f6413a2ba66859a78c536242fa787d1cdf204eb2`
**Decision status:** `gary_approved`
**Selected option:** `2` — Adopt an explicit fail-closed unknown policy
**Fail-closed unknown policy approved:** `true`
**LONG-002C design PR authorized:** `true`
**LONG-002C dataset construction authorized:** `false`
**Production promotion eligible:** `false`

## Authorization boundary

This amendment authorizes only a separate LONG-002C design/specification PR. It does not authorize LONG-002C dataset construction, implementation, provider calls, historical outcome analysis, model fitting, validation/holdout access, or any production change.

## Upstream locked specification hashes

| Spec | SHA-256 |
|------|---------|
| `LONG-002-v1.json` | `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5` |
| `LONG-002B-probe-v1.json` | `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98` |
| `LONG-002B-data-contract-v1.json` | `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a` |
| `LONG-002B-AMEND-001-probe-v1.json` | `38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7` |

## Decision packet reference (PR #51)

- **Markdown:** `docs/research/LONG-002B-DEC-001.md` — `6c2179ff5e73bbe655c101814fa98c66bc7c09c803e98f2afbaeda98c0b25026`
- **JSON:** `docs/research/specs/LONG-002B-DEC-001.json` — `6d750f7b1c6981db648d647883e8d3d493498eed7d36d2b282d969ea4eec1633`
- **Advisory recommendation in packet:** Option 2

## LONG-002B-AMEND-001 artifact reference (PR #50)

- **Bundle:** `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647`
- **Run ID:** `2026-08-16-222647`
- **Overall disposition:** `not_supported`
- **Manifest SHA-256:** `44b51c0d2e8c3d99d2e013633da2744b2eff0867910bd4bd2ad2d72eb375d3a6`
- **Feasibility report SHA-256:** `9f580e17dca0cf760dbdcb765d5fc2ef972120066c67eabc702d80febd03acd5`

## Locked security policy

- **Per Date Classification:** Every security classification is evaluated independently for its historical (symbol, as_of_date).
- **No Backfill:** Current or later classifications never backfill historical facts.
- **Unknown Not Common Stock:** Unknown security classification is never treated as common stock.
- **Unknown Excluded From Universe:** A row without defensible PIT classification is excluded from the eligible universe.
- **Locked Exclusions Apply:** ETFs, ETNs, closed-end funds, preferreds, warrants, rights, units, OTC securities, pre-merger SPACs/shells, and structurally incomparable securities retain their locked treatment.
- **Measure Selection Bias:** Exclusion coverage, cohort selection bias, comparability, and sample sufficiency must be measured during later authorized work.
- **Coverage Failure Inconclusive:** Coverage failure may make later research inconclusive; thresholds may not be weakened after results are observed.

## Locked earnings policy

- **Schedule Unknown When Unavailable:** When a historical PIT earnings schedule is unavailable, the schedule remains unknown.
- **No Confirmed Non Earnings:** The observation cannot be labeled a confirmed non-earnings setup.
- **No Enter Now Or Armed:** Under the ordinary policy it cannot reach Enter Now or Armed.
- **Maximum Actionable State:** Its maximum possible presentation is Waitlist or do_not_surface, with the exact presentation choice deferred to the separately approved LONG-002C design.
- **No Retrospective Proxies:** Current calendars, SEC filing timestamps, actual earnings-release dates, or later-reconstructed dates cannot retrospectively restore actionability.
- **No Feature Or Ranking Use:** Unknown earnings timing cannot become a feature, ranking input, implicit absence indicator, zero value, or post-hoc exclusion.
- **Actionability And Kpi Marked Unavailable:** Actionability and KPI reporting must mark affected observations unavailable and report known-schedule coverage separately.
- **Insufficient Coverage Inconclusive:** Insufficient known-schedule coverage makes executable-policy evaluation inconclusive.
- **No Weakening For Sample Size:** Later phases may not weaken this rule to recover sample size or improve performance.

## Governance invariants

- Option 2 is explicitly selected and Gary-approved; Options 1 and 3 are not selected or authorized.
- Prior not_supported feasibility findings from LONG-002B and LONG-002B-AMEND-001 remain unchanged.
- Security unknowns are excluded rather than treated as eligible common stock.
- Current or later security classifications may never be backfilled as historical facts.
- Earnings unknowns cannot be confirmed as non-earnings setups.
- Earnings unknowns cannot reach Enter Now or Armed under the ordinary policy.
- No retrospective earnings proxy can restore actionability.
- Unknown earnings observations are unavailable for actionability/KPI evaluation.
- Insufficient schedule coverage produces an inconclusive result rather than a relaxed gate.
- Only a LONG-002C design PR is authorized; dataset construction, provider calls, outcome analysis, and production promotion remain unauthorized.
- All referenced upstream specification hashes remain unchanged.

---

*This amendment is a versioned overlay; prior locked specifications and artifacts are referenced by hash and not modified.*
