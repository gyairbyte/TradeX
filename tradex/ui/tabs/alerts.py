"""Alerts Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st

from tradex.alerts.models import AlertCooldownConfig, AlertKey
from tradex.alerts.notifier import send_alert
from tradex.alerts.policy import AlertPolicy
from tradex.config import TradeXSettings, load_runtime_settings


def _alert_policy_from_env() -> AlertPolicy:
    """Build the default alert policy from environment variables.

    Isolated so tests can swap it without launching Streamlit.
    """
    return AlertPolicy(settings=load_runtime_settings())


def _effective_cooldowns(config: AlertCooldownConfig) -> dict[str, int | str]:
    """Return the effective cooldown minutes for each automatic alert category."""
    if not config.enabled:
        return {"status": "disabled"}
    return {
        "coil": config.cooldown_minutes_for(AlertKey("X", "coil", "x")),
        "confluence": config.cooldown_minutes_for(
            AlertKey("X", "confluence", "multi")
        ),
        "gap": config.cooldown_minutes_for(AlertKey("X", "gap:up", "premarket")),
    }


def render_alerts_tab(
    *,
    settings: TradeXSettings,
) -> None:
        """Render the Alert Configuration tab."""
        st.subheader("Alert Configuration")
        st.caption(
            "Alerts fire automatically when the watcher is running and thresholds are crossed. "
            "Configure channels and thresholds in your .env file."
        )
    
        st.markdown("### Channel Status")
        ch1, ch2 = st.columns(2)
        channels = settings.alert_channels
        with ch1:
            if channels.discord_token and channels.discord_channel_id:
                st.success("Discord: **Connected**")
            else:
                st.error("Discord: **Not configured**")
                st.code("ALERT_DISCORD_TOKEN=your-bot-token\nALERT_DISCORD_CHANNEL_ID=your-channel-id")
                st.caption("Setup: discord.com/developers/applications → New App → Bot → copy Token")
        with ch2:
            if channels.email_to:
                st.success(f"Email: **Configured** → {channels.email_to}")
            else:
                st.error("Email: **Not configured**")
                st.code("ALERT_EMAIL_TO=you@example.com\nALERT_EMAIL_HOST=smtp.gmail.com\nALERT_EMAIL_USER=...\nALERT_EMAIL_PASS=...")
    
        st.divider()
        st.markdown("### Current Thresholds")
        st.caption("Edit in your .env file — changes take effect on next watcher restart.")
        t1, t2, _t3 = st.columns(3)
        t1.metric("Coil threshold",      str(settings.alert_thresholds.coil),
                  help="Minimum coil strength score (0–100) to fire an alert. Lower = more alerts.")
        t2.metric("Confluence threshold", str(settings.alert_thresholds.confluence),
                  help="Minimum confluence score (0–100) to fire an alert.")
        st.code("ALERT_COIL_THRESHOLD=60\nALERT_CONFLUENCE_THRESHOLD=70")
    
        st.divider()
        st.markdown("### Cooldown Status")
        st.caption(
            "Cooldown affects alert delivery only. It does not change signals, scores, "
            "thresholds, rankings, or opportunity eligibility."
        )
        try:
            alert_policy = _alert_policy_from_env()
            cfg = alert_policy.config
            c1, c2 = st.columns(2)
            c1.metric("Cooldown enabled", str(cfg.enabled))
            c2.metric("Default duration", f"{cfg.default_minutes} min")
    
            st.markdown("**Effective per-type cooldowns**")
            st.json(_effective_cooldowns(cfg))
    
            st.markdown("### Persistent Alert State")
            st.caption(
                "Recent automatic alert history. The state file is created on the first "
                "eligible automatic alert or the first explicit query."
            )
            if alert_policy.store.resolved_path.exists():
                try:
                    state_df = alert_policy.list_alert_states(limit=50)
                    if state_df.empty:
                        st.info("No alert state records yet.")
                    else:
                        display_cols = [
                            "ticker",
                            "alert_type",
                            "timeframe",
                            "last_decision",
                            "last_success_at",
                            "cooldown_until",
                            "sent_count",
                            "suppressed_count",
                            "failed_count",
                        ]
                        st.dataframe(state_df[display_cols], use_container_width=True)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Alert state is unavailable or corrupt: {e}")
            else:
                st.info("Persistent alert state has not been initialized yet.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Invalid alert cooldown configuration: {e}")
    
        st.divider()
        st.markdown("### Send Test Alert")
        st.caption("Verify your channels are working before relying on them. Test alerts bypass cooldown.")
        if st.button("Send Test Alert", key="btn_test_alert"):
            results = send_alert(
                subject="TradeX Test Alert",
                body="This is a test alert from your TradeX dashboard. If you received this, alerts are configured correctly.",
            )
            sent   = [k for k, v in results.items() if v]
            failed = [k for k, v in results.items() if not v]
            if sent:
                st.success(f"Test alert sent via: {', '.join(sent)}")
            if failed:
                st.warning(f"Not sent (not configured): {', '.join(failed)}")
    
        st.divider()
        st.markdown("### What Triggers Alerts")
        st.markdown("""
    | Alert type | When it fires | Color in Discord |
    |---|---|---|
    | **Coil detected** | Coil strength ≥ threshold after a scan | 🟡 Amber |
    | **Confluence** | Cross-timeframe score ≥ threshold | 🟢 Green |
    | **Gap up** | Pre-market gap ≥ 4% upward (8am ET) | 🟢 Green |
    | **Gap down** | Pre-market gap ≥ 4% downward (8am ET) | 🔴 Red |
    | **Pattern similarity** | Not an automatic alert — use the *Pattern Similarity* tab for manual experimental inspection only | ⚪ Not applicable |
    
    Run the watcher to activate automatic alerts:
    ```bash
    .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
    ```
    
    Add a cooldown override:
    ```bash
    .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-cooldown-minutes 120
    ```
    
    Disable cooldown entirely:
    ```bash
    .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --disable-alert-cooldown
    ```
    """)
    
