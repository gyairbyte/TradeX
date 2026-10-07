"""Deterministic research-only ORB evaluator engine and fail-closed holdout guard."""
from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

from tradex.market.hours import get_market_session

from .indicators import compute_adv14, compute_atr14_wilder, compute_relative_volume
from .metrics import (
    compute_study_metrics,
    evaluate_validation_disposition,
    run_session_date_bootstrap,
)
from .models import (
    Candidate,
    DailyBar,
    DataIntegrityError,
    HoldoutAccessDeniedError,
    HoldoutAccessProof,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
    SessionResult,
    StudyResult,
    UniverseMember,
    ValidationDisposition,
)
from .portfolio import simulate_session_portfolio
from .ranking import evaluate_candidate, evaluate_opening_range, rank_and_select_top_20


def _lookup_symbol_data(mapping: dict[str, Any], sym: str) -> Any:
    """Lookup data for canonical symbol, case- and whitespace-insensitively."""
    if sym in mapping:
        return mapping[sym]
    matching_keys = [k for k in mapping if k.strip().upper() == sym]
    if len(matching_keys) == 1:
        return mapping[matching_keys[0]]
    elif len(matching_keys) > 1:
        raise DataIntegrityError(f"Multiple conflicting entries found for symbol {sym} in mapping")
    return None


def verify_holdout_access_guard(
    validation_disposition: str | ValidationDisposition,
) -> HoldoutAccessProof:
    """Fail-closed holdout authorization guard.

    Holdout access is permitted ONLY IF validation disposition == SUPPORTED.
    All other values reject:
        INVALID, INCONCLUSIVE, NOT_SUPPORTED, PROMISING_NOT_CONFIRMED, missing, unknown.
    """
    disp_str = (
        validation_disposition.value
        if isinstance(validation_disposition, ValidationDisposition)
        else str(validation_disposition).upper().strip()
    )

    if disp_str != ValidationDisposition.SUPPORTED.value:
        raise HoldoutAccessDeniedError(
            f"Holdout access strictly prohibited. Validation disposition is '{disp_str}', "
            f"must be exactly '{ValidationDisposition.SUPPORTED.value}'."
        )

    return HoldoutAccessProof(
        validation_disposition=disp_str,
        authorized=True,
        proof_timestamp=datetime.now(UTC),
    )


class ORBEvaluator:
    """Pure deterministic evaluator for Stocks-in-Play 5-minute ORB."""

    def __init__(
        self,
        initial_equity: float = 25000.0,
        leverage_cap: float = 4.0,
        stop_loss_atr_mult: float = 0.10,
        top_n: int = 20,
        bootstrap_resamples: int = 2000,
        bootstrap_seed: int = 20261007,
    ) -> None:
        self.initial_equity = initial_equity
        self.leverage_cap = leverage_cap
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.top_n = top_n
        self.bootstrap_resamples = bootstrap_resamples
        self.bootstrap_seed = bootstrap_seed

    def evaluate_session(
        self,
        session_date: date,
        universe_members: list[UniverseMember],
        daily_bars_by_symbol: dict[str, list[DailyBar]],
        prior_or_volumes_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
        opening_minute_bars_by_symbol: dict[str, list[MinuteBar]],
        trade_path_bars_by_symbol: dict[str, list[MinuteBar]],
        session_start_equity: float | None = None,
        candidate_pool_complete: bool = True,
    ) -> SessionResult:
        """Evaluate a single trading session deterministically.

        Enforces:
        1. XNYS calendar: non-trading dates fail closed as non_computable.
        2. Early-close policy: early-close sessions return EXCLUDED_EARLY_CLOSE.
        3. Candidate pool completeness: for every active universe member, all Stage-A data
           must be complete and verified. Missing/corrupted data fails the session closed.
        4. Trade-path completeness: active pending orders and open positions must have bars.
        """
        equity = session_start_equity if session_start_equity is not None else self.initial_equity

        def _fail_closed(error_reason: str) -> SessionResult:
            return SessionResult(
                session_date=session_date,
                is_valid=False,
                status="non_computable",
                error_reason=error_reason,
                candidate_count=0,
                qualified_candidate_count=0,
                top_20_count=0,
                orders_placed_count=0,
                trades_triggered_count=0,
                capacity_rejected_count=0,
                trades=(),
                session_start_equity=equity,
                session_end_equity_a=equity,
                session_end_equity_b=equity,
                session_end_equity_c=equity,
                session_net_pnl_a=0.0,
                session_net_pnl_b=0.0,
                session_net_pnl_c=0.0,
                session_net_return_a=0.0,
                session_net_return_b=0.0,
                session_net_return_c=0.0,
                max_gross_exposure=0.0,
                max_leverage_used=0.0,
                same_bar_ambiguity_count=0,
            )

        try:
            # Calendar check via canonical XNYS market hours
            session = get_market_session(session_date)
            if session is None:
                return _fail_closed(f"Date {session_date} is not a valid XNYS trading session")

            if session.is_early_close:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="EXCLUDED_EARLY_CLOSE",
                    error_reason=f"Exchange early-close session on {session_date} excluded by locked policy",
                    candidate_count=0,
                    qualified_candidate_count=0,
                    top_20_count=0,
                    orders_placed_count=0,
                    trades_triggered_count=0,
                    capacity_rejected_count=0,
                    trades=(),
                    session_start_equity=equity,
                    session_end_equity_a=equity,
                    session_end_equity_b=equity,
                    session_end_equity_c=equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=0.0,
                    max_leverage_used=0.0,
                    same_bar_ambiguity_count=0,
                )

            # Candidate pool completeness explicit flag
            if not candidate_pool_complete:
                return _fail_closed("Candidate pool incomplete: cannot prove Top 20 is uncorrupted")

            seen_active_symbols: set[str] = set()
            active_members: list[UniverseMember] = []
            for member in universe_members:
                if not member.active_on_date:
                    continue
                canonical_sym = member.symbol.strip().upper() if member.symbol else ""
                if not canonical_sym:
                    return _fail_closed("Active universe member has empty symbol")
                if canonical_sym in seen_active_symbols:
                    return _fail_closed(f"Duplicate active universe symbol detected: {canonical_sym}")
                seen_active_symbols.add(canonical_sym)
                active_members.append(member)

            evaluated_candidates: list[Candidate] = []
            opening_ranges: dict[str, OpeningRange] = {}

            for member in active_members:
                sym = member.symbol.strip().upper()

                # 1. Opening range bars: all five regular-session minutes required
                or_bars = _lookup_symbol_data(opening_minute_bars_by_symbol, sym)
                if or_bars is None or len(or_bars) == 0:
                    return _fail_closed(f"Stage-A data incomplete for active symbol {sym}: missing opening range minute bars")

                for b in or_bars:
                    if b.symbol.strip().upper() != sym:
                        return _fail_closed(
                            f"Stage-A opening range bar symbol mismatch for {sym}: bar has symbol {b.symbol}"
                        )

                op_range = evaluate_opening_range(or_bars)
                if op_range is None:
                    return _fail_closed(f"Stage-A data incomplete for active symbol {sym}: malformed or missing opening range minutes")

                if not all(
                    not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (op_range.or_open, op_range.or_high, op_range.or_low, op_range.or_close, op_range.or_volume)
                ):
                    return _fail_closed(f"Stage-A opening range values non-finite for active symbol {sym}")

                if op_range.symbol.strip().upper() != sym:
                    return _fail_closed(
                        f"Stage-A opening range symbol mismatch for {sym}: range has symbol {op_range.symbol}"
                    )

                opening_ranges[sym] = op_range

                # 2. Daily bars for ADV14 and ATR14
                daily_bars = _lookup_symbol_data(daily_bars_by_symbol, sym)
                if daily_bars is None or len(daily_bars) == 0:
                    return _fail_closed(f"Stage-A data incomplete for active symbol {sym}: missing daily bars")

                for b in daily_bars:
                    if b.symbol.strip().upper() != sym:
                        return _fail_closed(
                            f"Stage-A daily bar symbol mismatch for {sym}: bar has symbol {b.symbol}"
                        )

                adv14 = compute_adv14(daily_bars, session_date)
                if adv14 is None or not math.isfinite(adv14):
                    return _fail_closed(
                        f"Stage-A data incomplete for active symbol {sym}: ADV14 non-computable (missing/incomplete prior 14 XNYS sessions or non-finite)"
                    )

                atr14 = compute_atr14_wilder(daily_bars, session_date)
                if atr14 is None or not math.isfinite(atr14):
                    return _fail_closed(
                        f"Stage-A data incomplete for active symbol {sym}: ATR14 non-computable (missing/non-contiguous prior daily history or non-finite)"
                    )

                # 3. Relative Volume observations: exact prior 14 completed XNYS sessions
                prior_or_vols = _lookup_symbol_data(prior_or_volumes_by_symbol, sym)
                if prior_or_vols is None or len(prior_or_vols) == 0:
                    return _fail_closed(f"Stage-A data incomplete for active symbol {sym}: missing prior OR volume observations")

                for obs in prior_or_vols:
                    if obs.symbol.strip().upper() != sym:
                        return _fail_closed(
                            f"Stage-A prior OR volume observation symbol mismatch for {sym}: observation has symbol {obs.symbol}"
                        )

                rv, mean_prior_vol = compute_relative_volume(
                    prior_observations=prior_or_vols,
                    current_or_volume=op_range.or_volume,
                    target_session=session_date,
                )
                if rv is None or mean_prior_vol is None or not math.isfinite(rv) or not math.isfinite(mean_prior_vol):
                    return _fail_closed(
                        f"Stage-A data incomplete for active symbol {sym}: RV non-computable (missing/incomplete prior 14 XNYS observations or non-finite)"
                    )

                # Stage-A data verified complete: evaluate technical qualification
                candidate = evaluate_candidate(
                    symbol=sym,
                    session_date=session_date,
                    opening_range=op_range,
                    adv14=adv14,
                    atr14=atr14,
                    mean_prior_or_volume=mean_prior_vol,
                    rv=rv,
                )
                evaluated_candidates.append(candidate)

            # Rank and select Top 20
            ranked_candidates = rank_and_select_top_20(
                candidates=evaluated_candidates,
                opening_ranges=opening_ranges,
                session_start_equity=equity,
                top_n=self.top_n,
            )

            # Simulate execution across discrete 1-minute bars with state-aware path validation
            return simulate_session_portfolio(
                session_date=session_date,
                ranked_candidates=ranked_candidates,
                minute_bars_by_symbol=trade_path_bars_by_symbol,
                session_start_equity=equity,
                leverage_cap=self.leverage_cap,
                stop_loss_atr_mult=self.stop_loss_atr_mult,
                candidate_count=len(evaluated_candidates),
                qualified_candidate_count=len([c for c in evaluated_candidates if c.is_eligible]),
            )
        except DataIntegrityError as exc:
            return _fail_closed(f"Data integrity error: {exc}")

    def evaluate_study(
        self,
        study_name: str,
        session_results: list[SessionResult],
        integrity_error: str | None = None,
    ) -> StudyResult:
        """Aggregate session results, compute study metrics, run block bootstrap, and evaluate disposition."""
        # Auto-derive integrity failure if any full session failed closed
        if integrity_error is None:
            non_computable = [
                s for s in session_results if not s.is_valid and s.status != "EXCLUDED_EARLY_CLOSE"
            ]
            if non_computable:
                integrity_error = (
                    f"Integrity failure: {len(non_computable)} required session(s) non-computable. "
                    f"First: {non_computable[0].session_date} ({non_computable[0].error_reason})"
                )

        metrics = compute_study_metrics(session_results)
        bootstrap_ci = run_session_date_bootstrap(
            session_results=session_results,
            resamples=self.bootstrap_resamples,
            seed=self.bootstrap_seed,
        )
        disp, step, reason, gates = evaluate_validation_disposition(
            session_results=session_results,
            bootstrap_ci=bootstrap_ci,
            integrity_error=integrity_error,
        )

        return StudyResult(
            study_name=study_name,
            session_results=tuple(session_results),
            metrics=metrics,
            bootstrap_ci=bootstrap_ci,
            disposition=disp,
            disposition_step=step,
            disposition_reason=reason,
            gates=gates,
        )
