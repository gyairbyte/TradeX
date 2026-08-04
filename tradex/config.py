"""Centralized, typed, immutable TradeX runtime configuration.

This module is the only place in the production code base that is allowed to
read the process environment or a ``.env`` file. Everywhere else accepts an
explicit :class:`TradeXSettings` instance or calls :func:`load_runtime_settings`
at function-call time for backward compatibility.

Importing this module does not read any environment state.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════
SUPPORTED_OHLCV_PROVIDERS = ("yahoo", "alpaca", "ibkr", "schwab")
SUPPORTED_OPTIONS_SOURCES = ("auto", "unusual_whales", "tradier", "yahoo")
SUPPORTED_CHAIN_SOURCES = ("auto", "tradier", "yahoo")
SUPPORTED_EARNINGS_SOURCES = ("yahoo",)
SUPPORTED_MARKET_CAP_SOURCES = ("yahoo", "schwab")


# ═══════════════════════════════════════════════════════════════════════════════
# Pure parsing helpers (no env / .env / I/O side effects)
# ═══════════════════════════════════════════════════════════════════════════════
def _strip_text(raw: Any) -> str:
    return str(raw).strip()


def _parse_bool(raw: Any | None, default: bool, name: str) -> bool:
    """Parse a strict boolean string. Reject booleans, numbers, empty strings."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be a string, got boolean")
    text = _strip_text(raw)
    if text == "":
        raise ValueError(f"{name} is set but empty")
    lowered = text.lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"{name} must be a boolean string, got {text!r}")


def _parse_int(
    raw: Any | None,
    default: int,
    name: str,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Parse an integer string, rejecting floats, booleans, and empty values."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be an integer string, got boolean")
    if isinstance(raw, int):
        value = raw
    else:
        text = _strip_text(raw)
        if text == "":
            raise ValueError(f"{name} is set but empty")
        if re.search(r"[eE.]", text.lstrip("+-")):
            raise ValueError(f"{name} must be an integer, got {text!r}")
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer, got {text!r}") from exc
        # Reject leading zeros, stray spaces, "+" used as a flag, etc.
        normalized = str(value)
        if text.startswith("+"):
            expected = f"+{normalized}"
        else:
            expected = normalized
        if text != expected:
            raise ValueError(f"{name} must be an integer, got {text!r}")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be at least {min_value}, got {value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be at most {max_value}, got {value}")
    return value


def _parse_port(raw: Any | None, default: int, name: str) -> int:
    return _parse_int(raw, default, name, min_value=1, max_value=65535)


def _parse_minutes(raw: Any | None, default: int, name: str) -> int:
    """Parse cooldown minutes: 1 minute to 1 week (10080 minutes)."""
    return _parse_int(raw, default, name, min_value=1, max_value=10080)


def _parse_float(
    raw: Any | None,
    default: float,
    name: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be a numeric string, got boolean")
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = _strip_text(raw)
        if text == "":
            raise ValueError(f"{name} is set but empty")
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be a number, got {text!r}") from exc
    import math

    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be at least {min_value}, got {value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be at most {max_value}, got {value}")
    return value


def _parse_provider(raw: Any | None, default: str, allowed: tuple[str, ...], name: str) -> str:
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be a string, got boolean")
    text = _strip_text(raw).lower()
    if text == "":
        raise ValueError(f"{name} is set but empty")
    if text not in allowed:
        raise ValueError(f"{name} must be one of {list(allowed)}, got {text!r}")
    return text


def _parse_path(raw: Any | None, default: Path, name: str) -> Path:
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be a path string, got boolean")
    if isinstance(raw, Path):
        return raw
    text = _strip_text(raw)
    if text == "":
        raise ValueError(f"{name} is set but empty")
    return Path(text)


def _parse_fallback_order(
    raw: Any | None, default: tuple[str, ...], allowed: tuple[str, ...], name: str
) -> tuple[str, ...]:
    """Parse a comma-separated or sequence fallback order, deduplicate, validate."""
    if raw is None:
        return default
    if isinstance(raw, str):
        if _strip_text(raw) == "":
            return default
        parts = [_strip_text(p) for p in raw.split(",") if _strip_text(p)]
    elif isinstance(raw, (list, tuple)):
        parts = [_strip_text(p) for p in raw if _strip_text(p)]
    else:
        raise ValueError(f"{name} must be a string or list, got {type(raw).__name__}")

    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        canonical = _parse_provider(p, "", allowed, name)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return tuple(result)


def _secret_field(default: Any = None) -> Any:
    """Dataclass field helper for secret values (excluded from repr)."""
    return field(default=default, repr=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Settings dataclasses
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class DataProviderSettings:
    data_provider: str = "yahoo"
    ohlcv_max_retries: int = 0
    ohlcv_fallback_order: tuple[str, ...] = ()
    alpaca_api_key: str | None = _secret_field(None)
    alpaca_secret_key: str | None = _secret_field(None)
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1
    schwab_app_key: str | None = _secret_field(None)
    schwab_app_secret: str | None = _secret_field(None)
    schwab_token_path: Path = field(default_factory=lambda: Path("~/.tradex_schwab_token.json"))
    schwab_smoke_symbol: str = "SPY"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_provider",
            _parse_provider(
                self.data_provider, "yahoo", SUPPORTED_OHLCV_PROVIDERS, "DATA_PROVIDER"
            ),
        )
        object.__setattr__(
            self,
            "ohlcv_max_retries",
            _parse_int(self.ohlcv_max_retries, 0, "OHLCV_MAX_RETRIES", min_value=0, max_value=3),
        )
        object.__setattr__(
            self,
            "ohlcv_fallback_order",
            _parse_fallback_order(
                self.ohlcv_fallback_order,
                (),
                SUPPORTED_OHLCV_PROVIDERS,
                "OHLCV_FALLBACK_ORDER",
            ),
        )
        object.__setattr__(self, "ibkr_port", _parse_port(self.ibkr_port, 7497, "IBKR_PORT"))
        object.__setattr__(
            self,
            "ibkr_client_id",
            _parse_int(self.ibkr_client_id, 1, "IBKR_CLIENT_ID", min_value=0),
        )
        object.__setattr__(self, "schwab_token_path", _parse_path(self.schwab_token_path, Path("~/.tradex_schwab_token.json"), "SCHWAB_TOKEN_PATH"))
        object.__setattr__(self, "schwab_smoke_symbol", _strip_text(self.schwab_smoke_symbol) or "SPY")


@dataclass(frozen=True)
class OptionsSettings:
    options_data_source: str = "auto"
    unusual_whales_api_key: str | None = _secret_field(None)
    tradier_api_key: str | None = _secret_field(None)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "options_data_source",
            _parse_provider(
                self.options_data_source,
                "auto",
                SUPPORTED_OPTIONS_SOURCES,
                "OPTIONS_DATA_SOURCE",
            ),
        )


@dataclass(frozen=True)
class AlertChannelSettings:
    discord_token: str | None = _secret_field(None)
    discord_channel_id: str | None = _secret_field(None)
    email_to: str | None = _secret_field(None)
    email_from: str | None = _secret_field(None)
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: str | None = _secret_field(None)
    email_pass: str | None = _secret_field(None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "email_port", _parse_port(self.email_port, 587, "ALERT_EMAIL_PORT"))


@dataclass(frozen=True)
class AlertThresholdSettings:
    coil: int = 60
    pattern: float = 75.0
    confluence: int = 70

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "coil", _parse_int(self.coil, 60, "ALERT_COIL_THRESHOLD", min_value=0, max_value=100)
        )
        object.__setattr__(
            self,
            "pattern",
            _parse_float(self.pattern, 75.0, "ALERT_PATTERN_THRESHOLD", min_value=0.0, max_value=100.0),
        )
        object.__setattr__(
            self,
            "confluence",
            _parse_int(self.confluence, 70, "ALERT_CONFLUENCE_THRESHOLD", min_value=0, max_value=100),
        )


@dataclass(frozen=True)
class PathSettings:
    signals_db: Path = field(default_factory=lambda: Path("~/.tradex/signals.db"))
    fingerprint_db: Path = field(default_factory=lambda: Path("~/.tradex/fingerprints.db"))
    watchlists_db: Path = field(default_factory=lambda: Path("~/.tradex/watchlists.db"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals_db", _parse_path(self.signals_db, Path("~/.tradex/signals.db"), "TRADEX_DB_PATH"))
        object.__setattr__(self, "fingerprint_db", _parse_path(self.fingerprint_db, Path("~/.tradex/fingerprints.db"), "TRADEX_FP_DB"))
        object.__setattr__(self, "watchlists_db", _parse_path(self.watchlists_db, Path("~/.tradex/watchlists.db"), "TRADEX_WATCHLISTS_DB_PATH"))


def _default_cooldown():
    from tradex.alerts.models import AlertCooldownConfig
    return AlertCooldownConfig.from_mapping({})


@dataclass(frozen=True)
class TradeXSettings:
    data: DataProviderSettings = field(default_factory=DataProviderSettings)
    options: OptionsSettings = field(default_factory=OptionsSettings)
    alert_channels: AlertChannelSettings = field(default_factory=AlertChannelSettings)
    alert_thresholds: AlertThresholdSettings = field(default_factory=AlertThresholdSettings)
    alert_cooldown: AlertCooldownConfig = field(default_factory=_default_cooldown)
    paths: PathSettings = field(default_factory=PathSettings)
    earnings_data_source: str = "yahoo"
    market_cap_data_source: str = "yahoo"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "earnings_data_source",
            _parse_provider(
                self.earnings_data_source, "yahoo", SUPPORTED_EARNINGS_SOURCES, "EARNINGS_DATA_SOURCE"
            ),
        )
        object.__setattr__(
            self,
            "market_cap_data_source",
            _parse_provider(
                self.market_cap_data_source,
                "yahoo",
                SUPPORTED_MARKET_CAP_SOURCES,
                "MARKET_CAP_DATA_SOURCE",
            ),
        )

    def safe_summary(self) -> dict[str, Any]:
        """Return a credential-free summary suitable for logging or tests."""
        return {
            "data_provider": self.data.data_provider,
            "ohlcv_max_retries": self.data.ohlcv_max_retries,
            "ohlcv_fallback_order": list(self.data.ohlcv_fallback_order),
            "options_data_source": self.options.options_data_source,
            "alert_cooldown_enabled": self.alert_cooldown.enabled,
            "alert_cooldown_default_minutes": self.alert_cooldown.default_minutes,
            "alert_thresholds": {
                "coil": self.alert_thresholds.coil,
                "pattern": self.alert_thresholds.pattern,
                "confluence": self.alert_thresholds.confluence,
            },
            "email_configured": bool(
                self.alert_channels.email_to and self.alert_channels.email_host
            ),
            "discord_configured": bool(
                self.alert_channels.discord_token and self.alert_channels.discord_channel_id
            ),
            "signals_db": str(self.paths.signals_db),
            "fingerprint_db": str(self.paths.fingerprint_db),
            "watchlists_db": str(self.paths.watchlists_db),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Construction from a mapping
# ═══════════════════════════════════════════════════════════════════════════════
def settings_from_mapping(values: Mapping[str, str]) -> TradeXSettings:
    """Build a :class:`TradeXSettings` from a plain ``{key: value}`` mapping.

    This function is pure: it does not read ``os.environ`` or any ``.env`` file.
    Missing keys use the documented defaults. Invalid values raise ``ValueError``
    with the offending variable name (but never its value for secret fields).
    """
    v: dict[str, Any] = dict(values)

    data = DataProviderSettings(
        data_provider=v.get("DATA_PROVIDER", "yahoo"),
        ohlcv_max_retries=v.get("OHLCV_MAX_RETRIES", "0"),
        ohlcv_fallback_order=v.get("OHLCV_FALLBACK_ORDER", ""),
        alpaca_api_key=v.get("ALPACA_API_KEY") or None,
        alpaca_secret_key=v.get("ALPACA_SECRET_KEY") or None,
        ibkr_host=v.get("IBKR_HOST", "127.0.0.1"),
        ibkr_port=v.get("IBKR_PORT", "7497"),
        ibkr_client_id=v.get("IBKR_CLIENT_ID", "1"),
        schwab_app_key=v.get("SCHWAB_APP_KEY") or None,
        schwab_app_secret=v.get("SCHWAB_APP_SECRET") or None,
        schwab_token_path=v.get("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json"),
        schwab_smoke_symbol=v.get("SCHWAB_SMOKE_SYMBOL", "SPY"),
    )

    options = OptionsSettings(
        options_data_source=v.get("OPTIONS_DATA_SOURCE", "auto"),
        unusual_whales_api_key=v.get("UNUSUAL_WHALES_API_KEY") or None,
        tradier_api_key=v.get("TRADIER_API_KEY") or None,
    )

    alert_channels = AlertChannelSettings(
        discord_token=v.get("ALERT_DISCORD_TOKEN") or None,
        discord_channel_id=v.get("ALERT_DISCORD_CHANNEL_ID") or None,
        email_to=v.get("ALERT_EMAIL_TO") or None,
        email_from=v.get("ALERT_EMAIL_FROM") or None,
        email_host=v.get("ALERT_EMAIL_HOST", "smtp.gmail.com"),
        email_port=v.get("ALERT_EMAIL_PORT", "587"),
        email_user=v.get("ALERT_EMAIL_USER") or None,
        email_pass=v.get("ALERT_EMAIL_PASS") or None,
    )

    alert_thresholds = AlertThresholdSettings(
        coil=v.get("ALERT_COIL_THRESHOLD", "60"),
        pattern=v.get("ALERT_PATTERN_THRESHOLD", "75"),
        confluence=v.get("ALERT_CONFLUENCE_THRESHOLD", "70"),
    )

    from tradex.alerts.models import AlertCooldownConfig
    cooldown = AlertCooldownConfig.from_mapping(v)

    paths = PathSettings(
        signals_db=v.get("TRADEX_DB_PATH", "~/.tradex/signals.db"),
        fingerprint_db=v.get("TRADEX_FP_DB", "~/.tradex/fingerprints.db"),
        watchlists_db=v.get("TRADEX_WATCHLISTS_DB_PATH", "~/.tradex/watchlists.db"),
    )

    return TradeXSettings(
        data=data,
        options=options,
        alert_channels=alert_channels,
        alert_thresholds=alert_thresholds,
        alert_cooldown=cooldown,
        paths=paths,
        earnings_data_source=v.get("EARNINGS_DATA_SOURCE", "yahoo"),
        market_cap_data_source=v.get("MARKET_CAP_DATA_SOURCE", "yahoo"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Runtime loader
# ═══════════════════════════════════════════════════════════════════════════════
def load_runtime_settings(*, dotenv_path: str | Path | None = None) -> TradeXSettings:
    """Load runtime settings from ``.env`` (optional) and the process environment.

    Process environment variables override ``.env`` values, matching the legacy
    precedence of previous ``load_dotenv()`` + ``os.getenv`` callers. Missing
    ``.env`` files are valid and produce defaults. This function does not mutate
    ``os.environ``.

    Secrets are never printed or logged by this function.
    """
    from dotenv import dotenv_values, find_dotenv

    if dotenv_path is None:
        dotenv_path = find_dotenv()
    # ``dotenv_values('')`` returns an empty mapping; missing files are safe.
    raw_env: dict[str, str | None] = dotenv_values(dotenv_path)  # type: ignore[assignment]
    # Discard unset entries (``None`` values) and let ``os.environ`` provide overrides.
    env_values = {k: v for k, v in raw_env.items() if v is not None}
    merged = {**env_values, **os.environ}
    return settings_from_mapping(merged)
