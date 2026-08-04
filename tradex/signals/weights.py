"""
User-tunable signal weights.

Each scorer is composed of N named components. The point value awarded when a
component fires is configurable. Tiered components (intraday volume / rsi)
award half the configured weight when only the weaker tier fires — that
matches the original 30/15 and 20/15 ratios.

Defaults reproduce the original hard-coded scoring exactly. Saved to JSON at
~/.tradex/weights.json so changes survive restarts.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from tradex.config import TradeXSettings, load_runtime_settings

WEIGHTS_PATH = Path("~/.tradex/weights.json")
_DEFAULT_WEIGHTS_PATH = WEIGHTS_PATH  # sentinel for legacy WEIGHTS_PATH monkeypatch detection


@dataclass
class IntradayWeights:
    volume_surge: int = 30
    bb_expansion: int = 20
    rsi_momentum: int = 20
    macd_crossover: int = 30


@dataclass
class ShortWeights:
    ema_structure: int = 25
    volume_confirmation: int = 20
    rsi_momentum: int = 20
    macd_positive: int = 20
    pullback_ema: int = 15


@dataclass
class LongWeights:
    secular_uptrend: int = 25
    rsi_healthy: int = 20
    volume_accumulation: int = 25
    macd_bullish: int = 15
    bb_coil: int = 15


@dataclass
class Weights:
    intraday: IntradayWeights
    short: ShortWeights
    long: LongWeights

    @classmethod
    def defaults(cls) -> "Weights":
        return cls(IntradayWeights(), ShortWeights(), LongWeights())

    def to_dict(self) -> dict:
        return {
            "intraday": asdict(self.intraday),
            "short": asdict(self.short),
            "long": asdict(self.long),
        }


# Component metadata for the UI — label, tooltip, what makes the signal fire.
# Keyed by (timeframe, field_name).
COMPONENT_LABELS: dict[tuple[str, str], dict[str, str]] = {
    ("intraday", "volume_surge"): {
        "label": "Volume surge",
        "help": "Awarded when current bar volume is ≥2x the 20-bar average. Half-credit at ≥1.5x.",
    },
    ("intraday", "bb_expansion"): {
        "label": "Bollinger Band expansion",
        "help": "Awarded when BB width is in the top 20% of its recent range — volatility breakout after a squeeze.",
    },
    ("intraday", "rsi_momentum"): {
        "label": "RSI momentum",
        "help": "Full credit when RSI is 55–75 (bullish without overbought). Half-credit for oversold bounce setup (25–45).",
    },
    ("intraday", "macd_crossover"): {
        "label": "MACD crossover",
        "help": "Awarded the bar the MACD histogram crosses from negative to positive.",
    },
    ("short", "ema_structure"): {
        "label": "EMA structure",
        "help": "Price > EMA20 > EMA50 — clean bullish stacking.",
    },
    ("short", "volume_confirmation"): {
        "label": "Volume confirmation",
        "help": "Current bar volume ≥ 1.3× the 20-bar average.",
    },
    ("short", "rsi_momentum"): {
        "label": "RSI momentum",
        "help": "RSI in the 50–70 momentum zone.",
    },
    ("short", "macd_positive"): {
        "label": "MACD positive",
        "help": "MACD line positive and histogram rising — trend expanding.",
    },
    ("short", "pullback_ema"): {
        "label": "Pullback to EMA20",
        "help": "Price within 1.5% of EMA20 while EMA20 > EMA50 — buy-the-dip in uptrend.",
    },
    ("long", "secular_uptrend"): {
        "label": "Secular uptrend",
        "help": "Price above EMA50 on weekly bars.",
    },
    ("long", "rsi_healthy"): {
        "label": "RSI healthy",
        "help": "RSI in 40–65 — trending without being overbought.",
    },
    ("long", "volume_accumulation"): {
        "label": "Volume accumulation",
        "help": "Average volume_ratio over the last 8 bars ≥ 1.15× — sustained accumulation.",
    },
    ("long", "macd_bullish"): {
        "label": "MACD bullish bias",
        "help": "MACD above signal line on weekly bars.",
    },
    ("long", "bb_coil"): {
        "label": "BB coil",
        "help": "BB width in the bottom 25% of its recent range — consolidation before breakout.",
    },
}


def _field_names(cls) -> list[str]:
    return [f.name for f in fields(cls)]


def _resolve_weights_path(settings: TradeXSettings | None = None) -> Path:
    """Return the weights file path from explicit settings or runtime env.

    Legacy tests may monkeypatch ``WEIGHTS_PATH``; if the module constant has
    been replaced with a different path, that path takes precedence. Otherwise
    the call-time runtime settings are loaded so ``TRADEX_WEIGHTS_PATH`` is
    honored.
    """
    if settings is not None:
        return settings.paths.weights
    if WEIGHTS_PATH is not _DEFAULT_WEIGHTS_PATH and str(WEIGHTS_PATH) != str(_DEFAULT_WEIGHTS_PATH):
        return WEIGHTS_PATH
    return load_runtime_settings().paths.weights


def load(*, settings: TradeXSettings | None = None) -> Weights:
    """Return saved weights or defaults if no saved file exists."""
    weights_path = _resolve_weights_path(settings)
    if not Path(str(weights_path)).expanduser().exists():
        return Weights.defaults()
    try:
        data = json.loads(Path(str(weights_path)).expanduser().read_text())
        intraday = IntradayWeights(**{k: v for k, v in data.get("intraday", {}).items() if k in _field_names(IntradayWeights)})
        short = ShortWeights(**{k: v for k, v in data.get("short", {}).items() if k in _field_names(ShortWeights)})
        long_ = LongWeights(**{k: v for k, v in data.get("long", {}).items() if k in _field_names(LongWeights)})
        return Weights(intraday, short, long_)
    except (json.JSONDecodeError, TypeError, ValueError):
        return Weights.defaults()


def save(weights: Weights, *, settings: TradeXSettings | None = None) -> None:
    weights_path = _resolve_weights_path(settings)
    path = Path(str(weights_path)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(weights.to_dict(), indent=2))


def reset_to_defaults(*, settings: TradeXSettings | None = None) -> Weights:
    defaults = Weights.defaults()
    save(defaults, settings=settings)
    return defaults


def max_possible(weights_section) -> int:
    """Sum the weights — useful for the UI to show 'max possible score' per timeframe."""
    return sum(asdict(weights_section).values())
