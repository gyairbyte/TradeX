"""Typed alert policy, key, configuration, and dispatch-result models."""
from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class AlertDecision(str, Enum):
    """Stable, machine-readable automatic alert outcome."""

    SENT = "sent"
    SUPPRESSED_COOLDOWN = "suppressed_cooldown"
    SUPPRESSED_IN_FLIGHT = "suppressed_in_flight"
    DELIVERY_FAILED = "delivery_failed"
    NO_CHANNELS_CONFIGURED = "no_channels_configured"
    POLICY_ERROR = "policy_error"
    BELOW_THRESHOLD = "below_threshold"
    COOLDOWN_DISABLED = "cooldown_disabled"


_MAX_KEY_LEN = 80
_MAX_ALERT_TYPE_LEN = 80
_MAX_TIMEFRAME_LEN = 40
_MAX_COOLDOWN_MINUTES = 7 * 24 * 60  # one week
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")


def _reject_control(value: str, name: str) -> None:
    if _CONTROL_RE.search(value):
        raise ValueError(f"{name} contains control characters")


def _normalize_alert_key(ticker: str, alert_type: str, timeframe: str) -> tuple[str, str, str]:
    if not isinstance(ticker, str) or not isinstance(alert_type, str) or not isinstance(timeframe, str):
        raise TypeError("AlertKey fields must be strings")

    ticker = ticker.strip().upper()
    alert_type = alert_type.strip().lower()
    timeframe = timeframe.strip().lower()

    if not ticker:
        raise ValueError("ticker must not be empty")
    if not alert_type:
        raise ValueError("alert_type must not be empty")
    if not timeframe:
        raise ValueError("timeframe must not be empty")

    _reject_control(ticker, "ticker")
    _reject_control(alert_type, "alert_type")
    _reject_control(timeframe, "timeframe")

    if len(ticker) > _MAX_KEY_LEN:
        raise ValueError(f"ticker exceeds max length {_MAX_KEY_LEN}")
    if len(alert_type) > _MAX_ALERT_TYPE_LEN:
        raise ValueError(f"alert_type exceeds max length {_MAX_ALERT_TYPE_LEN}")
    if len(timeframe) > _MAX_TIMEFRAME_LEN:
        raise ValueError(f"timeframe exceeds max length {_MAX_TIMEFRAME_LEN}")

    return ticker, alert_type, timeframe


@dataclass(frozen=True, slots=True)
class AlertKey:
    """Immutable normalized identity for an automatic alert.

    Identity is (ticker, alert_type, timeframe) with trimming, upper-case ticker,
    lower-case type/timeframe, and rejection of control characters and empty values.
    """

    ticker: str
    alert_type: str
    timeframe: str

    def __post_init__(self) -> None:
        normalized = _normalize_alert_key(self.ticker, self.alert_type, self.timeframe)
        # frozen with slots requires object.__setattr__
        object.__setattr__(self, "ticker", normalized[0])
        object.__setattr__(self, "alert_type", normalized[1])
        object.__setattr__(self, "timeframe", normalized[2])

    def __str__(self) -> str:
        return f"{self.ticker} | {self.alert_type} | {self.timeframe}"


def _validate_minutes(value: int | None, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not bool")
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if isinstance(value, float):
        raise TypeError(f"{name} must be an integer, not float")
    if value <= 0:
        raise ValueError(f"{name} must be positive; use enabled=False to disable cooldown")
    if value > _MAX_COOLDOWN_MINUTES:
        raise ValueError(f"{name} exceeds maximum of {_MAX_COOLDOWN_MINUTES} minutes (7 days)")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite")


def _parse_env_minutes(raw: str, name: str) -> int:
    """Parse an environment-override cooldown value.

    Rejects empty strings, booleans, non-integers, negatives, zero, fractions,
    and values beyond one week.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError(f"{name} is set but empty")
    lower = raw.lower()
    if lower in ("true", "false", "yes", "no", "on", "off"):
        raise ValueError(f"{name} must be an integer, not a boolean string")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer: {raw!r}") from exc
    if str(value) != raw and not (raw.startswith("+") and str(value) == raw[1:]):
        # catches "60.0" or "  60" after int() succeeded, except leading +
        raise ValueError(f"{name} must be an integer without a fractional part: {raw!r}")
    _validate_minutes(value, name)
    return value


def _parse_env_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    if raw == "":
        raise ValueError("ALERT_COOLDOWN_ENABLED is set but empty")
    lower = raw.strip().lower()
    if lower in ("true", "1", "yes", "on"):
        return True
    if lower in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"ALERT_COOLDOWN_ENABLED must be a boolean string, got {raw!r}")


def _parse_env_path(raw: str | None, default: Path) -> Path:
    if raw is None:
        return default
    if raw == "":
        raise ValueError("ALERT_STATE_PATH is set but empty")
    return Path(raw)


@dataclass(frozen=True)
class AlertCooldownConfig:
    """Immutable alert-cooldown configuration.

    Environment variables:
      ALERT_COOLDOWN_ENABLED=true
      ALERT_COOLDOWN_MINUTES=60
      ALERT_COIL_COOLDOWN_MINUTES=
      ALERT_CONFLUENCE_COOLDOWN_MINUTES=
      ALERT_PATTERN_COOLDOWN_MINUTES=
      ALERT_GAP_COOLDOWN_MINUTES=
      ALERT_STATE_PATH=~/.tradex/alerts.db

    Per-type overrides fall back to default_minutes. ``state_path`` stores the
    literal (possibly ``~``-containing) path; expansion happens when the store
    first resolves the path.
    """

    enabled: bool = True
    default_minutes: int = 60
    coil_minutes: int | None = None
    confluence_minutes: int | None = None
    pattern_minutes: int | None = None
    gap_minutes: int | None = None
    state_path: Path = field(default_factory=lambda: Path("~/.tradex/alerts.db"))

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")
        if not isinstance(self.state_path, (str, Path)):
            raise TypeError("state_path must be a Path or str")
        if isinstance(self.state_path, str):
            object.__setattr__(self, "state_path", Path(self.state_path))
        _validate_minutes(self.default_minutes, "default_minutes")
        _validate_minutes(self.coil_minutes, "coil_minutes")
        _validate_minutes(self.confluence_minutes, "confluence_minutes")
        _validate_minutes(self.pattern_minutes, "pattern_minutes")
        _validate_minutes(self.gap_minutes, "gap_minutes")

    @classmethod
    def from_env(cls) -> AlertCooldownConfig:
        """Build a configuration from environment variables.

        Invalid values raise ValueError so watcher startup fails visibly.
        """
        enabled = _parse_env_bool(os.getenv("ALERT_COOLDOWN_ENABLED"), True)
        default_minutes = _parse_env_minutes(
            os.getenv("ALERT_COOLDOWN_MINUTES", "60"), "ALERT_COOLDOWN_MINUTES"
        )

        def _opt(name: str) -> int | None:
            raw = os.getenv(name)
            if raw is None:
                return None
            return _parse_env_minutes(raw, name)

        return cls(
            enabled=enabled,
            default_minutes=default_minutes,
            coil_minutes=_opt("ALERT_COIL_COOLDOWN_MINUTES"),
            confluence_minutes=_opt("ALERT_CONFLUENCE_COOLDOWN_MINUTES"),
            pattern_minutes=_opt("ALERT_PATTERN_COOLDOWN_MINUTES"),
            gap_minutes=_opt("ALERT_GAP_COOLDOWN_MINUTES"),
            state_path=_parse_env_path(os.getenv("ALERT_STATE_PATH"), Path("~/.tradex/alerts.db")),
        )

    def cooldown_minutes_for(self, key: AlertKey) -> int | None:
        """Effective cooldown duration for ``key`` in minutes, or None if disabled."""
        if not self.enabled:
            return None
        per_type: int | None = None
        if key.alert_type == "coil":
            per_type = self.coil_minutes
        elif key.alert_type == "confluence":
            per_type = self.confluence_minutes
        elif key.alert_type.startswith("pattern"):
            per_type = self.pattern_minutes
        elif key.alert_type.startswith("gap"):
            per_type = self.gap_minutes
        return self.default_minutes if per_type is None else per_type

    @property
    def resolved_state_path(self) -> Path:
        """Return the state path with ``~`` expanded."""
        return Path(os.path.expanduser(str(self.state_path)))


def _sanitize_channel_results(results: Any) -> dict[str, bool]:
    """Return a JSON-safe, deterministically ordered dict of channel results.

    Rejects non-bool values and non-mapping containers so a string like
    ``"false"`` or ``None`` cannot be interpreted as a successful delivery.
    """
    if not isinstance(results, Mapping):
        raise ValueError(f"channel results must be a mapping, got {type(results).__name__}")
    sanitized: dict[str, bool] = {}
    for k, v in sorted(results.items()):
        if not isinstance(k, str):
            raise ValueError(f"channel result key must be a string, got {type(k).__name__}")
        if not isinstance(v, bool):
            raise ValueError(f"channel result for {k!r} must be a bool, got {type(v).__name__}")
        sanitized[k] = v
    return sanitized


@dataclass(frozen=True)
class AlertDispatchResult:
    """Immutable result of an automatic alert dispatch attempt."""

    key: AlertKey
    decision: AlertDecision
    observed_at: datetime
    cooldown_minutes: int | None
    last_success_at: datetime | None
    next_eligible_at: datetime | None
    reason: str
    channel_results: Mapping[str, bool]
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "channel_results", _sanitize_channel_results(self.channel_results)
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict with ISO datetimes and deterministic channel ordering."""

        def _dt(value: datetime | None) -> str | None:
            if value is None:
                return None
            return value.astimezone(UTC).isoformat(timespec="microseconds")

        return {
            "key": {
                "ticker": self.key.ticker,
                "alert_type": self.key.alert_type,
                "timeframe": self.key.timeframe,
            },
            "decision": self.decision.value,
            "observed_at": _dt(self.observed_at),
            "cooldown_minutes": self.cooldown_minutes,
            "last_success_at": _dt(self.last_success_at),
            "next_eligible_at": _dt(self.next_eligible_at),
            "reason": self.reason,
            "channel_results": dict(self.channel_results),
            "error": self.error,
        }

    def to_json(self) -> str:
        """Strict JSON serialization (no NaN/Infinity)."""
        return json.dumps(self.to_dict(), allow_nan=False, sort_keys=True, ensure_ascii=True)


class AlertPolicyError(Exception):
    """Raised when alert state or configuration is invalid."""


def ensure_aware_utc(value: datetime | None) -> datetime:
    """Return an aware UTC datetime, rejecting naive values."""
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("naive datetime not allowed; use timezone-aware UTC")
    return value.astimezone(UTC)
