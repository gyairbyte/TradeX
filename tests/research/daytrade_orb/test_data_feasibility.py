"""Comprehensive deterministic offline tests for DAYTRADE-003D data feasibility and acquisition.

Verifies Massive and Alpaca client contracts, batching, pagination, data quality,
candidate pool completeness, Stage-A/B boundaries, and artifact safety using
injected mocks with zero network access and zero credentials.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.research.daytrade_orb.data_feasibility import (
    PROBE_DATES,
    FeasibilityDisposition,
    audit_candidate_pool_completeness,
    audit_exchange_distribution,
    audit_stage_b_path,
    audit_type_distribution,
    batch_symbols,
    calculate_pilot_resource_plan,
    compute_and_freeze_stage_a_selection,
    compute_full_year_estimate,
    determine_top_level_disposition,
    filter_target_universe,
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
    Direction,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)
from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

MARKET_TIMEZONE = ZoneInfo("America/New_York")


# =============================================================================
# Upstream Specification & Calendar Tests
# =============================================================================

def test_upstream_spec_hashes(tmp_path: Path) -> None:
    """Verify that verify_upstream_spec_hashes validates matching files and fails on mismatch."""
    repo_root = Path(__file__).resolve().parents[3]
    ok, sha_b, sha_c, errors = verify_upstream_spec_hashes(repo_root)
    assert ok is True
    assert sha_b == "62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0"
    assert sha_c == "20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6"
    assert errors == []


def test_fixed_probe_dates_xnys_sessions() -> None:
    """Verify all 3 fixed probe dates are regular full XNYS sessions."""
    from tradex.market.hours import get_market_session
    for dt_str in PROBE_DATES:
        dt = date.fromisoformat(dt_str)
        sess = get_market_session(dt)
        assert sess is not None, f"{dt_str} must be an XNYS session"
        assert sess.is_early_close is False, f"{dt_str} must not be an early close"


# =============================================================================
# Massive Universe & Exchange Mapping Tests
# =============================================================================

def test_audit_exchange_and_type_distribution() -> None:
    rows = [
        {"ticker": "AAPL", "primary_exchange": "XNAS", "type": "CS"},
        {"ticker": "IBM", "primary_exchange": "XNYS", "type": "CS"},
        {"ticker": "SPY", "primary_exchange": "ARCX", "type": "ETF"},
        {"ticker": "QQQ", "primary_exchange": "XNAS", "type": "ETF"},
        {"ticker": "UNK", "primary_exchange": None, "type": None},
    ]
    ex_dist = audit_exchange_distribution(rows)
    assert ex_dist["XNAS"] == 2
    assert ex_dist["XNYS"] == 1
    assert ex_dist["ARCX"] == 1
    assert ex_dist["EMPTY"] == 1

    type_dist = audit_type_distribution(rows)
    assert type_dist["CS"] == 2
    assert type_dist["ETF"] == 2
    assert type_dist["EMPTY"] == 1


def test_filter_target_universe_nyse_nasdaq() -> None:
    rows = [
        {"ticker": "AAPL", "primary_exchange": "XNAS", "type": "CS"},
        {"ticker": "MSFT", "primary_exchange": "xnas", "type": "CS"},
        {"ticker": "IBM", "primary_exchange": "XNYS", "type": "CS"},
        {"ticker": "SPY", "primary_exchange": "ARCX", "type": "ETF"},  # Excluded
        {"ticker": "BATS1", "primary_exchange": "BATS", "type": "CS"},  # Excluded
        {"ticker": "  ", "primary_exchange": "XNAS", "type": "CS"},     # Blank
        {"ticker": "AAPL", "primary_exchange": "XNAS", "type": "CS"},  # Duplicate
    ]
    symbols, _target_map, ev = filter_target_universe(rows, allowed_exchanges=("XNYS", "XNAS"))

    assert symbols == ["AAPL", "IBM", "MSFT"]
    assert "SPY" not in symbols
    assert "BATS1" not in symbols
    assert ev.target_universe_count == 3
    assert ev.target_exchange_distribution == {"XNAS": 3, "XNYS": 1}  # occurrences
    assert ev.excluded_exchange_distribution["ARCX"] == 1
    assert ev.excluded_exchange_distribution["BATS"] == 1
    assert ev.blank_ticker_count == 1
    assert ev.duplicate_ticker_count == 1
    assert ev.universe_sha256 != ""


# =============================================================================
# Resource Planning & Extrapolation Tests
# =============================================================================

def test_calculate_pilot_resource_plan_bounds() -> None:
    # Within bounds: 5,000 symbols, batch size 100 -> 50 batches
    # 50 daily + 50 * 15 OR + 1 Stage B = 801 pages + 36 Massive = 837 pages <= 1000
    plan_ok = calculate_pilot_resource_plan(5000, batch_size=100, massive_pages_actual=36)
    assert plan_ok.universe_size == 5000
    assert plan_ok.batch_count == 50
    assert plan_ok.total_planned_pages == 837
    assert plan_ok.is_within_bounds is True
    assert plan_ok.exceeds_pages_limit is False

    # Exceeds bounds: 6,500 symbols -> 65 batches
    # 65 daily + 65 * 15 OR + 1 Stage B = 1041 pages + 36 = 1077 > 1000
    plan_exceed = calculate_pilot_resource_plan(6500, batch_size=100, massive_pages_actual=36)
    assert plan_exceed.total_planned_pages > 1000
    assert plan_exceed.exceeds_pages_limit is True
    assert plan_exceed.is_within_bounds is False


def test_compute_full_year_estimate() -> None:
    est = compute_full_year_estimate(
        pilot_universe_size=5000,
        pilot_massive_pages=12,
        pilot_alpaca_pages=850,
        pilot_private_bytes=10_000_000,
        pilot_elapsed_seconds=300.0,
        full_year_sessions_count=249,
    )
    assert est.full_year_sessions_count == 249
    assert est.extrapolated_massive_snapshots == 249
    assert est.extrapolated_massive_pages == 249 * 12
    assert est.extrapolated_alpaca_total_pages == 249 * 850
    assert est.extrapolated_storage_bytes == 249 * 10_000_000
    assert est.extrapolated_runtime_hours > 0.0


# =============================================================================
# Alpaca Batching & Normalization Tests
# =============================================================================

def test_batch_symbols_deterministic() -> None:
    symbols = ["MSFT", "AAPL", "GOOG", "AMZN", "AAPL", "TSLA"]
    batches = batch_symbols(symbols, batch_size=2)
    assert batches == [["AAPL", "AMZN"], ["GOOG", "MSFT"], ["TSLA"]]


def test_alpaca_mock_retry_and_rate_limit() -> None:
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "1"}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-02T14:30:00Z", "o": 180.0, "h": 181.0, "l": 179.5, "c": 180.5, "v": 10000}
            ]
        },
        "next_page_token": None,
    }

    client = DatasetAlpacaClient(
        api_key="test_key",
        secret_key="test_secret",
        max_retries=1,
        request_func=MagicMock(side_effect=[mock_resp_429, mock_resp_200]),
    )

    dfs, meta = client.get_bars(
        symbols=["AAPL"],
        start_utc=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        end_utc=datetime(2024, 1, 2, 14, 34, tzinfo=UTC),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        sleeper=lambda _: None,
    )
    assert "AAPL" in dfs
    assert len(dfs["AAPL"]) == 1
    assert meta["http_429s"] == 1
    assert meta["http_attempts"] == 2
    assert meta["pagination_complete"] is True


def test_alpaca_mock_malformed_timestamp_detected() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "bars": {
            "AAPL": [
                {"t": "invalid_date", "o": 180.0, "h": 181.0, "l": 179.5, "c": 180.5, "v": 10000},
                {"t": "2024-01-02T14:31:00Z", "o": 180.5, "h": 181.0, "l": 180.0, "c": 180.8, "v": 5000},
            ]
        },
        "next_page_token": None,
    }

    client = DatasetAlpacaClient(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(return_value=mock_resp),
    )

    dfs, meta = client.get_bars(
        symbols=["AAPL"],
        start_utc=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        end_utc=datetime(2024, 1, 2, 14, 34, tzinfo=UTC),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        sleeper=lambda _: None,
    )
    assert meta["malformed_timestamp_counts"]["AAPL"] == 1
    assert len(dfs["AAPL"]) == 1  # invalid row dropped


def test_alpaca_mock_repeated_token_cycle_detected() -> None:
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        "bars": {"AAPL": []},
        "next_page_token": "token_repeat",
    }
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        "bars": {"AAPL": []},
        "next_page_token": "token_repeat",
    }

    client = DatasetAlpacaClient(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=[mock_resp_1, mock_resp_2]),
    )

    _dfs, meta = client.get_bars(
        symbols=["AAPL"],
        start_utc=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        end_utc=datetime(2024, 1, 2, 14, 34, tzinfo=UTC),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        sleeper=lambda _: None,
    )
    assert meta["pagination_cycle_detected"] is True
    assert meta["pagination_complete"] is False


# =============================================================================
# Stage-A Candidate Pool Completeness & Indicator Tests
# =============================================================================

def test_audit_candidate_pool_completeness_100_percent() -> None:
    target_date = date(2024, 1, 2)
    prior_dates = get_prior_xnys_sessions(target_date, 14)
    # Contiguous 20 daily sessions ending at D-1
    all_daily_dates = get_prior_xnys_sessions(target_date, 20)

    symbols = ["AAPL", "MSFT"]
    daily_bars_by_symbol = {}
    prior_or_by_symbol = {}
    current_or_by_symbol = {}

    for sym in symbols:
        daily_bars_by_symbol[sym] = [
            DailyBar(sym, d, 100.0, 105.0, 95.0, 102.0, 2_000_000) for d in all_daily_dates
        ]
        prior_or_by_symbol[sym] = [
            OpeningRangeVolumeObservation(sym, d, 50_000.0) for d in prior_dates
        ]
        current_or_by_symbol[sym] = OpeningRange(
            symbol=sym,
            session_date=target_date,
            or_open=100.0,
            or_high=102.0,
            or_low=99.0,
            or_close=101.5,
            or_volume=60_000.0,
            direction=Direction.LONG,
            stop_level=102.0,
        )

    ev, reasons = audit_candidate_pool_completeness(
        target_universe=symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=target_date,
        required_lookback=14,
    )

    assert ev.total_universe_symbols == 2
    assert ev.candidate_pool_computable_count == 2
    assert ev.is_100_percent_computable is True
    assert ev.candidate_pool_completeness_pct == 100.0
    assert reasons == {}


def test_audit_candidate_pool_surfaces_ipo_and_fails_100_pct() -> None:
    target_date = date(2024, 1, 2)
    prior_dates = get_prior_xnys_sessions(target_date, 14)
    all_daily_dates = get_prior_xnys_sessions(target_date, 20)

    symbols = ["ESTABLISHED", "RECENT_IPO"]
    daily_bars_by_symbol = {
        "ESTABLISHED": [DailyBar("ESTABLISHED", d, 50.0, 52.0, 49.0, 51.0, 1_500_000) for d in all_daily_dates],
        "RECENT_IPO": [DailyBar("RECENT_IPO", d, 20.0, 22.0, 19.0, 21.0, 500_000) for d in all_daily_dates[-5:]],  # Only 5 sessions
    }
    prior_or_by_symbol = {
        "ESTABLISHED": [OpeningRangeVolumeObservation("ESTABLISHED", d, 30_000.0) for d in prior_dates],
        "RECENT_IPO": [OpeningRangeVolumeObservation("RECENT_IPO", d, 10_000.0) for d in prior_dates[-5:]],
    }
    current_or_by_symbol = {
        "ESTABLISHED": OpeningRange("ESTABLISHED", target_date, 50.0, 51.0, 49.5, 50.8, 35_000.0, Direction.LONG, 51.0),
        "RECENT_IPO": OpeningRange("RECENT_IPO", target_date, 20.0, 21.0, 19.8, 20.5, 12_000.0, Direction.LONG, 21.0),
    }

    ev, reasons = audit_candidate_pool_completeness(
        target_universe=symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        prior_or_obs_by_symbol=prior_or_by_symbol,
        current_or_by_symbol=current_or_by_symbol,
        target_session=target_date,
        required_lookback=14,
    )

    assert ev.is_100_percent_computable is False
    assert ev.candidate_pool_computable_count == 1
    assert ev.incomplete_history_ipo_or_listing_count == 1
    assert "RECENT_IPO" in reasons
    assert "insufficient_history_ipo_or_symbol_change" in reasons["RECENT_IPO"]


# =============================================================================
# Stage-A Freezing & Top-20 Selection Tests
# =============================================================================

def test_compute_and_freeze_stage_a_selection_deterministic() -> None:
    target_date = date(2024, 1, 2)
    prior_dates = get_prior_xnys_sessions(target_date, 14)
    all_daily_dates = get_prior_xnys_sessions(target_date, 20)

    symbols = ["SYM1", "SYM2", "SYM3"]
    daily_bars = {
        s: [DailyBar(s, d, 50.0, 52.0, 48.0, 50.0, 2_000_000) for d in all_daily_dates]
        for s in symbols
    }
    # SYM1: RV = 2.0 (current 100k, prior mean 50k)
    # SYM2: RV = 1.5 (current 75k, prior mean 50k)
    # SYM3: RV = 0.8 (current 40k, prior mean 50k) -> fails RV filter < 1.0
    prior_or = {
        s: [OpeningRangeVolumeObservation(s, d, 50_000.0) for d in prior_dates]
        for s in symbols
    }
    current_or = {
        "SYM1": OpeningRange("SYM1", target_date, 50.0, 52.0, 49.0, 51.0, 100_000.0, Direction.LONG, 52.0),
        "SYM2": OpeningRange("SYM2", target_date, 50.0, 52.0, 49.0, 51.0, 75_000.0, Direction.LONG, 52.0),
        "SYM3": OpeningRange("SYM3", target_date, 50.0, 52.0, 49.0, 51.0, 40_000.0, Direction.LONG, 52.0),
    }

    ev, records, selected = compute_and_freeze_stage_a_selection(
        universe_symbols=symbols,
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_date,
    )

    assert ev.eligible_candidates_count == 2
    assert selected == ["SYM1", "SYM2"]
    assert records[0]["symbol"] == "SYM1"
    assert records[0]["relative_volume"] == 2.0
    assert records[1]["symbol"] == "SYM2"
    assert records[1]["relative_volume"] == 1.5
    assert ev.selection_sha256 != ""


# =============================================================================
# Stage-B Path Completeness Tests
# =============================================================================

def test_audit_stage_b_path_completeness() -> None:
    target_date = date(2024, 1, 2)
    selected = ["SYM1"]

    # Generate all 385 minutes from 09:35 to 15:59 ET
    bars = []
    curr = datetime(2024, 1, 2, 9, 35, tzinfo=MARKET_TIMEZONE)
    end = datetime(2024, 1, 2, 15, 59, tzinfo=MARKET_TIMEZONE)
    while curr <= end:
        bars.append(MinuteBar("SYM1", curr, target_date, 50.0, 50.5, 49.8, 50.2, 1000.0))
        curr = curr + pd.Timedelta(minutes=1)

    ev_complete, missing = audit_stage_b_path(selected, {"SYM1": bars}, target_date)
    assert ev_complete.total_expected_bars == 385
    assert ev_complete.total_observed_bars == 385
    assert ev_complete.missing_minutes_count == 0
    assert ev_complete.path_complete is True
    assert missing == {}

    # Drop one minute (e.g. 12:00)
    bars_with_gap = [b for b in bars if b.timestamp.astimezone(MARKET_TIMEZONE).strftime("%H:%M") != "12:00"]
    ev_gap, missing_gap = audit_stage_b_path(selected, {"SYM1": bars_with_gap}, target_date)
    assert ev_gap.path_complete is False
    assert ev_gap.missing_minutes_count == 1
    assert missing_gap["SYM1"] == ["12:00"]


# =============================================================================
# Disposition Precedence Tests
# =============================================================================

def test_disposition_precedence_hierarchy() -> None:
    # 1. Massive entitlement blocker takes precedence over everything
    d = determine_top_level_disposition(
        massive_entitled=False,
        alpaca_entitled=False,
        exchange_mapping_resolved=False,
        pit_semantics_demonstrated=False,
        symbol_identity_resolved=False,
        candidate_pool_complete=False,
        candidate_pool_has_ipo_semantics_gap=False,
        stage_a_data_complete=False,
        stage_b_path_complete=False,
        resource_bounds_passed=False,
    )
    assert d == FeasibilityDisposition.BLOCKED_MASSIVE_ENTITLEMENT

    # 2. Alpaca entitlement
    d = determine_top_level_disposition(
        massive_entitled=True,
        alpaca_entitled=False,
        exchange_mapping_resolved=True,
        pit_semantics_demonstrated=True,
        symbol_identity_resolved=True,
        candidate_pool_complete=True,
        candidate_pool_has_ipo_semantics_gap=False,
        stage_a_data_complete=True,
        stage_b_path_complete=True,
        resource_bounds_passed=True,
    )
    assert d == FeasibilityDisposition.BLOCKED_ALPACA_SIP_ENTITLEMENT

    # 3. Exchange mapping
    d = determine_top_level_disposition(
        massive_entitled=True,
        alpaca_entitled=True,
        exchange_mapping_resolved=False,
        pit_semantics_demonstrated=True,
        symbol_identity_resolved=True,
        candidate_pool_complete=True,
        candidate_pool_has_ipo_semantics_gap=False,
        stage_a_data_complete=True,
        stage_b_path_complete=True,
        resource_bounds_passed=True,
    )
    assert d == FeasibilityDisposition.BLOCKED_REFERENCE_EXCHANGE_MAPPING

    # 4. Candidate pool history semantics
    d = determine_top_level_disposition(
        massive_entitled=True,
        alpaca_entitled=True,
        exchange_mapping_resolved=True,
        pit_semantics_demonstrated=True,
        symbol_identity_resolved=True,
        candidate_pool_complete=False,
        candidate_pool_has_ipo_semantics_gap=True,
        stage_a_data_complete=False,
        stage_b_path_complete=True,
        resource_bounds_passed=True,
    )
    assert d == FeasibilityDisposition.BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS

    # 5. Feasible when all pass
    d = determine_top_level_disposition(
        massive_entitled=True,
        alpaca_entitled=True,
        exchange_mapping_resolved=True,
        pit_semantics_demonstrated=True,
        symbol_identity_resolved=True,
        candidate_pool_complete=True,
        candidate_pool_has_ipo_semantics_gap=False,
        stage_a_data_complete=True,
        stage_b_path_complete=True,
        resource_bounds_passed=True,
    )
    assert d == FeasibilityDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD


# =============================================================================
# Artifact Safety & Manifest Tests
# =============================================================================

def test_safe_artifacts_writer_scrubs_symbol_names_and_ohlc(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts"
    summary = {
        "task_id": "DAYTRADE-003D-TEST",
        "pilot_universe": {"target_universe_count": 5000, "universe_sha256": "abc123hash"},
        "top_level_disposition": "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD",
    }
    estimate = {"extrapolated_storage_bytes": 100_000_000}
    provider_ev = {"exchange_mapping_used": ["XNYS", "XNAS"]}

    write_safe_probe_artifacts(output_dir, summary, estimate, provider_ev)

    sum_content = (output_dir / "probe_summary.json").read_text(encoding="utf-8")
    assert "target_universe_count" in sum_content
    # Confirm no symbol arrays or raw prices
    assert "AAPL" not in sum_content
    assert "open" not in sum_content.lower() or "quarantined_unopened" in sum_content


def test_write_private_manifest_invariants(tmp_path: Path) -> None:
    manifest = TwoStageDatasetManifest(
        task_id="DAYTRADE-003D-TEST",
        strategy_id="DAYTRADE-003B-ORB-SIP5M",
        upstream_spec_sha256="abc",
        resolution_spec_sha256="def",
        provider_identity="massive+alpaca",
        feed="sip",
        adjustment_mode="raw",
        timezone="America/New_York",
        calendar_version="XNYS",
        universe_provider="massive",
        universe_query_date="2024-01-02",
        universe_symbol_count=5000,
        universe_hash="hash_universe",
        exchange_filters=("XNYS", "XNAS"),
        type_code_distribution={"CS": 4000},
        daily_data_hashes_and_counts={},
        opening_range_data_hashes_and_counts={},
        top_20_selection_artifact_hash="hash_top20",
        full_path_selected_symbol_data_hashes_and_counts={},
        session_coverage=("2024-01-02",),
        excluded_sessions=(),
        dq_reasons=(),
        provider_request_ids=(),
        pagination_completeness=True,
        acquisition_timestamps={},
        holdout_status="quarantined_unopened",
    )
    m_hash = write_private_manifest(tmp_path, manifest)
    assert len(m_hash) == 64
    assert (tmp_path / "manifest.json").exists()
