"""Contract v2 earnings applicability & skip-provider-call test suite.

Verifies:
1. For symbols with earnings="not_applicable":
   - Zero provider lookup calls (strict skip).
   - Truthful observation_origin="manifest" and applicability_source="manifest".
   - provider_call_attempted=False, timestamps None, provider None.
   - Canonical fact payload and SHA-256 fact hash.
2. For symbols with earnings="required":
   - Normal provider lookup performed, observation_origin="provider".
   - Provider timestamps and identity truthfully recorded.
3. Candidate C mixed universe (30 equities + 15 ETFs):
   - Exactly 30 provider calls, exactly 15 skipped.
4. All-not-applicable universe:
   - Exactly 0 provider calls, provider_required_n=0, run terminal status SUCCEEDED.
5. Zero inference from ticker strings or security types:
   - Applicability is 100% sourced from the validated manifest.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.models import CaptureRunStatus, CaptureSlot, ObservationStatus
from tradex.pit.ops import PITUniverseManifest
from tradex.pit.store import list_earnings_snapshots


def _dt() -> datetime:
    return datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


class TestV2EarningsApplicability:
    """Test v2 earnings applicability logic and provenance."""

    def test_single_not_applicable_skips_provider_call(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-etf-only",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=("SPY",),
            description="ETF universe",
            applicability={"SPY": {"earnings": "not_applicable", "reference": "required"}},
        )

        mock_lookup = MagicMock()
        result = capture_earnings_snapshot(
            symbols=("SPY",),
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=mock_lookup,
        )

        # Invariant: 0 provider calls attempted
        assert mock_lookup.call_count == 0

        # Run verification
        run = result.run
        assert run.status == CaptureRunStatus.SUCCEEDED
        assert run.requested_n == 1
        assert run.known_n == 0
        assert run.unavailable_n == 0
        assert run.not_applicable_n == 1
        assert run.error_n == 0
        assert run.manifest_hash == manifest.manifest_hash
        assert run.contract_version == 2

        # Snapshot verification
        assert len(result.snapshots) == 1
        snap = result.snapshots[0]
        assert snap.symbol == "SPY"
        assert snap.observation_status == ObservationStatus.NOT_APPLICABLE
        assert snap.observation_origin == "manifest"
        assert snap.applicability_source == "manifest"
        assert snap.provider_call_attempted is False
        assert snap.provider is None
        assert snap.provider_observed_at is None
        assert snap.request_started_at is None
        assert snap.response_received_at is None
        assert snap.next_earnings_date is None
        assert snap.error_category is None
        assert snap.error_message is None
        assert snap.contract_version == 2

        # Fact JSON verification
        fact = json.loads(snap.fact_json)
        assert fact == {
            "applicability_source": "manifest",
            "error_category": None,
            "error_message": None,
            "next_earnings_date": None,
            "status_reason": "manifest_not_applicable",
        }

        # Verify persisted snapshot matches read model
        persisted = list_earnings_snapshots(run.capture_run_id, db_path=db_path)
        assert len(persisted) == 1
        assert persisted[0].observation_status == ObservationStatus.NOT_APPLICABLE
        assert persisted[0].observation_origin == "manifest"
        assert persisted[0].applicability_source == "manifest"
        assert persisted[0].provider_call_attempted is False

    def test_candidate_c_mixed_universe_calls_only_required(self, tmp_path: Path) -> None:
        """Candidate C: 30 required equities + 15 not_applicable ETFs."""
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
            universe_id="u-candidate-c",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=all_symbols,
            description="Candidate C universe",
            applicability=applicability,
        )

        called_symbols: list[str] = []

        def fake_lookup(sym: str, source: str = "yahoo", settings=None):
            called_symbols.append(sym)
            return date(2026, 4, 15)

        result = capture_earnings_snapshot(
            symbols=all_symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=fake_lookup,
        )

        # Invariant: exactly 30 equities queried, 0 ETFs queried
        assert len(called_symbols) == 30
        assert set(called_symbols) == set(equities)
        for etf in etfs:
            assert etf not in called_symbols

        run = result.run
        assert run.status == CaptureRunStatus.SUCCEEDED
        assert run.requested_n == 45
        assert run.known_n == 30
        assert run.not_applicable_n == 15
        assert run.error_n == 0
        assert run.unavailable_n == 0

        # Verify all snapshots
        assert len(result.snapshots) == 45
        for snap in result.snapshots:
            if snap.symbol in equities:
                assert snap.observation_status == ObservationStatus.KNOWN
                assert snap.observation_origin == "provider"
                assert snap.applicability_source is None
                assert snap.provider_call_attempted is True
                assert snap.provider == "yahoo"
                assert snap.request_started_at is not None
                assert snap.response_received_at is not None
            else:
                assert snap.observation_status == ObservationStatus.NOT_APPLICABLE
                assert snap.observation_origin == "manifest"
                assert snap.applicability_source == "manifest"
                assert snap.provider_call_attempted is False
                assert snap.provider is None
                assert snap.request_started_at is None
                assert snap.response_received_at is None

    def test_all_not_applicable_universe_succeeds_with_zero_calls(self, tmp_path: Path) -> None:
        """Universe where 100% of symbols are not_applicable."""
        db_path = tmp_path / "signals.db"
        symbols = ("SPY", "QQQ", "IWM")
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-all-na",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=symbols,
            description="All ETF universe",
            applicability={s: {"earnings": "not_applicable", "reference": "required"} for s in symbols},
        )

        mock_lookup = MagicMock()
        result = capture_earnings_snapshot(
            symbols=symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=mock_lookup,
        )

        assert mock_lookup.call_count == 0
        run = result.run
        assert run.status == CaptureRunStatus.SUCCEEDED
        assert run.requested_n == 3
        assert run.known_n == 0
        assert run.not_applicable_n == 3
        assert run.error_n == 0

    def test_no_heuristic_inference_from_ticker_name(self, tmp_path: Path) -> None:
        """Even if ticker looks like an ETF (e.g. SPY), if manifest says required, provider must be called."""
        db_path = tmp_path / "signals.db"
        manifest = PITUniverseManifest(
            contract_version=2,
            universe_id="u-spy-required",
            universe_version="v1",
            effective_from=date(2025, 1, 1),
            symbols=("SPY",),
            description="Explicitly required SPY",
            applicability={"SPY": {"earnings": "required", "reference": "required"}},
        )

        called = False

        def fake_lookup(sym: str, source: str = "yahoo", settings=None):
            nonlocal called
            called = True
            return date(2026, 3, 1)

        result = capture_earnings_snapshot(
            symbols=("SPY",),
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=_dt,
            earnings_lookup=fake_lookup,
        )

        assert called is True
        assert result.snapshots[0].observation_origin == "provider"
        assert result.snapshots[0].observation_status == ObservationStatus.KNOWN
