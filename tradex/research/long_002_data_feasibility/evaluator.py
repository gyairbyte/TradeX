"""Deterministic evaluator mapping provider evidence to LONG-002B dispositions.

A family is promoted only when all of its locked `minimum_usable_contract`
booleans are satisfied by recorded evidence. Unexercised preferred-provider
capabilities are recorded as `unverified` (not provider failures). A mandatory
family that fails its minimum makes the overall disposition `not_supported`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FamilyEvidence:
    """Typed evidence bag for a single data family."""

    family: str
    flags: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "flags": self.flags,
            "notes": self.notes,
            "unverified": self.unverified,
        }


def _unmet_flags(min_contract: dict[str, Any], flags: dict[str, bool]) -> list[str]:
    unmet: list[str] = []
    for key, required in min_contract.items():
        if required and not flags.get(key):
            unmet.append(key)
    return unmet


def evaluate_family(
    family_name: str,
    min_contract: dict[str, Any],
    evidence: FamilyEvidence,
    any_provider_attempted: bool,
) -> tuple[str, str, list[str], list[str]]:
    """Return (disposition, evidence_confidence, blockers, limitations) for a family."""
    unmet = _unmet_flags(min_contract, evidence.flags)
    limitations = list(evidence.notes)
    blockers: list[str] = []

    if unmet:
        for key in unmet:
            blockers.append(f"minimum_usable_contract.{key} not satisfied")
        # If we never attempted a real provider call, label as unverified rather than
        # provider failure, but still downgrade the family to not_supported.
        if not any_provider_attempted:
            return "not_supported", "limited_but_usable_evidence", blockers, limitations + ["No provider attempt recorded for this family."]
        return "not_supported", "limited_but_usable_evidence", blockers, limitations

    # All minimums are met. Confidence is limited by the probe scope; never claim
    # strong evidence from a small bounded panel.
    if evidence.unverified:
        limitations.extend([f"Unverified capability: {u}" for u in evidence.unverified])
    return "supported_with_documented_limitations", "limited_but_usable_evidence", blockers, limitations


def evaluate_overall(
    family_results: list[tuple[str, str]],
    *,
    require_all_families: bool = True,
) -> tuple[str, str]:
    """Compute overall disposition and confidence from per-family dispositions.

    family_results is a list of (family_name, disposition).
    """
    dispositions = [d for _, d in family_results]
    if any(d in ("not_supported", "invalid_evidence") for d in dispositions):
        confidence = "invalid_evidence" if any(d == "invalid_evidence" for d in dispositions) else "limited_but_usable_evidence"
        return "not_supported", confidence
    if all(d == "supported" for d in dispositions):
        return "supported", "moderate_evidence"
    if all(d in ("supported", "supported_with_documented_limitations") for d in dispositions):
        return "supported_with_documented_limitations", "limited_but_usable_evidence"
    # Mixed state should not occur when the evaluator is used consistently,
    # but treat conservatively.
    return "not_supported", "limited_but_usable_evidence"
