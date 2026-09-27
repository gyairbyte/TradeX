# DAYTRADE-001B Reversal Study Report — Split: VALIDATION

- **Task ID:** `DAYTRADE-001B`
- **Split:** `validation`
- **Disposition:** **`INCONCLUSIVE`**
- **Disposition Step:** `step_2_evidence_sufficiency`
- **Disposition Reason:** Evidence sufficiency gate failure: split_excluded_sessions_7.83%_above_5.0%
- **Evidence Confidence Cap:** `limited_but_usable_evidence`
- **Production Promotion Eligible:** `False`

## Validation Gates

| Gate | Passed | Details |
|---|---|---|
| `baseline_uplift_gate` | **FAIL** | `{"ci_lower": null, "ci_status": "non_computable", "mean_uplift_2bps": 0.00015575372402749745}` |
| `breadth_gate` | **FAIL** | `{"min_required_pct": 60.0, "pct_positive_tickers": 26.666666666666668, "per_ticker_net_means": {"AAPL": -0.0002310966219604654, "AMGN": -0.0013251704605780046, "AMZN": -0.0005334270921591744, "AXP": -0.0004677025308828563, "BA": -0.0007391205043697204, "CAT": -0.00042163919103841037, "CRM": 0.0006467906041642757, "CSCO": 0.0001136547738226784, "CVX": -0.0005554742347900117, "DIS": -0.00040557136195112117, "GS": -0.00016414012535297877, "HD": -0.0004024248385975084, "HON": 0.00015976239304195088, "IBM": 0.0001424298151740834, "JNJ": -0.00033726977389297576, "JPM": -0.000873812667384352, "KO": -0.00048231313782818425, "MCD": -0.0010165935817280343, "MMM": -0.0010532528099457808, "MRK": 0.0006306674793915702, "MSFT": -0.0008182473328584975, "NKE": 3.011104222016364e-05, "NVDA": -9.536733300015506e-05, "PG": 0.00018401658752579246, "SHW": -7.264614259456079e-05, "TRV": -8.150470219402324e-06, "UNH": 0.0017278546227384463, "V": -0.00045756767099898503, "VZ": -6.991779751281454e-05, "WMT": -0.0009544587046421102}}` |
| `concentration_gate` | **PASS** | `{"max_allowed_pct": 15.0, "max_single_ticker_pct": 5.005561735261402}` |
| `data_quality_gate` | **FAIL** | `{"excluded_rate_pct": 7.830687830687831, "excluded_ticker_sessions": 148, "max_allowed_pct": 5.0, "total_ticker_sessions": 1890}` |
| `primary_net_effect_gate` | **FAIL** | `{"ci_lower": null, "ci_status": "non_computable", "cost_basis_bps_per_side": 2.0, "mean_net_return_2bps": -0.00024963354574038683}` |
| `sample_gate` | **PASS** | `{"event_count": 899, "min_events": 300, "min_tickers": 15, "represented_tickers": 30}` |

## Core Metrics

- **Total Eligible Minutes:** 664350
- **Event Count:** 899
- **Represented Tickers:** 30
- **Maximum Ticker Concentration:** 5.01%
- **Overlapping Events:** 749 (83.31%)
- **Mean Net Return (2 bps/side):** -0.00024963354574038683
- **Median Net Return (2 bps/side):** -0.0002658111108400058
- **Mean Baseline Net Return:** -0.0004053872697678843
- **Median Baseline Net Return:** -0.00039727874977123017
- **Mean Uplift:** 0.00015575372402749745
- **Median Uplift:** 0.00013145156667059948
- **Win Rate (1m gross):** 53.28%
- **Win Rate (2m gross):** 56.73%
- **Win Rate (5m gross):** 54.39%

## Statistical Inference (Joint Cluster Bootstrap)

- **Primary Net Return CI:** `{"point_estimate": null, "ci_lower": null, "ci_upper": null, "resamples": 2000, "seed": 20260925, "status": "non_computable", "error_reason": "replicate_202_empty_baseline_for_TRV_09:33"}`
- **Event Uplift CI:** `{"point_estimate": null, "ci_lower": null, "ci_upper": null, "resamples": 2000, "seed": 20260925, "status": "non_computable", "error_reason": "replicate_202_empty_baseline_for_TRV_09:33"}`

## Provenance

- **Provider:** `alpaca`
- **Feed:** `sip`
- **Timeframe:** `1Min`
- **Adjustment:** `split`
- **Calendar:** `XNYS`
- **Timezone:** `America/New_York`
- **Split:** `validation`
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
