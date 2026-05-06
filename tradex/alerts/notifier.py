"""
Alert notifier — Slack and email.

Sends alerts when:
  - A coil score crosses the coil threshold
  - A pattern match similarity crosses the alert threshold
  - A confluence score crosses the confluence threshold

Config via .env:
  ALERT_SLACK_WEBHOOK  — Slack incoming webhook URL
  ALERT_EMAIL_TO       — recipient address
  ALERT_EMAIL_FROM     — sender address
  ALERT_EMAIL_HOST     — SMTP host (e.g. smtp.gmail.com)
  ALERT_EMAIL_PORT     — SMTP port (default 587)
  ALERT_EMAIL_USER     — SMTP login username
  ALERT_EMAIL_PASS     — SMTP login password (use an app password for Gmail)

Leave any group empty to disable that channel. Both channels can be
active simultaneously.
"""
from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

# ── channel config ────────────────────────────────────────────────────────────
SLACK_WEBHOOK   = os.getenv("ALERT_SLACK_WEBHOOK", "")
EMAIL_TO        = os.getenv("ALERT_EMAIL_TO", "")
EMAIL_FROM      = os.getenv("ALERT_EMAIL_FROM", "")
EMAIL_HOST      = os.getenv("ALERT_EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT      = int(os.getenv("ALERT_EMAIL_PORT", "587"))
EMAIL_USER      = os.getenv("ALERT_EMAIL_USER", "")
EMAIL_PASS      = os.getenv("ALERT_EMAIL_PASS", "")

# ── alert thresholds ──────────────────────────────────────────────────────────
COIL_ALERT_THRESHOLD        = int(os.getenv("ALERT_COIL_THRESHOLD", "60"))
PATTERN_ALERT_THRESHOLD     = float(os.getenv("ALERT_PATTERN_THRESHOLD", "75"))
CONFLUENCE_ALERT_THRESHOLD  = int(os.getenv("ALERT_CONFLUENCE_THRESHOLD", "70"))


def _send_slack(message: str) -> bool:
    if not SLACK_WEBHOOK:
        return False
    try:
        resp = requests.post(
            SLACK_WEBHOOK,
            data=json.dumps({"text": message}),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[alert] Slack error: {e}")
        return False


def _send_email(subject: str, body: str) -> bool:
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_HOST, EMAIL_USER, EMAIL_PASS]):
        return False
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        print(f"[alert] Email error: {e}")
        return False


def send_alert(subject: str, body: str) -> dict[str, bool]:
    """Send an alert to all configured channels. Returns which channels succeeded."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    slack_msg = f"*TradeX Alert — {now}*\n*{subject}*\n{body}"
    results = {
        "slack": _send_slack(slack_msg),
        "email": _send_email(f"TradeX: {subject}", f"{body}\n\nSent: {now}"),
    }
    sent = [k for k, v in results.items() if v]
    print(f"[alert] '{subject}' → {sent if sent else 'no channels configured'}")
    return results


# ── typed alert helpers ───────────────────────────────────────────────────────

def alert_coil(ticker: str, coil_strength: float, score: int, trend: str, timeframe: str):
    if coil_strength < COIL_ALERT_THRESHOLD:
        return
    send_alert(
        subject=f"Coil Detected: {ticker}",
        body=(
            f"Ticker:        {ticker}\n"
            f"Timeframe:     {timeframe}\n"
            f"Coil strength: {coil_strength}\n"
            f"Latest score:  {score}\n"
            f"Trend:         {trend}\n\n"
            f"This stock has been building pressure over multiple sessions "
            f"without breaking out. Watch for a resolution."
        ),
    )


def alert_pattern_match(
    ticker: str,
    similarity: float,
    event_type: str,
    profile: str,
    fp_events: int,
    interpretation: str,
):
    if similarity < PATTERN_ALERT_THRESHOLD:
        return
    send_alert(
        subject=f"Pattern Match: {ticker} looks like a {event_type.upper()} setup ({similarity:.0f}%)",
        body=(
            f"Ticker:       {ticker}\n"
            f"Pattern type: {event_type}\n"
            f"Profile:      {profile}\n"
            f"Similarity:   {similarity:.1f}%\n"
            f"Based on:     {fp_events} historical events\n\n"
            f"{interpretation}"
        ),
    )


def alert_confluence(ticker: str, confluence_score: int, active_timeframes: list[str], last_close: float):
    if confluence_score < CONFLUENCE_ALERT_THRESHOLD:
        return
    send_alert(
        subject=f"Confluence Alert: {ticker} ({confluence_score}/100)",
        body=(
            f"Ticker:            {ticker}\n"
            f"Confluence score:  {confluence_score}\n"
            f"Active timeframes: {', '.join(active_timeframes)}\n"
            f"Last close:        ${last_close:.2f}\n\n"
            f"Multiple timeframes aligned — higher conviction setup."
        ),
    )


def alert_gap(ticker: str, gap_pct: float, direction: str, prev_close: float, pre_market: float):
    send_alert(
        subject=f"Pre-Market Gap {direction.upper()}: {ticker} ({gap_pct:+.1f}%)",
        body=(
            f"Ticker:          {ticker}\n"
            f"Direction:       {direction}\n"
            f"Gap:             {gap_pct:+.1f}%\n"
            f"Prev close:      ${prev_close:.2f}\n"
            f"Pre-market:      ${pre_market:.2f}\n\n"
            f"Significant pre-market gap detected before open."
        ),
    )
