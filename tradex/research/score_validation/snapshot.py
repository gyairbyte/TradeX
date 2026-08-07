"""Provider-backed snapshot creation for the score-validation dataset."""
from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.backtest.validation import canonicalize_bars
from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import resolve_provider
from tradex.data.history import fetch_daily_history

from .cleaning import (
    IngestionPolicy,
    build_snapshot_audit,
    clean_ticker,
    load_ingestion_policy,
    update_audit_reason_summary,
    write_invalid_rows,
    write_snapshot_audit,
    write_snapshot_checksums,
    write_snapshot_data_quality,
)
from .manifest import write_manifest
from .models import ManifestEntry, Split, ValidationError
from .report import _atomic_publish_dir

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]+$")


def create_snapshot(
    tickers: list[str],
    start: date,
    end: date,
    output_dir: str | Path,
    splits: dict[str, tuple[str, str]],
    provider: str | None = None,
    overwrite: bool = False,
    settings: TradeXSettings | None = None,
    dataset_name: str = "short-term-score-study",
    source_description: str | None = None,
    adjustment_policy: str = "provider_default",
    ingestion_spec: str | Path | IngestionPolicy | None = None,
    context_spec_sha256: str | None = None,
) -> Path:
    """Fetch daily history for ``tickers`` and write a versioned manifest + CSVs.

    Args:
        tickers: Nonempty list of ticker symbols (deduplicated by first occurrence).
        start: First calendar date to include.
        end: Last calendar date to include.
        output_dir: Directory to write CSVs and manifest.json into.
        splits: Required split date ranges as {"name": ("YYYY-MM-DD", "YYYY-MM-DD")}.
        provider: Provider name or None to use the environment default.
        overwrite: Whether to overwrite an existing nonempty output directory.
        settings: TradeXSettings instance or None to load from environment.
        dataset_name: Manifest dataset name.
        source_description: Manifest source description. Defaults to a value that
            includes the ingestion policy when one is supplied.
        adjustment_policy: Description of the provider's adjustment policy.
        ingestion_spec: Optional path to a locked ingestion-policy JSON, or an
            already-loaded ``IngestionPolicy``. When supplied, malformed rows are
            dropped and audited before the final strict ``canonicalize_bars`` pass.
        context_spec_sha256: Optional SHA-256 of the locked context spec; recorded
            in the snapshot audit.

    Returns:
        Path to the written manifest file.

    Raises:
        ValidationError: For invalid arguments or ingestion-policy violations.
        RuntimeError: If any provider fetch fails or returns empty data.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    if not tickers:
        raise ValidationError("Ticker list must not be empty")
    if end < start:
        raise ValidationError(f"End date {end} must be >= start date {start}")

    if settings is None:
        settings = load_runtime_settings()
    resolved_provider = resolve_provider(provider, settings=settings)

    # Parse splits early; the development start is needed for warmup checks.
    split_models = _parse_split_tuples(splits)
    development_start = split_models["development"].start

    seen: set[str] = set()
    unique_tickers: list[str] = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            raise ValidationError("Ticker list contains an empty symbol")
        _validate_ticker(t)
        if t in seen:
            continue
        seen.add(t)
        unique_tickers.append(t)

    ingestion_policy: IngestionPolicy | None = None
    ingestion_spec_path: Path | None = None
    ingestion_spec_sha256: str | None = None
    spec_bytes: bytes | None = None
    if ingestion_spec is not None:
        if isinstance(ingestion_spec, IngestionPolicy):
            ingestion_policy = ingestion_spec
            spec_bytes = ingestion_policy.to_json().encode("utf-8")
            ingestion_spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()
        else:
            ingestion_spec_path = Path(ingestion_spec).expanduser().resolve()
            ingestion_policy, spec_bytes = load_ingestion_policy(ingestion_spec_path)
            ingestion_spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()
        if resolved_provider != "schwab":
            raise ValidationError(
                f"Ingestion policy requires provider 'schwab'; got {resolved_provider!r}"
            )
        if source_description is None:
            source_description = f"offline OHLCV snapshots; ingestion policy: {ingestion_policy.policy_id}"
    if source_description is None:
        source_description = "offline OHLCV snapshots"

    tmp_dir = Path(tempfile.mkdtemp(prefix="tradex_score_study_", dir=output_dir.parent))
    try:
        entries: list[ManifestEntry] = []
        cleaning_results: list = []
        removed_frames: list[pd.DataFrame] = []
        for ticker in unique_tickers:
            df = fetch_daily_history(
                ticker, start, end, provider=resolved_provider, settings=settings
            )
            if df is None or df.empty:
                raise RuntimeError(f"No daily history returned for {ticker}")

            if ingestion_policy is not None:
                cleaned_df, removed_df, result = clean_ticker(
                    df,
                    ticker,
                    ingestion_policy,
                    start,
                    end,
                    development_start,
                    resolved_provider,
                )
                cleaning_results.append(result)
                if not removed_df.empty:
                    removed_frames.append(removed_df)
                df = canonicalize_bars(cleaned_df)
            else:
                df = canonicalize_bars(df)
            if df.empty:
                raise RuntimeError(f"No valid daily history rows for {ticker}")

            file_name = f"{ticker}.csv"
            csv_path = tmp_dir / file_name
            df.to_csv(csv_path, index=True, date_format="%Y-%m-%dT%H:%M:%S%z")

            sha = _sha256_file(csv_path)
            rows = len(df)
            start_dt = df.index[0].to_pydatetime()
            end_dt = df.index[-1].to_pydatetime()

            entries.append(
                ManifestEntry(
                    ticker=ticker,
                    path=file_name,
                    sha256=sha,
                    rows=rows,
                    start=start_dt,
                    end=end_dt,
                    data_source=resolved_provider,
                    adjustment_policy=adjustment_policy,
                )
            )

        manifest = _build_manifest(
            dataset_name=dataset_name,
            source_description=source_description,
            entries=entries,
            splits=split_models,
            created_at=datetime.now(UTC),
        )

        manifest_path = tmp_dir / "manifest.json"
        write_manifest(manifest, manifest_path)

        if ingestion_policy is not None and spec_bytes is not None:
            locked_spec_path = tmp_dir / "ingestion_spec.lock.json"
            locked_spec_path.write_bytes(spec_bytes)

        invalid_rows_df = (
            pd.concat([df.reset_index() for df in removed_frames], ignore_index=True)
            if removed_frames
            else pd.DataFrame()
        )

        if ingestion_policy is not None:
            write_snapshot_data_quality(cleaning_results, tmp_dir / "snapshot_data_quality.csv")
            write_invalid_rows(invalid_rows_df, tmp_dir / "invalid_rows.csv")

            audit = build_snapshot_audit(
                cleaning_results,
                ingestion_policy,
                resolved_provider,
                start,
                end,
                ingestion_spec_sha256 or "",
                context_spec_sha256,
            )
            audit = update_audit_reason_summary(audit, invalid_rows_df)
            write_snapshot_audit(audit, tmp_dir / "snapshot_audit.json")
            write_snapshot_checksums(tmp_dir, tmp_dir / "snapshot_checksums.sha256")

            # Manifest was written before the audit; update the audit with the
            # manifest and sidecar hashes now that all files exist.
            manifest_sha = _sha256_file(manifest_path)
            sidecar_sha256 = {
                name: _sha256_file(tmp_dir / name)
                for name in [
                    "ingestion_spec.lock.json",
                    "snapshot_audit.json",
                    "snapshot_data_quality.csv",
                    "invalid_rows.csv",
                ]
                if (tmp_dir / name).is_file()
            }
            audit = build_snapshot_audit(
                cleaning_results,
                ingestion_policy,
                resolved_provider,
                start,
                end,
                ingestion_spec_sha256 or "",
                context_spec_sha256,
                manifest_sha256=manifest_sha,
                sidecar_sha256=sidecar_sha256,
            )
            audit = update_audit_reason_summary(audit, invalid_rows_df)
            write_snapshot_audit(audit, tmp_dir / "snapshot_audit.json")
            write_snapshot_checksums(tmp_dir, tmp_dir / "snapshot_checksums.sha256")

        # Atomic publication: swap the completed temp directory into place.
        _atomic_publish_dir(tmp_dir, output_dir, overwrite)
        return output_dir / "manifest.json"
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _validate_ticker(ticker: str) -> None:
    """Reject path-unsafe or otherwise invalid ticker strings."""
    if ".." in ticker:
        raise ValidationError(f"Ticker {ticker!r} is invalid; must not contain '..'")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValidationError(
            f"Ticker {ticker!r} is invalid; must contain only uppercase letters, digits, '.', or '-'"
        )


def _parse_split_tuples(
    splits: dict[str, tuple[str | date, str | date] | list[str | date]],
) -> dict[str, Split]:
    """Validate split tuple input and return typed Split objects."""
    required = ["development", "validation", "holdout"]
    missing = [r for r in required if r not in splits]
    if missing:
        raise ValidationError(f"Missing required splits: {missing}")

    def _as_date(value: str | date) -> date:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"Invalid split date {value!r}: {exc}") from exc

    result: dict[str, Split] = {}
    prev_end: date | None = None
    for name in required:
        raw = splits[name]
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            raise ValidationError(f"Split {name} must be a (start, end) pair")
        start = _as_date(raw[0])
        end = _as_date(raw[1])
        if end < start:
            raise ValidationError(f"Split {name}: end {end} must be >= start {start}")
        if prev_end is not None and start <= prev_end:
            raise ValidationError(
                f"Split {name}: start {start} is not after previous split end {prev_end}; "
                "splits must be strictly non-overlapping"
            )
        prev_end = end
        result[name] = Split(start=start, end=end)
    return result


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest(
    dataset_name: str,
    source_description: str,
    entries: list[ManifestEntry],
    splits: dict[str, Split],
    created_at: datetime,
) -> Any:
    from .models import DatasetManifest

    return DatasetManifest(
        schema_version=1,
        dataset_name=dataset_name,
        created_at=created_at,
        source_description=source_description,
        entries=tuple(entries),
        splits=splits,
    )
