"""Contract v2 multi-attempt health & completeness test suite.

Verifies:
1. Operational health authoritative attempt selection:
   - Failed attempt superseded by succeeded retry -> HEALTHY.
   - Partial attempt superseded by succeeded retry -> HEALTHY.
   - Succeeded attempt followed by failed retry -> FAILED.
   - Dangling/stranded STARTED attempt -> DEGRADED (run_in_progress).
2. Independent evidence completeness selection:
   - Regression scenario: Older attempt is STARTED, newer attempt is SUCCEEDED:
     * Operational health is DEGRADED (failure_reason="run_in_progress").
     * Evidence completeness is derived strictly from the authoritative latest terminal run.
     * Completeness tier is COMPLETE (1.0).
     * Zero count contamination or double counting from the older attempt.
3. Missing due family:
   - Operational health is FAILED (failure_reason="missing_due_family").
   - Completeness derived from manifest expectation (known_n=0, tier SPARSE).
"""

from datetime import UTC, date, datetime
from pathlib import Path

from tradex.pit.models import (
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
    PITCaptureRun,
    PITEarningsSnapshot,
    PITEvidenceCompletenessTier,
    PITReferenceCaptureRun,
    build_known_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.ops import PITSlotHealthStatus, PITUniverseManifest, get_pit_slot_health
from tradex.pit.store import (
    create_capture_run,
    create_reference_capture_run,
    insert_earnings_snapshots,
)
from tradex.tracker import store


def _manifest() -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=2,
        universe_id="u-multi",
        universe_version="v1",
        effective_from=date(2025, 1, 1),
        symbols=("AAPL", "MSFT"),
        description="Multi-attempt test universe",
        applicability={
            "AAPL": {"earnings": "required", "reference": "required"},
            "MSFT": {"earnings": "required", "reference": "required"},
        },
    )


class TestV2MultiAttemptHealthAndCompleteness:
    """Test multi-attempt resolution for operational health and evidence completeness."""

    def test_failed_attempt_superseded_by_succeeded_retry(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        d = date(2026, 1, 2)
        slot = CaptureSlot.MORNING
        t1 = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        t2 = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Attempt 1: FAILED
        e_run1 = PITCaptureRun(
            capture_run_id="e-attempt-1",
            idempotency_key="key-e-1",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t1,
            completed_at=t1,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=2,
            not_applicable_n=0,
            status=CaptureRunStatus.FAILED,
            created_at=t1,
            updated_at=t1,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run1, db_path=db_path)

        # Attempt 2: SUCCEEDED
        e_run2 = PITCaptureRun(
            capture_run_id="e-attempt-2",
            idempotency_key="key-e-2",
            request_fingerprint="g" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=t2,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run2, db_path=db_path)

        # Reference run: SUCCEEDED
        r_run = PITReferenceCaptureRun(
            capture_run_id="r-attempt-1",
            idempotency_key="key-r-1",
            request_fingerprint="h" * 64,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=t2,
            requested_provider="massive",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_reference_capture_run(r_run, db_path=db_path)

        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=d,
            slot=slot,
            now=t2,
            db_path=db_path,
        )

        assert health.overall_status == PITSlotHealthStatus.HEALTHY
        assert health.failure_reason is None
        assert health.evidence_completeness is not None
        assert health.evidence_completeness.overall_tier == PITEvidenceCompletenessTier.COMPLETE
        assert health.evidence_completeness.pooled_ratio == 1.0

    def test_regression_older_started_newer_succeeded(self, tmp_path: Path) -> None:
        """Regression scenario: Older attempt is stranded STARTED (e.g. process crash),

        newer retry attempt is terminal SUCCEEDED:
        - Operational health is DEGRADED (failure_reason="run_in_progress")
        - Evidence completeness is COMPLETE (1.0) derived strictly from the newer terminal attempt!
        """
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        d = date(2026, 1, 2)
        slot = CaptureSlot.MORNING
        t_early = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        t_late = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Run 1: Stranded in STARTED status
        e_run1 = PITCaptureRun(
            capture_run_id="e-stranded-started",
            idempotency_key="key-e-stranded",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t_early,
            requested_at=t_early,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.STARTED,
            created_at=t_early,
            updated_at=t_early,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run1, db_path=db_path)

        # Run 2: Terminal SUCCEEDED
        e_run2 = PITCaptureRun(
            capture_run_id="e-terminal-succeeded",
            idempotency_key="key-e-terminal",
            request_fingerprint="g" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t_early,
            requested_at=t_late,
            completed_at=t_late,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t_late,
            updated_at=t_late,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run2, db_path=db_path)

        # Reference run: Terminal SUCCEEDED
        r_run = PITReferenceCaptureRun(
            capture_run_id="r-ok",
            idempotency_key="key-r-ok",
            request_fingerprint="h" * 64,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t_early,
            requested_at=t_late,
            completed_at=t_late,
            requested_provider="massive",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t_late,
            updated_at=t_late,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_reference_capture_run(r_run, db_path=db_path)

        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=d,
            slot=slot,
            now=t_late,
            db_path=db_path,
        )

        # 1. Operational status must truthfully reflect the unfinalized started run:
        assert health.overall_status == PITSlotHealthStatus.DEGRADED
        assert health.failure_reason == "run_in_progress"

        # 2. Evidence completeness independently selects the authoritative attempt (Run 2):
        assert health.evidence_completeness is not None
        assert health.evidence_completeness.overall_tier == PITEvidenceCompletenessTier.COMPLETE
        assert health.evidence_completeness.pooled_ratio == 1.0
        assert health.evidence_completeness.total_applicable_n == 4
        assert health.evidence_completeness.total_known_n == 4

        # 3. Earnings completeness independently reflects Run 2:
        assert health.earnings.completeness is not None
        assert health.earnings.completeness.tier == PITEvidenceCompletenessTier.COMPLETE
        assert health.earnings.completeness.known_n == 2
        assert health.earnings.completeness.applicable_n == 2

    def test_succeeded_attempt_superseded_by_later_failed_attempt(self, tmp_path: Path) -> None:
        """If a later attempt fails, the authoritative latest attempt determines operational health (FAILED)."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        d = date(2026, 1, 2)
        slot = CaptureSlot.MORNING
        t1 = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        t2 = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Attempt 1: SUCCEEDED
        e_run1 = PITCaptureRun(
            capture_run_id="e-early-ok",
            idempotency_key="key-e-early",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t1,
            completed_at=t1,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t1,
            updated_at=t1,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run1, db_path=db_path)

        # Attempt 2: Later FAILED
        e_run2 = PITCaptureRun(
            capture_run_id="e-late-fail",
            idempotency_key="key-e-late",
            request_fingerprint="g" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=t2,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=2,
            not_applicable_n=0,
            status=CaptureRunStatus.FAILED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run2, db_path=db_path)

        # Reference run: SUCCEEDED
        r_run = PITReferenceCaptureRun(
            capture_run_id="r-ok",
            idempotency_key="key-r-ok",
            request_fingerprint="h" * 64,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=t2,
            requested_provider="massive",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_reference_capture_run(r_run, db_path=db_path)

        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=d,
            slot=slot,
            now=t2,
            db_path=db_path,
        )

        assert health.overall_status == PITSlotHealthStatus.FAILED
        assert health.failure_reason == "capture_failed"
        # Completeness comes from latest attempt (Attempt 2, which has known_n=0)
        assert health.earnings.completeness is not None
        assert health.earnings.completeness.tier == PITEvidenceCompletenessTier.SPARSE

    def test_missing_due_family_yields_failed_and_sparse_completeness(self, tmp_path: Path) -> None:
        """When slot is due but reference runs are completely missing:

        - Health overall_status is FAILED (failure_reason="missing_due_family")
        - Completeness derived from manifest expectation with known_n=0
        """
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        d = date(2026, 1, 2)
        slot = CaptureSlot.MORNING
        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Earnings exists
        e_run = PITCaptureRun(
            capture_run_id="e-only",
            idempotency_key="key-e-only",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run, db_path=db_path)

        # No reference run inserted!

        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=d,
            slot=slot,
            now=t,
            db_path=db_path,
        )

        assert health.overall_status == PITSlotHealthStatus.FAILED
        assert health.failure_reason == "missing_due_family"
        assert health.reference.completeness is not None
        assert health.reference.completeness.known_n == 0
        assert health.reference.completeness.tier == PITEvidenceCompletenessTier.SPARSE
        assert health.evidence_completeness is not None
        assert health.evidence_completeness.overall_tier == PITEvidenceCompletenessTier.SPARSE

    def test_latest_started_attempt_completeness_reflects_persisted_known_snapshots(
        self, tmp_path: Path
    ) -> None:
        """When the latest attempt is STARTED and has persisted KNOWN snapshots:

        - Operational health remains DEGRADED (failure_reason="run_in_progress")
        - Family completeness derives from persisted KNOWN snapshots belonging only to that run
        - No cross-attempt double counting occurs
        """
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        d = date(2026, 1, 2)
        slot = CaptureSlot.MORNING
        t1 = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        t2 = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Attempt 1 (earlier): FAILED with 0 known in run record, but an old snapshot exists
        e_run1 = PITCaptureRun(
            capture_run_id="e-early-terminal",
            idempotency_key="key-e-early",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t1,
            completed_at=t1,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=2,
            not_applicable_n=0,
            status=CaptureRunStatus.FAILED,
            created_at=t1,
            updated_at=t1,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run1, db_path=db_path)

        # Attempt 2 (latest): STARTED, active/incomplete
        e_run2 = PITCaptureRun(
            capture_run_id="e-latest-started",
            idempotency_key="key-e-latest",
            request_fingerprint="g" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.STARTED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run2, db_path=db_path)

        # Reference run: Terminal SUCCEEDED with 2 known
        r_run = PITReferenceCaptureRun(
            capture_run_id="r-ok",
            idempotency_key="key-r-ok",
            request_fingerprint="h" * 64,
            capture_slot=slot,
            capture_date=d,
            scheduled_for=t1,
            requested_at=t2,
            completed_at=t2,
            requested_provider="massive",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t2,
            updated_at=t2,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_reference_capture_run(r_run, db_path=db_path)

        # Snapshot 1 for Attempt 1: belongs to e-early-terminal (MUST NOT be counted for Attempt 2!)
        payload_old = build_known_fact_payload(next_earnings_date=date(2026, 3, 15))
        json_old = serialize_canonical_fact_json(payload_old)
        snap_old = PITEarningsSnapshot(
            snapshot_id="snap-old-1",
            capture_run_id="e-early-terminal",
            symbol="MSFT",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=date(2026, 3, 15),
            provider="yahoo",
            provider_observed_at=t1,
            request_started_at=t1,
            response_received_at=t1,
            fact_hash=compute_fact_hash(json_old),
            fact_json=json_old,
            error_category=None,
            error_message=None,
            created_at=t1,
            contract_version=2,
        )

        # Snapshot 2 for Attempt 2: belongs to e-latest-started (KNOWN)
        payload_new = build_known_fact_payload(next_earnings_date=date(2026, 3, 1))
        json_new = serialize_canonical_fact_json(payload_new)
        snap_new = PITEarningsSnapshot(
            snapshot_id="snap-latest-1",
            capture_run_id="e-latest-started",
            symbol="AAPL",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=date(2026, 3, 1),
            provider="yahoo",
            provider_observed_at=t2,
            request_started_at=t2,
            response_received_at=t2,
            fact_hash=compute_fact_hash(json_new),
            fact_json=json_new,
            error_category=None,
            error_message=None,
            created_at=t2,
            contract_version=2,
        )
        insert_earnings_snapshots([snap_old, snap_new], db_path=db_path)

        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=d,
            slot=slot,
            now=t2,
            db_path=db_path,
        )

        # 1. Operational health remains truthfully DEGRADED (run_in_progress)
        assert health.overall_status == PITSlotHealthStatus.DEGRADED
        assert health.failure_reason == "run_in_progress"

        # 2. Family completeness reflects persisted KNOWN snapshots from only the latest run:
        assert health.earnings.completeness is not None
        assert health.earnings.completeness.applicable_n == 2
        assert health.earnings.completeness.known_n == 1  # only snap_new, not snap_old!
        assert health.earnings.completeness.tier == PITEvidenceCompletenessTier.PARTIAL
        assert health.earnings.completeness.ratio == 0.5
        assert health.earnings.completeness.pct == 50.0

        # 3. Overall slot aggregation preserves exact counts without double counting:
        assert health.evidence_completeness is not None
        assert health.evidence_completeness.total_applicable_n == 4
        assert health.evidence_completeness.total_known_n == 3  # 1 from earnings + 2 from reference
        assert health.evidence_completeness.overall_tier == PITEvidenceCompletenessTier.PARTIAL
        assert health.evidence_completeness.pooled_ratio == 0.75
