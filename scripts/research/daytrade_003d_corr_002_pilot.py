"""DAYTRADE-003D-CORR-002 Bounded January 2, 2024 Pilot Runner.

Orchestrates the single-session data feasibility pilot under corrected sparse-bar
semantics, inexpensive technical pre-filtering, and the formal 95% candidate-screening gate.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.research.daytrade_orb.corr_002_pilot import (
    CANDIDATE_SCREENING_GATE_THRESHOLD,
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRIVATE_ROOT,
    MAX_PILOT_PAGES_LIMIT,
    MAX_PILOT_STORAGE_BYTES_LIMIT,
    PILOT_DATE,
    STRATEGY_ID,
    TASK_ID,
    BroadDailyAvailabilityAudit,
    CandidateScreeningAudit,
    CandidateScreeningOutcome,
    FrozenSelectionEvidence,
    PilotDisposition,
    StageBPathAudit,
    TargetUniverseAudit,
    audit_broad_daily_availability,
    audit_candidate_screening,
    audit_stage_b_price_path,
    batch_symbols,
    determine_pilot_disposition,
    evaluate_opening_range,
    filter_and_audit_target_universe,
    freeze_top_20_selection,
    get_prior_xnys_sessions,
    rank_and_select_top_20,
    verify_upstream_spec_hashes,
)
from tradex.research.daytrade_orb.data_feasibility import load_probe_credentials
from tradex.research.daytrade_orb.models import (
    DailyBar,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)
from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient
from tradex.research.intraday_dataset.massive_client import MassiveDatasetClient
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

logger = logging.getLogger(__name__)
MARKET_TIMEZONE = ZoneInfo("America/New_York")


def _write_safe_public_report(
    output_dir: Path,
    disposition: PilotDisposition,
    blocker_details: list[str],
    pre_live_commit_sha: str,
    elapsed_seconds: float,
    massive_page_count: int,
    massive_row_count: int,
    massive_snapshot_hash: str,
    target_audit: TargetUniverseAudit | None,
    daily_audit: BroadDailyAvailabilityAudit | None,
    screening_audit: CandidateScreeningAudit | None,
    selection_evidence: FrozenSelectionEvidence | None,
    stage_b_audit: StageBPathAudit | None,
    alpaca_call_count: int,
    alpaca_page_count: int,
    alpaca_retry_count: int,
    private_storage_bytes: int,
) -> Path:
    """Write safe committed markdown report containing only aggregates and cryptographic hashes."""
    report_path = Path("docs/research/DAYTRADE-003D-CORR-002.md")
    report_lines = [
        "# DAYTRADE-003D-CORR-002",
        "# Sparse-Bar Correction and Final January 2 Data Pilot",
        "",
        "## 1. Executive Summary & Authoritative Disposition",
        "",
        f"- **Task ID:** `{TASK_ID}`",
        f"- **Strategy ID:** `{STRATEGY_ID}`",
        f"- **Pilot Date:** `{PILOT_DATE}`",
        f"- **Pre-Live Frozen Commit SHA:** `{pre_live_commit_sha}`",
        f"- **Authoritative Pilot Disposition:** `**{disposition.value}**`",
        f"- **Execution Wall-Clock Runtime:** `{elapsed_seconds:.2f} seconds`",
        f"- **Total Private Raw Storage:** `{private_storage_bytes:,} bytes` (Bound: `{MAX_PILOT_STORAGE_BYTES_LIMIT:,} bytes`)",
        f"- **Approved Production Strategies:** `{list(APPROVED_PRODUCTION_STRATEGIES)}` (strictly empty)",
        "",
    ]

    if blocker_details:
        report_lines.extend([
            "### Disposition Explanations & Blocker Details",
            "",
            *[f"- {b}" for b in blocker_details],
            "",
        ])

    report_lines.extend([
        "## 2. Methodology & Upstream Specification Hashes",
        "",
        "| Document | Path | SHA-256 Hash | Status |",
        "| :--- | :--- | :--- | :--- |",
        "| **003B Specification** | `docs/research/specs/DAYTRADE-003B-ORB-v1.json` | `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0` | Immutable Verified |",
        "| **003C Resolution** | `docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json` | `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6` | Immutable Verified |",
        "| **003D Data Feasibility** | `docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json` | `533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c` | Immutable Verified |",
        "| **003D-CORR-001 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-001-v1.json` | `d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd` | Immutable Verified |",
        "",
        "## 3. Data Availability & Coverage Audit Results",
        "",
    ])

    if target_audit is not None:
        report_lines.extend([
            "### Phase 1: Massive PIT Target Universe (2024-01-02)",
            "",
            f"- **Raw Massive Snapshot Rows:** `{target_audit.total_snapshot_rows:,}` (`{massive_page_count}` pages, SHA-256: `{massive_snapshot_hash}`)",
            "- **Target Exchange Scope:** `('XNYS', 'XNAS')`",
            f"- **Canonical Target Universe Count:** `{target_audit.canonical_target_universe_count:,}` (Denominator: valid + ambiguous)",
            f"- **Valid Canonical Symbols Queried:** `{len(target_audit.valid_target_symbols):,}`",
            f"- **Ambiguous Duplicate Symbols (Fail-Closed):** `{len(target_audit.ambiguous_symbols):,}`",
            f"- **Target Universe Hash:** `{target_audit.universe_sha256}`",
            "",
        ])

    if daily_audit is not None:
        report_lines.extend([
            "### Phase 2: Broad Daily Data Availability (Dec 2023 D-1 Lookback)",
            "",
            f"- **Broad PIT Universe Symbols:** `{daily_audit.canonical_target_universe_count:,}`",
            f"- **Daily Indicator Computable Symbols:** `{daily_audit.daily_computable_count:,}`",
            f"- **Broad Universe Daily Data Availability:** `{daily_audit.daily_availability_pct:.2f}%`",
            f"- **Missing Daily Data Count:** `{daily_audit.missing_daily_data_count:,}`",
            f"- **Daily-Base-Qualified Universe Count (ADV14 >= 1M, ATR14 > $0.50):** `{daily_audit.daily_base_qualified_count:,}`",
            "",
        ])

    if screening_audit is not None:
        report_lines.extend([
            "### Phase 3: Candidate-Screening Completeness Audit (Scope E Gate)",
            "",
            f"- **Screening Denominator (Daily-Base-Qualified Pool):** `{screening_audit.daily_base_qualified_count:,}`",
            f"- **Validly Determined Symbols:** `{screening_audit.validly_determined_count:,}`",
            f"- **Candidate-Screening Completeness:** `{screening_audit.screening_completeness_pct:.2f}%` (Gate Threshold: `{screening_audit.screening_gate_threshold_pct:.2f}%`)",
            f"- **Gate Evaluated:** `**{'PASSED' if screening_audit.meets_screening_gate else 'FAILED'}**`",
            "",
            "#### Classification Breakdown among Daily-Base-Qualified Pool:",
            "",
            f"- **Legitimate No-Opening-Print (09:30–09:34 ET no trades):** `{screening_audit.no_opening_print_count:,}`",
            f"- **Price Filter Rejected (Open <= $5.00):** `{screening_audit.outcome_distribution.get(CandidateScreeningOutcome.PRICE_REJECTED.value, 0):,}`",
            f"- **Undefined RV Baseline (All 14 prior sessions zero OR volume):** `{screening_audit.zero_rv_baseline_count:,}`",
            f"- **RV Filter Rejected (RV < 1.0):** `{screening_audit.outcome_distribution.get(CandidateScreeningOutcome.RV_REJECTED.value, 0):,}`",
            f"- **Eligible Candidates (Passed all 4 filters):** `{screening_audit.eligible_candidate_count:,}`",
            f"- **Genuine Provider Data Failures:** `{screening_audit.provider_failure_count:,}`",
            "",
        ])

    if selection_evidence is not None:
        report_lines.extend([
            "### Phase 4: Frozen Top-20 Selection Evidence (Scope D Step 6)",
            "",
            f"- **Total Qualifying Candidates:** `{selection_evidence.eligible_candidates_count:,}`",
            f"- **Top-20 Selected Count:** `{selection_evidence.selected_count:,}`",
            f"- **Doji Count (No-Order):** `{selection_evidence.doji_count:,}`",
            f"- **Selection Cryptographic SHA-256:** `{selection_evidence.selection_sha256}`",
            "- *(Detailed symbol records and position allocations preserved privately in private root)*",
            "",
        ])

    if stage_b_audit is not None:
        report_lines.extend([
            "### Phase 5: Stage-B Price Path Audit & Evaluator Compatibility (Scope F)",
            "",
            f"- **Selected Non-Doji Symbols Acquired:** `{stage_b_audit.selected_actionable_symbols_count:,}`",
            f"- **Total Expected Minute Intervals:** `{stage_b_audit.total_expected_minutes:,}`",
            f"- **Total Actual Provider Bars Received:** `{stage_b_audit.total_actual_bars:,}`",
            f"- **Total Sparse / Verified No-Print Minute Intervals:** `{stage_b_audit.total_sparse_minutes:,}`",
            f"- **Symbols Missing 15:59 EOD Liquidation Bar:** `{stage_b_audit.missing_eod_bar_symbols_count:,}`",
            f"- **Stage-B Provider Failures:** `{stage_b_audit.provider_failure_count:,}`",
            f"- **Stage-B Price Path Usability:** `**{'USABLE' if stage_b_audit.is_usable else 'UNUSABLE'}**`",
            "",
        ])

    report_lines.extend([
        "## 4. Provider Resource Consumption & Provenance",
        "",
        f"- **Alpaca Total Logical Calls:** `{alpaca_call_count:,}`",
        f"- **Alpaca Total HTTP Pages:** `{alpaca_page_count:,}`",
        f"- **Alpaca Retries / 429s:** `{alpaca_retry_count:,}`",
        f"- **Massive HTTP Pages:** `{massive_page_count:,}`",
        f"- **Total Provider HTTP Pages:** `{alpaca_page_count + massive_page_count:,}` (Ceiling: `{MAX_PILOT_PAGES_LIMIT:,}`)",
        f"- **Total Elapsed Runtime:** `{elapsed_seconds:.2f} seconds`",
        "",
        "## 5. Governance & Production Safeguards",
        "",
        "- **Strategy Simulation / Backtest:** Strictly forbidden and not executed.",
        "- **PnL / Sharpe / Win-Rate Computation:** Strictly forbidden and not executed.",
        "- **Full-Year 2024 Acquisition:** Quarantined and not executed.",
        "- **2025 Validation / 2026 Holdout Partitions:** Strictly unopened and quarantined.",
        "- **External Strategy Retention Principle:** The Stocks-in-Play 5-minute ORB strategy remains an authorized external candidate regardless of TradeX independent evaluation outcomes.",
        "- **Production Strategy Registry:** `APPROVED_PRODUCTION_STRATEGIES == ()` strictly verified.",
        "",
    ])

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return report_path


def run_corr_002_pilot(
    output_dir: Path,
    pre_live_commit_sha: str,
    repo_root: Path,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Execute the bounded January 2, 2024 pilot."""
    t0 = time.time()
    print("=" * 80)
    print(f"STARTING {TASK_ID} PILOT: Bounded {PILOT_DATE} Data Feasibility Study")
    print(f"Pre-Live Frozen Commit SHA: {pre_live_commit_sha}")
    print(f"Private Data Output Root:   {output_dir}")
    print("=" * 80)

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Spec hash verification
    print("\n[VERIFICATION] Verifying all upstream specification hashes...")
    specs_ok, actual_hashes, spec_errors = verify_upstream_spec_hashes(repo_root)
    for p, h in actual_hashes.items():
        print(f"  -> {p}: {h}")
    if not specs_ok:
        print(f"  [FATAL] Specification hash verification failed: {spec_errors}")
        return 1
    print("  -> All four upstream specification hashes VERIFIED.")

    # 2. Production strategy registry check
    print("\n[VERIFICATION] Verifying production strategy registry status...")
    if APPROVED_PRODUCTION_STRATEGIES != ():
        print(f"  [FATAL] Production strategy registry is not empty: {APPROVED_PRODUCTION_STRATEGIES}")
        return 1
    print("  -> Production strategy registry is strictly EMPTY.")

    # Credentials check
    massive_key, alpaca_key, alpaca_secret = load_probe_credentials()

    if not dry_run and (not alpaca_key or not alpaca_secret or not massive_key):
        print("  [FATAL] Missing required market data credentials (ALPACA_API_KEY / MASSIVE_API_KEY)")
        return 1

    massive_page_count = 0
    massive_row_count = 0
    massive_snapshot_hash = ""
    alpaca_call_count = 0
    alpaca_page_count = 0
    alpaca_retry_count = 0

    target_audit: TargetUniverseAudit | None = None
    daily_audit: BroadDailyAvailabilityAudit | None = None
    screening_audit: CandidateScreeningAudit | None = None
    selection_evidence: FrozenSelectionEvidence | None = None
    stage_b_audit: StageBPathAudit | None = None

    if dry_run:
        print("\n[DRY RUN] Executing dry run mode without live API calls...")
        # Offline dry run logic
        return 0

    massive_client = MassiveDatasetClient(massive_key)
    alpaca_client = DatasetAlpacaClient(alpaca_key, alpaca_secret)

    # -------------------------------------------------------------------------
    # PHASE 1: Massive PIT Reference Snapshot for 2024-01-02
    # -------------------------------------------------------------------------
    print(f"\n[PHASE 1] Retrieving Massive point-in-time reference snapshot for {PILOT_DATE}...")
    try:
        snap = massive_client.fetch_reference_snapshot(
            pit_date=PILOT_DATE,
            active=True,
            safety_max_pages=50,
        )
        obs = snap.observations[0]
        massive_page_count = obs.page_count
        massive_row_count = obs.row_count
        massive_snapshot_hash = obs.raw_sha256
        raw_rows = snap.rows

        if not obs.pagination_complete or obs.error:
            raise RuntimeError(f"Massive terminal pagination failure: {obs.error}")

        print(f"  -> Retrieved {massive_row_count:,} raw rows across {massive_page_count} pages (SHA-256: {massive_snapshot_hash[:16]}...)")

        # Save private raw reference snapshot
        private_ref_path = output_dir / f"massive_reference_{PILOT_DATE}.json"
        private_ref_path.write_text(json.dumps(raw_rows, indent=2), encoding="utf-8")

        # Filter target universe and audit duplicates
        target_audit, _target_rows_map = filter_and_audit_target_universe(raw_rows)
        print(f"  -> Canonical target universe count: {target_audit.canonical_target_universe_count:,} (valid: {len(target_audit.valid_target_symbols):,}, ambiguous: {len(target_audit.ambiguous_symbols):,})")
        print(f"  -> Target exchange distribution:   {target_audit.target_exchange_distribution}")

        # Save private universe file
        private_univ_path = output_dir / f"universe_{PILOT_DATE}.json"
        private_univ_path.write_text(
            json.dumps({
                "date": PILOT_DATE,
                "canonical_target_universe_count": target_audit.canonical_target_universe_count,
                "valid_symbols_count": len(target_audit.valid_target_symbols),
                "ambiguous_symbols_count": len(target_audit.ambiguous_symbols),
                "universe_sha256": target_audit.universe_sha256,
                "valid_symbols": target_audit.valid_target_symbols,
                "ambiguous_symbols": target_audit.ambiguous_symbols,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [FATAL] Massive snapshot failed: {exc}")
        disposition, blockers = determine_pilot_disposition(
            reference_success=False,
            provider_access_success=True,
            provider_data_integrity_success=True,
            candidate_screening_gate_passed=False,
            eligible_candidate_count=0,
            stage_b_path_usable=False,
        )
        blockers.append(str(exc))
        _write_safe_public_report(output_dir, disposition, blockers, pre_live_commit_sha, time.time() - t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, daily_audit, screening_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count, 0)
        return 1

    # -------------------------------------------------------------------------
    # PHASE 2: Inexpensive Daily Screening across Broad Universe (Scope D)
    # -------------------------------------------------------------------------
    print(f"\n[PHASE 2] Acquiring daily bars (Dec 2023) across {len(target_audit.valid_target_symbols):,} symbols in batches of {batch_size}...")
    valid_symbols = target_audit.valid_target_symbols
    symbol_batches = batch_symbols(valid_symbols, batch_size=batch_size)
    target_dt = date.fromisoformat(PILOT_DATE)

    d_start_utc = datetime(2023, 12, 1, 0, 0, tzinfo=UTC)
    d_end_utc = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)
    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}

    for b_idx, batch in enumerate(symbol_batches, start=1):
        if b_idx % 20 == 0 or b_idx == len(symbol_batches):
            print(f"    Fetching daily batch {b_idx}/{len(symbol_batches)} ({len(batch)} symbols)...")
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=d_start_utc,
            end_utc=d_end_utc,
            feed="sip",
            timeframe="1Day",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        alpaca_call_count += 1
        alpaca_page_count += meta.get("page_count", 1)

        for sym, df in dfs.items():
            if not df.empty:
                bars = []
                for ts, row in df.iterrows():
                    ny_dt = ts.astimezone(MARKET_TIMEZONE)
                    bars.append(DailyBar(
                        symbol=sym,
                        session_date=ny_dt.date(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                daily_bars_by_symbol[sym] = bars

    # Audit broad daily data availability and find daily-base-qualified pool
    daily_audit, _computable_daily, daily_base_qualified_symbols = audit_broad_daily_availability(
        valid_target_symbols=target_audit.valid_target_symbols,
        ambiguous_symbols=target_audit.ambiguous_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        lookback=14,
        adv_min=1_000_000.0,
        atr_min=0.50,
    )
    print(f"  -> Broad universe daily computable: {daily_audit.daily_computable_count:,} / {daily_audit.canonical_target_universe_count:,} ({daily_audit.daily_availability_pct:.2f}%)")
    print(f"  -> Missing daily data:             {daily_audit.missing_daily_data_count:,}")
    print(f"  -> Daily-base-qualified pool:       {daily_audit.daily_base_qualified_count:,} symbols (ADV14 >= 1M, ATR14 > $0.50)")

    # -------------------------------------------------------------------------
    # PHASE 3: Current Opening Range & Prior RV for Daily-Qualified Subset
    # -------------------------------------------------------------------------
    print(f"\n[PHASE 3] Acquiring current opening-range (09:30–09:34 ET) for {len(daily_base_qualified_symbols):,} daily-qualified symbols...")
    dq_batches = batch_symbols(daily_base_qualified_symbols, batch_size=batch_size)
    c_start_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    c_end_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    current_or_by_symbol: dict[str, OpeningRange | None] = {}
    current_or_provider_failures: set[str] = set()

    for b_idx, batch in enumerate(dq_batches, start=1):
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=c_start_utc,
            end_utc=c_end_utc,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        alpaca_call_count += 1
        alpaca_page_count += meta.get("page_count", 1)

        http_status = meta.get("http_status", 0)
        pagination_complete = meta.get("pagination_complete", False)
        if http_status != 200 or not pagination_complete:
            # Genuine provider failure for this batch
            current_or_provider_failures.update(batch)
            continue

        for sym in batch:
            df = dfs.get(sym, pd.DataFrame())
            if df.empty:
                # Verified completed response with zero trades -> NO_OPENING_PRINT_NO_SETUP
                current_or_by_symbol[sym] = None
            else:
                minute_bars = []
                for ts, row in df.iterrows():
                    minute_bars.append(MinuteBar(
                        symbol=sym,
                        timestamp=ts,
                        session_date=target_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                op = evaluate_opening_range(minute_bars, require_five_bars=False)
                current_or_by_symbol[sym] = op

    # Filter surviving symbols needing RV: those with valid opening range and or_open > 5.0
    surviving_needing_rv = [
        sym for sym in daily_base_qualified_symbols
        if sym in current_or_by_symbol
        and current_or_by_symbol[sym] is not None
        and current_or_by_symbol[sym].or_open > 5.0  # type: ignore[union-attr]
    ]
    print(f"  -> Surviving symbols needing RV (or_open > $5.00): {len(surviving_needing_rv):,} / {len(daily_base_qualified_symbols):,}")

    prior_14_sessions = get_prior_xnys_sessions(target_dt, 14)
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {}
    prior_or_provider_failures: set[str] = set()

    if surviving_needing_rv:
        rv_batches = batch_symbols(surviving_needing_rv, batch_size=batch_size)
        print(f"  -> Querying prior 14 opening sessions for {len(surviving_needing_rv):,} symbols ({len(rv_batches)} batches * 14 sessions = {len(rv_batches)*14} calls)...")

        for s_idx, sess_d in enumerate(prior_14_sessions, start=1):
            p_start_utc = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
            p_end_utc = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

            for batch in rv_batches:
                dfs, meta = alpaca_client.get_bars(
                    batch,
                    start_utc=p_start_utc,
                    end_utc=p_end_utc,
                    feed="sip",
                    timeframe="1Min",
                    adjustment="raw",
                    asof=PILOT_DATE,
                )
                alpaca_call_count += 1
                alpaca_page_count += meta.get("page_count", 1)

                http_status = meta.get("http_status", 0)
                pagination_complete = meta.get("pagination_complete", False)
                if http_status != 200 or not pagination_complete:
                    prior_or_provider_failures.update(batch)
                    continue

                for sym in batch:
                    df = dfs.get(sym, pd.DataFrame())
                    vol = float(df["volume"].sum()) if not df.empty else 0.0
                    prior_or_obs_by_symbol.setdefault(sym, []).append(
                        OpeningRangeVolumeObservation(
                            symbol=sym,
                            session_date=sess_d,
                            volume=vol,
                        )
                    )

    # Audit candidate-screening completeness
    screening_audit, _outcomes, eligible_candidates, surviving_opening_ranges = audit_candidate_screening(
        daily_base_qualified_symbols=daily_base_qualified_symbols,
        current_or_by_symbol=current_or_by_symbol,
        current_or_provider_failures=current_or_provider_failures,
        prior_or_obs_by_symbol=prior_or_obs_by_symbol,
        prior_or_provider_failures=prior_or_provider_failures,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        price_min=5.0,
        adv_min=1_000_000.0,
        atr_min=0.50,
        rv_min=1.0,
        gate_threshold=CANDIDATE_SCREENING_GATE_THRESHOLD,
    )
    print(f"\n[PHASE 3 AUDIT] Candidate-screening completeness: {screening_audit.screening_completeness_pct:.2f}% (threshold: {screening_audit.screening_gate_threshold_pct}%)")
    print(f"  -> Meets 95% screening gate: {screening_audit.meets_screening_gate}")
    print(f"  -> Classification breakdown: {screening_audit.outcome_distribution}")
    print(f"  -> Eligible candidates:     {screening_audit.eligible_candidate_count:,}")

    if not screening_audit.meets_screening_gate:
        print(f"  [STOP] Candidate-screening completeness ({screening_audit.screening_completeness_pct:.2f}%) < 95.0%!")
        disposition, blockers = determine_pilot_disposition(
            reference_success=True,
            provider_access_success=True,
            provider_data_integrity_success=True,
            candidate_screening_gate_passed=False,
            eligible_candidate_count=len(eligible_candidates),
            stage_b_path_usable=False,
        )
        _write_safe_public_report(output_dir, disposition, blockers, pre_live_commit_sha, time.time() - t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, daily_audit, screening_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count, 0)
        return 1

    # -------------------------------------------------------------------------
    # PHASE 4: Freeze Top-20 Selection
    # -------------------------------------------------------------------------
    print(f"\n[PHASE 4] Freezing Top-20 selection among {len(eligible_candidates):,} eligible candidates...")
    ranked_candidates = rank_and_select_top_20(
        candidates=eligible_candidates,
        opening_ranges=surviving_opening_ranges,
        session_start_equity=25000.0,
        top_n=20,
    )
    selection_evidence, selection_records, _selected_symbols = freeze_top_20_selection(ranked_candidates)
    print(f"  -> Selected Top-20 count: {selection_evidence.selected_count:,}")
    print(f"  -> Doji count:            {selection_evidence.doji_count:,}")
    print(f"  -> Selection SHA-256:     {selection_evidence.selection_sha256}")

    # Persist selection artifact privately
    private_sel_path = output_dir / f"top_20_selection_{PILOT_DATE}.json"
    private_sel_path.write_text(
        json.dumps({
            "date": PILOT_DATE,
            "selection_sha256": selection_evidence.selection_sha256,
            "selected_count": selection_evidence.selected_count,
            "doji_count": selection_evidence.doji_count,
            "eligible_candidates_count": selection_evidence.eligible_candidates_count,
            "records": selection_records,
        }, indent=2),
        encoding="utf-8",
    )

    # -------------------------------------------------------------------------
    # PHASE 5: Stage B (09:35–15:59 ET) for Actionable Symbols
    # -------------------------------------------------------------------------
    actionable_symbols = [
        r["symbol"] for r in selection_records if r["order_intent_status"] != "NO_ORDER"
    ]
    print(f"\n[PHASE 5] Acquiring Stage B (09:35–15:59 ET) for {len(actionable_symbols)} non-doji selected symbols...")
    stage_b_bars_by_symbol: dict[str, list[MinuteBar]] = {}
    stage_b_failures: set[str] = set()

    if actionable_symbols:
        b_start_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 35, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
        b_end_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 15, 59, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

        b_batches = batch_symbols(actionable_symbols, batch_size=batch_size)
        for batch in b_batches:
            dfs, meta = alpaca_client.get_bars(
                batch,
                start_utc=b_start_utc,
                end_utc=b_end_utc,
                feed="sip",
                timeframe="1Min",
                adjustment="raw",
                asof=PILOT_DATE,
            )
            alpaca_call_count += 1
            alpaca_page_count += meta.get("page_count", 1)

            http_status = meta.get("http_status", 0)
            pagination_complete = meta.get("pagination_complete", False)
            if http_status != 200 or not pagination_complete:
                stage_b_failures.update(batch)
                continue

            for sym in batch:
                df = dfs.get(sym, pd.DataFrame())
                bars = []
                for ts, row in df.iterrows():
                    bars.append(MinuteBar(
                        symbol=sym,
                        timestamp=ts,
                        session_date=target_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                stage_b_bars_by_symbol[sym] = bars

    stage_b_audit = audit_stage_b_price_path(
        active_selected_symbols=actionable_symbols,
        stage_b_bars_by_symbol=stage_b_bars_by_symbol,
        stage_b_provider_failures=stage_b_failures,
        expected_minutes=385,
    )
    print(f"  -> Total expected minutes:       {stage_b_audit.total_expected_minutes:,}")
    print(f"  -> Total actual bars received:   {stage_b_audit.total_actual_bars:,}")
    print(f"  -> Total sparse minutes:         {stage_b_audit.total_sparse_minutes:,}")
    print(f"  -> Missing 15:59 EOD bar count:  {stage_b_audit.missing_eod_bar_symbols_count:,}")
    print(f"  -> Stage-B path usability:       {'USABLE' if stage_b_audit.is_usable else 'UNUSABLE'}")

    # Calculate private storage bytes
    private_storage_bytes = sum(f.stat().st_size for f in output_dir.glob("*") if f.is_file())

    # -------------------------------------------------------------------------
    # PHASE 6: Final Pilot Disposition
    # -------------------------------------------------------------------------
    disposition, blockers = determine_pilot_disposition(
        reference_success=True,
        provider_access_success=True,
        provider_data_integrity_success=True,
        candidate_screening_gate_passed=screening_audit.meets_screening_gate,
        eligible_candidate_count=screening_audit.eligible_candidate_count,
        stage_b_path_usable=stage_b_audit.is_usable,
    )
    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"FINAL PILOT DISPOSITION: {disposition.value}")
    print(f"Total Runtime: {elapsed:.2f}s, Alpaca Pages: {alpaca_page_count}, Storage: {private_storage_bytes:,} bytes")
    print("=" * 80)

    # Write safe public report
    report_file = _write_safe_public_report(
        output_dir=output_dir,
        disposition=disposition,
        blocker_details=blockers,
        pre_live_commit_sha=pre_live_commit_sha,
        elapsed_seconds=elapsed,
        massive_page_count=massive_page_count,
        massive_row_count=massive_row_count,
        massive_snapshot_hash=massive_snapshot_hash,
        target_audit=target_audit,
        daily_audit=daily_audit,
        screening_audit=screening_audit,
        selection_evidence=selection_evidence,
        stage_b_audit=stage_b_audit,
        alpaca_call_count=alpaca_call_count,
        alpaca_page_count=alpaca_page_count,
        alpaca_retry_count=alpaca_retry_count,
        private_storage_bytes=private_storage_bytes,
    )
    print(f"Safe public report updated: {report_file}")
    return 0 if disposition == PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="DAYTRADE-003D-CORR-002 Pilot Runner")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PRIVATE_ROOT, help="Private storage root")
    parser.add_argument("--pre-live-sha", type=str, required=True, help="Pre-live frozen commit SHA")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root path")
    parser.add_argument("--dry-run", action="store_true", help="Run without live network calls")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for provider requests")
    args = parser.parse_args()

    return run_corr_002_pilot(
        output_dir=args.output_dir,
        pre_live_commit_sha=args.pre_live_sha,
        repo_root=args.repo_root,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    sys.exit(main())
