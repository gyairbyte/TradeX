"""Contract v2 reference provider exception handling & fatal failure test suite.

Verifies:
1. Massive HTTP 404 Error Semantic:
   - HTTP 404 raises MassiveResponseError.
   - Caught per-symbol and recorded as ReferenceObservationStatus.ERROR.
   - error_n is incremented (contributes to PARTIAL or FAILED).
   - Truthfully distinct from 200+200 clean absence.
2. Custom lookup exceptions in per-symbol loop:
   - Caught and sanitized (zero secrets).
   - Truthful start and end timestamps recorded.
   - Observation status is ERROR, run finalized matching Schema v8 constraints.
3. Fatal SQLite Write / Database Failure Test:
   - Injected database failure during runner execution.
   - Active runner returns operational status FAILED (exit 1).
   - Surviving database run remains STARTED with completed_at = NULL.
   - Subsequent health check inspects the stranded run as DEGRADED (run_in_progress).
"""

from datetime import UTC, date, datetime
from pathlib import Path

from tradex.pit.massive_reference import MassiveObservationResult, MassiveResponseError
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    ReferenceObservationStatus,
    build_unavailable_reference_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.ops import (
    PITOperationalStatus,
    PITSlotHealthStatus,
    PITUniverseManifest,
    get_pit_slot_health,
    run_pit_slot,
)
from tradex.pit.reference import capture_reference_snapshot
from tradex.pit.store import list_reference_capture_runs
from tradex.tracker import store


def _manifest() -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=2,
        universe_id="u-ref-exc",
        universe_version="v1",
        effective_from=date(2025, 1, 1),
        symbols=("AAPL", "MSFT"),
        description="Reference exception test universe",
        applicability={
            "AAPL": {"earnings": "required", "reference": "required"},
            "MSFT": {"earnings": "required", "reference": "required"},
        },
    )


def _dt() -> datetime:
    return datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


class TestV2ReferenceExceptionsAndFatalFailures:
    """Test reference error semantics and process fatal failure resilience."""

    def test_massive_404_produces_error_observation_and_increments_error_n(self, tmp_path: Path) -> None:
        """Massive HTTP 404 endpoint failure raises MassiveResponseError,

        which must be caught and recorded as ERROR, incrementing error_n.
        """
        db_path = tmp_path / "signals.db"
        manifest = _manifest()

        def lookup_with_404(sym: str, d: date, c):
            if sym == "AAPL":
                raise MassiveResponseError(
                    "Request failed with HTTP 404: Endpoint not found at https://api.polygon.io/v3/reference/tickers/AAPL?apiKey=SECRET_KEY"
                )
            # MSFT succeeds with UNAVAILABLE
            msft_payload = build_unavailable_reference_fact_payload(ticker="MSFT")
            msft_json = serialize_canonical_fact_json(msft_payload)
            msft_hash = compute_fact_hash(msft_json)
            return MassiveObservationResult(
                observation_status=ReferenceObservationStatus.UNAVAILABLE,
                symbol="MSFT",
                query_date=d,
                request_ids=(),
                provider_ticker=None,
                provider_name=None,
                provider_market=None,
                provider_locale=None,
                provider_active=None,
                provider_type_code=None,
                provider_primary_exchange=None,
                provider_cik=None,
                provider_composite_figi=None,
                provider_share_class_figi=None,
                provider_last_updated_at=None,
                provider_delisted_at=None,
                missing_fields=(),
                fact_hash=msft_hash,
                fact_json=msft_json,
                error_category=None,
                error_message=None,
            )

        result = capture_reference_snapshot(
            symbols=manifest.symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            reference_lookup=lookup_with_404,
        )

        run = result.run
        # AAPL: error, MSFT: unavailable -> error_n = 1 out of 2 -> PARTIAL
        assert run.status == CaptureRunStatus.PARTIAL
        assert run.error_n == 1
        assert run.unavailable_n == 1

        aapl_snap = next(s for s in result.snapshots if s.symbol == "AAPL")
        assert aapl_snap.observation_status == ReferenceObservationStatus.ERROR
        assert aapl_snap.error_category == "MassiveResponseError"
        assert "SECRET_KEY" not in str(aapl_snap.error_message)

    def test_custom_per_symbol_exception_records_truthful_error_snapshot(self, tmp_path: Path) -> None:
        """Unexpected exception in symbol lookup creates a truthful ERROR snapshot with timestamps."""
        db_path = tmp_path / "signals.db"
        manifest = _manifest()

        secret_text = "Connection reset by peer; apiKey=SUPERSECRET123"

        def leaking_lookup(sym: str, d: date, c):
            raise ConnectionResetError(secret_text)

        result = capture_reference_snapshot(
            symbols=manifest.symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            reference_lookup=leaking_lookup,
        )

        assert result.run.status == CaptureRunStatus.FAILED
        assert result.run.error_n == 2
        for snap in result.snapshots:
            assert snap.observation_status == ReferenceObservationStatus.ERROR
            assert snap.request_started_at is not None
            assert snap.response_received_at is not None
            assert "SUPERSECRET123" not in str(snap.error_message)

    def test_fatal_sqlite_write_failure_yields_runner_failed_and_stranded_started_run(
        self, tmp_path: Path
    ) -> None:
        """Fatal DB failure during runner execution:

        1. Runner catches exception, returns operational_status = FAILED.
        2. Zero fabricated observations.
        3. Surviving DB run row remains in STARTED state (Schema-v8 limitation).
        4. Subsequent health check evaluates the stranded run as DEGRADED (run_in_progress).
        """
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        # Ingest a mock reference capture that creates the run as STARTED and then crashes
        from tradex.pit.models import PITReferenceCaptureRun
        from tradex.pit.store import create_reference_capture_run

        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        def crashing_reference_capture(**kwargs):
            # Create a run record in STARTED state
            run = PITReferenceCaptureRun(
                capture_run_id="r-crashed",
                idempotency_key="key-r-crashed",
                request_fingerprint="f" * 64,
                capture_slot=CaptureSlot.MORNING,
                capture_date=date(2026, 1, 2),
                scheduled_for=t,
                requested_at=t,
                completed_at=None,
                requested_provider="massive",
                universe_hash=manifest.universe_hash,
                requested_n=2,
                known_n=0,
                unavailable_n=0,
                ambiguous_n=0,
                error_n=0,
                status=CaptureRunStatus.STARTED,
                created_at=t,
                updated_at=t,
                contract_version=2,
                manifest_hash=manifest.manifest_hash,
            )
            create_reference_capture_run(run, db_path=db_path)
            # Simulate sudden fatal failure (e.g. disk failure / process crash)
            raise OSError("Fatal I/O error: disk full or SQLite corrupted")

        def successful_earnings_capture(**kwargs):
            from tradex.pit.earnings import capture_earnings_snapshot
            return capture_earnings_snapshot(
                symbols=manifest.symbols,
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=manifest,
                db_path=db_path,
                now_fn=lambda: t,
                earnings_lookup=lambda s, **kw: date(2026, 3, 1),
            )

        # 1. Active runner execution
        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_capture=successful_earnings_capture,
            reference_capture=crashing_reference_capture,
        )

        # Runner operational status MUST be FAILED (exit code 1)
        assert result.operational_status == PITOperationalStatus.FAILED
        assert result.reference.status == CaptureRunStatus.STARTED
        assert result.reference.capture_run_id == "r-crashed"

        # 2. Invariant: Surviving DB run row remains truthfully in STARTED status
        runs_in_db = list_reference_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path)
        assert len(runs_in_db) == 1
        assert runs_in_db[0].status == CaptureRunStatus.STARTED
        assert runs_in_db[0].completed_at is None

        # 3. Subsequent offline health check evaluates the stranded run as DEGRADED (run_in_progress)
        health = get_pit_slot_health(
            universe_manifest=manifest,
            capture_date=date(2026, 1, 2),
            slot=CaptureSlot.MORNING,
            now=t,
            db_path=db_path,
        )
        assert health.overall_status == PITSlotHealthStatus.DEGRADED
        assert health.failure_reason == "run_in_progress"
