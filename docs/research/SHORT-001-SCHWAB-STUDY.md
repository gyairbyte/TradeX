# SHORT-001 Schwab Real-Data Study Report

## 1. Decision summary

Pending. The pre-registered study is being executed with real Schwab daily OHLCV data and the locked panel/splits below. The final decision will be inserted after candidate selection and holdout gates are complete.

## 2. Research classification

Research-only, non-production. This study evaluates whether adding point-in-time market-regime (`market_rs`) or market-plus-sector-relative-strength (`market_sector_rs`) context improves the short-term scorer over the `off` baseline on a locked, real-data panel.

## 3. Original hypothesis

Filtering short-term setups by broad-market relative strength (`market_rs`) and by combined market and sector relative strength (`market_sector_rs`) will improve risk-adjusted forward returns versus ignoring context (`off`).

## 4. Pre-registration evidence

Study design was locked before any Schwab data were fetched or any split metrics viewed. The pre-registration commit contains this report and `docs/research/specs/SHORT-001-schwab-v1.json`.

## 5. Pre-registration commit SHA

To be inserted after the pre-registration commit is made.

## 6. Context-spec SHA-256

To be inserted after the pre-registration commit is made.

## 7. Locked targets and mappings

- **33 target stocks** (3 per sector):
  - Technology (`XLK`): AAPL, MSFT, NVDA
  - Communication services (`XLC`): GOOGL, META, VZ
  - Consumer discretionary (`XLY`): AMZN, HD, MCD
  - Consumer staples (`XLP`): WMT, COST, PG
  - Financials (`XLF`): JPM, BAC, GS
  - Healthcare (`XLV`): JNJ, UNH, MRK
  - Industrials (`XLI`): CAT, HON, UPS
  - Energy (`XLE`): XOM, CVX, COP
  - Utilities (`XLU`): NEE, DUK, SO
  - Materials (`XLB`): LIN, APD, NEM
  - Real estate (`XLRE`): AMT, PLD, SPG
- **Market proxy for every target:** `SPY`
- **Required sector proxies:** `SPY`, `XLK`, `XLC`, `XLY`, `XLP`, `XLF`, `XLV`, `XLI`, `XLE`, `XLU`, `XLB`, `XLRE`
- **Expected unique snapshot symbols:** 45

## 8. Dataset dates and splits

- **Snapshot window:** 2018-10-01 through 2025-12-31
- **Development split:** 2019-01-02 through 2021-12-31
- **Validation split:** 2022-01-03 through 2023-12-29
- **Holdout split:** 2024-01-02 through 2025-12-31
- Splits are chronological, non-overlapping, and the holdout split is excluded from candidate selection.

## 9. Schwab configuration and security handling

- Provider: Schwab (`--provider schwab`).
- OAuth token stored outside the repository at the configured `SCHWAB_TOKEN_PATH`.
- `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` are read from the process environment and are not committed.
- No token, API response, or raw credential is committed to the repository.
- The approved token may remain at its configured external path.

## 10. Manifest summary

To be inserted after the snapshot is complete.

## 11. Provider-provenance audit

To be inserted after the snapshot is complete.

## 12. Bar-quality audit

To be inserted after the snapshot is complete.

## 13. Corporate-action audit

To be inserted after the snapshot is complete.

## 14. Development results

To be inserted after evaluation.

## 15. Validation results

To be inserted after evaluation.

## 16. Candidate-selection result

To be inserted after evaluation.

## 17. Selected policy or lack of selection

To be inserted after evaluation.

## 18. Holdout event-study result

To be inserted after evaluation.

## 19. Holdout paired-backtest result

To be inserted after evaluation.

## 20. Every gate failure reason

To be inserted after evaluation.

## 21. Slippage sensitivity

To be inserted after evaluation.

## 22. Event retention and ticker coverage

To be inserted after evaluation.

## 23. Ticker concentration

To be inserted after evaluation.

## 24. Determinism evidence

To be inserted after determinism verification.

## 25. Survivorship and delisting limitation

The locked target panel was fixed before results and spans all 11 GICS sectors. This design prevents post-result ticker replacement but does not eliminate survivorship or delisting bias. A failed result rejects the hypothesis for this locked panel. An inconclusive result provides no production evidence. A passing result is encouraging but, by itself, insufficient for broad production promotion; a point-in-time-universe confirmation study should precede production consideration.

## 26. What the evidence supports

To be inserted after evaluation.

## 27. What the evidence does not support

To be inserted after evaluation.

## 28. Final outcome

To be inserted after evaluation.

## 29. Production boundary

No production trading behavior is modified by this study. The production `short_term.score` path continues to use the default `ShortContextPolicy.OFF`. No dashboard control, watcher, alert, confluence, ranking, or screener path loads or exposes `market_rs` or `market_sector_rs`.

## 30. Recommended next action

To be inserted after evaluation. If the study completes cleanly, the next step is `INTRA-001B` (intraday data and manifest infrastructure) provided no SHORT-001 remediation is required.

## 31. Safe artifact location

To be inserted after the artifact bundle is built.

## 32. Test and CI evidence

To be inserted after verification runs.
