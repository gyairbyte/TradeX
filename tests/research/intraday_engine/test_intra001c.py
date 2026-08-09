"""Tests for the INTRA-001C synthetic intraday research engine."""
from __future__ import annotations

import hashlib
import json
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from tradex.research.intraday_engine import (
    TickerInput,
    generate_synthetic_inputs,
    load_spec,
    run_study,
)
from tradex.research.intraday_engine.baseline_a import (
    _baseline_a_search_window,
    evaluate_baseline_a_session,
)
from tradex.research.intraday_engine.baseline_b import evaluate_baseline_b_session
from tradex.research.intraday_engine.calendar import build_sessions
from tradex.research.intraday_engine.candidate import evaluate_candidate_session
from tradex.research.intraday_engine.execution import attempt_trade
from tradex.research.intraday_engine.gates import SampleMinimums, evaluate_gates
from tradex.research.intraday_engine.models import (
    CostScenario,
    DataQualitySummary,
    PerSymbolMetrics,
    StudyMetrics,
    TickerMeta,
)
from tradex.research.intraday_engine.normalize import (
    NormalizationError,
    evaluate_data_contract,
    evaluate_data_sufficiency,
    normalize_to_sessions,
)
from tradex.research.intraday_engine.opening_drive import evaluate_opening_drive
from tradex.research.intraday_engine.reclaim import _grid_in_window, find_first_reclaim
from tradex.research.intraday_engine.spec import _INTRA_001_SPEC_SHA256
from tradex.research.intraday_engine.vwap import compute_session_vwap


@pytest.fixture
def spec():
    return load_spec()[0]


@pytest.fixture
def primary_cost(spec):
    return spec.primary_cost_scenario()


def _session_grid_2025_01_02():
    sessions = build_sessions(date(2025, 1, 2), date(2025, 1, 2))
    assert sessions
    return sessions[0]


def _make_session_df(session, base: float = 100.0, reclaim: bool = True):
    """Create a DataFrame for one regular session with a controlled reclaim."""
    grid = sorted(session.grid)
    records = []
    cum_pv = 0.0
    cum_v = 0.0
    vwap = base
    prev_close = base
    for i, g in enumerate(grid):
        if i < 6:
            open_p = base * (1 + i * 0.0012)
            close_p = open_p * 1.0015
            vol = 10_000_000
        elif i == 12 and reclaim:
            open_p = prev_close
            close_p = max(vwap * 1.004, open_p * 1.002)
            low_p = vwap * 0.995
            high_p = close_p * 1.001
            vol = 1_000_000
        elif i == 13 and reclaim:
            # Entry bar that hits target on the same bar.
            signal_close = close_p if i == 13 else prev_close
            signal_low = low_p if i == 13 else prev_close * 0.995
            entry_fill = signal_close * 1.0005
            stop = signal_low - max(0.01, signal_close * 0.0005)
            risk = entry_fill - stop
            target = entry_fill + 1.5 * risk
            open_p = signal_close
            close_p = target * 1.001
            high_p = close_p * 1.001
            low_p = open_p * 0.999
            vol = 1_000_000
        else:
            open_p = prev_close
            close_p = open_p * 1.0002
            high_p = max(open_p, close_p) * 1.001
            low_p = min(open_p, close_p) * 0.999
            vol = 1_000_000

        if i < 12 or (i == 12 and not reclaim):
            high_p = max(open_p, close_p) * 1.001
            low_p = min(open_p, close_p) * 0.999

        typical = (high_p + low_p + close_p) / 3.0
        cum_pv += typical * vol
        cum_v += vol
        if cum_v > 0:
            vwap = cum_pv / cum_v

        records.append(
            {
                "datetime": g,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": vol,
            }
        )
        prev_close = close_p

    df = pd.DataFrame(records)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df.set_index("datetime").sort_index()


def _single_session_input(spec, base: float = 100.0, reclaim: bool = True, ticker: str = "SYNTH-001"):
    session = _session_grid_2025_01_02()
    df = _make_session_df(session, base=base, reclaim=reclaim)
    sessions, _ = normalize_to_sessions(df, ticker)
    assert sessions
    meta = TickerMeta(
        ticker=ticker,
        is_etf=False,
        is_eligible=True,
        prior_close=base,
        prior_20_median_dollar_volume=base * 1_000_000,
    )
    return TickerInput(ticker=ticker, meta=meta, sessions=sessions)


def _make_prior_sessions(spec, base: float = 100.0, n: int = 20, first_six_volume: float = 1_000_000):
    """Create prior sessions with low opening-drive volume for the current session to qualify."""
    prior = []
    for i in range(n):
        ti = _single_session_input(spec, base=base, reclaim=False, ticker=f"PRIOR-{i:03d}")
        sess = ti.sessions[0]
        for g in sorted(sess.grid)[:6]:
            sess.bars[g].volume = first_six_volume
        prior.append(sess)
    return prior


class TestSpec:
    def test_locked_spec_sha(self):
        spec, raw_bytes = load_spec()
        assert hashlib.sha256(raw_bytes).hexdigest() == _INTRA_001_SPEC_SHA256
        assert spec.sha256 == _INTRA_001_SPEC_SHA256


class TestSessionVwap:
    def test_session_vwap_and_bar_count(self):
        session = _session_grid_2025_01_02()
        assert len(session.grid) == 78  # 9:30-16:00 ET in 5m intervals
        df = _make_session_df(session)
        sessions, summary = normalize_to_sessions(df, "SYNTH-001")
        assert len(sessions) == 1
        sess = sessions[0]
        compute_session_vwap(sess)
        assert sess.valid_bar_count() == 78
        assert summary.valid_bars == 78
        assert summary.missing_bars == 0

    def test_reject_naive_timestamps(self):
        session = _session_grid_2025_01_02()
        df = _make_session_df(session)
        df.index = df.index.tz_localize(None)
        with pytest.raises(NormalizationError):
            normalize_to_sessions(df, "SYNTH-001")


class TestOpeningDrive:
    def test_opening_drive_qualifies(self, spec):
        ti = _single_session_input(spec)
        prior = _make_prior_sessions(spec, n=20)
        compute_session_vwap(ti.sessions[0])
        state = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        assert state.qualified is True
        assert state.return_pct is not None
        assert state.return_pct >= 0.75
        assert state.volume_multiple is not None
        assert state.volume_multiple >= 1.5

    def test_opening_drive_fails_with_low_volume(self, spec):
        ti = _single_session_input(spec)
        # Prior sessions have 10x volume, so current is below 1.5x median.
        prior = []
        for _ in range(20):
            s = _single_session_input(spec, ticker="PRIOR").sessions[0]
            for b in s.bars.values():
                b.volume = b.volume * 10
            prior.append(s)
        compute_session_vwap(ti.sessions[0])
        state = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        assert state.qualified is False


class TestReclaimAndExecution:
    def test_first_reclaim_only(self, spec):
        ti = _single_session_input(spec)
        from tradex.research.intraday_engine.opening_drive import evaluate_opening_drive
        prior = _make_prior_sessions(spec, n=20)
        compute_session_vwap(ti.sessions[0])
        od = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        bar = find_first_reclaim(ti.sessions[0], od, spec, require_opening_drive=True)
        assert bar is not None
        # Ensure the first reclaim is in the search window.
        et_time = bar.bar_start.astimezone(ZoneInfo("America/New_York")).time()
        assert et_time >= spec.reclaim_search_start_time
        assert et_time < spec.reclaim_search_end_time

    def test_target_exit(self, spec, primary_cost):
        ti = _single_session_input(spec)
        from tradex.research.intraday_engine.opening_drive import evaluate_opening_drive
        prior = _make_prior_sessions(spec, n=20)
        compute_session_vwap(ti.sessions[0])
        od = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        bar = find_first_reclaim(ti.sessions[0], od, spec, require_opening_drive=True)
        assert bar is not None
        stop = bar.low - max(0.01, bar.close * 0.0005)
        sig = attempt_trade(
            ti.ticker,
            ti.meta,
            ti.sessions[0],
            bar,
            stop,
            od.qualified,
            None,
            primary_cost,
            spec,
            "candidate",
        )
        assert sig.status == "executed"
        assert sig.trade is not None
        assert sig.trade.exit_type == "target"
        assert sig.trade.net_r > 0

    def test_entry_rejected_if_next_open_at_or_below_stop(self, spec, primary_cost):
        ti = _single_session_input(spec, reclaim=True)
        session = ti.sessions[0]
        compute_session_vwap(session)
        from tradex.research.intraday_engine.opening_drive import evaluate_opening_drive
        prior = _make_prior_sessions(spec, n=20)
        od = evaluate_opening_drive(session, prior, ti.meta, spec)
        bar = find_first_reclaim(session, od, spec, require_opening_drive=False)
        assert bar is not None
        # Manually set the next bar's open below stop.
        grid = sorted(session.grid)
        idx = grid.index(bar.bar_start)
        next_bar = session.bars[grid[idx + 1]]
        next_bar.open = bar.low - 0.10
        next_bar.low = next_bar.open * 0.999
        next_bar.high = next_bar.open * 1.001
        next_bar.close = next_bar.open
        stop = bar.low - max(0.01, bar.close * 0.0005)
        sig = attempt_trade(
            ti.ticker,
            ti.meta,
            session,
            bar,
            stop,
            True,
            None,
            primary_cost,
            spec,
            "candidate",
        )
        assert sig.status == "rejected_entry_at_or_below_stop"


class TestBaseline:
    def test_baseline_b_runs_without_opening_drive(self, spec, primary_cost):
        ti = _single_session_input(spec)
        from tradex.research.intraday_engine.baseline_b import evaluate_baseline_b_session
        signals = evaluate_baseline_b_session(
            ti.ticker, ti.meta, ti.sessions[0], [], primary_cost, spec
        )
        # Baseline B does not require opening drive; it should find the reclaim.
        assert signals
        executed = [s for s in signals if s.status == "executed"]
        assert executed

    def test_baseline_a_uses_fresh_weights_no_saved_weights(self, spec, primary_cost, monkeypatch):
        ti = _single_session_input(spec)
        from tradex.research.intraday_engine import baseline_a as baseline_a_mod
        from tradex.signals import weights as weights_mod

        def fake_load(*args, **kwargs):
            raise RuntimeError("load_weights should not be called")

        monkeypatch.setattr(weights_mod, "load", fake_load)
        signals = baseline_a_mod.evaluate_baseline_a_session(
            ti.ticker, ti.meta, ti.sessions[0], [], primary_cost, spec
        )
        assert signals


class TestCosts:
    def test_adverse_fill_formula(self, spec):
        cost = CostScenario(
            name="primary",
            entry_slippage_bps=5.0,
            exit_slippage_bps=5.0,
            entry_commission_bps=0.0,
            exit_commission_bps=0.0,
        )
        entry_open = 100.0
        assert cost.entry_fill(entry_open) == entry_open * (1 + 5 / 10000)
        exit_raw = 110.0
        assert cost.exit_fill(exit_raw) == exit_raw * (1 - 5 / 10000)


class TestSyntheticWorkflow:
    def test_synthetic_run_is_marked_synthetic_and_not_evidence(self, spec):
        inputs = generate_synthetic_inputs(
            spec, seed=42, n_stock_tickers=2, n_etf_tickers=1, n_sessions=30
        )
        result = run_study(inputs, spec, synthetic=True, evidence_eligible=False)
        assert result.synthetic is True
        assert result.evidence_eligible is False
        assert result.spec_sha256 == _INTRA_001_SPEC_SHA256
        # Baseline B usually produces trades; candidate may be limited by volume baseline.
        baseline_b_executed = [s for s in result.baseline_b_signals if s.status == "executed"]
        assert baseline_b_executed

    def test_synthetic_determinism(self, spec, tmp_path):
        inputs = generate_synthetic_inputs(
            spec, seed=99, n_stock_tickers=2, n_etf_tickers=1, n_sessions=25
        )
        r1 = run_study(inputs, spec)
        r2 = run_study(inputs, spec)
        assert r1.outcome.disposition == r2.outcome.disposition
        assert len(r1.candidate_signals) == len(r2.candidate_signals)


class TestCLI:
    def test_synthetic_smoke_cli(self, spec, tmp_path):
        from tradex.research.intraday_engine.cli import main
        out = str(tmp_path / "smoke")
        ret = main(
            [
                "synthetic-smoke",
                "--output",
                out,
                "--seed",
                "123",
                "--n-stock-tickers",
                "2",
                "--n-etf-tickers",
                "1",
                "--n-sessions",
                "20",
            ]
        )
        assert ret == 0
        result_path = Path(out) / "result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["synthetic"] is True
        assert data["evidence_eligible"] is False


class TestEligibility:
    def _meta(self, **kwargs):
        defaults = {
            "ticker": "SYNTH-001",
            "is_etf": False,
            "is_eligible": True,
            "prior_close": 100.0,
            "prior_20_median_dollar_volume": 100_000_000.0,
            "security_type": "common_stock",
        }
        defaults.update(kwargs)
        return TickerMeta(**defaults)

    def test_candidate_rejects_ineligible_ticker(self, spec, primary_cost):
        for kwargs, reason_substr in [
            ({"is_eligible": False}, "ticker_not_eligible"),
            ({"prior_close": 3.0}, "prior_close_3.0"),
            ({"prior_20_median_dollar_volume": 1_000_000.0}, "prior_20_median_dollar_volume"),
            ({"security_type": "preferred_stock"}, "security_type_excluded"),
        ]:
            ti = _single_session_input(spec)
            ti.meta = self._meta(**kwargs)
            sigs = evaluate_candidate_session(
                ti.ticker, ti.meta, ti.sessions[0], [], primary_cost, spec
            )
            assert len(sigs) == 1
            assert sigs[0].status == "no_signal"
            assert reason_substr in sigs[0].reason

    def test_baseline_a_rejects_ineligible_ticker(self, spec, primary_cost):
        ti = _single_session_input(spec)
        ti.meta = self._meta(is_eligible=False)
        sigs = evaluate_baseline_a_session(
            ti.ticker, ti.meta, ti.sessions[0], [], primary_cost, spec
        )
        assert len(sigs) == 1
        assert sigs[0].status == "no_signal"
        assert "ticker_not_eligible" in sigs[0].reason

    def test_baseline_b_rejects_ineligible_ticker(self, spec, primary_cost):
        ti = _single_session_input(spec)
        ti.meta = self._meta(security_type="warrant")
        sigs = evaluate_baseline_b_session(
            ti.ticker, ti.meta, ti.sessions[0], [], primary_cost, spec
        )
        assert len(sigs) == 1
        assert sigs[0].status == "no_signal"
        assert "security_type_excluded" in sigs[0].reason


class TestOpeningDriveHistory:
    def test_requires_twenty_complete_prior_sessions(self, spec):
        ti = _single_session_input(spec)
        # 19 prior sessions should fail the volume baseline.
        prior = _make_prior_sessions(spec, n=19)
        compute_session_vwap(ti.sessions[0])
        state = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        assert state.qualified is False
        assert any("insufficient_prior_20_complete_sessions" in r for r in state.reasons)

    def test_prior_session_with_missing_first_bar_fails(self, spec):
        ti = _single_session_input(spec)
        prior = _make_prior_sessions(spec, n=20)
        # Delete the first bar of the most recent prior session.
        latest = prior[-1]
        first_grid = min(latest.grid)
        del latest.bars[first_grid]
        compute_session_vwap(ti.sessions[0])
        state = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        assert state.qualified is False
        assert any("insufficient_prior_20_complete_sessions" in r for r in state.reasons)

    def test_uses_most_recent_twenty_prior_sessions(self, spec):
        ti = _single_session_input(spec)
        prior = _make_prior_sessions(spec, n=25)
        # Make the oldest 5 have a very different first-six volume.
        for s in prior[:5]:
            for g in sorted(s.grid)[:6]:
                s.bars[g].volume = 999_999_999
        compute_session_vwap(ti.sessions[0])
        state = evaluate_opening_drive(ti.sessions[0], prior, ti.meta, spec)
        # Median should be 6 * 1_000_000, not dominated by old outliers.
        assert state.median_prior_cumulative_volume == 6_000_000.0

    def test_exact_return_and_volume_boundaries(self, spec):
        session = _session_grid_2025_01_02()
        # Just enough to pass: 0.75% return and 1.5x volume.
        records = []
        close_p = 100.0
        for i, g in enumerate(sorted(session.grid)):
            if i < 6:
                open_p = 100.0
                close_p = 100.75
                vol = 1_500_000
            else:
                open_p = close_p
                close_p = open_p * 1.0001
                vol = 1_000_000
            high_p = max(open_p, close_p) * 1.001
            low_p = min(open_p, close_p) * 0.999
            records.append({"datetime": g, "open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": vol})
        df = pd.DataFrame(records).set_index("datetime")
        df.index = pd.to_datetime(df.index, utc=True)
        sessions, _ = normalize_to_sessions(df, "BOUNDARY")
        sess = sessions[0]
        prior = _make_prior_sessions(spec, n=20, first_six_volume=1_000_000)
        # Prior median cumulative volume = 6 * 1_000_000 = 6M.
        # Current first-six = 6 * 1.5M = 9M -> 1.5x exactly.
        compute_session_vwap(sess)
        state = evaluate_opening_drive(sess, prior, TickerMeta("BOUNDARY", False, True, 100.0, 100_000_000.0), spec)
        assert state.return_pct == pytest.approx(0.75, abs=1e-9)
        assert state.volume_multiple == pytest.approx(1.5, abs=1e-9)
        assert state.qualified is True


class TestReclaimAndWindows:
    def test_candidate_excludes_955_bar(self, spec, primary_cost):
        session = _session_grid_2025_01_02()
        # Build a session where the 9:55 bar (index 5) would satisfy reclaim.
        grid = sorted(session.grid)
        records = []
        for i, g in enumerate(grid):
            if i < 6:
                open_p = 100.0 + i * 0.01
                close_p = open_p + 0.02
                high_p = close_p + 0.01
                low_p = open_p - 0.01
                vol = 10_000_000
            else:
                open_p = close_p
                close_p = open_p
                high_p = open_p
                low_p = open_p
                vol = 1_000_000
            records.append({"datetime": g, "open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": vol})
        df = pd.DataFrame(records).set_index("datetime")
        df.index = pd.to_datetime(df.index, utc=True)
        sessions, _ = normalize_to_sessions(df, "RECLAIM")
        sess = sessions[0]
        compute_session_vwap(sess)
        # 9:55 bar is index 5; candidate window begins at index 6 (10:00).
        window_starts = [g.astimezone(ZoneInfo("America/New_York")).time() for g in _grid_in_window(sess, spec.reclaim_search_start_time, spec.reclaim_search_end_time)]
        assert time(9, 55) not in window_starts

    def test_baseline_a_includes_955_bar(self, spec):
        session = _session_grid_2025_01_02()
        grid = sorted(session.grid)
        records = []
        for i, g in enumerate(grid):
            if i < 6:
                open_p = 100.0
                close_p = 100.1
                high_p = close_p
                low_p = open_p
                vol = 10_000_000
            else:
                open_p = close_p
                close_p = open_p
                high_p = open_p
                low_p = open_p
                vol = 1_000_000
            records.append({"datetime": g, "open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": vol})
        df = pd.DataFrame(records).set_index("datetime")
        df.index = pd.to_datetime(df.index, utc=True)
        sessions, _ = normalize_to_sessions(df, "BASELINE-A")
        sess = sessions[0]
        window = _baseline_a_search_window(sess, spec)
        # The 9:55 bar completes at 10:00 and should be present.
        assert any(g == grid[5] for g in window)


class TestExecutionPriorities:
    def _make_trade(
        self,
        spec,
        primary_cost,
        signal_bar_index: int = 12,
        entry_values: dict | None = None,
        second_bar_values: dict | None = None,
    ):
        ti = _single_session_input(spec, reclaim=False)
        session = ti.sessions[0]
        compute_session_vwap(session)
        grid = sorted(session.grid)
        signal_grid = grid[signal_bar_index]
        signal_bar = session.bars[signal_grid]
        vwap = signal_bar.vwap
        signal_bar.low = vwap * 0.99
        signal_bar.close = max(vwap * 1.01, signal_bar.open * 1.001)
        signal_bar.high = max(signal_bar.open, signal_bar.close) * 1.001
        stop = signal_bar.low - max(0.01, signal_bar.close * 0.0005)
        next_grid = grid[signal_bar_index + 1]
        next_bar = session.bars[next_grid]
        if entry_values:
            for k, v in entry_values.items():
                setattr(next_bar, k, v)
        if second_bar_values and signal_bar_index + 2 < len(grid):
            second_grid = grid[signal_bar_index + 2]
            second_bar = session.bars[second_grid]
            for k, v in second_bar_values.items():
                setattr(second_bar, k, v)
        return attempt_trade(
            ti.ticker, ti.meta, session, signal_bar, stop, True, None, primary_cost, spec, "candidate"
        )

    def test_gap_stop_exit(self, spec, primary_cost):
        sig = self._make_trade(
            spec,
            primary_cost,
            entry_values={"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.1},
            second_bar_values={"open": 90.0, "high": 95.0, "low": 89.0, "close": 89.5},
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "gap_stop"
        assert sig.trade.exit_time == sig.trade.exit_bar_start

    def test_gap_target_exit(self, spec, primary_cost):
        ti = _single_session_input(spec, reclaim=False)
        session = ti.sessions[0]
        compute_session_vwap(session)
        grid = sorted(session.grid)
        signal_bar = session.bars[grid[12]]
        vwap = signal_bar.vwap
        signal_bar.low = vwap * 0.99
        signal_bar.close = max(vwap * 1.01, signal_bar.open * 1.001)
        signal_bar.high = max(signal_bar.open, signal_bar.close) * 1.001
        # Stop just below signal close so target is close to entry.
        stop = signal_bar.close * 0.99
        next_bar = session.bars[grid[13]]
        next_bar.open = signal_bar.close
        next_bar.low = next_bar.open * 0.999
        next_bar.high = next_bar.open * 1.001
        next_bar.close = next_bar.open
        # Second bar gaps above target.
        second_bar = session.bars[grid[14]]
        entry_fill = next_bar.open * 1.0005
        risk = entry_fill - stop
        target = entry_fill + 1.5 * risk
        second_bar.open = target * 1.02
        second_bar.high = second_bar.open * 1.01
        second_bar.low = second_bar.open * 0.99
        second_bar.close = second_bar.open
        sig = attempt_trade(
            ti.ticker, ti.meta, session, signal_bar, stop, True, None, primary_cost, spec, "candidate"
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "gap_target"

    def test_intrabar_stop(self, spec, primary_cost):
        sig = self._make_trade(
            spec,
            primary_cost,
            entry_values={"open": 100.0, "high": 100.5, "low": 95.0, "close": 96.0},
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "stop"

    def test_intrabar_target(self, spec, primary_cost):
        sig = self._make_trade(
            spec,
            primary_cost,
            entry_values={"open": 100.0, "high": 106.0, "low": 99.5, "close": 105.0},
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "target"

    def test_same_bar_ambiguity_stop_first(self, spec, primary_cost):
        sig = self._make_trade(
            spec,
            primary_cost,
            entry_values={"open": 100.0, "high": 106.0, "low": 95.0, "close": 100.5},
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "stop"
        assert sig.trade.same_bar_ambiguity is True

    def test_time_exit(self, spec, primary_cost):
        # Signal at 15:35; entry bar (15:40) is the time-exit bar.
        sig = self._make_trade(
            spec,
            primary_cost,
            signal_bar_index=73,
            entry_values={"open": 100.0, "high": 100.2, "low": 99.9, "close": 100.2},
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "time"

    def test_entry_rejected_when_next_bar_open_at_or_below_stop(self, spec, primary_cost):
        sig = self._make_trade(
            spec,
            primary_cost,
            entry_values={"open": 90.0, "high": 95.0, "low": 89.0, "close": 89.5},
        )
        assert sig.status == "rejected_entry_at_or_below_stop"

    def test_missing_next_bar_rejection(self, spec, primary_cost):
        ti = _single_session_input(spec, reclaim=False)
        session = ti.sessions[0]
        compute_session_vwap(session)
        grid = sorted(session.grid)
        signal_bar = session.bars[grid[12]]
        vwap = signal_bar.vwap
        signal_bar.low = vwap * 0.99
        signal_bar.close = max(vwap * 1.01, signal_bar.open * 1.001)
        signal_bar.high = max(signal_bar.open, signal_bar.close) * 1.001
        stop = signal_bar.low - max(0.01, signal_bar.close * 0.0005)
        del session.bars[grid[13]]
        sig = attempt_trade(
            ti.ticker, ti.meta, session, signal_bar, stop, True, None, primary_cost, spec, "candidate"
        )
        assert sig.status == "rejected_no_next_bar"

    def test_missing_time_exit_bar_fallback(self, spec, primary_cost):
        ti = _single_session_input(spec, reclaim=False)
        session = ti.sessions[0]
        compute_session_vwap(session)
        grid = sorted(session.grid)
        signal_bar = session.bars[grid[72]]
        vwap = signal_bar.vwap
        signal_bar.low = vwap * 0.99
        signal_bar.close = max(vwap * 1.01, signal_bar.open * 1.001)
        signal_bar.high = max(signal_bar.open, signal_bar.close) * 1.001
        stop = signal_bar.low - max(0.01, signal_bar.close * 0.0005)
        # Entry bar 15:35 exists; remove 15:40 time-exit bar.
        del session.bars[grid[74]]
        sig = attempt_trade(
            ti.ticker, ti.meta, session, signal_bar, stop, True, None, primary_cost, spec, "candidate"
        )
        assert sig.status == "executed"
        assert sig.trade.exit_type == "time_fallback"
        assert sig.trade.fallback_reason == "missing_time_exit_bar_fallback"


class TestCostsAndMetrics:
    def test_all_cost_scenarios_present(self, spec):
        inputs = generate_synthetic_inputs(spec, seed=42, n_stock_tickers=2, n_etf_tickers=1, n_sessions=30)
        result = run_study(inputs, spec)
        for strategy in ("candidate", "baseline_a", "baseline_b"):
            assert strategy in result.metrics_by_strategy
            for cost_name in ("primary_5bps", "slippage_0bps", "slippage_2.5bps", "slippage_5bps", "slippage_10bps"):
                assert cost_name in result.metrics_by_strategy[strategy]

    def test_metrics_include_signal_and_exit_counts(self, spec):
        inputs = generate_synthetic_inputs(spec, seed=42, n_stock_tickers=2, n_etf_tickers=1, n_sessions=30)
        result = run_study(inputs, spec)
        cand = result.metrics_by_strategy["candidate"]["primary_5bps"]
        assert cand.total_signals >= cand.executed_trades + cand.no_signal_count + cand.rejected_signals
        assert isinstance(cand.exit_counts, dict)
        assert cand.positive_trade_rate is None or 0.0 <= cand.positive_trade_rate <= 1.0


class TestGatesAndOutcomes:
    def _minimal_metrics(
        self,
        total_trades: int = 0,
        pooled_expectancy: float = 0.0,
        per_symbol_mean: float = 0.1,
        per_symbol: dict | None = None,
    ):
        cost = CostScenario("primary", 5.0, 5.0, 0.0, 0.0)
        if per_symbol is None and total_trades > 0:
            per_symbol = {
                f"T{i:03d}": PerSymbolMetrics(
                    ticker=f"T{i:03d}",
                    is_etf=False,
                    trade_count=max(1, total_trades // 20),
                    total_return=per_symbol_mean,
                    mean_expectancy=per_symbol_mean,
                    gross_profit=per_symbol_mean if per_symbol_mean > 0 else 0.0,
                    gross_loss=0.0 if per_symbol_mean > 0 else abs(per_symbol_mean),
                    profit_factor_value=(float("inf") if per_symbol_mean > 0 else 0.0),
                    profit_factor_case=("no_loss_positive" if per_symbol_mean > 0 else "no_profit"),
                    profit_factor_order=(float("inf") if per_symbol_mean > 0 else 0.0),
                    maximum_drawdown_pct=-1.0,
                    equity_curve=[100.0, 100.0 + per_symbol_mean],
                    positive=per_symbol_mean > 0,
                )
                for i in range(20)
            }
        elif per_symbol is None:
            per_symbol = {}
        return StudyMetrics(
            strategy="candidate",
            cost_scenario=cost,
            total_signals=total_trades,
            executed_trades=total_trades,
            rejected_signals=0,
            no_signal_count=0,
            total_trades=total_trades,
            pooled_expectancy=pooled_expectancy,
            pooled_total_return=pooled_expectancy * total_trades,
            overall_maximum_drawdown_pct=0.0,
            median_per_symbol_expectancy=per_symbol_mean if total_trades else None,
            equal_weighted_per_symbol_mean_expectancy=per_symbol_mean if total_trades else None,
            positive_symbol_rate=(1.0 if per_symbol_mean > 0 else 0.0) if total_trades else None,
            median_per_symbol_total_return=per_symbol_mean if total_trades else None,
            median_per_symbol_maximum_drawdown_pct=-1.0 if total_trades else None,
            median_per_symbol_profit_factor_order=1.1 if total_trades else None,
            median_per_symbol_profit_factor_value=1.1 if total_trades else None,
            trade_count_concentration=0.05,
            net_profit_concentration=None,
            absolute_loss_concentration=None,
            stock_stratum_trade_count=total_trades,
            etf_stratum_trade_count=total_trades,
            stock_stratum_pooled_expectancy=0.0,
            etf_stratum_pooled_expectancy=0.0,
            represented_stock_symbols=max(1, total_trades),
            represented_etf_symbols=max(1, total_trades),
            per_symbol=per_symbol,
        )

    def test_sample_minimums_inconclusive(self):
        outcome = evaluate_gates(
            self._minimal_metrics(total_trades=0),
            self._minimal_metrics(total_trades=0),
            self._minimal_metrics(total_trades=0),
            self._minimal_metrics(total_trades=0),
            sample_minimums=SampleMinimums(),
        )
        assert outcome.disposition == "inconclusive"

    def test_contract_invalid(self):
        metrics = self._minimal_metrics(total_trades=400, pooled_expectancy=0.1)
        outcome = evaluate_gates(
            metrics, metrics, metrics, metrics,
            sample_minimums=SampleMinimums(),
            data_contract_valid=False,
            contract_reasons=["non_finite_rows"],
        )
        assert outcome.disposition == "invalid"

    def test_supported_and_not_supported(self):
        good_candidate = self._minimal_metrics(total_trades=400, pooled_expectancy=0.1, per_symbol_mean=0.2)
        good_baseline = self._minimal_metrics(total_trades=400, pooled_expectancy=0.1, per_symbol_mean=0.1)
        outcome = evaluate_gates(
            good_candidate,
            good_baseline,
            good_baseline,
            good_candidate,
            sample_minimums=SampleMinimums(),
        )
        assert outcome.disposition == "supported"

        bad = self._minimal_metrics(total_trades=400, pooled_expectancy=-0.1, per_symbol_mean=-0.05)
        outcome = evaluate_gates(
            bad,
            good_baseline,
            good_baseline,
            good_candidate,
            sample_minimums=SampleMinimums(),
        )
        assert outcome.disposition == "not_supported"


class TestDataContractAndSufficiency:
    def test_non_finite_value_detected(self):
        session = _session_grid_2025_01_02()
        df = _make_session_df(session)
        # Inject a non-finite close.
        df.iloc[10, df.columns.get_loc("close")] = float("inf")
        _, summary = normalize_to_sessions(df, "NONFINITE")
        assert summary.non_finite_rows == 1
        valid, _ = evaluate_data_contract(summary)
        assert valid is False

    def test_invalid_ohlc_detected(self):
        session = _session_grid_2025_01_02()
        df = _make_session_df(session)
        df.iloc[10, df.columns.get_loc("high")] = df.iloc[10, df.columns.get_loc("low")] - 1.0
        _, summary = normalize_to_sessions(df, "OHLC")
        assert summary.invalid_ohlc_rows >= 1
        valid, _ = evaluate_data_contract(summary)
        assert valid is False

    def test_missing_bar_rate_threshold(self):
        summary = DataQualitySummary(
            ticker="TEST",
            total_rows=80,
            duplicate_timestamps=0,
            naive_timestamps=0,
            off_grid_bars=0,
            invalid_ohlc_rows=0,
            non_finite_rows=0,
            zero_volume_bars=0,
            missing_bars=5,
            valid_bars=73,
            sessions=1,
        )
        passed, reasons = evaluate_data_sufficiency(summary, expected_bars_per_session=78)
        # 5/78 = 6.4% > 5%
        assert passed is False
        assert "missing" in reasons[0]

    def test_duplicate_rate_threshold(self):
        summary = DataQualitySummary(
            ticker="TEST",
            total_rows=100,
            duplicate_timestamps=2,
            naive_timestamps=0,
            off_grid_bars=0,
            invalid_ohlc_rows=0,
            non_finite_rows=0,
            zero_volume_bars=0,
            missing_bars=0,
            valid_bars=98,
            sessions=1,
        )
        passed, reasons = evaluate_data_sufficiency(summary)
        # 2/100 = 2% > 1%
        assert passed is False
        assert "duplicate" in reasons[0]


class TestDeterminism:
    def test_synthetic_result_identical_for_fixed_generation_time(self, spec, tmp_path):
        inputs = generate_synthetic_inputs(spec, seed=42, n_stock_tickers=2, n_etf_tickers=1, n_sessions=20)
        from datetime import UTC, datetime

        from tradex.research.intraday_engine.models import as_json_dict
        fixed = datetime(2025, 1, 1, tzinfo=UTC)
        r1 = run_study(inputs, spec, generated_at=fixed)
        r2 = run_study(inputs, spec, generated_at=fixed)
        j1 = json.dumps(as_json_dict(r1), indent=2, sort_keys=True)
        j2 = json.dumps(as_json_dict(r2), indent=2, sort_keys=True)
        assert j1 == j2
