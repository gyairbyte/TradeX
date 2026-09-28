"""External Parquet and safe committed JSON artifact serialization for LONG-002D1."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tradex.research.long_002d.spec import (
    EXPECTED_BASE_RATE,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    FEATURE_REGISTRY,
    REPO_ROOT,
)

DEFAULT_EXTERNAL_DIR = REPO_ROOT / "data" / "research" / "long_002d1"
DEFAULT_SUMMARY_BASE_DIR = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002D1"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def save_external_parquets(
    df_feature_table: pd.DataFrame,
    df_decile_detail: pd.DataFrame,
    df_bootstrap_detail: pd.DataFrame,
    df_redundancy_matrix: pd.DataFrame,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Save external row-level Parquet datasets and compute their metadata."""
    out_dir = output_dir or DEFAULT_EXTERNAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    files_to_save: list[tuple[str, str, pd.DataFrame]] = [
        ("feature_table.parquet", "long_002d1_feature_table", df_feature_table),
        ("feature_decile_detail.parquet", "long_002d1_decile_detail", df_decile_detail),
        ("bootstrap_detail.parquet", "long_002d1_bootstrap_detail", df_bootstrap_detail),
        ("redundancy_matrix.parquet", "long_002d1_redundancy_matrix", df_redundancy_matrix),
    ]

    manifest_entries: list[dict[str, Any]] = []

    for fname, schema_name, df in files_to_save:
        file_path = out_dir / fname
        table = pa.Table.from_pandas(df)
        pq.write_table(table, file_path, compression="snappy")

        byte_count = file_path.stat().st_size
        sha256_hash = _compute_file_sha256(file_path)
        rel_path = f"data/research/long_002d1/{fname}"

        manifest_entries.append({
            "relative_path": rel_path,
            "schema_name": schema_name,
            "row_count": len(df),
            "byte_count": byte_count,
            "sha256": sha256_hash,
        })

    return manifest_entries


def save_committed_safe_summaries(
    run_id: str,
    execution_time_seconds: float,
    benchmark_report: dict[str, Any],
    external_files_manifest: list[dict[str, Any]],
    census_summaries: list[dict[str, Any]],
    bootstrap_summaries: dict[str, Any],
    redundancy_matrix: dict[str, Any],
    high_redundancy_pairs: list[dict[str, Any]],
    data_quality_report: dict[str, Any],
    output_base_dir: Path | None = None,
) -> Path:
    """Save safe committed summary JSON files and generate checksums.sha256."""
    base_dir = output_base_dir or DEFAULT_SUMMARY_BASE_DIR
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. execution_metadata.json
    exec_meta = {
        "task_id": "LONG-002D1-CORE-KPI-CENSUS",
        "run_id": run_id,
        "created_at_utc": _now_utc(),
        "execution_time_seconds": round(execution_time_seconds, 2),
        "total_observations": EXPECTED_DENOMINATOR,
        "clean_primary_events": EXPECTED_CLEAN_EVENTS,
        "clean_primary_base_rate": EXPECTED_BASE_RATE,
        "benchmark_report": benchmark_report,
        "external_files": external_files_manifest,
    }
    (run_dir / "execution_metadata.json").write_text(
        json.dumps(exec_meta, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 2. feature_registry.json
    registry_list = [asdict(f) for f in FEATURE_REGISTRY]
    (run_dir / "feature_registry.json").write_text(
        json.dumps({"features": registry_list}, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 3. feature_census_summary.json
    census_payload = {
        "task_id": "LONG-002D1-CORE-KPI-CENSUS",
        "run_id": run_id,
        "created_at_utc": _now_utc(),
        "total_observations": EXPECTED_DENOMINATOR,
        "clean_primary_events": EXPECTED_CLEAN_EVENTS,
        "clean_primary_base_rate": EXPECTED_BASE_RATE,
        "features": census_summaries,
    }
    (run_dir / "feature_census_summary.json").write_text(
        json.dumps(census_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 4. bootstrap_summary.json
    boot_payload = {
        "task_id": "LONG-002D1-CORE-KPI-CENSUS",
        "run_id": run_id,
        "created_at_utc": _now_utc(),
        "primary_block_size_sessions": 21,
        "robustness_block_size_sessions": 42,
        "num_bootstraps": 1000,
        "seed": 20260927,
        "bootstrap_results": bootstrap_summaries,
    }
    (run_dir / "bootstrap_summary.json").write_text(
        json.dumps(boot_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 5. redundancy_summary.json
    redundancy_payload = {
        "task_id": "LONG-002D1-CORE-KPI-CENSUS",
        "run_id": run_id,
        "created_at_utc": _now_utc(),
        "correlation_type": "spearman_rank",
        "high_redundancy_threshold": 0.95,
        "high_redundancy_pairs": high_redundancy_pairs,
        "spearman_correlation_matrix": redundancy_matrix,
    }
    (run_dir / "redundancy_summary.json").write_text(
        json.dumps(redundancy_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 6. data_quality_summary.json
    (run_dir / "data_quality_summary.json").write_text(
        json.dumps(data_quality_report, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 7. checksums.sha256
    json_files = sorted([
        f for f in run_dir.iterdir() if f.is_file() and f.suffix == ".json" and f.name != "checksums.sha256"
    ])
    checksum_lines: list[str] = []
    for f in json_files:
        sha = _compute_file_sha256(f)
        checksum_lines.append(f"{sha}  {f.name}")

    (run_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    return run_dir
