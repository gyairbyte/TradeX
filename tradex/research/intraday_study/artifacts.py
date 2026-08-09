"""Write safe, reproducible INTRA-001D artifact bundles."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tradex.research.intraday_engine.models import (
    CostScenario,
    PerSymbolMetrics,
    Signal,
    StudyMetrics,
    StudyResult,
    as_json_dict,
)

from .freeze import FreezeRecord


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("\n")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            clean = {k: _iso_or_none(v) for k, v in row.items()}
            writer.writerow(clean)


def _study_metrics_to_row(metrics: StudyMetrics) -> dict[str, Any]:
    """Flatten a StudyMetrics object into a CSV row."""
    d = asdict(metrics)
    # Remove nested per-symbol dict.
    d.pop("per_symbol", None)
    # Flatten cost_scenario.
    cost = d.pop("cost_scenario", None)
    if isinstance(cost, CostScenario):
        d["cost_scenario_name"] = cost.name
        d["entry_slippage_bps"] = cost.entry_slippage_bps
        d["exit_slippage_bps"] = cost.exit_slippage_bps
        d["entry_commission_bps"] = cost.entry_commission_bps
        d["exit_commission_bps"] = cost.exit_commission_bps
    else:
        d["cost_scenario_name"] = None
    return d


def _signal_to_row(signal: Signal, include_trade: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {
        "ticker": signal.ticker,
        "session_date": signal.session_date,
        "strategy": signal.strategy,
        "signal_bar_start": signal.signal_bar_start,
        "signal_time": signal.signal_time,
        "opening_drive_qualified": signal.opening_drive_qualified,
        "score": signal.score,
        "stop_price": signal.stop_price,
        "target_price": signal.target_price,
        "entry_open": signal.entry_open,
        "entry_fill": signal.entry_fill,
        "risk_per_share": signal.risk_per_share,
        "status": signal.status,
        "reason": signal.reason,
        "executed": signal.trade is not None,
        "entry_time": None,
        "entry_bar_start": None,
        "exit_time": None,
        "exit_bar_start": None,
        "raw_exit_price": None,
        "exit_fill": None,
        "profit": None,
        "net_r": None,
        "exit_type": None,
        "holding_minutes": None,
        "opening_gap_pct": None,
        "fallback_reason": None,
        "same_bar_ambiguity": None,
    }
    if include_trade and signal.trade is not None:
        t = signal.trade
        d["entry_time"] = t.entry_time
        d["entry_bar_start"] = t.entry_bar_start
        d["exit_time"] = t.exit_time
        d["exit_bar_start"] = t.exit_bar_start
        d["raw_exit_price"] = t.raw_exit_price
        d["exit_fill"] = t.exit_fill
        d["profit"] = t.profit
        d["net_r"] = t.net_r
        d["exit_type"] = t.exit_type
        d["holding_minutes"] = t.holding_minutes
        d["opening_gap_pct"] = t.opening_gap_pct
        d["fallback_reason"] = t.fallback_reason
        d["same_bar_ambiguity"] = t.same_bar_ambiguity
    return d


def _trade_to_row(trade: Any, strategy: str) -> dict[str, Any]:
    return {
        "ticker": trade.ticker,
        "session_date": trade.session_date,
        "strategy": strategy,
        "signal_time": trade.signal_time,
        "signal_bar_start": trade.signal_bar_start,
        "entry_time": trade.entry_time,
        "entry_bar_start": trade.entry_bar_start,
        "entry_open": trade.entry_open,
        "entry_fill": trade.entry_fill,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "risk_per_share": trade.risk_per_share,
        "exit_time": trade.exit_time,
        "exit_bar_start": trade.exit_bar_start,
        "raw_exit_price": trade.raw_exit_price,
        "exit_fill": trade.exit_fill,
        "profit": trade.profit,
        "net_r": trade.net_r,
        "exit_type": trade.exit_type,
        "holding_minutes": trade.holding_minutes,
        "opening_gap_pct": trade.opening_gap_pct,
        "fallback_reason": trade.fallback_reason,
        "same_bar_ambiguity": trade.same_bar_ambiguity,
        "entry_bar_index": trade.entry_bar_index,
        "exit_bar_index": trade.exit_bar_index,
        "status": trade.status,
        "rejection_reason": trade.rejection_reason,
    }


def _per_symbol_to_row(ticker: str, metrics: PerSymbolMetrics) -> dict[str, Any]:
    d = asdict(metrics)
    d.pop("equity_curve", None)
    d["ticker"] = ticker
    return d


def write_signals_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for signals in [result.candidate_signals, result.baseline_a_signals, result.baseline_b_signals]:
        for s in signals:
            rows.append(_signal_to_row(s, include_trade=True))
    _write_csv(path, rows)


def write_trades_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for strategy, trades in result.trades.items():
        for t in trades:
            rows.append(_trade_to_row(t, strategy))
    _write_csv(path, rows)


def write_candidate_metrics_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for name, metrics in result.metrics_by_strategy["candidate"].items():
        row = _study_metrics_to_row(metrics)
        row["cost_scenario_name"] = name
        rows.append(row)
    _write_csv(path, rows)


def write_baseline_metrics_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for strategy in ["baseline_a", "baseline_b"]:
        for name, metrics in result.metrics_by_strategy[strategy].items():
            row = _study_metrics_to_row(metrics)
            row["cost_scenario_name"] = name
            row["baseline"] = strategy
            rows.append(row)
    _write_csv(path, rows)


def write_cost_sensitivity_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for strategy in ["candidate", "baseline_a", "baseline_b"]:
        for name, metrics in result.metrics_by_strategy[strategy].items():
            row = _study_metrics_to_row(metrics)
            row["strategy"] = strategy
            row["cost_scenario_name"] = name
            rows.append(row)
    _write_csv(path, rows)


def write_ticker_comparison_csv(result: StudyResult, path: Path) -> None:
    candidate = result.metrics_by_strategy["candidate"]["primary_5bps"].per_symbol
    baseline_a = result.metrics_by_strategy["baseline_a"]["primary_5bps"].per_symbol
    baseline_b = result.metrics_by_strategy["baseline_b"]["primary_5bps"].per_symbol
    rows: list[dict[str, Any]] = []
    for ticker, cand in candidate.items():
        a = baseline_a.get(ticker)
        b = baseline_b.get(ticker)
        rows.append({
            "ticker": ticker,
            "is_etf": cand.is_etf,
            "candidate_trade_count": cand.trade_count,
            "candidate_total_return": cand.total_return,
            "candidate_mean_expectancy": cand.mean_expectancy,
            "candidate_maximum_drawdown_pct": cand.maximum_drawdown_pct,
            "baseline_a_trade_count": a.trade_count if a else None,
            "baseline_a_mean_expectancy": a.mean_expectancy if a else None,
            "baseline_b_trade_count": b.trade_count if b else None,
            "baseline_b_mean_expectancy": b.mean_expectancy if b else None,
            "candidate_beat_a": (cand.mean_expectancy > a.mean_expectancy) if a else None,
            "candidate_beat_b": (cand.mean_expectancy > b.mean_expectancy) if b else None,
        })
    _write_csv(path, rows)


def write_monthly_comparison_csv(result: StudyResult, path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for key, metrics in result.monthly_metrics.items():
        strategy, month = key.split(":", 1)
        row = _study_metrics_to_row(metrics)
        row["strategy"] = strategy
        row["month"] = month
        rows.append(row)
    _write_csv(path, rows)


def write_session_features_csv(result: StudyResult, path: Path) -> None:
    """Write a session-level feature/signal-status summary."""
    rows: list[dict[str, Any]] = []
    # Build lookup by ticker/session_date/strategy -> signal.
    signal_map: dict[tuple[str, Any, str], Signal] = {}
    for s in result.candidate_signals + result.baseline_a_signals + result.baseline_b_signals:
        signal_map[(s.ticker, s.session_date, s.strategy)] = s

    # Collect all evaluation sessions from result signals.
    sessions: set[tuple[str, Any]] = set()
    for s in result.candidate_signals + result.baseline_a_signals + result.baseline_b_signals:
        sessions.add((s.ticker, s.session_date))

    for (ticker, session_date) in sorted(sessions):
        cand = signal_map.get((ticker, session_date, "candidate"))
        a = signal_map.get((ticker, session_date, "baseline_a"))
        b = signal_map.get((ticker, session_date, "baseline_b"))
        rows.append({
            "ticker": ticker,
            "session_date": session_date,
            "candidate_status": cand.status if cand else "no_signal",
            "candidate_reason": cand.reason if cand else None,
            "candidate_opening_drive_qualified": cand.opening_drive_qualified if cand else None,
            "baseline_a_status": a.status if a else "no_signal",
            "baseline_a_score": a.score if a else None,
            "baseline_b_status": b.status if b else "no_signal",
        })
    _write_csv(path, rows)


def write_study_json(
    result: StudyResult,
    path: Path,
    *,
    split: str,
    dataset_id: str,
    freeze_record: FreezeRecord | None = None,
    manifest_sha256: str | None = None,
    manifest_lock_path: Path | None = None,
) -> None:
    """Write a JSON summary of the study outcome and metrics."""
    cost_rows: dict[str, dict[str, Any]] = {}
    for key, metrics in result.cost_scenarios.items():
        cost_rows[key] = _study_metrics_to_row(metrics)

    monthly_rows: dict[str, dict[str, Any]] = {}
    for key, metrics in result.monthly_metrics.items():
        monthly_rows[key] = _study_metrics_to_row(metrics)

    gap_rows: dict[str, dict[str, Any]] = {}
    for key, metrics in result.gap_bucket_metrics.items():
        gap_rows[key] = _study_metrics_to_row(metrics)

    data: dict[str, Any] = {
        "schema_version": "1.0",
        "study_id": "INTRA-001D",
        "dataset_id": dataset_id,
        "split": split,
        "spec_sha256": result.spec_sha256,
        "engine_version": result.engine_version,
        "synthetic": result.synthetic,
        "evidence_eligible": result.evidence_eligible,
        "generated_at": result.generated_at.isoformat(),
        "generated_at_fixed": result.generated_at_fixed,
        "disposition": result.outcome.disposition if result.outcome else None,
        "outcome_reason": result.outcome.reason if result.outcome else None,
        "gate_results": as_json_dict(result.outcome.gate_results) if result.outcome else [],
        "sample_met": result.outcome.sample_met if result.outcome else None,
        "cost_scenarios": cost_rows,
        "monthly_metrics": monthly_rows,
        "gap_bucket_metrics": gap_rows,
        "data_quality_summaries": as_json_dict(result.data_quality_summaries),
        "invalid_reasons": result.invalid_reasons,
    }
    if freeze_record is not None:
        data["freeze"] = {
            "evaluation_code_sha": freeze_record.evaluation_code_sha,
            "repository_clean": freeze_record.repository_clean,
            "frozen_at": freeze_record.frozen_at.isoformat(),
        }
    if manifest_sha256:
        data["manifest_sha256"] = manifest_sha256
    if manifest_lock_path:
        data["manifest_lock_path"] = str(manifest_lock_path)

    path.write_text(json.dumps(as_json_dict(data), indent=2), encoding="utf-8")


def _copy_locked_file(src: Path, dst: Path) -> None:
    if src and src.is_file():
        shutil.copy2(src, dst)


def write_artifact_bundle(
    result: StudyResult,
    output_dir: Path,
    *,
    split: str,
    dataset_id: str,
    freeze_record: FreezeRecord | None = None,
    manifest_lock_path: Path | None = None,
    universe_manifest_path: Path | None = None,
    data_quality_path: Path | None = None,
    spec_path: Path | None = None,
) -> dict[str, Path]:
    """Write the full safe artifact bundle for one split."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    study_json = output_dir / "study.json"
    manifest_sha = sha256_of_file(manifest_lock_path) if manifest_lock_path else None
    write_study_json(
        result,
        study_json,
        split=split,
        dataset_id=dataset_id,
        freeze_record=freeze_record,
        manifest_sha256=manifest_sha,
        manifest_lock_path=manifest_lock_path,
    )
    written["study.json"] = study_json

    report_md = output_dir / "report.md"
    report_md.write_text(result.report_markdown, encoding="utf-8")
    written["report.md"] = report_md

    if spec_path:
        dst = output_dir / "spec.lock.json"
        shutil.copy2(spec_path, dst)
        written["spec.lock.json"] = dst

    if manifest_lock_path:
        dst = output_dir / "manifest.lock.json"
        shutil.copy2(manifest_lock_path, dst)
        written["manifest.lock.json"] = dst

    if universe_manifest_path:
        dst = output_dir / "universe_manifest.csv"
        shutil.copy2(universe_manifest_path, dst)
        written["universe_manifest.csv"] = dst

    if data_quality_path:
        dst = output_dir / "data_quality.csv"
        shutil.copy2(data_quality_path, dst)
        written["data_quality.csv"] = dst

    for name, func in [
        ("session_features.csv", write_session_features_csv),
        ("signals.csv", write_signals_csv),
        ("trades.csv", write_trades_csv),
        ("candidate_metrics.csv", write_candidate_metrics_csv),
        ("baseline_metrics.csv", write_baseline_metrics_csv),
        ("ticker_comparison.csv", write_ticker_comparison_csv),
        ("monthly_comparison.csv", write_monthly_comparison_csv),
        ("cost_sensitivity.csv", write_cost_sensitivity_csv),
    ]:
        path = output_dir / name
        func(result, path)
        written[name] = path

    _write_artifact_manifest(output_dir)
    _write_checksums(output_dir)
    return written


def _write_artifact_manifest(output_dir: Path) -> None:
    manifest: dict[str, str] = {}
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.name not in {"artifact_manifest.json", "checksums.sha256"}:
            manifest[p.name] = sha256_of_file(p)
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "files": manifest}, indent=2),
        encoding="utf-8",
    )


def _write_checksums(output_dir: Path) -> None:
    lines: list[str] = []
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.name != "checksums.sha256":
            lines.append(f"{sha256_of_file(p)}  {p.name}")
    (output_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
