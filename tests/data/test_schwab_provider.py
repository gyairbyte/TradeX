"""Credential-free provider-contract tests for the Schwab data source.

These tests mock the Schwab authentication layer and HTTP responses. They never
contact Schwab servers and do not use real credentials.
"""
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.data import fetcher

pytest.importorskip("schwab")


def _make_candle(
    dt: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> dict:
    """Return a Schwab-style candle dict with an epoch-ms timestamp."""
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "datetime": int(dt.timestamp() * 1000),
    }


_SCHWAB_METHOD = {
    "intraday": "get_price_history_every_five_minutes",
    "short": "get_price_history_every_day",
    "long": "get_price_history_every_week",
}


def _mock_client(timeframe: str, candles: list[dict], **resp_overrides) -> MagicMock:
    """Return a mock Schwab client whose price-history method returns the candles."""
    method_name = _SCHWAB_METHOD[timeframe]
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"candles": candles}
    for attr, value in resp_overrides.items():
        setattr(resp, attr, value)
    getattr(client, method_name).return_value = resp
    return client


@pytest.fixture(autouse=True)
def reset_schwab_client(monkeypatch):
    """Reset the global Schwab client cache before every test."""
    monkeypatch.setattr(fetcher, "_SCHWAB_CLIENT", None)


@pytest.fixture
def tmp_token(tmp_path):
    p = tmp_path / "token.json"
    p.write_text("{}")
    return p


@pytest.fixture
def env_vars(monkeypatch, tmp_token):
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))


def _fetch(candles, timeframe, tmp_token, monkeypatch, **resp_overrides):
    """Call fetch() with a fully mocked Schwab client."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))
    client = _mock_client(timeframe, candles, **resp_overrides)
    with patch("schwab.auth.client_from_token_file", return_value=client):
        return fetcher.fetch("SPY", timeframe, provider="schwab")


def _assert_contract(df: pd.DataFrame) -> None:
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    if not df.empty:
        assert df.index.name == "datetime"
        assert df.index.tz is not None
        assert df.index.is_monotonic_increasing
        assert df.index.is_unique
        for col in ("open", "high", "low", "close", "volume"):
            assert pd.api.types.is_numeric_dtype(df[col])


@pytest.mark.parametrize("timeframe", ["intraday", "short", "long"])
def test_schwab_returns_canonical_ohlcv(timeframe, tmp_token, monkeypatch):
    """Five-minute, daily, and weekly candles normalize to the same schema."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, 14, 35, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        _make_candle(t2, 100.5, 102.0, 100.0, 101.5, 2000),
    ]

    df = _fetch(candles, timeframe, tmp_token, monkeypatch)
    _assert_contract(df)
    assert len(df) == 2
    assert df.index[0] == pd.Timestamp(t1)
    assert df.index[1] == pd.Timestamp(t2)
    assert df["close"].iloc[-1] == 101.5


def test_schwab_empty_candles_returns_stable_schema(tmp_token, monkeypatch):
    """An empty candles array must produce an empty DataFrame with the right columns."""
    df = _fetch([], "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert df.empty


def test_schwab_missing_candles_key(tmp_token, monkeypatch):
    """A response without a candles key is treated as empty."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))
    client = _mock_client("short", [])
    client.get_price_history_every_day.return_value.json.return_value = {}
    with patch("schwab.auth.client_from_token_file", return_value=client):
        df = fetcher.fetch("SPY", "short", provider="schwab")
    _assert_contract(df)
    assert df.empty


def test_schwab_http_error_raises_runtimeerror(tmp_token, monkeypatch):
    """Non-2xx responses are surfaced as safe, non-secret-bearing errors."""
    resp = MagicMock()
    resp.status_code = 401
    resp.raise_for_status.side_effect = RuntimeError("HTTP 401")
    client = MagicMock()
    client.get_price_history_every_day.return_value = resp

    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    with (
        patch("schwab.auth.client_from_token_file", return_value=client),
        pytest.raises(RuntimeError, match="Schwab price-history request failed"),
    ):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_malformed_json_raises_valueerror(tmp_token, monkeypatch):
    """A non-JSON response is surfaced as a clear ValueError."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)
    client = MagicMock()
    client.get_price_history_every_day.return_value = resp

    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    with (
        patch("schwab.auth.client_from_token_file", return_value=client),
        pytest.raises(ValueError, match="non-JSON"),
    ):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_missing_ohlc_field_drops_row(tmp_token, monkeypatch):
    """A candle missing a required OHLCV field is dropped, keeping the rest."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, 14, 35, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        {"open": 100.5, "high": 102.0, "low": 100.0, "volume": 2000, "datetime": int(t2.timestamp() * 1000)},
    ]
    df = _fetch(candles, "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert len(df) == 1
    assert df.index[0] == pd.Timestamp(t1)


def test_schwab_invalid_timestamp_drops_row(tmp_token, monkeypatch):
    """An unparseable datetime value is dropped without crashing."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        {"open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2000, "datetime": "not-a-timestamp"},
    ]
    df = _fetch(candles, "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert len(df) == 1
    assert df.index[0] == pd.Timestamp(t1)


def test_schwab_duplicate_timestamps_keep_last(tmp_token, monkeypatch):
    """Duplicate timestamps are de-duplicated, keeping the last value."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        _make_candle(t1, 100.5, 102.0, 100.0, 101.5, 2000),
    ]
    df = _fetch(candles, "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert len(df) == 1
    assert df["close"].iloc[0] == 101.5


def test_schwab_out_of_order_candles_sorted(tmp_token, monkeypatch):
    """Candles arriving out of chronological order are sorted."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, 14, 35, tzinfo=UTC)
    candles = [
        _make_candle(t2, 100.5, 102.0, 100.0, 101.5, 2000),
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
    ]
    df = _fetch(candles, "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert df.index[0] == pd.Timestamp(t1)
    assert df.index[1] == pd.Timestamp(t2)


def test_schwab_nan_ohlcv_drops_row(tmp_token, monkeypatch):
    """Candles with null/None OHLCV values are dropped."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, 14, 35, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        {"open": None, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2000, "datetime": int(t2.timestamp() * 1000)},
    ]
    df = _fetch(candles, "short", tmp_token, monkeypatch)
    _assert_contract(df)
    assert len(df) == 1


def test_schwab_missing_app_key(tmp_token, monkeypatch):
    """Missing SCHWAB_APP_KEY raises an EnvironmentError before any network call."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))
    with pytest.raises(EnvironmentError, match="SCHWAB_APP_KEY"):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_missing_app_secret(tmp_token, monkeypatch):
    """Missing SCHWAB_APP_SECRET raises an EnvironmentError before any network call."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))
    with pytest.raises(EnvironmentError, match="SCHWAB_APP_SECRET"):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_missing_token_file(tmp_token, monkeypatch):
    """A missing token file raises FileNotFoundError before any network call."""
    missing_path = tmp_token.parent / "missing_token.json"
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(missing_path))
    with pytest.raises(FileNotFoundError, match="Schwab OAuth token not found"):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_token_path_inside_repo_rejected(tmp_token, monkeypatch):
    """A token path inside the repository is rejected before authentication."""
    repo_root = fetcher._repo_root()
    if repo_root is None:
        pytest.skip("Cannot determine repository root")
    inside_path = repo_root / "schwab_token.json"
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(inside_path))
    with pytest.raises(ValueError, match="must not be inside the repository"):
        fetcher.fetch("SPY", "short", provider="schwab")


def test_schwab_unsupported_timeframe(tmp_token, monkeypatch):
    """A timeframe not supported by Schwab raises ValueError."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))
    with (
        patch("schwab.auth.client_from_token_file", return_value=MagicMock()),
        pytest.raises(ValueError, match="Unsupported timeframe for schwab"),
    ):
        # bypass the public fetch() timeframe validation
        fetcher._fetch_schwab("SPY", "unsupported")


def test_schwab_auth_failure_does_not_leak_secrets(tmp_token, monkeypatch, capsys):
    """An authentication error containing secret text is not printed, raised, or chained."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    sentinel = "SENTINEL_REFRESH_SECRET_TOKEN_67890"

    def fake_client(*args, **kwargs):
        raise RuntimeError(f"invalid refresh token: {sentinel}")

    with patch(
        "schwab.auth.client_from_token_file", side_effect=fake_client
    ), pytest.raises(RuntimeError) as exc_info:
        fetcher.fetch("SPY", "short", provider="schwab")

    assert exc_info.value.__cause__ is None
    assert sentinel not in str(exc_info.value)
    tb_text = "".join(traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb))
    assert sentinel not in tb_text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_schwab_http_failure_does_not_leak_secrets(tmp_token, monkeypatch, capsys):
    """An HTTP error containing secret text is not exposed in the safe message or chain."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    sentinel = "SENTINEL_HTTP_ERROR_SECRET_67890"

    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 403
    resp.raise_for_status.side_effect = RuntimeError(
        f"Forbidden: access token contains {sentinel}"
    )
    client.get_price_history_every_day.return_value = resp

    with patch(
        "schwab.auth.client_from_token_file", return_value=client
    ), pytest.raises(RuntimeError) as exc_info:
        fetcher.fetch("SPY", "short", provider="schwab")

    assert "HTTP 403" in str(exc_info.value)
    assert sentinel not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    tb_text = "".join(traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb))
    assert sentinel not in tb_text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_schwab_client_cached(tmp_token, monkeypatch):
    """The authenticated client is created once and reused across calls."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    candles = [_make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000)]

    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    client = _mock_client("short", candles)
    with patch("schwab.auth.client_from_token_file", return_value=client) as mock_auth:
        fetcher.fetch("SPY", "short", provider="schwab")
        fetcher.fetch("QQQ", "short", provider="schwab")

    mock_auth.assert_called_once()


def test_schwab_fetch_multi_uses_cached_client(tmp_token, monkeypatch):
    """fetch_multi reuses one authenticated client for all tickers."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    candles = [_make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000)]

    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    client = _mock_client("short", candles)
    with patch("schwab.auth.client_from_token_file", return_value=client) as mock_auth:
        results = fetcher.fetch_multi(["SPY", "QQQ"], "short", provider="schwab")

    mock_auth.assert_called_once()
    assert set(results.keys()) == {"SPY", "QQQ"}
    for df in results.values():
        _assert_contract(df)


def test_schwab_concurrent_fetch_uses_one_client(tmp_token, monkeypatch):
    """Concurrent fetch calls create one client and normalize safely."""
    t1 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    t2 = datetime(2024, 1, 2, 14, 35, tzinfo=UTC)
    candles = [
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        _make_candle(t2, 100.5, 102.0, 100.0, 101.5, 2000),
    ]

    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(tmp_token))

    client = _mock_client("short", candles)
    with (
        patch("schwab.auth.client_from_token_file", return_value=client) as mock_auth,
        ThreadPoolExecutor(max_workers=4) as executor,
    ):
        futures = [
            executor.submit(fetcher.fetch, sym, "short", "schwab")
            for sym in ["SPY", "QQQ", "IWM"]
        ]
        results = [futures[i].result() for i in range(len(futures))]

    mock_auth.assert_called_once()
    assert len(results) == 3
    for df in results:
        pd.testing.assert_frame_equal(df, results[0])
        _assert_contract(df)
    assert len(results[0]) == 2
