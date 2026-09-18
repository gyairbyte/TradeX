"""Contract v2 independent evidence completeness test suite.

Verifies:
1. Exact integer arithmetic for family completeness.
2. Slot-level aggregation preserving exact counts.
3. Completeness tiers (COMPLETE, PARTIAL, SPARSE).
4. All-not-applicable family produces COMPLETE tier with ratio 1.0.
5. Invariant: Pooled completeness ratio NEVER masks a sparse family tier.
6. Validation errors on invalid count configurations.
"""

import pytest

from tradex.pit.models import (
    PITEvidenceCompletenessTier,
    PITFamilyCompleteness,
)
from tradex.pit.ops import (
    aggregate_slot_completeness,
    compute_family_completeness,
)


class TestV2EvidenceCompletenessReadModel:
    """Test mathematical and tier properties of the evidence completeness read model."""

    def test_complete_tier_exact_ratio(self) -> None:
        comp = compute_family_completeness(
            "earnings",
            requested_n=10,
            known_n=10,
            not_applicable_n=0,
        )
        assert comp.tier == PITEvidenceCompletenessTier.COMPLETE
        assert comp.ratio == 1.0
        assert comp.pct == 100.0
        assert comp.applicable_n == 10
        assert comp.known_n == 10
        assert comp.all_not_applicable is False

    def test_partial_tier(self) -> None:
        comp = compute_family_completeness(
            "earnings",
            requested_n=10,
            known_n=6,
            not_applicable_n=2,  # applicable_n = 8
        )
        assert comp.tier == PITEvidenceCompletenessTier.PARTIAL
        assert comp.applicable_n == 8
        assert comp.known_n == 6
        assert comp.ratio == 0.75
        assert comp.pct == 75.0

    def test_sparse_tier(self) -> None:
        comp = compute_family_completeness(
            "reference",
            requested_n=10,
            known_n=0,
            not_applicable_n=0,
        )
        assert comp.tier == PITEvidenceCompletenessTier.SPARSE
        assert comp.applicable_n == 10
        assert comp.known_n == 0
        assert comp.ratio == 0.0
        assert comp.pct == 0.0

    def test_all_not_applicable_earnings_family(self) -> None:
        """When 100% of symbols are not_applicable, tier is COMPLETE and ratio is 1.0."""
        comp = compute_family_completeness(
            "earnings",
            requested_n=15,
            known_n=0,
            not_applicable_n=15,  # applicable_n = 0
        )
        assert comp.tier == PITEvidenceCompletenessTier.COMPLETE
        assert comp.ratio == 1.0
        assert comp.pct == 100.0
        assert comp.applicable_n == 0
        assert comp.known_n == 0
        assert comp.all_not_applicable is True

    def test_slot_aggregation_both_complete(self) -> None:
        e = compute_family_completeness("earnings", requested_n=30, known_n=30, not_applicable_n=0)
        r = compute_family_completeness("reference", requested_n=30, known_n=30)
        slot = aggregate_slot_completeness(e, r)

        assert slot.overall_tier == PITEvidenceCompletenessTier.COMPLETE
        assert slot.total_applicable_n == 60
        assert slot.total_known_n == 60
        assert slot.pooled_ratio == 1.0
        assert slot.pooled_pct == 100.0

    def test_sparse_family_never_masked_by_pooled_ratio(self) -> None:
        """Crucial invariant: If reference is 100% COMPLETE but earnings is SPARSE,

        overall tier MUST be SPARSE even if pooled_ratio is high (e.g. 75%).
        """
        # Earnings: 10 applicable, 0 known -> SPARSE
        e = compute_family_completeness("earnings", requested_n=10, known_n=0, not_applicable_n=0)
        assert e.tier == PITEvidenceCompletenessTier.SPARSE

        # Reference: 30 applicable, 30 known -> COMPLETE
        r = compute_family_completeness("reference", requested_n=30, known_n=30)
        assert r.tier == PITEvidenceCompletenessTier.COMPLETE

        slot = aggregate_slot_completeness(e, r)

        # total_applicable_n = 40, total_known_n = 30 -> pooled_ratio = 0.75 (75%)
        assert slot.total_applicable_n == 40
        assert slot.total_known_n == 30
        assert slot.pooled_ratio == 0.75
        assert slot.pooled_pct == 75.0

        # Tier MUST be SPARSE, not PARTIAL, because earnings evidence is sparse!
        assert slot.overall_tier == PITEvidenceCompletenessTier.SPARSE

    def test_slot_aggregation_partial(self) -> None:
        e = compute_family_completeness("earnings", requested_n=10, known_n=5)
        r = compute_family_completeness("reference", requested_n=10, known_n=8)
        slot = aggregate_slot_completeness(e, r)

        assert slot.overall_tier == PITEvidenceCompletenessTier.PARTIAL
        assert slot.total_applicable_n == 20
        assert slot.total_known_n == 13
        assert slot.pooled_ratio == 0.65
        assert slot.pooled_pct == 65.0

    def test_validation_rejects_negative_or_exceeding_counts(self) -> None:
        with pytest.raises(ValueError, match="known_n must satisfy 0 <= known_n <= applicable_n"):
            PITFamilyCompleteness(
                tier=PITEvidenceCompletenessTier.SPARSE,
                ratio=0.0,
                pct=0.0,
                applicable_n=10,
                known_n=-1,
                all_not_applicable=False,
            )

        with pytest.raises(ValueError, match="known_n must satisfy 0 <= known_n <= applicable_n"):
            PITFamilyCompleteness(
                tier=PITEvidenceCompletenessTier.COMPLETE,
                ratio=1.1,
                pct=110.0,
                applicable_n=10,
                known_n=11,
                all_not_applicable=False,
            )
