"""Local persistence and schema validation for reviewer labels in LONG-002D3A."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradex.research.long_002d3a.models import ReviewerLabel

ALLOWED_SURFACE_DECISIONS = {"surface", "do_not_surface"}
ALLOWED_VISIBLE_STATES = {"Enter Now", "Armed", "Qualified Waitlist", None}
ALLOWED_TARGET_PCTS = {10, 20, 30, None}
ALLOWED_HORIZONS = {5, 10, 21, None}
ALLOWED_ARCHETYPES = {"setup_archetype", "other", "unclear"}


def validate_reviewer_label_dict(data: dict[str, Any]) -> None:
    """Validate raw label dictionary against the locked reviewer schema."""
    case_id = data.get("case_id")
    if not case_id or not isinstance(case_id, str):
        raise ValueError(f"Invalid or missing case_id: {case_id}")

    stage = data.get("stage")
    if stage not in {"stage_a", "stage_b"}:
        raise ValueError(f"Invalid stage: {stage}; must be 'stage_a' or 'stage_b'")

    surf = data.get("surface_decision")
    if surf not in ALLOWED_SURFACE_DECISIONS:
        raise ValueError(f"Invalid surface_decision: {surf}")

    v_state = data.get("visible_state_if_surfaced")
    if surf == "surface" and v_state not in ALLOWED_VISIBLE_STATES:
        raise ValueError(f"Invalid visible_state_if_surfaced: {v_state}")
    if surf == "do_not_surface" and v_state is not None:
        raise ValueError("visible_state_if_surfaced must be null when surface_decision is do_not_surface")

    tgt = data.get("expected_target_pct")
    if tgt not in ALLOWED_TARGET_PCTS:
        raise ValueError(f"Invalid expected_target_pct: {tgt}")

    hor = data.get("expected_horizon_sessions")
    if hor not in ALLOWED_HORIZONS:
        raise ValueError(f"Invalid expected_horizon_sessions: {hor}")

    conf = data.get("qualitative_confidence")
    if conf not in {1, 2, 3, 4, 5}:
        raise ValueError(f"Invalid qualitative_confidence: {conf}; must be integer 1..5")

    arch = data.get("setup_archetype")
    if arch not in ALLOWED_ARCHETYPES:
        raise ValueError(f"Invalid setup_archetype: {arch}")

    max_v = data.get("max_validity_sessions")
    if max_v is not None and (not isinstance(max_v, int) or max_v < 1 or max_v > 5):
        raise ValueError(f"Invalid max_validity_sessions: {max_v}; must be integer 1..5 or null")

    reasons = data.get("positive_reasons", [])
    if not isinstance(reasons, list) or len(reasons) > 3:
        raise ValueError(f"positive_reasons must be list of at most 3 strings, got {reasons}")


class PilotReviewStore:
    """Manages reviewer label persistence, ensuring Stage A and Stage B separation."""

    def __init__(self, review_state_dir: Path) -> None:
        self.state_dir = review_state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _label_path(self, case_id: str, stage: str) -> Path:
        return self.state_dir / f"{case_id}_{stage}.json"

    def save_label(
        self,
        label: ReviewerLabel | dict[str, Any],
        allow_overwrite: bool = False,
    ) -> Path:
        """Persist a reviewer label record."""
        if isinstance(label, ReviewerLabel):
            label_dict = label.to_dict()
        else:
            label_dict = dict(label)

        validate_reviewer_label_dict(label_dict)

        case_id = str(label_dict["case_id"])
        stage = str(label_dict["stage"])
        target_path = self._label_path(case_id, stage)

        if target_path.exists() and not allow_overwrite:
            raise FileExistsError(
                f"Label for {case_id} ({stage}) already exists at {target_path}. "
                "Refusing silent overwrite without explicit allow_overwrite=True."
            )

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(label_dict, f, indent=2)

        return target_path

    def load_label(self, case_id: str, stage: str) -> dict[str, Any] | None:
        """Load a persisted label for a given case and stage."""
        p = self._label_path(case_id, stage)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_progress(self) -> dict[str, Any]:
        """Return review progress across all 24 cases."""
        stage_a_count = 0
        stage_b_count = 0
        fully_reviewed = 0

        for i in range(1, 25):
            cid = f"D3A-PILOT-{i:03d}"
            has_a = self._label_path(cid, "stage_a").exists()
            has_b = self._label_path(cid, "stage_b").exists()
            if has_a:
                stage_a_count += 1
            if has_b:
                stage_b_count += 1
            if has_a and has_b:
                fully_reviewed += 1

        return {
            "total_pilot_cases": 24,
            "stage_a_labeled_count": stage_a_count,
            "stage_b_labeled_count": stage_b_count,
            "fully_reviewed_count": fully_reviewed,
            "complete": fully_reviewed == 24,
        }
