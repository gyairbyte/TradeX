"""Provider-backed snapshot creation for the score-validation dataset."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from tradex.backtest.validation import canonicalize_bars
from tradex.data.history import fetch_daily_history

from .manifest import build_manifest, write_manifest
from .models import ManifestEntry, Split, ValidationError


def create_snapshot(
    tickers: list[str],
    start: date,
    end: date,
    output_dir: str | Path,
    provider: str | None = None,
    overwrite: bool = False,
    dataset_name: str = "short-term-score-study",
    source_description: str = "offline OHLCV snapshots",
    adjustment_policy: str = "provider_default",
    splits: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Fetch daily history for ``tickers`` and write a versioned manifest + CSVs.

    Args:
        tickers: Nonempty list of ticker symbols (deduplicated by first occurrence).
        start: First calendar date to include.
        end: Last calendar date to include.
        provider: Provider name or None to use the environment default.
        output_dir: Directory to write CSVs and manifest.json into.
        overwrite: Whether to overwrite an existing nonempty output directory.
        dataset_name: Manifest dataset name.
        source_description: Manifest source description.
        adjustment_policy: Description of the provider's adjustment policy.
        splits: Optional split date ranges as {"name": ("YYYY-MM-DD", "YYYY-MM-DD")}.

    Returns:
        Path to the written manifest file.

    Raises:
        ValidationError: For invalid arguments.
        RuntimeError: If any provider fetch fails or returns empty data.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise ValidationError(
                f"Output directory {output_dir} exists and is nonempty; pass --overwrite"
            )
        shutil.rmtree(output_dir)

    if not tickers:
        raise ValidationError("Ticker list must not be empty")
    if end < start:
        raise ValidationError(f"End date {end} must be >= start date {start}")

    seen: set[str] = set()
    unique_tickers: list[str] = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            raise ValidationError("Ticker list contains an empty symbol")
        if t in seen:
            continue
        seen.add(t)
        unique_tickers.append(t)

    if splits is None:
        splits = {
            "development": ("2018-01-01", "2022-12-31"),
            "validation": ("2023-01-01", "2024-12-31"),
            "holdout": ("2025-01-01", "2025-12-31"),
        }

    split_models = _parse_splits(splits)

    tmp_dir = Path(tempfile.mkdtemp(prefix="tradex_score_study_"))
    try:
        entries: list[ManifestEntry] = []
        for ticker in unique_tickers:
            df = fetch_daily_history(ticker, start, end, provider=provider)
            if df is None or df.empty:
                raise RuntimeError(f"No daily history returned for {ticker}")

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
                    data_source=provider or "yahoo",
                    adjustment_policy=adjustment_policy,
                )
            )

        manifest = build_manifest(
            dataset_name=dataset_name,
            source_description=source_description,
            entries=entries,
            splits=split_models,
            created_at=datetime.now(timezone.utc),
        )

        manifest_path = tmp_dir / "manifest.json"
        write_manifest(manifest, manifest_path)

        # Atomic publish: move the temp directory to the final output path.
        output_dir.mkdir(parents=True, exist_ok=True)
        for item in tmp_dir.iterdir():
            dest = output_dir / item.name
            shutil.move(str(item), str(dest))

        return output_dir / "manifest.json"
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_splits(splits: dict[str, tuple[str, str]]) -> dict[str, Split]:
    from .models import Split

    result: dict[str, Split] = {}
    prev_end: date | None = None
    for name in ["development", "validation", "holdout"]:
        if name not in splits:
            raise ValidationError(f"Missing required split: {name}")
        start_str, end_str = splits[name]
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        if end < start:
            raise ValidationError(f"Split {name}: end must be >= start")
        if prev_end is not None and start < prev_end:
            raise ValidationError(
                f"Split {name}: start {start} overlaps previous split ending {prev_end}"
            )
        prev_end = end
        result[name] = Split(start=start, end=end)
    return result
