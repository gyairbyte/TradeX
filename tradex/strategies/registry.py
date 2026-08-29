"""Neutral production strategy authorization registry and capability lookup (MVP-ARCH-001-R6).

Defines the single authoritative production strategy authorization boundary
and capability model for TradeX.

Supported capabilities:
- "journal_execution": Authorized to create executable Journal trade plans and records.
- "automatic_alerts": Authorized to generate automatic external market alert notifications.

Governance:
- APPROVED_PRODUCTION_STRATEGIES is code-reviewed, versioned, and Gary-approved.
- In this release, APPROVED_PRODUCTION_STRATEGIES is strictly EMPTY.
- Strategy promotion requires an explicit, separate Gary-approved PR.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED_CAPABILITIES: frozenset[str] = frozenset(
    {"journal_execution", "automatic_alerts"}
)

_STRATEGY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_STRATEGY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def validate_strategy_identity(strategy_id: str, strategy_version: str) -> None:
    """Validate strategy_id and strategy_version syntax according to R6 contract.

    Raises:
        TypeError: If strategy_id or strategy_version is not a str.
        ValueError: If strategy_id or strategy_version is empty, has leading/trailing
            whitespace, or does not match the canonical regex pattern.
    """
    if not isinstance(strategy_id, str):
        raise TypeError("strategy_id must be a str")
    if not strategy_id or strategy_id.strip() != strategy_id:
        raise ValueError(
            "strategy_id must be non-empty without leading or trailing whitespace"
        )
    if not _STRATEGY_ID_PATTERN.match(strategy_id):
        raise ValueError(
            f"strategy_id '{strategy_id}' does not match required pattern "
            "'^[a-z0-9][a-z0-9_-]{0,63}$'"
        )

    if not isinstance(strategy_version, str):
        raise TypeError("strategy_version must be a str")
    if not strategy_version or strategy_version.strip() != strategy_version:
        raise ValueError(
            "strategy_version must be non-empty without leading or trailing whitespace"
        )
    if not _STRATEGY_VERSION_PATTERN.match(strategy_version):
        raise ValueError(
            f"strategy_version '{strategy_version}' does not match required pattern "
            "'^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$'"
        )


@dataclass(frozen=True, slots=True)
class ApprovedProductionStrategy:
    """Immutable record for a production-approved strategy with explicit capabilities."""

    strategy_id: str
    strategy_version: str
    description: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        validate_strategy_identity(self.strategy_id, self.strategy_version)

        if not isinstance(self.description, str):
            raise TypeError("description must be a str")
        if not self.description or self.description.strip() != self.description:
            raise ValueError(
                "description must be non-empty without leading or trailing whitespace"
            )

        if not isinstance(self.capabilities, frozenset):
            raise TypeError("capabilities must be a frozenset[str]")
        for cap in self.capabilities:
            if not isinstance(cap, str):
                raise TypeError(f"capability '{cap}' must be a str")
        unknown_caps = self.capabilities - SUPPORTED_CAPABILITIES
        if unknown_caps:
            raise ValueError(
                f"capabilities contains unsupported capability value(s): {sorted(unknown_caps)}. "
                f"Supported capabilities are: {sorted(SUPPORTED_CAPABILITIES)}"
            )


# Authoritative central registry of approved production strategies.
# In R6-IMPL-0, this registry is strictly EMPTY. No strategy is authorized for
# journal execution or automatic alerts. Future promotion requires an explicit Gary-approved PR.
APPROVED_PRODUCTION_STRATEGIES: tuple[ApprovedProductionStrategy, ...] = ()


def has_production_strategy_capability(
    strategy_id: str,
    strategy_version: str,
    capability: str,
) -> bool:
    """Check if a strategy identity has a specific production capability at call time.

    Requirements:
    - Exact strategy_id match
    - Exact strategy_version match
    - Exact capability membership in the strategy's granted capabilities
    - Missing/unknown strategy -> False
    - Wrong version -> False
    - Capability not granted -> False
    - Unknown capability -> False
    - Empty registry -> False
    """
    if (
        not isinstance(strategy_id, str)
        or not isinstance(strategy_version, str)
        or not isinstance(capability, str)
    ):
        return False

    if capability not in SUPPORTED_CAPABILITIES:
        return False

    for strategy in APPROVED_PRODUCTION_STRATEGIES:
        if (
            strategy.strategy_id == strategy_id
            and strategy.strategy_version == strategy_version
        ):
            return capability in strategy.capabilities

    return False
