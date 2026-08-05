"""Weights Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st

from tradex.config import TradeXSettings
from tradex.signals import weights as signal_weights


def render_weights_tab(
    *,
    settings: TradeXSettings,
) -> None:
    """Render the Scoring Weights — tune signal component point values."""
    st.subheader("Scoring Weights — Tune Signal Contributions")
    st.caption(
        "Adjust how many points each signal component awards when it fires. "
        "Changes apply to every Scanner and Confluence run after Save. Persisted to ~/.tradex/weights.json."
    )

    with st.expander("How weighting works", expanded=False):
        st.markdown("""
    Each timeframe scorer is composed of several **components** (volume surge, RSI momentum, MACD crossover, etc.).
    When a component condition is met, it contributes its configured points to the total score. The final score
    is capped at 100, so the sum of weights *can* exceed 100 — that just makes individual components count for more.

    **Tiered signals** (intraday volume + RSI) award full credit for the strong tier and a reduced share for the
    weaker tier (50% for elevated volume, 75% for oversold-bounce RSI). The ratios scale with your configured weight.

    **Tips:**
    - If you trust volume more than indicators, raise volume weights and lower MACD / RSI.
    - If you want every clean setup to clear 50, keep the sum of your top 2–3 components ≥ 50.
    - Use **Reset to defaults** to get back the original 30/20/30/20-style scoring at any time.
        """)

    current = signal_weights.load(settings=settings)
    section_meta = [
        ("Intraday (5-min bars)", "intraday", current.intraday),
        ("Short-term (daily bars)", "short", current.short),
        ("Long-term (weekly bars)", "long", current.long),
    ]

    new_values: dict[str, dict[str, int]] = {"intraday": {}, "short": {}, "long": {}}

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

    col_save, col_reset = st.columns([1, 1])
    if col_save.button("Save weights", type="primary", key="weights_save",
                       help="Persist these weights to ~/.tradex/weights.json. All future scans will use them."):
        updated = signal_weights.Weights(
            intraday=signal_weights.IntradayWeights(**new_values["intraday"]),
            short=signal_weights.ShortWeights(**new_values["short"]),
            long=signal_weights.LongWeights(**new_values["long"]),
        )
        signal_weights.save(updated, settings=settings)
        st.success("Weights saved. Re-run any Scanner or Confluence scan to see the effect.")

    if col_reset.button("Reset to defaults", key="weights_reset",
                        help="Restore original built-in weights (matches the scoring shown in CLAUDE.md and the README)."):
        signal_weights.reset_to_defaults(settings=settings)
        st.success("Weights reset to defaults.")
        st.rerun()
