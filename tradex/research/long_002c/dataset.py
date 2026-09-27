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


def compute_atr_series(
    highs: list[float] | np.ndarray,
    lows: list[float] | np.ndarray,
    closes: list[float] | np.ndarray,
    period: int = 14,
) -> list[float | None]:
    """Calculate Wilder's ATR series over all bars in a single O(N) pass.

    The value at index i matches compute_atr(highs[:i+1], lows[:i+1], closes[:i+1], period).
    """
    n = len(closes)
    atrs: list[float | None] = [None] * n
    if n < period + 1:
        return atrs
    tr_list: list[float] = []
    for i in range(1, n):
        h = float(highs[i])
        l = float(lows[i])
        prev_c = float(closes[i - 1])
        tr_list.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))

    curr_unrounded = sum(tr_list[:period]) / period
    atrs[period] = round(curr_unrounded, 4)
    for j in range(period, len(tr_list)):
        curr_unrounded = (curr_unrounded * (period - 1) + tr_list[j]) / period
        atrs[j + 1] = round(curr_unrounded, 4)

    return atrs


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
    bar_meta: dict[str, Any] | None = None,
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
    bar_date_to_idx = {d: i for i, d in enumerate(bar_dates)}
    n_bars = len(bars_df)

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

    # Extract NumPy arrays for O(1) vectorized metric computations
    open_arr = bars_df["open"].to_numpy(dtype=float)
    high_arr = bars_df["high"].to_numpy(dtype=float)
    low_arr = bars_df["low"].to_numpy(dtype=float)
    close_arr = bars_df["close"].to_numpy(dtype=float)
    vol_arr = bars_df["volume"].to_numpy(dtype=float)
    as_traded_close_arr = (
        bars_df["as_traded_close"].to_numpy(dtype=float)
        if "as_traded_close" in bars_df.columns
        else close_arr
    )
    dollar_vol_arr = as_traded_close_arr * vol_arr

    # Audit duplicate and malformed bars across the entire provided bars_df
    dup_bar_count = int(bars_df.index.duplicated().sum())
    malformed_bar_flags = [False] * n_bars
    analytical_incomplete_flags = [False] * n_bars
    for i in range(n_bars):
        ac = as_traded_close_arr[i]
        c = close_arr[i]
        o = open_arr[i]
        h = high_arr[i]
        l = low_arr[i]
        v = vol_arr[i]
        if np.isnan(c) or np.isnan(o) or np.isnan(h) or np.isnan(l):
            analytical_incomplete_flags[i] = True
        if (
            (not np.isnan(ac) and ac <= 0)
            or (not np.isnan(c) and c <= 0)
            or (not np.isnan(v) and v < 0)
            or (not np.isnan(h) and not np.isnan(l) and h < l)
        ):
            malformed_bar_flags[i] = True

    total_malformed_count = sum(malformed_bar_flags)

    coverage = DataQualityCoverage(
        immutable_security_id=sec_id,
        split_name="development",
        expected_sessions=expected_count,
        observed_sessions=observed_count,
        completeness_pct=round(completeness_pct, 2),
        unexplained_missing_sessions=unexplained_missing,
        max_consecutive_missing_sessions=max_consec,
        duplicate_bar_count=dup_bar_count,
        malformed_bar_count=total_malformed_count,
        halt_sessions_count=0,
    )

    # Precompute Wilder ATR series once for the entire bar history (Item 3)
    atrs_14 = compute_atr_series(high_arr, low_arr, close_arr, 14)

    # Precompute session to index map once outside the session loop (Item 1)
    session_to_idx = {s: i for i, s in enumerate(trading_sessions)}

    listing_date_str = None
    if candidate is not None and isinstance(candidate.listing_lifecycle_provenance, dict):
        listing_date_str = candidate.listing_lifecycle_provenance.get("listing_date")
    if not listing_date_str and identity.listing_date:
        listing_date_str = identity.listing_date
    dt_listing = None
    if listing_date_str:
        try:
            dt_listing = date.fromisoformat(listing_date_str[:10])
        except ValueError:
            dt_listing = None

    analytical_incomplete_dates = (
        set(bar_meta.get("analytical_incomplete_dates", [])) if bar_meta else set()
    )

    # Process each trading session in the development window
    for session_date in dev_sessions:
        if session_date not in bar_date_set:
            # Session missing from provider history
            continue

        idx = bar_date_to_idx[session_date]

        # Resolve effective historical ticker at decision date
        ticker_unresolved = False
        ticker = ""
        if candidate is not None:
            interval = candidate.resolve_interval(session_date)
            if interval is not None:
                ticker = interval.symbol
            else:
                ticker_unresolved = True
                ticker = ""
        elif security_master is not None:
            resolved = security_master.resolve_ticker(sec_id, session_date)
            if resolved is not None:
                ticker = resolved
            else:
                ticker_unresolved = True
                ticker = ""
        else:
            if "ticker_at_decision" in bars_df.columns and session_date in bar_date_set:
                val = bars_df.loc[session_date, "ticker_at_decision"]
                val_str = str(val.iloc[-1] if isinstance(val, pd.Series) else val)
                if val_str and val_str != "nan":
                    ticker = val_str
                else:
                    ticker = identity.ticker_at_decision or ""
            else:
                ticker = identity.ticker_at_decision or ""
            if not ticker:
                ticker_unresolved = True

        # Point-in-time history:
        # At 09:00 ET, session T has not opened. Features MUST use history strictly through session T-1 (prior completed session).
        # At 20:30 ET, session T has completed. Features include session T.
        end = idx if cutoff_time == "09:00" else idx + 1
        n_hist = end
        if end == 0:
            as_traded_close = 0.0
            split_norm_close = 0.0
            vol = 0
            atr_14 = None
            med_close_20 = None
            dvol_20_median = None
            dvol_60_median = None
        else:
            as_traded_close = float(as_traded_close_arr[end - 1])
            split_norm_close = float(close_arr[end - 1])
            vol = int(vol_arr[end - 1])
            atr_14 = atrs_14[end - 1]
            if end >= 20:
                med_close_20 = float(np.median(as_traded_close_arr[end - 20 : end]))
                dvol_20_median = float(np.median(dollar_vol_arr[end - 20 : end]))
            else:
                med_close_20 = None
                dvol_20_median = None
            if end >= 60:
                dvol_60_median = float(np.median(dollar_vol_arr[end - 60 : end]))
            else:
                dvol_60_median = None

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
        mcap_gte_3b = bool(mcap_val >= 3_000_000_000.0) if mcap_val is not None else None
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

        # Trailing history quality evaluation (trailing 252 regular sessions or from listing date for IPOs)
        s_idx = session_to_idx.get(session_date, -1)

        is_recent_ipo_window = False
        if dt_listing:
            try:
                dt_session = date.fromisoformat(session_date[:10])
                days_since_listing = (dt_session - dt_listing).days
                if 0 <= days_since_listing <= 365:
                    is_recent_ipo_window = True
            except ValueError:
                is_recent_ipo_window = False

        if is_recent_ipo_window and listing_date_str:
            expected_trailing_sessions = [
                s for s in trading_sessions if listing_date_str[:10] <= s <= session_date
            ]
        else:
            start_s_idx = max(0, s_idx - 251) if s_idx >= 0 else 0
            expected_trailing_sessions = trading_sessions[start_s_idx : s_idx + 1] if s_idx >= 0 else []

        exp_trailing_count = len(expected_trailing_sessions)
        obs_trailing_sessions = [s for s in expected_trailing_sessions if s in bar_date_set]
        obs_trailing_count = len(obs_trailing_sessions)
        missing_trailing_count = exp_trailing_count - obs_trailing_count
        trailing_completeness_pct = (obs_trailing_count / exp_trailing_count * 100.0) if exp_trailing_count > 0 else 0.0

        max_consec_trailing = 0
        curr_consec_trailing = 0
        for s in expected_trailing_sessions:
            if s not in bar_date_set:
                curr_consec_trailing += 1
                max_consec_trailing = max(max_consec_trailing, curr_consec_trailing)
            else:
                curr_consec_trailing = 0

        # Check malformed bars and analytical completeness in trailing slice via precomputed flags (Item 2)
        trailing_malformed = 0
        trailing_analytical_incomplete = False
        if analytical_incomplete_dates and not analytical_incomplete_dates.isdisjoint(expected_trailing_sessions):
            trailing_analytical_incomplete = True

        for s in obs_trailing_sessions:
            b_idx = bar_date_to_idx[s]
            if malformed_bar_flags[b_idx]:
                trailing_malformed += 1
            if analytical_incomplete_flags[b_idx]:
                trailing_analytical_incomplete = True

        data_quality_reasons: list[str] = []
        if n_hist >= 63 and exp_trailing_count >= 63:
            if trailing_completeness_pct < 99.0:
                data_quality_reasons.append("data_quality_completeness_below_99")
            if missing_trailing_count > 2:
                data_quality_reasons.append("data_quality_missing_sessions_exceeded")
            if max_consec_trailing > 1:
                data_quality_reasons.append("data_quality_consecutive_missing_exceeded")
        if dup_bar_count > 0:
            data_quality_reasons.append("data_quality_duplicate_bars")
        if trailing_malformed > 0:
            data_quality_reasons.append("data_quality_malformed_bars")
        if trailing_analytical_incomplete:
            data_quality_reasons.append("analytical_data_incomplete")

        data_quality_passed = len(data_quality_reasons) == 0
        for r_code in data_quality_reasons:
            exclusions.append(
                ExclusionReasonRecord(
                    immutable_security_id=sec_id,
                    as_of_date=session_date,
                    cutoff_time=cutoff_time,
                    reason_code=r_code,
                    ticker_at_decision=ticker,
                    reason_category="data_quality",
                    description=f"Data quality failure: {r_code}",
                )
            )

        data_complete = (
            (atr_14 is not None)
            and (dvol_20_median is not None)
            and data_quality_passed
            and not trailing_analytical_incomplete
        )
        raw_eligible = (
            eligibility_passed
            and data_complete
            and not purged
            and not has_unresolved_dist
        )

        # Actionability status: if earnings schedule unknown, actionability is unavailable
        if not eligibility_passed:
            act_status = "excluded"
        elif not data_complete:
            act_status = "unavailable_data_incomplete"
        elif e_status == "unknown":
            act_status = "unavailable_earnings_unknown"
        else:
            act_status = "eligible"

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
                earnings_schedule_status="known_point_in_time" if e_status == "known_point_in_time" else "unknown",
                actionability_status=act_status,
                split_boundary_purged=purged,
            )
        )

    return observations, eligibilities, classifications, earnings_records, exclusions, coverage
