"""Dataset builder, eligibility filtering, technical indicator calculation, and PIT assembly for LONG-002C.

Handles as-traded vs split-normalized series, data quality audits, eligibility gates,
and point-in-time decision observation generation.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002c.calendar import (
    check_split_boundary_purge,
    get_decision_timestamp_utc,
)
from tradex.research.long_002c.identity import SecurityIdentity, SecurityMaster
from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002c.models import (
    DataEligibility,
    DataQualityCoverage,
    DecisionObservation,
    EarningsScheduleStatus,
    ExclusionReasonRecord,
    SecurityClassificationStatus,
)
from tradex.research.long_002c.spec import (
    DEV_END,
    DEV_START,
    enforce_split_guard,
)


def compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Calculate Average True Range (Wilder's ATR) over the specified period on split-normalized prices."""
    if len(closes) < period + 1:
        return None
    tr_list: list[float] = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

    if len(tr_list) < period:
        return None

    # Initial ATR is simple moving average of first `period` TRs
    atr = sum(tr_list[:period]) / period
    # Wilder's smoothing
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 4)


def build_decision_observations_for_security(
    identity: SecurityIdentity,
    bars_df: pd.DataFrame,  # columns: [open, high, low, close, volume, as_traded_close] sorted by date index
    trading_sessions: list[str],
    cutoff_time: str = "20:30",
    dev_start: str = DEV_START,
    dev_end: str = DEV_END,
    earnings_schedules: dict[str, dict[str, Any]] | None = None,  # date -> earnings info
    market_caps: dict[str, float] | None = None,  # date -> market cap
    market_cap_reasons: dict[str, str] | None = None,  # date -> reason code (e.g. missing_shares, unavailable_at_cutoff)
    index_memberships: dict[str, bool] | None = None,  # date -> bool
    special_distribution_dates: set[str] | None = None,
    candidate: CandidateSecurity | None = None,
    security_master: SecurityMaster | None = None,
) -> tuple[
    list[DecisionObservation],
    list[DataEligibility],
    list[SecurityClassificationStatus],
    list[EarningsScheduleStatus],
    list[ExclusionReasonRecord],
    DataQualityCoverage,
]:
    """Build PIT decision observations and eligibility records for a single security across development split."""
    observations: list[DecisionObservation] = []
    eligibilities: list[DataEligibility] = []
    classifications: list[SecurityClassificationStatus] = []
    earnings_records: list[EarningsScheduleStatus] = []
    exclusions: list[ExclusionReasonRecord] = []

    sec_id = identity.immutable_security_id
    ticker = identity.ticker_at_decision

    # Filter bars up to dev_end and ensure no 2021+ data is read
    enforce_split_guard(dev_end)

    # Reindex or align bars with expected trading sessions
    bar_dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in bars_df.index]
    bar_date_set = set(bar_dates)

    # Data quality audit on development split
    dev_sessions = [s for s in trading_sessions if dev_start <= s <= dev_end]
    dev_observed = [s for s in dev_sessions if s in bar_date_set]
    expected_count = len(dev_sessions)
    observed_count = len(dev_observed)
    completeness_pct = (observed_count / expected_count * 100.0) if expected_count > 0 else 0.0

    missing_sessions = [s for s in dev_sessions if s not in bar_date_set]
    unexplained_missing = len(missing_sessions)

    # Max consecutive missing sessions
    max_consec = 0
    curr_consec = 0
    for s in dev_sessions:
        if s not in bar_date_set:
            curr_consec += 1
            max_consec = max(max_consec, curr_consec)
        else:
            curr_consec = 0

    coverage = DataQualityCoverage(
        immutable_security_id=sec_id,
        split_name="development",
        expected_sessions=expected_count,
        observed_sessions=observed_count,
        completeness_pct=round(completeness_pct, 2),
        unexplained_missing_sessions=unexplained_missing,
        max_consecutive_missing_sessions=max_consec,
        duplicate_bar_count=0,
        malformed_bar_count=0,
        halt_sessions_count=0,
    )

    # Process each trading session in the development window
    for session_date in dev_sessions:
        if session_date not in bar_date_set:
            # Session missing from provider history
            continue

        idx = bar_dates.index(session_date)

        # Resolve effective historical ticker at decision date
        ticker_unresolved = False
        if candidate is not None:
            interval = candidate.resolve_interval(session_date)
            if interval is not None:
                ticker = interval.symbol
            else:
                ticker_unresolved = True
                ticker = candidate.primary_symbol
        elif security_master is not None:
            resolved = security_master.resolve_ticker(sec_id, session_date)
            if resolved is not None:
                ticker = resolved
            else:
                ticker_unresolved = True
                ticker = identity.ticker_at_decision
        else:
            ticker = identity.ticker_at_decision

        # Point-in-time history:
        # At 09:00 ET, session T has not opened. Features MUST use history strictly through session T-1 (prior completed session).
        # At 20:30 ET, session T has completed. Features include session T.
        if cutoff_time == "09:00":
            hist_slice = bars_df.iloc[:idx]
            if len(hist_slice) == 0:
                n_hist = 0
                as_traded_close = 0.0
                split_norm_close = 0.0
                vol = 0
            else:
                n_hist = len(hist_slice)
                as_traded_close = float(
                    hist_slice["as_traded_close"].iloc[-1]
                    if "as_traded_close" in hist_slice.columns
                    else hist_slice["close"].iloc[-1]
                )
                split_norm_close = float(hist_slice["close"].iloc[-1])
                vol = int(hist_slice["volume"].iloc[-1])
        else:
            hist_slice = bars_df.iloc[: idx + 1]
            n_hist = len(hist_slice)
            as_traded_close = float(
                hist_slice["as_traded_close"].iloc[-1]
                if "as_traded_close" in hist_slice.columns
                else hist_slice["close"].iloc[-1]
            )
            split_norm_close = float(hist_slice["close"].iloc[-1])
            vol = int(hist_slice["volume"].iloc[-1])

        # As-traded dollar volume: strictly computed as as-traded close * volume
        if "as_traded_close" in hist_slice.columns:
            as_traded_closes_20 = hist_slice["as_traded_close"].iloc[-20:].tolist() if n_hist >= 20 else []
            as_traded_closes_60 = hist_slice["as_traded_close"].iloc[-60:].tolist() if n_hist >= 60 else []
        else:
            as_traded_closes_20 = hist_slice["close"].iloc[-20:].tolist() if n_hist >= 20 else []
            as_traded_closes_60 = hist_slice["close"].iloc[-60:].tolist() if n_hist >= 60 else []

        vols_20 = hist_slice["volume"].iloc[-20:].tolist() if n_hist >= 20 else []
        vols_60 = hist_slice["volume"].iloc[-60:].tolist() if n_hist >= 60 else []

        dollar_vols_20 = [c * v for c, v in zip(as_traded_closes_20, vols_20)]
        dvol_20_median = float(np.median(dollar_vols_20)) if len(dollar_vols_20) >= 20 else None

        dollar_vols_60 = [c * v for c, v in zip(as_traded_closes_60, vols_60)]
        dvol_60_median = float(np.median(dollar_vols_60)) if len(dollar_vols_60) >= 60 else None

        # Price floor: 20-session median as-traded close >= 5 and current as-traded close >= 5
        med_close_20 = float(np.median(as_traded_closes_20)) if len(as_traded_closes_20) >= 20 else None

        # ATR 14 calculation on split-normalized series
        highs = hist_slice["high"].tolist()
        lows = hist_slice["low"].tolist()
        closes = hist_slice["close"].tolist()
        atr_14 = compute_atr(highs, lows, closes, 14)

        # Classification gate: fail closed on unknown or non-common stock
        is_common = identity.is_common_stock
        class_status = (
            "supported_common_stock"
            if is_common
            else (
                "unknown_fail_closed"
                if identity.security_type == "unknown"
                else "excluded_security_type"
            )
        )
        classifications.append(
            SecurityClassificationStatus(
                immutable_security_id=sec_id,
                as_of_date=session_date,
                ticker_at_decision=ticker,
                inferred_classification=identity.security_type,
                classification_status=class_status,
                is_eligible_common_stock=is_common,
                provenance_source="security_master",
                provider_type_code=identity.security_type,
            )
        )

        # Eligibility evaluation
        rejection_reasons: list[str] = []
        if ticker_unresolved:
            rejection_reasons.append("ticker_unresolved_at_decision")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="ticker_unresolved_at_decision",
                    ticker_at_decision=ticker,
                    reason_category="identity",
                    description=f"No verified active ticker interval covers session {session_date} (fail closed)",
                )
            )

        if not is_common:
            rejection_reasons.append(f"excluded_classification_{identity.security_type}")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code=f"excluded_classification_{identity.security_type}",
                    ticker_at_decision=ticker,
                    reason_category="security_type",
                    description=f"Security classification '{identity.security_type}' is not verified common stock (fail closed)",
                )
            )

        price_gte_5 = as_traded_close >= 5.0 and (med_close_20 is not None and med_close_20 >= 5.0)
        if not price_gte_5:
            rejection_reasons.append("price_below_5")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="price_below_5",
                    ticker_at_decision=ticker,
                    reason_category="price",
                    description=f"As-traded price {as_traded_close:.2f} or 20d median below $5 floor",
                )
            )

        dvol_20_gte_20m = dvol_20_median is not None and dvol_20_median >= 20_000_000.0
        if not dvol_20_gte_20m:
            rejection_reasons.append("dollar_volume_20d_below_20m")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="dollar_volume_20d_below_20m",
                    ticker_at_decision=ticker,
                    reason_category="liquidity",
                    description="20-session median as-traded dollar volume below $20M",
                )
            )

        dvol_60_gte_10m = dvol_60_median is not None and dvol_60_median >= 10_000_000.0
        if dvol_60_median is not None and not dvol_60_gte_10m:
            rejection_reasons.append("dollar_volume_60d_below_10m")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="dollar_volume_60d_below_10m",
                    ticker_at_decision=ticker,
                    reason_category="liquidity",
                    description="60-session median as-traded dollar volume below $10M",
                )
            )

        # Cohort type determination with listing provenance
        if n_hist >= 252:
            cohort_type = "established"
        elif 63 <= n_hist < 252:
            # Requires positive listing date / prospectus provenance to be classified as recent_ipo
            has_listing_provenance = False
            if identity.listing_date:
                try:
                    dt_listing = date.fromisoformat(identity.listing_date[:10])
                    dt_session = date.fromisoformat(session_date[:10])
                    calendar_days_since_listing = (dt_session - dt_listing).days
                    if 0 <= calendar_days_since_listing <= 365:
                        has_listing_provenance = True
                except ValueError:
                    has_listing_provenance = False

            if has_listing_provenance:
                cohort_type = "recent_ipo"
            else:
                cohort_type = "unverified_history_truncated"
                rejection_reasons.append("unverified_history_truncated")
                exclusions.append(
                    ExclusionReasonRecord(
                        immutable_security_id=sec_id,
                        as_of_date=session_date,
                        cutoff_time=cutoff_time,
                        reason_code="unverified_history_truncated",
                        ticker_at_decision=ticker,
                        reason_category="trading_history",
                        description=f"Provider history has {n_hist} sessions but lacks verified IPO listing provenance; cannot assume IPO",
                    )
                )
        else:
            cohort_type = "insufficient_history"
            rejection_reasons.append("insufficient_trading_history")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="insufficient_trading_history",
                    ticker_at_decision=ticker,
                    reason_category="trading_history",
                    description=f"Only {n_hist} trading sessions available (< 63 minimum)",
                )
            )

        # Market cap gate: fail-closed (missing is None and NEVER passes)
        mcap_val = market_caps.get(session_date) if market_caps else None
        mcap_gte_3b = (mcap_val >= 3_000_000_000.0) if mcap_val is not None else None
        index_verified = bool(index_memberships.get(session_date, False)) if index_memberships else False

        if mcap_val is not None:
            mcap_reason = "valid_ge_3b" if mcap_gte_3b else "valid_below_3b"
        else:
            mcap_reason = (
                market_cap_reasons.get(session_date, "missing_shares")
                if market_cap_reasons
                else "missing_shares"
            )

        # Fail closed: must have verified mcap >= $3B OR verified index membership point-in-time
        if not (mcap_gte_3b is True or index_verified is True):
            rejection_reasons.append("market_cap_or_index_unverified")
            rejection_reasons.append(f"market_cap_{mcap_reason}")
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code=f"market_cap_{mcap_reason}",
                    ticker_at_decision=ticker,
                    reason_category="market_cap",
                    description=f"Neither point-in-time market cap >= $3B ({mcap_reason}) nor verified index membership available (fail closed)",
                )
            )

        eligibility_passed = len(rejection_reasons) == 0

        eligibilities.append(
            DataEligibility(
                immutable_security_id=sec_id,
                ticker_at_decision=ticker,
                as_of_date=session_date,
                cutoff_time=cutoff_time,
                price_gte_5=price_gte_5,
                dollar_volume_20d_gte_20m=dvol_20_gte_20m,
                trading_history_sessions=n_hist,
                cohort_type=cohort_type,
                eligibility_passed=eligibility_passed,
                rejection_reason_codes=rejection_reasons,
                dollar_volume_60d_gte_10m=dvol_60_gte_10m,
                market_cap=mcap_val,
                market_cap_gte_3b=mcap_gte_3b,
                index_membership_verified=index_verified,
            )
        )

        # Earnings schedule status
        e_info = earnings_schedules.get(session_date) if earnings_schedules else None
        if e_info and e_info.get("next_earnings_date"):
            e_status = "known_point_in_time"
            next_e_date = e_info.get("next_earnings_date")
            ann_timing = e_info.get("announcement_timing")
            sessions_to_e = e_info.get("sessions_to_earnings")
        else:
            e_status = "unknown"
            next_e_date = None
            ann_timing = None
            sessions_to_e = None

        earnings_records.append(
            EarningsScheduleStatus(
                immutable_security_id=sec_id,
                as_of_date=session_date,
                cutoff_time=cutoff_time,
                ticker_at_decision=ticker,
                schedule_status=e_status,
                provenance_source="sec_edgar_or_provider",
                next_earnings_date=next_e_date,
                announcement_timing=ann_timing,
                sessions_to_earnings=sessions_to_e,
            )
        )

        # Boundary purge check (26 forward sessions into 2021)
        purged = check_split_boundary_purge(session_date, dev_end=dev_end)
        if purged:
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="split_boundary_purged",
                    ticker_at_decision=ticker,
                    reason_category="split_boundary",
                    description="Forward 26-session outcome window crosses beyond development split (2020-12-31)",
                )
            )

        # Special distribution exclusion check
        has_unresolved_dist = (
            special_distribution_dates is not None
            and session_date in special_distribution_dates
        )
        if has_unresolved_dist:
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code="special_distribution_unresolved",
                    ticker_at_decision=ticker,
                    reason_category="corporate_action",
                    description="Unresolved special distribution or spin-off inside outcome horizon",
                )
            )

        # Actionability status: if earnings schedule unknown, actionability is unavailable
        if not eligibility_passed:
            act_status = "excluded"
        elif atr_14 is None or dvol_20_median is None:
            act_status = "unavailable_data_incomplete"
        elif e_status == "unknown":
            act_status = "unavailable_earnings_unknown"
        else:
            act_status = "eligible"

        data_complete = (atr_14 is not None) and (dvol_20_median is not None)
        raw_eligible = eligibility_passed and data_complete and not purged and not has_unresolved_dist

        dec_ts_utc = get_decision_timestamp_utc(session_date, cutoff_time)

        observations.append(
            DecisionObservation(
                immutable_security_id=sec_id,
                ticker_at_decision=ticker,
                as_of_date=session_date,
                cutoff_time=cutoff_time,
                decision_timestamp_utc=dec_ts_utc,
                as_traded_close=round(as_traded_close, 4),
                split_normalized_close=round(split_norm_close, 4),
                volume=vol,
                immutable_issuer_id=identity.cik,
                dollar_volume_20d_median=round(dvol_20_median, 2) if dvol_20_median else None,
                atr_14=atr_14,
                raw_outcome_eligible=raw_eligible,
                universe_eligible=eligibility_passed,
                data_complete=data_complete,
                earnings_schedule_status="known" if e_status == "known_point_in_time" else "unknown",
                actionability_status=act_status,
                split_boundary_purged=purged,
            )
        )

    return observations, eligibilities, classifications, earnings_records, exclusions, coverage
