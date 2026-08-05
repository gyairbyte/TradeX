"""Shared UI test fixtures."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_st(monkeypatch):
    """Return a deterministic MagicMock that stands in for Streamlit."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st._active_button_keys = set()
    st._column_returns = []

    def _button(*args, **kwargs):
        return kwargs.get("key") in st._active_button_keys

    st.button.side_effect = _button

    def _slider(*args, **kwargs):
        # The dashboard calls st.slider(label, min, max, value, ...)
        if len(args) >= 4:
            return args[3]
        return kwargs.get("value", 0)

    st.slider.side_effect = _slider

    def _selectbox(label, *args, **kwargs):
        for arg in args:
            if isinstance(arg, (list, tuple)) and arg:
                return arg[0]
        return kwargs.get("index")

    st.selectbox.side_effect = _selectbox

    def _columns(spec, *args, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            col = MagicMock()
            col.button.side_effect = _button
            col.slider.side_effect = _slider
            cols.append(col)
        st._column_returns.append(cols)
        return cols

    st.columns.side_effect = _columns

    return st
