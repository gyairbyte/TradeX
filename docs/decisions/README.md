# TradeX Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for TradeX. Each ADR captures a significant architectural choice, the context in which it was made, and the consequences of that choice. They are intended for future contributors and AI agents working on the codebase.

## ADR lifecycle

- **Proposed**: under discussion or awaiting review; not yet binding.
- **Accepted**: approved and current.
- **Deprecated**: no longer recommended, but retained for historical context.
- **Superseded**: replaced by a newer ADR. The old ADR remains in place with a `Superseded by` link and its status updated to `Superseded`; the new ADR lists `Supersedes` links.

An ADR is immutable once **Accepted**. If the decision changes, create a new ADR, mark the old one `Superseded`, and update this index.

## Index

| ID | Title | Status | Date | Notes |
|---|---|---|---|---|
| [ADR-0000](0000-template.md) | ADR Template | — | — | Copy this template for new ADRs |
| [ADR-0001](0001-coil-definition.md) | Coil Definition and Detection | Accepted | 2026-08-01 | Pre-signal heuristic, not a trade instruction |
| [ADR-0002](0002-confluence-scoring.md) | Cross-Timeframe Confluence Scoring | Accepted | 2026-08-01 | Coverage-aware aggregation |
| [ADR-0003](0003-ohlcv-provider-contract.md) | OHLCV Provider Contract and Error Taxonomy | Accepted | 2026-08-01 | Universal columns; Schwab enforces UTC index |
| [ADR-0004](0004-market-timezone.md) | Market Timezone and Session Calendar | Accepted | 2026-08-01 | NYSE (`XNYS`) in `America/New_York` |

## Navigation

- Project tracker: [`docs/PROJECT-TRACKER.md`](../PROJECT-TRACKER.md)
- AI development workflow: [`docs/AI-DEVELOPMENT-WORKFLOW.md`](../AI-DEVELOPMENT-WORKFLOW.md)
- Research protocol: [`docs/RESEARCH-PROTOCOL.md`](../RESEARCH-PROTOCOL.md)
