"""Tests for options source capabilities, true-flow scanning, chain activity, and put/call balance."""

# ruff: noqa: SIM117

import json
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from tradex.data.fetcher import (
    ProviderCapabilityError,
    ProviderResponseError,
    ProviderTransientError,
)
from tradex.options import flow
from tradex.options.models import (
    OptionsDataKind,
    OptionsScanStatus,
    OptionsSourceStatus,
)


@pytest.fixture(autouse=True)
def _no_options_credentials(monkeypatch):
    """Ensure tests never accidentally use real credentials."""
    monkeypatch.setattr(flow, "UNUSUAL_WHALES_KEY", "")
    monkeypatch.setattr(flow, "TRADIER_KEY", "")
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "auto")


@pytest.fixture
def _uw_configured(monkeypatch):
    monkeypatch.setattr(flow, "UNUSUAL_WHALES_KEY", "uw-test-key")


@pytest.fixture
def _tradier_configured(monkeypatch):
    monkeypatch.setattr(flow, "TRADIER_KEY", "tradier-test-key")


@pytest.fixture
def _uw_record():
    return {
        "put_call": "CALL",
        "side": "ASK",
        "strike_price": 150.0,
        "expiry_date": "2024-02-16",
        "premium": 50000.0,
        "volume": 3000,
        "open_interest": 1000,
        "is_sweep": True,
        "sentiment": "bullish",
        "created_at": "2024-02-15T10:00:00Z",
    }


@pytest.fixture
def _tradier_chain_row():
    return {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 3000,
        "open_interest": 1000,
        "last": 5.0,
        "bid": 4.9,
        "ask": 5.1,
    }


@pytest.fixture
def _yahoo_chain():
    calls = pd.DataFrame({
        "strike": [150.0],
        "volume": [3000.0],
        "openInterest": [1000.0],
        "lastPrice": [5.0],
        "bid": [4.9],
        "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0],
        "volume": [500.0],
        "openInterest": [50.0],
        "lastPrice": [4.0],
        "bid": [3.9],
        "ask": [4.1],
    })
    return calls, puts


# ── model tests ───────────────────────────────────────────────────────────────
def test_data_kind_values():
    assert OptionsDataKind.TRUE_FLOW.value == "true_flow"
    assert OptionsDataKind.CHAIN_SNAPSHOT.value == "chain_snapshot"


def test_source_status_is_immutable():
    status = OptionsSourceStatus(
        requested_source="auto",
        actual_source="yahoo",
        configured=True,
        available=True,
        data_kind=OptionsDataKind.CHAIN_SNAPSHOT,
        freshness="delayed",
        delayed=True,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=True,
        supports_open_interest=True,
        limitations=("delayed",),
        error=None,
    )
    with pytest.raises(FrozenInstanceError):
        status.available = False


def test_source_status_serialization_is_json_safe():
    status = flow.resolve_chain_source("yahoo")
    d = status.to_dict()
    assert d["requested_source"] == "yahoo"
    assert d["data_kind"] == "chain_snapshot"
    assert d["delayed"] is True
    assert isinstance(d["limitations"], list)
    assert all(isinstance(item, str) for item in d["limitations"])


def test_scan_report_to_dict_is_json_safe():
    report = flow.scan_unusual_flow_with_report(["AAPL"], source="yahoo")
    d = report.to_dict()
    assert d["status"] == "not_flow_capable"
    assert d["results"] == []
    assert isinstance(d["source_status"], dict)


def test_capabilities_per_source():
    uw = flow.resolve_flow_source("unusual_whales")
    assert uw.configured is False
    assert uw.available is False
    assert uw.data_kind == OptionsDataKind.TRUE_FLOW
    assert "UNUSUAL_WHALES_API_KEY" in uw.error

    with _uw_configured_via_patch():
        uw = flow.resolve_flow_source("unusual_whales")
    assert uw.data_kind == OptionsDataKind.TRUE_FLOW
    assert uw.supports_sweeps is True
    assert uw.supports_chain_volume is False

    tr = flow.resolve_chain_source("tradier")
    assert tr.data_kind == OptionsDataKind.CHAIN_SNAPSHOT
    assert tr.supports_chain_volume is True
    assert tr.supports_sweeps is False

    yh = flow.resolve_chain_source("yahoo")
    assert yh.data_kind == OptionsDataKind.CHAIN_SNAPSHOT
    assert yh.delayed is True
    assert yh.freshness == "delayed"


def test_limitations_are_stable_and_ordered():
    status = flow.resolve_chain_source("yahoo")
    assert status.limitations == tuple(status.limitations)
    assert "delayed" in status.limitations[0].lower()


def test_no_credentials_in_metadata():
    with _uw_configured_via_patch():
        status = flow.resolve_flow_source("unusual_whales")
    for attr in ("to_dict",):
        d = status.to_dict()
        for value in d.values():
            if isinstance(value, str):
                assert "uw-test-key" not in value


# ── source resolution tests ───────────────────────────────────────────────────
def test_resolve_options_source_name_rejects_unknown():
    with pytest.raises(ProviderCapabilityError):
        flow._resolve_options_source_name("bloomberg")


def test_resolve_options_source_name_defaults_from_env(monkeypatch):
    monkeypatch.setattr(flow, "OPTIONS_DATA_SOURCE", "yahoo")
    assert flow._resolve_options_source_name(None) == "yahoo"


def test_resolve_flow_source_auto_with_unconfigured_whales():
    status = flow.resolve_flow_source("auto")
    assert status.requested_source == "auto"
    assert status.actual_source is None
    assert status.available is False
    assert status.data_kind is None
    assert "no true-flow source" in status.error.lower()


def test_resolve_flow_source_auto_does_not_call_tradier_or_yahoo():
    with _tradier_configured_via_patch():
        status = flow.resolve_flow_source("auto")
    assert status.actual_source is None
    assert status.available is False
    assert "no true-flow source" in status.error.lower()


def test_resolve_flow_source_explicit_tradier_rejected():
    status = flow.resolve_flow_source("tradier")
    assert status.available is False
    assert status.data_kind is None
    assert "chain snapshot" in status.error.lower()


def test_resolve_flow_source_explicit_yahoo_rejected():
    status = flow.resolve_flow_source("yahoo")
    assert status.available is False
    assert status.data_kind is None
    assert "delayed" in status.error.lower()


def test_resolve_chain_source_auto_prefers_tradier(_tradier_configured):
    status = flow.resolve_chain_source("auto")
    assert status.requested_source == "auto"
    assert status.actual_source == "tradier"
    assert status.data_kind == OptionsDataKind.CHAIN_SNAPSHOT


def test_resolve_chain_source_auto_uses_yahoo_without_tradier():
    status = flow.resolve_chain_source("auto")
    assert status.actual_source == "yahoo"


def test_resolve_chain_source_explicit_yahoo():
    status = flow.resolve_chain_source("yahoo")
    assert status.actual_source == "yahoo"
    assert status.delayed is True


def test_resolve_chain_source_unconfigured_tradier_is_unavailable():
    status = flow.resolve_chain_source("tradier")
    assert status.available is False
    assert "TRADIER_API_KEY" in status.error


def test_resolve_chain_source_unusual_whales_rejected():
    status = flow.resolve_chain_source("unusual_whales")
    assert status.available is False
    assert "true-flow" in status.error.lower()
    assert "UNUSUAL_WHALES_API_KEY" in status.error


def test_resolve_chain_source_unusual_whales_configured_still_rejected():
    with _uw_configured_via_patch():
        status = flow.resolve_chain_source("unusual_whales")
    assert status.available is False
    assert "true-flow source" in status.error.lower()


def test_data_provider_does_not_affect_options_resolution(monkeypatch):
    monkeypatch.setenv("DATA_PROVIDER", "schwab")
    assert flow.resolve_chain_source("yahoo").actual_source == "yahoo"


# ── true-flow scan tests ─────────────────────────────────────────────────────
def test_scan_unusual_flow_with_report_rejects_yahoo_source():
    report = flow.scan_unusual_flow_with_report(["AAPL"], source="yahoo")
    assert report.status == OptionsScanStatus.NOT_FLOW_CAPABLE
    assert report.results.empty
    assert report.total_requested == 1
    assert report.total_fetched == 0


def test_scan_unusual_flow_with_report_unavailable_auto():
    report = flow.scan_unusual_flow_with_report(["AAPL"], source="auto")
    assert report.status == OptionsScanStatus.SOURCE_UNAVAILABLE


def test_scan_unusual_flow_wrapper_raises_for_non_flow_source():
    with pytest.raises(ProviderCapabilityError, match="not transaction-level flow"):
        flow.scan_unusual_flow(["AAPL"], source="yahoo")


def test_scan_unusual_flow_with_report_successful_mocked_uw(_uw_record):
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", return_value=[_uw_record]):
            report = flow.scan_unusual_flow_with_report(["AAPL"], min_vol_oi=3.0)

    assert report.status == OptionsScanStatus.COMPLETED
    assert report.total_matches == 1
    assert len(report.results) == 1
    row = report.results.iloc[0]
    assert row["data_kind"] == "true_flow"
    assert row["actual_source"] == "unusual_whales"
    assert bool(row["is_sweep"]) is True
    assert row["provider_sentiment"] == "bullish"
    assert row["side"] == "ASK"
    assert row["vol_oi_ratio"] == 3.0


def test_scan_unusual_flow_with_report_provider_sweep_unavailable_becomes_none(_uw_record):
    record = dict(_uw_record)
    record.pop("is_sweep")
    record.pop("sentiment")
    record.pop("side")
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", return_value=[record]):
            report = flow.scan_unusual_flow_with_report(["AAPL"], min_vol_oi=3.0)
    row = report.results.iloc[0]
    assert row["is_sweep"] is None
    assert row["provider_sentiment"] is None
    assert row["side"] is None


def test_scan_unusual_flow_with_report_valid_zero_events():
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", return_value=[]):
            report = flow.scan_unusual_flow_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.status == OptionsScanStatus.NO_MATCHES
    assert report.total_fetched == 0
    assert report.total_matches == 0


def test_scan_unusual_flow_with_report_partial_failure(_uw_record):
    with _uw_configured_via_patch():
        def _fetch(ticker):
            if ticker == "AAPL":
                return [_uw_record]
            raise ProviderTransientError("network timeout")

        with patch.object(flow, "_fetch_unusual_whales_flow", side_effect=_fetch):
            report = flow.scan_unusual_flow_with_report(["AAPL", "MSFT"], min_vol_oi=3.0)

    assert report.status == OptionsScanStatus.PARTIAL_FAILURE
    assert report.total_matches == 1
    assert "MSFT" in report.failures
    assert "network timeout" in report.failures["MSFT"]
    assert "ProviderTransientError" in report.failures["MSFT"]


def test_scan_unusual_flow_with_report_complete_failure():
    with _uw_configured_via_patch(), patch.object(
        flow, "_fetch_unusual_whales_flow", side_effect=ProviderResponseError("HTTP 500")
    ):
        report = flow.scan_unusual_flow_with_report(["AAPL", "MSFT"], min_vol_oi=3.0)
    assert report.status == OptionsScanStatus.COMPLETE_FAILURE
    assert report.total_matches == 0
    assert set(report.failures.keys()) == {"AAPL", "MSFT"}


def test_scan_unusual_flow_wrapper_returns_results_for_success(_uw_record):
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", return_value=[_uw_record]):
            df = flow.scan_unusual_flow(["AAPL"], min_vol_oi=3.0)
    assert len(df) == 1
    assert df.iloc[0]["data_kind"] == "true_flow"


def test_true_flow_sorting_is_deterministic(_uw_record):
    rec1 = dict(_uw_record)
    rec2 = dict(_uw_record)
    rec2["put_call"] = "PUT"
    rec2["volume"] = 2000
    rec2["open_interest"] = 500  # 4.0 ratio, lower than 3.0? Wait 2000/500=4.0
    # Actually rec1 ratio = 3000/1000 = 3.0; rec2 ratio = 2000/500 = 4.0
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", return_value=[rec1, rec2]):
            report = flow.scan_unusual_flow_with_report(["AAPL"], min_vol_oi=3.0)
    ratios = report.results["vol_oi_ratio"].tolist()
    assert ratios[0] >= ratios[1]


# ── chain scan tests ─────────────────────────────────────────────────────────
def test_scan_chain_activity_with_report_mocked_yahoo(_yahoo_chain):
    calls, puts = _yahoo_chain
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0, source="yahoo")

    assert report.status == OptionsScanStatus.COMPLETED
    assert report.actual_source == "yahoo"
    assert report.data_kind == OptionsDataKind.CHAIN_SNAPSHOT
    assert report.total_matches == 2
    row = report.results.iloc[0]
    assert row["data_kind"] == "chain_snapshot"
    assert bool(row["is_sweep"]) is False
    assert row["side"] is None or pd.isna(row["side"])
    assert row["provider_sentiment"] is None or pd.isna(row["provider_sentiment"])
    assert row["timestamp"] is None or pd.isna(row["timestamp"])


def test_scan_chain_activity_with_report_mocked_tradier(_tradier_chain_row):
    df = pd.DataFrame([_tradier_chain_row])
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=df):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0, source="tradier")

    assert report.status == OptionsScanStatus.COMPLETED
    assert report.actual_source == "tradier"
    assert len(report.results) == 1
    assert report.results.iloc[0]["data_kind"] == "chain_snapshot"


def test_scan_chain_activity_wrapper_returns_results(_yahoo_chain):
    calls, puts = _yahoo_chain
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        df = flow.scan_chain_activity(["AAPL"], min_vol_oi=3.0, source="yahoo")
    assert len(df) == 2


def test_chain_report_high_vol_oi_qualifies(_tradier_chain_row):
    row = _tradier_chain_row
    row["volume"] = 3000
    row["open_interest"] = 1000
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_matches == 1
    assert report.results.iloc[0]["vol_oi_ratio"] == 3.0


def test_chain_report_exact_boundary():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 3000,
        "open_interest": 1000,
        "last": 5.0,
        "bid": 4.9,
        "ask": 5.1,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_matches == 1
    assert report.results.iloc[0]["vol_oi_ratio"] == 3.0


def test_chain_report_below_boundary_is_filtered():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 2999,
        "open_interest": 1000,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_matches == 0
    assert report.status == OptionsScanStatus.NO_MATCHES


def test_chain_report_zero_open_interest_is_null_ratio():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 3000,
        "open_interest": 0,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_fetched == 1
    assert report.total_matches == 0

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    assert pd.isna(df.iloc[0]["vol_oi_ratio"])


def test_chain_report_negative_open_interest_is_null_ratio():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 3000,
        "open_interest": -100,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_fetched == 1
    assert report.total_matches == 0

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    assert pd.isna(df.iloc[0]["vol_oi_ratio"])


def test_chain_report_negative_volume_is_excluded():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": -100,
        "open_interest": 100,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_fetched == 1
    assert report.total_matches == 0

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    assert pd.isna(df.iloc[0]["vol_oi_ratio"])


def test_chain_report_missing_volume_is_excluded():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "open_interest": 100,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_fetched == 1
    assert report.total_matches == 0

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    assert pd.isna(df.iloc[0]["vol_oi_ratio"])


def test_chain_report_nan_and_inf_rejection():
    row = {
        "option_type": "call",
        "strike": float("nan"),
        "expiration_date": "2024-02-16",
        "volume": float("inf"),
        "open_interest": 100,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.total_fetched == 1
    assert report.total_matches == 0

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    assert pd.isna(df.iloc[0]["strike"])
    assert pd.isna(df.iloc[0]["volume"])


def test_chain_report_no_premature_rounding():
    row = {
        "option_type": "call",
        "strike": 150.0,
        "expiration_date": "2024-02-16",
        "volume": 2000,
        "open_interest": 3,
    }
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=666.0)
    assert report.total_matches == 1

    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame([row])):
            df = flow.get_flow("AAPL", source="tradier")
    ratio = df.iloc[0]["vol_oi_ratio"]
    assert ratio is not None
    assert ratio > 666.0
    assert ratio == 2000 / 3


def test_chain_report_valid_zero_matches():
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame()):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=3.0)
    assert report.status == OptionsScanStatus.NO_MATCHES
    assert report.results.empty


def test_chain_report_partial_failure(_tradier_chain_row):
    df = pd.DataFrame([_tradier_chain_row])
    with _tradier_configured_via_patch():
        def _fetch(ticker):
            if ticker == "AAPL":
                return df
            raise ProviderTransientError("network timeout")

        with patch.object(flow, "_fetch_tradier_chain", side_effect=_fetch):
            report = flow.scan_chain_activity_with_report(["AAPL", "MSFT"], min_vol_oi=3.0)
    assert report.status == OptionsScanStatus.PARTIAL_FAILURE
    assert report.total_matches == 1
    assert "MSFT" in report.failures


def test_chain_report_complete_failure():
    with _tradier_configured_via_patch(), patch.object(
        flow, "_fetch_tradier_chain", side_effect=ProviderResponseError("HTTP 500")
    ):
        report = flow.scan_chain_activity_with_report(["AAPL", "MSFT"], min_vol_oi=3.0)
    assert report.status == OptionsScanStatus.COMPLETE_FAILURE
    assert "AAPL" in report.failures


def test_chain_report_sorting_is_deterministic():
    rows = [
        {"option_type": "call", "strike": 150.0, "expiration_date": "2024-02-16", "volume": 2000, "open_interest": 1000},
        {"option_type": "put", "strike": 150.0, "expiration_date": "2024-02-16", "volume": 3000, "open_interest": 1000},
    ]
    with _tradier_configured_via_patch():
        with patch.object(flow, "_fetch_tradier_chain", return_value=pd.DataFrame(rows)):
            report = flow.scan_chain_activity_with_report(["AAPL"], min_vol_oi=2.0)
    ratios = report.results["vol_oi_ratio"].tolist()
    assert ratios[0] >= ratios[1]


def test_chain_source_auto_no_fallback_for_explicit():
    with _tradier_configured_via_patch(), patch.object(flow, "_fetch_yf_chain") as yf_fetch:
        flow.scan_chain_activity_with_report(["AAPL"], source="tradier")
    yf_fetch.assert_not_called()


# ── put/call balance tests ───────────────────────────────────────────────────
def test_put_call_activity_call_only(_yahoo_chain):
    calls, puts = _yahoo_chain
    puts = puts.copy()
    puts["volume"] = 0.0
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["directional_inference"] is False
    assert result["volume_balance"] == "call_only"
    assert result["put_call_volume_ratio"] == 0.0
    assert result["call_volume"] == 3000
    assert result["put_volume"] == 0
    assert result["actual_source"] == "yahoo"


def test_put_call_activity_put_only():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [0.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [500.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["volume_balance"] == "put_only"
    assert result["put_call_volume_ratio"] is None


def test_put_call_activity_balanced():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [1000.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [900.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["volume_balance"] == "balanced"
    assert result["directional_inference"] is False


def test_put_call_activity_put_heavy():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [1000.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [2000.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["volume_balance"] == "put_heavy"


def test_put_call_activity_both_zero():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [0.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [0.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["put_call_volume_ratio"] is None
    assert result["volume_balance"] == "unknown"


def test_put_call_activity_no_bullish_bearish_wording():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [1000.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [0.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_activity("AAPL", source="yahoo")

    assert result["volume_balance"] != "bullish"
    assert result["volume_balance"] != "bearish"
    assert result["directional_inference"] is False


def test_put_call_activity_unavailable_source_is_structured():
    result = flow.get_put_call_activity("AAPL", source="unusual_whales")
    assert result["volume_balance"] == "unavailable"
    assert result["directional_inference"] is False
    assert "UNUSUAL_WHALES_API_KEY" in result["error"]


def test_put_call_sentiment_compatibility_wrapper():
    calls = pd.DataFrame({
        "strike": [150.0], "volume": [1000.0], "openInterest": [100.0],
        "lastPrice": [5.0], "bid": [4.9], "ask": [5.1],
    })
    puts = pd.DataFrame({
        "strike": [150.0], "volume": [0.0], "openInterest": [50.0],
        "lastPrice": [4.0], "bid": [3.9], "ask": [4.1],
    })
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        result = flow.get_put_call_sentiment("AAPL", source="yahoo")

    assert result["sentiment"] == "call_only"
    assert result["put_call_ratio"] == 0.0
    assert result["directional_inference"] is False
    assert result["data_source"] == "yahoo"


def test_put_call_sentiment_unavailable_source_compatibility():
    result = flow.get_put_call_sentiment("AAPL", source="unusual_whales")
    assert result["sentiment"] == "unavailable"
    assert result["directional_inference"] is False
    assert "UNUSUAL_WHALES_API_KEY" in result["error"]


# ── provider error handling tests ─────────────────────────────────────────────
def test_fetch_unusual_whales_missing_credentials():
    with pytest.raises(ProviderCapabilityError, match="UNUSUAL_WHALES_API_KEY"):
        flow._fetch_unusual_whales_flow("AAPL")


def test_fetch_tradier_missing_credentials():
    with pytest.raises(ProviderCapabilityError, match="TRADIER_API_KEY"):
        flow._fetch_tradier_chain("AAPL")


def test_fetch_unusual_whales_transient_timeout():
    with _uw_configured_via_patch():
        with patch.object(flow.requests, "get", side_effect=requests.Timeout("timeout")):
            with pytest.raises(ProviderTransientError, match="Timeout"):
                flow._fetch_unusual_whales_flow("AAPL")


def test_fetch_unusual_whales_http_error():
    resp = Mock(status_code=500, json=Mock(return_value={}), text="internal server error")
    with _uw_configured_via_patch(), patch.object(flow.requests, "get", return_value=resp):
        with pytest.raises(ProviderResponseError, match="HTTP 500"):
            flow._fetch_unusual_whales_flow("AAPL")


def test_fetch_unusual_whales_malformed_json():
    resp = Mock(status_code=200, json=Mock(side_effect=json.JSONDecodeError("test", "", 0)))
    with _uw_configured_via_patch(), patch.object(flow.requests, "get", return_value=resp):
        with pytest.raises(ProviderResponseError, match="malformed JSON"):
            flow._fetch_unusual_whales_flow("AAPL")


def test_fetch_tradier_valid_empty_response():
    resp = Mock(status_code=200, json=Mock(return_value={"expirations": {"date": []}}))
    with _tradier_configured_via_patch(), patch.object(flow.requests, "get", return_value=resp):
        df = flow._fetch_tradier_chain("AAPL")
    assert df.empty


def test_fetch_yf_valid_empty_options():
    fake_ticker = Mock(options=())
    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        df = flow._fetch_yf_chain("AAPL")
    assert df.empty


def test_no_raw_response_body_in_errors():
    resp = Mock(status_code=500, json=Mock(return_value={}), text="secret payload here")
    with _uw_configured_via_patch(), patch.object(flow.requests, "get", return_value=resp):
        with pytest.raises(ProviderResponseError) as exc:
            flow._fetch_unusual_whales_flow("AAPL")
    assert "secret payload" not in str(exc.value)
    assert "500" in str(exc.value)


def test_no_credential_leakage_in_errors():
    with _uw_configured_via_patch(), patch.object(
        flow, "_fetch_unusual_whales_flow", side_effect=ProviderResponseError("uw-test-key leak")
    ):
        report = flow.scan_unusual_flow_with_report(["AAPL"])
    if report.failures:
        assert "uw-test-key" not in report.failures["AAPL"]


def test_explicit_source_does_not_fall_back():
    with _uw_configured_via_patch():
        with patch.object(flow, "_fetch_unusual_whales_flow", side_effect=ProviderResponseError("fail")) as _uw_fetch:
            with patch.object(flow, "_fetch_tradier_chain") as tradier_fetch:
                with patch.object(flow, "_fetch_yf_chain") as yahoo_fetch:
                    report = flow.scan_unusual_flow_with_report(["AAPL"], source="unusual_whales")

    assert report.status == OptionsScanStatus.COMPLETE_FAILURE
    assert report.actual_source == "unusual_whales"
    tradier_fetch.assert_not_called()
    yahoo_fetch.assert_not_called()


# ── min_vol_oi validation tests ─────────────────────────────────────────────
def test_validate_min_vol_oi_rejects_bool():
    with pytest.raises((TypeError, ValueError)):
        flow._validate_min_vol_oi(True)


def test_validate_min_vol_oi_rejects_string():
    with pytest.raises((TypeError, ValueError)):
        flow._validate_min_vol_oi("3.0")


def test_validate_min_vol_oi_rejects_nan():
    with pytest.raises(ValueError):
        flow._validate_min_vol_oi(float("nan"))


def test_validate_min_vol_oi_rejects_inf():
    with pytest.raises(ValueError):
        flow._validate_min_vol_oi(float("inf"))


def test_validate_min_vol_oi_rejects_negative():
    with pytest.raises(ValueError):
        flow._validate_min_vol_oi(-1.0)


def test_validate_min_vol_oi_rejects_zero():
    with pytest.raises(ValueError):
        flow._validate_min_vol_oi(0.0)


def test_validate_min_vol_oi_accepts_positive():
    assert flow._validate_min_vol_oi(3.0) == 3.0


# ── compatibility and scope guards ────────────────────────────────────────────
def test_existing_source_choices_still_accepted():
    for source in ("auto", "unusual_whales", "tradier", "yahoo"):
        assert flow._resolve_options_source_name(source) == source


def test_scan_unusual_flow_is_importable():
    assert callable(flow.scan_unusual_flow)


def test_get_put_call_sentiment_is_importable():
    assert callable(flow.get_put_call_sentiment)


def test_get_flow_yahoo_returns_chain_snapshot(_yahoo_chain):
    calls, puts = _yahoo_chain
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        df = flow.get_flow("AAPL", source="yahoo")

    assert not df.empty
    assert (df["actual_source"] == "yahoo").all()
    assert (df["data_kind"] == "chain_snapshot").all()


def test_get_flow_auto_with_no_paid_keys_falls_back_to_yahoo(_yahoo_chain):
    calls, puts = _yahoo_chain
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        df = flow.get_flow("AAPL", source="auto")

    assert not df.empty
    assert (df["actual_source"] == "yahoo").all()


def test_wrapper_does_not_restore_misleading_behavior(_yahoo_chain):
    with pytest.raises(ProviderCapabilityError):
        flow.scan_unusual_flow(["AAPL"], source="yahoo")


# ── helpers ───────────────────────────────────────────────────────────────────
def _uw_configured_via_patch():
    return patch.object(flow, "UNUSUAL_WHALES_KEY", "uw-test-key")


def _tradier_configured_via_patch():
    return patch.object(flow, "TRADIER_KEY", "tradier-test-key")
