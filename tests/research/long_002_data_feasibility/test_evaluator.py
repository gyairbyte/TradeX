"""Deterministic evaluator regression tests for LONG-002B disposition gating."""
from __future__ import annotations

from tradex.research.long_002_data_feasibility.evaluator import (
    FamilyEvidence,
    evaluate_family,
    evaluate_overall,
)


def test_family_not_promoted_without_minimum_contract() -> None:
    min_contract = {
        "one_complete_dev_year_plus_prior_history": True,
        "daily_bar_integrity_compatible_with_99pct_trailing_year": True,
        "no_unresolved_duplicates": True,
        "no_unresolved_malformed_rows": True,
        "explicit_raw_as_traded_policy": True,
        "explicit_split_adjusted_policy": True,
        "reconstructable_split_handling": True,
        "stable_identity_join": True,
    }
    evidence = FamilyEvidence(
        family="daily_market_data",
        flags={"explicit_raw_as_traded_policy": True},
    )
    disp, conf, blockers, _ = evaluate_family("daily_market_data", min_contract, evidence, any_provider_attempted=True)
    assert disp == "not_supported"
    assert conf == "limited_but_usable_evidence"
    assert any("minimum_usable_contract" in b for b in blockers)
    assert any("one_complete_dev_year_plus_prior_history" in b for b in blockers)


def test_family_promoted_when_minimum_contract_satisfied() -> None:
    min_contract = {
        "one_complete_dev_year_plus_prior_history": True,
        "daily_bar_integrity_compatible_with_99pct_trailing_year": True,
        "no_unresolved_duplicates": True,
        "no_unresolved_malformed_rows": True,
        "explicit_raw_as_traded_policy": True,
        "explicit_split_adjusted_policy": True,
        "reconstructable_split_handling": True,
        "stable_identity_join": True,
    }
    evidence = FamilyEvidence(
        family="daily_market_data",
        flags={k: True for k in min_contract},
    )
    disp, conf, blockers, _ = evaluate_family("daily_market_data", min_contract, evidence, any_provider_attempted=True)
    assert disp == "supported_with_documented_limitations"
    assert conf == "limited_but_usable_evidence"
    assert blockers == []


def test_successful_http_response_cannot_promote_without_min_contract() -> None:
    min_contract = {
        "ciK_identity_for_probe_issuers": True,
        "filing_acceptance_time_controls_availability": True,
        "viable_non_index_market_cap_pathway": True,
        "missing_facts_remain_null": True,
    }
    # Payload present (submissions and facts returned) but the PIT market-cap
    # pathway has not been demonstrated, so the family is not promoted.
    evidence = FamilyEvidence(
        family="issuer_fundamentals_and_shares",
        flags={
            "ciK_identity_for_probe_issuers": True,
            "filing_acceptance_time_controls_availability": False,
            "viable_non_index_market_cap_pathway": False,
            "missing_facts_remain_null": True,
        },
    )
    disp, conf, blockers, _ = evaluate_family(
        "issuer_fundamentals_and_shares", min_contract, evidence, any_provider_attempted=True,
    )
    assert disp == "not_supported"
    assert conf == "limited_but_usable_evidence"
    assert blockers


def test_unexercised_preferred_provider_is_not_capability_failure() -> None:
    min_contract = {"one_complete_dev_year_plus_prior_history": True}
    evidence = FamilyEvidence(family="daily_market_data", flags={})
    disp, conf, blockers, limitations = evaluate_family(
        "daily_market_data", min_contract, evidence, any_provider_attempted=False,
    )
    assert disp == "not_supported"
    assert conf == "limited_but_usable_evidence"
    # The record should not claim an unsupported provider capability; it should
    # report the attempt as unverified.
    assert any("provider attempt" in lim.lower() for lim in limitations)
    assert not any("unsupported" in b.lower() for b in blockers)


def test_unsupported_mandatory_family_blocks_overall() -> None:
    families = [
        ("daily_market_data", "supported_with_documented_limitations"),
        ("security_master_and_corporate_actions", "supported_with_documented_limitations"),
        ("issuer_fundamentals_and_shares", "supported_with_documented_limitations"),
        ("earnings_event_timing", "not_supported"),
    ]
    overall, confidence = evaluate_overall(families)
    assert overall == "not_supported"
    assert confidence == "limited_but_usable_evidence"


def test_overall_supported_only_when_all_families_supported() -> None:
    families = [
        ("daily_market_data", "supported"),
        ("security_master_and_corporate_actions", "supported"),
        ("issuer_fundamentals_and_shares", "supported"),
        ("earnings_event_timing", "supported"),
    ]
    overall, confidence = evaluate_overall(families)
    assert overall == "supported"
    assert confidence == "moderate_evidence"


def test_overall_not_supported_when_any_family_invalid() -> None:
    families = [
        ("daily_market_data", "supported"),
        ("security_master_and_corporate_actions", "invalid_evidence"),
        ("issuer_fundamentals_and_shares", "supported"),
        ("earnings_event_timing", "supported"),
    ]
    overall, confidence = evaluate_overall(families)
    assert overall == "not_supported"
    assert confidence == "invalid_evidence"


def test_overall_amendment_required_when_mandatory_family_not_supported() -> None:
    """A mandatory family whose minimum is not satisfied blocks LONG-002C.

    This test freezes the blocking/amendment rule: without an explicit
    approved amendment, an unsupported mandatory family yields an overall
    `not_supported` disposition.
    """
    families = [
        ("daily_market_data", "supported_with_documented_limitations"),
        ("security_master_and_corporate_actions", "supported_with_documented_limitations"),
        ("issuer_fundamentals_and_shares", "supported_with_documented_limitations"),
        ("earnings_event_timing", "not_supported"),
    ]
    overall, _ = evaluate_overall(families)
    assert overall == "not_supported"
