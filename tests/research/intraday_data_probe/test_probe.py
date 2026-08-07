"""Credential-free tests for the INTRA-001B Schwab five-minute probe."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderAuthenticationError
from tradex.research.intraday_data_probe.cli import main
from tradex.research.intraday_data_probe.models import ProbeReport, ProbeRequestRecord
from tradex.research.intraday_data_probe.probe import (
    _analyze_request,
    _build_decision,
    _classify_date_bound,
    _compare_methods,
    _count_duplicate_timestamps,
    _eastern_bounds,
    _expected_primary_sessions_and_bars,
    _is_early_close,
    _is_full_session,
    _load_calendar,
    _probe_kind,
    _sha256_dataframe,
    run_probe,
)
from tradex.research.intraday_data_probe.report import write_probe_artifacts, write_probe_report
from tradex.research.intraday_data_probe.spec import (
    IntradayProbeSpec,
    SpecValidationError,
    load_probe_spec,
    sha256_of_spec,
)


@pytest.fixture
def spec_path(tmp_path: Path) -> Path:
    """Return the path to a valid, locked probe-spec JSON."""
    spec = {
        "schema_version": 1,
        "task_id": "INTRA-001B-PROBE",
        "provider": "schwab",
        "bar_interval": "5m",
        "timezone": "America/New_York",
        "exchange_calendar": "XNYS",
        "need_extended_hours_data": False,
        "repeat_count": 2,
        "request_delay_seconds": 0.75,
        "symbols": ["SPY", "AAPL", "JPM"],
        "methods": ["convenience_every_five_minutes", "raw_price_history_five_minutes"],
        "full_range_probe": {"symbols": ["SPY"], "start_date": "2024-06-03", "end_date": "2024-06-07"},
        "bounded_window_probes": [
            {"id": "window-2024-w1", "start_date": "2024-06-03", "end_date": "2024-06-07"},
            {"id": "window-2024-w2", "start_date": "2024-06-10", "end_date": "2024-06-14"},
            {"id": "window-2024-w3", "start_date": "2024-06-17", "end_date": "2024-06-21"},
            {"id": "window-2024-w4", "start_date": "2024-06-24", "end_date": "2024-06-28"},
        ],
        "overlap_probe": {
            "symbol": "SPY",
            "left_start_date": "2024-06-03",
            "left_end_date": "2024-06-14",
            "right_start_date": "2024-06-10",
            "right_end_date": "2024-06-14",
        },
        "exclude_early_close_sessions_from_primary_coverage": True,
        "minimum_regular_session_coverage_pct": 95.0,
        "maximum_duplicate_bar_rate_pct": 1.0,
        "maximum_zero_volume_bar_rate_pct": 10.0,
        "maximum_persistent_retry_count": 1,
        "decision_requires_repeat_hash_match": True,
        "decision_requires_method_overlap_match": True,
        "decision_requires_chunk_overlap_match": True,
    }
    p = tmp_path / "probe-spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


@pytest.fixture
def spec(spec_path: Path) -> IntradayProbeSpec:
    spec, _ = load_probe_spec(spec_path)
    return spec


@pytest.fixture
def strategy_spec_path(tmp_path: Path) -> Path:
    p = tmp_path / "strategy-spec.json"
    p.write_text(json.dumps({"schema_version": 1, "task_id": "INTRA-001"}), encoding="utf-8")
    return p


class FakeResponse:
    def __init__(self, status_code: int, json_data=None, content: bytes = b"", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._json


class FakeClient:
    class PriceHistory:
        class FrequencyType:
            MINUTE = "minute"

        class Frequency:
            EVERY_FIVE_MINUTES = 5

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    def get_price_history_every_five_minutes(self, symbol, **kwargs):
        self.calls.append(("convenience", {"symbol": symbol, **kwargs}))
        return self.handler("convenience", symbol, kwargs)

    def get_price_history(self, symbol, **kwargs):
        self.calls.append(("raw", {"symbol": symbol, **kwargs}))
        return self.handler("raw", symbol, kwargs)


def _make_candles(symbol: str, start_utc: datetime, end_utc: datetime, seed: float = 100.0):
    """Return five-minute bar_start candles for every XNYS session in the requested UTC range."""
    from zoneinfo import ZoneInfo

    import exchange_calendars as xcals

    cal = xcals.get_calendar("XNYS")
    start_date = start_utc.astimezone(ZoneInfo("America/New_York")).date()
    end_date = end_utc.astimezone(ZoneInfo("America/New_York")).date()
    sessions = cal.sessions_in_range(start_date, end_date)
    candles: list[dict] = []
    day = 0
    for session in sessions:
        d = session.date()
        if not cal.is_session(d):
            continue
        open_ts = cal.session_open(d).tz_convert(UTC)
        close_ts = cal.session_close(d).tz_convert(UTC)
        for ts in pd.date_range(start=open_ts, end=close_ts, freq="5min", inclusive="left"):
            # Use the UTC timestamp in minutes so identical timestamps always get identical OHLCV values.
            i = int(ts.timestamp() // 60)
            o = seed + i * 0.01
            c = o + 0.005
            h = max(o, c) + 0.002
            l = min(o, c) - 0.002
            v = 1000 + i
            candles.append({
                "datetime": int(ts.timestamp() * 1000),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })
        day += 1
    return candles


def _make_empty_response():
    return FakeResponse(200, {"candles": []}, content=b'{"candles":[]}')


def _make_full_response(symbol: str, start_utc: datetime, end_utc: datetime):
    candles = _make_candles(symbol, start_utc, end_utc)
    payload = json.dumps({"candles": candles}, separators=(",", ":")).encode()
    return FakeResponse(200, {"candles": candles}, content=payload)


def test_load_probe_spec(spec_path: Path, spec: IntradayProbeSpec):
    assert spec.task_id == "INTRA-001B-PROBE"
    assert spec.provider == "schwab"
    assert spec.symbols == ("SPY", "AAPL", "JPM")
    assert spec.methods == (
        "convenience_every_five_minutes",
        "raw_price_history_five_minutes",
    )
    assert len(spec.bounded_window_probes) == 4
    assert sha256_of_spec(spec_path) == sha256_of_spec(spec_path)


def test_spec_rejects_unknown_fields(spec_path: Path, tmp_path: Path):
    data = json.loads(spec_path.read_text())
    data["extra_field"] = "bad"
    p = tmp_path / "bad-spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SpecValidationError, match="Unknown field"):
        load_probe_spec(p)


def test_strategy_spec_hash_matches(spec_path: Path, strategy_spec_path: Path):
    import hashlib
    _spec, raw = load_probe_spec(spec_path)
    assert hashlib.sha256(raw).hexdigest() == sha256_of_spec(spec_path)
    strategy_sha = hashlib.sha256(strategy_spec_path.read_bytes()).hexdigest()
    assert len(strategy_sha) == 64


def test_eastern_bounds_converts_to_utc():
    start_utc, end_utc = _eastern_bounds(date(2024, 6, 3), date(2024, 6, 7), "America/New_York")
    assert start_utc.tzinfo is UTC
    assert end_utc.tzinfo is UTC
    assert start_utc.day == 3
    assert start_utc.hour == 4  # 00:00 EDT is 04:00 UTC
    assert end_utc.day == 8
    assert end_utc.hour == 3  # 23:59:59.999 EDT is 03:59:59.999 UTC next day


def test_xnys_full_session_and_early_close():
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    assert _is_full_session(cal, date(2024, 6, 3))
    assert _is_early_close(cal, date(2024, 11, 29))
    assert not _is_early_close(cal, date(2024, 6, 3))


def test_expected_bars_for_full_session_window(spec: IntradayProbeSpec):
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    sessions, bars = _expected_primary_sessions_and_bars(
        cal, date(2024, 6, 3), date(2024, 6, 7), exclude_early_close=True
    )
    # 2024-06-03 to 2024-06-07 contains 5 full sessions (Mon-Fri).
    assert sessions == 5
    assert bars == 5 * 78


def test_holiday_sessions_excluded(spec: IntradayProbeSpec):
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    sessions, bars = _expected_primary_sessions_and_bars(
        cal, date(2024, 1, 1), date(2024, 1, 5), exclude_early_close=True
    )
    assert sessions == 4  # New Year's Day holiday
    assert bars == 4 * 78


def test_duplicate_timestamps_counted():
    candles = [
        {"datetime": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        {"datetime": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        {"datetime": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 200},
    ]
    assert _count_duplicate_timestamps(candles) == 1


def test_canonical_dataframe_hash_deterministic():
    df = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100]},
        index=pd.to_datetime(["2024-06-03T13:30:00+00:00"]),
    )
    df.index.name = "datetime"
    h1 = _sha256_dataframe(df)
    h2 = _sha256_dataframe(df.copy())
    assert h1 == h2


def test_date_bound_classification_full_coverage():
    index = pd.date_range("2024-06-03 09:30", periods=78, freq="5min", tz="America/New_York")
    df = pd.DataFrame(index=index, columns=["open", "high", "low", "close", "volume"]).fillna(1.0)
    result = _classify_date_bound(df, date(2024, 6, 3), date(2024, 6, 3), 100.0, 95.0, 0)
    assert result == "honored_exactly"


def test_date_bound_classification_empty():
    df = pd.DataFrame(index=pd.DatetimeIndex([], tz="America/New_York"))
    result = _classify_date_bound(df, date(2024, 6, 3), date(2024, 6, 3), 0.0, 95.0, 0)
    assert result == "empty"


def test_run_probe_empty_200(spec: IntradayProbeSpec, strategy_spec_path: Path, tmp_path: Path):
    def handler(method, symbol, kwargs):
        return _make_empty_response()

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    assert isinstance(report, ProbeReport)
    assert all(r.http_status == 200 for r in report.records)
    assert all(r.raw_candle_count == 0 for r in report.records)


def test_run_probe_no_period_or_frequency_type_for_convenience(spec: IntradayProbeSpec, strategy_spec_path: Path, tmp_path: Path):
    """Convenience method must not pass period_type/period; raw must pass frequency only."""
    captured = []

    def handler(method, symbol, kwargs):
        captured.append((method, kwargs))
        return _make_empty_response()

    client = FakeClient(handler)
    run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    for method, kwargs in captured:
        assert "period_type" not in kwargs
        assert "period" not in kwargs
        assert kwargs.get("need_extended_hours_data") is False
        if method == "convenience":
            assert "frequency_type" not in kwargs
            assert "frequency" not in kwargs
        else:
            assert kwargs.get("frequency_type") == FakeClient.PriceHistory.FrequencyType.MINUTE
            assert kwargs.get("frequency") == FakeClient.PriceHistory.Frequency.EVERY_FIVE_MINUTES


def test_run_probe_401_403_raises_authentication_error(spec: IntradayProbeSpec, tmp_path: Path):
    def handler(method, symbol, kwargs):
        return FakeResponse(401, {"error": "unauthorized"})

    client = FakeClient(handler)
    with pytest.raises(ProviderAuthenticationError):
        run_probe(
            spec=spec,
            strategy_spec_sha256="a" * 64,
            probe_spec_sha256="b" * 64,
            output_dir=tmp_path / "out",
            pre_registration_commit="abc123",
            schwab_py_version="1.5.1",
            client=client,
            sleeper=lambda _: None,
        )


def test_run_probe_400_recorded_safe(spec: IntradayProbeSpec, tmp_path: Path):
    def handler(method, symbol, kwargs):
        return FakeResponse(400, {"error": "bad request"})

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    assert all(r.http_status == 400 for r in report.records)
    assert all(r.safe_error_classification == "http_400" for r in report.records)


def test_run_probe_429_retries_once(spec: IntradayProbeSpec, tmp_path: Path):
    responses = [
        FakeResponse(429, {}, headers={"Retry-After": "1"}),
        _make_empty_response(),
    ] + [_make_empty_response()] * 200

    def handler(method, symbol, kwargs):
        return responses.pop(0) if responses else _make_empty_response()

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    first = report.records[0]
    assert first.http_status == 200
    assert first.retry_after_seconds == 1.0


def test_run_probe_5xx_fails_after_retry(spec: IntradayProbeSpec, tmp_path: Path):
    responses = [FakeResponse(500, {}), FakeResponse(500, {})]
    responses += [_make_empty_response()] * 200

    def handler(method, symbol, kwargs):
        return responses.pop(0) if responses else _make_empty_response()

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.records[0].http_status == 500
    assert report.records[0].safe_error_classification == "http_500"


def test_run_probe_full_coverage_and_timestamp_semantics(spec: IntradayProbeSpec, tmp_path: Path):
    """All bounded windows return full coverage; expect bar_start semantics and identical methods."""
    calls = []

    def handler(method, symbol, kwargs):
        calls.append((method, symbol, kwargs))
        start = kwargs["start_datetime"]
        end = kwargs["end_datetime"]
        return _make_full_response(symbol, start, end)

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    for r in report.records:
        if r.http_status == 200 and r.raw_candle_count > 0:
            assert r.timestamp_semantics_classification in ("bar_start", "bar_end", "undetermined")
            assert r.threshold_result in ("passed", "failed")


def test_run_probe_repeatability_and_method_parity(spec: IntradayProbeSpec, tmp_path: Path):
    def handler(method, symbol, kwargs):
        start = kwargs["start_datetime"]
        end = kwargs["end_datetime"]
        return _make_full_response(symbol, start, end)

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.repeatability_rows
    assert report.method_parity_rows
    assert all(r["repeat_hash_match"] for r in report.repeatability_rows)
    assert all(r["classification"] == "identical" for r in report.method_parity_rows)


def test_run_probe_chunk_overlap(spec: IntradayProbeSpec, tmp_path: Path):
    def handler(method, symbol, kwargs):
        start = kwargs["start_datetime"]
        end = kwargs["end_datetime"]
        return _make_full_response(symbol, start, end)

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.chunk_overlap_rows
    assert all(r["classification"] == "match" for r in report.chunk_overlap_rows)


def test_artifact_bundle_excludes_full_ohlcv(spec: IntradayProbeSpec, tmp_path: Path, strategy_spec_path: Path):
    def handler(method, symbol, kwargs):
        start = kwargs["start_datetime"]
        end = kwargs["end_datetime"]
        return _make_full_response(symbol, start, end)

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    artifact_dir = tmp_path / "artifacts"
    spec_bytes = json.dumps(spec.to_dict()).encode()
    write_probe_artifacts(
        report=report,
        spec=spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=strategy_spec_path,
        artifact_dir=artifact_dir,
        pre_registration_commit="abc123",
        repo_root=tmp_path,
    )
    run_dirs = list(artifact_dir.iterdir())
    assert run_dirs
    safe_dir = run_dirs[0]
    bundled = {p.name for p in safe_dir.iterdir()}
    required = {
        "README.txt",
        "artifact_manifest.json",
        "checksums.sha256",
        "probe_spec.lock.json",
        "strategy_spec_reference.json",
        "request_audit.csv",
        "coverage_summary.csv",
        "repeatability_summary.csv",
        "method_parity.csv",
        "chunk_overlap.csv",
        "decision.json",
    }
    assert required.issubset(bundled)
    assert not any(p.name.endswith(".csv") and "payload" in p.name for p in safe_dir.iterdir())


def test_report_generated(spec: IntradayProbeSpec, tmp_path: Path, strategy_spec_path: Path):
    def handler(method, symbol, kwargs):
        return _make_full_response(symbol, kwargs["start_datetime"], kwargs["end_datetime"])

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="abc123",
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    report_path = tmp_path / "report.md"
    write_probe_report(
        report=report,
        spec=spec,
        probe_spec_sha256="b" * 64,
        strategy_spec_sha256="a" * 64,
        pre_registration_commit="abc123",
        report_path=report_path,
    )
    text = report_path.read_text()
    assert "INTRA-001B" in text
    assert "decision" in text.lower()


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_run_help():
    with pytest.raises(SystemExit) as exc:
        main(["run", "--help"])
    assert exc.value.code == 0


def test_probe_kind():
    assert _probe_kind("full-SPY-convenience_every_five_minutes-rep1") == "full"
    assert _probe_kind("window-2022-02-AAPL-convenience_every_five_minutes-rep1") == "bounded"
    assert _probe_kind("overlap-left-SPY-convenience_every_five_minutes-rep1") == "overlap"


def _base_record(**kwargs):
    defaults = {
        "probe_id": "test", "symbol": "SPY", "method": "convenience_every_five_minutes", "repetition": 1,
        "requested_eastern_start": "", "requested_eastern_end": "", "requested_utc_start": "", "requested_utc_end": "",
        "http_status": 200, "safe_error_classification": "none", "raw_candle_count": 0, "normalized_candle_count": 0,
        "raw_earliest_timestamp": None, "raw_latest_timestamp": None, "requested_range_earliest": None, "requested_range_latest": None,
        "out_of_range_candles": 0, "unique_regular_sessions": 0, "expected_eligible_sessions": 0, "expected_regular_session_bars": 0,
        "returned_regular_session_bars": 0, "primary_session_bars": 0, "early_close_session_bars": 0, "extended_hours_bars": 0,
        "regular_session_coverage_pct": 0.0, "missing_regular_session_bars": 0, "duplicate_timestamps": 0, "duplicate_bar_rate_pct": 0.0,
        "zero_volume_bars": 0, "zero_volume_rate_pct": 0.0, "invalid_ohlc_rows": 0, "non_five_minute_intervals": 0,
        "candle_payload_sha256": "", "requested_range_normalized_sha256": "", "date_bound_classification": "honored_exactly",
        "timestamp_semantics_classification": "bar_start", "threshold_result": "failed", "retry_after_seconds": None, "notes": "",
        "page_count": 1, "next_page_token_present": False, "pagination_complete": True,
        "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": (), "token_sequence_sha256": "",
        "regular_session_zero_volume_bars": 0, "regular_session_zero_volume_rate_pct": 0.0,
        "regular_session_invalid_ohlc_rows": 0, "regular_session_duplicate_timestamps": 0, "regular_session_duplicate_bar_rate_pct": 0.0,
    }
    return ProbeRequestRecord(**{**defaults, **kwargs})


def test_grid_coverage_complete_session(spec: IntradayProbeSpec):
    cal = _load_calendar(spec.exchange_calendar)
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, spec.timezone)
    candles = _make_candles("SPY", start_utc, end_utc)
    rec = _analyze_request(
        None, 200, candles, "SPY", "convenience_every_five_minutes", start_utc, end_utc,
        start_date, end_date, cal, spec, "test", 1, None, "none",
    )
    assert rec.primary_session_bars == 78
    assert rec.regular_session_coverage_pct == 100.0
    assert rec.missing_regular_session_bars == 0
    assert rec.non_five_minute_intervals == 0


def test_grid_coverage_1600_extra_bar_does_not_inflate(spec: IntradayProbeSpec):
    cal = _load_calendar(spec.exchange_calendar)
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, spec.timezone)
    candles = _make_candles("SPY", start_utc, end_utc)
    close_ts = pd.Timestamp("2024-06-03 16:00", tz=spec.timezone).tz_convert(UTC)
    i = int(close_ts.timestamp() // 60)
    candles.append({
        "datetime": int(close_ts.timestamp() * 1000),
        "open": 100.0 + i * 0.01,
        "high": 100.0 + i * 0.01 + 0.002,
        "low": 100.0 + i * 0.01 - 0.002,
        "close": 100.0 + i * 0.01 + 0.005,
        "volume": 1000 + i,
    })
    rec = _analyze_request(
        None, 200, candles, "SPY", "convenience_every_five_minutes", start_utc, end_utc,
        start_date, end_date, cal, spec, "test", 1, None, "none",
    )
    assert rec.primary_session_bars == 78
    assert rec.extended_hours_bars == 1
    assert rec.regular_session_coverage_pct == 100.0
    assert rec.non_five_minute_intervals == 0


def test_grid_coverage_missing_bar_reduces_coverage(spec: IntradayProbeSpec):
    cal = _load_calendar(spec.exchange_calendar)
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, spec.timezone)
    candles = _make_candles("SPY", start_utc, end_utc)
    # Remove the 9:30 open bar.
    candles = candles[1:]
    rec = _analyze_request(
        None, 200, candles, "SPY", "convenience_every_five_minutes", start_utc, end_utc,
        start_date, end_date, cal, spec, "test", 1, None, "none",
    )
    assert rec.primary_session_bars == 77
    assert rec.missing_regular_session_bars == 1
    assert abs(rec.regular_session_coverage_pct - (77 / 78 * 100)) < 0.001
    assert rec.non_five_minute_intervals == 0


def test_pre_post_market_rows_are_extended_not_non_five(spec: IntradayProbeSpec):
    cal = _load_calendar(spec.exchange_calendar)
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, spec.timezone)
    candles = _make_candles("SPY", start_utc, end_utc)
    for ts_str in ("2024-06-03 09:25", "2024-06-03 16:05"):
        ts = pd.Timestamp(ts_str, tz=spec.timezone).tz_convert(UTC)
        i = int(ts.timestamp() // 60)
        candles.append({
            "datetime": int(ts.timestamp() * 1000),
            "open": 100.0 + i * 0.01,
            "high": 100.0 + i * 0.01 + 0.002,
            "low": 100.0 + i * 0.01 - 0.002,
            "close": 100.0 + i * 0.01 + 0.005,
            "volume": 1000 + i,
        })
    rec = _analyze_request(
        None, 200, candles, "SPY", "convenience_every_five_minutes", start_utc, end_utc,
        start_date, end_date, cal, spec, "test", 1, None, "none",
    )
    assert rec.primary_session_bars == 78
    assert rec.extended_hours_bars == 2
    assert rec.non_five_minute_intervals == 0


def test_method_parity_empty_empty_is_not_comparable():
    conv = _base_record(probe_id="window-2024-w1-SPY-convenience-rep1", symbol="SPY", method="convenience_every_five_minutes")
    raw = _base_record(probe_id="window-2024-w1-SPY-raw-rep1", symbol="SPY", method="raw_price_history_five_minutes")
    dfs = {"window-2024-w1-SPY-convenience": pd.DataFrame(), "window-2024-w1-SPY-raw": pd.DataFrame()}
    row = _compare_methods("window-2024-w1", "SPY", 1, conv, raw, dfs)
    assert row["classification"] == "not_comparable"


def test_chunked_support_false_when_expected_window_missing(spec: IntradayProbeSpec):
    """Only one bounded window passes; chunked support must be false because the locked set is incomplete."""
    records = [
        _base_record(
            probe_id="window-2025-12-SPY-convenience_every_five_minutes-rep1",
            symbol="SPY", method="convenience_every_five_minutes", threshold_result="passed",
            date_bound_classification="honored_exactly", primary_session_bars=78,
        ),
        _base_record(
            probe_id="window-2025-12-SPY-raw_price_history_five_minutes-rep1",
            symbol="SPY", method="raw_price_history_five_minutes", threshold_result="passed",
            date_bound_classification="honored_exactly", primary_session_bars=78,
        ),
    ]
    repeat_rows = [
        {"repeat_hash_match": True, "method": "convenience_every_five_minutes"},
        {"repeat_hash_match": True, "method": "raw_price_history_five_minutes"},
    ]
    parity_rows = [{"window": "window-2025-12-SPY", "classification": "identical"}]
    overlap_rows = [{"classification": "match", "method": "convenience_every_five_minutes"}]
    decision = _build_decision(
        spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1",
    )
    assert not decision.chunked_historical_windows_supported
    assert not decision.coverage_threshold_passed


def test_date_filtering_required_is_evidence_based(spec: IntradayProbeSpec):
    """date_filtering_required must be true only when a request actually returned out-of-range candles or a superset."""
    records = [
        _base_record(
            probe_id="window-2025-12-SPY-convenience_every_five_minutes-rep1",
            out_of_range_candles=1, date_bound_classification="superset_with_complete_requested_range", threshold_result="passed",
        ),
    ]
    decision = _build_decision(
        spec, records, [], [], [], "a" * 64, "b" * 64, "abc123", "1.5.1",
    )
    assert decision.date_filtering_required is True

    records_clean = [
        _base_record(
            probe_id="window-2025-12-SPY-convenience_every_five_minutes-rep1",
            out_of_range_candles=0, date_bound_classification="honored_exactly", threshold_result="passed",
        ),
    ]
    decision_clean = _build_decision(
        spec, records_clean, [], [], [], "a" * 64, "b" * 64, "abc123", "1.5.1",
    )
    assert decision_clean.date_filtering_required is False


def test_selected_request_method_is_none_when_not_supported(spec: IntradayProbeSpec):
    """If neither direct nor chunked access is supported, selected_request_method must be 'none'."""
    records = [
        _base_record(
            probe_id="full-SPY-convenience_every_five_minutes-rep1",
            symbol="SPY", method="convenience_every_five_minutes", threshold_result="failed",
            date_bound_classification="clipped_to_recent_history", primary_session_bars=10, expected_regular_session_bars=1000,
        ),
    ]
    repeat_rows = [{"repeat_hash_match": True, "method": "convenience_every_five_minutes"}]
    parity_rows = [{"window": "full-SPY", "classification": "not_comparable"}]
    overlap_rows = [{"classification": "not_comparable", "method": "convenience_every_five_minutes", "overlap_start": "2024-06-10T13:30:00.000000+0000"}]
    decision = _build_decision(
        spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1",
    )
    assert decision.selected_request_method == "none"
    assert decision.selected_windowing_policy == "none"
    assert not decision.approved_for_intra_001_five_minute_ohlcv


def _make_full_record(method: str, probe_id: str, symbol: str = "SPY", passed: bool = True) -> ProbeRequestRecord:
    return _base_record(
        probe_id=probe_id,
        symbol=symbol,
        method=method,
        threshold_result="passed" if passed else "failed",
        date_bound_classification="honored_exactly" if passed else "empty",
        primary_session_bars=78,
        raw_candle_count=78 if passed else 0,
        normalized_candle_count=78 if passed else 0,
        returned_regular_session_bars=78 if passed else 0,
        regular_session_coverage_pct=100.0 if passed else 0.0,
    )


def _full_records(method: str, passed: bool = True) -> list[ProbeRequestRecord]:
    return [_make_full_record(method, f"full-SPY-{method}-rep1", "SPY", passed=passed)]


def _bounded_records(method: str, spec: IntradayProbeSpec, passed: bool = True) -> list[ProbeRequestRecord]:
    records: list[ProbeRequestRecord] = []
    for window in spec.bounded_window_probes:
        for symbol in spec.symbols:
            records.append(_make_full_record(method, f"{window.id}-{symbol}-{method}-rep1", symbol, passed=passed))
    return records


def _repeat_row(method: str, match: bool = True) -> dict[str, Any]:
    return {"repeat_hash_match": match, "method": method}


def _parity_row(window: str, classification: str = "identical") -> dict[str, Any]:
    return {"window": window, "classification": classification}


def _overlap_row(method: str, classification: str = "match") -> dict[str, Any]:
    return {"classification": classification, "method": method, "overlap_start": "2024-06-10T13:30:00.000000+0000"}


def test_direct_support_raw_only(spec: IntradayProbeSpec):
    """A passing raw full-range request with a failing convenience method selects raw."""
    records = _full_records("raw_price_history_five_minutes") + _full_records("convenience_every_five_minutes", passed=False)
    repeat_rows = [_repeat_row("raw_price_history_five_minutes"), _repeat_row("convenience_every_five_minutes")]
    parity_rows = [_parity_row("full-SPY", "one_method_empty")]
    overlap_rows = []
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is True
    assert decision.chunked_historical_windows_supported is False
    assert decision.selected_request_method == "raw_price_history_five_minutes"
    assert decision.selected_windowing_policy == "direct_full_range"
    assert decision.approved_for_intra_001_five_minute_ohlcv is True


def test_direct_support_convenience_only(spec: IntradayProbeSpec):
    """A passing convenience full-range request with a failing raw method selects convenience."""
    records = _full_records("convenience_every_five_minutes") + _full_records("raw_price_history_five_minutes", passed=False)
    repeat_rows = [_repeat_row("convenience_every_five_minutes"), _repeat_row("raw_price_history_five_minutes")]
    parity_rows = [_parity_row("full-SPY", "one_method_empty")]
    overlap_rows = []
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is True
    assert decision.chunked_historical_windows_supported is False
    assert decision.selected_request_method == "convenience_every_five_minutes"
    assert decision.selected_windowing_policy == "direct_full_range"
    assert decision.approved_for_intra_001_five_minute_ohlcv is True


def test_chunked_support_raw_only(spec: IntradayProbeSpec):
    """A raw method that covers every bounded window and passes overlap selects raw + bounded chunks."""
    records = _bounded_records("raw_price_history_five_minutes", spec) + _bounded_records("convenience_every_five_minutes", spec, passed=False)
    repeat_rows = [_repeat_row("raw_price_history_five_minutes"), _repeat_row("convenience_every_five_minutes")]
    parity_rows = [_parity_row(f"{w.id}-{s}", "one_method_empty") for w in spec.bounded_window_probes for s in spec.symbols]
    overlap_rows = [_overlap_row("raw_price_history_five_minutes", "match")]
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is True
    assert decision.selected_request_method == "raw_price_history_five_minutes"
    assert decision.selected_windowing_policy == "bounded_monthly_chunks"
    assert decision.approved_for_intra_001_five_minute_ohlcv is True


def test_chunked_support_convenience_only(spec: IntradayProbeSpec):
    """A convenience method that covers every bounded window and passes overlap selects convenience + bounded chunks."""
    records = _bounded_records("convenience_every_five_minutes", spec) + _bounded_records("raw_price_history_five_minutes", spec, passed=False)
    repeat_rows = [_repeat_row("convenience_every_five_minutes"), _repeat_row("raw_price_history_five_minutes")]
    parity_rows = [_parity_row(f"{w.id}-{s}", "one_method_empty") for w in spec.bounded_window_probes for s in spec.symbols]
    overlap_rows = [_overlap_row("convenience_every_five_minutes", "match")]
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is True
    assert decision.selected_request_method == "convenience_every_five_minutes"
    assert decision.selected_windowing_policy == "bounded_monthly_chunks"
    assert decision.approved_for_intra_001_five_minute_ohlcv is True


def test_chunked_support_both_methods_matching_selects_convenience(spec: IntradayProbeSpec):
    """Both methods cover all bounded windows with identical data; convenience is preferred."""
    records = _bounded_records("convenience_every_five_minutes", spec) + _bounded_records("raw_price_history_five_minutes", spec)
    repeat_rows = [_repeat_row("convenience_every_five_minutes"), _repeat_row("raw_price_history_five_minutes")]
    parity_rows = [_parity_row(f"{w.id}-{s}", "identical") for w in spec.bounded_window_probes for s in spec.symbols]
    overlap_rows = [_overlap_row("convenience_every_five_minutes", "match"), _overlap_row("raw_price_history_five_minutes", "match")]
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is True
    assert decision.selected_request_method == "convenience_every_five_minutes"
    assert decision.selected_windowing_policy == "bounded_monthly_chunks"
    assert decision.approved_for_intra_001_five_minute_ohlcv is True


def test_both_methods_data_bearing_but_different_blocks_support(spec: IntradayProbeSpec):
    """If both methods produce data but disagree materially, no method or access pattern is selected."""
    records = _full_records("convenience_every_five_minutes") + _full_records("raw_price_history_five_minutes")
    repeat_rows = [_repeat_row("convenience_every_five_minutes"), _repeat_row("raw_price_history_five_minutes")]
    parity_rows = [_parity_row("full-SPY", "same_timestamps_different_values")]
    overlap_rows = []
    decision = _build_decision(spec, records, repeat_rows, parity_rows, overlap_rows, "a" * 64, "b" * 64, "abc123", "1.5.1")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is False
    assert decision.selected_request_method == "none"
    assert decision.selected_windowing_policy == "none"
    assert decision.approved_for_intra_001_five_minute_ohlcv is False


def test_safe_artifact_bundle_contains_no_absolute_paths(spec: IntradayProbeSpec, tmp_path: Path, strategy_spec_path: Path):
    """Generated safe artifacts must not embed /tmp/, /home/, Windows drive, or other absolute local paths."""
    def handler(method, symbol, kwargs):
        start = kwargs["start_datetime"]
        end = kwargs["end_datetime"]
        return _make_full_response(symbol, start, end)

    client = FakeClient(handler)
    report = run_probe(
        spec=spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="1.5.1",
        client=client,
        sleeper=lambda _: None,
    )
    artifact_dir = tmp_path / "artifacts"
    spec_bytes = json.dumps(spec.to_dict()).encode()
    write_probe_artifacts(
        report=report,
        spec=spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=strategy_spec_path,
        artifact_dir=artifact_dir,
        pre_registration_commit="a" * 40,
        repo_root=tmp_path,
    )
    safe_dirs = [p for p in artifact_dir.iterdir() if p.is_dir()]
    assert safe_dirs
    safe_dir = safe_dirs[0]

    forbidden_patterns = [
        "/tmp/",
        "/home/",
        "/Users/",
        "C:\\\\",
        "C:/",
        "D:\\\\",
        ":\\\\",
    ]
    failures: list[str] = []
    for p in safe_dir.iterdir():
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            if pat in text:
                failures.append(f"{p.name} contains forbidden path pattern {pat!r}")
    assert not failures, "\n".join(failures)
    ref = json.loads((safe_dir / "strategy_spec_reference.json").read_text())
    ref_path = Path(ref["file"])
    assert not ref_path.is_absolute(), f"strategy_spec_reference path must be relative, got {ref['file']!r}"


def test_decision_records_full_pre_registration_commit(spec: IntradayProbeSpec):
    """The pre-registration commit stored in the decision must be a 40-character SHA."""
    full_sha = "09fdbc4290705f3ecd175ba40bbc5f5cdc42ac74"
    records = _full_records("convenience_every_five_minutes", passed=False)
    decision = _build_decision(spec, records, [], [], [], "a" * 64, "b" * 64, full_sha, "1.5.1")
    assert decision.pre_registration_commit == full_sha
    assert len(decision.pre_registration_commit) == 40


# ---------------------------------------------------------------------------
# Alpaca-specific credential-free tests
# ---------------------------------------------------------------------------

@pytest.fixture
def alpaca_spec_path(tmp_path: Path) -> Path:
    """Return a valid, minimal Alpaca probe-spec JSON."""
    spec = {
        "schema_version": 1,
        "task_id": "INTRA-001B-ALPACA-TEST",
        "provider": "alpaca",
        "target_entitlement": "basic_free",
        "bar_interval": "5Min",
        "timezone": "America/New_York",
        "exchange_calendar": "XNYS",
        "candidate_feed": "sip",
        "comparison_feed": "iex",
        "adjustment": "raw",
        "asof": "2025-12-31",
        "sort": "asc",
        "page_limit": 10000,
        "repeat_count": 2,
        "request_delay_seconds": 0.01,
        "symbols": ["SPY"],
        "full_range_probe": {"symbols": ["SPY"], "start_date": "2024-06-03", "end_date": "2024-06-07"},
        "bounded_window_probes": [
            {"id": "window-2024-w1", "start_date": "2024-06-03", "end_date": "2024-06-07"},
        ],
        "overlap_probe": {
            "symbol": "SPY",
            "left_start_date": "2024-06-03",
            "left_end_date": "2024-06-07",
            "right_start_date": "2024-06-05",
            "right_end_date": "2024-06-11",
        },
        "exclude_early_close_sessions_from_primary_coverage": True,
        "minimum_regular_session_coverage_pct": 95.0,
        "maximum_duplicate_bar_rate_pct": 1.0,
        "maximum_zero_volume_bar_rate_pct": 10.0,
        "maximum_persistent_retry_count": 1,
        "decision_requires_repeat_hash_match": True,
        "decision_requires_method_overlap_match": False,
        "decision_requires_chunk_overlap_match": True,
        "approve_only_candidate_feed": True,
        "need_extended_hours_data": False,
    }
    p = tmp_path / "alpaca-probe-spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


@pytest.fixture
def alpaca_spec(alpaca_spec_path: Path) -> IntradayProbeSpec:
    spec, _ = load_probe_spec(alpaca_spec_path)
    return spec


@pytest.fixture
def locked_alpaca_spec() -> IntradayProbeSpec:
    spec, _ = load_probe_spec("docs/research/specs/INTRA-001B-alpaca-probe-v1.json")
    return spec


def _make_alpaca_candles(symbol: str, start_utc: datetime, end_utc: datetime, *, seed: float = 100.0, volume_offset: int = 0):
    """Return Alpaca-format bars for every XNYS session in the requested UTC range."""
    from zoneinfo import ZoneInfo

    import exchange_calendars as xcals

    cal = xcals.get_calendar("XNYS")
    start_date = start_utc.astimezone(ZoneInfo("America/New_York")).date()
    end_date = end_utc.astimezone(ZoneInfo("America/New_York")).date()
    sessions = cal.sessions_in_range(start_date, end_date)
    bars: list[dict] = []
    for session in sessions:
        d = session.date()
        if not cal.is_session(d):
            continue
        open_ts = cal.session_open(d).tz_convert(UTC)
        close_ts = cal.session_close(d).tz_convert(UTC)
        for ts in pd.date_range(start=open_ts, end=close_ts, freq="5min", inclusive="left"):
            i = int(ts.timestamp() // 60)
            o = seed + i * 0.01
            c = o + 0.005
            h = max(o, c) + 0.002
            l = min(o, c) - 0.002
            bars.append({
                "t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": 1000 + i + volume_offset,
            })
    return bars


def _make_alpaca_full_response(symbol: str, start_utc: datetime, end_utc: datetime, *, seed: float = 100.0, volume_offset: int = 0):
    bars = _make_alpaca_candles(symbol, start_utc, end_utc, seed=seed, volume_offset=volume_offset)
    payload = json.dumps({"bars": bars, "next_page_token": None}, separators=(",", ":")).encode()
    return FakeResponse(200, {"bars": bars, "next_page_token": None}, content=payload)


def _make_alpaca_empty_response():
    return FakeResponse(200, {"bars": [], "next_page_token": None}, content=b'{"bars":[],"next_page_token":null}')


def _make_paginated_alpaca_handler(pages: list[list[dict]]) -> Callable:
    """Return a request_func that serves the given pages sequentially."""
    calls: list[int] = [0]

    def handler(url: str, **kwargs):
        _params = kwargs.get("params", {})
        if "/v2/assets" in url:
            return FakeResponse(200, [{"symbol": "SPY", "asset_class": "us_equity"}], content=b'[]')
        if "/v1/corporate-actions" in url:
            return FakeResponse(200, {"corporate_actions": []}, content=b'{}')
        idx = calls[0]
        calls[0] += 1
        page = pages[idx] if idx < len(pages) else []
        token = "more" if idx < len(pages) - 1 else None
        data = {"bars": page, "next_page_token": token}
        return FakeResponse(200, data, content=json.dumps(data, separators=(",", ":")).encode())

    return handler


def _make_alpaca_handler(symbol: str = "SPY", *, seed: float = 100.0, volume_offset: int = 0, fail_status: int | None = None) -> Callable:
    calls: dict[str, Any] = {"count": 0, "params": []}

    def handler(url: str, **kwargs):
        params = kwargs.get("params", {})
        calls["params"].append((url, params))
        calls["count"] += 1
        if "/v2/assets" in url:
            return FakeResponse(200, [{"symbol": "SPY", "asset_class": "us_equity"}], content=b'[]')
        if "/v1/corporate-actions" in url:
            return FakeResponse(200, {"corporate_actions": []}, content=b'{}')
        if fail_status is not None and calls["count"] == 1:
            return FakeResponse(fail_status, {"error": "test"}, content=b'{}')
        # Parse symbol from /v2/stocks/{symbol}/bars
        parts = url.rstrip("/").split("/")
        sym = parts[-2] if parts[-1] == "bars" else symbol
        start = pd.to_datetime(params["start"], utc=True).to_pydatetime()
        end = pd.to_datetime(params["end"], utc=True).to_pydatetime()
        # SIP and IEX are expected to differ in volume; add a constant offset for IEX.
        effective_offset = volume_offset + (500 if params.get("feed") == "iex" else 0)
        bars = _make_alpaca_candles(sym, start, end, seed=seed, volume_offset=effective_offset)
        data = {"bars": bars, "next_page_token": None}
        return FakeResponse(200, data, content=json.dumps(data, separators=(",", ":")).encode())

    return handler, calls


def _make_alpaca_client(handler: Callable) -> Any:
    from tradex.research.intraday_data_probe.alpaca_client import AlpacaRestClient
    return AlpacaRestClient("PKFAKE", "FAKESECRET", request_func=handler)


def test_alpaca_spec_loads(locked_alpaca_spec: IntradayProbeSpec):
    assert locked_alpaca_spec.provider == "alpaca"
    assert locked_alpaca_spec.candidate_feed == "sip"
    assert locked_alpaca_spec.comparison_feed == "iex"
    assert locked_alpaca_spec.methods == ("sip", "iex")


def test_alpaca_missing_credentials_fail_before_network(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    from tradex.config import DataProviderSettings, TradeXSettings
    from tradex.research.intraday_data_probe.alpaca_client import make_alpaca_client
    settings = TradeXSettings(data=DataProviderSettings(alpaca_api_key="", alpaca_secret_key=""))
    with pytest.raises(OSError, match="ALPACA"):
        make_alpaca_client(settings)


def test_alpaca_query_parameters_exact(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    handler, calls = _make_alpaca_handler()
    client = _make_alpaca_client(handler)
    _ = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    bar_calls = [(url, p) for url, p in calls["params"] if "/v2/stocks/" in url]
    assert bar_calls
    for _, params in bar_calls:
        assert params["timeframe"] == "5Min"
        assert params["adjustment"] == "raw"
        assert params["asof"] == "2025-12-31"
        assert params["sort"] == "asc"
        assert params["limit"] == 10000
        assert params["feed"] in ("sip", "iex")
        assert "start" in params
        assert "end" in params


def test_alpaca_pagination_one_and_multi_page(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    start_utc, end_utc = _eastern_bounds(date(2024, 6, 3), date(2024, 6, 3), alpaca_spec.timezone)
    all_bars = _make_alpaca_candles("SPY", start_utc, end_utc)
    mid = len(all_bars) // 2
    pages = [all_bars[:mid], all_bars[mid:]]
    handler = _make_paginated_alpaca_handler(pages)
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    rec = next(r for r in report.records if r.probe_id.startswith("full") and r.method == "sip")
    assert rec.pagination_complete is True
    assert rec.page_count == 2
    assert rec.raw_candle_count == 78


def test_alpaca_repeated_page_token_cycle_detected(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    start_utc, end_utc = _eastern_bounds(date(2024, 6, 3), date(2024, 6, 3), alpaca_spec.timezone)
    bars = _make_alpaca_candles("SPY", start_utc, end_utc)
    data = {"bars": bars, "next_page_token": "stuck"}
    def handler(url: str, **kwargs):
        return FakeResponse(200, data, content=json.dumps(data, separators=(",", ":")).encode())
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    rec = next(r for r in report.records if r.probe_id.startswith("full"))
    assert rec.pagination_cycle_detected is True
    assert rec.repeated_page_token is True


def test_alpaca_401_stops_live_execution(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    def handler(url: str, **kwargs):
        return FakeResponse(401, {"error": "unauthorized"}, content=b'{}')
    client = _make_alpaca_client(handler)
    with pytest.raises(ProviderAuthenticationError):
        run_probe(
            spec=alpaca_spec,
            strategy_spec_sha256="a" * 64,
            probe_spec_sha256="b" * 64,
            output_dir=tmp_path / "out",
            pre_registration_commit="a" * 40,
            schwab_py_version="",
            client=client,
            sleeper=lambda _: None,
        )


def test_alpaca_403_recorded_safe(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    def handler(url: str, **kwargs):
        return FakeResponse(403, {"error": "forbidden"}, content=b'{}')
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert all(r.http_status == 403 for r in report.records)
    assert all(r.safe_error_classification == "http_403" for r in report.records)


def test_alpaca_429_retries_once(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    calls = {"n": 0}
    def handler(url: str, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(429, {}, headers={"Retry-After": "1"}, content=b'{}')
        return _make_alpaca_empty_response()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    rec = report.records[0]
    assert rec.http_status == 200
    assert rec.retry_after_seconds == 1.0


def test_alpaca_5xx_fails_after_retry(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    calls = {"n": 0}
    def handler(url: str, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            return FakeResponse(500, {}, content=b'{}')
        return _make_alpaca_empty_response()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.records[0].http_status == 500
    assert report.records[0].safe_error_classification == "http_500"


def test_alpaca_empty_response(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    client = _make_alpaca_client(lambda url, **kwargs: _make_alpaca_empty_response())
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert all(r.http_status == 200 and r.raw_candle_count == 0 for r in report.records)


def test_alpaca_78_bar_grid_and_missing_bar(alpaca_spec: IntradayProbeSpec):
    from tradex.research.intraday_data_probe.probe import _analyze_request
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, alpaca_spec.timezone)
    cal = _load_calendar(alpaca_spec.exchange_calendar)
    candles = _make_alpaca_candles("SPY", start_utc, end_utc)
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc,
        start_date, end_date, cal, alpaca_spec, "full-SPY-sip-rep1", 1, None, "none",
        provider="alpaca",
    )
    assert rec.primary_session_bars == 78
    assert rec.regular_session_coverage_pct == 100.0
    rec_missing = _analyze_request(
        None, 200, candles[1:], "SPY", "sip", start_utc, end_utc,
        start_date, end_date, cal, alpaca_spec, "full-SPY-sip-rep1", 1, None, "none",
        provider="alpaca",
    )
    assert rec_missing.primary_session_bars == 77
    assert rec_missing.missing_regular_session_bars == 1


def test_alpaca_1600_extra_bar_and_extended_hours(alpaca_spec: IntradayProbeSpec):
    from tradex.research.intraday_data_probe.probe import _analyze_request
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, alpaca_spec.timezone)
    cal = _load_calendar(alpaca_spec.exchange_calendar)
    candles = _make_alpaca_candles("SPY", start_utc, end_utc)
    for ts_str in ("2024-06-03 09:25", "2024-06-03 16:00", "2024-06-03 16:05"):
        ts = pd.Timestamp(ts_str, tz=alpaca_spec.timezone).tz_convert(UTC)
        i = int(ts.timestamp() // 60)
        candles.append({
            "t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "o": 100.0 + i * 0.01,
            "h": 100.0 + i * 0.01 + 0.002,
            "l": 100.0 + i * 0.01 - 0.002,
            "c": 100.0 + i * 0.01 + 0.005,
            "v": 1000 + i,
        })
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc,
        start_date, end_date, cal, alpaca_spec, "full-SPY-sip-rep1", 1, None, "none",
        provider="alpaca",
    )
    assert rec.primary_session_bars == 78
    assert rec.extended_hours_bars == 3
    assert rec.non_five_minute_intervals == 0


def test_alpaca_duplicate_zero_volume_invalid_ohlc_rates(alpaca_spec: IntradayProbeSpec):
    from tradex.research.intraday_data_probe.probe import _analyze_request
    start_date = date(2024, 6, 3)
    end_date = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(start_date, end_date, alpaca_spec.timezone)
    cal = _load_calendar(alpaca_spec.exchange_calendar)
    candles = _make_alpaca_candles("SPY", start_utc, end_utc)
    # Duplicate first timestamp
    candles.insert(0, candles[0].copy())
    # Zero volume bar
    candles[2]["v"] = 0
    # Invalid OHLC: low > open
    candles[3]["l"] = candles[3]["o"] + 1.0
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc,
        start_date, end_date, cal, alpaca_spec, "full-SPY-sip-rep1", 1, None, "none",
        provider="alpaca",
    )
    assert rec.duplicate_timestamps == 1
    assert rec.zero_volume_bars == 1
    assert rec.invalid_ohlc_rows == 1


def test_alpaca_repeat_hash_match_and_chunk_overlap(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    handler, _ = _make_alpaca_handler()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert all(r["repeat_hash_match"] for r in report.repeatability_rows if r["method"] == "sip")
    overlap = [r for r in report.chunk_overlap_rows if r["method"] == "sip"]
    assert overlap and all(r["classification"] == "match" for r in overlap)


def test_alpaca_feed_comparison_and_decision_paths(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    handler, _ = _make_alpaca_handler()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.feed_comparison_rows
    sip_rows = [r for r in report.feed_comparison_rows if r["candidate_probe_id"].endswith("-sip-rep1")]
    assert all(r["classification"] == "same_timestamps_different_values" for r in sip_rows)
    assert report.decision.outcome in ("supported_ohlcv_only", "supported_complete")
    assert report.decision.approved_for_intra_001_five_minute_ohlcv is True


def test_alpaca_supported_complete_when_contract_fully_met(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    """If every remaining contract dimension were supported, outcome would be supported_complete."""
    from tradex.research.intraday_data_probe.probe import _build_decision
    records = [
        _base_record(
            probe_id="full-SPY-sip-rep1", symbol="SPY", method="sip",
            threshold_result="passed", date_bound_classification="honored_exactly", primary_session_bars=78,
            raw_candle_count=78, normalized_candle_count=78, http_status=200,
        ),
        _base_record(
            probe_id="full-SPY-sip-rep2", symbol="SPY", method="sip",
            threshold_result="passed", date_bound_classification="honored_exactly", primary_session_bars=78,
            raw_candle_count=78, normalized_candle_count=78, http_status=200,
        ),
    ]
    provider_rows = [
        {"requirement": "point_in_time_universe", "supported": True},
        {"requirement": "security_type_provenance", "supported": True},
        {"requirement": "inactive_delisted_symbol_listing", "supported": True},
        {"requirement": "corporate_action_provenance", "supported": True},
    ]
    repeat_rows = [{"repeat_hash_match": True, "method": "sip"}]
    # The decision is tied to spec.provider, so we create a tiny spec clone.
    from dataclasses import replace
    test_spec = replace(alpaca_spec)
    decision = _build_decision(
        test_spec, records, repeat_rows, [], [], "a" * 64, "b" * 64, "a" * 40, "",
        provider_contract_rows=provider_rows,
    )
    assert decision.outcome == "supported_complete"
    assert decision.approved_as_complete_intra_001_data_source is True


def test_alpaca_not_supported_when_no_data(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    client = _make_alpaca_client(lambda url, **kwargs: _make_alpaca_empty_response())
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.decision.outcome == "not_supported"
    assert report.decision.approved_for_intra_001_five_minute_ohlcv is False


def test_alpaca_safe_artifact_bundle_no_absolute_paths(alpaca_spec: IntradayProbeSpec, tmp_path: Path, strategy_spec_path: Path):
    handler, _ = _make_alpaca_handler()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    artifact_dir = tmp_path / "artifacts"
    spec_bytes = json.dumps(alpaca_spec.to_dict()).encode()
    write_probe_artifacts(
        report=report,
        spec=alpaca_spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=strategy_spec_path,
        artifact_dir=artifact_dir,
        pre_registration_commit="a" * 40,
        repo_root=tmp_path,
    )
    safe_dirs = [p for p in artifact_dir.iterdir() if p.is_dir()]
    assert safe_dirs
    safe_dir = safe_dirs[0]
    forbidden = ["/tmp/", "/home/", "/Users/", "C:\\\\", "C:/", "D:\\\\", ":\\\\"]
    failures: list[str] = []
    for p in safe_dir.iterdir():
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for pat in forbidden:
            if pat in text:
                failures.append(f"{p.name} contains forbidden path {pat!r}")
    assert not failures, "\n".join(failures)


def test_alpaca_preregistration_commit_retained_in_decision(alpaca_spec: IntradayProbeSpec, tmp_path: Path):
    handler, _ = _make_alpaca_handler()
    client = _make_alpaca_client(handler)
    report = run_probe(
        spec=alpaca_spec,
        strategy_spec_sha256="a" * 64,
        probe_spec_sha256="b" * 64,
        output_dir=tmp_path / "out",
        pre_registration_commit="a" * 40,
        schwab_py_version="",
        client=client,
        sleeper=lambda _: None,
    )
    assert report.decision.pre_registration_commit == "a" * 40
    assert len(report.decision.pre_registration_commit) == 40
