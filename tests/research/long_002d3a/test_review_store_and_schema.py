"""Reviewer label schema validation and ReviewStore persistence tests for LONG-002D3A."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tradex.research.long_002d3a.review_store import (
    PilotReviewStore,
    validate_reviewer_label_dict,
)


@pytest.fixture
def tmp_review_dir(tmp_path: Path) -> Path:
    return tmp_path / "reviews"


@pytest.fixture
def valid_stage_a_dict() -> dict[str, Any]:
    return {
        "case_id": "D3A-PILOT-001",
        "stage": "stage_a",
        "surface_decision": "surface",
        "visible_state_if_surfaced": "Armed",
        "expected_target_pct": 10,
        "expected_horizon_sessions": 10,
        "qualitative_confidence": 4,
        "setup_archetype": "setup_archetype",
        "entry_plan": "Enter on breakout above T0 high",
        "trigger_or_zone": "105.00-105.50",
        "max_validity_sessions": 3,
        "gap_handling": "Reject if gap > 1.5%",
        "invalidation": "Close below SMA20",
        "positive_reasons": ["consolidation near highs", "relative volume surge"],
        "material_risks_counterarguments": "market resistance near benchmark high",
        "submitted_at_utc": "2026-10-04T12:00:00Z",
    }


@pytest.fixture
def valid_stage_b_dict() -> dict[str, Any]:
    return {
        "case_id": "D3A-PILOT-001",
        "stage": "stage_b",
        "surface_decision": "do_not_surface",
        "visible_state_if_surfaced": None,
        "expected_target_pct": None,
        "expected_horizon_sessions": None,
        "qualitative_confidence": 2,
        "setup_archetype": "other",
        "entry_plan": "",
        "trigger_or_zone": "",
        "max_validity_sessions": 5,
        "gap_handling": "",
        "invalidation": "Earnings scheduled inside horizon",
        "positive_reasons": [],
        "material_risks_counterarguments": "Imminent earnings risk makes risk/reward unfavorable",
        "submitted_at_utc": "2026-10-04T12:15:00Z",
    }


def test_validate_valid_labels(
    valid_stage_a_dict: dict[str, Any], valid_stage_b_dict: dict[str, Any]
) -> None:
    # Must not raise
    validate_reviewer_label_dict(valid_stage_a_dict)
    validate_reviewer_label_dict(valid_stage_b_dict)


def test_schema_rejects_invalid_surface_decision(valid_stage_a_dict: dict[str, Any]) -> None:
    bad = dict(valid_stage_a_dict, surface_decision="maybe")
    with pytest.raises(ValueError, match="Invalid surface_decision"):
        validate_reviewer_label_dict(bad)


def test_schema_rejects_invalid_visible_state(valid_stage_a_dict: dict[str, Any]) -> None:
    bad = dict(valid_stage_a_dict, visible_state_if_surfaced="InvalidState")
    with pytest.raises(ValueError, match="Invalid visible_state_if_surfaced"):
        validate_reviewer_label_dict(bad)


def test_schema_rejects_visible_state_when_do_not_surface(
    valid_stage_b_dict: dict[str, Any]
) -> None:
    bad = dict(valid_stage_b_dict, visible_state_if_surfaced="Armed")
    with pytest.raises(ValueError, match="visible_state_if_surfaced must be null"):
        validate_reviewer_label_dict(bad)


def test_schema_rejects_invalid_confidence(valid_stage_a_dict: dict[str, Any]) -> None:
    bad = dict(valid_stage_a_dict, qualitative_confidence=6)
    with pytest.raises(ValueError, match="Invalid qualitative_confidence"):
        validate_reviewer_label_dict(bad)


def test_schema_rejects_invalid_max_validity(valid_stage_a_dict: dict[str, Any]) -> None:
    bad = dict(valid_stage_a_dict, max_validity_sessions=6)
    with pytest.raises(ValueError, match="Invalid max_validity_sessions"):
        validate_reviewer_label_dict(bad)


def test_schema_rejects_too_many_positive_reasons(valid_stage_a_dict: dict[str, Any]) -> None:
    bad = dict(valid_stage_a_dict, positive_reasons=["r1", "r2", "r3", "r4"])
    with pytest.raises(ValueError, match="positive_reasons must be list of at most 3 strings"):
        validate_reviewer_label_dict(bad)


def test_store_saves_stage_a_and_stage_b_separately(
    tmp_review_dir: Path,
    valid_stage_a_dict: dict[str, Any],
    valid_stage_b_dict: dict[str, Any],
) -> None:
    store = PilotReviewStore(tmp_review_dir)

    path_a = store.save_label(valid_stage_a_dict)
    path_b = store.save_label(valid_stage_b_dict)

    assert path_a.name == "D3A-PILOT-001_stage_a.json"
    assert path_b.name == "D3A-PILOT-001_stage_b.json"
    assert path_a != path_b

    loaded_a = store.load_label("D3A-PILOT-001", "stage_a")
    assert loaded_a is not None
    assert loaded_a["surface_decision"] == "surface"

    loaded_b = store.load_label("D3A-PILOT-001", "stage_b")
    assert loaded_b is not None
    assert loaded_b["surface_decision"] == "do_not_surface"


def test_store_prevents_unauthorized_overwrite(
    tmp_review_dir: Path, valid_stage_a_dict: dict[str, Any]
) -> None:
    store = PilotReviewStore(tmp_review_dir)
    store.save_label(valid_stage_a_dict)

    with pytest.raises(FileExistsError, match="Refusing silent overwrite"):
        store.save_label(valid_stage_a_dict, allow_overwrite=False)

    # Allowed with explicit flag
    store.save_label(valid_stage_a_dict, allow_overwrite=True)


def test_store_tracks_review_progress(
    tmp_review_dir: Path,
    valid_stage_a_dict: dict[str, Any],
    valid_stage_b_dict: dict[str, Any],
) -> None:
    store = PilotReviewStore(tmp_review_dir)
    p0 = store.get_progress()
    assert p0["stage_a_labeled_count"] == 0
    assert p0["stage_b_labeled_count"] == 0
    assert p0["fully_reviewed_count"] == 0

    store.save_label(valid_stage_a_dict)
    p1 = store.get_progress()
    assert p1["stage_a_labeled_count"] == 1
    assert p1["stage_b_labeled_count"] == 0
    assert p1["fully_reviewed_count"] == 0

    store.save_label(valid_stage_b_dict)
    p2 = store.get_progress()
    assert p2["stage_a_labeled_count"] == 1
    assert p2["stage_b_labeled_count"] == 1
    assert p2["fully_reviewed_count"] == 1
