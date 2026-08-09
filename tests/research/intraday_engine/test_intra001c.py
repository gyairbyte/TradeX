"""Tests for the INTRA-001C synthetic intraday research engine."""
from __future__ import annotations

import hashlib
import json
from datetime import date
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
from tradex.research.intraday_engine.calendar import build_sessions
from tradex.research.intraday_engine.execution import attempt_trade
from tradex.research.intraday_engine.models import CostScenario, TickerMeta
from tradex.research.intraday_engine.normalize import NormalizationError, normalize_to_sessions
from tradex.research.intraday_engine.opening_drive import evaluate_opening_drive
from tradex.research.intraday_engine.reclaim import find_first_reclaim
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
