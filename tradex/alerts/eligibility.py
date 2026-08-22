"""Central, domain-level automatic-alert eligibility boundary (MVP-ARCH-001-R4).

Enforces fail-closed gating between market observations/threshold events and
automatic external market alert delivery (Discord / email).

Requirements:
- Unknown, missing, legacy, exploratory, rejected, research-only, archived,
  inconclusive, or otherwise non-approved inputs are ineligible for automatic
  external delivery.
- Exact production strategy authorization must be explicit via strategy_id and
  strategy_version in APPROVED_ACTIONABLE_STRATEGIES.
- The approved actionable strategy set is EMPTY in R4. No strategy is promoted
  or authorized as production-approved in this PR.
- Independent of UI, Streamlit, or presentation layers.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradex.alerts.models import AlertKey


@dataclass(frozen=True, slots=True)
class ApprovedActionableStrategy:
    """Immutable record for an approved actionable strategy authorized for alerts."""

    strategy_id: str
    strategy_version: str
    description: str


# Authoritative domain registry of approved actionable strategies authorized to
# generate automatic external market notifications.
# In R4, this registry is strictly EMPTY. No strategy is authorized for automatic
# external market alerts. Future promotion requires an explicit Gary-approved PR.
APPROVED_ACTIONABLE_STRATEGIES: tuple[ApprovedActionableStrategy, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertEligibilityResult:
    """Result of evaluating an automatic alert event for external delivery eligibility."""

    eligible: bool
    reason: str
    strategy_id: str | None = None
    strategy_version: str | None = None
    evidence_state: str | None = None


def check_automatic_alert_eligibility(
    key: AlertKey,
    *,
    strategy_id: str | None = None,
    strategy_version: str | None = None,
    evidence_state: str | None = None,
) -> AlertEligibilityResult:
    """Check if an automatic market alert event is eligible for external dispatch.

    Fail-closed rules:
    1. If strategy_id or strategy_version is missing / None -> ineligible.
    2. If evidence_state is not "production_approved" -> ineligible.
    3. Even if evidence_state == "production_approved", (strategy_id, strategy_version)
       MUST exist in APPROVED_ACTIONABLE_STRATEGIES.
    4. All current legacy heuristic, exploratory, rejected, research-only,
       archived, and inconclusive outputs (coil, confluence, gap, pattern, etc.)
       lack an approved strategy identity and fail closed.
    """
    if not isinstance(key, AlertKey):
        return AlertEligibilityResult(
            eligible=False,
            reason="Automatic market alerts gated: invalid or non-AlertKey object (fail-closed)",
        )

    if not strategy_id or not strategy_version:
        return AlertEligibilityResult(
            eligible=False,
            reason=(
                f"Automatic market alerts gated for {key.ticker} | {key.alert_type}: "
                "no approved actionable strategy identity (fail-closed)"
            ),
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence_state=evidence_state,
        )

    if evidence_state != "production_approved":
        return AlertEligibilityResult(
            eligible=False,
            reason=(
                f"Automatic market alerts gated for {key.ticker} | {key.alert_type}: "
                f"evidence state '{evidence_state}' is not production_approved (fail-closed)"
            ),
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence_state=evidence_state,
        )

    is_approved = any(
        s.strategy_id == strategy_id and s.strategy_version == strategy_version
        for s in APPROVED_ACTIONABLE_STRATEGIES
    )

    if not is_approved:
        return AlertEligibilityResult(
            eligible=False,
            reason=(
                f"Automatic market alerts gated for {key.ticker} | {key.alert_type}: "
                f"strategy '{strategy_id}:{strategy_version}' is not in approved actionable strategy registry (fail-closed)"
            ),
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence_state=evidence_state,
        )

    return AlertEligibilityResult(
        eligible=True,
        reason=(
            f"Approved actionable strategy '{strategy_id}:{strategy_version}' authorized "
            f"for automatic market alert delivery"
        ),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evidence_state=evidence_state,
    )
