"""Point-in-time context alignment for short-term signal events."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from tradex.backtest.validation import canonicalize_bars
from tradex.market.context import compute_short_term_context
from tradex.market.models import ShortTermMarketContext
from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import DatasetManifest
from tradex.research.short_context.models import ShortContextSpec, ValidationError


def load_manifest_and_spec(
    manifest_path: str | Path,
    spec_path: str | Path,
) -> tuple[DatasetManifest, ShortContextSpec]:
    """Load and cross-validate a manifest and context spec."""
    manifest = load_manifest(manifest_path)
    from tradex.research.short_context.spec import load_spec as _load_spec
    spec, _ = _load_spec(spec_path)

    manifest_tickers = {e.ticker for e in manifest.entries}
    for t in spec.target_tickers:
        if t not in manifest_tickers:
            raise ValidationError(f"Target ticker {t} is not in the manifest")
        ctx = spec.ticker_context[t]
        if ctx["market_proxy"] not in manifest_tickers:
            raise ValidationError(f"Market proxy {ctx['market_proxy']} for {t} is not in the manifest")
        if ctx.get("sector_proxy") and ctx["sector_proxy"] not in manifest_tickers:
            raise ValidationError(f"Sector proxy {ctx['sector_proxy']} for {t} is not in the manifest")

    return manifest, spec


def load_ticker_df(manifest: DatasetManifest, ticker: str) -> pd.DataFrame:
    """Load and canonicalize the CSV for ``ticker`` from the manifest."""
    base_dir = getattr(manifest, "_base_dir", None)
    if base_dir is None:
        raise ValidationError("Manifest was not loaded from a path; cannot resolve CSV files")
    entry = next(e for e in manifest.entries if e.ticker == ticker)
    csv_path = Path(base_dir) / entry.path
    df = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
    return canonicalize_bars(df)


def context_for_signal(
    as_of: Any,
    ticker_df: pd.DataFrame,
    spec: ShortContextSpec,
    ticker: str,
    market_df: pd.DataFrame,
    sector_df: pd.DataFrame | None = None,
) -> ShortTermMarketContext:
    """Compute the point-in-time market context for a signal at ``as_of``.

    ``as_of`` may be a pandas Timestamp or timezone-aware datetime.
    """
    if isinstance(as_of, pd.Timestamp):
        as_of_dt = as_of.to_pydatetime()
    else:
        as_of_dt = as_of

    ctx = spec.ticker_context[ticker]
    return compute_short_term_context(
        as_of=as_of_dt,
        ticker_df=ticker_df,
        market_proxy=ctx["market_proxy"],
        market_df=market_df,
        sector_proxy=ctx.get("sector_proxy"),
        sector_df=sector_df,
    )
