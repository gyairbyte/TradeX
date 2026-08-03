"""Short-term context study orchestration, serialization, and reporting."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.score_validation.report import (
    _atomic_publish_dir,
    _fsync_file,
)
from tradex.research.short_context.alignment import load_manifest_and_spec
from tradex.research.short_context.backtest import run_paired_backtests
from tradex.research.short_context.comparison import (
    build_candidate_comparison_df,
    evaluate_holdout,
    select_candidate,
)
from tradex.research.short_context.events import build_event_dataframe, generate_context_events
from tradex.research.short_context.models import (
    CandidateResult,
    ContextStudyResult,
    HoldoutResult,
    PairedBacktestResult,
    PolicySplitMetrics,
    ShortContextSpec,
    sha256_file,
)
from tradex.signals.weights import ShortWeights


def run_study(
    manifest_path: str | Path,
    spec_path: str | Path,
    output_dir: str | Path,
    *,
    config: ScoreValidationConfig | None = None,
    overwrite: bool = False,
) -> ContextStudyResult:
    """Run the full short-term market-context study and write results."""
    if config is None:
        config = ScoreValidationConfig()

    manifest, spec = load_manifest_and_spec(manifest_path, spec_path)
    manifest_sha = getattr(manifest, "_sha256", None)
    if manifest_sha is None:
        manifest_sha = sha256_file(manifest_path)
    spec_bytes = Path(spec_path).read_bytes()
    spec_sha = hashlib.sha256(spec_bytes).hexdigest()

    events, quality_rows = generate_context_events(manifest_path, spec, config)
    events_df = build_event_dataframe(events, spec)
    candidate_comparison = build_candidate_comparison_df(events_df, spec, config)

    candidate_selection = select_candidate(events_df, spec, config)
    selected_policy = candidate_selection.selected_policy

    holdout = evaluate_holdout(events_df, selected_policy, spec, config)

    paired = run_paired_backtests(manifest_path, spec, config, selected_policy)

    ticker_comparison = _build_ticker_comparison(events_df, spec, config, selected_policy)
    data_quality = _build_data_quality(quality_rows)

    weight_snapshot = {
        "short_term": {
            "source": "explicit ShortWeights() default",
            "weights": _short_weights_snapshot(),
        }
    }

    generated_at = manifest.created_at

    report_md = _render_report(
        spec=spec,
        manifest_path=manifest_path,
        manifest_sha=manifest_sha,
        spec_sha=spec_sha,
        weight_snapshot=weight_snapshot,
        events_df=events_df,
        candidate_comparison=candidate_comparison,
        candidate_selection=candidate_selection,
        holdout=holdout,
        paired=paired,
        ticker_comparison=ticker_comparison,
        data_quality=data_quality,
        generated_at=generated_at,
    )

    generated_at = manifest.created_at

    study = ContextStudyResult(
        spec=spec,
        manifest_path=Path(manifest_path).expanduser().resolve(),
        manifest_sha256=manifest_sha,
        context_spec_sha256=spec_sha,
        weight_snapshot=weight_snapshot,
        events=events_df,
        candidate_comparison=candidate_comparison,
        candidate_selection=candidate_selection,
        holdout=holdout,
        paired_backtests=paired,
        ticker_comparison=ticker_comparison,
        data_quality=data_quality,
        report_markdown=report_md,
        generated_at=generated_at,
    )

    write_study(study, output_dir, overwrite=overwrite)
    return study


def write_study(study: ContextStudyResult, output_dir: str | Path, overwrite: bool = False) -> dict[str, Path]:
    """Write all study outputs atomically."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="tradex_short_context_", dir=output_dir.parent))
    try:
        paths = _write_study_files(study, tmp_dir)
        _atomic_publish_dir(tmp_dir, output_dir, overwrite)
        for name in paths:
            paths[name] = output_dir / name
        return paths
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _write_study_files(study: ContextStudyResult, tmp_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["context_events.csv"] = _write_csv(study.events, tmp_dir / "context_events.csv")
    paths["candidate_comparison.csv"] = _write_csv(study.candidate_comparison, tmp_dir / "candidate_comparison.csv")
    paths["holdout_evaluation.csv"] = _write_csv(_holdout_df(study.holdout), tmp_dir / "holdout_evaluation.csv")
    paths["paired_backtests.csv"] = _write_csv(_paired_df(study.paired_backtests), tmp_dir / "paired_backtests.csv")
    paths["ticker_comparison.csv"] = _write_csv(study.ticker_comparison, tmp_dir / "ticker_comparison.csv")
    paths["data_quality.csv"] = _write_csv(study.data_quality, tmp_dir / "data_quality.csv")
    paths["candidate_selection.json"] = _write_json(study.candidate_selection.to_dict(), tmp_dir / "candidate_selection.json")
    paths["manifest.lock.json"] = _write_json(_manifest_lock(study), tmp_dir / "manifest.lock.json")
    paths["context_spec.lock.json"] = _write_json(_spec_lock(study), tmp_dir / "context_spec.lock.json")
    paths["study.json"] = _write_json(study.to_dict(), tmp_dir / "study.json")
    paths["report.md"] = _write_text(study.report_markdown, tmp_dir / "report.md")
    return paths


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.10g")
    _fsync_file(path)
    return path


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False, default=_json_default, sort_keys=True))
    _fsync_file(path)
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _fsync_file(path)
    return path


def _json_default(obj: Any) -> Any:
    from datetime import date

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _manifest_lock(study: ContextStudyResult) -> dict[str, Any]:
    return {
        "manifest_sha256": study.manifest_sha256,
        "context_spec_sha256": study.context_spec_sha256,
        "weight_snapshot": study.weight_snapshot,
    }


def _spec_lock(study: ContextStudyResult) -> dict[str, Any]:
    return {
        "context_spec_sha256": study.context_spec_sha256,
        "context_spec": study.spec.to_dict(),
    }


def _short_weights_snapshot() -> dict[str, int]:
    return {k: int(v) for k, v in ShortWeights().__dict__.items()}


def _build_data_quality(quality_rows: list[Any]) -> pd.DataFrame:
    if not quality_rows:
        return _empty_data_quality_df()
    rows = []
    for q in quality_rows:
        if hasattr(q, "to_dict"):
            rows.append(q.to_dict())
        else:
            rows.append(dict(q))
    df = pd.DataFrame(rows)
    for col in _empty_data_quality_df().columns:
        if col not in df.columns:
            df[col] = None
    return df[_empty_data_quality_df().columns]


def _empty_data_quality_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ticker",
            "data_source",
            "sha256",
            "manifest_rows",
            "validated_rows",
            "data_start",
            "data_end",
            "duplicate_timestamps",
            "missing_required_values",
            "invalid_ohlc_rows",
            "complete_1_bar_outcomes",
            "complete_3_bar_outcomes",
            "complete_5_bar_outcomes",
            "warnings",
        ]
    )


def _holdout_df(holdout: HoldoutResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if holdout.metrics is not None:
        rows.append(_metrics_to_dict(holdout.metrics, "candidate"))
    if holdout.baseline_metrics is not None:
        rows.append(_metrics_to_dict(holdout.baseline_metrics, "baseline"))
    if not rows:
        return _empty_metrics_df()
    df = pd.DataFrame(rows)
    for col in _empty_metrics_df().columns:
        if col not in df.columns:
            df[col] = None
    return df[_empty_metrics_df().columns]


def _paired_df(paired: PairedBacktestResult) -> pd.DataFrame:
    if paired.baseline_metrics.empty and paired.candidate_metrics.empty:
        return _empty_paired_df()
    merged = pd.merge(
        paired.baseline_metrics,
        paired.candidate_metrics,
        on="ticker",
        suffixes=("_baseline", "_candidate"),
        how="outer",
    )
    for col in _empty_paired_df().columns:
        if col not in merged.columns:
            merged[col] = None
    return merged[_empty_paired_df().columns]


def _empty_metrics_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "split", "policy", "event_count", "baseline_event_count", "retention_pct",
        "unique_tickers", "baseline_unique_tickers", "coverage_pct",
        "mean_net_return_pct", "median_net_return_pct", "positive_return_rate_pct",
        "mean_ticker_event_return_pct", "median_ticker_event_return_pct",
    ])


def _empty_paired_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "ticker", "total_trades_baseline", "expectancy_pct_baseline",
        "total_return_pct_baseline", "profit_factor_baseline", "max_drawdown_pct_baseline",
        "sharpe_ratio_baseline", "total_trades_candidate", "expectancy_pct_candidate",
        "total_return_pct_candidate", "profit_factor_candidate", "max_drawdown_pct_candidate",
        "sharpe_ratio_candidate",
    ])


def _metrics_to_dict(m: PolicySplitMetrics, label: str) -> dict[str, Any]:
    d = _comparison_metrics_to_dict(m)
    d["label"] = label
    return d


def _comparison_metrics_to_dict(m: PolicySplitMetrics) -> dict[str, Any]:
    return {
        "split": m.split,
        "policy": m.policy,
        "event_count": m.event_count,
        "baseline_event_count": m.baseline_event_count,
        "retention_pct": m.retention_pct,
        "unique_tickers": m.unique_tickers,
        "baseline_unique_tickers": m.baseline_unique_tickers,
        "coverage_pct": m.coverage_pct,
        "mean_net_return_pct": m.mean_net_return_pct,
        "median_net_return_pct": m.median_net_return_pct,
        "positive_return_rate_pct": m.positive_return_rate_pct,
        "mean_ticker_event_return_pct": m.mean_ticker_event_return_pct,
        "median_ticker_event_return_pct": m.median_ticker_event_return_pct,
    }


def _build_ticker_comparison(
    events_df: pd.DataFrame,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    selected_policy: str | None,
) -> pd.DataFrame:
    """Return per-ticker holdout event-study comparison for selected candidate."""
    if events_df.empty or selected_policy is None:
        return _empty_ticker_comparison_df()

    from tradex.research.short_context.comparison import (
        _eligible_mask,
        _net_return_col,
        _policy_from_string,
    )

    holdout_df = events_df[events_df["split"] == "holdout"]
    if holdout_df.empty:
        return _empty_ticker_comparison_df()

    policy = _policy_from_string(selected_policy)
    col = _net_return_col(spec, config)
    rows: list[dict[str, Any]] = []
    for ticker in sorted(holdout_df["ticker"].unique()):
        ticker_df = holdout_df[holdout_df["ticker"] == ticker]
        baseline_df = ticker_df[ticker_df["baseline_qualifies"]]
        candidate_df = ticker_df[_eligible_mask(ticker_df, policy)]

        baseline_vals = pd.to_numeric(baseline_df[col], errors="coerce").dropna()
        candidate_vals = pd.to_numeric(candidate_df[col], errors="coerce").dropna()

        baseline_mean = float(baseline_vals.mean()) if not baseline_vals.empty else None
        candidate_mean = float(candidate_vals.mean()) if not candidate_vals.empty else None
        improved = (
            candidate_mean is not None
            and baseline_mean is not None
            and candidate_mean >= baseline_mean
        )

        rows.append({
            "ticker": ticker,
            "baseline_event_count": len(baseline_df),
            "candidate_event_count": len(candidate_df),
            "baseline_mean_net_return_pct": baseline_mean,
            "candidate_mean_net_return_pct": candidate_mean,
            "candidate_improved": improved,
        })

    if not rows:
        return _empty_ticker_comparison_df()
    df = pd.DataFrame(rows)
    for col_name in _empty_ticker_comparison_df().columns:
        if col_name not in df.columns:
            df[col_name] = None
    return df[_empty_ticker_comparison_df().columns]


def _empty_ticker_comparison_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "ticker", "baseline_event_count", "candidate_event_count",
        "baseline_mean_net_return_pct", "candidate_mean_net_return_pct", "candidate_improved",
    ])


def _render_report(
    spec: ShortContextSpec,
    manifest_path: Any,
    manifest_sha: str | None,
    spec_sha: str,
    weight_snapshot: dict[str, Any],
    events_df: pd.DataFrame,
    candidate_comparison: pd.DataFrame,
    candidate_selection: CandidateResult,
    holdout: HoldoutResult,
    paired: PairedBacktestResult,
    ticker_comparison: pd.DataFrame,
    data_quality: pd.DataFrame,
    generated_at: datetime,
) -> str:
    """Build the Markdown report."""
    lines: list[str] = []
    lines.append("# Short-Term Market Context Study")
    lines.append("")
    lines.append("## 1. Study identity")
    lines.append(f"- Study: {spec.study_name}")
    lines.append(f"- Manifest: {manifest_path}")
    lines.append(f"- Generated: {generated_at.isoformat()}")
    lines.append("")

    lines.append("## 2. Dataset provenance")
    lines.append("The study used manifest-locked offline OHLCV snapshots. Every input CSV was verified by SHA-256 before analysis.")
    lines.append("")

    lines.append("## 3. Manifest checksum")
    if manifest_sha:
        lines.append(f"- Manifest SHA-256: `{manifest_sha}`")
    lines.append("")

    lines.append("## 4. Context-spec checksum")
    lines.append(f"- Context-spec SHA-256: `{spec_sha}`")
    lines.append("")

    lines.append("## 5. Target universe")
    lines.append(f"- Targets: {', '.join(spec.target_tickers)}")
    lines.append(f"- Target count: {len(spec.target_tickers)}")
    lines.append("")

    lines.append("## 6. Proxy mappings")
    for t in spec.target_tickers:
        ctx = spec.ticker_context[t]
        sector = ctx.get("sector_proxy") or "(none)"
        lines.append(f"- {t}: market={ctx['market_proxy']}, sector={sector}")
    lines.append("")

    lines.append("## 7. Existing baseline score")
    lines.append("The existing short-term component score and weights were not changed.")
    lines.append(f"- Baseline score threshold: {spec.baseline_score_threshold}")
    lines.append(f"- Weight snapshot: {json.dumps(weight_snapshot, indent=2)}")
    lines.append("")

    lines.append("## 8. Context formulas")
    lines.append("- Bullish market regime: close > EMA20, EMA20 > EMA50, EMA20 today > EMA20 five bars earlier.")
    lines.append("- Bullish sector regime: same rule on the sector proxy.")
    lines.append("- Market relative strength: ticker_close / market_close; positive when ratio > EMA20(ratio) and 20-bar change > 0.")
    lines.append("- Sector relative strength: ticker_close / sector_close; same rule.")
    lines.append("")

    lines.append("## 9. Point-in-time alignment")
    lines.append("- Context is computed from the most recent market/sector bar <= signal time.")
    lines.append("- Context is rejected as stale when it is more than one expected trading session behind.")
    lines.append("- Future market, sector, or ticker rows cannot influence an earlier context.")
    lines.append("")

    lines.append("## 10. Candidate policies")
    lines.append(f"- Candidate policies: {[p.value for p in spec.candidate_policies]}")
    lines.append("")

    section_number = 11
    for split in ("development", "validation"):
        lines.append(f"## {section_number}. {split.capitalize()} results")
        section_number += 1
        split_df = candidate_comparison[candidate_comparison["split"] == split]
        if split_df.empty:
            lines.append(f"No {split} results available.")
        else:
            lines.append(_df_to_md(split_df))
        lines.append("")

    lines.append(f"## {section_number}. Candidate selection")
    section_number += 1
    lines.append(f"- Selected policy: {candidate_selection.selected_policy or 'none'}")
    lines.append(f"- Selection reason: {candidate_selection.selection_reason}")
    lines.append("")

    lines.append(f"## {section_number}. Holdout event-study results")
    section_number += 1
    if holdout.metrics is None:
        lines.append("No holdout evaluation performed.")
    else:
        lines.append(_df_to_md(_holdout_df(holdout)))
    if holdout.failure_reasons:
        lines.append("Failed criteria:")
        for reason in holdout.failure_reasons:
            lines.append(f"- {reason}")
    lines.append("")

    lines.append(f"## {section_number}. Holdout paired-backtest results")
    section_number += 1
    paired_df = _paired_df(paired)
    if paired_df.empty:
        lines.append("No paired backtests available.")
    else:
        lines.append(_df_to_md(paired_df))
    if paired.failure_reasons:
        lines.append("Failed executable-backtest criteria:")
        for reason in paired.failure_reasons:
            lines.append(f"- {reason}")
    lines.append("")

    lines.append(f"## {section_number}. Event retention")
    section_number += 1
    if holdout.metrics is not None:
        lines.append(f"- Candidate retention: {holdout.metrics.retention_pct:.2f}%")
    lines.append("")

    lines.append(f"## {section_number}. Ticker coverage")
    section_number += 1
    if holdout.metrics is not None:
        lines.append(f"- Candidate coverage: {holdout.metrics.coverage_pct:.2f}%")
    lines.append("")

    lines.append(f"## {section_number}. Per-ticker robustness")
    section_number += 1
    if ticker_comparison.empty:
        lines.append("No per-ticker comparison available.")
    else:
        lines.append(_df_to_md(ticker_comparison))
        if not ticker_comparison["candidate_improved"].isna().all():
            improved = ticker_comparison["candidate_improved"].sum()
            total = ticker_comparison["candidate_improved"].notna().sum()
            lines.append(f"- {int(improved)} of {int(total)} tickers have candidate mean >= baseline mean.")
    lines.append("")

    lines.append(f"## {section_number}. Data-quality warnings")
    section_number += 1
    if data_quality.empty:
        lines.append("No data quality information available.")
    else:
        lines.append(_df_to_md(data_quality))
    lines.append("")

    lines.append(f"## {section_number}. Survivorship and provider limitations")
    section_number += 1
    lines.append("- The dataset does not eliminate survivorship bias, delisting bias, or point-in-time index membership.")
    lines.append("- Corporate actions, provider adjustments, retroactive splits, and liquidity capacity are not modeled.")
    lines.append("- Sector mappings are provided by the context specification, not inferred dynamically.")
    lines.append("")

    lines.append(f"## {section_number}. Promotion criteria")
    section_number += 1
    lines.append("Event-study gate:")
    lines.append("- Holdout events >= minimum, tickers >= minimum, retention >= minimum, coverage >= minimum.")
    lines.append("- Candidate mean, equal-weighted per-ticker mean, median, and positive rate must meet baseline comparisons.")
    lines.append("- Improvement must not be produced by only one ticker; at least half of represented tickers must improve.")
    lines.append("Executable-backtest gate:")
    lines.append("- Median and mean expectancy must exceed baseline; median total return not lower; drawdown not worse by >2pp.")
    lines.append("")

    lines.append(f"## {section_number}. Promotion decision")
    section_number += 1
    event_gate = holdout.passed
    backtest_gate = paired.passed
    if event_gate and backtest_gate:
        lines.append("The context policy passed the predefined promotion gate and is available as an opt-in filter.")
    else:
        lines.append("The context policy did not pass the predefined promotion gate and was not exposed to production.")
        if not event_gate:
            lines.append("- Event-study holdout gate failed.")
        if not backtest_gate:
            lines.append("- Executable-backtest holdout gate failed.")
    lines.append("")

    lines.append(f"## {section_number}. Production behavior")
    section_number += 1
    if event_gate and backtest_gate:
        lines.append(f"- The selected policy `{candidate_selection.selected_policy}` may be used as an opt-in filter.")
    lines.append("- The production default remains `off`.")
    lines.append("- No short-term component condition, weight, or threshold was changed.")
    lines.append("")

    lines.append(f"## {section_number}. Research limitations")
    lines.append("- Events may overlap and are not independent.")
    lines.append("- Event-study averages are not portfolio returns.")
    lines.append("- Results are descriptive evidence, not proof of a durable edge, statistical significance, or profitability.")
    lines.append("")

    return "\n".join(lines)


def _df_to_md(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a Markdown table."""
    if df.empty:
        return "(empty table)"
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join([" --- " for _ in cols]) + "|"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                if pd.isna(v):
                    cells.append("")
                else:
                    cells.append(f"{v:.4f}")
            elif v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)
