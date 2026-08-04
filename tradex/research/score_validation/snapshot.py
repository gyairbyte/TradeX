"""Provider-backed snapshot creation for the score-validation dataset."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.backtest.validation import canonicalize_bars
from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import resolve_provider
from tradex.data.history import fetch_daily_history

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
    source_description: str = "offline OHLCV snapshots",
    adjustment_policy: str = "provider_default",
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
        dataset_name: Manifest dataset name.
        source_description: Manifest source description.
        adjustment_policy: Description of the provider's adjustment policy.

    Returns:
        Path to the written manifest file.

    Raises:
        ValidationError: For invalid arguments.
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

    split_models = _parse_split_tuples(splits)

    tmp_dir = Path(tempfile.mkdtemp(prefix="tradex_score_study_", dir=output_dir.parent))
    try:
        entries: list[ManifestEntry] = []
        for ticker in unique_tickers:
            df = fetch_daily_history(
                ticker, start, end, provider=resolved_provider, settings=settings
            )
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
                    data_source=resolved_provider,
                    adjustment_policy=adjustment_policy,
                )
            )

        manifest = _build_manifest(
            dataset_name=dataset_name,
            source_description=source_description,
            entries=entries,
            splits=split_models,
            created_at=datetime.now(timezone.utc),
        )

        manifest_path = tmp_dir / "manifest.json"
        write_manifest(manifest, manifest_path)

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
