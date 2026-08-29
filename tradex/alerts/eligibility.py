"""Central, domain-level automatic-alert eligibility boundary (MVP-ARCH-001-R4/R6).

Enforces fail-closed gating between market observations/threshold events and
automatic external market alert delivery (Discord / email).

Requirements:
- Unknown, missing, legacy, exploratory, rejected, research-only, archived,
  inconclusive, or otherwise non-approved inputs are ineligible for automatic
  external delivery.
- Exact production strategy authorization must be explicit via strategy_id and
  strategy_version holding the "automatic_alerts" capability in the central
  strategy registry (tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES).
- The approved production strategy registry is strictly EMPTY in this release.
- Independent of UI, Streamlit, or presentation layers.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradex.alerts.models import AlertKey
from tradex.strategies.registry import has_production_strategy_capability


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
    1. If key is not an AlertKey instance -> ineligible.
    2. If strategy_id or strategy_version is missing / None -> ineligible.
    3. If evidence_state is not "production_approved" -> ineligible.
    4. Even if evidence_state == "production_approved", (strategy_id, strategy_version)
       MUST have the "automatic_alerts" capability in the central production strategy registry.
    5. All current legacy heuristic, exploratory, rejected, research-only,
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

    if not has_production_strategy_capability(strategy_id, strategy_version, "automatic_alerts"):
        return AlertEligibilityResult(
            eligible=False,
            reason=(
                f"Automatic market alerts gated for {key.ticker} | {key.alert_type}: "
                f"strategy '{strategy_id}:{strategy_version}' lacks 'automatic_alerts' capability in central production strategy registry (fail-closed)"
            ),
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence_state=evidence_state,
        )

    return AlertEligibilityResult(
        eligible=True,
        reason=(
            f"Approved production strategy '{strategy_id}:{strategy_version}' authorized "
            f"for automatic market alert delivery"
        ),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evidence_state=evidence_state,
    )
