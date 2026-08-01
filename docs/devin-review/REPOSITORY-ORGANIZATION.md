# TradeX Repository Organization Review

## Current repository tree

```text
TradeX/
├── .env.example
├── .gitattributes
├── .gitignore
├── CLAUDE.md
├── README.md
├── SETUP.md
├── launchers/
│   ├── macos/TradeX.app/
│   ├── windows/TradeX.{bat,ps1,ico}
│   └── make_icon.py
├── pyproject.toml
├── scripts/
│   └── schwab_oauth.py
└── tradex/
    ├── __init__.py
    ├── alerts/
    │   └── notifier.py
    ├── data/
    │   └── fetcher.py
    ├── earnings/
    │   └── calendar.py
    ├── options/
    │   └── flow.py
    ├── patterns/
    │   ├── config.py
    │   ├── fingerprint.py
    │   ├── matcher.py
    │   └── miner.py
    ├── premarket/
    │   └── gap_scanner.py
    ├── screener/
    │   └── engine.py
    ├── signals/
    │   ├── indicators.py
    │   ├── intraday.py
    │   ├── long_term.py
    │   ├── short_term.py
    │   └── weights.py
    ├── tracker/
    │   ├── analyzer.py
    │   ├── confluence.py
    │   ├── outcome_tracker.py
    │   ├── store.py
    │   └── watcher.py
    ├── ui/
    │   └── dashboard.py          # 1,721 lines
    ├── watchlists/
    │   ├── presets.py
    │   ├── refresh.py
    │   └── store.py
```

There is no `research/` or `docs/decisions/` directory. This audit introduces `tests/` with an initial characterization suite.

## Recommended target structure

```text
TradeX/
├── .env.example
├── .gitattributes
├── .gitignore
├── pyproject.toml
├── README.md
├── SETUP.md
├── docs/
│   ├── README.md                 # Documentation index
│   ├── decisions/                # Architectural Decision Records
│   └── devin-review/             # This audit
├── launchers/
├── research/
│   ├── README.md
│   ├── hypotheses/
│   ├── experiments/
│   ├── notebooks/
│   └── results/
├── scripts/
│   └── schwab_oauth.py
├── tests/
│   ├── conftest.py
│   ├── data/
│   ├── signals/
│   ├── screener/
│   ├── tracker/
│   ├── patterns/
│   ├── options/
│   ├── alerts/
│   ├── watchlists/
│   ├── ui/
│   ├── integration/
│   └── fixtures/
└── tradex/
    ├── __init__.py
    ├── config.py                 # Centralized, typed settings
    ├── alerts/
    │   ├── notifier.py           # Delivery only
    │   └── policy.py             # Cooldown / dedup / state (new)
    ├── backtest/                 # New (validation harness)
    ├── data/
    │   ├── fetcher.py            # Provider dispatch
    │   └── providers/            # One module per provider adapter (new)
    ├── earnings/
    ├── market/                   # New: market hours, timezone, context
    │   ├── hours.py
    │   └── context.py
    ├── options/
    │   ├── flow.py               # Public API
    │   ├── unusual_whales.py     # Provider adapter
    │   ├── tradier.py            # Provider adapter
    │   └── yfinance_chain.py     # Provider adapter
    ├── patterns/
    ├── premarket/
    ├── screener/
    ├── signals/
    │   ├── indicators.py
    │   ├── intraday.py
    │   ├── short_term.py
    │   ├── long_term.py
    │   └── weights.py            # Values only
    ├── tracker/
    ├── ui/
    │   ├── dashboard.py          # Router only
    │   ├── tabs/                 # One file per tab
    │   ├── components/           # Reusable widgets
    │   └── signal_config.py      # COMPONENT_LABELS moved here
    └── watchlists/
```

## Module responsibility map

| Module | What it owns | What it does not own | Depends on | Should never depend on |
|---|---|---|---|---|
| `tradex.config` | Typed settings, env vars, defaults | Secret values themselves | `pydantic` or `python-dotenv` | Streamlit, trading logic |
| `tradex.data.*` | Fetching and normalizing market data | Indicator/ signal computation | `config` (for keys) | `ui`, `tracker` |
| `tradex.signals.*` | Computing indicators and per-timeframe scores | Scheduling, persistence, alerting | `data`, `ta`, `pandas` | `streamlit`, `alerts` |
| `tradex.screener.engine` | Running a scorer over a watchlist | Storing results, sending alerts | `data`, `signals`, `earnings` | `ui`, `alerts` |
| `tradex.tracker.store` | Recording observations and scan metadata | Trading decisions | SQLite | `ui` |
| `tradex.tracker.analyzer` | Reading history, detecting coils | Writing results, scheduling | `store` | `fetcher`, `ui` |
| `tradex.tracker.outcome_tracker` | Fetching post-signal prices | Interpreting edge | `store`, `yf` | `ui` |
| `tradex.tracker.watcher` | Scheduling and orchestration | Computing indicators | `engine`, `store`, `alerts` | `streamlit` |
| `tradex.alerts.notifier` | Sending messages via Discord/email | Deciding when to alert | `config`, `requests`, `smtplib` | `tracker` logic |
| `tradex.alerts.policy` | Cooldown, dedup, threshold policy | Message delivery | `tracker.store` or new `alert_state` | `notifier` internals |
| `tradex.ui.*` | Rendering controls and charts | Trading logic, persistence | All backend modules (at UI layer) | Should not be imported by backend |
| `tradex.backtest.*` | Point-in-time backtests | Live execution | `data`, `signals`, `tracker` | `ui` |
| `tradex.research.*` | Experiments and notebooks | Production logic | Anything read-only | Should not be imported by production code |

## Files recommended for movement

| File / Object | Current location | Recommended location | Why move |
|---|---|---|---|
| `COMPONENT_LABELS` | `tradex/signals/weights.py` | `tradex/ui/signal_config.py` | UI metadata should not live in signal logic. |
| Per-tab UI logic | `tradex/ui/dashboard.py` | `tradex/ui/tabs/{scanner,coil,confluence,pattern,premarket,options,alerts,journal,weights,help}.py` | Dashboard is too large and mixes unrelated concerns. |
| Provider-specific options code | `tradex/options/flow.py` | `tradex/options/{unusual_whales,tradier,yfinance_chain}.py` | Multiple providers in one file makes testing and error handling hard. |
| Provider-specific data code | `tradex/data/fetcher.py` | `tradex/data/providers/{yahoo,alpaca,ibkr,schwab}.py` | Each provider can be tested and mocked in isolation. |
| Market-hours and timezone logic | (missing) | `tradex/market/hours.py` | Centralize time handling instead of scattering it across watcher and scanner. |
| Alert cooldown/dedup state | (missing) | `tradex/alerts/policy.py` | Separate the decision to alert from the delivery of the alert. |
| VWAP / anchored VWAP | (missing) | `tradex/signals/indicators.py` | Needed for any serious intraday redesign. |
| Schwab OAuth script | `scripts/schwab_oauth.py` | Keep, but reference from `SETUP.md` | It is a one-time setup script; location is fine. |

## Files recommended for removal

| File / Object | Reason | Replacement |
|---|---|---|
| None immediately | The existing modules have salvageable logic. | N/A |

No files should be deleted in the initial audit PR. Future PRs may remove or quarantine low-value features after validation:
- `tradex/options/flow.py` as a default feature (keep as optional provider adapter).
- `tradex/patterns/*` from the main dashboard (move to `research/` if not validated).

## Documentation hierarchy

| Topic | Canonical source | Other docs link to it |
|---|---|---|
| User-facing overview | `README.md` | `SETUP.md`, in-app Help |
| Installation and setup | `SETUP.md` | `README.md` |
| Architecture | `docs/devin-review/ARCHITECTURE-REVIEW.md` | `CLAUDE.md` |
| Trading feature definitions | `docs/devin-review/TRADING-FEATURE-REVIEW.md` | README, in-app Help |
| Data-provider behavior | `docs/decisions/0001-data-provider-contract.md` (proposed) | `data/fetcher.py`, README |
| Database schema | `docs/decisions/0002-database-schema.md` (proposed) | `tracker/store.py` |
| Testing instructions | `tests/README.md` (proposed) | `SETUP.md` |
| Development workflow | `docs/devin-review/DEVELOPMENT-WORKFLOW.md` | PR template, `CLAUDE.md` |
| Configuration reference | `.env.example` + `docs/decisions/0003-configuration.md` | `SETUP.md` |
| Known limitations | `docs/devin-review/EXECUTIVE-SUMMARY.md` | README |
| Research hypotheses & results | `research/README.md` and per-experiment READMEs | `VALIDATION-PLAN.md` |
| Roadmap | `docs/devin-review/RECOMMENDED-ROADMAP.md` | `PROJECT-TRACKER.md` |
| ADRs | `docs/decisions/*.md` | `ARCHITECTURE-REVIEW.md` |

## Testing hierarchy

```text
tests/
├── conftest.py                # Shared fixtures, temp DBs, env isolation
├── data/
│   ├── test_fetcher.py        # Provider dispatch and normalization
│   └── test_provider_contracts.py
├── signals/
│   ├── test_indicators.py
│   ├── test_intraday.py
│   ├── test_short_term.py
│   └── test_long_term.py
├── screener/
│   └── test_engine.py
├── tracker/
│   ├── test_store.py
│   ├── test_analyzer.py
│   ├── test_confluence.py
│   ├── test_outcome_tracker.py
│   └── test_watcher.py
├── patterns/
│   ├── test_miner.py
│   ├── test_fingerprint.py
│   └── test_matcher.py
├── options/
│   └── test_flow_degradation.py
├── alerts/
│   └── test_notifier.py
├── watchlists/
│   └── test_store.py
├── integration/
│   └── test_dashboard_smoke.py  # Skip unless Streamlit/Playwright available
└── fixtures/
    ├── sample_ohlcv.csv
    └── mock_provider_responses/
```

Test categories:
- **Unit tests:** Pure functions (indicators, scoring, config, normalization).
- **Database tests:** Isolated SQLite files; reset tables per test.
- **Provider-contract tests:** Mock responses for each provider verifying column/index shape.
- **Characterization tests:** Pin current behavior; update when bugs are fixed.
- **Integration tests:** End-to-end with mocked external calls; optional UI smoke tests.
- **Research experiments:** Live in `research/experiments/`; not run by default `pytest`.

## Research-code organization

```text
research/
├── README.md
├── hypotheses/
│   └── 2026-08-intraday-vwap-reversal.md
├── experiments/
│   ├── 2026-08-01_short_term_ema_pullback/
│   │   ├── README.md
│   │   ├── notebook.ipynb
│   │   └── results.csv
│   └── ...
├── notebooks/
└── results/
```

Every experiment must record:
- Hypothesis
- Universe and period
- Signal definition
- Entry, stop, target, costs
- Results (win rate, expectancy, drawdown, etc.)
- Limitations
- Decision (adopt / reject / continue research)

`tradex/` production code must not import from `research/`.

## Proposed migration sequence

1. **Do not move files in the initial audit PR.** The audit PR should only add documentation and characterization tests.
2. **Project 1 (correctness) and Project 2 (tests):** Make minimal file changes; do not reorganize.
3. **Project 9 (UI split):** This is the first large reorganization. Move `dashboard.py` tab bodies into `tradex/ui/tabs/*.py` in a single mechanical move with no behavior change.
4. **Project 4 (scheduler/alert) and Project 5 (backtest):** Add new packages (`tradex/market`, `tradex/alerts/policy.py`, `tradex/backtest/`).
5. **Project 6/7 (signal redesign):** Keep files in place; change logic only after validation.
6. **Project 8 (remove/quarantine):** If a feature is removed, move it to `research/` or delete it in a dedicated PR.

This sequence keeps reorganization and logic changes in separate pull requests, reducing the risk of mixing the two.
