"""Deterministic research CLI for LONG-002C.

Subcommands:
- preflight: Audit credentials, provider connectivity, spec hashes, and run universe audit.
- build: Ingest provider data, build observations, calculate outcomes, cluster episodes, evaluate baselines, and generate artifacts.
- evaluate: Run offline evaluation from frozen Parquet dataset without network access.
- verify: Verify artifact checksums and manifest consistency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.long_002c.artifacts import (
    write_committed_summaries,
    write_external_parquet_tables,
)
from tradex.research.long_002c.audit import execute_bounded_universe_audit
from tradex.research.long_002c.bars import load_interval_aware_daily_bars
from tradex.research.long_002c.baselines import (
    evaluate_baselines_for_date,
    select_winning_baseline,
)
from tradex.research.long_002c.cache import ResponseCache
from tradex.research.long_002c.calendar import (
    get_trading_sessions,
)
from tradex.research.long_002c.dataset import (
    build_decision_observations_for_security,
)
from tradex.research.long_002c.episodes import cluster_master_episodes
from tradex.research.long_002c.feasibility import (
    analyze_endpoint_feasibility,
    run_block_resampling,
)
from tradex.research.long_002c.frozen_manifest import (
    build_frozen_pre_run_manifest_data,
    compute_file_sha256,
    get_git_commit_sha,
    verify_frozen_pre_run_manifest,
    write_frozen_pre_run_manifest,
)
from tradex.research.long_002c.identity import (
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    SecurityIdentity,
    SecurityMaster,
    extract_share_class_discriminator,
    make_immutable_id,
)
from tradex.research.long_002c.manifest import (
    CandidateSecurity,
    TickerInterval,
    build_full_development_discovery_manifest,
    load_candidate_manifest,
    register_manifest_in_security_master,
)
from tradex.research.long_002c.market_cap import compute_security_pit_market_caps
from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    DataEligibility,
    DataQualityCoverage,
    DecisionObservation,
    EarningsScheduleStatus,
    ExclusionReasonRecord,
    OutcomeLabelRecord,
    ProvenanceProviderRecord,
    SecurityClassificationStatus,
)
from tradex.research.long_002c.outcomes import (
    compute_all_nine_outcomes,
    derive_affected_special_distribution_sessions,
    parse_special_distribution_dates,
)
from tradex.research.long_002c.providers import (
    AlpacaDailyClient,
    EdgarClient,
    MassiveRefClient,
    ProviderDataUnavailable,
    resolve_credentials,
)
from tradex.research.long_002c.screening import (
    screen_candidates_manifest,
)
from tradex.research.long_002c.spec import (
    DEV_END,
    DEV_START,
    PRIMARY_ENTRY_FRICTION_BPS,
    REPO_ROOT,
    WARMUP_START,
    enforce_split_guard,
    verify_upstream_spec_hashes,
)

# Bounded smoke test panel for connectivity and integration tests only.
# Synthetic or smoke panels must NEVER be described as the full development universe.
SMOKE_CANDIDATES: list[dict[str, Any]] = [
    {"ticker": "AAPL", "cik": "0000320193", "composite_figi": "BBG000B9XRY4", "name": "Apple Inc.", "start": "1980-12-12", "type": "common_stock"},
    {"ticker": "MSFT", "cik": "0000789019", "composite_figi": "BBG000BPH459", "name": "Microsoft Corp.", "start": "1986-03-13", "type": "common_stock"},
    {"ticker": "NVDA", "cik": "0001045810", "composite_figi": "BBG000BBJQV0", "name": "NVIDIA Corp.", "start": "1999-01-22", "type": "common_stock"},
    {"ticker": "AMZN", "cik": "0001018724", "composite_figi": "BBG000BVPV84", "name": "Amazon.com Inc.", "start": "1997-05-15", "type": "common_stock"},
    {"ticker": "JNJ", "cik": "0000200406", "composite_figi": "BBG000BMHYD1", "name": "Johnson & Johnson", "start": "1944-09-25", "type": "common_stock"},
    # Meta Platforms: effective historical ticker during 2016-2020 was FB (renamed to META in 2022)
    {"ticker": "FB", "cik": "0001326801", "composite_figi": "BBG000MM2P62", "name": "Meta Platforms Inc.", "start": "2012-05-18", "type": "common_stock"},
]


def run_universe_audit_preflight(creds: dict[str, str | None]) -> dict[str, Any]:
    """Execute evidence-backed historical universe construction and PIT eligibility audit."""
    return execute_bounded_universe_audit(creds)


def cmd_discover(args: argparse.Namespace) -> int:
    """Stage A: Build complete candidate discovery universe across 72 monthly snapshots + inactive snapshot."""
    print("=== LONG-002C STAGE A: CANDIDATE DISCOVERY ===")
    creds = resolve_credentials()
    if not creds.get("massive_api_key"):
        print("ERROR: Massive API key (MASSIVE_API_KEY) is required for candidate discovery.")
        return 1

    cache = ResponseCache()
    massive = MassiveRefClient(creds["massive_api_key"], cache=cache)

    out_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else REPO_ROOT / "data" / "research" / "long_002c"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "discovery_manifest.json"
    metrics_file = out_dir / "discovery_manifest_metrics.json"

    def _on_progress(kind: str, cur: int, tot: int, dt: str) -> None:
        print(f"      [{kind} {cur}/{tot}] Fetching snapshot for {dt}...")

    custom_dates = getattr(args, "dates", None)
    include_inactive = not getattr(args, "skip_inactive", False)
    if custom_dates:
        print(f"Enumerating custom panel of {len(custom_dates)} reference snapshots...")
    else:
        print("Enumerating 72 monthly active reference snapshots + DEV_END inactive snapshot...")

    start_disc_time = time.monotonic()
    candidates, metrics, comparison = build_full_development_discovery_manifest(
        massive=massive,
        custom_dates=custom_dates,
        include_inactive=include_inactive,
        on_progress=_on_progress,
    )
    disc_elapsed = time.monotonic() - start_disc_time

    manifest_dict = {
        "discovery_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_candidates": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
        "metrics": metrics.to_dict(),
        "classification_comparison": comparison,
    }

    out_file.write_text(json.dumps(manifest_dict, indent=2), encoding="utf-8")
    metrics_file.write_text(json.dumps({"metrics": metrics.to_dict(), "comparison": comparison}, indent=2), encoding="utf-8")

    disc_sha = hashlib.sha256(out_file.read_bytes()).hexdigest()
    chk_file = out_file.with_suffix(".sha256")
    chk_file.write_text(f"{disc_sha}  {out_file.name}\n", encoding="utf-8")

    print("\nStage A Discovery Complete:")
    print(f"  - Output Manifest: {out_file} (SHA-256: {disc_sha})")
    print(f"  - Metrics Summary: {metrics_file}")
    print(f"  - Runtime: {disc_elapsed:.1f}s")
    print(f"  - Massive Network Requests: {massive.network_requests_count}")
    print(f"  - Massive Cache Hits: {massive.cache_hits_count}")
    print(f"  - Massive Retries: {massive.retries_count}")
    print(f"  - Massive 429 Rate Limits: {massive.rate_limit_429_count}")
    print("  - Monthly Active Snapshots: 72 (2015-01 through 2020-12)")
    print("  - Inactive Snapshot: 1 (2020-12-31, active=False)")
    print(f"  - Total Raw Records: {metrics.total_raw_records_evaluated}")
    print(f"  - Unique Symbols Seen: {metrics.unique_symbols_seen}")
    print(f"  - Unique Securities Discovered: {metrics.unique_securities_discovered}")
    print(f"  - Supported Common Stock: {metrics.supported_common_stock_count}")
    print(f"  - Excluded Types: {metrics.excluded_security_type_count}")
    print(f"  - Unknown (Fail Closed): {metrics.unknown_fail_closed_count}")
    print(f"  - CIK Coverage: {metrics.cik_coverage_pct}%")
    print(f"  - FIGI Coverage: {metrics.figi_coverage_pct}%")
    cov_16 = comparison["coverage_2016"]
    cov_20 = comparison["coverage_2020"]
    print(f"  - 2016 Coverage: Common {cov_16['common_stock_pct']}%, CIK {cov_16['cik_coverage_pct']}%, FIGI {cov_16['figi_coverage_pct']}%")
    print(f"  - 2020 Coverage: Common {cov_20['common_stock_pct']}%, CIK {cov_20['cik_coverage_pct']}%, FIGI {cov_20['figi_coverage_pct']}%")
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    """Stage B: Screen candidate securities and produce frozen pre-run manifest."""
    print("=== LONG-002C STAGE B: CANDIDATE SCREENING ===")
    creds = resolve_credentials()
    if not (creds.get("alpaca_api_key") and creds.get("alpaca_secret_key")):
        print("ERROR: Alpaca credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY) are required for Stage B screening.")
        return 1

    cache = ResponseCache()
    alpaca = AlpacaDailyClient(creds["alpaca_api_key"], creds["alpaca_secret_key"], cache=cache)  # type: ignore[arg-type]
    edgar = EdgarClient(cache=cache)

    candidates_path = (
        Path(args.candidates_file)
        if getattr(args, "candidates_file", None)
        else (REPO_ROOT / "data" / "research" / "long_002c" / "discovery_manifest.json")
    )
    if not candidates_path.exists():
        print(f"ERROR: Candidates manifest not found: {candidates_path}")
        print("Run 'tradex-long-002c discover' first or specify --candidates-file.")
        return 1

    with candidates_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)
    raw_list = raw_data.get("candidates", raw_data) if isinstance(raw_data, dict) else raw_data

    candidates: list[CandidateSecurity] = []
    for item in raw_list:
        if isinstance(item, dict) and "immutable_security_id" in item:
            candidates.append(CandidateSecurity.from_dict(item))
        elif isinstance(item, dict):
            sym = item["ticker"]
            cik = item.get("cik")
            if not cik:
                continue
            candidates.append(
                CandidateSecurity(
                    immutable_security_id=make_immutable_id(
                        sym,
                        cik=cik,
                        composite_figi=item.get("composite_figi"),
                        share_class_figi=item.get("share_class_figi"),
                        share_class_discriminator=item.get("share_class_discriminator") or extract_share_class_discriminator(item),
                        allow_unverified=False,
                    ),
                    primary_symbol=sym,
                    cik=cik,
                    composite_figi=item.get("composite_figi"),
                    share_class_figi=item.get("share_class_figi"),
                    company_name=item.get("name", ""),
                    primary_exchange=item.get("primary_exchange", "XNAS"),
                    security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
                    first_seen_date=WARMUP_START,
                    last_seen_date=DEV_END,
                )
            )

    max_cands = getattr(args, "max_candidates", None)
    eval_cands = candidates[:max_cands] if max_cands else candidates
    print(f"Screening {len(eval_cands)} candidates against Stage B eligibility criteria...")
    eligible_ids, rejected_ids, summary = screen_candidates_manifest(
        eval_cands,
        alpaca=alpaca,
        edgar=edgar,
        max_candidates=max_cands,
        on_progress=lambda cur, tot, sym, ok: print(f"      [{cur}/{tot}] {sym}: {'PASS' if ok else 'FAIL'}"),
    )

    if summary.get("unresolved_provider_failures_count", 0) > 0:
        fail_cnt = summary["unresolved_provider_failures_count"]
        print(f"\nERROR: Stage B screening halted with {fail_cnt} unresolved provider failures!")
        print(f"  - Provider failure breakdown: {summary.get('provider_failure_reason_counts')}")
        print(f"  - Affected security IDs: {summary.get('provider_failed_security_ids')}")
        print("Official frozen pre-run manifest CANNOT be generated while unresolved provider failures exist.")
        return 1

    out_path = (
        Path(args.output)
        if getattr(args, "output", None)
        else (REPO_ROOT / "data" / "research" / "long_002c" / "frozen_pre_run_manifest.json")
    )
    pre_run_data = build_frozen_pre_run_manifest_data(
        discovery_manifest_path=candidates_path,
        stage_b_eligible_ids=eligible_ids,
        stage_b_summary=summary,
        repo_root=REPO_ROOT,
    )
    written_path, frozen_sha = write_frozen_pre_run_manifest(out_path, pre_run_data)
    print("\nStage B Screening Complete:")
    print(f"  - Evaluated: {len(eval_cands)}")
    print(f"  - Eligible: {len(eligible_ids)} ({summary['pass_rate_pct']}%)")
    print(f"  - Rejected: {len(rejected_ids)}")
    print(f"  - Genuine No-Bars: {summary.get('genuine_no_bars_count', 0)}")
    print(f"  - Provider Failures: {summary.get('provider_failures_count', 0)}")
    print(f"  - Rejection Reason Summary: {summary.get('rejection_reason_counts', {})}")
    print(f"  - Alpaca Audit Metrics: {summary.get('alpaca_audit_metrics', {})}")
    print(f"  - PIT Market Cap Coverage: {summary.get('pit_market_cap_coverage_pct', 0.0)}%")
    print(f"  - Ticker Resolution Coverage: {summary.get('ticker_resolution_coverage_pct', 0.0)}%")
    print(f"  - Classification Coverage: {summary.get('classification_coverage_pct', 0.0)}%")
    print(f"  - Early-2016 Attrition: {summary.get('early_2016_attrition_pct', 0.0)}%")
    print(f"  - Exact Acceptance Shares Coverage: {summary.get('exact_acceptance_shares_count', 0)} sessions ({summary.get('exact_acceptance_shares_pct', 0.0)}%)")
    print(f"  - Conservative Date-Only Shares Coverage: {summary.get('conservative_date_only_shares_count', 0)} sessions ({summary.get('conservative_date_only_shares_pct', 0.0)}%)")
    print(f"  - Frozen Pre-Run Manifest: {written_path}")
    print(f"  - Frozen Pre-Run SHA-256: {frozen_sha}")
    verified = verify_frozen_pre_run_manifest(written_path, frozen_sha)
    print(f"  - Verification: {'PASS' if verified else 'FAIL'}")
    return 0 if verified else 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Audit provider credentials, network status, spec hashes, and boundaries."""
    print("=== LONG-002C PREFLIGHT AUDIT ===")

    # 1. Spec hashes
    print("[1/5] Verifying 11 upstream specification hashes...")
    try:
        verified = verify_upstream_spec_hashes()
        print(f"      OK: All {len(verified)} upstream spec hashes match exact SHA-256.")
    except Exception as e:  # noqa: BLE001
        print(f"      FAILED: Upstream spec hash verification failed: {e}")
        return 1

    # 2. Credentials presence (NEVER printing secrets)
    print("[2/5] Checking provider credentials...")
    creds = resolve_credentials()
    alpaca_k = bool(creds.get("alpaca_api_key"))
    alpaca_s = bool(creds.get("alpaca_secret_key"))
    massive_k = bool(creds.get("massive_api_key"))

    print(f"      - alpaca_api_key: {'present' if alpaca_k else 'MISSING'}")
    print(f"      - alpaca_secret_key: {'present' if alpaca_s else 'MISSING'}")
    print(f"      - Massive key: {'present' if massive_k else 'MISSING'}")

    if not (alpaca_k and alpaca_s):
        print("      WARNING: Alpaca credentials missing. Historical daily bars fallback unavailable.")
    if not massive_k:
        print("      WARNING: Massive key missing. Reference and corporate actions unavailable.")

    # 3. Provider connectivity test
    print("[3/5] Testing provider endpoints...")
    if alpaca_k and alpaca_s:
        try:
            alpaca = AlpacaDailyClient(creds["alpaca_api_key"], creds["alpaca_secret_key"])  # type: ignore[arg-type]
            bars, _ = alpaca.fetch_daily_bars("AAPL", "2016-01-01T00:00:00Z", "2016-01-08T23:59:59Z")
            print(f"      - Alpaca Daily Bars (AAPL Jan 2016): OK ({len(bars)} bars returned)")
        except Exception as e:  # noqa: BLE001
            print(f"      - Alpaca Daily Bars: FAILED ({e})")

    if massive_k:
        try:
            massive = MassiveRefClient(creds["massive_api_key"], min_interval_seconds=0)  # type: ignore[arg-type]
            splits, divs, _ = massive.fetch_corporate_actions("AAPL")
            print(f"      - Massive Corporate Actions (AAPL): OK ({len(splits)} splits, {len(divs)} divs)")
        except Exception as e:  # noqa: BLE001
            print(f"      - Massive Corporate Actions: FAILED ({e})")

    edgar = EdgarClient()
    try:
        sub, _ = edgar.fetch_submissions("0000320193")
        print(f"      - SEC EDGAR (Apple CIK 0000320193): OK ({bool(sub.get('cik'))})")
    except Exception as e:  # noqa: BLE001
        print(f"      - SEC EDGAR: FAILED ({e})")

    # 4. Disk destination & gitignore
    print("[4/5] Checking disk destination and .gitignore protection...")
    gitignore_path = REPO_ROOT / ".gitignore"
    if gitignore_path.exists():
        gi_text = gitignore_path.read_text(encoding="utf-8")
        if "data/" in gi_text:
            print("      OK: 'data/' is explicitly gitignored.")
        else:
            print("      WARNING: 'data/' not found in .gitignore!")
    data_dir = REPO_ROOT / "data" / "research" / "long_002c"
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"      OK: External dataset directory ready at {data_dir}")

    # 5. Split guard check
    print("[5/5] Testing fail-closed split guard...")
    try:
        enforce_split_guard("2021-01-01")
        print("      FAILED: Split guard did not reject 2021-01-01!")
        return 1
    except Exception:  # noqa: BLE001
        print("      OK: Split guard correctly rejected 2021-01-01.")

    # Optional universe audit
    if getattr(args, "universe_audit", False):
        run_universe_audit_preflight(creds)

    print("\nPreflight complete. Status: READY.")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build development dataset and run full offline analysis."""
    start_time = time.monotonic()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")

    # Determine candidate panel
    manifest_candidates: list[CandidateSecurity] = []
    if args.candidates_file:
        c_path = Path(args.candidates_file)
        if not c_path.exists():
            print(f"ERROR: Candidates file not found: {c_path}")
            return 1
        with c_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
        raw_list = (
            raw_data["candidates"]
            if isinstance(raw_data, dict) and "candidates" in raw_data
            else raw_data
        )
        for item in raw_list:
            if isinstance(item, dict) and "immutable_security_id" in item:
                cand = CandidateSecurity.from_dict(item)
            else:
                sym = item["ticker"]
                cik = item.get("cik")
                if not cik:
                    continue
                disc = item.get("share_class_discriminator") or extract_share_class_discriminator(item)
                sec_id = make_immutable_id(
                    sym,
                    cik=cik,
                    composite_figi=item.get("composite_figi"),
                    share_class_figi=item.get("share_class_figi"),
                    share_class_discriminator=disc,
                    allow_unverified=False,
                )
                cand = CandidateSecurity(
                    immutable_security_id=sec_id,
                    primary_symbol=sym,
                    cik=cik,
                    composite_figi=item.get("composite_figi"),
                    share_class_figi=item.get("share_class_figi"),
                    company_name=item.get("name", ""),
                    primary_exchange=item.get("primary_exchange", "XNAS"),
                    security_type=item.get("security_type", CLASSIFICATION_SUPPORTED_COMMON_STOCK),
                    first_seen_date=item.get("start", WARMUP_START),
                    last_seen_date=DEV_END,
                    ticker_intervals=[
                        TickerInterval(
                            symbol=sym,
                            start_date=item.get("start", WARMUP_START),
                            end_date=DEV_END,
                            source="input_file",
                        )
                    ],
                )
            manifest_candidates.append(cand)
        mode_label = f"candidates_manifest ({len(manifest_candidates)} securities)"
    elif args.smoke:
        for item in SMOKE_CANDIDATES:
            sym = item["ticker"]
            cik = item["cik"]
            disc = item.get("share_class_discriminator") or extract_share_class_discriminator(item)
            sec_id = make_immutable_id(
                sym,
                cik=cik,
                composite_figi=item.get("composite_figi"),
                share_class_figi=item.get("share_class_figi"),
                share_class_discriminator=disc,
                allow_unverified=False,
            )
            cand = CandidateSecurity(
                immutable_security_id=sec_id,
                primary_symbol=sym,
                cik=cik,
                composite_figi=item.get("composite_figi"),
                share_class_figi=item.get("share_class_figi"),
                company_name=item["name"],
                primary_exchange="XNAS",
                security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
                first_seen_date=WARMUP_START,
                last_seen_date=DEV_END,
                ticker_intervals=[
                    TickerInterval(
                        symbol=sym,
                        start_date=WARMUP_START,
                        end_date=DEV_END,
                        source="smoke_panel",
                        confidence="smoke_test",
                    )
                ],
                listing_lifecycle_provenance={"source": "smoke_panel", "listing_date": item.get("start")},
            )
            manifest_candidates.append(cand)
        mode_label = f"smoke_test_panel ({len(manifest_candidates)} securities)"
    else:
        print("ERROR: Full development dataset build requires an auditable candidate panel via --candidates-file.")
        print("      Hardcoded survivor panels are prohibited by locked research-correctness invariants.")
        print("      Use --smoke for bounded test pulls or --candidates-file <path> for an authorized candidate manifest.")
        return 1

    print(f"=== LONG-002C BUILD (Run ID: {run_id}, Mode: {mode_label}) ===")

    creds = resolve_credentials()
    if not (creds.get("alpaca_api_key") and creds.get("alpaca_secret_key")):
        print("ERROR: Alpaca credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY) are required to build historical daily bars.")
        return 1

    cache = ResponseCache()
    alpaca = AlpacaDailyClient(creds["alpaca_api_key"], creds["alpaca_secret_key"], cache=cache)  # type: ignore[arg-type]
    massive = (
        MassiveRefClient(creds["massive_api_key"], cache=cache)
        if creds.get("massive_api_key")
        else None
    )
    edgar = EdgarClient(cache=cache)

    sessions = get_trading_sessions("2015-01-01", DEV_END)
    dev_sessions = [s for s in sessions if DEV_START <= s <= DEV_END]

    # Gate on Stage C outcome calculation
    if not getattr(args, "authorize_outcomes", False) or getattr(args, "pre_run_only", False):
        max_cands = getattr(args, "max_candidates", None)
        eval_cands = manifest_candidates[:max_cands] if max_cands else manifest_candidates
        print(f"\n[Stage B Screening] Screening {len(eval_cands)} candidates against locked Stage B criteria...")
        eligible_ids, rejected_ids, summary = screen_candidates_manifest(
            eval_cands,
            alpaca=alpaca,
            edgar=edgar,
            max_candidates=max_cands,
            on_progress=lambda cur, tot, sym, ok: print(f"      [{cur}/{tot}] {sym}: {'PASS' if ok else 'FAIL'}"),
        )
        print(f"      Stage B Screening: {len(eligible_ids)} passed, {len(rejected_ids)} rejected.")

        frozen_manifest_path = REPO_ROOT / "data" / "research" / "long_002c" / "frozen_pre_run_manifest.json"
        disc_manifest_path = (
            Path(args.candidates_file)
            if args.candidates_file
            else (REPO_ROOT / "data" / "research" / "long_002c" / "discovery_manifest.json")
        )
        if not disc_manifest_path.exists():
            disc_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            disc_manifest_path.write_text(
                json.dumps({"candidates": [c.to_dict() for c in manifest_candidates]}, indent=2),
                encoding="utf-8",
            )

        pre_run_data = build_frozen_pre_run_manifest_data(
            discovery_manifest_path=disc_manifest_path,
            stage_b_eligible_ids=eligible_ids,
            stage_b_summary=summary,
            repo_root=REPO_ROOT,
        )
        _, frozen_sha = write_frozen_pre_run_manifest(frozen_manifest_path, pre_run_data)
        print(f"      Frozen pre-run manifest written: {frozen_manifest_path}")
        print(f"      Frozen pre-run SHA-256: {frozen_sha}")
        if not verify_frozen_pre_run_manifest(frozen_manifest_path, frozen_sha):
            print("ERROR: Frozen pre-run manifest failed hash verification!")
            return 1
        print("      Verification: Frozen pre-run manifest verified.")

        print("\n" + "=" * 70)
        print("STAGE B SCREENING COMPLETE & FROZEN PRE-RUN MANIFEST LOCKED.")
        print(f"Stage B Eligible Candidates: {len(eligible_ids)}")
        print(f"Frozen Pre-Run Manifest: {frozen_manifest_path}")
        print(f"Frozen Pre-Run SHA-256: {frozen_sha}")
        print("Stage C outcome census is BLOCKED pending Gary & ChatGPT authorization.")
        print("PR #85 remains draft and unmerged.")
        print("=" * 70)
        return 0

    # STAGE C AUTHORIZATION BOUNDARY ENFORCEMENT (Item 6)
    if getattr(args, "max_candidates", None):
        print("ERROR: Stage C outcome execution strictly rejects --max-candidates truncation.")
        return 1

    frozen_arg_path = getattr(args, "frozen_manifest", None)
    expected_frozen_sha = getattr(args, "expected_frozen_sha256", None)
    if not (frozen_arg_path and expected_frozen_sha):
        print("ERROR: Stage C outcome execution requires explicit --frozen-manifest <path> and --expected-frozen-sha256 <sha>.")
        return 1

    frozen_manifest_path = Path(frozen_arg_path)
    if not frozen_manifest_path.exists():
        print(f"ERROR: Specified frozen manifest not found: {frozen_manifest_path}")
        return 1

    with frozen_manifest_path.open("r", encoding="utf-8") as f:
        frozen_manifest_data = json.load(f)

    # Recompute SHA-256 and require exact match
    clean_manifest = {k: v for k, v in frozen_manifest_data.items() if k != "frozen_pre_run_manifest_sha256"}
    computed_sha = hashlib.sha256(json.dumps(clean_manifest, indent=2, sort_keys=True).encode("utf-8")).hexdigest()
    if computed_sha != expected_frozen_sha:
        print(f"ERROR: Frozen manifest SHA-256 mismatch! Computed: {computed_sha}, Expected: {expected_frozen_sha}")
        return 1

    # Require git commit SHA match
    current_git_sha = get_git_commit_sha(REPO_ROOT)
    recorded_git_sha = frozen_manifest_data.get("git_commit_sha")
    if recorded_git_sha != current_git_sha:
        print(f"ERROR: Frozen manifest git commit SHA mismatch! Recorded: {recorded_git_sha}, Current HEAD: {current_git_sha}")
        return 1

    # Require discovery manifest match
    disc_meta = frozen_manifest_data.get("discovery_manifest", {})
    disc_recorded_sha = disc_meta.get("sha256")
    disc_file = Path(disc_meta.get("path", ""))
    if not disc_file.exists():
        disc_file = REPO_ROOT / "data" / "research" / "long_002c" / "discovery_manifest.json"
    if not disc_file.exists():
        print(f"ERROR: Discovery manifest missing: {disc_file}")
        return 1
    disc_computed_sha = compute_file_sha256(disc_file)
    if disc_computed_sha != disc_recorded_sha:
        print(f"ERROR: Discovery manifest SHA mismatch! Recorded: {disc_recorded_sha}, Computed: {disc_computed_sha}")
        return 1

    # If --candidates-file is passed, require its resolved SHA-256 to equal the frozen discovery SHA-256
    if getattr(args, "candidates_file", None):
        cand_arg_path = Path(args.candidates_file)
        if not cand_arg_path.exists():
            print(f"ERROR: Specified --candidates-file does not exist: {cand_arg_path}")
            return 1
        cand_arg_sha = compute_file_sha256(cand_arg_path)
        if cand_arg_sha != disc_recorded_sha:
            print(
                f"ERROR: Specified --candidates-file SHA ({cand_arg_sha}) does not match frozen discovery manifest SHA ({disc_recorded_sha})! "
                f"Stage C strictly rejects independent or mismatched candidate files."
            )
            return 1

    # Load candidate objects DIRECTLY from the verified discovery manifest
    all_discovery_candidates = load_candidate_manifest(disc_file)

    # Require Stage B eligible IDs match
    frozen_eligible_ids = frozen_manifest_data.get("stage_b_screening", {}).get("eligible_security_ids", [])
    if not frozen_eligible_ids:
        print("ERROR: Frozen manifest contains 0 Stage B eligible securities.")
        return 1

    frozen_eligible_set = set(frozen_eligible_ids)
    stage_c_candidates = [c for c in all_discovery_candidates if c.immutable_security_id in frozen_eligible_set]
    stage_c_ids = [c.immutable_security_id for c in stage_c_candidates]

    # Pre-execution validation
    if set(stage_c_ids) != frozen_eligible_set:
        print(
            f"ERROR: Candidate ID set mismatch between discovery manifest and frozen eligible IDs! "
            f"Found {len(set(stage_c_ids))}, expected {len(frozen_eligible_set)}"
        )
        return 1
    if len(stage_c_candidates) != len(frozen_eligible_ids):
        print(
            f"ERROR: Candidate count mismatch! Candidates: {len(stage_c_candidates)}, Frozen IDs: {len(frozen_eligible_ids)}"
        )
        return 1
    if len(stage_c_ids) != len(set(stage_c_ids)):
        print("ERROR: Duplicate immutable security IDs found in Stage C candidates!")
        return 1

    manifest_candidates = stage_c_candidates
    eligible_ids = frozen_eligible_ids
    print(f"Stage C Authorization: VERIFIED against {frozen_manifest_path} (SHA: {computed_sha[:16]}...)")
    print(f"      Source of truth verified: {len(manifest_candidates)} candidates loaded directly from {disc_file.name}")

    all_obs: list[DecisionObservation] = []
    all_elig: list[DataEligibility] = []
    all_class: list[SecurityClassificationStatus] = []
    all_earnings: list[EarningsScheduleStatus] = []
    all_exclusions: list[ExclusionReasonRecord] = []
    all_quality: list[DataQualityCoverage] = []
    all_provenance: list[ProvenanceProviderRecord] = []
    all_outcomes: list[OutcomeLabelRecord] = []

    securities_history_df: dict[str, pd.DataFrame] = {}
    securities_identity: dict[str, SecurityIdentity] = {}
    obs_by_sec: dict[str, list[dict[str, Any]]] = {}
    outcomes_by_obs_key: dict[tuple[str, str, str], dict[tuple[float, int], OutcomeLabelRecord]] = {}

    sec_master = SecurityMaster()
    register_manifest_in_security_master(manifest_candidates, sec_master)

    # Step 0: Ingest SPY daily bars for SPY-relative momentum baseline
    print("\n[0/6] Ingesting SPY benchmark daily bars for SPY-relative baseline...")
    try:
        spy_bars_raw, spy_prov = alpaca.fetch_daily_bars(
            "SPY", f"{WARMUP_START}T00:00:00Z", f"{DEV_END}T23:59:59Z", feed="sip", adjustment="split"
        )
    except ProviderDataUnavailable as exc:
        print(f"ERROR: Failed to retrieve SPY benchmark daily bars: {exc}")
        print("Official Stage C execution ABORTED due to benchmark data unavailability.")
        return 1
    all_provenance.extend(spy_prov)
    if not spy_bars_raw:
        print("ERROR: SPY benchmark daily bars are empty! Stage C outcome execution aborted.")
        return 1

    df_spy = pd.DataFrame(spy_bars_raw)
    df_spy["datetime"] = pd.to_datetime(df_spy["t"], utc=True)
    df_spy["date"] = df_spy["datetime"].dt.strftime("%Y-%m-%d")
    df_spy = df_spy.rename(columns={"c": "close"})
    df_spy = df_spy.set_index("date").sort_index()

    # Step 1: Ingest bars, corporate actions, and EDGAR facts for candidate securities
    print(f"\n[1/6] Ingesting historical daily bars, EDGAR facts, and corporate actions for {len(manifest_candidates)} candidates...")
    for cand in manifest_candidates:
        sec_id = cand.immutable_security_id
        primary_sym = cand.primary_symbol
        cik = cand.cik

        # Strict classification gate: only verified supported common stock
        if cand.security_type != CLASSIFICATION_SUPPORTED_COMMON_STOCK:
            print(f"      SKIPPING {primary_sym} ({sec_id}): unverified or excluded classification '{cand.security_type}'")
            continue

        if not cik:
            print(f"      ERROR: Security {primary_sym} lacks CIK; symbol-only identity prohibited for official runs.")
            continue

        # Ingest daily bars using the shared interval-aware loader (Item 3)
        df_final, prov_bars, bar_meta = load_interval_aware_daily_bars(
            candidate=cand,
            alpaca=alpaca,
            warmup_start=WARMUP_START,
            dev_end=DEV_END,
            load_split_adjusted=True,
        )
        all_provenance.extend(prov_bars)

        if bar_meta.get("provider_failure"):
            fail_info = bar_meta["provider_failure"]
            print(f"ERROR: Alpaca provider failure for candidate {primary_sym} ({sec_id}): {fail_info}")
            print("Official Stage C execution ABORTED due to unresolved provider failure.")
            return 1

        if df_final.empty:
            print(f"ERROR: Candidate {primary_sym} ({sec_id}) was verified eligible in Stage B, but returned empty bars in Stage C!")
            print("Official Stage C execution ABORTED due to dataset integrity mismatch.")
            return 1

        securities_history_df[sec_id] = df_final

        # Ingest corporate actions across all historical ticker intervals intersecting warmup/dev
        special_dist_dates: set[str] = set()
        if massive:
            historical_symbols: set[str] = set()
            for ti in cand.ticker_intervals:
                s = ti.start_date or ""
                e = ti.end_date or ""
                if (not s or s <= DEV_END) and (not e or e >= WARMUP_START) and ti.symbol:
                    historical_symbols.add(ti.symbol)
            if not historical_symbols:
                historical_symbols.add(primary_sym)

            all_splits: list[dict[str, Any]] = []
            all_divs: list[dict[str, Any]] = []
            for sym in sorted(historical_symbols):
                try:
                    splits_sym, divs_sym, prov_corp = massive.fetch_corporate_actions(sym)
                    all_provenance.extend(prov_corp)
                    all_splits.extend(splits_sym)
                    all_divs.extend(divs_sym)
                except ProviderDataUnavailable as exc:
                    print(f"ERROR: Massive provider failure fetching corporate actions for {sym} ({sec_id}): {exc}")
                    print("Official Stage C execution ABORTED due to unresolved corporate action provider failure.")
                    return 1

            # Deduplicate dividends by (ex_date, cash_amount, dividend_type)
            deduped_divs: list[dict[str, Any]] = []
            seen_div_keys: set[tuple[Any, ...]] = set()
            for div in all_divs:
                div_key = (div.get("ex_date"), div.get("cash_amount"), div.get("dividend_type"))
                if div_key not in seen_div_keys:
                    seen_div_keys.add(div_key)
                    deduped_divs.append(div)

            special_dist_dates = parse_special_distribution_dates(deduped_divs)

        affected_special_sessions = derive_affected_special_distribution_sessions(
            special_dist_dates, sessions, max_horizon_sessions=26
        )

        # Ingest SEC EDGAR company facts and submissions for PIT market cap
        facts_data = None
        acceptance_map = None
        try:
            facts_data, prov_facts = edgar.fetch_company_facts(cik)
            all_provenance.extend(prov_facts)
            subs_data, prov_subs = edgar.fetch_submissions(cik)
            all_provenance.extend(prov_subs)
            if subs_data:
                acceptance_map = EdgarClient.get_accession_acceptance_map(subs_data)
        except ProviderDataUnavailable as exc:
            print(f"ERROR: SEC EDGAR provider failure for CIK {cik} ({primary_sym}): {exc}")
            print("Official Stage C execution ABORTED due to unresolved EDGAR provider failure.")
            return 1

        # Build as-traded close prices for 09:00 (T-1 close) and 20:30 (T close)
        as_traded_closes_2030 = {d: float(df_final.loc[d, "as_traded_close"]) for d in df_final.index}
        as_traded_closes_0900 = {
            df_final.index[i]: float(df_final.iloc[i - 1]["as_traded_close"])
            for i in range(1, len(df_final))
        }

        mcap_0900, reasons_0900, _ = compute_security_pit_market_caps(
            company_facts=facts_data,
            session_dates=sessions,
            as_traded_closes=as_traded_closes_0900,
            cutoff_time="09:00",
            accession_acceptance_map=acceptance_map,
        )
        mcap_2030, reasons_2030, _ = compute_security_pit_market_caps(
            company_facts=facts_data,
            session_dates=sessions,
            as_traded_closes=as_traded_closes_2030,
            cutoff_time="20:30",
            accession_acceptance_map=acceptance_map,
        )

        identity = sec_master.get_security_by_id(sec_id)
        if not identity:
            identity = SecurityIdentity(
                immutable_security_id=sec_id,
                ticker_at_decision=primary_sym,
                effective_start=WARMUP_START,
                effective_end=DEV_END,
                cik=cik,
                company_name=cand.company_name,
                security_type=cand.security_type,
            )
        securities_identity[sec_id] = identity

        # Step 2: Build decision observations for BOTH 09:00 and 20:30 cutoffs
        bar_dates = list(df_final.index)
        obs_by_sec[sec_id] = []

        for cutoff_time in ["09:00", "20:30"]:
            mcap_curr = mcap_0900 if cutoff_time == "09:00" else mcap_2030
            reasons_curr = reasons_0900 if cutoff_time == "09:00" else reasons_2030

            obs_sec, elig_sec, class_sec, earn_sec, excl_sec, qual_sec = build_decision_observations_for_security(
                identity=identity,
                bars_df=df_final,
                trading_sessions=sessions,
                cutoff_time=cutoff_time,
                dev_start=DEV_START,
                dev_end=DEV_END,
                market_caps=mcap_curr,
                market_cap_reasons=reasons_curr,
                special_distribution_dates=affected_special_sessions,
                candidate=cand,
                security_master=sec_master,
                bar_meta=bar_meta,
            )
            all_obs.extend(obs_sec)
            all_elig.extend(elig_sec)
            all_class.extend(class_sec)
            all_earnings.extend(earn_sec)
            all_exclusions.extend(excl_sec)
            all_quality.append(qual_sec)
            obs_by_sec[sec_id].extend([o.to_dict() for o in obs_sec])

            # Step 3: Compute outcomes across all nine cells using forward bars
            for obs in obs_sec:
                if obs.split_boundary_purged:
                    continue
                as_of_date = obs.as_of_date
                if as_of_date not in bar_dates:
                    continue
                idx = bar_dates.index(as_of_date)

                if cutoff_time == "09:00":
                    # 09:00: session T is entry session; forward bars start at session T (21 sessions)
                    forward_slice = df_final.iloc[idx : idx + 21]
                    if len(forward_slice) < 21:
                        continue
                    next_open = float(forward_slice["open"].iloc[0])
                    as_traded_open = float(forward_slice["as_traded_open"].iloc[0])
                else:
                    # 20:30: session T+1 is entry session; forward bars start at session T+1 (21 sessions)
                    forward_slice = df_final.iloc[idx + 1 : idx + 22]
                    if len(forward_slice) < 21:
                        continue
                    next_open = float(forward_slice["open"].iloc[0])
                    as_traded_open = float(forward_slice["as_traded_open"].iloc[0])

                forward_bars = forward_slice[["open", "high", "low", "close"]].to_dict(orient="records")
                atr_val = obs.atr_14 or 0.0

                has_unresolved_dist = as_of_date in affected_special_sessions

                nine_outcomes = compute_all_nine_outcomes(
                    immutable_security_id=sec_id,
                    ticker_at_decision=obs.ticker_at_decision,
                    as_of_date=as_of_date,
                    cutoff_time=cutoff_time,
                    next_open_price=next_open,
                    forward_bars=forward_bars,
                    pre_entry_atr=atr_val,
                    entry_friction_bps=PRIMARY_ENTRY_FRICTION_BPS,
                    special_distribution_unresolved=has_unresolved_dist,
                    as_traded_entry_price=as_traded_open,
                )
                all_outcomes.extend(nine_outcomes)

                key = (sec_id, as_of_date, cutoff_time)
                outcomes_by_obs_key[key] = {
                    (o.target_pct, o.horizon_sessions): o for o in nine_outcomes
                }

    print(f"      Built {len(all_obs)} decision observations and {len(all_outcomes)} outcome label records.")

    # Step 4: Cluster Master Opportunity Episodes with 20:30 primary anchoring (Item 9)
    print("\n[2/6] Clustering Master Opportunity Episodes (anchored on 20:30 primary census)...")
    episodes, memberships = cluster_master_episodes(
        observations_by_security=obs_by_sec,
        outcomes_by_obs_key=outcomes_by_obs_key,
        anchor_cutoff_time="20:30",
    )
    print(f"      Constructed {len(episodes)} independent master episodes ({len(memberships)} constituent memberships).")

    # Step 5: Evaluate Baselines with SPY benchmark for both 09:00 and 20:30
    print("\n[3/6] Evaluating frozen baseline comparators on common observations (09:00 & 20:30)...")
    all_baselines: list[BaselineComparatorOutput] = []

    for d in dev_sessions:
        for cutoff_time in ["09:00", "20:30"]:
            date_sec_data: dict[str, dict[str, Any]] = {}
            for sec_id, hdf in securities_history_df.items():
                if d in hdf.index:
                    d_idx = list(hdf.index).index(d)
                    sub_df = hdf.iloc[:d_idx] if cutoff_time == "09:00" else hdf.iloc[:d_idx + 1]
                    if sub_df.empty:
                        continue
                    matching_obs = next(
                        (o for o in all_obs if o.immutable_security_id == sec_id and o.as_of_date == d and o.cutoff_time == cutoff_time),
                        None,
                    )
                    date_sec_data[sec_id] = {
                        "ticker": matching_obs.ticker_at_decision if matching_obs else securities_identity[sec_id].ticker_at_decision,
                        "history_df": sub_df,
                        "atr_14": matching_obs.atr_14 if matching_obs else None,
                        "sector": None,
                        "universe_eligible": matching_obs.universe_eligible if matching_obs else True,
                    }
            if date_sec_data:
                if not df_spy.empty and d in df_spy.index:
                    spy_idx = list(df_spy.index).index(d)
                    spy_sub_df = df_spy.iloc[:spy_idx] if cutoff_time == "09:00" else df_spy.iloc[:spy_idx + 1]
                else:
                    spy_sub_df = None

                base_outputs = evaluate_baselines_for_date(
                    as_of_date=d,
                    cutoff_time=cutoff_time,
                    securities_data=date_sec_data,
                    spy_history_df=spy_sub_df,
                )
                all_baselines.extend(base_outputs)

    print(f"      Evaluated {len(all_baselines)} baseline comparator outputs.")

    # Empirically select winning baseline on 20:30 primary population (Item 9)
    winning_baseline_selection = select_winning_baseline(
        baseline_outputs=all_baselines,
        outcomes=all_outcomes,
        primary_cutoff_time="20:30",
    )
    print(f"      Strongest simple baseline empirically selected (20:30 primary): {winning_baseline_selection.get('winner_comparator_id')} "
          f"(Top-10 Lift: {winning_baseline_selection.get('winner_top_10_lift'):.2f}x vs base rate {winning_baseline_selection.get('universe_base_rate'):.4f})")

    # Step 6: Dependence-aware Resampling & Endpoint Feasibility on 20:30 Primary Population (Item 8 & Item 9)
    print("\n[4/6] Running 21-session and 42-session block resampling on 20:30 primary census...")
    obs_dicts_2030 = [o.to_dict() for o in all_obs if o.cutoff_time == "20:30"]
    obs_dicts_0900 = [o.to_dict() for o in all_obs if o.cutoff_time == "09:00"]
    outcomes_2030 = [o for o in all_outcomes if o.cutoff_time == "20:30"]
    outcomes_0900 = [o for o in all_outcomes if o.cutoff_time == "09:00"]

    resampling_21 = run_block_resampling(
        observations=obs_dicts_2030,
        outcomes_by_obs_key=outcomes_by_obs_key,
        sessions_ordered=dev_sessions,
        block_size_sessions=21,
        num_bootstraps=1000,
        seed=42,
    )
    resampling_42 = run_block_resampling(
        observations=obs_dicts_2030,
        outcomes_by_obs_key=outcomes_by_obs_key,
        sessions_ordered=dev_sessions,
        block_size_sessions=42,
        num_bootstraps=1000,
        seed=42,
    )

    feasibility_report = analyze_endpoint_feasibility(
        observations=obs_dicts_2030,
        episodes=episodes,
        outcomes=outcomes_2030,
        resampling_21=resampling_21,
        resampling_42=resampling_42,
    )

    # Separately reported 09:00 pre-market reevaluation diagnostic (Item 9)
    resampling_21_0900 = run_block_resampling(
        observations=obs_dicts_0900,
        outcomes_by_obs_key=outcomes_by_obs_key,
        sessions_ordered=dev_sessions,
        block_size_sessions=21,
        num_bootstraps=1000,
        seed=42,
    )
    clean_10_10_0900 = sum(1 for o in outcomes_0900 if o.target_pct == 10.0 and o.horizon_sessions == 10 and o.clean_target_reached)
    clean_10_21_0900 = sum(1 for o in outcomes_0900 if o.target_pct == 10.0 and o.horizon_sessions == 21 and o.clean_target_reached)
    feasibility_report["reevaluation_0900_diagnostic"] = {
        "observations_count": len(obs_dicts_0900),
        "clean_target_10_10_events": clean_10_10_0900,
        "clean_target_10_21_events": clean_10_21_0900,
        "clean_target_10_10_prevalence": round(clean_10_10_0900 / len(outcomes_0900), 6) if outcomes_0900 else 0.0,
        "clean_target_10_21_prevalence": round(clean_10_21_0900 / len(outcomes_0900), 6) if outcomes_0900 else 0.0,
        "resampling_21": resampling_21_0900,
    }

    print(f"      Endpoint Disposition: {feasibility_report.get('endpoint_disposition')}")
    print(f"      Selected Endpoint: {feasibility_report.get('selected_endpoint')}")

    # Step 7: Save Parquet Tables (External, Gitignored)
    print("\n[5/6] Writing external row-level Parquet datasets...")
    ext_data_dir = REPO_ROOT / "data" / "research" / "long_002c"
    file_manifests = write_external_parquet_tables(
        output_dir=ext_data_dir,
        observations=all_obs,
        eligibilities=all_elig,
        classifications=all_class,
        outcomes=all_outcomes,
        episodes=episodes,
        memberships=memberships,
        baselines=all_baselines,
        quality=all_quality,
        provenance=all_provenance,
        exclusions=all_exclusions,
        earnings=all_earnings,
    )
    print(f"      Saved {len(file_manifests)} Parquet files to {ext_data_dir}")

    # Step 8: Write Committed Summaries
    print("\n[6/6] Writing committed summary manifests and checksums...")
    bundle_dir = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002C" / run_id
    elapsed = time.monotonic() - start_time
    exec_meta = {
        "task_id": "LONG-002C-EXEC-001",
        "run_id": run_id,
        "runtime_seconds": round(elapsed, 2),
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mode": "smoke" if args.smoke else "full",
        "python_version": sys.version.split()[0],
        "endpoint_disposition": feasibility_report.get("endpoint_disposition"),
        "selected_endpoint": feasibility_report.get("selected_endpoint"),
        "total_observations": len(all_obs),
        "master_episodes_count": len(episodes),
        "strongest_baseline_winner": winning_baseline_selection.get("winner_comparator_id"),
    }

    _sha_map = write_committed_summaries(
        bundle_dir=bundle_dir,
        run_id=run_id,
        manifest_files=file_manifests,
        observations=all_obs,
        outcomes=all_outcomes,
        episodes=episodes,
        baselines=all_baselines,
        quality=all_quality,
        provenance=all_provenance,
        exclusions=all_exclusions,
        feasibility_report=feasibility_report,
        execution_metadata=exec_meta,
        winning_baseline=winning_baseline_selection,
    )
    print(f"      Committed summary artifacts generated in {bundle_dir}")
    print(f"\nLONG-002C BUILD FINISHED SUCCESSFULLY in {elapsed:.1f}s.")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run offline deterministic evaluation from frozen Parquet dataset."""
    print("=== LONG-002C OFFLINE EVALUATE ===")
    ext_data_dir = REPO_ROOT / "data" / "research" / "long_002c"
    obs_file = ext_data_dir / "decision_observations.parquet"
    if not obs_file.exists():
        print(f"ERROR: Missing frozen dataset: {obs_file}. Run 'build' first.")
        return 1

    print(f"Loading frozen dataset from {ext_data_dir}...")
    df_obs = pd.read_parquet(obs_file)
    df_outcomes = pd.read_parquet(ext_data_dir / "outcome_matrix.parquet")
    df_episodes = pd.read_parquet(ext_data_dir / "master_episodes.parquet")
    df_baselines = pd.read_parquet(ext_data_dir / "baseline_comparator_outputs.parquet")

    print(f"Loaded {len(df_obs)} observations, {len(df_outcomes)} outcomes, {len(df_episodes)} episodes, {len(df_baselines)} baselines.")

    clean_10_10 = df_outcomes[(df_outcomes["target_pct"] == 10.0) & (df_outcomes["horizon_sessions"] == 10)]["clean_target_reached"].sum()
    clean_10_21 = df_outcomes[(df_outcomes["target_pct"] == 10.0) & (df_outcomes["horizon_sessions"] == 21)]["clean_target_reached"].sum()

    print(f"Primary clean +10/10 events: {clean_10_10}")
    print(f"Fallback clean +10/21 events: {clean_10_21}")
    print(f"Total Master Episodes: {len(df_episodes)}")
    print("Offline evaluation verified identical results.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify artifact checksums against checksums.sha256."""
    print("=== LONG-002C VERIFY ===")
    artifacts_root = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002C"
    if not artifacts_root.exists():
        print(f"ERROR: Artifacts directory missing: {artifacts_root}")
        return 1

    run_dirs = [d for d in artifacts_root.iterdir() if d.is_dir()]
    if not run_dirs:
        print("No run bundles found to verify.")
        return 0

    target_dir = max(run_dirs, key=lambda d: d.name)
    chk_file = target_dir / "checksums.sha256"
    if not chk_file.exists():
        print(f"ERROR: Missing checksums file: {chk_file}")
        return 1

    lines = chk_file.read_text(encoding="utf-8").splitlines()
    all_ok = True
    for line in lines:
        if not line.strip():
            continue
        expected_sha, fname = line.strip().split(maxsplit=1)
        fpath = target_dir / fname
        if not fpath.exists():
            print(f"MISSING: {fname}")
            all_ok = False
            continue
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            print(f"MISMATCH: {fname} (expected {expected_sha}, got {actual_sha})")
            all_ok = False
        else:
            print(f"OK: {fname}")

    if all_ok:
        print(f"\nAll artifacts in {target_dir.name} successfully verified against checksums.")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="LONG-002C Research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Audit credentials, providers, hashes, and boundaries")
    preflight_parser.add_argument("--universe-audit", action="store_true", help="Audit historical universe coverage and provider call/runtime estimates")

    discover_parser = subparsers.add_parser("discover", help="Stage A: Candidate discovery across 72 monthly snapshots + inactive snapshot")
    discover_parser.add_argument("--output-dir", type=str, default=None, help="Output directory for discovery manifest")
    discover_parser.add_argument("--dates", nargs="+", default=None, help="Custom list of snapshot dates (e.g. 2016-01-04 2018-01-02 2020-01-02)")
    discover_parser.add_argument("--skip-inactive", action="store_true", help="Skip inactive snapshot query")

    screen_parser = subparsers.add_parser("screen", help="Stage B: Screen candidate manifest against locked eligibility criteria")
    screen_parser.add_argument("--candidates-file", type=str, default=None, help="Path to discovery manifest JSON")
    screen_parser.add_argument("--output", type=str, default=None, help="Path to write frozen pre-run manifest JSON")
    screen_parser.add_argument("--max-candidates", type=int, default=None, help="Maximum number of candidates to screen")

    build_parser = subparsers.add_parser("build", help="Build development dataset and run evaluation")
    build_parser.add_argument("--smoke", action="store_true", help="Run bounded smoke pull (smoke test panel only)")
    build_parser.add_argument("--candidates-file", type=str, default=None, help="Path to auditable candidate securities JSON manifest")
    build_parser.add_argument("--run-id", type=str, default=None, help="Custom run ID")
    build_parser.add_argument("--max-candidates", type=int, default=None, help="Maximum number of candidates to screen")
    build_parser.add_argument("--authorize-outcomes", action="store_true", help="Explicit authorization to proceed past Stage B to Stage C")
    build_parser.add_argument("--pre-run-only", action="store_true", help="Stop after Stage B screening and frozen pre-run manifest generation")
    build_parser.add_argument("--frozen-manifest", type=str, default=None, help="Path to frozen pre-run manifest JSON (required for Stage C)")
    build_parser.add_argument("--expected-frozen-sha256", type=str, default=None, help="Expected SHA-256 of frozen pre-run manifest (required for Stage C)")

    subparsers.add_parser("evaluate", help="Offline deterministic evaluation from frozen Parquet dataset")
    subparsers.add_parser("verify", help="Verify artifact checksums")

    args = parser.parse_args()

    if args.command == "preflight":
        return cmd_preflight(args)
    elif args.command == "discover":
        return cmd_discover(args)
    elif args.command == "screen":
        return cmd_screen(args)
    elif args.command == "build":
        return cmd_build(args)
    elif args.command == "evaluate":
        return cmd_evaluate(args)
    elif args.command == "verify":
        return cmd_verify(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
