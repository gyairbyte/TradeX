# DAYTRADE-002C-CORR-002 — Correct DAYTRADE Evaluator Provider-Provenance Summary Metadata

## Executive Summary

* **Task ID:** `DAYTRADE-002C-CORR-002`
* **Title:** Correct DAYTRADE evaluator provider-provenance summary metadata for future executions
* **Classification:** Research-only evaluator metadata/correctness fix (zero production trading behavior change)
* **Date:** 2026-10-05
* **Execution Status:** Complete
* **Production Trading Behavior:** NO CHANGE
* **Trading Logic:** NO CHANGE
* **Historical Empirical Results:** NO CHANGE (byte-for-byte immutable)
* **Real-Data Execution Authorized:** NO
* **Holdout Access Authorized:** NO
* **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved

---

## 1. Historical Defect

Under task `DAYTRADE-002C-CORR-001B`, preholdout development and validation splits were executed on real Alpaca SIP 1-minute ETF bars under explicit Gary Yang authorization. The empirical executions were valid research evidence:
* Development executed exactly once (disposition: `REJECTED`, `step_3_directional_hypothesis_failure`);
* Validation executed exactly once (disposition: `INCONCLUSIVE`, `step_4_statistical_uncertainty`, primary net return 95% CI lower $\le 0$ at $-2.02$ bps);
* Preholdout dataset manifest SHA-256: `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb` (verified 100% against all 15 ETF source files);
* Runtime lineage correctly preserved provider `alpaca`, feed `sip`, timeframe `1Min`, adjustment `split`, calendar `XNYS`, timezone `America/New_York`.

However, in the emitted artifact bundles (`development/metrics.json` and `validation/metrics.json`), the metadata block:
```json
"provider_provenance_summary": {
    "provider": "alpaca",
    "feed": "sip",
    "timeframe": "1Min",
    "adjustment": "split",
    "calendar": "XNYS",
    "timezone": "America/New_York",
    "status": "synthetic_fixtures_only"
}
```
mechanically emitted `status = "synthetic_fixtures_only"`, despite the authoritative acquisition provenance status in the verified manifest being `"authorized_provider_acquisition"`.

As documented in the CORR-001B evidence wrapper (`docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/evidence-index.json`):
* **Calculation Impact:** False (zero calculation impact on returns, uplift, bootstrap, or data quality);
* **Dataset Integrity Impact:** False (exact preholdout dataset bytes were verified);
* **Disposition Impact:** False (development `REJECTED` and validation `INCONCLUSIVE` unchanged);
* **Reexecution Required:** False (no rerun permitted or scientifically justified).

---

## 2. Correct Root Cause

The historical results document `docs/research/DAYTRADE-002C-CORR-001B-RESULTS.md` originally stated that the hard-coded label string originated from:
`tradex/research/daytrade_momentum/metrics.py`

That implementation path was incorrect. There is no `tradex/research/daytrade_momentum/metrics.py` in the repository.

The actual defect was located directly in:
`tradex/research/daytrade_momentum/study.py`

In `study.py`, during metrics dictionary assembly inside `evaluate_split()`, `provider_provenance_summary` was hard-coded with literal `"status": "synthetic_fixtures_only"`. This hard-coded block was emitted identically for both synthetic test runs and canonical manifest-backed real-data evaluations.

---

## 3. Implementation Fix

The evaluator in `tradex/research/daytrade_momentum/study.py` now deterministically distinguishes between injected custom fixtures and canonical manifest-backed evaluations:

### 3.1 Synthetic / Custom Injected Evaluation
When `evaluate_split()` is called with `custom_sessions` AND `custom_reports`:
* `metrics["provider_provenance_summary"]["status"]` remains strictly `"synthetic_fixtures_only"`.
* Summary fields retain locked default assumptions: `provider = "alpaca"`, `feed = "sip"`, `timeframe = "1Min"`, `adjustment = "split"`, `calendar = "XNYS"`, `timezone = "America/New_York"`.
* Custom sessions take precedence for source classification even if a formal manifest and evaluation freeze exist on disk. This prevents synthetic test evidence from ever being misclassified as real.

### 3.2 Canonical Manifest-Backed Evaluation
When `evaluate_split()` loads data through the canonical private dataset path (`load_private_dataset`), the provenance summary is derived from the verified manifest for the target dataset partition:
* For development and validation: sourced from the verified `preholdout` manifest (`manifest.lock.json`).
* For holdout: sourced from the verified `holdout` target manifest (`manifest.lock.json`).
* The provider summary fields reflect the verified manifest:
  * `provider = manifest.provider`
  * `feed = manifest.feed`
  * `timeframe = manifest.timeframe`
  * `adjustment = manifest.adjustment`
  * `calendar = manifest.calendar`
  * `timezone = manifest.timezone`
* The `status` field is derived from `manifest.acquisition_provenance["status"]` when present and non-empty (e.g. `"authorized_provider_acquisition"`).
* If a verified formal manifest lacks a non-empty acquisition status, the evaluator falls back deterministically to `"verified_manifest_dataset"`.

### 3.3 Zero Methodology Changes
No trading or research methodology was changed:
* Zero changes to signals, thresholds, rolling window, events, directions, entry, exit, friction, baselines, bootstrap, CI, validation gates, or disposition logic.
* Locked specification SHA-256 remains: `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`.

### 3.4 Scope Boundary: Top-Level `StudyResult.provenance` Strictly Preserved
Following independent review and reconciliation under `PR #99`, this correction strictly modifies ONLY the nested evaluation output metadata:
`metrics["provider_provenance_summary"]`

The top-level `StudyResult.provenance` audit structure is deliberately and strictly UNCHANGED:
* `StudyResult.provenance["evaluator_code_sha"]` maintains its pre-existing definition (derived from `EvaluationFreezeRecord` or `HoldoutAccessProof`, falling back to `"unfrozen_synthetic"`).
* `StudyResult.provenance["manifest_sha256"]` maintains its pre-existing definition (derived from `EvaluationFreezeRecord` or `HoldoutAccessProof`).
* Top-level provenance environment keys (`provider`, `feed`, `timeframe`, `adjustment`, `calendar`, `timezone`) remain fixed to their locked specification baseline.
* Target manifest data from disk is NEVER substituted into top-level `StudyResult.provenance`.
* Any manifest loaded from disk is strictly validated via `verify_dataset_manifest(target_manifest, spec, manifest_file.parent)` prior to building `provider_provenance_summary`.

---

## 4. Historical Evidence Immutability

All historical artifacts remain strictly immutable:
* `docs/research/artifacts/DAYTRADE-002C-v1/**` is unchanged.
* `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/development/**` is unchanged.
* `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/validation/**` is unchanged.
* `docs/research/artifacts/DAYTRADE-002C-CORR-001B-v1/evidence-index.json` is unchanged.
* The historical emitted `"synthetic_fixtures_only"` string remains preserved in historical bundles as audit evidence of the frozen evaluator's output at that time.
* This fix applies strictly to future evaluator executions.

---

## 5. Governance & Invariants

* **Real Market Data Reads:** 0
* **External Provider API Calls:** 0
* **Empirical Reruns:** 0
* **Holdout Data Access:** Strictly UNAUTHORIZED (`unread_not_acquired`)
* **Production Strategy Promotion:** Ineligible (`production_promotion_eligible = false`)
* **Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved
