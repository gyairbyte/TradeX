"""Alerts Streamlit tab renderer."""
from __future__ import annotations

import streamlit as st

from tradex.alerts.models import AlertCooldownConfig, AlertKey
from tradex.alerts.notifier import send_alert
from tradex.alerts.policy import AlertPolicy
from tradex.config import TradeXSettings, load_runtime_settings
from tradex.ui.evidence import render_evidence_notice


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
    st.subheader("Alert Delivery Configuration")
    render_evidence_notice("alerts", st_module=st)
    st.info(
        "**Automatic Market Alerts: Gated — No Approved Actionable Strategy**\n\n"
        "Automatic external delivery to Discord/email is fail-closed and blocked for all "
        "market observations (Coil, Confluence, pre-market gap, Pattern Similarity, legacy heuristic scores) "
        "because TradeX currently has no production-approved actionable strategy. "
        "Manual test alerts remain available below for transport connectivity verification."
    )
    st.caption(
        "Configure delivery channel credentials and cooldown settings. "
        "Automatic market notifications remain gated until an approved actionable strategy is authorized."
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
    st.markdown("### Legacy Evaluation Thresholds (Non-Actionable)")
    st.caption(
        "Used for internal observation/telemetry evaluation. "
        "Adjusting these thresholds does not enable automatic external market alerts."
    )
    t1, t2, _t3 = st.columns(3)
    t1.metric("Coil threshold",      str(settings.alert_thresholds.coil),
              help="Minimum coil strength score (0–100) for internal telemetry evaluation.")
    t2.metric("Confluence threshold", str(settings.alert_thresholds.confluence),
              help="Minimum confluence score (0–100) for internal telemetry evaluation.")
    st.code("ALERT_COIL_THRESHOLD=60\nALERT_CONFLUENCE_THRESHOLD=70")

    st.divider()
    st.markdown("### Cooldown Status")
    st.caption(
        "Cooldown configuration governs delivery frequency for otherwise-eligible automatic alerts. "
        "Modifying or disabling cooldown does not bypass evidence gating."
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
            "Recent alert history and suppression audit telemetry. "
            "Evidence gate suppressions and delivery outcomes are recorded here."
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
| Alert type | Trigger condition | External Delivery Status |
|---|---|---|
| **Coil detected** | Coil strength ≥ threshold after scan | ⛔ Gated (exploratory — no approved strategy) |
| **Confluence** | Cross-timeframe score ≥ threshold | ⛔ Gated (exploratory — no approved strategy) |
| **Gap up** | Pre-market gap ≥ 4% upward (8am ET) | ⛔ Gated (exploratory — no approved strategy) |
| **Gap down** | Pre-market gap ≥ 4% downward (8am ET) | ⛔ Gated (exploratory — no approved strategy) |
| **Pattern similarity** | Experimental research only | ⛔ Quarantined (rejected on holdout) |

Run the watcher to evaluate observations and record local history:
```bash
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
```

Add a cooldown override for future eligible alerts:
```bash
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-cooldown-minutes 120
```

Disable cooldown for future eligible alerts (does not bypass evidence gating):
```bash
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --disable-alert-cooldown
```
""")
    
