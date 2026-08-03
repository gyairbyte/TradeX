"""Alert policy: identity, cooldown, atomic claim, and delivery-result logic."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from tradex.alerts.models import (
    AlertCooldownConfig,
    AlertDecision,
    AlertDispatchResult,
    AlertKey,
    ensure_aware_utc,
)
from tradex.alerts.notifier import is_alert_configured, send_alert
from tradex.alerts.store import AlertStateError, AlertStore

_DEFAULT_LEASE_SECONDS = 120


def _payload_hash(subject: str, body: str, color_key: str) -> str:
    """Deterministic SHA-256 fingerprint of an alert payload for audit."""
    payload = json.dumps(
        {"subject": subject, "body": body, "color_key": color_key},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sanitize_exception(exc: BaseException) -> str:
    """Sanitize an exception for logging/state without exposing credentials."""
    text = str(exc)
    # Redact common secret patterns: long hex tokens and email addresses.
    text = re.sub(r"\b[A-Fa-f0-9]{24,}\b", "[REDACTED]", text)
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED]", text
    )
    return text[:500]


class AlertPolicy:
    """Enforces cooldown, atomic claim, and delivery-success semantics.

    ``transport`` is a callable ``(subject, body, color_key) -> dict[str, bool]``.
    ``is_configured`` returns whether at least one channel is configured.
    Both default to the raw notifier functions so the watcher can inject mocks
    for deterministic tests.
    """

    def __init__(
        self,
        config: AlertCooldownConfig | None = None,
        store: AlertStore | None = None,
        transport: Callable[[str, str, str], dict[str, bool]] | None = None,
        is_configured: Callable[[], bool] | None = None,
        *,
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    ) -> None:
        self.config = config or AlertCooldownConfig()
        self.store = store or AlertStore(self.config.resolved_state_path)
        self.transport = transport or send_alert
        self.is_configured = is_configured or is_alert_configured
        self.lease_seconds = lease_seconds

    def cooldown_minutes_for(self, key: AlertKey) -> int | None:
        return self.config.cooldown_minutes_for(key)

    def _cooldown_minutes_for(self, key: AlertKey) -> int | None:
        return self.cooldown_minutes_for(key)

    def _send_without_cooldown(
        self,
        key: AlertKey,
        subject: str,
        body: str,
        color_key: str,
        observed_at: datetime,
    ) -> AlertDispatchResult:
        """Send without state when cooldown is disabled."""
        try:
            channel_results = self.transport(subject, body, color_key)
        except Exception as exc:  # noqa: BLE001
            sanitized = _sanitize_exception(exc)
            return AlertDispatchResult(
                key=key,
                decision=AlertDecision.DELIVERY_FAILED,
                observed_at=observed_at,
                cooldown_minutes=None,
                last_success_at=None,
                next_eligible_at=None,
                reason=f"Transport exception: {sanitized}",
                channel_results={},
                error=sanitized,
            )
        return AlertDispatchResult(
            key=key,
            decision=AlertDecision.COOLDOWN_DISABLED,
            observed_at=observed_at,
            cooldown_minutes=None,
            last_success_at=None,
            next_eligible_at=None,
            reason="Cooldown disabled; alert sent without state",
            channel_results=channel_results,
        )

    def dispatch(
        self,
        key: AlertKey,
        subject: str,
        body: str,
        *,
        color_key: str = "test",
        observed_at: datetime | None = None,
    ) -> AlertDispatchResult:
        """Dispatch an automatic alert under the cooldown policy.

        Returns an immutable ``AlertDispatchResult``. The transport call happens
        outside any database lock, and state is only mutated for successful sends
        (to start cooldown) or delivery failures (to increment counters).
        """
        observed_at = ensure_aware_utc(observed_at)
        cooldown_minutes = self._cooldown_minutes_for(key)

        if not self.config.enabled or cooldown_minutes is None:
            return self._send_without_cooldown(key, subject, body, color_key, observed_at)

        # Acquire an atomic claim before touching the transport.
        try:
            claim = self.store.claim(key, observed_at, lease_seconds=self.lease_seconds)
        except AlertStateError as exc:
            reason = f"State store error: {exc}"
            return AlertDispatchResult(
                key=key,
                decision=AlertDecision.POLICY_ERROR,
                observed_at=observed_at,
                cooldown_minutes=cooldown_minutes,
                last_success_at=None,
                next_eligible_at=None,
                reason=reason,
                channel_results={},
                error=str(exc),
            )

        if not claim["allowed"]:
            return AlertDispatchResult(
                key=key,
                decision=claim["decision"],
                observed_at=observed_at,
                cooldown_minutes=cooldown_minutes,
                last_success_at=claim["last_success_at"],
                next_eligible_at=claim["next_eligible_at"],
                reason=claim["reason"],
                channel_results={},
            )

        token = claim["token"]
        payload_hash = _payload_hash(subject, body, color_key)

        # Transport runs outside the SQLite lock.
        try:
            channel_results = self.transport(subject, body, color_key)
        except Exception as exc:  # noqa: BLE001
            sanitized = _sanitize_exception(exc)
            try:
                self.store.finalize(
                    key,
                    token,
                    observed_at,
                    AlertDecision.DELIVERY_FAILED,
                    None,
                    subject,
                    payload_hash,
                    {},
                    reason=f"Transport exception: {sanitized}",
                )
            except AlertStateError as store_exc:
                return AlertDispatchResult(
                    key=key,
                    decision=AlertDecision.POLICY_ERROR,
                    observed_at=observed_at,
                    cooldown_minutes=cooldown_minutes,
                    last_success_at=claim["last_success_at"],
                    next_eligible_at=None,
                    reason=f"Transport exception and state finalize failed: {store_exc}",
                    channel_results={},
                    error=f"{sanitized}; store: {store_exc}",
                )
            return AlertDispatchResult(
                key=key,
                decision=AlertDecision.DELIVERY_FAILED,
                observed_at=observed_at,
                cooldown_minutes=cooldown_minutes,
                last_success_at=claim["last_success_at"],
                next_eligible_at=None,
                reason=f"Transport exception: {sanitized}",
                channel_results={},
                error=sanitized,
            )

        if any(channel_results.values()):
            decision = AlertDecision.SENT
            reason = "At least one channel succeeded"
            next_eligible_at = observed_at + timedelta(minutes=cooldown_minutes)
            last_success_at = observed_at
        elif not self.is_configured():
            decision = AlertDecision.NO_CHANNELS_CONFIGURED
            reason = "No alert channels are configured"
            next_eligible_at = None
            last_success_at = claim["last_success_at"]
        else:
            decision = AlertDecision.DELIVERY_FAILED
            reason = "All configured channels returned False"
            next_eligible_at = None
            last_success_at = claim["last_success_at"]

        try:
            self.store.finalize(
                key,
                token,
                observed_at,
                decision,
                cooldown_minutes if decision == AlertDecision.SENT else None,
                subject,
                payload_hash,
                channel_results,
                reason,
            )
        except AlertStateError as exc:
            return AlertDispatchResult(
                key=key,
                decision=AlertDecision.POLICY_ERROR,
                observed_at=observed_at,
                cooldown_minutes=cooldown_minutes,
                last_success_at=claim["last_success_at"],
                next_eligible_at=next_eligible_at,
                reason=f"State store finalize failed: {exc}",
                channel_results=channel_results,
                error=str(exc),
            )

        return AlertDispatchResult(
            key=key,
            decision=decision,
            observed_at=observed_at,
            cooldown_minutes=cooldown_minutes,
            last_success_at=last_success_at,
            next_eligible_at=next_eligible_at,
            reason=reason,
            channel_results=channel_results,
        )

    def list_alert_states(
        self,
        *,
        ticker: str | None = None,
        alert_type: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Stable read API over the persistent alert state."""
        return self.store.list_alert_states(
            ticker=ticker, alert_type=alert_type, limit=limit
        )
