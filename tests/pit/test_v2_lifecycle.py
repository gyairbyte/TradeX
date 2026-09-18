"""Contract v2 run lifecycle & terminal status suite.

Verifies:
1. Clean absence (UNAVAILABLE observations, 0 provider errors) -> SUCCEEDED.
2. Reference clean absence (200 OK active + 200 OK inactive with 0 exact matches)
   yields ReferenceObservationStatus.UNAVAILABLE, error_n = 0 -> SUCCEEDED.
3. Reference AMBIGUOUS observations with 0 provider errors -> SUCCEEDED.
4. Manifest NOT_APPLICABLE observations with 0 provider errors -> SUCCEEDED.
5. Partial provider errors (0 < error_n < provider_required_n) -> PARTIAL.
6. Candidate C regression test: requested_n=45, not_applicable_n=15, error_n=30
   (provider_required_n = 45 - 15 = 30; error_n == 30) -> FAILED.
7. Reference total outage: requested_n=45, error_n=45 -> FAILED.
"""

from datetime import UTC, date, datetime
from pathlib import Path

from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.massive_reference import MassiveObservationResult
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    ReferenceObservationStatus,
    build_ambiguous_reference_fact_payload,
    build_unavailable_reference_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.ops import PITUniverseManifest
from tradex.pit.reference import capture_reference_snapshot


def _dt() -> datetime:
    return datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


class TestV2RunLifecycleStatus:
    """Test contract v2 terminal status derivation formulas."""

    def test_earnings_clean_unavailable_yields_succeeded(self, tmp_path: Path) -> None:
        """When an equity has no upcoming earnings date (clean absence), status is SUCCEEDED."""
        db_path = tmp_path / "signals.db"
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-unavail",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=("AAPL",),
            description="Unavailable test",
            applicability={"AAPL": {"earnings": "required", "reference": "required"}},
        )

        # Lookup returns None (clean absence)
        result = capture_earnings_snapshot(
            symbols=("AAPL",),
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=lambda s, **kw: None,
        )

        assert result.run.status == CaptureRunStatus.SUCCEEDED
        assert result.run.known_n == 0
        assert result.run.unavailable_n == 1
        assert result.run.error_n == 0

    def test_reference_clean_absence_yields_succeeded(self, tmp_path: Path) -> None:
        """Active 200 + inactive 200 with 0 exact matches -> UNAVAILABLE -> SUCCEEDED."""
        db_path = tmp_path / "signals.db"
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-ref-unavail",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=("UNKNOWN",),
            description="Reference unavailable test",
            applicability={"UNKNOWN": {"earnings": "required", "reference": "required"}},
        )

        fact_payload = build_unavailable_reference_fact_payload(ticker="UNKNOWN")
        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)
        obs = MassiveObservationResult(
            observation_status=ReferenceObservationStatus.UNAVAILABLE,
            symbol="UNKNOWN",
            query_date=date(2026, 1, 2),
            request_ids=("req-1", "req-2"),
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
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
        )

        result = capture_reference_snapshot(
            symbols=("UNKNOWN",),
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            reference_lookup=lambda s, d, c: obs,
        )

        assert result.run.status == CaptureRunStatus.SUCCEEDED
        assert result.run.known_n == 0
        assert result.run.unavailable_n == 1
        assert result.run.error_n == 0

    def test_reference_ambiguous_yields_succeeded(self, tmp_path: Path) -> None:
        """Ambiguous reference candidate matching -> AMBIGUOUS -> SUCCEEDED."""
        db_path = tmp_path / "signals.db"
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-ref-ambig",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=("AMBIG",),
            description="Reference ambiguous test",
            applicability={"AMBIG": {"earnings": "required", "reference": "required"}},
        )

        fact_payload = build_ambiguous_reference_fact_payload(
            ticker="AMBIG",
            candidates=(
                {"ticker": "AMBIG", "name": "Co A", "primary_exchange": "XNAS", "active": True},
                {"ticker": "AMBIG", "name": "Co B", "primary_exchange": "XNYS", "active": True},
            ),
        )
        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)
        obs = MassiveObservationResult(
            observation_status=ReferenceObservationStatus.AMBIGUOUS,
            symbol="AMBIG",
            query_date=date(2026, 1, 2),
            request_ids=("req-1",),
            provider_ticker="AMBIG",
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
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
        )

        result = capture_reference_snapshot(
            symbols=("AMBIG",),
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            reference_lookup=lambda s, d, c: obs,
        )

        assert result.run.status == CaptureRunStatus.SUCCEEDED
        assert result.run.ambiguous_n == 1
        assert result.run.error_n == 0

    def test_earnings_partial_provider_errors_yields_partial(self, tmp_path: Path) -> None:
        """When some symbols succeed and some error (0 < error_n < provider_required_n), status is PARTIAL."""
        db_path = tmp_path / "signals.db"
        symbols = ("AAPL", "MSFT", "SPY")
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-partial",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=symbols,
            description="Partial test",
            applicability={
                "AAPL": {"earnings": "required", "reference": "required"},
                "MSFT": {"earnings": "required", "reference": "required"},
                "SPY": {"earnings": "not_applicable", "reference": "required"},
            },
        )

        def mock_lookup(sym: str, source: str = "yahoo", settings=None):
            if sym == "AAPL":
                return date(2026, 3, 1)
            raise RuntimeError("Provider error on MSFT")

        result = capture_earnings_snapshot(
            symbols=symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=mock_lookup,
        )

        # provider_required_n = 3 - 1 = 2
        # error_n = 1 -> 0 < 1 < 2 -> PARTIAL
        assert result.run.status == CaptureRunStatus.PARTIAL
        assert result.run.known_n == 1
        assert result.run.error_n == 1
        assert result.run.not_applicable_n == 1

    def test_mandatory_candidate_c_total_outage_regression(self, tmp_path: Path) -> None:
        """Candidate C: requested_n=45, not_applicable_n=15, error_n=30 -> FAILED (NOT PARTIAL)."""
        db_path = tmp_path / "signals.db"
        equities = tuple(f"EQ{i:02d}" for i in range(1, 31))
        etfs = tuple(f"ETF{i:02d}" for i in range(1, 16))
        all_symbols = tuple(sorted(equities + etfs))

        applicability = {}
        for s in all_symbols:
            if s in equities:
                applicability[s] = {"earnings": "required", "reference": "required"}
            else:
                applicability[s] = {"earnings": "not_applicable", "reference": "required"}

        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-candidate-c-fail",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=all_symbols,
            description="Candidate C total outage",
            applicability=applicability,
        )

        def total_outage_lookup(sym: str, source: str = "yahoo", settings=None):
            raise RuntimeError("Yahoo Finance completely unavailable 500")

        result = capture_earnings_snapshot(
            symbols=all_symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=total_outage_lookup,
        )

        # provider_required_n = 45 - 15 = 30
        # error_n = 30 == provider_required_n -> FAILED (NOT PARTIAL!)
        assert result.run.status == CaptureRunStatus.FAILED
        assert result.run.requested_n == 45
        assert result.run.not_applicable_n == 15
        assert result.run.error_n == 30
        assert result.run.known_n == 0
        assert result.run.unavailable_n == 0

    def test_reference_total_outage_yields_failed(self, tmp_path: Path) -> None:
        """When 100% of reference symbols error out, status is FAILED."""
        db_path = tmp_path / "signals.db"
        symbols = ("AAPL", "MSFT")
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-ref-outage",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=symbols,
            description="Reference outage",
            applicability={s: {"earnings": "required", "reference": "required"} for s in symbols},
        )

        def failing_lookup(sym: str, d: date, c):
            raise RuntimeError("Massive 503 Service Unavailable")

        result = capture_reference_snapshot(
            symbols=symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            reference_lookup=failing_lookup,
        )

        assert result.run.status == CaptureRunStatus.FAILED
        assert result.run.requested_n == 2
        assert result.run.error_n == 2
        assert result.run.known_n == 0
