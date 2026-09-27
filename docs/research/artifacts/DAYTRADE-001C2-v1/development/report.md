# DAYTRADE-001B Reversal Study Report — Split: DEVELOPMENT

- **Task ID:** `DAYTRADE-001B`
- **Split:** `development`
- **Disposition:** **`REJECTED`**
- **Disposition Step:** `step_3_directional_hypothesis_failure`
- **Disposition Reason:** Directional hypothesis failure: primary_mean_net_-0.000545_le_0; mean_uplift_-0.000150_le_0; ticker_breadth_6.7%_below_60.0%
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Validation Gates

| Gate | Passed | Details |
|---|---|---|
| `baseline_uplift_gate` | **FAIL** | `{"ci_lower": -0.00032522133685468965, "ci_status": "computable", "mean_uplift_2bps": -0.00015027304622491845}` |
| `breadth_gate` | **FAIL** | `{"min_required_pct": 60.0, "pct_positive_tickers": 6.666666666666667, "per_ticker_net_means": {"AAPL": 0.0005826283844501361, "AMGN": -0.0008268920346176513, "AMZN": -0.0005957511650079391, "AXP": -0.0007926419581811986, "BA": -3.527683348523685e-05, "CAT": -0.0007261984383833223, "CRM": -0.001111836538653659, "CSCO": -0.000350633022534246, "CVX": -0.00040184224153480146, "DIS": -0.0011462085343900952, "GS": -0.0010785673018133901, "HD": -0.0005178201854098635, "HON": -0.0006966428030928787, "IBM": -0.00039575985694213073, "JNJ": -0.0006884510224239718, "JPM": -0.0009684086424872789, "KO": -0.0002437295691506381, "MCD": -0.0005588288716977529, "MMM": -0.0006447343661354684, "MRK": -0.0004876845296687675, "MSFT": -0.000795005791097617, "NKE": 0.0007836037647193596, "NVDA": -0.00014189487218313972, "PG": -0.00030732117309053994, "SHW": -0.0005324127018953623, "TRV": -0.000847516768215805, "UNH": -0.000957378386742552, "V": -0.0008808615571083281, "VZ": -0.00020066660743672788, "WMT": -0.0005753418110666468}}` |
| `concentration_gate` | **PASS** | `{"max_allowed_pct": 15.0, "max_single_ticker_pct": 5.083088954056696}` |
| `data_quality_gate` | **PASS** | `{"excluded_rate_pct": 4.53551912568306, "excluded_ticker_sessions": 166, "max_allowed_pct": 5.0, "total_ticker_sessions": 3660}` |
| `primary_net_effect_gate` | **FAIL** | `{"ci_lower": -0.000717614651872239, "ci_status": "computable", "cost_basis_bps_per_side": 2.0, "mean_net_return_2bps": -0.0005451362430175138}` |
| `sample_gate` | **PASS** | `{"event_count": 2046, "min_events": 300, "min_tickers": 15, "represented_tickers": 30}` |

## Core Metrics

- **Total Eligible Minutes:** 1317083
- **Event Count:** 2046
- **Represented Tickers:** 30
- **Maximum Ticker Concentration:** 5.08%
- **Overlapping Events:** 1816 (88.76%)
- **Mean Net Return (2 bps/side):** -0.0005451362430175138
- **Median Net Return (2 bps/side):** -0.0004927579990610955
- **Mean Baseline Net Return:** -0.0003948631967925953
- **Median Baseline Net Return:** -0.0003926920652017595
- **Mean Uplift:** -0.00015027304622491845
- **Median Uplift:** -0.00013834748703907637
- **Win Rate (1m gross):** 47.31%
- **Win Rate (2m gross):** 47.36%
- **Win Rate (5m gross):** 49.44%

## Statistical Inference (Joint Cluster Bootstrap)

- **Primary Net Return CI:** `{"point_estimate": -0.0005451362430175138, "ci_lower": -0.000717614651872239, "ci_upper": -0.0003763428035189014, "resamples": 2000, "seed": 20260925, "status": "computable", "error_reason": null}`
- **Event Uplift CI:** `{"point_estimate": -0.00015027304622491845, "ci_lower": -0.00032522133685468965, "ci_upper": 1.657666444086609e-05, "resamples": 2000, "seed": 20260925, "status": "computable", "error_reason": null}`

## Provenance

- **Provider:** `alpaca`
- **Feed:** `sip`
- **Timeframe:** `1Min`
- **Adjustment:** `split`
- **Calendar:** `XNYS`
- **Timezone:** `America/New_York`
- **Split:** `development`
- **Spec SHA-256:** `0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620`
- **Evaluator Code SHA:** `1b96751c0c62043bd3cd2af0b702c7757842eb7d`
- **Manifest SHA-256:** `80bd6b0e9b89e1b8cf578625c795aeec2730f3e9e31de0a01de8075e8f165884`
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Acquisition Provenance

- **Total Symbols:** 30
- **Total Requests:** 300
- **Total HTTP Pages:** 394
- **Total HTTP Retries:** 0
- **Total HTTP Errors:** 0
- **Total Malformed Timestamps:** 0
- **Pagination Complete:** True

## Limitations

- Fixed 2026 Dow 30 snapshot applied to 2025 introduces survivorship and constituent selection limitations.
- Maximum evidence confidence is strictly capped at `limited_but_usable_evidence`.
