"""Tests for the alert cooldown policy and fail-closed evidence gating."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradex.alerts.models import AlertCooldownConfig, AlertDecision, AlertKey
from tradex.alerts.policy import AlertPolicy
from tradex.alerts.store import AlertStore
from tradex.strategies.registry import ApprovedProductionStrategy


@pytest.fixture
def fixed_clock():
    return datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=UTC)


@pytest.fixture
def authorized_strategy(monkeypatch):
    """Register an approved strategy for testing authorized alert pathways."""
    strat = ApprovedProductionStrategy(
        strategy_id="test_001",
        strategy_version="1.0.0",
        description="Authorized test strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    return strat


class TestAlertPolicyEvidenceGating:
    """Tests for fail-closed automatic market alert gating (MVP-ARCH-001-R4)."""

    def test_unapproved_market_event_gated_fail_closed(self, tmp_alert_store, fixed_clock):
        """Unapproved market alerts fail closed with SUPPRESSED_EVIDENCE_GATE."""
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(key, "subject", "body", observed_at=fixed_clock)

        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
        assert len(calls) == 0
        assert result.channel_results == {}
        assert result.next_eligible_at is None
        assert "no approved actionable strategy identity" in result.reason

        # Verify alert_state in store
        state = tmp_alert_store.get_state(key)
        assert state is not None
        assert state.suppressed_count == 1
        assert state.sent_count == 0
        assert state.failed_count == 0
        assert state.cooldown_until is None
        assert state.claim_token is None
        assert state.last_decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE.value

    def test_disabled_cooldown_cannot_bypass_evidence_gating(self, tmp_alert_store, fixed_clock):
        """--disable-alert-cooldown / config.enabled=False cannot bypass evidence gating."""
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        config = AlertCooldownConfig(enabled=False)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            config=config,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(key, "subject", "body", observed_at=fixed_clock)

        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
        assert len(calls) == 0
        state = tmp_alert_store.get_state(key)
        assert state is not None
        assert state.suppressed_count == 1
        assert state.sent_count == 0

    def test_unconfigured_channels_still_gated_before_channel_check(
        self, tmp_alert_store, fixed_clock
    ):
        """Missing channels produce SUPPRESSED_EVIDENCE_GATE before channel check."""
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": False, "email": False},
            is_configured=lambda: False,
        )
        key = AlertKey("AAPL", "confluence", "multi")
        result = policy.dispatch(key, "subject", "body", observed_at=fixed_clock)

        # Must be evidence gate, NOT NO_CHANNELS_CONFIGURED
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_repeated_gated_events_increment_suppressed_count(self, tmp_alert_store, fixed_clock):
        """Repeated gated events remain SUPPRESSED_EVIDENCE_GATE and increment count."""
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")

        r1 = policy.dispatch(key, "s1", "b1", observed_at=fixed_clock)
        r2 = policy.dispatch(key, "s2", "b2", observed_at=fixed_clock + timedelta(minutes=5))
        r3 = policy.dispatch(key, "s3", "b3", observed_at=fixed_clock + timedelta(minutes=10))

        assert r1.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
        assert r2.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
        assert r3.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
        assert len(calls) == 0

        state = tmp_alert_store.get_state(key)
        assert state is not None
        assert state.suppressed_count == 3
        assert state.sent_count == 0
        assert state.failed_count == 0
        assert state.cooldown_until is None

    def test_store_failure_on_evidence_suppression_fails_closed(
        self, tmp_alert_store, fixed_clock, monkeypatch
    ):
        """If store.record_suppression fails, result is POLICY_ERROR and no transport is called."""
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        from tradex.alerts.store import AlertStateError

        def failing_record_suppression(*args, **kwargs):
            raise AlertStateError("disk I/O failure")

        monkeypatch.setattr(tmp_alert_store, "record_suppression", failing_record_suppression)

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(key, "subject", "body", observed_at=fixed_clock)

        assert result.decision == AlertDecision.POLICY_ERROR
        assert len(calls) == 0
        assert "disk I/O failure" in result.reason

    def test_existing_cooldown_row_does_not_preempt_evidence_gate(
        self, tmp_alert_store, fixed_clock
    ):
        """Historical cooldown rows do not prevent evidence gating."""
        key = AlertKey("AAPL", "coil", "intraday")
        # Pre-seed a row with cooldown_until in the future
        token = tmp_alert_store.claim(key, fixed_clock)["token"]
        tmp_alert_store.finalize(
            key,
            token,
            fixed_clock,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
        )

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        result = policy.dispatch(key, "subject", "body", observed_at=fixed_clock + timedelta(minutes=5))
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE


class TestAlertPolicyAuthorizedDispatch:
    """Tests for alert cooldown policy on explicitly authorized strategies."""

    def test_first_send(self, tmp_alert_store, fixed_clock, authorized_strategy):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT
        assert result.channel_results == {"discord": True, "email": False}
        assert result.last_success_at == fixed_clock
        assert result.next_eligible_at == fixed_clock + timedelta(minutes=60)

    def test_repeat_suppressed(self, tmp_alert_store, fixed_clock, authorized_strategy):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        result = policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SUPPRESSED_COOLDOWN
        assert result.channel_results == {}

    def test_exact_expiry_sends(self, tmp_alert_store, fixed_clock, authorized_strategy):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        exact = fixed_clock + timedelta(minutes=60)
        result = policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=exact,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT

    def test_transport_not_called_when_suppressed(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert len(calls) == 1

    def test_partial_success_starts_cooldown(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT
        state = tmp_alert_store.get_state(key)
        assert state.cooldown_until == fixed_clock + timedelta(minutes=60)

    def test_total_failure_does_not_start_cooldown(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": False, "email": False},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.DELIVERY_FAILED
        state = tmp_alert_store.get_state(key)
        assert state.cooldown_until is None
        assert state.failed_count == 1

    def test_no_channels_configured(self, tmp_alert_store, fixed_clock, authorized_strategy):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": False, "email": False},
            is_configured=lambda: False,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.NO_CHANNELS_CONFIGURED
        state = tmp_alert_store.get_state(key)
        assert state.failed_count == 1

    def test_disabled_cooldown_sends_every_time(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        config = AlertCooldownConfig(enabled=False)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            config=config,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        r1 = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        r2 = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r1.decision == AlertDecision.COOLDOWN_DISABLED
        assert r2.decision == AlertDecision.COOLDOWN_DISABLED
        assert tmp_alert_store.get_state(key) is None

    def test_transport_exception(self, tmp_alert_store, fixed_clock, authorized_strategy):
        def transport(s, b, c):
            raise RuntimeError("network failure")

        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.DELIVERY_FAILED
        state = tmp_alert_store.get_state(key)
        assert state.claim_token is None
        assert state.failed_count == 1

    def test_state_store_error_fails_closed(self, tmp_path, fixed_clock, authorized_strategy):
        path = tmp_path / "alerts.db"
        path.write_text("corrupt")
        policy = AlertPolicy(clock=lambda: fixed_clock, store=AlertStore(path))
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.POLICY_ERROR
        assert "state" in result.reason.lower()

    def test_different_ticker_independent(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = policy.dispatch(
            AlertKey("AAPL", "coil", "intraday"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        r2 = policy.dispatch(
            AlertKey("MSFT", "coil", "intraday"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_different_alert_type_independent(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = policy.dispatch(
            AlertKey("AAPL", "coil", "intraday"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        r2 = policy.dispatch(
            AlertKey("AAPL", "confluence", "multi"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_different_timeframe_independent(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = policy.dispatch(
            AlertKey("AAPL", "coil", "intraday"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        r2 = policy.dispatch(
            AlertKey("AAPL", "coil", "short"),
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_concurrent_claim_only_one_sends(
        self, tmp_path, fixed_clock, authorized_strategy
    ):
        path = tmp_path / "alerts.db"
        store1 = AlertStore(path)
        store2 = AlertStore(path)
        calls = []

        def transport(s, b, c):
            calls.append(1)
            return {"discord": True}

        policy2 = AlertPolicy(
            clock=lambda: fixed_clock,
            store=store2,
            transport=transport,
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")

        # Process 1 acquires the claim and holds it while process 2 attempts dispatch.
        claim = store1.claim(key, fixed_clock, lease_seconds=120)
        r2 = policy2.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r2.decision == AlertDecision.SUPPRESSED_IN_FLIGHT

        # Process 1 finalizes the held claim.
        store1.finalize(
            key,
            claim["token"],
            fixed_clock,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
        )

        # A later attempt by process 2 is now on cooldown.
        r2_later = policy2.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r2_later.decision == AlertDecision.SUPPRESSED_COOLDOWN
        # Process 2 never invoked the transport while the claim was held.
        assert len(calls) == 0
        assert store2.get_state(key).sent_count == 1

    def test_stale_claim_reclaimable(self, tmp_alert_store, fixed_clock, authorized_strategy):
        key = AlertKey("AAPL", "coil", "intraday")
        # Manually create an expired, unfinalized claim.
        tmp_alert_store.claim(key, fixed_clock, lease_seconds=1)
        later = fixed_clock + timedelta(seconds=2)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=later,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT

    def test_naive_observed_at_rejected(self, tmp_alert_store, fixed_clock):
        policy = AlertPolicy(clock=lambda: fixed_clock, store=tmp_alert_store)
        with pytest.raises(ValueError, match="naive"):
            policy.dispatch(
                AlertKey("AAPL", "coil", "intraday"),
                "s",
                "b",
                observed_at=datetime(2024, 1, 1, 12, 0),  # noqa: DTZ001
            )


class TestAlertPolicyPerTypeOverrides:
    def test_coil_override(self, tmp_alert_store, fixed_clock, authorized_strategy):
        config = AlertCooldownConfig(coil_minutes=5)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            config=config,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock + timedelta(minutes=5),
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT

    def test_gap_override(self, tmp_alert_store, fixed_clock, authorized_strategy):
        config = AlertCooldownConfig(gap_minutes=5)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            config=config,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "gap:up", "premarket")
        policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock + timedelta(minutes=5),
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT

    def test_pattern_override(self, tmp_alert_store, fixed_clock, authorized_strategy):
        config = AlertCooldownConfig(pattern_minutes=5)
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            config=config,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "pattern:runup:standard", "pattern")
        policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock + timedelta(minutes=5),
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT


class TestAlertPolicyFinalizeHandling:
    def test_finalize_false_becomes_policy_error(
        self, tmp_alert_store, fixed_clock, authorized_strategy, monkeypatch
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        monkeypatch.setattr(tmp_alert_store, "finalize", lambda *args, **kwargs: False)
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.POLICY_ERROR
        assert "finalization" in result.reason.lower()

    def test_finalize_uses_finalized_at_for_lease(self, tmp_alert_store, fixed_clock):
        """Lease expiry is checked against the finalization time, not the observation time."""
        key = AlertKey("AAPL", "coil", "intraday")
        claim_ts = fixed_clock
        token = tmp_alert_store.claim(key, claim_ts, lease_seconds=120)["token"]
        success = tmp_alert_store.finalize(
            key,
            token,
            claim_ts,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
            finalized_at=claim_ts + timedelta(seconds=200),
        )
        assert success is False

    def test_finalize_succeeds_before_lease_expiry(self, tmp_alert_store, fixed_clock):
        key = AlertKey("AAPL", "coil", "intraday")
        claim_ts = fixed_clock
        token = tmp_alert_store.claim(key, claim_ts, lease_seconds=120)["token"]
        success = tmp_alert_store.finalize(
            key,
            token,
            claim_ts,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
            finalized_at=claim_ts + timedelta(seconds=60),
        )
        assert success is True

    def test_reclaimed_lease_finalize_rejected(self, tmp_path, fixed_clock):
        path = tmp_path / "alerts.db"
        store1 = AlertStore(path)
        store2 = AlertStore(path)
        key = AlertKey("AAPL", "coil", "intraday")
        now = fixed_clock
        token1 = store1.claim(key, now, lease_seconds=60)["token"]
        later = now + timedelta(seconds=120)
        store2.claim(key, later, lease_seconds=120)
        success = store1.finalize(
            key,
            token1,
            now,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
            finalized_at=later,
        )
        assert success is False

    def test_transport_completion_after_lease_expiry_returns_policy_error(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        """The policy reports POLICY_ERROR when transport completes after the lease expired."""
        late_clock = lambda: fixed_clock + timedelta(seconds=200)
        policy = AlertPolicy(
            clock=late_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.POLICY_ERROR
        assert "lease" in result.reason.lower() or "finalization" in result.reason.lower()

    def test_normal_transport_completion_succeeds(
        self, tmp_alert_store, fixed_clock, authorized_strategy
    ):
        policy = AlertPolicy(
            clock=lambda: fixed_clock,
            store=tmp_alert_store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        result = policy.dispatch(
            key,
            "s",
            "b",
            observed_at=fixed_clock,
            strategy_id="test_001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert result.decision == AlertDecision.SENT

    def test_idempotent_finalize_rejects_different_outcome(self, tmp_alert_store, fixed_clock):
        key = AlertKey("AAPL", "coil", "intraday")
        now = fixed_clock
        token = tmp_alert_store.claim(key, now)["token"]
        args = (key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent")
        assert tmp_alert_store.finalize(*args) is True
        wrong_args = (
            key,
            token,
            now,
            AlertDecision.DELIVERY_FAILED,
            None,
            "subj",
            "hash",
            {},
            "failed",
        )
        assert tmp_alert_store.finalize(*wrong_args) is False

    def test_wrong_token_after_completed_finalize(self, tmp_alert_store, fixed_clock):
        key = AlertKey("AAPL", "coil", "intraday")
        now = fixed_clock
        token = tmp_alert_store.claim(key, now)["token"]
        tmp_alert_store.finalize(
            key, token, now, AlertDecision.SENT, 60, "subj", "hash", {"discord": True}, "sent"
        )
        success = tmp_alert_store.finalize(
            key,
            "wrong-token",
            now,
            AlertDecision.SENT,
            60,
            "subj",
            "hash",
            {"discord": True},
            "sent",
        )
        assert success is False
