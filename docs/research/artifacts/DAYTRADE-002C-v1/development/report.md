# DAYTRADE-002B Early-to-Late Momentum Study Report — Split: DEVELOPMENT

- **Task ID:** `DAYTRADE-002B`
- **Study Name:** `DAYTRADE-002: Early-to-Late ETF Intraday Momentum`
- **Split:** `development`
- **Disposition:** **`INCONCLUSIVE`**
- **Disposition Step:** `step_2_evidence_sufficiency`
- **Disposition Reason:** sample_gate_failed (events=0, etfs=0, dates=0); data_quality_gate_failed (100.00%)
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Validation Gates

| Gate | Passed | Details |
|---|---|---|
| `baseline_uplift_gate` | **FAIL** | `{"ci_lower": null, "ci_status": "non_computable", "mean_uplift_2bps": null}` |
| `breadth_gate` | **FAIL** | `{"min_required_pct": 60.0, "pct_positive_etfs": 0.0, "per_etf_net_means": {}}` |
| `concentration_gate` | **PASS** | `{"max_allowed_pct": 15.0, "max_single_etf_pct": 0.0}` |
| `data_quality_gate` | **FAIL** | `{"excluded_rate_pct": 100.0, "excluded_ticker_sessions": 930, "max_allowed_pct": 5.0, "total_ticker_sessions": 930}` |
| `primary_net_effect_gate` | **FAIL** | `{"ci_lower": null, "ci_status": "non_computable", "cost_basis_bps_per_side": 2.0, "mean_net_return_2bps": null}` |
| `sample_gate` | **FAIL** | `{"event_count": 0, "event_session_count": 0, "min_event_session_count": 20, "min_events": 75, "min_represented_etfs": 10, "represented_etfs": 0}` |

## Core Metrics

- **Eligible Ticker-Sessions:** 0
- **Event Count:** 0
- **Represented ETFs:** 0
- **Event Session Count (Dates):** 0
- **Long Events:** 0
- **Short Events:** 0
- **Maximum ETF Concentration:** 0.00%
- **Multi-Signal Session Count:** 0 (0.00%)
- **Gross Win Rate (30m):** 0.00%
- **Mean Gross Signed Return:** 0.0
- **Mean Net Return (2 bps/side):** 0.0
- **Median Net Return (2 bps/side):** 0.0
- **Mean Baseline Net Return (2 bps):** None
- **Median Baseline Net Return (2 bps):** None
- **Mean Uplift:** None
- **Median Uplift:** None

## Statistical Inference (Session-Date Cluster Bootstrap)

- **Primary Net Return CI:** `{"point_estimate": null, "ci_lower": null, "ci_upper": null, "resamples": 2000, "seed": 20260926, "status": "non_computable", "error_reason": "no_eligible_target_dates"}`
- **Event Uplift CI:** `{"point_estimate": null, "ci_lower": null, "ci_upper": null, "resamples": 2000, "seed": 20260926, "status": "non_computable", "error_reason": "no_eligible_target_dates"}`

## Provenance

- **Provider:** `alpaca`
- **Feed:** `sip`
- **Timeframe:** `1Min`
- **Adjustment:** `split`
- **Calendar:** `XNYS`
- **Timezone:** `America/New_York`
- **Split:** `development`
- **Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
- **Evaluator Code SHA:** `774b37efe883233d0c3f2a888e37aebf0851d347`
- **Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`