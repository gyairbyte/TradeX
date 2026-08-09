"""Locked INTRA-001 specification loading and verification."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import CostScenario

_INTRA_001_SPEC_SHA256 = "09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464"
_DEFAULT_SPEC_PATH = Path(__file__).resolve().parents[3] / "docs/research/specs/INTRA-001-v1.json"


class SpecError(Exception):
    """Raised when the locked spec cannot be loaded or its hash mismatches."""


def _parse_hh_mm(value: str) -> time:
    match = re.search(r"(\d{1,2}):(\d{2})", value)
    if not match:
        raise SpecError(f"Cannot parse time from {value!r}")
    return time(int(match.group(1)), int(match.group(2)))


def _parse_multiplier(formula: str) -> float:
    match = re.search(r"([0-9]*\.?[0-9]+)\s*\*\s*risk_per_share", formula)
    if not match:
        raise SpecError(f"Cannot parse target multiple from {formula!r}")
    return float(match.group(1))


@dataclass(frozen=True)
class IntradaySpec:
    """Relevant locked values from INTRA-001-v1.json."""

    raw: dict[str, Any]
    path: Path
    sha256: str

    @property
    def session_start_time(self) -> time:
        return _parse_hh_mm(str(self.raw["session"]["regular_session_start"]))

    @property
    def session_end_time(self) -> time:
        return _parse_hh_mm(str(self.raw["session"]["regular_session_end"]))

    @property
    def bar_interval_minutes(self) -> int:
        return 5

    @property
    def exclude_early_close(self) -> bool:
        return bool(self.raw["session"]["exclude_early_close_sessions"])

    @property
    def opening_drive_min_return_pct(self) -> float:
        return float(
            self.raw["opening_drive_qualification"][
                "return_from_session_open_to_10am_close_min_pct"
            ]
        )

    @property
    def opening_drive_min_volume_multiple(self) -> float:
        return float(
            self.raw["opening_drive_qualification"][
                "cumulative_volume_930_to_10am_min_multiple_of_prior_20_same_window_median"
            ]
        )

    @property
    def reclaim_search_start_time(self) -> time:
        # First completed bar after 10:00 AM = bar_start 10:00.
        return time(10, 0)

    @property
    def reclaim_search_end_time(self) -> time:
        # "five-minute bar completing at 11:30 AM Eastern" -> bar_start 11:25.
        return time(11, 30)

    @property
    def time_exit_time(self) -> time:
        return _parse_hh_mm(str(self.raw["exit_policy"]["time_exit_time"]))

    @property
    def primary_slippage_bps(self) -> float:
        return float(self.raw["costs"]["primary"]["entry_slippage_bps"])

    @property
    def primary_commission_bps(self) -> float:
        return float(self.raw["costs"]["primary"]["commission_bps"])

    @property
    def sensitivity_scenarios(self) -> tuple[float, ...]:
        return tuple(float(v) for v in self.raw["costs"]["sensitivity_scenarios_bps_per_side"])

    @property
    def prior_close_min(self) -> float:
        return float(self.raw["liquidity"]["prior_close_min_usd"])

    @property
    def prior_dollar_volume_min(self) -> float:
        return float(self.raw["liquidity"]["prior_20_sessions_median_dollar_volume_min_usd"])

    @property
    def target_multiple(self) -> float:
        return _parse_multiplier(str(self.raw["target"]["target_price"]))

    def primary_cost_scenario(self) -> CostScenario:
        from .models import CostScenario

        return CostScenario(
            name="primary_5bps",
            entry_slippage_bps=self.primary_slippage_bps,
            exit_slippage_bps=self.primary_slippage_bps,
            entry_commission_bps=self.primary_commission_bps,
            exit_commission_bps=self.primary_commission_bps,
        )

    def all_cost_scenarios(self) -> list[CostScenario]:
        from .models import CostScenario

        scenarios = []
        for bps in self.sensitivity_scenarios:
            scenarios.append(
                CostScenario(
                    name=f"slippage_{bps:g}bps",
                    entry_slippage_bps=bps,
                    exit_slippage_bps=bps,
                    entry_commission_bps=0.0,
                    exit_commission_bps=0.0,
                )
            )
        return scenarios


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()


def load_spec(path: str | Path | None = None) -> tuple[IntradaySpec, bytes]:
    """Load the locked INTRA-001 spec and verify its SHA-256."""
    if path is None:
        path = _DEFAULT_SPEC_PATH
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SpecError(f"INTRA-001 spec not found: {p}")
    raw_bytes = p.read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != _INTRA_001_SPEC_SHA256:
        raise SpecError(
            f"INTRA-001 spec SHA-256 mismatch: expected {_INTRA_001_SPEC_SHA256}, got {actual_sha}"
        )
    data = json.loads(raw_bytes.decode("utf-8"))
    return IntradaySpec(raw=data, path=p, sha256=actual_sha), raw_bytes
