"""Run a full pattern-similarity validation study and publish deterministic artifacts."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .baselines import frequency_matched_controls, unconditional_baseline_observations
from .fingerprints import build_development_fingerprints
from .metrics import compute_all_metrics, evaluate_evidence_gates
from .models import (
    DatasetManifest,
    PromotionDecision,
    StudyResult,
    StudySpec,
    ValidationError,
    _clean,
)
from .observations import (
    build_executable_trades,
    evaluate_splits,
    observations_to_dataframe,
    trades_to_dataframe,
)
from .snapshot import _count_split_events


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    if df is None or df.empty:
        path.write_text("\n")
        return
    df.to_csv(path, index=False, float_format="%.6f")


def _build_data_quality(
    manifest: DatasetManifest,
    bars: dict[str, pd.DataFrame],
    observations: list[Any],
    spec: StudySpec,
) -> pd.DataFrame:
    """Build a per-ticker data-quality summary with counts from snapshot validation."""
    from .snapshot import _count_complete_bars

    obs_by_ticker_split: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for obs in observations:
        obs_by_ticker_split[(obs.ticker, obs.split)]["eligible"] += 1
        if obs.is_qualifying:
            obs_by_ticker_split[(obs.ticker, obs.split)]["qualifying"] += 1
        if obs.outcome_status == "complete":
            obs_by_ticker_split[(obs.ticker, obs.split)]["complete"] += 1
        elif obs.outcome_status == "insufficient_future_bars":
            obs_by_ticker_split[(obs.ticker, obs.split)]["insufficient_future_bars"] += 1
        elif obs.outcome_status == "missing_signal_data":
            obs_by_ticker_split[(obs.ticker, obs.split)]["missing_signal_data"] += 1

    rows: list[dict[str, Any]] = []
    for entry in manifest.entries:
        quality = entry.quality or {}
        warnings = list(entry.warnings or [])
        if entry.failure and entry.failure not in warnings:
            warnings.append(entry.failure)

        df = bars.get(entry.ticker)
        validated_rows = len(df) if df is not None else entry.rows
        complete_lookbacks = 0
        complete_forward_bars = 0
        if df is not None and not df.empty:
            complete_lookbacks, complete_forward_bars = _count_complete_bars(df, spec.lookback_days, spec.holding_days)

        eligible_per_split: dict[str, int] = {}
        event_counts_per_split: dict[str, int] = {}
        for split_name in spec.splits:
            eligible_per_split[split_name] = obs_by_ticker_split.get((entry.ticker, split_name), {}).get("eligible", 0)
            if df is not None and not df.empty:
                event_counts_per_split[split_name] = _count_split_events(
                    df, spec.splits, spec.lookback_days, spec.holding_days, spec.move_days, spec.runup_pct, spec.decline_pct
                ).get(split_name, 0)
            else:
                event_counts_per_split[split_name] = 0

        rows.append({
            "ticker": entry.ticker,
            "data_source": entry.data_source,
            "sha256": entry.sha256,
            "manifest_rows": entry.rows,
            "validated_rows": validated_rows,
            "data_start": entry.start.isoformat() if entry.start else None,
            "data_end": entry.end.isoformat() if entry.end else None,
            "duplicate_timestamps": quality.get("duplicate_timestamps", 0),
            "missing_required_values": quality.get("missing_required_values", 0),
            "invalid_ohlc_rows": quality.get("invalid_ohlc_rows", 0),
            "bars_outside_range": quality.get("bars_outside_range", 0),
            "complete_lookbacks": complete_lookbacks,
            "complete_forward_bars": complete_forward_bars,
            "eligible_observations_per_split": eligible_per_split,
            "split_event_counts": event_counts_per_split,
            "warnings": warnings,
        })

    return pd.DataFrame(rows)


def _build_baseline_comparison(
    period_metrics: dict[tuple[str, str], Any],
    per_ticker: list[Any],
    spec: StudySpec,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for (split, event_type), pm in sorted(period_metrics.items()):
        records.append({
            "split": split,
            "event_type": event_type,
            "metric_level": "pooled",
            "identifier": "pooled",
            "observations": pm.eligible_observations,
            "signals": pm.qualifying_signals,
            "mean_signal_net_return_pct": pm.mean_net_return_pct,
            "mean_baseline_net_return_pct": pm.baseline_mean_return_pct,
            "lift_bps": pm.baseline_lift_bps,
            "lift_ci_lower": pm.baseline_lift_ci_lower,
            "lift_ci_upper": pm.baseline_lift_ci_upper,
            "mean_return_ci_lower": pm.mean_return_ci_lower,
            "mean_return_ci_upper": pm.mean_return_ci_upper,
            "win_rate": pm.win_rate,
            "executable_trades": pm.executed_trades,
            "executable_mean_net_return_pct": pm.executable_mean_net_return_pct,
            "executable_win_rate": pm.executable_win_rate,
        })
    for tm in sorted(per_ticker, key=lambda x: (x.split, x.event_type, x.ticker)):
        records.append({
            "split": tm.split,
            "event_type": tm.event_type,
            "metric_level": "ticker",
            "identifier": tm.ticker,
            "observations": tm.observations,
            "signals": tm.qualifying_signals,
            "mean_signal_net_return_pct": tm.mean_net_return_pct,
            "mean_baseline_net_return_pct": tm.mean_baseline_return_pct,
            "lift_bps": tm.lift_bps,
            "lift_ci_lower": None,
            "lift_ci_upper": None,
            "mean_return_ci_lower": None,
            "mean_return_ci_upper": None,
            "win_rate": tm.win_rate,
            "executable_trades": tm.executed_trades,
            "executable_mean_net_return_pct": tm.executable_mean_net_return_pct,
            "executable_win_rate": tm.executable_win_rate,
        })
    return pd.DataFrame(records)


def _build_period_summary(period_metrics: dict[tuple[str, str], Any], spec: StudySpec) -> pd.DataFrame:
    records = []
    for (split, event_type), pm in sorted(period_metrics.items()):
        d = pm.to_dict()
        d.pop("returns_by_slippage", None)
        d.pop("component_scores", None)
        records.append(d)
    return pd.DataFrame(records)


def _build_report_markdown(
    spec: StudySpec,
    manifest: DatasetManifest,
    fingerprints: dict[str, Any],
    period_metrics: dict[tuple[str, str], Any],
    per_ticker: list[Any],
    promotion: PromotionDecision,
    limitations: list[str],
    generated_at: datetime,
) -> str:
    study_mode = "research test (not the locked PATTERN-001 contract)" if spec.research_test_mode else "locked PATTERN-001 contract"
    lines: list[str] = [
        "# Pattern Similarity Validation Study Report",
        "",
        f"**Dataset:** `{spec.dataset_name}`  ",
        f"**Provider:** `{spec.provider}`  ",
        f"**Profile:** `{spec.profile}`  ",
        f"**Study range:** `{spec.start_date}` to `{spec.end_date}`  ",
        f"**Study mode:** `{study_mode}`  ",
        f"**Generated:** `{generated_at.isoformat()}`  ",
        "",
        "## Hypothesis",
        "",
        "For the fixed study cohort and unchanged standard-profile matcher, decision dates with",
        "similarity at or above 75 have higher signed five-session returns than deterministic",
        "frequency-matched controls after conservative execution costs.",
        "",
        "- Run-up modeled as long; positive signed return means price rose.",
        "- Decline modeled as short; positive signed return means price fell.",
        "",
        "## Universe and Selection Bias",
        "",
        f"- **Universe:** fixed convenience cohort of {len(spec.tickers)} tickers.",
        "- This is **not** a point-in-time S&P 500 or Nasdaq-100 universe.",
        "- Survivorship and selection bias are present and disclosed.",
        f"- Universe hash: `{spec.universe_hash}`",
        "",
        "## Methodology",
        "",
        "Similarity is computed as a weighted Pearson correlation between the live pre-event",
        "window and the stored fingerprint. Correlation measures shape resemblance, not",
        "causality or expected return. A similarity of 75 is the existing fixed display cutoff",
        "used in this study; it is not a validated trading threshold.",
        "",
        "## Locked Study Parameters",
        "",
        f"- Similarity threshold: `{spec.similarity_threshold}`",
        f"- Lookback days: `{spec.lookback_days}`",
        f"- Move days / holding days: `{spec.move_days}` / `{spec.holding_days}`",
        f"- Run-up threshold: `+{spec.runup_pct}%`; decline threshold: `-{spec.decline_pct}%`",
        f"- Series weights: `{dict(sorted(spec.series_weights.items()))}`",
        f"- Cost scenario for evidence decision: `{spec.decision_slippage_bps}` bps per side",
        f"- Commission: `{spec.commission_bps}` bps",
        f"- Bootstrap: `{spec.bootstrap.method}`, {spec.bootstrap.resamples} resamples, seed `{spec.bootstrap.seed}`",
        "",
        "## Data Snapshot",
        "",
        f"- Requested tickers: {len(manifest.requested_tickers)}",
        f"- Successful: {len(manifest.successful_tickers)}",
        f"- Failed: {len(manifest.failed_tickers)} ({', '.join(manifest.failure_categories) or 'none'})",
        f"- Request date range: `{manifest.request_start}` to `{manifest.request_end}`",
        f"- Provider adjustment policy: `{manifest.adjustment_policy}`",
        "",
        "## Development Fingerprints",
        "",
    ]
    for event_type, fp in sorted(fingerprints.items()):
        lines.extend([
            f"- `{event_type}`: {fp.n_events} events across {fp.ticker_count} tickers",
            f"  - lookback: {fp.lookback_days} days",
            f"  - config hash: `{fp.config_hash}`",
            f"  - fingerprint hash: `{fp.fingerprint_sha256}`",
        ])

    lines.extend(["", "## Period Metrics", ""])
    for (split, event_type), pm in sorted(period_metrics.items()):
        lines.extend([
            f"### {split.title()} — {event_type}",
            "",
            f"- Eligible observations: {pm.eligible_observations}",
            f"- Qualifying signals (≥ {spec.similarity_threshold}): {pm.qualifying_signals}",
            f"- Executed trades: {pm.executed_trades}",
            f"- Tickers represented: {pm.ticker_count}",
            f"- Date coverage: `{pm.date_start}` to `{pm.date_end}`",
            f"- Mean similarity: {pm.mean_similarity:.2f}" if pm.mean_similarity is not None else "- Mean similarity: N/A",
            f"- Mean gross return: {pm.mean_gross_return_pct:.4f}%" if pm.mean_gross_return_pct is not None else "- Mean gross return: N/A",
            f"- Mean net return at {spec.decision_slippage_bps} bps/side: {pm.mean_net_return_pct:.4f}%" if pm.mean_net_return_pct is not None else "- Mean net return: N/A",
            f"- Median net return: {pm.median_net_return_pct:.4f}%" if pm.median_net_return_pct is not None else "- Median net return: N/A",
            f"- Win rate: {pm.win_rate:.2%}" if pm.win_rate is not None else "- Win rate: N/A",
            f"- Mean net return (non-overlapping executable trades): {pm.executable_mean_net_return_pct:.4f}%" if pm.executable_mean_net_return_pct is not None else "- Mean net return (executable trades): N/A",
            f"- Win rate (executable trades): {pm.executable_win_rate:.2%}" if pm.executable_win_rate is not None else "- Win rate (executable trades): N/A",
            f"- Baseline mean return: {pm.baseline_mean_return_pct:.4f}%" if pm.baseline_mean_return_pct is not None else "- Baseline mean return: N/A",
            f"- Lift over baseline: {pm.baseline_lift_bps} bps" if pm.baseline_lift_bps is not None else "- Lift over baseline: N/A",
            f"- Lift CI (2.5%-97.5%): [{pm.baseline_lift_ci_lower:.4f}, {pm.baseline_lift_ci_upper:.4f}]" if pm.baseline_lift_ci_lower is not None else "- Lift CI: N/A",
            f"- Mean return CI (2.5%-97.5%): [{pm.mean_return_ci_lower:.4f}, {pm.mean_return_ci_upper:.4f}]" if pm.mean_return_ci_lower is not None else "- Mean return CI: N/A",
            f"- Max ticker concentration: {pm.max_ticker_concentration:.2%}" if pm.max_ticker_concentration is not None else "- Max ticker concentration: N/A",
            f"- Max contribution concentration: {pm.max_contribution_concentration:.2%}" if pm.max_contribution_concentration is not None else "- Max contribution concentration: N/A",
            f"- Overlapping signals: {pm.overlap_count}",
            f"- Frequency-matched controls underfilled: {pm.baseline_underfilled}",
            f"- Missing/insufficient data observations: {pm.missing_data_count}",
            "",
            "#### Returns by slippage scenario",
            "",
        ])
        for key, dist in sorted(pm.returns_by_slippage.items()):
            lines.append(f"- {key} bps/side: mean={dist.get('mean'):.4f}%, median={dist.get('median'):.4f}%, win_rate={dist.get('win_rate'):.2%}" if dist.get("mean") is not None else f"- {key} bps/side: N/A")
        lines.append("")

    lines.extend(["## Promotion Decision", "", f"**Classification:** `{promotion.classification}`", f"**Production promotion eligible:** `{promotion.production_promotion_eligible}`", f"**Reason:** {promotion.reason}", ""])

    if limitations:
        lines.extend(["## Limitations and Disclosures", ""])
        for lim in limitations:
            lines.append(f"- {lim}")
        lines.append("")

    lines.extend([
        "## Research Safeguards",
        "",
        "- Development fingerprints were built only from the development split.",
        "- Validation and holdout observations used the immutable development fingerprint.",
        "- Point-in-time correctness was enforced: only bars available through the decision date were used for similarity.",
        "- Forward returns did not cross split boundaries.",
        "- The frequency-matched baseline was selected deterministically with the locked seed.",
        "- Automatic pattern-match alerts were removed; the matcher output and dashboard tab are labeled experimental research only.",
        "- No production scores, rankings, eligibility, thresholds, or weights were changed.",
        "",
    ])
    return "\n".join(lines)


def run_study(
    manifest: DatasetManifest,
    bars: dict[str, pd.DataFrame],
    spec: StudySpec,
) -> StudyResult:
    """Execute the full pattern-similarity validation pipeline."""
    # 1. Build development-only fingerprints.
    fingerprints, _ = build_development_fingerprints(bars, spec)
    # An empty fingerprint set is allowed; downstream metrics produce an inconclusive result.

    # 2. Evaluate validation and holdout observations.
    observations = evaluate_splits(bars, fingerprints, spec)

    # 3. Executable trades.
    trades = build_executable_trades(observations, spec)

    # 4. Baselines.
    if spec.baseline_definition == "frequency_matched":
        baseline_selection = frequency_matched_controls(observations, spec)
    else:
        baseline_selection = unconditional_baseline_observations(observations, spec)

    # 5. Metrics and evidence gates.
    period_metrics, per_ticker = compute_all_metrics(observations, baseline_selection, trades, spec)
    manifest_ok = manifest.verify_integrity()
    integrity_reasons = [] if manifest_ok else ["manifest integrity check failed"]
    promotion = evaluate_evidence_gates(
        period_metrics, per_ticker, spec, manifest_ok=manifest_ok, integrity_reasons=integrity_reasons
    )

    # 6. Data quality.
    data_quality_df = _build_data_quality(manifest, bars, observations, spec)

    # 7. DataFrames.
    observations_df = observations_to_dataframe(observations)
    qualifying_df = observations_df[observations_df["is_qualifying"] == True].copy() if not observations_df.empty else pd.DataFrame()
    controls_df = observations_to_dataframe(baseline_selection.controls)
    event_study_df = qualifying_df.copy() if not qualifying_df.empty else pd.DataFrame()
    trades_df = trades_to_dataframe(trades)
    ticker_summary_df = pd.DataFrame([tm.to_dict() for tm in per_ticker])
    period_summary_df = _build_period_summary(period_metrics, spec)
    baseline_comparison_df = _build_baseline_comparison(period_metrics, per_ticker, spec)

    limitations = [
        "This is a research study, not a live-trading recommendation.",
        "The universe is a fixed convenience cohort and is not point-in-time; survivorship and selection bias are present.",
        "Execution assumptions use next-open entry and fifth-close exit with conservative slippage but no borrow fees or borrow-availability constraints for shorts.",
        "Results depend on the market-data provider's adjustment and dividend policy.",
    ]

    report_markdown = _build_report_markdown(
        spec, manifest, fingerprints, period_metrics, per_ticker, promotion, limitations,
        generated_at=manifest.created_at,
    )

    return StudyResult(
        spec=spec,
        manifest=manifest,
        fingerprints=fingerprints,
        observations=observations_df,
        qualifying_signals=qualifying_df,
        frequency_matched_controls=controls_df,
        event_study=event_study_df,
        executable_trades=trades_df,
        ticker_summary=ticker_summary_df,
        period_summary=period_summary_df,
        baseline_comparison=baseline_comparison_df,
        data_quality=data_quality_df,
        promotion_decision=promotion,
        report_markdown=report_markdown,
        limitations=limitations,
        generated_at=manifest.created_at,
    )


def write_study(
    study: StudyResult,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, str]:
    """Write all deterministic artifacts to ``output_dir`` atomically."""
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise ValidationError(f"output directory already exists: {output_dir}. Use --overwrite.")

    stage = Path(tempfile.mkdtemp(prefix="pattern_validation_eval_"))
    try:
        # JSON / lock files.
        (stage / "study_spec.lock.json").write_text(study.spec.to_json(indent=2), encoding="utf-8")
        (stage / "study.json").write_text(study.to_json(indent=2), encoding="utf-8")
        (stage / "manifest.lock.json").write_text(study.manifest.to_json(indent=2), encoding="utf-8")

        fingerprints: dict[str, Any] = {k: fp.to_dict() for k, fp in sorted(study.fingerprints.items())}
        (stage / "development_fingerprints.json").write_text(
            json.dumps(_clean(fingerprints), indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )

        promotion = study.promotion_decision.to_dict()
        (stage / "promotion_decision.json").write_text(
            json.dumps(_clean(promotion), indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )

        # CSVs.
        _write_csv(study.observations, stage / "observations.csv")
        _write_csv(study.qualifying_signals, stage / "qualifying_signals.csv")
        _write_csv(study.frequency_matched_controls, stage / "frequency_matched_controls.csv")
        _write_csv(study.event_study, stage / "event_study.csv")
        _write_csv(study.executable_trades, stage / "executable_trades.csv")
        _write_csv(study.baseline_comparison, stage / "baseline_comparison.csv")
        _write_csv(study.ticker_summary, stage / "ticker_summary.csv")
        _write_csv(study.period_summary, stage / "period_summary.csv")
        _write_csv(study.data_quality, stage / "data_quality.csv")

        # Report.
        (stage / "report.md").write_text(study.report_markdown, encoding="utf-8")

        # Artifact manifest.
        artifact_manifest: dict[str, Any] = {
            "schema_version": 1,
            "created_at": study.generated_at.isoformat(),
            "spec_sha256": study.spec.sha256,
            "manifest_sha256": study.manifest.manifest_sha256,
            "files": {},
        }
        for file_path in sorted(stage.iterdir()):
            if file_path.is_file():
                artifact_manifest["files"][file_path.name] = _hash_file(file_path)
        manifest_path = stage / "artifact_manifest.json"
        manifest_path.write_text(
            json.dumps(_clean(artifact_manifest), indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )

        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.move(str(stage), str(output_dir))

        files = dict(artifact_manifest["files"])
        files[manifest_path.name] = _hash_file(output_dir / manifest_path.name)
        return files
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
