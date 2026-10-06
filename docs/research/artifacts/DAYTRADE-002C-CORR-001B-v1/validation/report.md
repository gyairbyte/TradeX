# DAYTRADE-002B Early-to-Late Momentum Study Report — Split: VALIDATION

- **Task ID:** `DAYTRADE-002B`
- **Study Name:** `DAYTRADE-002: Early-to-Late ETF Intraday Momentum`
- **Split:** `validation`
- **Disposition:** **`INCONCLUSIVE`**
- **Disposition Step:** `step_4_statistical_uncertainty`
- **Disposition Reason:** primary_ci_lower_le_zero (-0.00020152034006772274)
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Validation Gates

| Gate | Passed | Details |
|---|---|---|
| `baseline_uplift_gate` | **PASS** | `{"ci_lower": 4.394056472640493e-05, "ci_status": "computable", "mean_uplift_2bps": 0.0006444268766389628}` |
| `breadth_gate` | **PASS** | `{"min_required_pct": 60.0, "pct_positive_etfs": 66.66666666666666, "per_etf_net_means": {"DIA": -0.0006306817771697463, "IWM": 0.00039257000402176606, "QQQ": 0.0010184134417423076, "SPY": 0.00036743125095686655, "XLB": -0.0002710339373067475, "XLC": 0.0004990477096208704, "XLE": 6.121217500110708e-05, "XLF": -0.0007165871062583704, "XLI": 0.00023962961339323076, "XLK": 0.0014809949205839765, "XLP": -0.00032841683855865355, "XLRE": 0.0015965725673024267, "XLU": 0.001278472441980066, "XLV": -9.43786448004632e-05, "XLY": 7.668961774068448e-07}}` |
| `concentration_gate` | **PASS** | `{"max_allowed_pct": 15.0, "max_single_etf_pct": 7.8431372549019605}` |
| `data_quality_gate` | **PASS** | `{"excluded_rate_pct": 0.0, "excluded_ticker_sessions": 0, "max_allowed_pct": 5.0, "total_ticker_sessions": 615}` |
| `primary_net_effect_gate` | **FAIL** | `{"ci_lower": -0.00020152034006772274, "ci_status": "computable", "cost_basis_bps_per_side": 2.0, "mean_net_return_2bps": 0.00034621217631573825}` |
| `sample_gate` | **PASS** | `{"event_count": 153, "event_session_count": 36, "min_event_session_count": 20, "min_events": 75, "min_represented_etfs": 10, "represented_etfs": 15}` |

## Core Metrics

- **Eligible Ticker-Sessions:** 615
- **Event Count:** 153
- **Represented ETFs:** 15
- **Event Session Count (Dates):** 36
- **Long Events:** 91
- **Short Events:** 62
- **Maximum ETF Concentration:** 7.84%
- **Multi-Signal Session Count:** 33 (91.67%)
- **Gross Win Rate (30m):** 67.97%
- **Mean Gross Signed Return:** 0.0007462121763157383
- **Mean Net Return (2 bps/side):** 0.00034621217631573825
- **Median Net Return (2 bps/side):** 0.0005002925950933882
- **Mean Baseline Net Return (2 bps):** -0.00029821470032322464
- **Median Baseline Net Return (2 bps):** -0.00037689295797005515
- **Mean Uplift:** 0.0006444268766389628
- **Median Uplift:** 0.0006583715696906746

## Statistical Inference (Session-Date Cluster Bootstrap)

- **Primary Net Return CI:** `{"point_estimate": 0.0003462121763157391, "ci_lower": -0.00020152034006772274, "ci_upper": 0.000856287977792278, "resamples": 2000, "seed": 20260926, "status": "computable", "error_reason": null}`
- **Event Uplift CI:** `{"point_estimate": 0.0006444268766389622, "ci_lower": 4.394056472640493e-05, "ci_upper": 0.001214367634257783, "resamples": 2000, "seed": 20260926, "status": "computable", "error_reason": null}`

## Provenance

- **Provider:** `alpaca`
- **Feed:** `sip`
- **Timeframe:** `1Min`
- **Adjustment:** `split`
- **Calendar:** `XNYS`
- **Timezone:** `America/New_York`
- **Split:** `validation`
- **Spec SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
- **Evaluator Code SHA:** `770a1a66382351dd63b9245c50bed0c1d92f3ca1`
- **Manifest SHA-256:** `1b0da463a5d928cce3019fcb785f014180650d824f7d04d713d4e8fd75fd8ebb`
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`