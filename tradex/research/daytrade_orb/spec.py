"""Locked specification loader and SHA-256 verifier for DAYTRADE-003B/003C."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOCKED_003B_SPEC_SHA256 = (
    "62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0"
)
LOCKED_003C_RESOLUTION_SHA256 = (
    "20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6"
)


class SpecError(ValueError):
    """Raised when the study specification fails validation or cryptographic hash checks."""


@dataclass(frozen=True)
class EffectiveORBSpec:
    """Strongly typed representation of the effective DAYTRADE-003 research configuration."""

    task_id: str
    strategy_id: str
    upstream_task_id: str
    upstream_spec_sha256: str
    resolution_spec_sha256: str

    @property
    def upstream_strategy_id(self) -> str:
        return self.strategy_id
    base_commit_sha: str
    price_threshold: float
    adv14_threshold: float
    atr14_threshold: float
    rv_threshold: float
    top_n: int
    adv_lookback_sessions: int
    atr_lookback_sessions: int
    rv_lookback_sessions: int
    initial_equity: float
    risk_fraction: float
    leverage_cap: float
    stop_loss_atr_mult: float
    commission_per_share: float
    slippage_bps_a: float
    slippage_bps_b: float
    slippage_bps_c: float
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence_level_pct: float
    min_sessions_for_sufficiency: int
    min_trades_for_sufficiency: int
    min_securities_for_sufficiency: int
    raw_003b_dict: dict[str, Any]
    raw_003c_dict: dict[str, Any]


def sha256_of_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file from its exact bytes on disk."""
    if not path.is_file():
        raise SpecError(f"Target file does not exist: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_effective_spec(repo_root: Path | None = None) -> EffectiveORBSpec:
    """Load and cryptographically verify both DAYTRADE-003B and DAYTRADE-003C specifications.

    Fails closed if either upstream or resolution spec has drifted from its locked hash.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    spec_003b_path = repo_root / "docs" / "research" / "specs" / "DAYTRADE-003B-ORB-v1.json"
    spec_003c_path = (
        repo_root / "docs" / "research" / "specs" / "DAYTRADE-003C-ORB-RESOLUTION-v1.json"
    )

    if not spec_003b_path.exists():
        raise SpecError(f"Missing locked upstream spec at {spec_003b_path}")
    if not spec_003c_path.exists():
        raise SpecError(f"Missing resolution spec at {spec_003c_path}")

    actual_003b_hash = sha256_of_file(spec_003b_path)
    if actual_003b_hash != LOCKED_003B_SPEC_SHA256:
        raise SpecError(
            f"Upstream DAYTRADE-003B spec hash drift detected! "
            f"Expected {LOCKED_003B_SPEC_SHA256}, got {actual_003b_hash}"
        )

    actual_003c_hash = sha256_of_file(spec_003c_path)
    if actual_003c_hash != LOCKED_003C_RESOLUTION_SHA256:
        raise SpecError(
            f"Resolution DAYTRADE-003C spec hash drift detected! "
            f"Expected {LOCKED_003C_RESOLUTION_SHA256}, got {actual_003c_hash}"
        )

    spec_003b_dict = json.loads(spec_003b_path.read_text(encoding="utf-8"))
    spec_003c_dict = json.loads(spec_003c_path.read_text(encoding="utf-8"))

    # Extract locked parameters
    filters = spec_003b_dict["eligibility_filters"]
    price_th = float(filters["price_filter"]["threshold"])
    adv_th = float(filters["average_daily_volume_filter"]["threshold"])
    atr_th = float(filters["atr_filter"]["threshold"])

    rv_spec = spec_003b_dict["relative_volume_ranking"]
    rv_th = float(rv_spec["threshold_value"])
    top_n = int(rv_spec["top_n_selection"])
    rv_lookback = int(rv_spec["lookback_sessions"])

    sizing = spec_003b_dict["strategy_mechanics"]["position_sizing"]
    initial_capital = float(sizing["initial_capital_usd"])
    max_leverage = float(sizing["max_leverage_ratio"])
    risk_frac = float(sizing["source_reported_deployed_capital_loss_pct"]) / 100.0

    costs = spec_003c_dict["transaction_costs_and_scenarios"]
    comm_rate = float(costs["scenario_b_tradex_primary"]["commission_per_share_usd"])
    slip_a = float(costs["scenario_a_source_comparison"]["adverse_slippage_bps_per_side"])
    slip_b = float(costs["scenario_b_tradex_primary"]["adverse_slippage_bps_per_side"])
    slip_c = float(costs["scenario_c_stress"]["adverse_slippage_bps_per_side"])

    bs_cfg = spec_003c_dict["metrics_and_bootstrap_contract"]["bootstrap_parameters"]
    resamples = int(bs_cfg["resamples"])
    seed = int(bs_cfg["seed"])
    conf_level = float(bs_cfg["confidence_level_pct"])

    suff = spec_003b_dict["validation_gates"]["evidence_sufficiency_gate"]
    min_sessions = int(suff["min_regular_sessions_with_candidates"])
    min_trades = int(suff["min_triggered_trades_total"])
    min_secs = int(suff["min_unique_securities_traded"])

    return EffectiveORBSpec(
        task_id=spec_003c_dict["task_id"],
        strategy_id=spec_003c_dict["upstream_strategy_id"],
        upstream_task_id=spec_003c_dict["upstream_task_id"],
        upstream_spec_sha256=LOCKED_003B_SPEC_SHA256,
        resolution_spec_sha256=LOCKED_003C_RESOLUTION_SHA256,
        base_commit_sha=spec_003c_dict["base_commit_sha"],
        price_threshold=price_th,
        adv14_threshold=adv_th,
        atr14_threshold=atr_th,
        rv_threshold=rv_th,
        top_n=top_n,
        adv_lookback_sessions=14,
        atr_lookback_sessions=14,
        rv_lookback_sessions=rv_lookback,
        initial_equity=initial_capital,
        risk_fraction=risk_frac,
        leverage_cap=max_leverage,
        stop_loss_atr_mult=0.10,
        commission_per_share=comm_rate,
        slippage_bps_a=slip_a,
        slippage_bps_b=slip_b,
        slippage_bps_c=slip_c,
        bootstrap_resamples=resamples,
        bootstrap_seed=seed,
        bootstrap_confidence_level_pct=conf_level,
        min_sessions_for_sufficiency=min_sessions,
        min_trades_for_sufficiency=min_trades,
        min_securities_for_sufficiency=min_secs,
        raw_003b_dict=spec_003b_dict,
        raw_003c_dict=spec_003c_dict,
    )
