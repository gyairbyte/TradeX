"""Deterministic tests for the ORB Candidate Preview UI tab (DAYTRADE-003E-ORB-PREVIEW-001)."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import settings_from_mapping
from tradex.research.daytrade_orb.demo_fixture import (
    DEMO_SESSION_DATE,
    get_demo_snapshot_json,
)
from tradex.research.daytrade_orb.snapshot import MAX_SNAPSHOT_BYTES


@pytest.fixture
def fake_orb_st():
    """Return a deterministic Streamlit MagicMock for testing ORB Preview tab."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    st.expander.return_value.__enter__ = MagicMock()
    st.expander.return_value.__exit__ = MagicMock()
    st.radio.return_value = "Synthetic Demo Snapshot"
    st.file_uploader.return_value = None
    return st


@pytest.fixture
def orb_preview_module(fake_orb_st, monkeypatch):
    """Import the orb_preview tab fresh with mocked Streamlit."""
    mod_name = "tradex.ui.tabs.orb_preview"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_orb_st)
    return importlib.import_module(mod_name)


def test_import_does_not_render_or_touch_backend(orb_preview_module, fake_orb_st):
    """Importing the orb_preview module must not call Streamlit or backend operations."""
    assert fake_orb_st.subheader.call_count == 0
    assert fake_orb_st.warning.call_count == 0
    assert fake_orb_st.dataframe.call_count == 0


def test_render_shows_subheader_and_disclaimer(orb_preview_module, fake_orb_st):
    """Rendering the ORB preview tab displays the subheader and research disclaimer."""
    settings = settings_from_mapping({})
    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.subheader.assert_called_once_with(
        "Stocks-in-Play 5-Minute ORB Candidate Preview — Research Only"
    )
    assert fake_orb_st.warning.call_count >= 1
    disclaimer_call = str(fake_orb_st.warning.call_args_list[0][0][0])
    assert "RESEARCH PREVIEW ONLY — NOT AN ACTIONABLE TRADING STRATEGY" in disclaimer_call


def test_render_with_demo_snapshot_renders_dataframe(orb_preview_module, fake_orb_st):
    """Selecting the demo snapshot renders metrics, warning, dataframe, and exclusions."""
    settings = settings_from_mapping({})
    fake_orb_st.radio.return_value = "Synthetic Demo Snapshot"

    orb_preview_module.render_orb_preview_tab(settings=settings)

    # Info message about synthetic demo
    assert any("Synthetic Demo Snapshot" in str(c[0][0]) for c in fake_orb_st.info.call_args_list)

    # DataFrame called for candidate table and exclusions table
    assert fake_orb_st.dataframe.call_count >= 1
    candidates_df = fake_orb_st.dataframe.call_args_list[0][0][0]
    assert len(candidates_df) == 20  # Top 20 candidates
    assert "Rank" in candidates_df.columns
    assert "Symbol" in candidates_df.columns
    assert "Direction" in candidates_df.columns
    assert "Theoretical Stop Offset" in candidates_df.columns
    assert "Stop-Entry Trigger" in candidates_df.columns


def test_render_upload_mode_prompts_when_no_file(orb_preview_module, fake_orb_st):
    """When upload mode is active but no file is selected, prompts the user to upload."""
    settings = settings_from_mapping({})
    fake_orb_st.radio.return_value = "Upload Custom Snapshot JSON"
    fake_orb_st.file_uploader.return_value = None

    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.file_uploader.assert_called_once()
    assert any(
        "Please upload a snapshot JSON file" in str(c[0][0])
        for c in fake_orb_st.info.call_args_list
    )


def test_render_upload_mode_rejects_exceeded_size(orb_preview_module, fake_orb_st):
    """When uploaded file exceeds 5 MB, renders an error message."""
    settings = settings_from_mapping({})
    fake_orb_st.radio.return_value = "Upload Custom Snapshot JSON"

    oversized_mock = MagicMock()
    oversized_mock.getvalue.return_value = b"x" * (MAX_SNAPSHOT_BYTES + 10)
    fake_orb_st.file_uploader.return_value = oversized_mock

    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.error.assert_called_once()
    error_msg = str(fake_orb_st.error.call_args[0][0])
    assert "exceeds the 5 MB limit" in error_msg


def test_render_upload_mode_rejects_malformed_json(orb_preview_module, fake_orb_st):
    """When uploaded file has invalid JSON, renders a validation error."""
    settings = settings_from_mapping({})
    fake_orb_st.radio.return_value = "Upload Custom Snapshot JSON"

    bad_json_mock = MagicMock()
    bad_json_mock.getvalue.return_value = b"{ invalid json"
    fake_orb_st.file_uploader.return_value = bad_json_mock

    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.error.assert_called_once()
    error_msg = str(fake_orb_st.error.call_args[0][0])
    assert "Snapshot Validation Error" in error_msg


def test_render_upload_mode_processes_valid_json(orb_preview_module, fake_orb_st):
    """When valid JSON is uploaded, parses and renders the candidate table."""
    settings = settings_from_mapping({})
    fake_orb_st.radio.return_value = "Upload Custom Snapshot JSON"

    valid_mock = MagicMock()
    valid_mock.getvalue.return_value = get_demo_snapshot_json().encode("utf-8")
    fake_orb_st.file_uploader.return_value = valid_mock

    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.success.assert_called_once()
    assert fake_orb_st.dataframe.call_count >= 1
    candidates_df = fake_orb_st.dataframe.call_args_list[0][0][0]
    assert len(candidates_df) == 20


def test_render_time_gate_blocks_before_0935(orb_preview_module, fake_orb_st, monkeypatch):
    """When snapshot as-of time is before 09:35 ET, renders error and halts execution."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from tradex.research.daytrade_orb.snapshot import ORBSnapshot

    settings = settings_from_mapping({})
    early_as_of = datetime(2024, 1, 2, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    early_snap = ORBSnapshot(
        session_date=DEMO_SESSION_DATE,
        as_of_time=early_as_of,
        source_type="synthetic_demo",
        source_label="Early Snapshot",
        completeness_status="unknown",
        symbols={},
    )
    monkeypatch.setattr(
        "tradex.ui.tabs.orb_preview.create_demo_snapshot",
        lambda: early_snap,
    )

    fake_orb_st.radio.return_value = "Synthetic Demo Snapshot"

    orb_preview_module.render_orb_preview_tab(settings=settings)

    fake_orb_st.error.assert_called_once()
    error_msg = str(fake_orb_st.error.call_args[0][0])
    assert "Time-Gate Blocked" in error_msg
    fake_orb_st.stop.assert_called_once()
