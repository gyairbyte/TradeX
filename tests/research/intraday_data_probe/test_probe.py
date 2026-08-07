"""Credential-free tests for the INTRA-001B Schwab five-minute probe."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderAuthenticationError
from tradex.research.intraday_data_probe.cli import main
from tradex.research.intraday_data_probe.models import ProbeReport
from tradex.research.intraday_data_probe.probe import (
    _classify_date_bound,
    _count_duplicate_timestamps,
    _eastern_bounds,
    _expected_primary_sessions_and_bars,
    _is_early_close,
    _is_full_session,
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
        output_dir=tmp_path / "out",
        artifact_dir=artifact_dir,
        pre_registration_commit="abc123",
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
