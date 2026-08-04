"""Locked daily-snapshot creation for LONG-001."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.history import fetch_daily_history

from .models import (
    DatasetManifest,
    LongTermStudySpec,
    ManifestEntry,
    StudyError,
    _build_split_dates,
    _file_sha256,
    _json_default,
    _validate_bars,
)


def snapshot_dataset(
    spec: LongTermStudySpec,
    output_dir: Path,
    *,
    fetch_fn: Callable[[str, Any, Any, str], pd.DataFrame] | None = None,
    settings: TradeXSettings | None = None,
) -> DatasetManifest:
    """Fetch daily bars for the universe + benchmark and write a locked manifest.

    Parameters
    ----------
    spec:
        Study specification (determines universe, dates, provider).
    output_dir:
        Directory where ticker CSVs and ``manifest.json`` will be written.
    fetch_fn:
        Optional override for fetching. For tests, pass a callable
        ``(ticker, start, end, provider) -> DataFrame``.
    settings:
        Optional ``TradeXSettings``; if omitted, runtime settings are loaded once.
    """
    settings = settings or load_runtime_settings()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_tickers = list(spec.universe) + [spec.benchmark_ticker]
    entries: list[ManifestEntry] = []

    for ticker in all_tickers:
        path = data_dir / f"{ticker}.csv"
        try:
            if fetch_fn is not None:
                df = fetch_fn(ticker, spec.start, spec.end, spec.provider)
            else:
                df = fetch_daily_history(
                    ticker,
                    spec.start,
                    spec.end,
                    provider=spec.provider,
                    settings=settings,
                )
            if df is None or df.empty:
                raise StudyError("no data returned")

            df, duplicate_timestamps, missing_required_values, invalid_ohlc_rows = _validate_bars(
                df, ticker
            )
            df.to_csv(path, index=True, index_label="datetime")
            sha = _file_sha256(path)
            entries.append(
                ManifestEntry(
                    ticker=ticker,
                    path=str(path.relative_to(output_dir)),
                    sha256=sha,
                    rows=len(df),
                    start=df.index[0].to_pydatetime(),
                    end=df.index[-1].to_pydatetime(),
                    data_source=spec.provider,
                    adjustment_policy=spec.adjustment_policy,
                    quality={
                        "missing_required_values": missing_required_values,
                        "invalid_ohlc_rows": invalid_ohlc_rows,
                        "duplicate_timestamps": duplicate_timestamps,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            entries.append(
                ManifestEntry(
                    ticker=ticker,
                    path=str(path.relative_to(output_dir)),
                    sha256="",
                    rows=0,
                    start=datetime.min.replace(tzinfo=UTC),
                    end=datetime.min.replace(tzinfo=UTC),
                    data_source=spec.provider,
                    adjustment_policy=spec.adjustment_policy,
                    failure=str(exc),
                    quality={},
                    warnings=[str(exc)],
                )
            )

    manifest = DatasetManifest(
        created_at=datetime.now(UTC),
        requested_start=spec.start,
        requested_end=spec.end,
        requested_universe=spec.universe,
        benchmark_ticker=spec.benchmark_ticker,
        entries=tuple(entries),
        splits=_build_split_dates(spec),
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, default=_json_default), encoding="utf-8"
    )
    return manifest
