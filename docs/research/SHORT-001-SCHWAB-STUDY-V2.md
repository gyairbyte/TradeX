# SHORT-001 Schwab Real-Data Study — v2 Rerun

**Status:** Pre-registered and locked. Real-data snapshot and evaluation pending.

This document will contain the outcome of the `short-001-hard-invalid-row-exclusion-v2` ingestion rerun against the locked `SHORT-001-schwab-v1.json` context specification. The ingestion policy does not repair, clamp, interpolate, or infer any OHLCV values; it only drops rows that violate the hard invariants and records deterministic audit evidence.

- Context spec: `docs/research/specs/SHORT-001-schwab-v1.json`
- Ingestion spec: `docs/research/specs/SHORT-001-ingestion-v2.json`
- Policy ID: `short-001-hard-invalid-row-exclusion-v2`
- Snapshot window: 2018-10-01 to 2025-12-31
- Universe: 45 symbols (33 targets + SPY + 11 sector ETFs)

Results will be populated after the snapshot and evaluation complete.
