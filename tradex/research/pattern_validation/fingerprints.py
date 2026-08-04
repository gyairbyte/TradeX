"""Development-only fingerprint construction from locked offline snapshots."""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from tradex.signals.indicators import add_indicators

from .models import Fingerprint, StudySpec, ValidationError, _canonical_json_sha256


def _find_events(
    df: pd.DataFrame,
    *,
    runup_pct: float,
    decline_pct: float,
    move_days: int,
    lookback: int,
    event_type: str,
) -> list[int]:
    """Return integer start positions for non-overlapping events of ``event_type``."""
    n = len(df)
    if n < move_days + lookback + 1:
        return []

    closes = df["close"].values
    positions: list[int] = []
    i = lookback  # event start needs enough pre-history to later extract window
    max_i = n - move_days
    while i < max_i:
        entry = closes[i]
        if entry == 0:
            i += 1
            continue
        exit_ = closes[i + move_days]
        pct = (exit_ - entry) / entry * 100.0

        if event_type == "runup" and pct >= runup_pct:
            positions.append(i)
            i += move_days  # skip overlapping event horizon
        elif event_type == "decline" and pct <= -decline_pct:
            positions.append(i)
            i += move_days
        else:
            i += 1
    return positions


def _normalize_window(window: pd.DataFrame) -> dict[str, list[float]] | None:
    """Normalize a pre-event window to a comparable shape vector."""
    if len(window) < 5 or window["close"].iloc[0] == 0:
        return None

    base_close = window["close"].iloc[0]
    base_vol_avg = window["volume"].mean()
    if base_vol_avg == 0:
        return None

    return {
        "price_pct":    ((window["close"] / base_close) - 1).mul(100).round(4).tolist(),
        "volume_ratio": (window["volume"] / base_vol_avg).round(4).tolist(),
        "rsi":          window["rsi"].round(2).tolist(),
        "macd_diff":    window["macd_diff"].round(4).tolist(),
        "bb_width":     window["bb_width"].round(4).tolist(),
    }


def _config_hash(spec: StudySpec) -> str:
    """SHA-256 of the fingerprint-relevant configuration subset."""
    cfg = {
        "profile": spec.profile,
        "runup_pct": spec.runup_pct,
        "decline_pct": spec.decline_pct,
        "move_days": spec.move_days,
        "lookback_days": spec.lookback_days,
        "min_events": spec.min_events,
        "series_weights": dict(sorted(spec.series_weights.items())),
        "universe_hash": spec.universe_hash,
    }
    return _canonical_json_sha256(cfg)


def build_development_fingerprints(
    bars: dict[str, pd.DataFrame],
    spec: StudySpec,
) -> tuple[dict[str, Fingerprint], pd.DataFrame]:
    """Build one immutable development-only fingerprint per event type.

    Returns a mapping ``{event_type: Fingerprint}`` and a DataFrame of all
    development events for artifact serialization.
    """
    split = spec.splits.get("development")
    if split is None:
        raise ValidationError("development split is required to build fingerprints")

    cfg_hash = _config_hash(spec)
    development_events: list[dict[str, Any]] = []
    windows_by_event: dict[str, list[dict[str, list[float]]]] = {"runup": [], "decline": []}

    for ticker, df in sorted(bars.items()):
        # Restrict to development split.
        mask = (df.index >= pd.Timestamp(split.start, tz="UTC")) & (df.index <= pd.Timestamp(split.end, tz="UTC"))
        split_df = df[mask].copy()
        if len(split_df) < spec.lookback_days + spec.move_days + 5:
            continue

        split_df = add_indicators(split_df)
        # Drop rows with NaN in series we need; indicator warmup will trim the start.
        required_cols = ["open", "high", "low", "close", "volume", "rsi", "macd_diff", "bb_width"]
        split_df = split_df.dropna(subset=required_cols)
        if len(split_df) < spec.lookback_days + spec.move_days + 1:
            continue

        for event_type in spec.event_types:
            positions = _find_events(
                split_df,
                runup_pct=spec.runup_pct,
                decline_pct=spec.decline_pct,
                move_days=spec.move_days,
                lookback=spec.lookback_days,
                event_type=event_type,
            )
            for pos in positions:
                window = split_df.iloc[pos - spec.lookback_days : pos]
                if len(window) != spec.lookback_days:
                    continue
                normalized = _normalize_window(window)
                if normalized is None:
                    continue
                event_date = split_df.index[pos].to_pydatetime().date()
                event_close = float(split_df["close"].iloc[pos])
                future_close = float(split_df["close"].iloc[pos + spec.move_days])
                move_pct = (future_close - event_close) / event_close * 100.0
                development_events.append({
                    "ticker": ticker,
                    "event_type": event_type,
                    "event_date": event_date.isoformat(),
                    "event_close": event_close,
                    "future_close": future_close,
                    "move_pct": round(move_pct, 4),
                    "profile": spec.profile,
                    "lookback_days": spec.lookback_days,
                    "move_days": spec.move_days,
                    "config_hash": cfg_hash,
                })
                windows_by_event[event_type].append(normalized)

    if not development_events:
        # Allow an empty/inconclusive study when no development events are available.
        return {}, pd.DataFrame()

    fingerprints: dict[str, Fingerprint] = {}
    for event_type in spec.event_types:
        windows = windows_by_event[event_type]
        if not windows:
            continue

        n_events = len(windows)
        if n_events < spec.min_events:
            continue
        lookback = spec.lookback_days
        series: dict[str, dict[str, list[float]]] = {}
        for key in sorted(spec.series_weights.keys()):
            values = [w[key] for w in windows]
            # Truncate to lookback length and pad if needed.
            arrays = []
            for v in values:
                if len(v) >= lookback:
                    arrays.append(v[-lookback:])
                elif len(v) > 0:
                    pad = [v[0]] * (lookback - len(v))
                    arrays.append(pad + v)
            if not arrays:
                continue
            matrix = np.array(arrays, dtype=float)
            mean = np.nanmean(matrix, axis=0).round(4).tolist()
            std = np.nanstd(matrix, axis=0).round(4).tolist()
            arr_mean = np.array(mean)
            arr_std = np.array(std)
            upper = (arr_mean + arr_std).round(4).tolist()
            lower = (arr_mean - arr_std).round(4).tolist()
            series[key] = {"mean": mean, "std": std, "upper": upper, "lower": lower}

        # Collect event dates for metadata.
        et_events = [e for e in development_events if e["event_type"] == event_type]
        dates = sorted({date.fromisoformat(e["event_date"]) for e in et_events})
        tickers_used = sorted({e["ticker"] for e in et_events})

        fp = Fingerprint(
            event_type=event_type,
            profile=spec.profile,
            source=spec.provider,
            n_events=n_events,
            ticker_count=len(tickers_used),
            lookback_days=lookback,
            earliest_event_date=dates[0] if dates else None,
            latest_event_date=dates[-1] if dates else None,
            config_hash=cfg_hash,
            series=series,
        )
        fingerprints[event_type] = fp

    events_df = pd.DataFrame(development_events)
    if not events_df.empty:
        events_df = events_df.sort_values(["event_type", "ticker", "event_date"]).reset_index(drop=True)
    return fingerprints, events_df
