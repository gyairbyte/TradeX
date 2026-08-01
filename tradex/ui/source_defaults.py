"""Pure helpers for resolving default source selector indices in the dashboard.

These are split out so they can be tested without importing the full Streamlit
application module.
"""
from __future__ import annotations

import os


def _default_source_index(sources: list[str], env_var: str, default: str) -> int:
    """Return the selector index for ``env_var`` (falling back to ``default``).

    If the environment value is not one of the supported ``sources``, the
    ``default`` is used. This keeps malformed env vars from breaking the UI.
    """
    raw = os.getenv(env_var, default).lower().strip()
    if raw in sources:
        return sources.index(raw)
    return sources.index(default)


_OPTIONS_SOURCES = ["auto", "unusual_whales", "tradier", "yahoo"]
_EARNINGS_SOURCES = ["yahoo"]
_MARKET_CAP_SOURCES = ["yahoo", "schwab"]


def options_source_index() -> int:
    return _default_source_index(_OPTIONS_SOURCES, "OPTIONS_DATA_SOURCE", "auto")


def earnings_source_index() -> int:
    return _default_source_index(_EARNINGS_SOURCES, "EARNINGS_DATA_SOURCE", "yahoo")


def market_cap_source_index() -> int:
    return _default_source_index(_MARKET_CAP_SOURCES, "MARKET_CAP_DATA_SOURCE", "yahoo")


def options_sources() -> list[str]:
    return _OPTIONS_SOURCES


def earnings_sources() -> list[str]:
    return _EARNINGS_SOURCES


def market_cap_sources() -> list[str]:
    return _MARKET_CAP_SOURCES
