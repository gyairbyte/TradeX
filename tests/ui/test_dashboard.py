"""Tests for dashboard pure source-resolution helpers."""


from tradex.ui import source_defaults


def test_options_source_index_uses_env_var(monkeypatch):
    """The options source selector default honors OPTIONS_DATA_SOURCE."""
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "yahoo")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("yahoo")


def test_options_source_index_falls_back_for_invalid_env_var(monkeypatch):
    """A malformed OPTIONS_DATA_SOURCE falls back to the safe default."""
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "bloomberg")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("auto")


def test_earnings_source_index_uses_env_var(monkeypatch):
    monkeypatch.setenv("EARNINGS_DATA_SOURCE", "yahoo")
    assert source_defaults.earnings_source_index() == source_defaults.earnings_sources().index("yahoo")


def test_earnings_source_index_falls_back_for_invalid_env_var(monkeypatch):
    monkeypatch.setenv("EARNINGS_DATA_SOURCE", "schwab")
    assert source_defaults.earnings_source_index() == source_defaults.earnings_sources().index("yahoo")


def test_market_cap_source_index_uses_env_var(monkeypatch):
    monkeypatch.setenv("MARKET_CAP_DATA_SOURCE", "schwab")
    assert source_defaults.market_cap_source_index() == source_defaults.market_cap_sources().index("schwab")


def test_market_cap_source_index_falls_back_for_invalid_env_var(monkeypatch):
    monkeypatch.setenv("MARKET_CAP_DATA_SOURCE", "bloomberg")
    assert source_defaults.market_cap_source_index() == source_defaults.market_cap_sources().index("yahoo")


def test_default_source_index_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "TRADIER")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("tradier")
