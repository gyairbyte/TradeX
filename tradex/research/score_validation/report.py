"""Study result serialization and Markdown report generation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .aggregate import (
    build_component_frequency,
    build_components,
    build_data_quality_df,
    build_event_dataframe,
    build_score_buckets,
    build_score_distribution,
    build_thresholds,
    build_ticker_summary,
)
from .events import generate_events
from .manifest import load_manifest
from .models import (
    DatasetManifest,
    ScoreValidationConfig,
    StudyResult,
    ValidationError,
    _config_to_dict,
    _manifest_to_dict,
)


def run_study(
    manifest_path: str | Path,
    config: ScoreValidationConfig,
    *,
    generated_at: datetime | None = None,
) -> StudyResult:
    """Load a manifest, generate events, aggregate, and return a StudyResult.

    ``generated_at`` defaults to the manifest creation timestamp so the same
    manifest produces a deterministic output across reruns.
    """
    manifest = load_manifest(manifest_path)
    events, quality_rows = generate_events(manifest, config)
    events_df = build_event_dataframe(events, config)
    score_buckets = build_score_buckets(events_df, config)
    thresholds = build_thresholds(events_df, config)
    components = build_components(events_df, config)
    score_distribution = build_score_distribution(events_df)
    component_frequency = build_component_frequency(events_df)
    ticker_summary = build_ticker_summary(events_df, config)
    data_quality = build_data_quality_df(quality_rows)

    from tradex.signals.weights import ShortWeights

    weight_snapshot = {
        "short_term": {
            "source": "explicit ShortWeights() default",
            "weights": {k: int(v) for k, v in ShortWeights().__dict__.items()},
        }
    }

    report_md = _render_report(
        config,
        manifest,
        weight_snapshot,
        events_df,
        score_buckets,
        thresholds,
        components,
        score_distribution,
        component_frequency,
        ticker_summary,
        data_quality,
    )

    if generated_at is None:
        generated_at = manifest.created_at

    return StudyResult(
        config=config,
        manifest=manifest,
        weight_snapshot=weight_snapshot,
        events=events_df,
        score_buckets=score_buckets,
        thresholds=thresholds,
        components=components,
        score_distribution=score_distribution,
        component_frequency=component_frequency,
        ticker_summary=ticker_summary,
        data_quality=data_quality,
        report_markdown=report_md,
        generated_at=generated_at,
    )


def write_study(
    study: StudyResult, output_dir: str | Path, overwrite: bool = False
) -> dict[str, Path]:
    """Write all study outputs atomically to ``output_dir``.

    Files are written to a sibling temporary directory and then renamed into
    place. If ``overwrite`` is true and the previous directory exists, it is
    moved to a backup path before the rename; if the rename fails the backup
    is restored.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="tradex_score_result_", dir=output_dir.parent))
    try:
        paths = _write_study_files(study, tmp_dir)
        _atomic_publish_dir(tmp_dir, output_dir, overwrite)
        # Update returned paths to final location.
        for name in paths:
            paths[name] = output_dir / name
        return paths
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _write_study_files(study: StudyResult, tmp_dir: Path) -> dict[str, Path]:
    """Write every study artifact into ``tmp_dir`` and return name -> tmp path."""
    paths = {}
    paths["events.csv"] = _write_csv(study.events, tmp_dir / "events.csv")
    paths["score_buckets.csv"] = _write_csv(study.score_buckets, tmp_dir / "score_buckets.csv")
    paths["thresholds.csv"] = _write_csv(study.thresholds, tmp_dir / "thresholds.csv")
    paths["components.csv"] = _write_csv(study.components, tmp_dir / "components.csv")
    paths["score_distribution.csv"] = _write_csv(
        study.score_distribution, tmp_dir / "score_distribution.csv"
    )
    paths["component_frequency.csv"] = _write_csv(
        study.component_frequency, tmp_dir / "component_frequency.csv"
    )
    paths["ticker_summary.csv"] = _write_csv(study.ticker_summary, tmp_dir / "ticker_summary.csv")
    paths["data_quality.csv"] = _write_csv(study.data_quality, tmp_dir / "data_quality.csv")
    paths["manifest.lock.json"] = _write_json(_manifest_lock(study), tmp_dir / "manifest.lock.json")
    paths["study.json"] = _write_json(study.to_dict(), tmp_dir / "study.json")
    paths["report.md"] = _write_text(study.report_markdown, tmp_dir / "report.md")
    return paths


def _atomic_publish_dir(tmp_dir: Path, output_dir: Path, overwrite: bool) -> None:
    """Atomically replace ``output_dir`` with the contents of ``tmp_dir``.

    If ``output_dir`` already exists and is nonempty, ``overwrite`` must be
    true. The old directory is moved to a backup path, then ``tmp_dir`` is
    renamed to ``output_dir``. If anything fails after the backup is created,
    the backup is restored.
    """
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise ValidationError(
                f"Output directory {output_dir} exists and is nonempty; pass --overwrite"
            )
        backup_dir = output_dir.with_name(output_dir.name + ".tmp-rename-backup")
        # Remove any stale backup first.
        shutil.rmtree(backup_dir, ignore_errors=True)
        os.replace(str(output_dir), str(backup_dir))
        try:
            os.replace(str(tmp_dir), str(output_dir))
        except Exception:
            # Restore the backup on failure.
            _rollback(output_dir, backup_dir)
            raise
        # Success: remove backup.
        shutil.rmtree(backup_dir, ignore_errors=True)
    else:
        if output_dir.exists():
            # Empty directory can be removed or replaced directly.
            os.rmdir(str(output_dir))
        try:
            os.replace(str(tmp_dir), str(output_dir))
        except Exception:
            if not output_dir.exists():
                # Empty placeholder that was just removed; leave tmp for debugging.
                pass
            raise

    # fsync the parent directory so the rename is durable.
    _fsync_dir(output_dir.parent)


def _rollback(output_dir: Path, backup_dir: Path) -> None:
    """Move ``backup_dir`` back to ``output_dir`` if it is safe to do so."""
    if backup_dir.exists() and not output_dir.exists():
        try:
            os.replace(str(backup_dir), str(output_dir))
        except Exception:
            pass


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, AttributeError):
        pass


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


def _fsync_file(path: Path) -> None:
    try:
        with path.open("rb") as f:
            os.fsync(f.fileno())
    except OSError:
        pass


def _manifest_lock(study: StudyResult) -> dict[str, Any]:
    """Lock the exact inputs used to produce this study."""
    manifest_sha = getattr(study.manifest, "_sha256", None)
    raw_manifest = getattr(study.manifest, "_raw", _manifest_to_dict(study.manifest))
    return {
        "manifest_sha256": manifest_sha,
        "manifest": raw_manifest,
        "config": _config_to_dict(study.config),
        "weight_snapshot": study.weight_snapshot,
    }


def _json_default(obj: Any) -> Any:
    from datetime import date, datetime

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _render_report(
    config,
    manifest: DatasetManifest,
    weight_snapshot,
    events_df,
    score_buckets,
    thresholds,
    components,
    score_distribution,
    component_frequency,
    ticker_summary,
    data_quality,
) -> str:
    """Build the human-readable Markdown report."""
    manifest_sha = getattr(manifest, "_sha256", None)

    lines = []
    lines.append("# Short-Term Score Validation Study")
    lines.append("")
    lines.append("## 1. Study identity")
    lines.append(f"- Dataset: {manifest.dataset_name}")
    lines.append(f"- Source: {manifest.source_description}")
    lines.append(f"- Generated: {manifest.created_at.isoformat()}")
    lines.append("")
    lines.append("## 2. Dataset provenance")
    lines.append("The study used manifest-locked offline OHLCV snapshots. Every input CSV was verified by SHA-256 before analysis.")
    lines.append("")
    lines.append("## 3. Manifest checksum")
    if manifest_sha:
        lines.append(f"- Manifest SHA-256: `{manifest_sha}`")
    lines.append("- The exact input manifest, configuration, and weight snapshot are preserved in `manifest.lock.json`.")
    lines.append("")
    lines.append("## 4. Study configuration")
    lines.append("```json")
    lines.append(json.dumps(_config_to_dict(config), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 5. Explicit weight snapshot")
    lines.append("```json")
    lines.append(json.dumps(weight_snapshot, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 6. Research questions")
    lines.append("1. Do higher short-term scores correspond to better forward returns?")
    lines.append("2. Does the current default threshold of 40 separate stronger outcomes from weaker outcomes?")
    lines.append("3. Which existing short-term components are associated with stronger or weaker outcomes?")
    lines.append("4. Are those relationships stable across tickers, time periods, and transaction-cost assumptions?")
    lines.append("5. Is there enough evidence to justify a later production-scoring change?")
    lines.append("")
    lines.append("## 7. Data-quality summary")
    if data_quality.empty:
        lines.append("No data-quality information available.")
    else:
        lines.append(_df_to_md(data_quality))
    lines.append("")
    lines.append("## 8. Score distribution")
    if score_distribution.empty:
        lines.append("No events available for score distribution.")
    else:
        lines.append(_df_to_md(score_distribution))
    lines.append("")
    lines.append("## 9. Score-bucket results")
    if score_buckets.empty:
        lines.append("No score-bucket results available.")
    else:
        lines.append(_df_to_md(score_buckets))
    lines.append("")
    lines.append("## 10. Threshold results")
    if thresholds.empty:
        lines.append("No threshold results available.")
    else:
        lines.append(_df_to_md(thresholds))
    lines.append("")
    lines.append("## 11. Current threshold 40")
    current = thresholds[thresholds["threshold_label"] == "current_default"]
    if current.empty:
        lines.append("No events at or above the current default threshold of 40.")
    else:
        lines.append(_df_to_md(current))
    lines.append("")
    lines.append("## 12. Component diagnostics")
    if components.empty:
        lines.append("No component diagnostics available.")
    else:
        lines.append(_df_to_md(components))
    lines.append("")
    lines.append("## 13. Development results")
    dev_buckets = score_buckets[score_buckets["split"] == "development"]
    if dev_buckets.empty:
        lines.append("No development-period results available.")
    else:
        lines.append(_df_to_md(dev_buckets))
    lines.append("")
    lines.append("## 14. Validation results")
    val_buckets = score_buckets[score_buckets["split"] == "validation"]
    if val_buckets.empty:
        lines.append("No validation-period results available.")
    else:
        lines.append(_df_to_md(val_buckets))
    lines.append("")
    lines.append("## 15. Holdout results")
    hold_buckets = score_buckets[score_buckets["split"] == "holdout"]
    if hold_buckets.empty:
        lines.append("No holdout-period results available.")
    else:
        lines.append(_df_to_md(hold_buckets))
    lines.append("")
    lines.append("## 16. Cost sensitivity")
    lines.append("Net returns are reported for each configured slippage scenario. Commission is applied per side.")
    lines.append("")
    lines.append("## 17. Per-ticker robustness")
    if ticker_summary.empty:
        lines.append("No per-ticker summary available.")
    else:
        lines.append(_df_to_md(ticker_summary))
    lines.append("")
    lines.append("## 18. Limitations")
    lines.append("- Events are not independent and may overlap.")
    lines.append("- Multiple daily observations from the same ticker are correlated.")
    lines.append("- Event counts are not trade counts from an executable portfolio.")
    lines.append("- Pooled results can be dominated by tickers with longer histories.")
    lines.append("- Event returns do not model capital allocation, stops, targets, or position sizing.")
    lines.append("- The existing backtest engine remains the executable-strategy tool.")
    lines.append("- Results do not account for survivorship bias, delistings, or corporate actions.")
    lines.append("")
    lines.append("## 19. Interpretation guardrails")
    lines.append("This is a descriptive calibration study, not proof of a profitable strategy. Do not treat event-study averages as portfolio returns.")
    lines.append("")
    lines.append("## 20. Production-change status")
    lines.append("No production score, weight, or threshold is changed by this study.")
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
