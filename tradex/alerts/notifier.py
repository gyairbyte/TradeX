"""Alert notifier — Discord bot and email.

Sends alerts when:
  - A coil score crosses the coil threshold
  - A pattern match similarity crosses the alert threshold
  - A confluence score crosses the confluence threshold
  - A pre-market gap exceeds the gap threshold

Discord setup (one-time):
  1. Go to https://discord.com/developers/applications → New Application
  2. Bot tab → Add Bot → copy the Token → set ALERT_DISCORD_TOKEN
  3. OAuth2 → URL Generator → scopes: bot → permissions: Send Messages, Embed Links
  4. Open the generated URL to invite the bot to your server
  5. Right-click the channel you want alerts in → Copy Channel ID → set ALERT_DISCORD_CHANNEL_ID
     (Enable Developer Mode in Discord settings if you don't see Copy ID)

Email setup:
  For Gmail, generate an App Password at myaccount.google.com/apppasswords
  and use that as ALERT_EMAIL_PASS (not your regular Gmail password).

Config via .env:
  ALERT_DISCORD_TOKEN       — Discord bot token
  ALERT_DISCORD_CHANNEL_ID  — ID of the channel to post alerts to
  ALERT_EMAIL_TO            — recipient address
  ALERT_EMAIL_FROM          — sender address
  ALERT_EMAIL_HOST          — SMTP host (default: smtp.gmail.com)
  ALERT_EMAIL_PORT          — SMTP port (default: 587)
  ALERT_EMAIL_USER          — SMTP login username
  ALERT_EMAIL_PASS          — SMTP app password
"""
from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Any

import requests

from tradex.alerts.models import (
    AlertDecision,
    AlertDispatchResult,
    AlertKey,
    _sanitize_channel_results,
    ensure_aware_utc,
)
from tradex.config import (
    AlertChannelSettings,
    AlertThresholdSettings,
    TradeXSettings,
    load_runtime_settings,
)


# Public defaults used when no runtime settings are provided (e.g. direct imports
# without an explicit settings object). Real channel/threshold values are read
# from the central ``TradeXSettings`` boundary at call time.
COIL_ALERT_THRESHOLD = 60
CONFLUENCE_ALERT_THRESHOLD = 70
PATTERN_ALERT_THRESHOLD = 75.0

# Internal aliases to keep the notifier implementation consistent.
_COIL_ALERT_THRESHOLD = COIL_ALERT_THRESHOLD
_PATTERN_ALERT_THRESHOLD = PATTERN_ALERT_THRESHOLD
_CONFLUENCE_ALERT_THRESHOLD = CONFLUENCE_ALERT_THRESHOLD


def _alert_channels(settings: TradeXSettings | None = None) -> AlertChannelSettings:
    if settings is None:
        settings = load_runtime_settings()
    return settings.alert_channels


def _alert_thresholds(settings: TradeXSettings | None = None) -> AlertThresholdSettings:
    if settings is None:
        settings = load_runtime_settings()
    return settings.alert_thresholds

# Discord embed colors per alert type
_COLORS = {
    "coil":      0xF4A700,   # amber
    "pattern":   0x5865F2,   # blurple
    "confluence":0x57F287,   # green
    "gap_up":    0x57F287,   # green
    "gap_down":  0xED4245,   # red
    "test":      0x99AAB5,   # grey
}


def _send_discord(
    subject: str,
    body: str,
    color_key: str = "test",
    *,
    channels: AlertChannelSettings | None = None,
) -> bool:
    """
    Send a rich embed message via the Discord bot API.
    Uses embeds so alerts are visually distinct from regular chat.
    """
    channels = channels or _alert_channels()
    token = channels.discord_token
    channel_id = channels.discord_channel_id
    if not token or not channel_id:
        return False
    try:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        embed = {
            "title":       f"TradeX — {subject}",
            "description": f"```{body}```",
            "color":       _COLORS.get(color_key, 0x99AAB5),
            "footer":      {"text": f"TradeX • {now}"},
        }
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type":  "application/json",
        }
        resp = requests.post(url, json={"embeds": [embed]}, headers=headers, timeout=10)
        if resp.status_code not in (200, 201):
            print(f"[alert] Discord error {resp.status_code}: {resp.text}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[alert] Discord error: {e}")
        return False


def _send_email(
    subject: str,
    body: str,
    *,
    channels: AlertChannelSettings | None = None,
) -> bool:
    channels = channels or _alert_channels()
    if not all(
        [channels.email_to, channels.email_from, channels.email_host, channels.email_user, channels.email_pass]
    ):
        return False
    try:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        msg = MIMEText(f"{body}\n\nSent: {now}", "plain")
        msg["Subject"] = f"TradeX: {subject}"
        msg["From"]    = channels.email_from
        msg["To"]      = channels.email_to
        with smtplib.SMTP(channels.email_host, channels.email_port) as server:
            server.starttls()
            server.login(channels.email_user, channels.email_pass)
            server.sendmail(channels.email_from, channels.email_to, msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[alert] Email error: {e}")
        return False


def send_alert(
    subject: str,
    body: str,
    color_key: str = "test",
    *,
    settings: TradeXSettings | None = None,
) -> dict[str, bool]:
    """Send an alert to all configured channels. Returns which channels succeeded."""
    channels = _alert_channels(settings)
    results = {
        "discord": _send_discord(subject, body, color_key=color_key, channels=channels),
        "email":   _send_email(subject, body, channels=channels),
    }
    sent = [k for k, v in results.items() if v]
    print(f"[alert] '{subject}' → {sent if sent else 'no channels configured'}")
    return results


def is_alert_configured(*, settings: TradeXSettings | None = None) -> bool:
    """Return ``True`` when at least one alert channel has credentials configured."""
    channels = _alert_channels(settings)
    discord_ready = bool(channels.discord_token and channels.discord_channel_id)
    email_ready = bool(
        all(
            [
                channels.email_to,
                channels.email_from,
                channels.email_host,
                channels.email_user,
                channels.email_pass,
            ]
        )
    )
    return discord_ready or email_ready


def _cooldown_minutes_for(
    policy: Any | None,
    key: AlertKey,
) -> int | None:
    if policy is None:
        return None
    return policy.cooldown_minutes_for(key)


def _decision_from_raw_send(
    channel_results: dict[str, bool],
    *,
    settings: TradeXSettings | None = None,
) -> tuple[AlertDecision, str]:
    """Classify a raw send result without a cooldown policy."""
    if not is_alert_configured(settings=settings):
        return AlertDecision.NO_CHANNELS_CONFIGURED, "No alert channels are configured"
    if any(channel_results.values()):
        return AlertDecision.COOLDOWN_DISABLED, "Cooldown disabled; alert sent without state"
    return AlertDecision.DELIVERY_FAILED, "All configured channels returned False"


def _dispatch_or_raw(
    key: AlertKey,
    subject: str,
    body: str,
    color_key: str,
    policy: Any | None,
    observed_at: datetime | None,
    *,
    settings: TradeXSettings | None = None,
) -> AlertDispatchResult:
    """Dispatch through a policy if provided, otherwise send raw and return a result."""
    observed_at = ensure_aware_utc(observed_at)
    if policy is not None:
        return policy.dispatch(key, subject, body, color_key=color_key, observed_at=observed_at)
    try:
        raw_results = send_alert(subject, body, color_key, settings=settings)
    except Exception as exc:  # noqa: BLE001
        return AlertDispatchResult(
            key=key,
            decision=AlertDecision.DELIVERY_FAILED,
            observed_at=observed_at,
            cooldown_minutes=None,
            last_success_at=None,
            next_eligible_at=None,
            reason=f"Raw send failed: {exc}",
            channel_results={},
            error=str(exc)[:500],
        )

    try:
        channel_results = _sanitize_channel_results(raw_results)
    except ValueError as exc:
        return AlertDispatchResult(
            key=key,
            decision=AlertDecision.DELIVERY_FAILED,
            observed_at=observed_at,
            cooldown_minutes=None,
            last_success_at=None,
            next_eligible_at=None,
            reason=f"Malformed raw send result: {exc}",
            channel_results={},
            error=str(exc)[:500],
        )

    decision, reason = _decision_from_raw_send(channel_results, settings=settings)
    return AlertDispatchResult(
        key=key,
        decision=decision,
        observed_at=observed_at,
        cooldown_minutes=None,
        last_success_at=None,
        next_eligible_at=None,
        reason=reason,
        channel_results=channel_results,
    )


def _below_threshold_result(
    key: AlertKey,
    policy: Any | None,
    observed_at: datetime | None,
    reason: str,
) -> AlertDispatchResult:
    observed_at = ensure_aware_utc(observed_at)
    return AlertDispatchResult(
        key=key,
        decision=AlertDecision.BELOW_THRESHOLD,
        observed_at=observed_at,
        cooldown_minutes=_cooldown_minutes_for(policy, key),
        last_success_at=None,
        next_eligible_at=None,
        reason=reason,
        channel_results={},
    )


# ── typed alert helpers ───────────────────────────────────────────────────────

def alert_coil(
    ticker: str,
    coil_strength: float,
    score: int,
    trend: str,
    timeframe: str,
    *,
    policy: Any | None = None,
    observed_at: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> AlertDispatchResult:
    thresholds = _alert_thresholds(settings)
    key = AlertKey(ticker=ticker, alert_type="coil", timeframe=timeframe)
    if coil_strength < thresholds.coil:
        return _below_threshold_result(
            key,
            policy,
            observed_at,
            f"Coil strength {coil_strength} below threshold {thresholds.coil}",
        )
    subject = f"Coil Detected: {ticker}"
    body = (
        f"Ticker:        {ticker}\n"
        f"Timeframe:     {timeframe}\n"
        f"Coil strength: {coil_strength}\n"
        f"Latest score:  {score}\n"
        f"Trend:         {trend}\n\n"
        f"Building pressure over multiple sessions — no breakout yet."
    )
    return _dispatch_or_raw(key, subject, body, "coil", policy, observed_at, settings=settings)


def alert_pattern_match(
    ticker: str,
    similarity: float,
    event_type: str,
    profile: str,
    fp_events: int,
    interpretation: str,
    *,
    policy: Any | None = None,
    observed_at: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> AlertDispatchResult:
    thresholds = _alert_thresholds(settings)
    key = AlertKey(ticker=ticker, alert_type=f"pattern:{event_type}:{profile}", timeframe="pattern")
    if similarity < thresholds.pattern:
        return _below_threshold_result(
            key,
            policy,
            observed_at,
            f"Pattern similarity {similarity} below threshold {thresholds.pattern}",
        )
    subject = f"Pattern Match: {ticker} — {event_type.upper()} ({similarity:.0f}%)"
    body = (
        f"Ticker:       {ticker}\n"
        f"Pattern:      {event_type}\n"
        f"Profile:      {profile}\n"
        f"Similarity:   {similarity:.1f}%\n"
        f"Based on:     {fp_events} historical events\n\n"
        f"{interpretation}"
    )
    return _dispatch_or_raw(key, subject, body, "pattern", policy, observed_at, settings=settings)


def alert_confluence(
    ticker: str,
    confluence_score: int,
    active_timeframes: list[str],
    last_close: float,
    *,
    policy: Any | None = None,
    observed_at: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> AlertDispatchResult:
    thresholds = _alert_thresholds(settings)
    key = AlertKey(ticker=ticker, alert_type="confluence", timeframe="multi")
    if confluence_score < thresholds.confluence:
        return _below_threshold_result(
            key,
            policy,
            observed_at,
            f"Confluence score {confluence_score} below threshold {thresholds.confluence}",
        )
    subject = f"Confluence Alert: {ticker} ({confluence_score}/100)"
    body = (
        f"Ticker:            {ticker}\n"
        f"Confluence score:  {confluence_score}\n"
        f"Active timeframes: {', '.join(active_timeframes)}\n"
        f"Last close:        ${last_close:.2f}\n\n"
        f"Multiple timeframes aligned — higher conviction setup."
    )
    return _dispatch_or_raw(key, subject, body, "confluence", policy, observed_at, settings=settings)


def alert_gap(
    ticker: str,
    gap_pct: float,
    direction: str,
    prev_close: float,
    pre_market: float,
    *,
    policy: Any | None = None,
    observed_at: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> AlertDispatchResult:
    key = AlertKey(ticker=ticker, alert_type=f"gap:{direction}", timeframe="premarket")
    subject = f"Pre-Market Gap {direction.upper()}: {ticker} ({gap_pct:+.1f}%)"
    body = (
        f"Ticker:      {ticker}\n"
        f"Direction:   {direction}\n"
        f"Gap:         {gap_pct:+.1f}%\n"
        f"Prev close:  ${prev_close:.2f}\n"
        f"Pre-market:  ${pre_market:.2f}\n\n"
        f"Significant pre-market gap detected before open."
    )
    return _dispatch_or_raw(
        key, subject, body, f"gap_{direction}", policy, observed_at, settings=settings
    )
