"""DAYTRADE-003D-CORR-003 Bounded January 2, 2024 Pilot Runner and Offline Replay CLI.

Features:
1. 'replay' subcommand: deterministic, credential-free, network-free offline replay from
   persisted private raw provider artifacts with fail-closed cryptographic manifest verification.
2. 'pilot' subcommand: bounded live provider pilot gated behind Gary Yang's explicit authorization.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.research.daytrade_orb.corr_003_pilot import (
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
    acquire_atomic_pilot_run_lock,
    audit_broad_daily_availability,
    audit_candidate_screening,
    audit_stage_b_price_path_corr_003,
    batch_symbols,
    check_one_shot_pilot_guard,
    check_pilot_authorization,
    check_pre_live_code_freeze,
    check_resource_limits,
    create_and_save_manifest,
    determine_pilot_disposition_corr_003,
    evaluate_opening_range,
    filter_and_audit_target_universe,
    freeze_top_20_selection,
    get_prior_xnys_sessions,
    hash_bytes,
    rank_and_select_top_20,
    replay_corr_003_pilot,
    validate_batch_size,
    validate_provider_batch_response,
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
    manifest_sha256: str = "",
) -> Path:
    """Write safe committed markdown report containing only aggregates and cryptographic hashes."""
    report_path = Path("docs/research/DAYTRADE-003D-CORR-003.md")
    report_lines = [
        "# DAYTRADE-003D-CORR-003",
        "# ORB Provider Integrity, Offline Replay, and Stage-B Validation",
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
        f"- **Manifest SHA-256:** `{manifest_sha256}`",
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
        "| **003D-CORR-002 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-002-v1.json` | `d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c` | Locked Preregistered |",
        "| **003D-CORR-003 Spec** | `docs/research/specs/DAYTRADE-003D-CORR-003-v1.json` | `2f86d1231f55180b8fe4f65832cde8783e7c6058788a1e98130353b5822a1cdb` | Locked Preregistered |",
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
            "### Phase 5: Stage-B Price Path Audit & Evaluator Compatibility",
            "",
            f"- **Selected Non-Doji Symbols Acquired:** `{stage_b_audit.selected_actionable_symbols_count:,}`",
            f"- **Total Expected Minute Intervals:** `{stage_b_audit.total_expected_minutes:,}`",
            f"- **Total Actual Provider Bars Received:** `{stage_b_audit.total_actual_bars:,}`",
            f"- **Total Sparse / Verified No-Print Minute Intervals:** `{stage_b_audit.total_sparse_minutes:,}`",
            f"- **Symbols Missing 15:59 EOD Liquidation Bar:** `{stage_b_audit.missing_eod_bar_symbols_count:,}`",
            f"- **Stage-B Provider Failures:** `{stage_b_audit.provider_failure_count:,}`",
            f"- **Stage-B Integrity Failures:** `{stage_b_audit.integrity_failure_count:,}`",
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


def run_corr_003_live_pilot(
    output_dir: Path,
    pre_live_commit_sha: str,
    repo_root: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    authorized_by_gary: bool = False,
) -> int:
    """Execute the bounded January 2, 2024 live pilot with full raw persistence and integrity checks."""
    # 0. Prospective execution, freeze, and authorization guards
    try:
        validate_batch_size(batch_size)
        check_one_shot_pilot_guard(output_dir, PILOT_DATE)
        check_pre_live_code_freeze(repo_root, pre_live_commit_sha)
        check_pilot_authorization(repo_root, pre_live_commit_sha, authorized_by_gary)
    except (ValueError, RuntimeError, PermissionError) as guard_exc:
        print(f"[FATAL] Execution guard rejected run: {guard_exc}")
        return 1

    t0 = time.time()
    print("=" * 80)
    print(f"STARTING {TASK_ID} LIVE PILOT: Bounded {PILOT_DATE} Feasibility Study")
    print(f"Pre-Live Frozen Commit SHA: {pre_live_commit_sha}")
    print(f"Private Data Output Root:   {output_dir}")
    print("=" * 80)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Durable atomic run lock marker: fail closed on restart or concurrent runs
    lock_marker_path = acquire_atomic_pilot_run_lock(output_dir, PILOT_DATE, pre_live_commit_sha)
    lock_data = lock_marker_path.read_bytes()

    current_storage_bytes = len(lock_data)
    total_pages_used = 0

    # 1. Spec hash verification
    specs_ok, actual_hashes, spec_errors = verify_upstream_spec_hashes(repo_root)
    for p, h in actual_hashes.items():
        print(f"  -> {p}: {h}")
    if not specs_ok:
        print(f"  [FATAL] Specification hash verification failed: {spec_errors}")
        return 1
    print("  -> All upstream specification hashes VERIFIED.")

    # 2. Production strategy registry check
    if APPROVED_PRODUCTION_STRATEGIES != ():
        print(f"  [FATAL] Production strategy registry is not empty: {APPROVED_PRODUCTION_STRATEGIES}")
        return 1
    print("  -> Production strategy registry is strictly EMPTY.")

    massive_key, alpaca_key, alpaca_secret = load_probe_credentials()
    if not alpaca_key or not alpaca_secret or not massive_key:
        print("  [FATAL] Missing market data credentials (ALPACA_API_KEY / MASSIVE_API_KEY)")
        return 1

    massive_client = MassiveDatasetClient(massive_key)
    alpaca_client = DatasetAlpacaClient(alpaca_key, alpaca_secret)

    artifacts_info: dict[str, dict[str, Any]] = {}
    alpaca_call_count = 0
    alpaca_page_count = 0
    alpaca_retry_count = 0

    # -------------------------------------------------------------------------
    # PHASE 1: Massive PIT Reference Snapshot for 2024-01-02
    # -------------------------------------------------------------------------
    print(f"\n[PHASE 1] Retrieving Massive point-in-time reference snapshot for {PILOT_DATE}...")
    snap = massive_client.fetch_reference_snapshot(pit_date=PILOT_DATE, active=True, safety_max_pages=50)
    obs = snap.observations[0]
    massive_page_count = obs.page_count
    massive_row_count = obs.row_count
    massive_snapshot_hash = obs.raw_sha256
    raw_rows = snap.rows

    if not obs.pagination_complete or obs.error:
        raise RuntimeError(f"Massive terminal pagination failure: {obs.error}")

    # Track Massive page count prospectively
    total_pages_used += massive_page_count
    if total_pages_used > MAX_PILOT_PAGES_LIMIT:
        raise RuntimeError(
            f"Resource ceiling exceeded in Phase 1: total pages {total_pages_used} > limit {MAX_PILOT_PAGES_LIMIT}"
        )

    # Save private raw reference snapshot prospectively
    ref_filename = f"massive_reference_{PILOT_DATE}.json"
    ref_path = output_dir / ref_filename
    ref_bytes = json.dumps(raw_rows, indent=2).encode("utf-8")
    if current_storage_bytes + len(ref_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {ref_filename}: "
            f"current {current_storage_bytes} + prospective {len(ref_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    ref_path.write_bytes(ref_bytes)
    current_storage_bytes += len(ref_bytes)
    artifacts_info[ref_filename] = {
        "sha256": hash_bytes(ref_bytes),
        "size_bytes": len(ref_bytes),
        "description": "Massive reference snapshot raw rows",
        "record_count": len(raw_rows),
    }

    target_audit, _target_rows_map = filter_and_audit_target_universe(raw_rows)
    univ_filename = f"universe_{PILOT_DATE}.json"
    univ_path = output_dir / univ_filename
    univ_bytes = json.dumps({
        "date": PILOT_DATE,
        "canonical_target_universe_count": target_audit.canonical_target_universe_count,
        "valid_symbols_count": len(target_audit.valid_target_symbols),
        "ambiguous_symbols_count": len(target_audit.ambiguous_symbols),
        "universe_sha256": target_audit.universe_sha256,
        "valid_symbols": target_audit.valid_target_symbols,
        "ambiguous_symbols": target_audit.ambiguous_symbols,
    }, indent=2).encode("utf-8")
    if current_storage_bytes + len(univ_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {univ_filename}: "
            f"current {current_storage_bytes} + prospective {len(univ_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    univ_path.write_bytes(univ_bytes)
    current_storage_bytes += len(univ_bytes)
    artifacts_info[univ_filename] = {
        "sha256": hash_bytes(univ_bytes),
        "size_bytes": len(univ_bytes),
        "description": "Target universe classification and symbols",
        "record_count": target_audit.canonical_target_universe_count,
    }

    # -------------------------------------------------------------------------
    # PHASE 2: Inexpensive Daily Screening across Broad Universe
    # -------------------------------------------------------------------------
    valid_symbols = target_audit.valid_target_symbols
    symbol_batches = batch_symbols(valid_symbols, batch_size=batch_size)
    target_dt = date.fromisoformat(PILOT_DATE)
    d_start_utc = datetime(2023, 12, 1, 0, 0, tzinfo=UTC)
    d_end_utc = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)

    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}
    daily_raw_batches: list[dict[str, Any]] = []
    daily_provider_failures: set[str] = set()

    for b_idx, batch in enumerate(symbol_batches, start=1):
        remaining_pages = MAX_PILOT_PAGES_LIMIT - total_pages_used
        if remaining_pages <= 0:
            raise RuntimeError(
                f"Provider page budget exhausted before batch request: used {total_pages_used} >= limit {MAX_PILOT_PAGES_LIMIT}"
            )
        call_max_pages = min(100, remaining_pages)
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=d_start_utc,
            end_utc=d_end_utc,
            feed="sip",
            timeframe="1Day",
            adjustment="raw",
            asof=PILOT_DATE,
            include_raw_bars=True,
            include_raw_pages=True,
            max_pages=call_max_pages,
        )
        alpaca_call_count += 1
        pages_fetched = meta.get("page_count", 1)
        alpaca_page_count += pages_fetched
        total_pages_used += pages_fetched
        if meta.get("safe_error_classification") == "max_pages_exceeded" or total_pages_used > MAX_PILOT_PAGES_LIMIT:
            raise RuntimeError(
                f"Provider page budget exceeded during batch request: {total_pages_used} > limit {MAX_PILOT_PAGES_LIMIT}"
            )
        raw_bars = meta.get("raw_bars_by_symbol", {})

        batch_check = validate_provider_batch_response(
            symbols_requested=batch,
            meta=meta,
            bars_by_symbol=raw_bars,
            expected_start=datetime(2023, 12, 1, 0, 0, tzinfo=UTC),
            expected_end=datetime(2023, 12, 31, 23, 59, tzinfo=UTC),
            require_raw_pages=True,
        )

        batch_record = {
            "batch_index": b_idx,
            "symbols_requested": batch,
            "request_params": meta.get("request_params", {}),
            "http_status": meta.get("http_status"),
            "pagination_complete": meta.get("pagination_complete"),
            "meta": {
                "http_status": meta.get("http_status"),
                "pagination_complete": meta.get("pagination_complete"),
                "page_count": meta.get("page_count", 1),
                "safe_error_classification": meta.get("safe_error_classification", "none"),
                "repeated_page_token": meta.get("repeated_page_token", False),
                "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                "terminal_next_page_token_present": meta.get("terminal_next_page_token_present", False),
                "unconsumed_page_token_present": meta.get("unconsumed_page_token_present", False),
                "response_symbols": meta.get("response_symbols", []),
                "malformed_timestamp_counts": meta.get("malformed_timestamp_counts", {}),
                "token_hashes": meta.get("token_hashes", []),
                "token_sequence_sha256": meta.get("token_sequence_sha256", ""),
                "raw_pages": meta.get("raw_pages", []),
            },
            "bars_by_symbol": raw_bars,
            "integrity_status": batch_check.status.value,
        }
        daily_raw_batches.append(batch_record)

        if not batch_check.is_valid:
            daily_provider_failures.update(batch)
            continue

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

    daily_filename = "alpaca_daily_dec2023.json"
    daily_payload = {
        "metadata": {"stage": "phase_2_broad_daily", "session_date": PILOT_DATE},
        "batches": daily_raw_batches,
    }
    daily_bytes = json.dumps(daily_payload, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(daily_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {daily_filename}: "
            f"current {current_storage_bytes} + prospective {len(daily_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    (output_dir / daily_filename).write_bytes(daily_bytes)
    current_storage_bytes += len(daily_bytes)
    daily_hash = hash_bytes(daily_bytes)
    daily_size = len(daily_bytes)
    artifacts_info[daily_filename] = {
        "sha256": daily_hash,
        "size_bytes": daily_size,
        "description": "Raw Alpaca daily bars for Dec 2023 across target universe",
        "record_count": sum(len(b["bars_by_symbol"]) for b in daily_raw_batches),
    }

    daily_audit, _computable, daily_base_qualified = audit_broad_daily_availability(
        valid_target_symbols=target_audit.valid_target_symbols,
        ambiguous_symbols=target_audit.ambiguous_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        lookback=14,
        adv_min=1_000_000.0,
        atr_min=0.50,
    )

    # -------------------------------------------------------------------------
    # PHASE 3: Current Opening Range & Prior 14 Sessions RV
    # -------------------------------------------------------------------------
    dq_batches = batch_symbols(daily_base_qualified, batch_size=batch_size)
    c_start_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    c_end_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    current_or_by_symbol: dict[str, OpeningRange | None] = {}
    current_or_failures: set[str] = set()
    current_or_raw_batches: list[dict[str, Any]] = []

    for b_idx, batch in enumerate(dq_batches, start=1):
        remaining_pages = MAX_PILOT_PAGES_LIMIT - total_pages_used
        if remaining_pages <= 0:
            raise RuntimeError(
                f"Provider page budget exhausted before batch request: used {total_pages_used} >= limit {MAX_PILOT_PAGES_LIMIT}"
            )
        call_max_pages = min(100, remaining_pages)
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=c_start_utc,
            end_utc=c_end_utc,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=PILOT_DATE,
            include_raw_bars=True,
            include_raw_pages=True,
            max_pages=call_max_pages,
        )
        alpaca_call_count += 1
        pages_fetched = meta.get("page_count", 1)
        alpaca_page_count += pages_fetched
        total_pages_used += pages_fetched
        if meta.get("safe_error_classification") == "max_pages_exceeded" or total_pages_used > MAX_PILOT_PAGES_LIMIT:
            raise RuntimeError(
                f"Provider page budget exceeded during batch request: {total_pages_used} > limit {MAX_PILOT_PAGES_LIMIT}"
            )
        raw_bars = meta.get("raw_bars_by_symbol", {})

        batch_check = validate_provider_batch_response(
            symbols_requested=batch,
            meta=meta,
            bars_by_symbol=raw_bars,
            allowed_time_window=(time(9, 30), time(9, 34)),
            session_date=target_dt,
            require_raw_pages=True,
        )

        batch_record = {
            "batch_index": b_idx,
            "symbols_requested": batch,
            "request_params": meta.get("request_params", {}),
            "http_status": meta.get("http_status"),
            "pagination_complete": meta.get("pagination_complete"),
            "meta": {
                "http_status": meta.get("http_status"),
                "pagination_complete": meta.get("pagination_complete"),
                "page_count": meta.get("page_count", 1),
                "safe_error_classification": meta.get("safe_error_classification", "none"),
                "repeated_page_token": meta.get("repeated_page_token", False),
                "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                "terminal_next_page_token_present": meta.get("terminal_next_page_token_present", False),
                "unconsumed_page_token_present": meta.get("unconsumed_page_token_present", False),
                "response_symbols": meta.get("response_symbols", []),
                "malformed_timestamp_counts": meta.get("malformed_timestamp_counts", {}),
                "token_hashes": meta.get("token_hashes", []),
                "token_sequence_sha256": meta.get("token_sequence_sha256", ""),
                "raw_pages": meta.get("raw_pages", []),
            },
            "bars_by_symbol": raw_bars,
            "integrity_status": batch_check.status.value,
        }
        current_or_raw_batches.append(batch_record)

        if not batch_check.is_valid:
            current_or_failures.update(batch)
            continue

        for sym in batch:
            df = dfs.get(sym, pd.DataFrame())
            if df.empty:
                current_or_by_symbol[sym] = None
            else:
                m_bars = []
                for ts, row in df.iterrows():
                    m_bars.append(MinuteBar(
                        symbol=sym,
                        timestamp=ts,
                        session_date=target_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                current_or_by_symbol[sym] = evaluate_opening_range(m_bars, require_five_bars=False)

    cur_filename = f"alpaca_current_or_{PILOT_DATE}.json"
    cur_payload = {
        "metadata": {"stage": "phase_3_current_opening_range", "session_date": PILOT_DATE},
        "batches": current_or_raw_batches,
    }
    cur_bytes = json.dumps(cur_payload, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(cur_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {cur_filename}: "
            f"current {current_storage_bytes} + prospective {len(cur_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    (output_dir / cur_filename).write_bytes(cur_bytes)
    current_storage_bytes += len(cur_bytes)
    cur_hash = hash_bytes(cur_bytes)
    cur_size = len(cur_bytes)
    artifacts_info[cur_filename] = {
        "sha256": cur_hash,
        "size_bytes": cur_size,
        "description": "Raw Alpaca 09:30-09:34 opening range minute bars for session D",
        "record_count": sum(len(b["bars_by_symbol"]) for b in current_or_raw_batches),
    }

    surviving_needing_rv = [
        sym for sym in daily_base_qualified
        if sym in current_or_by_symbol
        and current_or_by_symbol[sym] is not None
        and current_or_by_symbol[sym].or_open > 5.0  # type: ignore[union-attr]
    ]

    prior_14_sessions = get_prior_xnys_sessions(target_dt, 14)
    prior_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {}
    prior_or_failures: set[str] = set()
    prior_raw_sessions_data: dict[str, list[dict[str, Any]]] = {}

    if surviving_needing_rv:
        rv_batches = batch_symbols(surviving_needing_rv, batch_size=batch_size)
        for sess_d in prior_14_sessions:
            sess_key = sess_d.isoformat()
            prior_raw_sessions_data[sess_key] = []
            p_start_utc = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
            p_end_utc = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

            for b_idx, batch in enumerate(rv_batches, start=1):
                remaining_pages = MAX_PILOT_PAGES_LIMIT - total_pages_used
                if remaining_pages <= 0:
                    raise RuntimeError(
                        f"Provider page budget exhausted before batch request: used {total_pages_used} >= limit {MAX_PILOT_PAGES_LIMIT}"
                    )
                call_max_pages = min(100, remaining_pages)
                dfs, meta = alpaca_client.get_bars(
                    batch,
                    start_utc=p_start_utc,
                    end_utc=p_end_utc,
                    feed="sip",
                    timeframe="1Min",
                    adjustment="raw",
                    asof=PILOT_DATE,
                    include_raw_bars=True,
                    include_raw_pages=True,
                    max_pages=call_max_pages,
                )
                alpaca_call_count += 1
                pages_fetched = meta.get("page_count", 1)
                alpaca_page_count += pages_fetched
                total_pages_used += pages_fetched
                if meta.get("safe_error_classification") == "max_pages_exceeded" or total_pages_used > MAX_PILOT_PAGES_LIMIT:
                    raise RuntimeError(
                        f"Provider page budget exceeded during batch request: {total_pages_used} > limit {MAX_PILOT_PAGES_LIMIT}"
                    )
                raw_bars = meta.get("raw_bars_by_symbol", {})

                batch_check = validate_provider_batch_response(
                    symbols_requested=batch,
                    meta=meta,
                    bars_by_symbol=raw_bars,
                    allowed_time_window=(time(9, 30), time(9, 34)),
                    session_date=sess_d,
                    require_raw_pages=True,
                )

                b_rec = {
                    "batch_index": b_idx,
                    "symbols_requested": batch,
                    "request_params": meta.get("request_params", {}),
                    "http_status": meta.get("http_status"),
                    "pagination_complete": meta.get("pagination_complete"),
                    "meta": {
                        "http_status": meta.get("http_status"),
                        "pagination_complete": meta.get("pagination_complete"),
                        "page_count": meta.get("page_count", 1),
                        "safe_error_classification": meta.get("safe_error_classification", "none"),
                        "repeated_page_token": meta.get("repeated_page_token", False),
                        "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                        "terminal_next_page_token_present": meta.get("terminal_next_page_token_present", False),
                        "unconsumed_page_token_present": meta.get("unconsumed_page_token_present", False),
                        "response_symbols": meta.get("response_symbols", []),
                        "malformed_timestamp_counts": meta.get("malformed_timestamp_counts", {}),
                        "token_hashes": meta.get("token_hashes", []),
                        "token_sequence_sha256": meta.get("token_sequence_sha256", ""),
                        "raw_pages": meta.get("raw_pages", []),
                    },
                    "bars_by_symbol": raw_bars,
                    "integrity_status": batch_check.status.value,
                }
                prior_raw_sessions_data[sess_key].append(b_rec)

                if not batch_check.is_valid:
                    prior_or_failures.update(batch)
                    continue

                for sym in batch:
                    df = dfs.get(sym, pd.DataFrame())
                    vol = float(df["volume"].sum()) if not df.empty else 0.0
                    prior_obs_by_symbol.setdefault(sym, []).append(
                        OpeningRangeVolumeObservation(symbol=sym, session_date=sess_d, volume=vol)
                    )

    prior_filename = f"alpaca_prior_or_14sessions_{PILOT_DATE}.json"
    prior_payload = {
        "metadata": {"stage": "phase_3_prior_14_sessions_opening_range", "target_session": PILOT_DATE},
        "sessions_data": prior_raw_sessions_data,
    }
    p_bytes = json.dumps(prior_payload, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(p_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {prior_filename}: "
            f"current {current_storage_bytes} + prospective {len(p_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    (output_dir / prior_filename).write_bytes(p_bytes)
    current_storage_bytes += len(p_bytes)
    artifacts_info[prior_filename] = {
        "sha256": hash_bytes(p_bytes),
        "size_bytes": len(p_bytes),
        "description": "Raw Alpaca 14 prior sessions opening range minute bars",
        "record_count": sum(len(bl) for bl in prior_raw_sessions_data.values()),
    }

    # Resource check after Phase 3
    current_storage_bytes = sum(f.stat().st_size for f in output_dir.glob("*") if f.is_file())
    check_resource_limits(
        page_count=massive_page_count + alpaca_page_count,
        storage_bytes=current_storage_bytes,
    )

    (
        screening_audit,
        _outcomes,
        eligible_candidates,
        surviving_ors,
    ) = audit_candidate_screening(
        daily_base_qualified_symbols=daily_base_qualified,
        current_or_by_symbol=current_or_by_symbol,
        current_or_provider_failures=current_or_failures,
        prior_or_obs_by_symbol=prior_obs_by_symbol,
        prior_or_provider_failures=prior_or_failures,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        price_min=5.0,
        adv_min=1_000_000.0,
        atr_min=0.50,
        rv_min=1.0,
        gate_threshold=CANDIDATE_SCREENING_GATE_THRESHOLD,
    )

    # -------------------------------------------------------------------------
    # PHASE 4: Freeze Top-20 Selection
    # -------------------------------------------------------------------------
    ranked_candidates = rank_and_select_top_20(
        candidates=eligible_candidates,
        opening_ranges=surviving_ors,
        session_start_equity=25000.0,
        top_n=20,
    )
    (
        selection_evidence,
        selection_records,
        _selected_syms,
    ) = freeze_top_20_selection(ranked_candidates)

    sel_filename = f"top_20_selection_{PILOT_DATE}.json"
    sel_bytes = json.dumps({
        "date": PILOT_DATE,
        "selection_sha256": selection_evidence.selection_sha256,
        "selected_count": selection_evidence.selected_count,
        "doji_count": selection_evidence.doji_count,
        "eligible_candidates_count": selection_evidence.eligible_candidates_count,
        "records": selection_records,
    }, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(sel_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {sel_filename}: "
            f"current {current_storage_bytes} + prospective {len(sel_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    (output_dir / sel_filename).write_bytes(sel_bytes)
    current_storage_bytes += len(sel_bytes)
    artifacts_info[sel_filename] = {
        "sha256": hash_bytes(sel_bytes),
        "size_bytes": len(sel_bytes),
        "description": "Frozen Top-20 selection records and cryptographic hash",
        "record_count": len(selection_records),
    }

    # -------------------------------------------------------------------------
    # PHASE 5: Stage B (09:35–15:59 ET) for Actionable Symbols
    # -------------------------------------------------------------------------
    actionable_symbols = [
        r["symbol"] for r in selection_records if r["order_intent_status"] != "NO_ORDER"
    ]
    stage_b_bars_by_symbol: dict[str, list[MinuteBar]] = {}
    stage_b_failures: set[str] = set()
    stage_b_raw_batches: list[dict[str, Any]] = []

    if actionable_symbols:
        b_start_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 35, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
        b_end_utc = datetime(target_dt.year, target_dt.month, target_dt.day, 15, 59, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
        b_batches = batch_symbols(actionable_symbols, batch_size=batch_size)

        for b_idx, batch in enumerate(b_batches, start=1):
            remaining_pages = MAX_PILOT_PAGES_LIMIT - total_pages_used
            if remaining_pages <= 0:
                raise RuntimeError(
                    f"Provider page budget exhausted before batch request: used {total_pages_used} >= limit {MAX_PILOT_PAGES_LIMIT}"
                )
            call_max_pages = min(100, remaining_pages)
            dfs, meta = alpaca_client.get_bars(
                batch,
                start_utc=b_start_utc,
                end_utc=b_end_utc,
                feed="sip",
                timeframe="1Min",
                adjustment="raw",
                asof=PILOT_DATE,
                include_raw_bars=True,
                include_raw_pages=True,
                max_pages=call_max_pages,
            )
            alpaca_call_count += 1
            pages_fetched = meta.get("page_count", 1)
            alpaca_page_count += pages_fetched
            total_pages_used += pages_fetched
            if meta.get("safe_error_classification") == "max_pages_exceeded" or total_pages_used > MAX_PILOT_PAGES_LIMIT:
                raise RuntimeError(
                    f"Provider page budget exceeded during batch request: {total_pages_used} > limit {MAX_PILOT_PAGES_LIMIT}"
                )
            raw_bars = meta.get("raw_bars_by_symbol", {})

            batch_check = validate_provider_batch_response(
                symbols_requested=batch,
                meta=meta,
                bars_by_symbol=raw_bars,
                allowed_time_window=(time(9, 35), time(15, 59)),
                session_date=target_dt,
                require_raw_pages=True,
            )

            b_rec = {
                "batch_index": b_idx,
                "symbols_requested": batch,
                "request_params": meta.get("request_params", {}),
                "http_status": meta.get("http_status"),
                "pagination_complete": meta.get("pagination_complete"),
                "meta": {
                    "http_status": meta.get("http_status"),
                    "pagination_complete": meta.get("pagination_complete"),
                    "page_count": meta.get("page_count", 1),
                    "safe_error_classification": meta.get("safe_error_classification", "none"),
                    "repeated_page_token": meta.get("repeated_page_token", False),
                    "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                    "terminal_next_page_token_present": meta.get("terminal_next_page_token_present", False),
                    "unconsumed_page_token_present": meta.get("unconsumed_page_token_present", False),
                    "response_symbols": meta.get("response_symbols", []),
                    "malformed_timestamp_counts": meta.get("malformed_timestamp_counts", {}),
                    "token_hashes": meta.get("token_hashes", []),
                    "token_sequence_sha256": meta.get("token_sequence_sha256", ""),
                    "raw_pages": meta.get("raw_pages", []),
                },
                "bars_by_symbol": raw_bars,
                "integrity_status": batch_check.status.value,
            }
            stage_b_raw_batches.append(b_rec)

            if not batch_check.is_valid:
                stage_b_failures.update(batch)
                continue

            for sym in batch:
                df = dfs.get(sym, pd.DataFrame())
                m_bars = []
                for ts, row in df.iterrows():
                    m_bars.append(MinuteBar(
                        symbol=sym,
                        timestamp=ts,
                        session_date=target_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
                stage_b_bars_by_symbol[sym] = m_bars

    sb_filename = f"alpaca_stage_b_{PILOT_DATE}.json"
    sb_payload = {
        "metadata": {"stage": "phase_5_stage_b_minute_bars", "session_date": PILOT_DATE},
        "batches": stage_b_raw_batches,
    }
    sb_bytes = json.dumps(sb_payload, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(sb_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing {sb_filename}: "
            f"current {current_storage_bytes} + prospective {len(sb_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    (output_dir / sb_filename).write_bytes(sb_bytes)
    current_storage_bytes += len(sb_bytes)
    sb_hash = hash_bytes(sb_bytes)
    sb_size = len(sb_bytes)
    artifacts_info[sb_filename] = {
        "sha256": sb_hash,
        "size_bytes": sb_size,
        "description": "Raw Alpaca Stage-B minute bars for actionable selected symbols",
        "record_count": sum(len(b["bars_by_symbol"]) for b in stage_b_raw_batches),
    }

    stage_b_audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=actionable_symbols,
        stage_b_bars_by_symbol=stage_b_bars_by_symbol,
        stage_b_provider_failures=stage_b_failures,
        expected_minutes=385,
        session_date=target_dt,
    )

    # -------------------------------------------------------------------------
    # Include Durable Run Lock Marker in Manifest
    # -------------------------------------------------------------------------
    lock_bytes = lock_marker_path.read_bytes()
    artifacts_info[lock_marker_path.name] = {
        "sha256": hash_bytes(lock_bytes),
        "size_bytes": len(lock_bytes),
        "description": "Durable atomic pilot run-start lock marker",
        "record_count": 1,
    }

    # -------------------------------------------------------------------------
    # Save Checksum Manifest
    # -------------------------------------------------------------------------
    manifest_data = {
        "schema_version": "1.0",
        "task_id": TASK_ID,
        "date": PILOT_DATE,
        "created_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "artifacts": artifacts_info,
    }
    manifest_bytes = json.dumps(manifest_data, indent=2, sort_keys=True).encode("utf-8")
    if current_storage_bytes + len(manifest_bytes) > MAX_PILOT_STORAGE_BYTES_LIMIT:
        raise RuntimeError(
            f"Storage ceiling exceeded before writing manifest_{PILOT_DATE}.json: "
            f"current {current_storage_bytes} + prospective {len(manifest_bytes)} > limit {MAX_PILOT_STORAGE_BYTES_LIMIT}"
        )
    _manifest_path, manifest_hash = create_and_save_manifest(output_dir, artifacts_info, PILOT_DATE)
    current_storage_bytes += len(manifest_bytes)

    # -------------------------------------------------------------------------
    # PHASE 6: Final Pilot Disposition
    # -------------------------------------------------------------------------
    provider_data_integrity_success = (
        len(daily_provider_failures) == 0
        and len(current_or_failures) == 0
        and len(prior_or_failures) == 0
        and stage_b_audit.provider_failure_count == 0
        and stage_b_audit.integrity_failure_count == 0
    )

    disposition, blockers = determine_pilot_disposition_corr_003(
        reference_success=True,
        provider_access_success=True,
        provider_data_integrity_success=provider_data_integrity_success,
        candidate_screening_gate_passed=screening_audit.meets_screening_gate,
        eligible_candidate_count=screening_audit.eligible_candidate_count,
        stage_b_path_usable=stage_b_audit.is_usable,
    )

    elapsed = time.time() - t0
    private_storage_bytes = sum(f.stat().st_size for f in output_dir.glob("*") if f.is_file())

    _write_safe_public_report(
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
        manifest_sha256=manifest_hash,
    )

    print("\n" + "=" * 80)
    print(f"FINAL PILOT DISPOSITION: {disposition.value}")
    print(f"Manifest Hash: {manifest_hash}")
    print(f"Total Runtime: {elapsed:.2f}s, Alpaca Pages: {alpaca_page_count}, Storage: {private_storage_bytes:,} bytes")
    print("=" * 80)

    return 0 if disposition == PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="DAYTRADE-003D-CORR-003 Pilot and Replay CLI")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Replay subcommand
    replay_parser = subparsers.add_parser("replay", help="Deterministic offline replay without network or credentials")
    replay_parser.add_argument("--input-dir", type=Path, default=DEFAULT_PRIVATE_ROOT, help="Private raw storage root")
    replay_parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root path")
    replay_parser.add_argument("--date", type=str, default=PILOT_DATE, help="Pilot date to replay")

    # Pilot subcommand
    pilot_parser = subparsers.add_parser("pilot", help="Bounded live pilot (gated pending Gary Yang authorization)")
    pilot_parser.add_argument("--output-dir", type=Path, default=DEFAULT_PRIVATE_ROOT, help="Private storage root")
    pilot_parser.add_argument("--pre-live-sha", type=str, required=True, help="Pre-live frozen commit SHA")
    pilot_parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root path")
    pilot_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for provider requests")
    pilot_parser.add_argument("--authorize-live", action="store_true", help="Authorize bounded live pilot")

    args = parser.parse_args()

    if args.subcommand == "replay":
        try:
            print("=" * 80)
            print(f"STARTING OFFLINE REPLAY: {TASK_ID} ({args.date})")
            print(f"Input Directory: {args.input_dir}")
            print("=" * 80)
            res = replay_corr_003_pilot(input_dir=args.input_dir, repo_root=args.repo_root, pilot_date=args.date)
            print(f"[REPLAY SUCCESS] Manifest SHA: {res.manifest_sha256}")
            print(f"  -> Canonical target universe: {res.target_audit.canonical_target_universe_count:,}")
            print(f"  -> Daily computable symbols:  {res.daily_audit.daily_computable_count:,}")
            print(f"  -> Daily base qualified:      {res.daily_audit.daily_base_qualified_count:,}")
            print(f"  -> Screening completeness:    {res.screening_audit.screening_completeness_pct:.2f}% (meets gate: {res.screening_audit.meets_screening_gate})")
            print(f"  -> Eligible candidates:       {res.screening_audit.eligible_candidate_count:,}")
            print(f"  -> Top-20 selection hash:     {res.selection_evidence.selection_sha256}")
            print(f"  -> Stage-B actual bars:       {res.stage_b_audit.total_actual_bars:,}")
            print(f"  -> Stage-B sparse minutes:    {res.stage_b_audit.total_sparse_minutes:,}")
            print(f"  -> Missing 15:59 EOD bars:    {res.stage_b_audit.missing_eod_bar_symbols_count:,}")
            print(f"  -> Stage-B usability:         {'USABLE' if res.stage_b_audit.is_usable else 'UNUSABLE'}")
            print(f"  -> Final Disposition:         {res.disposition.value}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"[REPLAY FAILED] {exc}")
            return 1

    if args.subcommand == "pilot":
        try:
            validate_batch_size(args.batch_size)
        except ValueError as exc:
            print(f"[FATAL] Invalid batch size: {exc}")
            return 1
        return run_corr_003_live_pilot(
            output_dir=args.output_dir,
            pre_live_commit_sha=args.pre_live_sha,
            repo_root=args.repo_root,
            batch_size=args.batch_size,
            authorized_by_gary=args.authorize_live,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
