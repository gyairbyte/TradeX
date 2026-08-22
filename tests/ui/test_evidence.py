"""Tests for tradex.ui.evidence module."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradex.ui.evidence import (
    EVIDENCE_NOTICES,
    EvidenceNotice,
    get_evidence_notice,
    render_evidence_notice,
)

EXPECTED_TABS = {
    "scanner",
    "coil_detector",
    "confluence",
    "pattern_similarity",
    "premarket",
    "options_activity",
    "alerts",
    "signal_journal",
    "weights",
    "help",
}


def test_all_ten_tabs_have_evidence_notices() -> None:
    assert set(EVIDENCE_NOTICES.keys()) == EXPECTED_TABS


def test_no_tab_is_labeled_production_approved() -> None:
    for tab_id, notice in EVIDENCE_NOTICES.items():
        assert notice.evidence_state != "production_approved", tab_id
        assert "production_approved" not in notice.badge_label.lower(), tab_id
        assert "production approved" not in notice.summary.lower(), tab_id


def test_evidence_notice_field_types_and_values() -> None:
    for tab_id in EXPECTED_TABS:
        notice = get_evidence_notice(tab_id)
        assert isinstance(notice, EvidenceNotice)
        assert notice.tab_id == tab_id
        assert isinstance(notice.evidence_state, str) and notice.evidence_state
        assert isinstance(notice.badge_label, str) and notice.badge_label
        assert isinstance(notice.summary, str) and notice.summary
        assert notice.level in {"info", "warning"}


def test_pattern_similarity_is_rejected_on_holdout() -> None:
    notice = get_evidence_notice("pattern_similarity")
    assert notice.evidence_state == "rejected"
    assert "rejected on holdout" in notice.badge_label.lower()
    assert "pattern-001" in notice.summary.lower()
    assert notice.level == "warning"


def test_signal_journal_is_legacy_telemetry() -> None:
    notice = get_evidence_notice("signal_journal")
    assert notice.evidence_state == "legacy_signal_telemetry"
    assert "generic" in notice.summary.lower()


def test_get_evidence_notice_unknown_key_raises() -> None:
    with pytest.raises(KeyError, match="Unknown dashboard tab_id"):
        get_evidence_notice("non_existent_tab")


def test_render_evidence_notice_calls_streamlit_info_and_warning() -> None:
    fake_st = MagicMock()
    # Test info render
    notice_scanner = render_evidence_notice("scanner", st_module=fake_st)
    assert fake_st.info.call_count == 1
    assert "Legacy Heuristic" in fake_st.info.call_args[0][0]
    assert notice_scanner.tab_id == "scanner"

    # Test warning render for pattern similarity
    fake_st.reset_mock()
    notice_pattern = render_evidence_notice("pattern_similarity", st_module=fake_st)
    assert fake_st.warning.call_count == 1
    assert "Rejected on Holdout" in fake_st.warning.call_args[0][0]
    assert notice_pattern.tab_id == "pattern_similarity"
