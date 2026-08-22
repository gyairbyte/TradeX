"""Settings container tab renderer (MVP-ARCH-001-R3)."""

from __future__ import annotations

import streamlit as st

from tradex.config import TradeXSettings
from tradex.ui.tabs.alerts import render_alerts_tab
from tradex.ui.tabs.weights import render_weights_tab


def render_settings_tab(
    *,
    settings: TradeXSettings,
) -> None:
    """Render the Settings container tab with nested operational controls."""
    st.subheader("Settings")
    st.info(
        "This transitional Settings surface groups existing operational controls. "
        "Global provider and watchlist controls remain in the sidebar for this rollout. "
        "Automatic alert gating has not been implemented (alerts continue to use delivery "
        "infrastructure over legacy/exploratory triggers), and legacy weight controls remain unvalidated."
    )

    tab_alerts, tab_weights = st.tabs(
        [
            "Alert Delivery",
            "Legacy Weights",
        ]
    )

    with tab_alerts:
        render_alerts_tab(settings=settings)

    with tab_weights:
        render_weights_tab(settings=settings)
