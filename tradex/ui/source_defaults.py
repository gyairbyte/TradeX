"""Pure helpers for resolving default source selector indices in the dashboard.

These are split out so they can be tested without importing the full Streamlit
application module.
"""
from __future__ import annotations

from tradex.config import TradeXSettings, load_runtime_settings


def _default_source_index(
    sources: list[str],
    configured: str,
    default: str,
) -> int:
    """Return the selector index for a configured source (falling back to ``default``).

    If the configured value is not one of the supported ``sources``, the
    ``default`` is used. This keeps malformed configuration from breaking the UI.
    """
    raw = configured.lower().strip()
    if raw in sources:
        return sources.index(raw)
    return sources.index(default)


_OPTIONS_SOURCES = ["auto", "unusual_whales", "tradier", "yahoo"]
_EARNINGS_SOURCES = ["yahoo"]
_MARKET_CAP_SOURCES = ["yahoo", "schwab"]


def options_source_index(settings: TradeXSettings | None = None) -> int:
    if settings is None:
        try:
            settings = load_runtime_settings()
        except ValueError:
            return _OPTIONS_SOURCES.index("auto")
    return _default_source_index(
        _OPTIONS_SOURCES, settings.options.options_data_source, "auto"
    )


def earnings_source_index(settings: TradeXSettings | None = None) -> int:
    if settings is None:
        try:
            settings = load_runtime_settings()
        except ValueError:
            return _EARNINGS_SOURCES.index("yahoo")
    return _default_source_index(_EARNINGS_SOURCES, settings.earnings_data_source, "yahoo")


def market_cap_source_index(settings: TradeXSettings | None = None) -> int:
    if settings is None:
        try:
            settings = load_runtime_settings()
        except ValueError:
            return _MARKET_CAP_SOURCES.index("yahoo")
    return _default_source_index(
        _MARKET_CAP_SOURCES, settings.market_cap_data_source, "yahoo"
    )


def options_sources() -> list[str]:
    return _OPTIONS_SOURCES


def earnings_sources() -> list[str]:
    return _EARNINGS_SOURCES


def market_cap_sources() -> list[str]:
    return _MARKET_CAP_SOURCES
