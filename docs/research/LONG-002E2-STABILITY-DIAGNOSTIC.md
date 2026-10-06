# LONG-002E2: Development-Only Logistic Regime/Stability Diagnostic

**Task ID:** `LONG-002E2-LOGISTIC-STABILITY-DIAGNOSTIC-001`
**Official Run ID:** `LONG-002E2-20261006_183219`
**Correction Contract:** `LONG-002E2-CORR-001` (`docs/research/specs/LONG-002E2-CORR-001-v1.json`)
**Representative Configuration:** `LOGIT_S4_C300` (best_by_locked_LONG_002E1_ordering; C=3.0, penalty=l2, solver=lbfgs)
**Diagnostic Disposition:** `no_bounded_regime_hypothesis_supported`
**Recommended Next Action:** `close_initial_long_002e_search_preserve_unused_budget`
**Authorization:** Authorized by Gary Yang on 2026-10-06 (Research-Only / Post-Hoc Diagnostic)

---

## Executive Summary

In corrected Round 1 (`LONG-002E1-20261006_152832`), the best regularized logistic configuration (`LOGIT_S4_C300`, C=3.0) demonstrated pooled Precision@10 of 26.8109% (+2.7216 pp vs matched VAM5) and Precision@25 of 25.2420% (+4.2909 pp vs matched VAM5), but exhibited negative delta in 2020 (-1.4520 pp), failing the preregistered 3-of-3 year annual stability gate (achieving 2/3 years).

This diagnostic (LONG-002E2) investigated why the logistic family underperformed in 2020 without model refitting, hyperparameter tuning, or searching new configurations. Formal correction contract `LONG-002E2-CORR-001` corrects representative model hyperparameter metadata from erroneous C=300.0 to canonical C=3.0 (matching canonical E1 `configuration_registry.json`), preserving all empirical results without rerun because E2 evaluates frozen predictions and consumes no hyperparameter metadata. The evaluation locked two preregistered localization rules:
- **Rule A (Calendar Localization):** One calendar quarter accounts for >= 60% of 2020 negative hit loss AND other 3 quarters have clean hit delta >= 0.
- **Rule B (Market-Context Localization):** One SPY return regime accounts for >= 60% of 2020 negative hit loss AND other 2 regimes have clean hit delta >= 0.

- **Rule A Passed:** `False`
- **Rule B Passed:** `False`
- **Final Disposition:** `no_bounded_regime_hypothesis_supported`
- **Recommended Next Action:** `close_initial_long_002e_search_preserve_unused_budget`

---

## 1. Provenance and Input Verification

- **Execution Code SHA:** `bbb9b136c54cde87de143e9ea7b033e4ed21bbdb`
- **Preregistration Commit SHA:** `90f3b3daa8c6ac234da724e8ad1ce2ec629a1bc7`
- **E2 Spec SHA-256:** `cec5105883198cbd856c763cd39993fa1e2f72960fd7c4c5bb17dbfd2a0f9519`
- **E2 Correction Spec (CORR-001) SHA-256:** `4e57fb503d99bab5e02a90461eb2da6ce32825f065075c85587e8fec225c74a0`
- **E1 Input Prediction SHA-256:** `837b824ac11754a900b44c2e118872996a9cad424cab1c549be7df5b61780062` (Verified)
- **D1 Feature Table SHA-256:** `7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8` (Verified)
- **Stage C Baseline SHA-256:** `faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734` (Verified)
- **Total Development Observations:** 610,648 (730 sessions, 2018-2020)

### Exact Reproduction of E1 Metrics

| Metric | Reconstructed | Committed Target | Match Status |
|---|---|---|---|
| Top-10 Precision | 26.8109% | 26.8109% | EXACT MATCH |
| Top-10 VAM5 Precision | 24.0893% | 24.0893% | EXACT MATCH |
| Top-10 Delta | +2.7216 pp | +2.7216 pp | EXACT MATCH |
| Top-25 Precision | 25.2420% | 25.2420% | EXACT MATCH |
| Top-25 VAM5 Precision | 20.9510% | 20.9510% | EXACT MATCH |
| Top-25 Delta | +4.2909 pp | +4.2909 pp | EXACT MATCH |
| 2018 P@10 Delta | +3.9841 pp | +3.9841 pp | EXACT MATCH |
| 2019 P@10 Delta | +5.0000 pp | +5.0000 pp | EXACT MATCH |
| 2020 P@10 Delta | -1.4520 pp | -1.4520 pp | EXACT MATCH |

---

## 2. Family-Wide Annual Context

- **All 12 LOGIT configurations share 2018+ / 2019+ / 2020- pattern:** `True`
- **Interpretation:** all 12 tested E1 logistic configurations exhibited the same annual sign pattern; therefore the 2020 reversal was not unique to LOGIT_S4_C300 within the tested Round-1 logistic grid.

---

## 3. Diagnostic 1 — Annual Paired Uncertainty (21-Session Block Bootstrap)

| Year | Candidate P@10 | VAM5 P@10 | Delta | Bootstrap Median | 95% Bootstrap CI | Clean Hit Diff |
|---|---|---|---|---|---|---|
| 2018 | 21.71% | 17.73% | +3.98 pp | +4.05 pp | [+1.68 pp, +6.39 pp] | +100 hits |
| 2019 | 28.61% | 23.61% | +5.00 pp | +5.20 pp | [+1.11 pp, +8.49 pp] | +126 hits |
| 2020 | 30.68% | 32.13% | -1.45 pp | -1.50 pp | [-4.29 pp, +1.33 pp] | -31 hits |

---

## 4. Diagnostic 2 — Fixed Calendar-Quarter Decomposition

| Quarter | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | P@10 Delta | Cand Adverse | VAM5 Adverse | Top10 Overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2018Q1 | 61 | 610 | 131 | 107 | +24 | 21.48% | 17.54% | +3.93 pp | 50.8% | 51.6% | 29.7% |
| 2018Q2 | 64 | 640 | 146 | 132 | +14 | 22.81% | 20.62% | +2.19 pp | 36.6% | 37.7% | 26.6% |
| 2018Q3 | 63 | 630 | 109 | 89 | +20 | 17.30% | 14.13% | +3.17 pp | 45.7% | 49.2% | 28.9% |
| 2018Q4 | 63 | 630 | 159 | 117 | +42 | 25.24% | 18.57% | +6.67 pp | 46.7% | 55.6% | 20.6% |
| 2019Q1 | 61 | 610 | 224 | 170 | +54 | 36.72% | 27.87% | +8.85 pp | 24.6% | 29.5% | 26.2% |
| 2019Q2 | 63 | 630 | 172 | 112 | +60 | 27.30% | 17.78% | +9.52 pp | 36.0% | 46.4% | 18.7% |
| 2019Q3 | 64 | 640 | 94 | 127 | -33 | 14.69% | 19.84% | -5.16 pp | 46.4% | 48.3% | 12.2% |
| 2019Q4 | 64 | 640 | 231 | 186 | +45 | 36.09% | 29.06% | +7.03 pp | 33.0% | 38.3% | 25.6% |
| 2020Q1 | 62 | 620 | 131 | 149 | -18 | 21.13% | 24.03% | -2.90 pp | 56.8% | 58.6% | 16.0% |
| 2020Q2 | 63 | 630 | 237 | 251 | -14 | 37.62% | 39.84% | -2.22 pp | 23.8% | 33.3% | 19.5% |
| 2020Q3 | 64 | 640 | 228 | 211 | +17 | 35.62% | 32.97% | +2.66 pp | 29.1% | 41.4% | 15.5% |
| 2020Q4 | 38 | 245 | 59 | 75 | -16 | 24.08% | 30.61% | -6.53 pp | 46.1% | 51.4% | 18.8% |

---

## 5. Diagnostic 3 — Market-Context Regimes (SPY Return 20)

- **SPY Return q30 Threshold:** `-0.002398`
- **SPY Return q70 Threshold:** `0.034049`
- **Regime Date Counts:** LOWER=219, MIDDLE=292, UPPER=219

### Overall Regime Performance

| Regime | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | Delta P@10 | Cand Adverse | VAM5 Adverse | Overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LOWER | 219 | 2182 | 662 | 605 | +57 | 30.34% | 27.73% | +2.61 pp | 34.9% | 41.5% | 19.7% |
| MIDDLE | 292 | 2838 | 632 | 546 | +86 | 22.27% | 19.24% | +3.03 pp | 43.3% | 48.3% | 24.0% |
| UPPER | 219 | 2145 | 627 | 575 | +52 | 29.23% | 26.81% | +2.42 pp | 38.3% | 43.3% | 20.5% |

### 2020 Year x Regime Performance

| Regime (2020) | Dates | Selected | Cand Clean | VAM5 Clean | Hit Diff | Cand P@10 | VAM5 P@10 | Delta P@10 |
|---|---|---|---|---|---|---|---|---|
| LOWER | 60 | 592 | 199 | 204 | -5 | 33.61% | 34.46% | -0.84 pp |
| MIDDLE | 64 | 558 | 159 | 159 | +0 | 28.49% | 28.49% | +0.00 pp |
| UPPER | 103 | 985 | 297 | 323 | -26 | 30.15% | 32.79% | -2.64 pp |

---

## 6. Diagnostic 4 — Selection-Set Decomposition

| Partition | 2018 Obs (Clean %) | 2019 Obs (Clean %) | 2020 Obs (Clean %) | Overall Obs (Clean %) | Overall ECMV |
|---|---|---|---|---|---|
| OVERLAP | 663 (20.21%) | 520 (32.31%) | 367 (31.88%) | 1550 (27.03%) | 5.07 |
| LOGIT_ONLY | 1847 (22.25%) | 2000 (27.65%) | 1768 (30.43%) | 5615 (26.75%) | 5.12 |
| VAM5_ONLY | 1847 (16.84%) | 2000 (21.35%) | 1768 (32.18%) | 5615 (23.28%) | 3.71 |

---

## 7. Diagnostic 5 — Feature-Profile Drift (Percentile Profiles)

Comparison of average cross-sectional percentile rank of securities chosen by `LOGIT_ONLY` vs `VAM5_ONLY`:

| Feature | 2018 Diff (L - V) | 2019 Diff (L - V) | 2020 Diff (L - V) | Overall Diff (L - V) |
|---|---|---|---|---|
| `return_5` | -67.91 | -76.77 | -75.00 | -73.30 |
| `atr_pct_14` | +4.49 | +3.56 | +4.98 | +4.31 |
| `return_20` | -44.94 | -40.21 | -45.16 | -43.33 |
| `return_60` | -21.82 | -18.22 | -21.43 | -20.42 |
| `close_vs_sma20` | -51.33 | -57.44 | -62.30 | -56.96 |
| `close_vs_sma60` | -36.93 | -33.91 | -37.58 | -36.06 |
| `sma20_slope_5` | -27.72 | -23.79 | -33.50 | -28.14 |
| `relative_volume_20` | -6.51 | -4.95 | -13.06 | -8.02 |

- **Descriptive Observation:** The LOGIT_ONLY vs VAM5_ONLY relative-volume percentile gap was larger in 2020 (-13.06 vs -6.51 in 2018 and -4.95 in 2019); this coincided with weaker relative performance, but E2 does not establish causality.

---

## 8. Diagnostic 6 — Selection Concentration

| Year | Model | Distinct Sec | Max Count | Top-5 Share | Top-10 Share | HHI | Eff N |
|---|---|---|---|---|---|---|---|
| 2018 | LOGIT_S4_C300 | 127 | 156 | 21.5% | 35.8% | 0.022056 | 45.3 |
| 2018 | VAM5 Baseline | 247 | 66 | 11.4% | 19.8% | 0.009818 | 101.8 |
| 2019 | LOGIT_S4_C300 | 127 | 243 | 29.3% | 43.2% | 0.030384 | 32.9 |
| 2019 | VAM5 Baseline | 240 | 110 | 14.2% | 22.8% | 0.011493 | 87.0 |
| 2020 | LOGIT_S4_C300 | 120 | 120 | 22.4% | 36.9% | 0.022233 | 45.0 |
| 2020 | VAM5 Baseline | 266 | 67 | 12.1% | 20.8% | 0.009874 | 101.3 |

---

## 9. Diagnostic 7 — Raw Probability Stability

| Year | Obs | Empirical Base Rate | Brier Score | Mean Predicted Prob | Median Predicted Prob |
|---|---|---|---|---|---|
| 2018 | 211,140 | 6.25% | 0.056923 | 6.21% | 4.08% |
| 2019 | 217,101 | 6.90% | 0.061069 | 5.82% | 4.13% |
| 2020 | 182,407 | 18.20% | 0.161748 | 21.57% | 10.38% |

- **Descriptive Observation:** 2020 had a substantially higher empirical base rate (18.20%) than 2018 (6.25%) and 2019 (6.90%). E2 measured empirical distribution shifts only and does not establish specific macro causal drivers.

---

## 10. 2020 Localization Metrics & Decision Gate

- **2020 Annual Clean Hit Delta:** `-31` hits

### Rule A — Calendar Localization
- **Dominant Negative Quarter:** `2020Q1` (loss: `18` hits)
- **Quarter Negative Loss Share:** `37.50%` (Threshold: 60.0%)
- **Remaining Three Quarters Hit Delta:** `-13` hits (Threshold: >= 0)
- **Rule A Disposition:** `FAILED`

### Rule B — Market-Context Localization
- **Dominant Negative SPY Regime:** `UPPER` (loss: `26` hits)
- **Regime Negative Loss Share:** `83.87%` (Threshold: 60.0%)
- **Remaining Two Regimes Hit Delta:** `-5` hits (Threshold: >= 0)
- **Rule B Disposition:** `FAILED`

### Final Decision
- **Diagnostic Disposition:** `no_bounded_regime_hypothesis_supported`
- **Recommended Next Action:** `close_initial_long_002e_search_preserve_unused_budget`
- **Search Budget Status:** 36 consumed / 12 unused (Total: 48). Unchanged.
- **Round 2 Authorized:** `False`

---

## 11. Governance, Isolation, and Limitations

1. **Zero Provider / Network Calls:** All evaluations were executed offline against frozen TradeX artifacts.
2. **Strict Quarantines:** Validation (2021-2022), Holdout (2023-2025), and Shadow (2026+) remain unopened.
3. **Zero Model Refitting:** No model parameters, coefficients, scalers, or probability calibrations were refitted.
4. **No Production Strategy Promotion:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.
5. **Hypothesis Generation Only:** Findings from this development diagnostic cannot directly justify trading rules, market timing gates, or score modifications without independent preregistered validation.
6. **Metadata Correction (LONG-002E2-CORR-001):** Preregistered specification `LONG-002E2-v1.json` recorded representative hyperparameter `C: 300.0` due to a typographic error for ID `LOGIT_S4_C300`. Canonical E1 `configuration_registry.json` documents `C: 3.0` (penalty=l2, solver=lbfgs). Correction contract `LONG-002E2-CORR-001` formally corrects this metadata without empirical rerun because E2 evaluates frozen predictions and no calculation branched on or consumed the hyperparameter value. The original run and all 13 safe JSON artifacts are preserved as valid empirical evidence subject to corrected metadata.
