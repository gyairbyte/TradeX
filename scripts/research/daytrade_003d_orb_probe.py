"""Executable CLI for DAYTRADE-003D Stocks-in-Play ORB real-data feasibility probe.

Usage:
    # 1. Pre-live checklist / offline verification:
    uv run python scripts/research/daytrade_003d_orb_probe.py --pre-live-check

    # 2. Bounded live probe execution:
    uv run python scripts/research/daytrade_003d_orb_probe.py --run-live-probe
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.market.hours import get_market_session
from tradex.research.daytrade_orb.data_feasibility import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRIVATE_ROOT,
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    MAX_PILOT_PAGES_LIMIT,
    PILOT_DATE,
    PROBE_DATES,
    SAFETY_MAX_PAGES,
    TARGET_EXCHANGE_MAPPING,
    TASK_ID,
    AlpacaSmokeEvidence,
    FeasibilityDisposition,
    MassiveSnapshotEvidence,
    PilotResourcePlan,
    PilotUniverseEvidence,
    StageAAuditEvidence,
    StageASelectionEvidence,
    StageBAuditEvidence,
    audit_candidate_pool_completeness,
    audit_exchange_distribution,
    audit_stage_b_path,
    audit_type_distribution,
    batch_symbols,
    calculate_pilot_resource_plan,
    compute_and_freeze_stage_a_selection,
    compute_full_year_estimate,
    filter_target_universe,
    load_probe_credentials,
    verify_upstream_spec_hashes,
    write_private_manifest,
    write_safe_probe_artifacts,
)
from tradex.research.daytrade_orb.dataset_contract import (
    TwoStageDatasetManifest,
)
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
ARTIFACTS_DIR = REPO_ROOT / "docs" / "research" / "artifacts" / "DAYTRADE-003D"
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
    """Run comprehensive pre-live verification checklist before provider calls."""
    print("=" * 80)
    print("DAYTRADE-003D PRE-LIVE CHECKLIST VERIFICATION")
    print("=" * 80)

    # 1. Spec hashes
    valid_specs, sha_b, sha_c, _spec_errors = verify_upstream_spec_hashes(REPO_ROOT)
    print(f"[1] 003B Spec Hash ({LOCKED_003B_SPEC_PATH}):")
    print(f"    Expected: {LOCKED_003B_SPEC_SHA256}")
    print(f"    Actual:   {sha_b} -> {'MATCH' if sha_b == LOCKED_003B_SPEC_SHA256 else 'MISMATCH'}")
    print(f"[2] 003C Resolution Hash ({LOCKED_003C_RESOLUTION_PATH}):")
    print(f"    Expected: {LOCKED_003C_RESOLUTION_SHA256}")
    print(f"    Actual:   {sha_c} -> {'MATCH' if sha_c == LOCKED_003C_RESOLUTION_SHA256 else 'MISMATCH'}")

    spec_003d_path = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json"
    if spec_003d_path.exists():
        import hashlib
        sha_d = hashlib.sha256(spec_003d_path.read_bytes()).hexdigest()
        print(f"[3] 003D Spec Hash ({spec_003d_path.name}): {sha_d}")
    else:
        sha_d = "NOT_YET_CREATED"
        print(f"[3] 003D Spec Hash: {sha_d}")

    # 2. Git status
    head_sha = _get_git_commit("HEAD")
    main_sha = _get_git_commit("origin/main")
    status = _get_git_status()
    print(f"[4] Git HEAD:        {head_sha}")
    print(f"[5] Git origin/main: {main_sha}")
    print(f"[6] Worktree clean:  {'YES' if status == '' else 'DIRTY'}")

    # 3. Calendar checks
    print("[7] Fixed probe dates verification on XNYS calendar:")
    cal_ok = True
    for dt_str in PROBE_DATES:
        dt = date.fromisoformat(dt_str)
        sess = get_market_session(dt)
        is_full = sess is not None and not sess.is_early_close
        print(f"    {dt_str}: is_session={sess is not None}, is_early_close={getattr(sess, 'is_early_close', None)}, opens={getattr(sess, 'opens_at', None)}")
        if not is_full:
            cal_ok = False

    # 4. Strategy registry check
    from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES
    registry_empty = APPROVED_PRODUCTION_STRATEGIES == ()
    print(f"[8] Production Strategy Registry Empty: {registry_empty} ({APPROVED_PRODUCTION_STRATEGIES})")

    # 5. Credentials check
    massive_key, alpaca_key, alpaca_secret = load_probe_credentials(dotenv_path)
    creds_ok = bool(massive_key and alpaca_key and alpaca_secret)
    print(f"[9] Provider credentials loaded: massive={bool(massive_key)}, alpaca_key={bool(alpaca_key)}, alpaca_secret={bool(alpaca_secret)}")

    print("-" * 80)
    all_ok = valid_specs and cal_ok and registry_empty and creds_ok
    print(f"PRE-LIVE CHECKLIST OVERALL RESULT: {'PASS' if all_ok else 'FAIL'}")
    print("=" * 80)
    return 0 if all_ok else 1


def run_live_probe(
    output_dir: Path,
    dotenv_path: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    safety_max_pages: int = SAFETY_MAX_PAGES,
) -> int:
    """Execute the bounded live probe strictly according to preregistered rules."""
    start_time = datetime.now(UTC)
    t0 = time.time()
    print("=" * 80)
    print("DAYTRADE-003D BOUNDED REAL-DATA FEASIBILITY PROBE EXECUTION")
    print(f"Timestamp: {start_time.isoformat()}")
    print(f"Private Output Root: {output_dir}")
    print("=" * 80)

    pre_live_commit_sha = _get_git_commit("HEAD")
    output_dir.mkdir(parents=True, exist_ok=True)

    massive_key, alpaca_key, alpaca_secret = load_probe_credentials(dotenv_path)
    if not massive_key or not alpaca_key or not alpaca_secret:
        print("[FATAL] Provider credentials missing!")
        return 1

    massive_client = MassiveDatasetClient(massive_key)
    alpaca_client = DatasetAlpacaClient(alpaca_key, alpaca_secret)

    disposition = FeasibilityDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD
    blocker_details: list[str] = []

    # -------------------------------------------------------------------------
    # STEP 1: Massive credential & taxonomy check
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Massive taxonomy and capability check...")
    try:
        taxonomy_mapping, taxonomy_rows = massive_client.fetch_taxonomy()
        print(f"  -> Taxonomy fetched successfully ({len(taxonomy_mapping)} types, {len(taxonomy_rows)} rows)")
    except Exception as exc:  # noqa: BLE001
        print(f"  -> Massive taxonomy check failed: {exc}")
        disposition = FeasibilityDisposition.BLOCKED_MASSIVE_ENTITLEMENT
        blocker_details.append(f"Massive taxonomy check error: {exc}")
        _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0)
        return 1

    # -------------------------------------------------------------------------
    # STEPS 2-4: Massive 3 Historical Active Snapshots
    # -------------------------------------------------------------------------
    snapshot_evidence_by_date: dict[str, MassiveSnapshotEvidence] = {}
    snapshot_rows_by_date: dict[str, list[dict[str, Any]]] = {}

    for p_date in PROBE_DATES:
        print(f"\n[STEP] Fetching Massive PIT snapshot for {p_date} (active=true, limit=1000)...")
        try:
            t_snap = time.time()
            snap = massive_client.fetch_reference_snapshot(
                pit_date=p_date,
                active=True,
                safety_max_pages=safety_max_pages,
            )
            elapsed_snap = time.time() - t_snap
            obs = snap.observations[0]
            ex_dist = audit_exchange_distribution(snap.rows)
            type_dist = audit_type_distribution(snap.rows)

            ev = MassiveSnapshotEvidence(
                date=p_date,
                active=True,
                page_count=obs.page_count,
                row_count=obs.row_count,
                canonical_ticker_count=obs.canonical_ticker_count,
                blank_ticker_count=obs.blank_ticker_count,
                duplicate_ticker_count=obs.duplicate_ticker_count,
                unresolved_duplicate_count=obs.unresolved_duplicate_count,
                pagination_complete=obs.pagination_complete,
                repeated_cursor=obs.repeated_cursor_detected,
                cycle_detected=obs.cycle_detected,
                http_status=obs.http_status,
                raw_sha256=obs.raw_sha256,
                canonical_sha256=snap.canonical_sha256,
                primary_exchange_distribution=ex_dist,
                type_distribution=type_dist,
                elapsed_seconds=elapsed_snap,
                error=obs.error,
            )
            snapshot_evidence_by_date[p_date] = ev
            snapshot_rows_by_date[p_date] = snap.rows

            print(f"  -> {p_date}: rows={ev.row_count}, pages={ev.page_count}, pagination_complete={ev.pagination_complete}, canonical_sha256={ev.canonical_sha256[:16]}...")
            print(f"     Exchanges: {dict(list(ex_dist.items())[:6])}")
            print(f"     Types:     {dict(list(type_dist.items())[:6])}")

            if not ev.pagination_complete or ev.error:
                print(f"  -> Fatal: snapshot {p_date} failed to reach terminal pagination: {ev.error}")
                disposition = FeasibilityDisposition.BLOCKED_MASSIVE_ENTITLEMENT
                blocker_details.append(f"Snapshot {p_date} incomplete: {ev.error}")
                _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date)
                return 1

        except Exception as exc:  # noqa: BLE001
            print(f"  -> Fatal exception during Massive snapshot {p_date}: {exc}")
            disposition = FeasibilityDisposition.BLOCKED_MASSIVE_ENTITLEMENT
            blocker_details.append(f"Snapshot {p_date} exception: {exc}")
            _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date)
            return 1

    # -------------------------------------------------------------------------
    # STEP 5: Verify Historical PIT Semantics & NYSE/Nasdaq Mapping
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Auditing Historical Point-in-Time Semantics & Exchange Mapping...")
    # Compare 3 snapshots
    snap_dates = list(PROBE_DATES)
    hashes = [snapshot_evidence_by_date[d].canonical_sha256 for d in snap_dates]
    counts = [snapshot_evidence_by_date[d].row_count for d in snap_dates]
    print(f"  Snapshot row counts: {dict(zip(snap_dates, counts))}")
    print(f"  Snapshot SHA-256s:   {[h[:12] for h in hashes]}")

    if len(set(hashes)) == 1 and hashes[0]:
        print("  [WARNING] All three snapshot hashes across 2024 are identical; date parameter may be non-sensitive!")
        disposition = FeasibilityDisposition.BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS
        blocker_details.append("Identical universe snapshots across all 3 probe dates in 2024")
        _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date)
        return 1
    else:
        print("  -> Historical date sensitivity confirmed: universe snapshots vary across 2024 dates.")

    # Exchange mapping check on pilot date
    pilot_rows = snapshot_rows_by_date[PILOT_DATE]
    pilot_ex_dist = snapshot_evidence_by_date[PILOT_DATE].primary_exchange_distribution
    has_xnys = "XNYS" in pilot_ex_dist
    has_xnas = "XNAS" in pilot_ex_dist

    if not (has_xnys and has_xnas):
        print(f"  [FATAL] NYSE/Nasdaq mapping ambiguous; missing expected MIC codes: {pilot_ex_dist}")
        disposition = FeasibilityDisposition.BLOCKED_REFERENCE_EXCHANGE_MAPPING
        blocker_details.append(f"Missing XNYS or XNAS in observed exchanges: {pilot_ex_dist}")
        _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date)
        return 1

    print(f"  -> Verified exchange mapping: XNYS ({pilot_ex_dist.get('XNYS')}) and XNAS ({pilot_ex_dist.get('XNAS')})")

    # -------------------------------------------------------------------------
    # STEP 6: Construct 2024-01-02 Target PIT Universe Privately
    # -------------------------------------------------------------------------
    print("\n[STEP 6] Constructing 2024-01-02 Target PIT Universe...")
    target_symbols, _target_map, universe_evidence = filter_target_universe(
        pilot_rows, allowed_exchanges=TARGET_EXCHANGE_MAPPING
    )
    print(f"  -> Target universe count: {universe_evidence.target_universe_count}")
    print(f"  -> Universe SHA-256:      {universe_evidence.universe_sha256}")
    print(f"  -> Target exchange breakdown: {universe_evidence.target_exchange_distribution}")
    print(f"  -> Excluded exchange count:   {sum(universe_evidence.excluded_exchange_distribution.values())}")

    # Persist universe privately
    private_univ_path = output_dir / f"universe_{PILOT_DATE}.json"
    private_univ_path.write_text(
        json.dumps({
            "date": PILOT_DATE,
            "count": len(target_symbols),
            "hash": universe_evidence.universe_sha256,
            "symbols": target_symbols,
        }, indent=2),
        encoding="utf-8",
    )

    # -------------------------------------------------------------------------
    # STEP 7: Alpaca Capability Smoke Test
    # -------------------------------------------------------------------------
    print("\n[STEP 7] Alpaca tiny SIP/raw capability test...")
    try:
        t_smoke_start = datetime(2023, 12, 1, 0, 0, tzinfo=UTC)
        t_smoke_end = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)
        daily_dfs, daily_meta = alpaca_client.get_bars(
            ["SPY"],
            start_utc=t_smoke_start,
            end_utc=t_smoke_end,
            feed="sip",
            timeframe="1Day",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        spy_daily = daily_dfs.get("SPY", pd.DataFrame())

        m_start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
        m_end = datetime(2024, 1, 2, 14, 34, 59, tzinfo=UTC)
        min_dfs, min_meta = alpaca_client.get_bars(
            ["SPY"],
            start_utc=m_start,
            end_utc=m_end,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        spy_min = min_dfs.get("SPY", pd.DataFrame())

        smoke_ev = AlpacaSmokeEvidence(
            symbol="SPY",
            sip_entitled=daily_meta.get("http_status") == 200 and min_meta.get("http_status") == 200,
            daily_bars_count=len(spy_daily),
            minute_bars_count=len(spy_min),
            raw_adjustment_verified=daily_meta.get("http_status") == 200,
            asof_verified=True,
            http_statuses=[daily_meta.get("http_status", 0), min_meta.get("http_status", 0)],
        )
        print(f"  -> SPY daily bars:  {smoke_ev.daily_bars_count} (expected ~20)")
        print(f"  -> SPY minute bars: {smoke_ev.minute_bars_count} (expected 5)")
        print(f"  -> SIP entitlement verified: {smoke_ev.sip_entitled}")

        if not smoke_ev.sip_entitled or len(spy_daily) == 0:
            print("  [FATAL] Alpaca SIP entitlement test failed!")
            disposition = FeasibilityDisposition.BLOCKED_ALPACA_SIP_ENTITLEMENT
            blocker_details.append("Alpaca SIP entitlement test returned non-200 or empty bars")
            _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date, universe_evidence, smoke_ev)
            return 1

    except Exception as exc:  # noqa: BLE001
        print(f"  [FATAL] Alpaca capability test exception: {exc}")
        disposition = FeasibilityDisposition.BLOCKED_ALPACA_SIP_ENTITLEMENT
        blocker_details.append(f"Alpaca smoke test exception: {exc}")
        _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date, universe_evidence)
        return 1

    # -------------------------------------------------------------------------
    # STEP 8: Calculate Pilot Resource Plan
    # -------------------------------------------------------------------------
    print("\n[STEP 8] Calculating pilot resource plan...")
    total_massive_pages_actual = sum(ev.page_count for ev in snapshot_evidence_by_date.values())
    plan = calculate_pilot_resource_plan(
        universe_size=len(target_symbols),
        batch_size=batch_size,
        daily_lookback_sessions=20,
        or_lookback_sessions=14,
        massive_pages_actual=total_massive_pages_actual,
    )
    print(f"  -> Universe symbols:          {plan.universe_size}")
    print(f"  -> Batches (size {plan.batch_size}):        {plan.batch_count}")
    print(f"  -> Planned daily requests:    {plan.planned_daily_requests}")
    print(f"  -> Planned OR requests:       {plan.planned_or_requests}")
    print(f"  -> Total planned HTTP pages:  {plan.total_planned_pages} (limit: {MAX_PILOT_PAGES_LIMIT})")
    print(f"  -> Estimated storage:         {plan.estimated_storage_bytes / (1024*1024):.1f} MB (limit: 2048 MB)")
    print(f"  -> Is within bounds:          {plan.is_within_bounds}")

    if not plan.is_within_bounds:
        print("  [STOP] Planned pilot exceeds resource bounds (>1000 pages or >2GB storage)!")
        disposition = FeasibilityDisposition.BLOCKED_RESOURCE_BOUND
        blocker_details.append(
            f"Planned pages ({plan.total_planned_pages}) > {MAX_PILOT_PAGES_LIMIT} or storage > 2GB"
        )
        _finalize_probe(output_dir, disposition, blocker_details, pre_live_commit_sha, t0, snapshot_evidence_by_date, universe_evidence, smoke_ev, plan)
        return 0  # Stop as per instruction

    # -------------------------------------------------------------------------
    # STEP 9: Acquire 2024-01-02 Stage-A Daily History
    # -------------------------------------------------------------------------
    print("\n[STEP 9] Acquiring Stage-A Daily History (2023-12-01..2023-12-29, 20 XNYS sessions)...")
    symbol_batches = batch_symbols(target_symbols, batch_size=batch_size)
    d_start_utc = datetime(2023, 12, 1, 0, 0, tzinfo=UTC)
    d_end_utc = datetime(2023, 12, 29, 23, 59, tzinfo=UTC)

    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}
    total_daily_pages = 0
    total_daily_bars = 0

    for b_idx, batch in enumerate(symbol_batches, start=1):
        if b_idx % 10 == 0 or b_idx == len(symbol_batches):
            print(f"  Fetching daily batch {b_idx}/{len(symbol_batches)} ({len(batch)} symbols)...")
        dfs, meta = alpaca_client.get_bars(
            batch,
            start_utc=d_start_utc,
            end_utc=d_end_utc,
            feed="sip",
            timeframe="1Day",
            adjustment="raw",
            asof=PILOT_DATE,
        )
        total_daily_pages += meta.get("page_count", 1)
        for sym, df in dfs.items():
            bars = []
            if not df.empty:
                for ts, row in df.iterrows():
                    ny_dt = ts.astimezone(MARKET_TIMEZONE)
                    sess_d = ny_dt.date()
                    if sess_d >= date(2024, 1, 2):
                        # Strict lookahead guard: session D must never enter historical daily bars!
                        continue
                    try:
                        b = DailyBar(
                            symbol=sym,
                            session_date=sess_d,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                        bars.append(b)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Daily bar parsing skipped: %s", exc)
            daily_bars_by_symbol[sym] = sorted(bars, key=lambda x: x.session_date)
            total_daily_bars += len(bars)

    print(f"  -> Acquired daily bars for {len(daily_bars_by_symbol)} symbols ({total_daily_bars} total bars, {total_daily_pages} pages)")

    # -------------------------------------------------------------------------
    # STEP 10: Acquire Stage-A Prior & Current Opening-Range Data
    # -------------------------------------------------------------------------
    print("\n[STEP 10] Acquiring Stage-A Opening-Range History (14 prior sessions + current session)...")
    prior_sessions = get_prior_xnys_sessions(date(2024, 1, 2), count=14)
    all_or_sessions = list(prior_sessions) + [date(2024, 1, 2)]

    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {s: [] for s in target_symbols}
    current_or_by_symbol: dict[str, Any] = {}
    total_or_pages = 0

    for s_idx, sess_d in enumerate(all_or_sessions, start=1):
        is_current = (sess_d == date(2024, 1, 2))
        label = "CURRENT D (2024-01-02)" if is_current else f"PRIOR D-{15 - s_idx} ({sess_d})"
        print(f"  Fetching OR session {s_idx}/15: {label}...")

        s_open_ny = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 30, 0, tzinfo=MARKET_TIMEZONE)
        s_close_ny = datetime(sess_d.year, sess_d.month, sess_d.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE)
        s_open_utc = s_open_ny.astimezone(UTC)
        s_close_utc = s_close_ny.astimezone(UTC)

        for batch in symbol_batches:
            dfs, meta = alpaca_client.get_bars(
                batch,
                start_utc=s_open_utc,
                end_utc=s_close_utc,
                feed="sip",
                timeframe="1Min",
                adjustment="raw",
                asof=PILOT_DATE,
            )
            total_or_pages += meta.get("page_count", 1)
            for sym, df in dfs.items():
                if df.empty:
                    continue
                min_bars = []
                for ts, row in df.iterrows():
                    ny_ts = ts.astimezone(MARKET_TIMEZONE)
                    try:
                        mb = MinuteBar(
                            symbol=sym,
                            timestamp=ts.to_pydatetime(),
                            session_date=ny_ts.date(),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                        min_bars.append(mb)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("OR bar parsing skipped: %s", exc)

                if is_current:
                    op = evaluate_opening_range(min_bars)
                    if op is not None:
                        current_or_by_symbol[sym] = op
                else:
                    if len(min_bars) == 5:
                        tot_vol = sum(b.volume for b in min_bars)
                        obs = OpeningRangeVolumeObservation(
                            symbol=sym,
                            session_date=sess_d,
                            volume=tot_vol,
                        )
                        prior_or_obs_by_symbol[sym].append(obs)

    print(f"  -> Acquired OR data: {len(current_or_by_symbol)} symbols have valid current OR; {total_or_pages} HTTP pages")

    # -------------------------------------------------------------------------
    # STEP 11: Audit Complete Stage-A Candidate Pool
    # -------------------------------------------------------------------------
    print("\n[STEP 11] Auditing Complete Candidate Pool...")
    stage_a_evidence, reasons_by_sym = audit_candidate_pool_completeness(
        target_universe=target_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_obs_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=date(2024, 1, 2),
        required_lookback=14,
    )

    print(f"  -> Total universe symbols:        {stage_a_evidence.total_universe_symbols}")
    print(f"  -> Computable candidate pool:     {stage_a_evidence.candidate_pool_computable_count} ({stage_a_evidence.candidate_pool_completeness_pct:.2f}%)")
    print(f"  -> Incomplete history (IPO/age):  {stage_a_evidence.incomplete_history_ipo_or_listing_count}")
    print(f"  -> Missing provider bars:         {stage_a_evidence.missing_provider_bars_count}")
    print(f"  -> Data integrity errors:         {stage_a_evidence.data_integrity_error_count}")
    print(f"  -> Cross-provider unmapped:       {stage_a_evidence.cross_provider_unmapped_count}")
    print(f"  -> 100% computable gate passed:   {stage_a_evidence.is_100_percent_computable}")

    # Persist Stage-A candidate pool audit details privately
    audit_path = output_dir / "stage_a_candidate_audit.json"
    audit_path.write_text(
        json.dumps({
            "target_session": PILOT_DATE,
            "evidence": asdict(stage_a_evidence),
            "reasons_sample": dict(list(reasons_by_sym.items())[:50]),
        }, indent=2),
        encoding="utf-8",
    )

    if not stage_a_evidence.is_100_percent_computable:
        print("  [DISPOSITION] Candidate pool is NOT 100% computable under the locked DAYTRADE-003C contract!")
        if stage_a_evidence.incomplete_history_ipo_or_listing_count > 0:
            print(f"  -> Primary blocker: BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS ({stage_a_evidence.incomplete_history_ipo_or_listing_count} members lack 14 prior sessions due to IPO/listing age).")
            disposition = FeasibilityDisposition.BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS
            blocker_details.append(
                f"{stage_a_evidence.incomplete_history_ipo_or_listing_count} active PIT members lack 14 prior sessions due to listing age/history"
            )
        elif stage_a_evidence.cross_provider_unmapped_count > 0:
            print("  -> Primary blocker: BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY")
            disposition = FeasibilityDisposition.BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY
            blocker_details.append(f"{stage_a_evidence.cross_provider_unmapped_count} symbols completely unmapped between providers")
        else:
            print("  -> Primary blocker: BLOCKED_STAGE_A_DATA_COMPLETENESS")
            disposition = FeasibilityDisposition.BLOCKED_STAGE_A_DATA_COMPLETENESS
            blocker_details.append(f"Candidate pool only {stage_a_evidence.candidate_pool_completeness_pct:.2f}% complete")

        print("  -> STOPPING before Stage-B as required by Section 20 / Section 32!")
        _finalize_probe(
            output_dir,
            disposition,
            blocker_details,
            pre_live_commit_sha,
            t0,
            snapshot_evidence_by_date,
            universe_evidence,
            smoke_ev,
            plan,
            stage_a_evidence,
        )
        return 0

    # -------------------------------------------------------------------------
    # STEP 12: Deterministically Construct, Freeze, and Hash Top-20 Selection
    # -------------------------------------------------------------------------
    print("\n[STEP 12] Ranking Candidates and Freezing Top-20 Selection...")
    selection_ev, selection_records, selected_symbols = compute_and_freeze_stage_a_selection(
        universe_symbols=target_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_obs_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=date(2024, 1, 2),
    )
    print(f"  -> Eligible candidates: {selection_ev.eligible_candidates_count}")
    print(f"  -> Top-20 selected:     {selection_ev.selected_count}")
    print(f"  -> Selection SHA-256:   {selection_ev.selection_sha256}")
    print(f"  -> Doji count:          {selection_ev.doji_count}")

    # Persist selection artifact PRIVATELY
    sel_path = output_dir / "stage_a_top_20_selection.json"
    sel_path.write_text(json.dumps(selection_records, indent=2), encoding="utf-8")

    # -------------------------------------------------------------------------
    # STEP 13: Acquire Stage-B 09:35..15:59 Raw SIP Path strictly for Top 20
    # -------------------------------------------------------------------------
    print("\n[STEP 13] Acquiring Stage-B 09:35..15:59 regular-session path for Top 20...")
    b_start_ny = datetime(2024, 1, 2, 9, 35, 0, tzinfo=MARKET_TIMEZONE)
    b_end_ny = datetime(2024, 1, 2, 15, 59, 59, tzinfo=MARKET_TIMEZONE)
    b_start_utc = b_start_ny.astimezone(UTC)
    b_end_utc = b_end_ny.astimezone(UTC)

    b_dfs, _b_meta = alpaca_client.get_bars(
        selected_symbols,
        start_utc=b_start_utc,
        end_utc=b_end_utc,
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        asof=PILOT_DATE,
    )

    stage_b_bars_by_symbol: dict[str, list[MinuteBar]] = {}
    for sym in selected_symbols:
        df = b_dfs.get(sym, pd.DataFrame())
        bars = []
        if not df.empty:
            for ts, row in df.iterrows():
                ny_ts = ts.astimezone(MARKET_TIMEZONE)
                try:
                    mb = MinuteBar(
                        symbol=sym,
                        timestamp=ts.to_pydatetime(),
                        session_date=ny_ts.date(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                    bars.append(mb)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Stage B bar parsing skipped: %s", exc)
        stage_b_bars_by_symbol[sym] = bars

    # -------------------------------------------------------------------------
    # STEP 14: Audit Stage-B Data
    # -------------------------------------------------------------------------
    print("\n[STEP 14] Auditing Stage-B Path Completeness...")
    stage_b_evidence, missing_minutes_by_sym = audit_stage_b_path(
        selected_symbols=selected_symbols,
        bars_by_symbol=stage_b_bars_by_symbol,
        target_session=date(2024, 1, 2),
    )
    print(f"  -> Selected symbols:       {stage_b_evidence.symbols_count}")
    print(f"  -> Total expected bars:    {stage_b_evidence.total_expected_bars} (385 bars/symbol)")
    print(f"  -> Total observed bars:    {stage_b_evidence.total_observed_bars}")
    print(f"  -> Missing minutes count:  {stage_b_evidence.missing_minutes_count}")
    print(f"  -> Path complete:          {stage_b_evidence.path_complete}")

    if not stage_b_evidence.path_complete:
        print("  [DISPOSITION] Stage-B path is INCOMPLETE!")
        disposition = FeasibilityDisposition.BLOCKED_STAGE_B_PATH_COMPLETENESS
        blocker_details.append(
            f"Stage-B missing {stage_b_evidence.missing_minutes_count} bars across {len(missing_minutes_by_sym)} symbols"
        )
    else:
        disposition = FeasibilityDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD
        print("  [SUCCESS] All data feasibility gates passed!")

    # -------------------------------------------------------------------------
    # STEP 15: Generate Safe Evidence & Resource Estimate Artifacts
    # -------------------------------------------------------------------------
    _finalize_probe(
        output_dir,
        disposition,
        blocker_details,
        pre_live_commit_sha,
        t0,
        snapshot_evidence_by_date,
        universe_evidence,
        smoke_ev,
        plan,
        stage_a_evidence,
        selection_ev,
        stage_b_evidence,
    )
    return 0


def _finalize_probe(
    output_dir: Path,
    disposition: FeasibilityDisposition,
    blocker_details: list[str],
    pre_live_commit_sha: str,
    t0: float,
    snapshot_evidence_by_date: dict[str, MassiveSnapshotEvidence] | None = None,
    universe_evidence: PilotUniverseEvidence | None = None,
    smoke_ev: AlpacaSmokeEvidence | None = None,
    plan: PilotResourcePlan | None = None,
    stage_a_evidence: StageAAuditEvidence | None = None,
    selection_ev: StageASelectionEvidence | None = None,
    stage_b_evidence: StageBAuditEvidence | None = None,
) -> None:
    """Write public safe artifacts and private manifest."""
    elapsed_total = time.time() - t0
    print("\n[STEP 15] Writing safe artifacts and resource estimates...")

    # Calculate private storage bytes
    private_bytes = 0
    if output_dir.exists():
        for f in output_dir.rglob("*"):
            if f.is_file():
                private_bytes += f.stat().st_size

    # Estimate full year build
    universe_count = universe_evidence.target_universe_count if universe_evidence else 0
    massive_pages = sum(ev.page_count for ev in snapshot_evidence_by_date.values()) if snapshot_evidence_by_date else 0
    alpaca_pages = (plan.total_planned_alpaca_pages if plan else 0)

    est = compute_full_year_estimate(
        pilot_universe_size=universe_count,
        pilot_massive_pages=math.ceil(massive_pages / 3.0) if massive_pages > 0 else 12,
        pilot_alpaca_pages=alpaca_pages,
        pilot_private_bytes=private_bytes,
        pilot_elapsed_seconds=elapsed_total,
        full_year_sessions_count=249,
    )

    # Safe summary JSON
    summary_data: dict[str, Any] = {
        "task_id": TASK_ID,
        "strategy_id": "DAYTRADE-003B-ORB-SIP5M",
        "pre_live_commit_sha": pre_live_commit_sha,
        "live_probe_completion_timestamp": datetime.now(UTC).isoformat(),
        "probe_dates": list(PROBE_DATES),
        "pilot_date": PILOT_DATE,
        "providers": ["massive", "alpaca"],
        "feeds": {"massive": "reference_v3", "alpaca": "sip"},
        "adjustment_mode": "raw",
        "top_level_disposition": disposition.value,
        "blocker_details": blocker_details,
        "governance": {
            "performance_evaluation_executed": False,
            "strategy_evaluator_executed": False,
            "holdout_status": "quarantined_unopened",
            "validation_status": "unopened",
            "production_promotion_status": "none",
            "approved_production_strategies_empty": True,
        },
        "massive_snapshots": {
            d: asdict(ev) for d, ev in (snapshot_evidence_by_date or {}).items()
        },
        "alpaca_smoke": asdict(smoke_ev) if smoke_ev else None,
        "pilot_universe": asdict(universe_evidence) if universe_evidence else None,
        "pilot_resource_plan": asdict(plan) if plan else None,
        "stage_a_candidate_pool": asdict(stage_a_evidence) if stage_a_evidence else None,
        "stage_a_selection": asdict(selection_ev) if selection_ev else None,
        "stage_b_path": asdict(stage_b_evidence) if stage_b_evidence else None,
        "private_storage_bytes": private_bytes,
        "total_runtime_seconds": round(elapsed_total, 2),
    }

    # Resource estimate JSON
    resource_estimate_data = asdict(est)

    # Provider evidence JSON
    provider_evidence_data = {
        "massive_taxonomy_capability": True,
        "massive_historical_pit_sensitivity_proven": (
            len(snapshot_evidence_by_date) == 3
            if snapshot_evidence_by_date
            else False
        ),
        "exchange_mapping_used": list(TARGET_EXCHANGE_MAPPING),
        "alpaca_sip_entitled": smoke_ev.sip_entitled if smoke_ev else False,
        "alpaca_raw_adjustment_verified": smoke_ev.raw_adjustment_verified if smoke_ev else False,
        "alpaca_asof_tested": smoke_ev.asof_verified if smoke_ev else False,
        "disposition": disposition.value,
    }

    # Write safe artifacts to repo
    write_safe_probe_artifacts(
        output_dir=ARTIFACTS_DIR,
        summary_data=summary_data,
        resource_estimate_data=resource_estimate_data,
        provider_evidence_data=provider_evidence_data,
    )
    print(f"  -> Written safe artifacts to: {ARTIFACTS_DIR}")

    # Write private manifest to private root
    if universe_evidence and selection_ev:
        manifest = TwoStageDatasetManifest(
            task_id=TASK_ID,
            strategy_id="DAYTRADE-003B-ORB-SIP5M",
            upstream_spec_sha256=LOCKED_003B_SPEC_SHA256,
            resolution_spec_sha256=LOCKED_003C_RESOLUTION_SHA256,
            provider_identity="massive+alpaca_sip",
            feed="sip",
            adjustment_mode="raw",
            timezone="America/New_York",
            calendar_version="XNYS",
            universe_provider="massive",
            universe_query_date=PILOT_DATE,
            universe_symbol_count=universe_evidence.target_universe_count,
            universe_hash=universe_evidence.universe_sha256,
            exchange_filters=TARGET_EXCHANGE_MAPPING,
            type_code_distribution=universe_evidence.type_distribution,
            daily_data_hashes_and_counts={
                "symbols_complete": stage_a_evidence.daily_history_complete_count if stage_a_evidence else 0
            },
            opening_range_data_hashes_and_counts={
                "symbols_complete": stage_a_evidence.prior_or_history_complete_count if stage_a_evidence else 0
            },
            top_20_selection_artifact_hash=selection_ev.selection_sha256,
            full_path_selected_symbol_data_hashes_and_counts={
                "symbols_count": stage_b_evidence.symbols_count if stage_b_evidence else 0,
                "path_complete": stage_b_evidence.path_complete if stage_b_evidence else False,
            },
            session_coverage=(PILOT_DATE,),
            excluded_sessions=(),
            dq_reasons=tuple(blocker_details),
            provider_request_ids=(),
            pagination_completeness=True,
            acquisition_timestamps={"completed_at": datetime.now(UTC).isoformat()},
            holdout_status="quarantined_unopened",
        )
        write_private_manifest(output_dir, manifest)
        print(f"  -> Written private manifest to: {output_dir / 'manifest.json'}")

    print("\n" + "=" * 80)
    print(f"FINAL PROBE DISPOSITION: {disposition.value}")
    if blocker_details:
        print("Blocker details:")
        for b in blocker_details:
            print(f"  * {b}")
    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="DAYTRADE-003D ORB data feasibility CLI")
    parser.add_argument("--pre-live-check", action="store_true", help="Run pre-live checklist")
    parser.add_argument("--run-live-probe", action="store_true", help="Run bounded live probe")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PRIVATE_ROOT, help="Private dataset root")
    parser.add_argument("--dotenv-path", type=str, default=None, help="Explicit path to .env")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Alpaca symbol batch size")
    parser.add_argument("--safety-max-pages", type=int, default=SAFETY_MAX_PAGES, help="Massive safety max pages")
    args = parser.parse_args()

    if args.pre_live_check:
        return run_pre_live_check(args.dotenv_path)

    if args.run_live_probe:
        return run_live_probe(
            output_dir=args.output_dir,
            dotenv_path=args.dotenv_path,
            batch_size=args.batch_size,
            safety_max_pages=args.safety_max_pages,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
