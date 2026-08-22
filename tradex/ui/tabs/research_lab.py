"""Research Lab container tab renderer (MVP-ARCH-001-R3)."""

from __future__ import annotations

import streamlit as st

from tradex.config import TradeXSettings
from tradex.ui.tabs.coil_detector import render_coil_detector_tab
from tradex.ui.tabs.options_activity import render_options_activity_tab
from tradex.ui.tabs.pattern_similarity import render_pattern_similarity_tab


def render_research_lab_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    timeframe: str,
    provider: str,
    options_source: str,
) -> None:
    """Render the Research Lab container tab with nested exploratory and research tools."""
    st.subheader("Research Lab")
    st.info(
        "Research Lab contains exploratory, rejected, contextual, and archived functionality. "
        "Nothing in this area is a production-approved actionable strategy."
    )

    tab_coil, tab_pattern, tab_options = st.tabs(
        [
            "Coil Context",
            "Pattern Similarity — Rejected",
            "Options Activity — Exploratory",
        ]
    )

    with tab_coil:
        render_coil_detector_tab(
            settings=settings,
            timeframe=timeframe,
        )

    with tab_pattern:
        render_pattern_similarity_tab(
            settings=settings,
            watchlist=watchlist,
            provider=provider,
        )

    with tab_options:
        render_options_activity_tab(
            settings=settings,
            watchlist=watchlist,
            options_source=options_source,
        )
