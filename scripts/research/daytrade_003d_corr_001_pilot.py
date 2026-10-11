"""Executable CLI for DAYTRADE-003D-CORR-001 corrected Jan-2 ORB data feasibility pilot.

Usage:
    # 1. Pre-live checklist / offline verification:
    uv run python scripts/research/daytrade_003d_corr_001_pilot.py --pre-live-check

    # 2. Bounded live pilot execution:
    uv run python scripts/research/daytrade_003d_corr_001_pilot.py --run-live-pilot
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tradex.market.hours import get_market_session
from tradex.research.daytrade_orb.corrected_pilot import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRIVATE_ROOT,
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    LOCKED_003D_SPEC_PATH,
    LOCKED_003D_SPEC_SHA256,
    MAX_PILOT_PAGES_LIMIT,
    MAX_PILOT_STORAGE_BYTES_LIMIT,
    PILOT_DATE,
    STAGE_A_COVERAGE_THRESHOLD,
    TARGET_EXCHANGE_MAPPING,
    TASK_ID,
    CorrectedStageASelectionEvidence,
    CorrectedStageBAuditEvidence,
    PilotDisposition,
    StageACoverageAudit,
    TargetUniverseAudit,
    audit_corrected_stage_b_path,
    audit_stage_a_coverage,
    batch_symbols,
    calculate_corrected_resource_plan,
    compute_and_freeze_corrected_stage_a_selection,
    filter_and_audit_target_universe,
    hash_bytes,
    verify_all_upstream_spec_hashes,
    write_pilot_summary_artifact,
)
from tradex.research.daytrade_orb.data_feasibility import load_probe_credentials
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import (
    DailyBar,
    MinuteBar,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.ranking import evaluate_opening_range
from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient
from tradex.research.intraday_dataset.massive_client import MassiveDatasetClient

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "docs" / "research" / "artifacts" / "DAYTRADE-003D-CORR-001"
SPEC_CORR_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-003D-CORR-001-v1.json"
MARKET_TIMEZONE = ZoneInfo("America/New_York")


def _get_git_commit(ref: str = "HEAD") -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", ref],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _get_git_status() -> str:
    try:
        return subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def run_pre_live_check(dotenv_path: str | None = None) -> int:
    """Run comprehensive pre-live verification checklist before live provider calls."""
    print("=" * 80)
    print("DAYTRADE-003D-CORR-001 PRE-LIVE CHECKLIST VERIFICATION")
    print("=" * 80)

    # 1. Spec hashes
    valid_specs, actual_hashes, _spec_errors = verify_all_upstream_spec_hashes(REPO_ROOT)
    print(f"[1] 003B Spec Hash ({LOCKED_003B_SPEC_PATH}):")
    print(f"    Expected: {LOCKED_003B_SPEC_SHA256}")
    print(f"    Actual:   {actual_hashes.get(LOCKED_003B_SPEC_PATH, '')} -> {'MATCH' if actual_hashes.get(LOCKED_003B_SPEC_PATH) == LOCKED_003B_SPEC_SHA256 else 'MISMATCH'}")
    print(f"[2] 003C Resolution Hash ({LOCKED_003C_RESOLUTION_PATH}):")
    print(f"    Expected: {LOCKED_003C_RESOLUTION_SHA256}")
    print(f"    Actual:   {actual_hashes.get(LOCKED_003C_RESOLUTION_PATH, '')} -> {'MATCH' if actual_hashes.get(LOCKED_003C_RESOLUTION_PATH) == LOCKED_003C_RESOLUTION_SHA256 else 'MISMATCH'}")
    print(f"[3] 003D Spec Hash ({LOCKED_003D_SPEC_PATH}):")
    print(f"    Expected: {LOCKED_003D_SPEC_SHA256}")
    print(f"    Actual:   {actual_hashes.get(LOCKED_003D_SPEC_PATH, '')} -> {'MATCH' if actual_hashes.get(LOCKED_003D_SPEC_PATH) == LOCKED_003D_SPEC_SHA256 else 'MISMATCH'}")

    if SPEC_CORR_PATH.exists():
        sha_corr = hash_bytes(SPEC_CORR_PATH.read_bytes())
        print(f"[4] CORR-001 Spec Hash ({SPEC_CORR_PATH.name}): {sha_corr}")
    else:
        sha_corr = "NOT_YET_CREATED"
        print(f"[4] CORR-001 Spec Hash: {sha_corr}")

    # 2. Git status
    head_sha = _get_git_commit("HEAD")
    main_sha = _get_git_commit("origin/main")
    status = _get_git_status()
    print(f"[5] Git HEAD:        {head_sha}")
    print(f"[6] Git origin/main: {main_sha}")
    print(f"[7] Worktree clean:  {'YES' if status == '' else 'DIRTY'}")

    # 3. Calendar check
    print(f"[8] Fixed pilot date verification on XNYS calendar ({PILOT_DATE}):")
    dt = date.fromisoformat(PILOT_DATE)
    sess = get_market_session(dt)
    is_full = sess is not None and not sess.is_early_close
    print(f"    is_session={sess is not None}, is_early_close={getattr(sess, 'is_early_close', None)}, opens={getattr(sess, 'opens_at', None)}, closes={getattr(sess, 'closes_at', None)}")

    # 4. Strategy registry check
    from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

    reg_empty = len(APPROVED_PRODUCTION_STRATEGIES) == 0
    print(f"[9] Production strategy registry empty: {reg_empty} ({APPROVED_PRODUCTION_STRATEGIES})")

    # 5. Resource bounds
    plan = calculate_corrected_resource_plan(
        universe_size=8000,
        batch_size=DEFAULT_BATCH_SIZE,
        massive_pages_actual=12,
        max_pages_limit=MAX_PILOT_PAGES_LIMIT,
        max_storage_bytes_limit=MAX_PILOT_STORAGE_BYTES_LIMIT,
    )
    print(f"[10] Runaway guards: max_pages={plan.max_pages_limit}, max_storage={plan.max_storage_bytes_limit / (1024*1024):.0f} MB")
    print(f"     Projected pilot pages (N=8000, B=100): {plan.total_planned_pages} <= {plan.max_pages_limit}")
    print(f"     Is within bounds: {plan.is_within_bounds}")

    # Summary
    all_ok = valid_specs and (status == "") and is_full and reg_empty and plan.is_within_bounds
    print("=" * 80)
    print(f"PRE-LIVE CHECK RESULT: {'PASS' if all_ok else 'FAIL'}")
    print("=" * 80)
    return 0 if all_ok else 1


def run_live_pilot(
    output_dir: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dotenv_path: str | None = None,
    alpaca_request_delay: float = 0.05,
) -> int:
    """Execute the bounded 2024-01-02 ORB real-data feasibility pilot."""
    t0 = time.time()
    print("=" * 80)
    print("DAYTRADE-003D-CORR-001 BOUNDED 2024-01-02 LIVE PILOT EXECUTION")
    print("=" * 80)

    pre_live_commit_sha = _get_git_commit("HEAD")
    output_dir.mkdir(parents=True, exist_ok=True)

    massive_key, alpaca_key, alpaca_secret = load_probe_credentials(dotenv_path)
    if not (massive_key and alpaca_key and alpaca_secret):
        print("[FATAL] Missing provider API credentials in environment or .env!")
        return 1

    massive_client = MassiveDatasetClient(massive_key)
    alpaca_client = DatasetAlpacaClient(
        alpaca_key,
        alpaca_secret,
        request_delay_seconds=alpaca_request_delay,
    )

    disposition = PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET
    blocker_details: list[str] = []

    massive_page_count = 0
    massive_row_count = 0
    massive_snapshot_hash = ""

    target_audit: TargetUniverseAudit | None = None
    coverage_audit: StageACoverageAudit | None = None
    selection_evidence: CorrectedStageASelectionEvidence | None = None
    stage_b_audit: CorrectedStageBAuditEvidence | None = None

    alpaca_call_count = 0
    alpaca_page_count = 0
    alpaca_retry_count = 0

    # -------------------------------------------------------------------------
    # STEP 1: Massive Jan-2 PIT Universe Snapshot
    # -------------------------------------------------------------------------
    print(f"\n[STEP 1] Fetching Massive PIT snapshot for {PILOT_DATE} (active=true, limit=1000)...")
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

        print(f"  -> Snapshot complete: rows={obs.row_count}, pages={obs.page_count}, terminal={obs.pagination_complete}, hash={obs.raw_sha256[:16]}...")

        if not obs.pagination_complete or obs.error:
            print(f"  [FATAL] Massive snapshot did not reach terminal pagination: {obs.error}")
            disposition = PilotDisposition.BLOCKED_MASSIVE_REFERENCE
            blocker_details.append(f"Massive terminal pagination failure: {obs.error}")
            _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
            return 1

        # Perform corrected universe filtering and duplicate handling
        target_audit, _target_rows_map = filter_and_audit_target_universe(
            snap.rows, allowed_exchanges=TARGET_EXCHANGE_MAPPING
        )
        print(f"  -> Target filtered rows:              {target_audit.target_filtered_rows}")
        print(f"  -> Canonical target universe count:   {target_audit.canonical_target_universe_count}")
        print(f"  -> Valid candidate symbols to query:  {len(target_audit.valid_target_symbols)}")
        print(f"  -> Ambiguous identity symbols:        {len(target_audit.ambiguous_symbols)}")
        print(f"  -> Collapsed duplicates count:        {target_audit.collapsed_duplicates_count}")
        print(f"  -> Exchanges: {target_audit.target_exchange_distribution}")
        print(f"  -> Types:     {dict(list(target_audit.type_distribution.items())[:6])}")

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
        print(f"  [FATAL] Exception during Massive Jan-2 snapshot: {exc}")
        disposition = PilotDisposition.BLOCKED_MASSIVE_REFERENCE
        blocker_details.append(f"Massive snapshot exception: {exc}")
        _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
        return 1

    # -------------------------------------------------------------------------
    # STEP 2: Alpaca Batch Capability Test
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Alpaca 100-symbol batch capability test...")
    try:
        test_batch = target_audit.valid_target_symbols[:batch_size]
        t_cap_start = datetime(2023, 12, 29, 0, 0, tzinfo=UTC)
        t_cap_end = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)

        cap_dfs, cap_meta = alpaca_client.get_bars(
            test_batch,
            start_utc=t_cap_start,
            end_utc=t_cap_end,
            feed="sip",
            timeframe="1Day",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        alpaca_call_count += 1
        alpaca_page_count += cap_meta.get("page_count", 1)

        http_status = cap_meta.get("http_status")
        returned_syms = len([s for s, df in cap_dfs.items() if not df.empty])
        print(f"  -> Capability batch of {len(test_batch)} symbols: HTTP {http_status}, returned bars for {returned_syms} symbols")

        if http_status != 200 or returned_syms == 0:
            print("  [FATAL] Alpaca batch capability request failed or returned 0 symbols!")
            disposition = PilotDisposition.BLOCKED_PROVIDER_BATCH_CAPABILITY
            blocker_details.append(f"Batch request returned status {http_status}, valid symbols {returned_syms}")
            _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
            return 1

        print("  -> Provider batch capability VERIFIED.")

    except Exception as exc:  # noqa: BLE001
        print(f"  [FATAL] Alpaca batch capability exception: {exc}")
        disposition = PilotDisposition.BLOCKED_PROVIDER_BATCH_CAPABILITY
        blocker_details.append(f"Batch capability exception: {exc}")
        _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
        return 1

    # -------------------------------------------------------------------------
    # STEP 3: Acquire Jan-2 Stage A
    # -------------------------------------------------------------------------
    print(f"\n[STEP 3] Acquiring Stage A across {len(target_audit.valid_target_symbols)} symbols in batches of {batch_size}...")
    valid_symbols = target_audit.valid_target_symbols
    symbol_batches = batch_symbols(valid_symbols, batch_size=batch_size)

    # Lookback sessions on XNYS calendar
    target_dt = date.fromisoformat(PILOT_DATE)
    prior_14_sessions = get_prior_xnys_sessions(target_dt, 14)
    daily_lookback_sessions = get_prior_xnys_sessions(target_dt, 20)
    print(f"  -> Daily lookback sessions: {len(daily_lookback_sessions)} ({daily_lookback_sessions[0]} to {daily_lookback_sessions[-1]})")
    print(f"  -> Prior OR sessions:       {len(prior_14_sessions)} ({prior_14_sessions[0]} to {prior_14_sessions[-1]})")

    # Safety check on total projected pages
    total_projected_pages = (
        massive_page_count
        + len(symbol_batches)  # daily
        + (len(symbol_batches) * (len(prior_14_sessions) + 1))  # OR
        + 1  # stage B
    )
    print(f"  -> Total planned HTTP pages: {total_projected_pages} (runaway safety limit: {MAX_PILOT_PAGES_LIMIT})")
    if total_projected_pages > MAX_PILOT_PAGES_LIMIT:
        print(f"  [FATAL] Planned pages exceed runaway safety limit of {MAX_PILOT_PAGES_LIMIT}!")
        disposition = PilotDisposition.INVALID_CORRECTED_PROBE_IMPLEMENTATION
        blocker_details.append(f"Planned pages ({total_projected_pages}) > {MAX_PILOT_PAGES_LIMIT}")
        _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
        return 1

    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {}
    current_or_by_symbol: dict[str, Any] = {}

    # 3A. Acquire Daily Bars
    print("  [3A] Fetching daily bars (20 sessions in Dec 2023)...")
    d_start_utc = datetime(2023, 12, 1, 0, 0, tzinfo=UTC)
    d_end_utc = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)

    for b_idx, batch in enumerate(symbol_batches, start=1):
        if b_idx % 10 == 0 or b_idx == len(symbol_batches):
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
            bars = []
            if not df.empty:
                for ts, row in df.iterrows():
                    ny_dt = ts.astimezone(MARKET_TIMEZONE)
                    sess_d = ny_dt.date()
                    if sess_d >= target_dt:
                        continue
                    bars.append(DailyBar(
                        symbol=sym,
                        session_date=sess_d,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ))
            daily_bars_by_symbol[sym] = bars

    # 3B. Acquire Prior 14 Opening Ranges
    print("  [3B] Fetching prior 14 opening-range windows (09:30-09:34 ET)...")
    for s_idx, sess_d in enumerate(prior_14_sessions, start=1):
        if s_idx % 5 == 0 or s_idx == len(prior_14_sessions):
            print(f"    Fetching prior OR session {s_idx}/14 ({sess_d})...")

        or_start = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
        or_end = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

        for batch in symbol_batches:
            dfs, meta = alpaca_client.get_bars(
                batch,
                start_utc=or_start,
                end_utc=or_end,
                feed="sip",
                timeframe="1Min",
                adjustment="raw",
                asof=PILOT_DATE,
            )
            alpaca_call_count += 1
            alpaca_page_count += meta.get("page_count", 1)

            for sym, df in dfs.items():
                if not df.empty and len(df) == 5:
                    tot_vol = float(df["volume"].sum())
                    prior_or_obs_by_symbol.setdefault(sym, []).append(
                        OpeningRangeVolumeObservation(
                            symbol=sym,
                            session_date=sess_d,
                            volume=tot_vol,
                        )
                    )

    # 3C. Acquire Current Opening Range (2024-01-02 09:30-09:34 ET)
    print("  [3C] Fetching 2024-01-02 current opening-range window (09:30-09:34 ET)...")
    c_start = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    c_end = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    for batch in symbol_batches:
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=c_start,
            end_utc=c_end,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        alpaca_call_count += 1
        alpaca_page_count += meta.get("page_count", 1)

        for sym, df in dfs.items():
            if not df.empty and len(df) == 5:
                # 5 minute bars
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
                current_or_by_symbol[sym] = evaluate_opening_range(minute_bars)

    # -------------------------------------------------------------------------
    # STEP 4: Measure Actual Stage-A Coverage
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Auditing Stage-A candidate computability and coverage gate...")
    coverage_audit, _unavailable_reasons, computable_symbols = audit_stage_a_coverage(
        valid_target_symbols=target_audit.valid_target_symbols,
        ambiguous_symbols=target_audit.ambiguous_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_obs_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=target_dt,
        required_lookback=14,
        coverage_threshold=STAGE_A_COVERAGE_THRESHOLD,
    )
    print(f"  -> Canonical target universe count: {coverage_audit.canonical_target_universe_count}")
    print(f"  -> Computable Stage-A symbols:       {coverage_audit.computable_stage_a_symbols_count}")
    print(f"  -> Actual Stage-A coverage:          {coverage_audit.stage_a_coverage_pct:.2f}% (threshold: {coverage_audit.coverage_threshold_pct}%)")
    print(f"  -> Meets coverage threshold:         {coverage_audit.meets_coverage_threshold}")
    print(f"  -> Unavailable reasons breakdown:    {coverage_audit.unavailable_counts_by_reason}")

    if not coverage_audit.meets_coverage_threshold:
        print(f"  [STOP] Stage-A coverage ({coverage_audit.stage_a_coverage_pct:.2f}%) < 95.0% threshold!")
        disposition = PilotDisposition.BLOCKED_STAGE_A_COVERAGE
        blocker_details.append(
            f"Stage-A coverage {coverage_audit.stage_a_coverage_pct:.2f}% is below 95.0% threshold"
        )
        _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
        return 1

    # -------------------------------------------------------------------------
    # STEP 5: Freeze Top-20 Selection
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Applying locked ORB filters and freezing Top-20 selection...")
    selection_evidence, selection_records, _selected_symbols = compute_and_freeze_corrected_stage_a_selection(
        computable_symbols=computable_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_obs_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=target_dt,
        session_start_equity=25000.0,
        top_n=20,
    )
    print(f"  -> Eligible candidates:  {selection_evidence.eligible_candidates_count}")
    print(f"  -> Top-20 selected count: {selection_evidence.selected_count}")
    print(f"  -> Doji count:            {selection_evidence.doji_count}")
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
    print(f"  -> Top-20 selection frozen and saved privately: {private_sel_path.name}")

    # -------------------------------------------------------------------------
    # STEP 6: Acquire Stage B
    # -------------------------------------------------------------------------
    # Filter for selected symbols requiring execution path (non-doji)
    active_selected_symbols = [
        r["symbol"] for r in selection_records if r["order_intent_status"] != "NO_ORDER"
    ]
    print(f"\n[STEP 6] Acquiring Stage B (09:35..15:59 ET) for {len(active_selected_symbols)} non-doji selected symbols...")

    b_start = datetime(target_dt.year, target_dt.month, target_dt.day, 9, 35, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    b_end = datetime(target_dt.year, target_dt.month, target_dt.day, 15, 59, 59, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    stage_b_bars_by_sym: dict[str, list[MinuteBar]] = {}
    if active_selected_symbols:
        dfs, meta = alpaca_client.get_bars(
            active_selected_symbols,
            start_utc=b_start,
            end_utc=b_end,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        alpaca_call_count += 1
        alpaca_page_count += meta.get("page_count", 1)

        for sym, df in dfs.items():
            bars = []
            if not df.empty:
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
            stage_b_bars_by_sym[sym] = bars

    stage_b_audit, _missing_minutes_by_sym = audit_corrected_stage_b_path(
        selected_symbols=active_selected_symbols,
        bars_by_symbol=stage_b_bars_by_sym,
        target_session=target_dt,
    )
    print(f"  -> Expected minutes per symbol: {stage_b_audit.expected_minutes_per_symbol}")
    print(f"  -> Total expected bars:         {stage_b_audit.total_expected_bars}")
    print(f"  -> Total observed bars:         {stage_b_audit.total_observed_bars}")
    print(f"  -> Missing minutes count:       {stage_b_audit.missing_minutes_count}")
    print(f"  -> Path complete:               {stage_b_audit.path_complete}")

    if not stage_b_audit.path_complete:
        print("  [FATAL] Stage B path incomplete for selected symbols!")
        disposition = PilotDisposition.BLOCKED_STAGE_B_COVERAGE
        blocker_details.append(
            f"Stage-B missing {stage_b_audit.missing_minutes_count} minutes across active selected symbols"
        )
        _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
        return 1

    # If we made it here, pilot is completely feasible!
    disposition = PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET
    print("\n[SUCCESS] 2024-01-02 pilot feasibility fully proven!")
    _finalize(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, massive_page_count, massive_row_count, massive_snapshot_hash, target_audit, coverage_audit, selection_evidence, stage_b_audit, alpaca_call_count, alpaca_page_count, alpaca_retry_count)
    return 0


def _finalize(
    output_dir: Path,
    disposition: PilotDisposition,
    blocker_details: list[str],
    pre_live_commit_sha: str,
    t0: float,
    massive_page_count: int,
    massive_row_count: int,
    massive_snapshot_hash: str,
    target_audit: TargetUniverseAudit | None,
    coverage_audit: StageACoverageAudit | None,
    selection_evidence: CorrectedStageASelectionEvidence | None,
    stage_b_audit: CorrectedStageBAuditEvidence | None,
    alpaca_call_count: int,
    alpaca_page_count: int,
    alpaca_retry_count: int,
) -> None:
    total_elapsed = round(time.time() - t0, 2)

    # Compute private storage bytes
    private_storage_bytes = 0
    if output_dir.exists():
        for p in output_dir.rglob("*"):
            if p.is_file():
                private_storage_bytes += p.stat().st_size

    corr_spec_hash = hash_bytes(SPEC_CORR_PATH.read_bytes()) if SPEC_CORR_PATH.exists() else ""

    summary = {
        "task_id": TASK_ID,
        "pilot_date": PILOT_DATE,
        "final_pilot_disposition": disposition.value,
        "blocker_details": blocker_details,
        "pre_live_commit_sha": pre_live_commit_sha,
        "upstream_spec_hashes": {
            "daytrade_003b": LOCKED_003B_SPEC_SHA256,
            "daytrade_003c": LOCKED_003C_RESOLUTION_SHA256,
            "daytrade_003d": LOCKED_003D_SPEC_SHA256,
            "daytrade_003d_corr_001": corr_spec_hash,
        },
        "massive_reference": {
            "pilot_date": PILOT_DATE,
            "page_count": massive_page_count,
            "row_count": massive_row_count,
            "snapshot_sha256": massive_snapshot_hash,
        },
        "pilot_universe": {
            "date": PILOT_DATE,
            "canonical_target_universe_count": target_audit.canonical_target_universe_count if target_audit else 0,
            "target_filtered_rows": target_audit.target_filtered_rows if target_audit else 0,
            "valid_target_symbols_count": len(target_audit.valid_target_symbols) if target_audit else 0,
            "ambiguous_duplicate_count": len(target_audit.ambiguous_symbols) if target_audit else 0,
            "collapsed_duplicates_count": target_audit.collapsed_duplicates_count if target_audit else 0,
            "universe_sha256": target_audit.universe_sha256 if target_audit else "",
            "target_exchange_distribution": target_audit.target_exchange_distribution if target_audit else {},
            "type_distribution": target_audit.type_distribution if target_audit else {},
        },
        "stage_a_coverage": {
            "canonical_target_universe_count": coverage_audit.canonical_target_universe_count if coverage_audit else 0,
            "computable_stage_a_symbols_count": coverage_audit.computable_stage_a_symbols_count if coverage_audit else 0,
            "stage_a_coverage_pct": coverage_audit.stage_a_coverage_pct if coverage_audit else 0.0,
            "coverage_threshold_pct": coverage_audit.coverage_threshold_pct if coverage_audit else 95.0,
            "meets_coverage_threshold": coverage_audit.meets_coverage_threshold if coverage_audit else False,
            "unavailable_counts_by_reason": coverage_audit.unavailable_counts_by_reason if coverage_audit else {},
        },
        "stage_a_selection": {
            "eligible_candidates_count": selection_evidence.eligible_candidates_count if selection_evidence else 0,
            "selected_count": selection_evidence.selected_count if selection_evidence else 0,
            "selection_sha256": selection_evidence.selection_sha256 if selection_evidence else "",
            "doji_count": selection_evidence.doji_count if selection_evidence else 0,
        },
        "stage_b_path": {
            "symbols_count": stage_b_audit.symbols_count if stage_b_audit else 0,
            "expected_minutes_per_symbol": stage_b_audit.expected_minutes_per_symbol if stage_b_audit else 0,
            "total_expected_bars": stage_b_audit.total_expected_bars if stage_b_audit else 0,
            "total_observed_bars": stage_b_audit.total_observed_bars if stage_b_audit else 0,
            "missing_minutes_count": stage_b_audit.missing_minutes_count if stage_b_audit else 0,
            "duplicate_minutes_count": stage_b_audit.duplicate_minutes_count if stage_b_audit else 0,
            "malformed_bars_count": stage_b_audit.malformed_bars_count if stage_b_audit else 0,
            "path_complete": stage_b_audit.path_complete if stage_b_audit else False,
        },
        "alpaca_provider_metrics": {
            "calls_count": alpaca_call_count,
            "pages_count": alpaca_page_count,
            "retries_count": alpaca_retry_count,
        },
        "resource_consumption": {
            "total_http_pages": massive_page_count + alpaca_page_count,
            "max_pages_limit": MAX_PILOT_PAGES_LIMIT,
            "private_storage_bytes": private_storage_bytes,
            "max_storage_bytes_limit": MAX_PILOT_STORAGE_BYTES_LIMIT,
            "total_runtime_seconds": total_elapsed,
        },
        "governance": {
            "strategy_evaluator_executed": False,
            "performance_evaluation_executed": False,
            "validation_status": "unopened",
            "holdout_status": "quarantined_unopened",
            "approved_production_strategies_empty": True,
        },
    }

    summary_file = ARTIFACTS_DIR / "pilot_summary.json"
    write_pilot_summary_artifact(summary_file, summary)
    print(f"\nSafe pilot summary written to: {summary_file}")
    print(f"Final Disposition: {disposition.value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DAYTRADE-003D-CORR-001 Corrected Pilot CLI")
    parser.add_argument("--pre-live-check", action="store_true", help="Run pre-live offline verification checklist")
    parser.add_argument("--run-live-pilot", action="store_true", help="Execute the bounded 2024-01-02 live pilot")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Symbol batch size (default 100)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_PRIVATE_ROOT), help="Private storage directory")
    parser.add_argument("--dotenv-path", type=str, default=None, help="Optional path to .env file")
    parser.add_argument("--alpaca-delay", type=float, default=0.05, help="Alpaca inter-request delay in seconds")

    args = parser.parse_args()

    if args.pre_live_check:
        return run_pre_live_check(dotenv_path=args.dotenv_path)

    if args.run_live_pilot:
        return run_live_pilot(
            output_dir=Path(args.output_dir),
            batch_size=args.batch_size,
            dotenv_path=args.dotenv_path,
            alpaca_request_delay=args.alpaca_delay,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
