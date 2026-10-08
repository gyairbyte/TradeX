"""Weights Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st

from tradex.config import TradeXSettings
from tradex.signals import weights as signal_weights
from tradex.ui.evidence import render_evidence_notice


def render_weights_tab(
    *,
    settings: TradeXSettings,
) -> None:
    """Render the Scoring Weights — configure legacy heuristic point values."""
    st.subheader("Scoring Weights — Configure Heuristic Contributions")
    render_evidence_notice("weights", st_module=st)
    st.caption(
        "Adjust how many points each technical condition awards when it fires in legacy heuristic scoring. "
        "Changes apply to Scanner and Confluence after Save. Persisted to ~/.tradex/weights.json."
    )

    with st.expander("How weighting works", expanded=False):
        st.markdown("""
    Each timeframe scorer is composed of several **components** (volume surge, RSI momentum, MACD crossover, etc.).
    When a component condition is met, it contributes its configured points to the total score. The final score
    is capped at 100, so the sum of weights *can* exceed 100 — that just makes individual components count for more.

    **Tiered signals** (intraday volume + RSI) award full credit for the strong tier and a reduced share for the
    weaker tier (50% for elevated volume, 75% for oversold-bounce RSI). The ratios scale with your configured weight.

    **Unvalidated configuration notice:**
    - Adjusting weights modifies the point allocations of legacy discovery heuristics.
    - Custom weight combinations have not been validated through controlled backtesting or holdout evaluations.
    - Manually tuning weights to match recent winning setups carries a high risk of post-hoc overfitting.
    - Use **Reset to defaults** to restore the original baseline heuristic weights at any time.
        """)

    current = signal_weights.load(settings=settings)
    section_meta = [
        ("Intraday (5-min bars)", "intraday", current.intraday),
        ("Short-term (daily bars)", "short", current.short),
    ]

    new_values: dict[str, dict[str, int]] = {"intraday": {}, "short": {}}

    for title, key, section in section_meta:
        st.markdown(f"### {title}")
        st.caption(f"Max possible score (uncapped sum): **{signal_weights.max_possible(section)}**")
        for field_name in section.__dataclass_fields__:
            meta = signal_weights.COMPONENT_LABELS.get((key, field_name), {"label": field_name, "help": ""})
            new_values[key][field_name] = st.slider(
                meta["label"],
                0, 50, getattr(section, field_name),
                key=f"w_{key}_{field_name}",
                help=meta["help"],
            )
        st.divider()

    st.markdown("### Long-term (Long MVP v1)")
    st.info(
        "Long Opportunity Strategy v1 scoring weights are locked by strategy contract (LONG-MVP-001) "
        "and are not user-editable. 100-point opportunity scoring is deterministic across all environments: "
        "Trend Quality (30 pts), Momentum Quality (25 pts), Setup Quality (20 pts), "
        "Movement Capacity (15 pts), and Participation (10 pts)."
    )
    st.divider()

    col_save, col_reset = st.columns([1, 1])
    if col_save.button("Save weights", type="primary", key="weights_save",
                       help="Persist these weights to ~/.tradex/weights.json. All future scans will use them."):
        updated = signal_weights.Weights(
            intraday=signal_weights.IntradayWeights(**new_values["intraday"]),
            short=signal_weights.ShortWeights(**new_values["short"]),
            long=current.long,
        )
        signal_weights.save(updated, settings=settings)
        st.success("Weights saved. Re-run any Scanner or Confluence scan to see the effect.")

    if col_reset.button("Reset to defaults", key="weights_reset",
                        help="Restore original built-in weights (matches the scoring shown in CLAUDE.md and the README)."):
        signal_weights.reset_to_defaults(settings=settings)
        st.success("Weights reset to defaults.")
        st.rerun()
