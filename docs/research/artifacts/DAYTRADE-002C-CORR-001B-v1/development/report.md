# DAYTRADE-002B Early-to-Late Momentum Study Report — Split: DEVELOPMENT

- **Task ID:** `DAYTRADE-002B`
- **Study Name:** `DAYTRADE-002: Early-to-Late ETF Intraday Momentum`
- **Split:** `development`
- **Disposition:** **`REJECTED`**
- **Disposition Step:** `step_3_directional_hypothesis_failure`
- **Disposition Reason:** mean_net_return_le_zero (-9.471154340871249e-05); breadth_gate_failed (53.33% < 60.0%)
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Validation Gates

| Gate | Passed | Details |
|---|---|---|
| `baseline_uplift_gate` | **FAIL** | `{"ci_lower": -0.0003345382119786687, "ci_status": "computable", "mean_uplift_2bps": 0.0003848131174872465}` |
| `breadth_gate` | **FAIL** | `{"min_required_pct": 60.0, "pct_positive_etfs": 53.333333333333336, "per_etf_net_means": {"DIA": -4.908262743683104e-05, "IWM": 0.0005579925872198098, "QQQ": 0.0003170501881833268, "SPY": 2.2748998700753576e-05, "XLB": 0.00021167982337329003, "XLC": -0.0009590707488365604, "XLE": 0.0002395201205783533, "XLF": -0.0001705757628828123, "XLI": -0.0003639796785246422, "XLK": 8.337428255005814e-05, "XLP": -0.00014461199595291812, "XLRE": -0.00014046188672137993, "XLU": 0.00013791388662660631, "XLV": 0.00013038089532752377, "XLY": -0.0011084012559675245}}` |
| `concentration_gate` | **PASS** | `{"max_allowed_pct": 15.0, "max_single_etf_pct": 7.766990291262135}` |
| `data_quality_gate` | **PASS** | `{"excluded_rate_pct": 0.0, "excluded_ticker_sessions": 0, "max_allowed_pct": 5.0, "total_ticker_sessions": 930}` |
| `primary_net_effect_gate` | **FAIL** | `{"ci_lower": -0.0007563420747303547, "ci_status": "computable", "cost_basis_bps_per_side": 2.0, "mean_net_return_2bps": -9.471154340871249e-05}` |
| `sample_gate` | **PASS** | `{"event_count": 206, "event_session_count": 47, "min_event_session_count": 20, "min_events": 75, "min_represented_etfs": 10, "represented_etfs": 15}` |

## Core Metrics

- **Eligible Ticker-Sessions:** 930
- **Event Count:** 206
- **Represented ETFs:** 15
- **Event Session Count (Dates):** 47
- **Long Events:** 111
- **Short Events:** 95
- **Maximum ETF Concentration:** 7.77%
- **Multi-Signal Session Count:** 36 (76.60%)
- **Gross Win Rate (30m):** 56.80%
- **Mean Gross Signed Return:** 0.00030528845659128753
- **Mean Net Return (2 bps/side):** -9.471154340871249e-05
- **Median Net Return (2 bps/side):** -9.029345898847404e-06
- **Mean Baseline Net Return (2 bps):** -0.00047952466089595916
- **Median Baseline Net Return (2 bps):** -0.0003969678302138949
- **Mean Uplift:** 0.0003848131174872465
- **Median Uplift:** 0.00044175945569599234

## Statistical Inference (Session-Date Cluster Bootstrap)

- **Primary Net Return CI:** `{"point_estimate": -9.4711543408713e-05, "ci_lower": -0.0007563420747303547, "ci_upper": 0.0005547494073994659, "resamples": 2000, "seed": 20260926, "status": "computable", "error_reason": null}`
- **Event Uplift CI:** `{"point_estimate": 0.00038481311748724684, "ci_lower": -0.0003345382119786687, "ci_upper": 0.0010563213939105173, "resamples": 2000, "seed": 20260926, "status": "computable", "error_reason": null}`

## Provenance

- **Provider:** `alpaca`
- **Feed:** `sip`
- **Timeframe:** `1Min`
- **Adjustment:** `split`
- **Calendar:** `XNYS`
- **Timezone:** `America/New_York`
- **Split:** `development`
- **Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
- **Evaluator Code SHA:** `770a1a66382351dd63b9245c50bed0c1d92f3ca1`
- **Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`