"""Tests for the extracted Alerts tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.alerts.models import AlertCooldownConfig
from tradex.alerts.policy import AlertPolicy
from tradex.config import TradeXSettings, settings_from_mapping


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _configured_settings(tmp_path) -> TradeXSettings:
    return settings_from_mapping(
        {
            "ALERT_DISCORD_TOKEN": "fake-discord-token-12345",
            "ALERT_DISCORD_CHANNEL_ID": "fake-channel-67890",
            "ALERT_EMAIL_TO": "gary@example.com",
            "ALERT_EMAIL_FROM": "alerts@example.com",
            "ALERT_EMAIL_HOST": "smtp.gmail.com",
            "ALERT_EMAIL_PORT": "587",
            "ALERT_EMAIL_USER": "alerts@example.com",
            "ALERT_EMAIL_PASS": "fake-email-password-secret",
            "ALERT_STATE_PATH": str(tmp_path / "alerts.db"),
        }
    )


def _make_policy(settings: TradeXSettings, *, tmp_path) -> AlertPolicy:
    """Build an AlertPolicy with a mocked store for isolated rendering tests."""
    store = MagicMock(name="alert_store")
    store.resolved_path = MagicMock(name="resolved_path")
    store.resolved_path.exists.return_value = False
    return AlertPolicy(
        config=settings.alert_cooldown,
        store=store,
        transport=MagicMock(return_value={}),
        is_configured=MagicMock(return_value=False),
        settings=settings,
    )


@pytest.fixture
def alerts_tab_module(fake_st, monkeypatch):
    """Import the Alerts tab fresh with a mocked Streamlit and safe backend defaults."""
    mod_name = "tradex.ui.tabs.alerts"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    mod = importlib.import_module(mod_name)
    # Provide deterministic settings and a no-op send_alert for the tab module.
    monkeypatch.setattr(mod, "load_runtime_settings", MagicMock(return_value=_default_settings()))
    monkeypatch.setattr(mod, "send_alert", MagicMock(return_value={"discord": False, "email": False}))
    return mod


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render widgets or call alert backends."""
    mod_name = "tradex.ui.tabs.alerts"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    alert_policy_cls = MagicMock()
    send_alert_fn = MagicMock()
    load_runtime_fn = MagicMock()
    list_states_fn = MagicMock()
    monkeypatch.setattr("tradex.alerts.policy.AlertPolicy", alert_policy_cls)
    monkeypatch.setattr("tradex.alerts.notifier.send_alert", send_alert_fn)
    monkeypatch.setattr("tradex.config.load_runtime_settings", load_runtime_fn)
    monkeypatch.setattr("tradex.alerts.store.AlertStore.list_alert_states", list_states_fn)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.markdown.call_count == 0
    assert alert_policy_cls.call_count == 0
    assert send_alert_fn.call_count == 0
    assert load_runtime_fn.call_count == 0
    assert list_states_fn.call_count == 0


def test_unconfigured_channels_show_setup_examples(alerts_tab_module, fake_st, monkeypatch):
    """When no alert channel is configured, the tab shows the not-configured messages and examples."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=settings.alert_cooldown.resolved_state_path)
    alerts_tab_module.load_runtime_settings.return_value = settings
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("Delivery Infrastructure" in t for t in info_texts)

    error_texts = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Discord: **Not configured**" in t for t in error_texts)
    assert any("Email: **Not configured**" in t for t in error_texts)

    code_texts = [str(c[0][0]) for c in fake_st.code.call_args_list]
    assert any("ALERT_DISCORD_TOKEN" in t for t in code_texts)
    assert any("ALERT_EMAIL_PASS" in t for t in code_texts)


def test_configured_channels_do_not_expose_secrets(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """Configured channels display status without leaking tokens or passwords."""
    settings = _configured_settings(tmp_path)
    policy = _make_policy(settings, tmp_path=tmp_path)
    alerts_tab_module.load_runtime_settings.return_value = settings
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("Discord: **Connected**" in t for t in success_texts)
    assert any("Email: **Configured** → gary@example.com" in t for t in success_texts)

    leaked_values = {"fake-discord-token-12345", "fake-email-password-secret", "fake-channel-67890"}
    all_renders = []
    for method in (fake_st.success, fake_st.error, fake_st.markdown, fake_st.caption, fake_st.metric):
        for call in method.call_args_list:
            for arg in call.args:
                all_renders.append(str(arg))
            for kwarg in call.kwargs.values():
                all_renders.append(str(kwarg))
    for col_list in fake_st._column_returns:
        for col in col_list:
            for call in col.metric.call_args_list:
                for arg in call.args:
                    all_renders.append(str(arg))
                for kwarg in call.kwargs.values():
                    all_renders.append(str(kwarg))
    joined = " ".join(all_renders)
    for secret in leaked_values:
        assert secret not in joined


def test_thresholds_display_from_explicit_settings(alerts_tab_module, fake_st, monkeypatch):
    """The Alerts tab displays the configured coil and confluence thresholds."""
    settings = settings_from_mapping(
        {"ALERT_COIL_THRESHOLD": "55", "ALERT_CONFLUENCE_THRESHOLD": "75"}
    )
    policy = _make_policy(settings, tmp_path=settings.alert_cooldown.resolved_state_path)
    alerts_tab_module.load_runtime_settings.return_value = settings
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    metric_labels = []
    for col_list in fake_st._column_returns:
        for col in col_list:
            for call in col.metric.call_args_list:
                metric_labels.append((call.args[0], call.args[1] if len(call.args) > 1 else None))
    assert ("Coil threshold", "55") in metric_labels
    assert ("Confluence threshold", "75") in metric_labels


def test_effective_cooldowns_helper(alerts_tab_module):
    """_effective_cooldowns exposes per-alert-type cooldown durations."""
    cfg = AlertCooldownConfig(enabled=True, default_minutes=60, coil_minutes=30)
    result = alerts_tab_module._effective_cooldowns(cfg)
    assert result["coil"] == 30
    assert result["confluence"] == 60
    assert result["gap"] == 60
    assert "pattern" not in result  # pattern matching is quarantined from automatic alerts

    disabled_cfg = AlertCooldownConfig(enabled=False)
    assert alerts_tab_module._effective_cooldowns(disabled_cfg) == {"status": "disabled"}


def test_alert_policy_from_env_honors_state_path_and_does_not_create_db(alerts_tab_module, tmp_path):
    """The policy helper uses ALERT_STATE_PATH and does not initialize the database."""
    state_path = tmp_path / "tab_alerts.db"
    settings = settings_from_mapping({"ALERT_STATE_PATH": str(state_path)})
    alerts_tab_module.load_runtime_settings.return_value = settings

    policy = alerts_tab_module._alert_policy_from_env()

    assert policy.config.resolved_state_path == state_path
    assert not state_path.exists()


def test_state_not_initialized_shows_message_and_skips_query(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When the state file does not exist, the tab shows the not-initialized message."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    policy.store.resolved_path.exists.return_value = False
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("has not been initialized yet" in t for t in info_texts)
    assert policy.store.list_alert_states.call_count == 0


def test_empty_state_shows_no_records_message(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When the state file exists but contains no records, the tab shows the empty message."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    policy.store.resolved_path.exists.return_value = True
    policy.store.list_alert_states.return_value = pd.DataFrame(
        columns=[
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
    )
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("No alert state records yet" in t for t in info_texts)
    policy.store.list_alert_states.assert_called_once()


def test_populated_state_renders_display_columns(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When alert state has records, the tab renders the expected display columns."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    policy.store.resolved_path.exists.return_value = True
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
    policy.store.list_alert_states.return_value = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "alert_type": ["coil"],
            "timeframe": ["short"],
            "last_decision": ["sent"],
            "last_success_at": ["2026-01-01T00:00:00+00:00"],
            "cooldown_until": ["2026-01-01T01:00:00+00:00"],
            "sent_count": [1],
            "suppressed_count": [0],
            "failed_count": [0],
            "extra": ["ignored"],
        }
    )
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    assert fake_st.dataframe.call_count >= 1
    passed_df = fake_st.dataframe.call_args[0][0]
    assert list(passed_df.columns) == display_cols


def test_state_query_failure_shows_error(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When alert state query fails, the tab shows the existing unavailable/corrupt error."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    policy.store.resolved_path.exists.return_value = True
    policy.store.list_alert_states.side_effect = Exception("database is locked")
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    error_texts = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("unavailable or corrupt" in t for t in error_texts)


def test_invalid_cooldown_configuration_shows_error(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When the alert cooldown config is invalid, the tab shows the existing error."""
    settings = _default_settings()
    monkeypatch.setattr(
        alerts_tab_module,
        "_alert_policy_from_env",
        MagicMock(side_effect=ValueError("ALERT_COOLDOWN_MINUTES must be an integer")),
    )

    alerts_tab_module.render_alerts_tab(settings=settings)

    error_texts = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Invalid alert cooldown configuration" in t for t in error_texts)


def test_no_test_alert_click_does_not_call_send_alert(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """When the test-alert button is not clicked, send_alert is not invoked."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)

    alerts_tab_module.render_alerts_tab(settings=settings)

    alerts_tab_module.send_alert.assert_not_called()


def test_test_alert_click_calls_send_alert_once(alerts_tab_module, fake_st, tmp_path, monkeypatch):
    """Clicking Send Test Alert calls send_alert exactly once with the existing subject and body."""
    settings = _default_settings()
    policy = _make_policy(settings, tmp_path=tmp_path)
    monkeypatch.setattr(alerts_tab_module, "_alert_policy_from_env", lambda: policy)
    alerts_tab_module.send_alert.return_value = {"discord": True, "email": False}
    fake_st._active_button_keys = {"btn_test_alert"}

    alerts_tab_module.render_alerts_tab(settings=settings)

    alerts_tab_module.send_alert.assert_called_once_with(
        subject="TradeX Test Alert",
        body="This is a test alert from your TradeX dashboard. If you received this, alerts are configured correctly.",
    )
    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("Test alert sent via: discord" in t for t in success_texts)
    assert any("Not sent (not configured): email" in t for t in warning_texts)
