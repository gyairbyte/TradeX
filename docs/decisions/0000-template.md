# ADR-0000: ADR Template

## Status

Proposed / Accepted / Deprecated / Superseded

If the status is **Superseded**, add a `Superseded by` link and keep this file as a historical record. If the status is **Deprecated**, explain why and what should be used instead.

## Recorded

YYYY-MM-DD

## Decision owners

TradeX maintainers; final product decisions by Gary Yang. Code-level ownership follows `docs/AI-DEVELOPMENT-WORKFLOW.md`. Replace `<owner>` with the specific owner only when the decision has a single, named maintainer.

## Context

What problem does this decision address? What forces are at play? Include links to the relevant code, tests, tracker items, or research artifacts.

## Decision

The exact decision made. Be specific: constants, defaults, public APIs, error handling, formulas, thresholds, and precedence rules. Do not imply profitability or authorize a production trading change unless that is the explicit, separately approved scope.

## Consequences

Positive and negative outcomes. What becomes easier or harder? What is explicitly out of scope or left unchanged? What limitations remain?

## Non-goals

What this ADR explicitly does not cover or guarantee.

## Risks and limitations

What could go wrong, what edge cases exist, and what the decision does not validate.

## Change control and supersession

This ADR is immutable once **Accepted**. Any material change requires a new ADR that supersedes this one. Changes that affect production trading behavior require separate approval per `docs/AI-DEVELOPMENT-WORKFLOW.md` and validation per `docs/RESEARCH-PROTOCOL.md`.

## Rejected alternatives

Briefly list alternatives considered and why they were rejected. This prevents future debates from restarting from scratch.

## References

- `tradex/...` source files
- `tests/...` test files
- `docs/PROJECT-TRACKER.md` items
- Research artifacts or safe-handoff bundles
- External documentation

## Revision history

| Version | Date | Change | Owner |
|---|---|---|---|
| 1.0 | YYYY-MM-DD | Initial recorded version | TradeX maintainers |
