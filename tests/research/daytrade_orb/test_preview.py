"""Comprehensive deterministic tests for ORB Candidate Preview service and snapshot parser.

Tests acceptance criteria for DAYTRADE-003E-ORB-PREVIEW-001:
- Snapshot parsing and strict <= 5 MB file size limit
- Per-symbol error isolation without collapsing the whole preview
- 09:35 ET time gating (blocking before 09:35 ET)
- Source fidelity: price > $5, ADV >= 1M, ATR > $0.50, RV >= 1.0
- Deterministic RV ranking and ticker ascending tie-breaker
- Top-20 cutoff and unranked eligible candidates (no backfill for Doji)
- Doji setup in Top 20 receiving NO_ORDER_DOJI
- Theoretical protective-stop offset (0.10 * ATR14) without promised fill
- Input order invariance (shuffled input yields identical output)
- Network-free and credential-free execution
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb.demo_fixture import (
    DEMO_AS_OF_TIME,
    DEMO_SESSION_DATE,
    create_demo_snapshot,
    get_demo_snapshot_dict,
    get_demo_snapshot_json,
)
from tradex.research.daytrade_orb.models import Direction, OrderStatus
from tradex.research.daytrade_orb.preview import (
    ExclusionCategory,
    generate_orb_candidate_preview,
)
from tradex.research.daytrade_orb.snapshot import (
    MAX_SNAPSHOT_BYTES,
    ORBSnapshot,
    SnapshotValidationError,
    parse_snapshot_dict,
    parse_snapshot_json,
)

MARKET_TIMEZONE = ZoneInfo("America/New_York")


# ==============================================================================
# SNAPSHOT PARSER & VALIDATION TESTS
# ==============================================================================


def test_parse_snapshot_json_success_with_demo_json():
    """Valid JSON round-trips into an ORBSnapshot preserving symbols and metadata."""
    json_str = get_demo_snapshot_json()
    snapshot = parse_snapshot_json(json_str)

    assert isinstance(snapshot, ORBSnapshot)
    assert snapshot.session_date == DEMO_SESSION_DATE
    assert snapshot.as_of_time == DEMO_AS_OF_TIME
    assert snapshot.source_type == "synthetic_demo"
    assert len(snapshot.symbols) >= 30
    assert "SYNTH_L01" in snapshot.symbols
    assert len(snapshot.symbols["SYNTH_L01"].daily_bars) == 15
    assert len(snapshot.symbols["SYNTH_L01"].opening_range_bars) == 5
    assert len(snapshot.symbols["SYNTH_L01"].prior_opening_range_volumes) == 14


def test_parse_snapshot_json_rejects_exceeded_file_size():
    """Snapshots exceeding the 5 MB limit fail closed immediately."""
    oversized = b" " * (MAX_SNAPSHOT_BYTES + 1)
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_json(oversized)
    assert "exceeds the maximum allowed limit of 5242880 bytes (5 MB)" in str(exc_info.value)


def test_parse_snapshot_json_rejects_malformed_json():
    """Malformed JSON string raises SnapshotValidationError with context."""
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_json(b"{ invalid json content")
    assert "Malformed JSON" in str(exc_info.value)


def test_parse_snapshot_dict_rejects_missing_root_fields():
    """Missing required top-level snapshot fields fail closed."""
    valid_dict = get_demo_snapshot_dict()
    for field in ("session_date", "as_of_time", "source_type", "source_label", "symbols"):
        bad_dict = dict(valid_dict)
        del bad_dict[field]
        with pytest.raises(SnapshotValidationError) as exc_info:
            parse_snapshot_dict(bad_dict)
        assert f"Missing required snapshot field: '{field}'" in str(exc_info.value)


def test_parse_snapshot_dict_rejects_naive_as_of_time():
    """as_of_time without timezone fails validation."""
    bad_dict = get_demo_snapshot_dict()
    bad_dict["as_of_time"] = "2024-01-02T09:35:00"  # Naive (no offset)
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_dict(bad_dict)
    assert "as_of_time must be timezone-aware" in str(exc_info.value)


def test_parse_snapshot_dict_rejects_date_time_mismatch():
    """as_of_time New York date must match session_date."""
    bad_dict = get_demo_snapshot_dict()
    bad_dict["as_of_time"] = "2024-01-03T09:35:00-05:00"  # Next day
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_dict(bad_dict)
    assert "does not match session_date" in str(exc_info.value)


def test_parse_snapshot_dict_rejects_invalid_source_type():
    """Invalid source_type is rejected."""
    bad_dict = get_demo_snapshot_dict()
    bad_dict["source_type"] = "unauthorized_live_production"
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_dict(bad_dict)
    assert "Invalid source_type" in str(exc_info.value)


def test_parse_snapshot_dict_rejects_duplicate_normalized_symbol():
    """Duplicate symbol keys differing only by whitespace or casing fail closed."""
    bad_dict = get_demo_snapshot_dict()
    # Add duplicate key in lowercase
    bad_dict["symbols"]["synth_l01"] = bad_dict["symbols"]["SYNTH_L01"]
    with pytest.raises(SnapshotValidationError) as exc_info:
        parse_snapshot_dict(bad_dict)
    assert "Duplicate symbol key in snapshot: 'synth_l01'" in str(exc_info.value)


def test_parse_snapshot_dict_isolates_corrupt_symbol_error():
    """A corrupt symbol bar is captured on that symbol without collapsing valid symbols."""
    snap = parse_snapshot_json(get_demo_snapshot_json())

    # BLOCKED_CORRUPT was emitted with high < open in daily bars
    assert "BLOCKED_CORRUPT" in snap.symbols
    corrupt_payload = snap.symbols["BLOCKED_CORRUPT"]
    assert corrupt_payload.integrity_error is not None
    assert "Corrupt daily_bar [0] for symbol 'BLOCKED_CORRUPT'" in corrupt_payload.integrity_error

    # Valid symbol parsed normally
    assert "SYNTH_L01" in snap.symbols
    assert snap.symbols["SYNTH_L01"].integrity_error is None


# ==============================================================================
# PREVIEW ENGINE & RULES FIDELITY TESTS
# ==============================================================================


def test_generate_orb_candidate_preview_end_to_end_on_demo():
    """Synthetic demo preview reproduces all required acceptance criteria behaviors."""
    snap = create_demo_snapshot()
    res = generate_orb_candidate_preview(snap)

    assert not res.is_time_gated
    assert res.time_gate_message is None
    assert res.universe_coverage.provided_count == 33
    assert res.universe_coverage.eligible_count == 23
    assert len(res.candidates) == 20  # Top 20 max
    assert len(res.unranked_eligible_candidates) == 3  # Ranks 21, 22, 23

    # Rank 1 must have the highest RV
    top = res.candidates[0]
    assert top.rank == 1
    assert top.symbol == "SYNTH_L01"
    assert top.direction == Direction.LONG
    assert top.rv14 == pytest.approx(4.50, rel=1e-2)
    assert top.stop_entry_trigger == top.or_high
    assert top.theoretical_stop_offset > 0.0
    assert top.order_intent_status == OrderStatus.ORDER_NOT_TRIGGERED

    # Top-20 Doji invariant: rank 4 is Doji, produces NO_ORDER_DOJI, and is NOT backfilled
    doji_candidates = [c for c in res.candidates if c.direction == Direction.DOJI]
    assert len(doji_candidates) == 1
    doji_cand = doji_candidates[0]
    assert doji_cand.symbol == "SYNTH_DOJI_TOP"
    assert doji_cand.order_intent_status == OrderStatus.NO_ORDER_DOJI
    assert doji_cand.stop_entry_trigger is None
    assert "NO_ORDER generated" in doji_cand.explanation

    # Total ranked candidates remains 20 (no backfill occurred)
    assert len(res.candidates) == 20
    selected_symbols = {c.symbol for c in res.candidates}
    assert "SYNTH_L10_CUTOFF" not in selected_symbols
    assert "SYNTH_S09_CUTOFF" not in selected_symbols
    assert "SYNTH_L11_CUTOFF" not in selected_symbols

    # Deterministic alphabetical tie-breaking: SYNTH_TIE_A ranks before SYNTH_TIE_B
    tie_candidates = [c for c in res.candidates if "TIE" in c.symbol]
    assert len(tie_candidates) == 2
    assert tie_candidates[0].symbol == "SYNTH_TIE_A"
    assert tie_candidates[1].symbol == "SYNTH_TIE_B"
    assert tie_candidates[0].rank < tie_candidates[1].rank
    assert tie_candidates[0].rv14 == tie_candidates[1].rv14


def test_exclusions_taxonomy_and_explanations():
    """All 13 excluded constituents are properly categorized with explicit explanations."""
    snap = create_demo_snapshot()
    res = generate_orb_candidate_preview(snap)

    exclusions_by_sym = {e.symbol: e for e in res.exclusions}

    # 1. Technical filter rejections
    assert "REJ_PENNY" in exclusions_by_sym
    assert exclusions_by_sym["REJ_PENNY"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "Price 4.20 <= 5.00" in exclusions_by_sym["REJ_PENNY"].reason

    assert "REJ_LOWADV" in exclusions_by_sym
    assert exclusions_by_sym["REJ_LOWADV"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "ADV14" in exclusions_by_sym["REJ_LOWADV"].reason

    assert "REJ_LOWATR" in exclusions_by_sym
    assert exclusions_by_sym["REJ_LOWATR"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "ATR14" in exclusions_by_sym["REJ_LOWATR"].reason

    assert "REJ_LOWRV" in exclusions_by_sym
    assert exclusions_by_sym["REJ_LOWRV"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "RV14" in exclusions_by_sym["REJ_LOWRV"].reason

    # Cutoff beyond Top 20
    assert "SYNTH_L10_CUTOFF" in exclusions_by_sym
    assert exclusions_by_sym["SYNTH_L10_CUTOFF"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "exceeds Top-20 cutoff" in exclusions_by_sym["SYNTH_L10_CUTOFF"].reason

    # 2. Data Unavailable
    assert "UNAV_MISSHIST" in exclusions_by_sym
    assert exclusions_by_sym["UNAV_MISSHIST"].category == ExclusionCategory.DATA_UNAVAILABLE
    assert "non-computable" in exclusions_by_sym["UNAV_MISSHIST"].reason

    assert "UNAV_MISSORV" in exclusions_by_sym
    assert exclusions_by_sym["UNAV_MISSORV"].category == ExclusionCategory.DATA_UNAVAILABLE
    assert "RV14 non-computable" in exclusions_by_sym["UNAV_MISSORV"].reason

    assert "UNAV_ZERORV" in exclusions_by_sym
    assert exclusions_by_sym["UNAV_ZERORV"].category == ExclusionCategory.DATA_UNAVAILABLE
    assert "Zero RV baseline" in exclusions_by_sym["UNAV_ZERORV"].reason

    assert "UNAV_NOPRINT" in exclusions_by_sym
    assert exclusions_by_sym["UNAV_NOPRINT"].category == ExclusionCategory.DATA_UNAVAILABLE
    assert "NO_OPENING_PRINT_NO_SETUP" in exclusions_by_sym["UNAV_NOPRINT"].reason

    # 3. Integrity Blocked
    assert "BLOCKED_CORRUPT" in exclusions_by_sym
    assert exclusions_by_sym["BLOCKED_CORRUPT"].category == ExclusionCategory.INTEGRITY_BLOCKED

    assert "BLOCKED_FUTURE" in exclusions_by_sym
    assert exclusions_by_sym["BLOCKED_FUTURE"].category == ExclusionCategory.INTEGRITY_BLOCKED
    assert "Future-bar leakage" in exclusions_by_sym["BLOCKED_FUTURE"].reason


def test_time_gate_blocks_preview_prior_to_0935_et():
    """Snapshots timestamped before 09:35 ET block candidate ranking."""
    snap = create_demo_snapshot()
    # Modify as-of time to 09:34:59 ET
    early_as_of = datetime(2024, 1, 2, 9, 34, 59, tzinfo=MARKET_TIMEZONE)
    early_snap = ORBSnapshot(
        session_date=snap.session_date,
        as_of_time=early_as_of,
        source_type=snap.source_type,
        source_label=snap.source_label,
        completeness_status=snap.completeness_status,
        symbols=snap.symbols,
        notes="Early snapshot",
    )

    res = generate_orb_candidate_preview(early_snap)

    assert res.is_time_gated
    assert res.candidates == []
    assert res.unranked_eligible_candidates == []
    assert res.time_gate_message is not None
    assert "Candidate ranking is blocked: snapshot as-of time 09:34:59 EST is prior to 09:35 ET" in res.time_gate_message


def test_input_order_invariance():
    """Shuffling the order of symbols in the snapshot produces identical ranked results."""
    snap = create_demo_snapshot()
    res_orig = generate_orb_candidate_preview(snap)

    # Reverse the order of symbols
    reversed_symbols = {k: snap.symbols[k] for k in reversed(list(snap.symbols.keys()))}
    shuffled_snap = ORBSnapshot(
        session_date=snap.session_date,
        as_of_time=snap.as_of_time,
        source_type=snap.source_type,
        source_label=snap.source_label,
        completeness_status=snap.completeness_status,
        symbols=reversed_symbols,
        notes="Shuffled symbols",
    )
    res_shuffled = generate_orb_candidate_preview(shuffled_snap)

    assert len(res_orig.candidates) == len(res_shuffled.candidates)
    for c1, c2 in zip(res_orig.candidates, res_shuffled.candidates):
        assert c1.rank == c2.rank
        assert c1.symbol == c2.symbol
        assert c1.direction == c2.direction
        assert c1.rv14 == c2.rv14
        assert c1.stop_entry_trigger == c2.stop_entry_trigger
        assert c1.theoretical_stop_offset == c2.theoretical_stop_offset
        assert c1.order_intent_status == c2.order_intent_status


def test_theoretical_stop_offset_calculation():
    """Theoretical protective-stop offset is exactly 0.10 * ATR14."""
    snap = create_demo_snapshot()
    res = generate_orb_candidate_preview(snap)

    for cand in res.candidates:
        if cand.direction != Direction.DOJI:
            expected_offset = round(0.10 * cand.atr14, 4)
            assert cand.theoretical_stop_offset == pytest.approx(expected_offset, rel=1e-3)
            # Prospective trigger is OR High for Long, OR Low for Short
            if cand.direction == Direction.LONG:
                assert cand.stop_entry_trigger == cand.or_high
            else:
                assert cand.stop_entry_trigger == cand.or_low


def test_orb_candidate_preview_as_of_time_et_conversion():
    """ORBCandidatePreviewResult.as_of_time_et converts UTC aware datetime to America/New_York."""
    snap = create_demo_snapshot()
    # 2024-01-02 14:35:00 UTC == 2024-01-02 09:35:00 EST
    utc_as_of = datetime(2024, 1, 2, 14, 35, 0, tzinfo=ZoneInfo("UTC"))
    utc_snap = ORBSnapshot(
        session_date=snap.session_date,
        as_of_time=utc_as_of,
        source_type=snap.source_type,
        source_label=snap.source_label,
        completeness_status=snap.completeness_status,
        symbols=snap.symbols,
    )

    res = generate_orb_candidate_preview(utc_snap)
    assert res.as_of_time.tzinfo == ZoneInfo("UTC")
    assert res.as_of_time_et.tzinfo == MARKET_TIMEZONE
    assert res.as_of_time_et.hour == 9
    assert res.as_of_time_et.minute == 35
    assert res.as_of_time_et.strftime("%H:%M:%S %Z") == "09:35:00 EST"


def test_universe_coverage_warning_enforced_on_declared_complete():
    """Snapshots claiming declared_complete still produce an unverified completeness warning."""
    snap = create_demo_snapshot()
    # 1-symbol snapshot claiming declared_complete
    single_symbol = {"SYNTH_L01": snap.symbols["SYNTH_L01"]}
    decl_snap = ORBSnapshot(
        session_date=snap.session_date,
        as_of_time=snap.as_of_time,
        source_type="user_provided_unverified",
        source_label="Self Declared Complete Snapshot",
        completeness_status="declared_complete",
        symbols=single_symbol,
    )

    res = generate_orb_candidate_preview(decl_snap)
    assert res.universe_coverage.completeness_status == "declared_complete"
    assert res.universe_coverage.provided_count == 1
    # Completeness warning must be present in warnings and universe_coverage
    assert any("Completeness is self-declared ('declared_complete')" in w for w in res.warnings)
    assert "has NOT been independently verified" in res.universe_coverage.completeness_warning
    assert "limited to the provided constituent set (1 symbols provided)" in res.universe_coverage.completeness_warning
