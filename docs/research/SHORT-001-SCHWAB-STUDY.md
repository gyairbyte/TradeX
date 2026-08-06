# SHORT-001 Schwab Real-Data Study Report

## 1. Decision summary

The locked SHORT-001 real-data v1 study is **invalid** (Outcome E). The Schwab daily OHLCV data for the pre-registered panel fail the repository's point-in-time bar-quality invariants, preventing both the snapshot and any downstream evaluation from running. No candidate policy was selected, no holdout gate was reached, and no production promotion is warranted or implemented. This is a v1 attempt failure; a narrowly scoped data-ingestion remediation followed by a fresh locked rerun can still be attempted.

## 2. Research classification

Research-only, non-production. The study was designed to evaluate whether point-in-time `market_rs` or `market_sector_rs` context filtering improves short-term forward returns versus the `off` baseline on a locked real-data panel. The study did not proceed past data ingestion.

## 3. Original hypothesis

Filtering short-term setups by broad-market relative strength (`market_rs`) or by combined market-and-sector relative strength (`market_sector_rs`) improves risk-adjusted forward returns versus ignoring context (`off`).

## 4. Pre-registration evidence

The study design, locked target/proxy mappings, dates, splits, and context specification were committed before any Schwab data were fetched or any split metrics viewed. The pre-registration commit contains this report and `docs/research/specs/SHORT-001-schwab-v1.json`.

## 5. Pre-registration commit SHA

`4d696729a10288bb239988c4255f3d9cf3677191`

## 6. Context-spec SHA-256

`5ae8a420be97d3665c48ed82401cb4d9b0f0d71610898b7036f72453755acb45`

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
- **Expected unique snapshot symbols:** 45; **observed unique symbols fetched:** 45

## 8. Dataset dates and splits

- **Snapshot window:** 2018-10-01 through 2025-12-31
- **Development split:** 2019-01-02 through 2021-12-31
- **Validation split:** 2022-01-03 through 2023-12-29
- **Holdout split:** 2024-01-02 through 2025-12-31
- Splits are chronological, non-overlapping, and the holdout split was excluded from candidate selection.

## 9. Schwab configuration and security handling

- Provider: Schwab (`--provider schwab`).
- OAuth token stored outside the repository at `/home/ubuntu/.tradex_schwab_token.json`.
- `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` were read from the process environment and are not committed.
- No token, API response, or raw credential was committed to the repository.

## 10. Manifest summary

No manifest was generated. The snapshot command failed on the first ticker that violated the repository's bar-quality invariants (`MCD` at `2023-01-24`). The temporary snapshot directory was removed by the atomic-publish logic. Audit files captured outside the repository record the fetch outcomes for all 45 symbols.

## 11. Provider-provenance audit

- All 45 requested symbols returned data from the Schwab API.
- `26` symbols passed `canonicalize_bars` without error.
- `19` symbols failed `canonicalize_bars` with OHLC invariant violations, producing `23` malformed rows out of approximately `82,035` fetched rows (`45 × 1,823`), or about `0.028%` of rows.
- Every successful fetch used `provider=schwab`; no fallback provider was requested or used.

## 12. Bar-quality audit

For every symbol the repository's `canonicalize_bars` validated: nonpositive prices, negative volume, `high < low`, `high < open`/`close`, and `low > open`/`close`.

**Result:** `23` candles across `19` symbols violate these invariants out of approximately `82,035` fetched daily rows (`0.028%`). The `canonicalize_bars` ingestion gate rejects an entire symbol after the first malformed row, so the snapshot stopped on `MCD` before a manifest could be written.

Bad candles:

| ticker | datetime | open | high | low | close | volume |
| --- | --- | --- | --- | --- | --- | --- |
| MCD | 2023-01-24 06:00:00+00:00 | 236.4200 | 270.1600 | 236.7700 | 269.5600 | 2517081 |
| WMT | 2023-06-05 05:00:00+00:00 | 49.7900 | 50.4167 | 49.8800 | 49.9333 | 15553173 |
| JPM | 2023-06-05 05:00:00+00:00 | 140.1100 | 139.3100 | 138.1300 | 139.0900 | 8511902 |
| BAC | 2023-06-05 05:00:00+00:00 | 28.8200 | 28.7100 | 28.3000 | 28.5400 | 34757752 |
| JNJ | 2023-06-05 05:00:00+00:00 | 156.7500 | 158.6400 | 156.9700 | 158.3200 | 6430453 |
| CAT | 2023-06-05 05:00:00+00:00 | 226.9900 | 226.2800 | 220.7500 | 222.4700 | 3438443 |
| HON | 2018-11-14 06:00:00+00:00 | 140.0529 | 140.5616 | 138.6961 | 138.2251 | 2827278 |
| HON | 2019-05-22 05:00:00+00:00 | 159.6687 | 160.6250 | 159.2259 | 158.7454 | 2251462 |
| HON | 2019-08-14 05:00:00+00:00 | 156.4277 | 157.1437 | 154.4962 | 153.7802 | 2457342 |
| HON | 2020-02-26 06:00:00+00:00 | 158.8396 | 162.1277 | 157.1249 | 156.6632 | 3412306 |
| UPS | 2023-06-05 05:00:00+00:00 | 169.9500 | 169.1100 | 167.6150 | 167.8500 | 2314285 |
| XOM | 2023-06-05 05:00:00+00:00 | 107.1900 | 107.0250 | 105.0900 | 105.2900 | 10628001 |
| CVX | 2023-06-05 05:00:00+00:00 | 158.4500 | 157.8900 | 155.2400 | 155.5100 | 6443842 |
| COP | 2023-06-05 05:00:00+00:00 | 103.0500 | 102.3700 | 99.7700 | 100.8700 | 5154045 |
| SO | 2023-01-24 06:00:00+00:00 | 74.9300 | 71.1800 | 58.8500 | 66.7000 | 3444199 |
| APD | 2020-10-21 05:00:00+00:00 | 294.0400 | 298.0300 | 293.2700 | 293.2600 | 429763 |
| PLD | 2023-01-24 06:00:00+00:00 | 110.0000 | 126.9900 | 115.5000 | 126.4000 | 2142754 |
| XLB | 2018-11-15 06:00:00+00:00 | 26.8850 | 27.4725 | 26.9550 | 27.3450 | 17793246 |
| XLC | 2023-06-05 05:00:00+00:00 | 62.9200 | 63.8800 | 63.0800 | 63.3200 | 7260693 |
| XLE | 2018-11-15 06:00:00+00:00 | 30.7138 | 31.4463 | 30.9288 | 31.4038 | 31203130 |
| XLE | 2023-06-05 05:00:00+00:00 | 40.5325 | 40.3075 | 39.6150 | 39.6850 | 37826192 |
| XLF | 2023-06-05 05:00:00+00:00 | 32.8400 | 32.7500 | 32.4800 | 32.6300 | 50531444 |
| XLI | 2023-06-05 05:00:00+00:00 | 101.1500 | 100.9200 | 100.1100 | 100.2400 | 9655636 |

## 13. Corporate-action audit

Close-to-close absolute returns were computed for every target and proxy. No absolute daily return exceeded 35%, so no extreme single-day genuine market moves were flagged. The malformed rows cluster around a small number of dates. The likely causes are classified as follows:

- **Confirmed corporate action / suspected provider adjustment artifact:** `HON` on 2018-11-14 falls near the Garrett/Resideo spin-off (October 2018). The additional `HON` dates in 2019-2020 are suspected residual provider adjustment artifacts, not independently confirmed corporate actions.
- **Suspected provider adjustment-basis artifact:** `XLB` and `XLE` on 2018-11-15, `APD` on 2020-10-21, and the `XLE` second occurrence on 2023-06-05 appear on or near dates where funds/constituents were reconstituted or adjusted, but no specific corporate action was verified for every affected symbol.
- **Likely provider-wide historical-adjustment anomaly:** The 2023-06-05 cluster (`WMT`, `JPM`, `BAC`, `JNJ`, `CAT`, `UPS`, `XOM`, `CVX`, `COP`, `XLC`, `XLF`, `XLI`) and the 2023-01-24 cluster (`MCD`, `SO`, `PLD`) span unrelated stocks and sector ETFs. The simultaneous appearance of impossible OHLC relationships across many unrelated tickers is most consistent with a provider-side historical-adjustment or dividend/split-basis inconsistency, not independently confirmed corporate actions for every symbol.
- **Unexplained provider anomaly:** Individual rows that do not clearly map to a known public event are labeled unexplained pending further audit.

These are not isolated random errors. Using the rows unchanged would violate the OHLC invariants and could distort indicators, forward-return calculations, and backtests.

## 14. Development results

Not produced. The study halted at data ingestion.

## 15. Validation results

Not produced. The study halted at data ingestion.

## 16. Candidate-selection result

No candidate was selected. Candidate selection requires clean development/validation event data, which could not be generated.

## 17. Selected policy or lack of selection

No policy selected.

## 18. Holdout event-study result

Not evaluated.

## 19. Holdout paired-backtest result

Not evaluated.

## 20. Every gate failure reason

- Snapshot/ingestion gate: `canonicalize_bars` rejected the Schwab daily OHLCV because the `open`, `high`, `low`, and `close` values violated hard OHLC invariants (e.g., `low > open` or `high < open`) on 23 rows across 19 symbols. The cause is unconfirmed, but the date clustering suggests provider-side historical-adjustment or split/dividend-basis inconsistencies rather than genuine market moves.
- Without a clean snapshot, the candidate-selection, event-study, and paired-backtest gates cannot be reached.
- The predefined holdout event-study gate criteria and paired-backtest gate criteria were not modified or bypassed.

## 21. Slippage sensitivity

Not evaluated because no clean event/backtest data were produced.

## 22. Event retention and ticker coverage

Not evaluated because no clean event/backtest data were produced.

## 23. Ticker concentration

Not evaluated because no clean event/backtest data were produced.

## 24. Determinism evidence

The evaluation step was not executed, so deterministic-output comparison could not be performed. The pre-registration spec and report are deterministic and locked by SHA-256. The audit script is deterministic (same inputs produce the same `fetch_status.csv` and `bad_candles.csv` for the same Schwab response).

## 25. Survivorship and delisting limitation

The locked target panel was fixed before results and spans all 11 GICS sectors. This design prevents post-result ticker replacement but does not eliminate survivorship or delisting bias. A failed result rejects the hypothesis for this locked panel. An inconclusive result provides no production evidence. A passing result is encouraging but, by itself, insufficient for broad production promotion; a point-in-time-universe confirmation study should precede production consideration.

## 26. What the evidence supports

- Schwab OAuth credentials and the `schwab-py` client can authenticate and return daily price history for all 45 requested symbols.
- The repository's `canonicalize_bars` correctly rejects OHLC rows that violate elementary market invariants.
- The Schwab daily-history endpoint used by `tradex/data/history.py` returned `23` hard-invalid rows out of `82,035` fetched rows for the locked panel. The date clustering suggests provider-side historical-adjustment or split/dividend-basis inconsistencies. A separate, approved data-ingestion remediation assignment is needed before the locked study can be rerun.

## 27. What the evidence does not support

- Any conclusion that `market_rs` or `market_sector_rs` improves or harms short-term forward returns.
- Any production promotion or default change for `ShortContextPolicy`.

## 28. Final outcome

**Outcome E — Methodology or data invalid.**

Conclusion: Invalid study.
Production promotion eligible: false.

Reason: Real Schwab daily OHLCV data for the locked panel contain impossible OHLC relationships on `23` candles across `19` symbols (`0.028%` of approximately `82,035` fetched rows), most concentrated around dates that suggest provider-side historical-adjustment or split/dividend-basis inconsistencies. The single confirmed corporate-action link is `HON` near its 2018 spin-offs; the broad 2023-06-05 and 2023-01-24 clusters are unexplained provider-wide anomalies. Using these data unchanged would distort indicators, forward-return calculations, and executable backtests. The pre-registered methodology was not changed; this v1 data source does not satisfy the bar-quality requirements of the existing pipeline. This is an invalid v1 attempt, not a reason to abandon SHORT-001.

## 29. Production boundary

No production trading behavior is modified. The production `short_term.score` path continues to use the default `ShortContextPolicy.OFF`. No dashboard control, watcher, alert, confluence, ranking, or screener path loads or exposes `market_rs` or `market_sector_rs`.

## 30. Recommended next action

- Open a separate, approved research-only data-ingestion remediation PR before reattempting the locked SHORT-001 real-data study. The remediation must reuse the existing PATTERN-001 precedent for malformed OHLCV rows:
  1. Detect rows using only the hard OHLCV invariants already enforced by `canonicalize_bars`.
  2. **Drop the malformed row; never alter, clamp, interpolate, or infer its OHLC values.**
  3. Preserve every original offending row in a separate audit artifact with ticker, timestamp, original values, and failure reason.
  4. Record pre-clean and post-clean row counts and hashes in the manifest/data-quality outputs.
  5. Keep the complete locked 45-symbol panel; do not replace or silently omit symbols.
  6. Treat removed rows as missing observations and rerun all existing coverage, warmup, event-count, retention, ticker-breadth, and holdout requirements unchanged.
  7. Fail the rerun if cleaning leaves a symbol without sufficient usable data, materially compromises a split, or breaches a predefined missing-row threshold.
  8. Commit and lock the remediation policy before running any development, validation, candidate-selection, or holdout evaluation.
  9. Keep all target symbols, dates, splits, policies, thresholds, costs, horizons, and promotion gates unchanged.
- Do not promote any `ShortContextPolicy` until a locked, clean, real-data study passes both holdout gates.
- `INTRA-001B` (intraday data and manifest infrastructure) should not resume until the SHORT-001 data-quality issue is resolved.

## 31. Safe artifact location

Safe audit artifacts are committed under `docs/research/artifacts/SHORT-001/2026-08-01-5ae8a420/` and are the evidence bundle for PR #38. Raw Schwab OHLCV CSVs, the OAuth token, and row-level provider-derived output are excluded.

## 32. Test and CI evidence

No source, test, gate, or production code was changed. Verification results:
- `git diff --check` clean
- `uv run ruff check tests scripts` clean
- `uv run python -m json.tool docs/research/specs/SHORT-001-schwab-v1.json` valid
- `uv run pytest tests/data tests/market tests/backtest tests/research/short_context tests/research/score_validation -q` — 351 passed
- Full isolated suite with temporary `HOME` and redirected persistence paths — 1229 passed, 5 pre-existing `datetime.utcnow()` deprecation warnings
- `uv run python -m tradex.research.short_context --help`, `snapshot --help`, and `evaluate --help` work offline
- Real `~/.tradex` db files (alerts.db, earnings_cache.db, fingerprints.db, signals.db, watchlists.db) were not modified by tests
