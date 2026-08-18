"""MVP-ARCH-001: TradeX provider, strategy, and dashboard consolidation decision packet.

This module generates the human-readable and machine-readable consolidation plan.
It performs no provider calls, uses no credentials, and makes no product changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STARTING_MAIN_SHA = "52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2"

_PROVIDER_LIFECYCLES = {
    "operational_primary",
    "operational_fallback",
    "specialized_reference",
    "research_only",
    "experimental",
    "archived",
}

_DASHBOARD_DISPOSITIONS = {
    "keep_primary",
    "keep_but_relabel",
    "merge_into_workflow",
    "move_to_research_lab",
    "replace",
    "archive",
}

_EVIDENCE_STATES = {
    "legacy_heuristic",
    "exploratory",
    "research_only",
    "not_supported",
    "rejected",
    "inconclusive",
    "shadow",
    "production_approved",
    "archived",
}


def build_inventory() -> dict[str, Any]:
    """Return the MVP-ARCH-001 decision inventory as a JSON-safe dict."""
    return {
        "artifact_id": "MVP-ARCH-001",
        "schema_version": "1.0",
        "classification": "product-architecture-and-governance-design-only",
        "task_id": "MVP-ARCH-001",
        "program_id": "TradeX",
        "decision_status": "pending_gary_decision",
        "gary_approval_source": "pending; this packet is advisory and requires Gary's explicit selection before any implementation PR",
        "starting_main_sha": STARTING_MAIN_SHA,
        "prerequisite_commit": STARTING_MAIN_SHA,
        "authorization": {
            "production_behavior_changes_authorized": False,
            "provider_calls_authorized": False,
            "dashboard_changes_authorized": False,
            "provider_removal_authorized": False,
            "alert_changes_authorized": False,
            "database_migration_authorized": False,
            "strategy_promotion_authorized": False,
            "long_002c_work_authorized": False,
            "pr_merge_authorized_without_gary_decision": False,
        },
        "product_summary": {
            "diagnosis": (
                "TradeX has a strong modular technical and research foundation, but the current "
                "product is a collection of scanners, context tools, and research pipelines rather "
                "than one cohesive daily decision-support workflow. The MVP objective is to "
                "consolidate around a single understandable daily job: surface, evaluate, and "
                "review a small set of actionable long-candidates while quarantining research, "
                "context, and unproven heuristics."
            ),
            "primary_daily_job": (
                "Help Gary discover, evaluate, monitor, and review a small set of actionable "
                "long-only swing candidates each trading day, with explicit evidence, data confidence, "
                "and unknown-value handling."
            ),
            "first_screen": (
                "The Today view: a prioritized list of Enter Now / Armed / Waitlist candidates, "
                "with pre-market, earnings, and market context attached. Nothing else competes for "
                "attention until Gary clicks into a candidate."
            ),
        },
        "product_questions": [
            {
                "question": "What is TradeX's primary daily job for Gary?",
                "answer": "Discover, evaluate, monitor, and review a small set of actionable long-only swing candidates each trading day.",
            },
            {
                "question": "What should Gary see first when opening the application?",
                "answer": "Today — Enter Now, Armed, and Waitlist candidates with context and data-confidence badges.",
            },
            {
                "question": "Which current features directly support that job?",
                "answer": "Scanner (after relabeling), Pre-Market (as context), Candidate Detail (future), and Journal (future).",
            },
            {
                "question": "Which features are useful only as context?",
                "answer": "Pre-Market gaps, earnings proximity, confluence aggregation, and coil detector persistence metrics.",
            },
            {
                "question": "Which features belong exclusively in Research Lab?",
                "answer": "Pattern Similarity, Score validation (VAL-002), LONG-001/SHORT-001/INTRA-001/LONG-002 artifacts, and research-only parameter studies.",
            },
            {
                "question": "Which features should be archived?",
                "answer": "Pattern Similarity primary navigation, Options Activity primary navigation, Signal Journal as a performance claim, and Weights as an untuned user-facing control.",
            },
            {
                "question": "Which outputs can currently support actionability, and which cannot?",
                "answer": "None of the existing numeric scores or heuristics are validated as executable strategies; they may be used only as discovery/context. A candidate must carry an approved strategy ID, entry plan, stop, target, and invalidation before it can be actioned.",
            },
            {
                "question": "What evidence must exist before an experimental system becomes part of the primary workflow?",
                "answer": "A locked research protocol, development evidence, validation and untouched-holdout gates, paired executable backtests, and a separate Gary-approved production PR that defines strategy ID, version, entry/stop/target/expiration, and universe.",
            },
            {
                "question": "How should TradeX measure whether a complete strategy worked?",
                "answer": "Using an executable journal that records the planned entry, realized fill, stop/target/expiration outcome, slippage, costs, and provider provenance per strategy version — not generic 1/3/5-session signal returns.",
            },
            {
                "question": "What is the smallest sequence of changes that turns the existing foundation into a cohesive MVP?",
                "answer": "1. Truthful labels and evidence badges; 2. Provider lifecycle/config simplification; 3. Navigation consolidation; 4. Alert gating; 5. Candidate persistence contract; 6. Journal/outcome replacement; 7. Prospective PIT data capture; 8. Later LONG-002C resumption.",
            },
        ],
        "provider_inventory": [
            {
                "name": "yahoo",
                "roles": ["ohlcv", "premarket_bars", "earnings", "market_cap_ranking", "options_chain_snapshot"],
                "production_runtime": True,
                "research_use": True,
                "credential_burden": "none",
                "delay_feed_entitlement": "15-min delayed intraday; free daily/weekly; no entitlement check",
                "pit_reliability": "not point-in-time; historical adjustments and splits may differ from premium sources",
                "fallback_behavior": "Default OHLCV provider; pre-market only supports Yahoo; no silent fallback from other providers to Yahoo for intraday execution",
                "mix_in_scan_or_outcome": "FetchReport records actual_provider; signal_history and outcome_tracker store provider provenance; mixing is visible, not hidden",
                "recommended_lifecycle": "operational_fallback",
                "recommended_role": "Daily/weekly/research OHLCV fallback; earnings treated as current/prospective only; unknown values must fail visibly",
            },
            {
                "name": "schwab",
                "roles": ["ohlcv", "market_cap_ranking", "liquidity_filter_fundamentals"],
                "production_runtime": True,
                "research_use": True,
                "credential_burden": "Schwab brokerage account + OAuth app + local token file",
                "delay_feed_entitlement": "Real-time US equity data if entitled; account required",
                "pit_reliability": "Used for PATTERN-001, SHORT-001, and other research with UTC-indexed, sorted, de-duplicated daily bars",
                "fallback_behavior": "Configured as DATA_PROVIDER; whole-scan fallback disabled unless explicitly set via OHLCV_FALLBACK_ORDER",
                "mix_in_scan_or_outcome": "Provenance stored separately; outcome tracker may use different provider from signal provider",
                "recommended_lifecycle": "operational_primary",
                "recommended_role": "Primary operational OHLCV provider when configured; used for daily-history and outcome resolution",
            },
            {
                "name": "alpaca",
                "roles": ["ohlcv"],
                "production_runtime": True,
                "research_use": True,
                "credential_burden": "API key + secret key",
                "delay_feed_entitlement": "Free tier IEX feed; real-time but may differ from SIP/consolidated tape",
                "pit_reliability": "Historical daily bars validated in LONG-002B; SIP/feed limitations must be exposed",
                "fallback_behavior": "Currently a whole-scan fallback if configured in OHLCV_FALLBACK_ORDER",
                "mix_in_scan_or_outcome": "actual_provider recorded in FetchReport and signal_history",
                "recommended_lifecycle": "operational_fallback",
                "recommended_role": "Explicitly degraded intraday fallback only if IEX/feed limitations are visible and tested; not a silent replacement for Schwab",
            },
            {
                "name": "ibkr",
                "roles": ["ohlcv"],
                "production_runtime": True,
                "research_use": False,
                "credential_burden": "IB account + TWS/IB Gateway running locally",
                "delay_feed_entitlement": "Real-time global markets; requires local gateway",
                "pit_reliability": "Not used in any research artifact",
                "fallback_behavior": "Supported in fetcher but not configured by default",
                "mix_in_scan_or_outcome": "Could be primary or fallback if configured",
                "recommended_lifecycle": "archived",
                "recommended_role": "Archive from MVP unless Gary explicitly selects IBKR as intended brokerage or global-market platform",
            },
            {
                "name": "massive_polygon",
                "roles": ["ohlcv", "reference_ticker_data", "corporate_actions"],
                "production_runtime": False,
                "research_use": True,
                "credential_burden": "API key",
                "delay_feed_entitlement": "Paid/institutional entitlement; v2/aggs returned 403 in LONG-002B probes",
                "pit_reliability": "Reference endpoints provide per-ticker PIT rows but generic type codes do not satisfy LONG-002 exclusion contract",
                "fallback_behavior": "Used as research/reference only; not integrated into operational fallback chain",
                "mix_in_scan_or_outcome": "Not used in production scans",
                "recommended_lifecycle": "research_only",
                "recommended_role": "Retain for research/reference and PIT data-family probes; do not promote to operational primary without a new Gary-approved amendment",
            },
            {
                "name": "sec_edgar",
                "roles": ["filings", "fundamentals", "shares", "issuer_identity"],
                "production_runtime": False,
                "research_use": True,
                "credential_burden": "none (public, rate-limited)",
                "delay_feed_entitlement": "Public filing acceptance timestamps; not real-time quotes",
                "pit_reliability": "Demonstrated PIT shares/filing acceptance-time control in LONG-002B; acceptance timestamps are actual disclosure, not previously known schedules",
                "fallback_behavior": "Specialized source used directly in long_002_data_feasibility; not a general fallback",
                "mix_in_scan_or_outcome": "Not mixed with OHLCV outcomes; used for fundamental/identity validation",
                "recommended_lifecycle": "specialized_reference",
                "recommended_role": "Primary specialized filing/fundamental source; useful for identity and shares, not for earnings-calendar scheduling",
            },
            {
                "name": "unusual_whales",
                "roles": ["options_true_flow"],
                "production_runtime": False,
                "research_use": False,
                "credential_burden": "Paid API key",
                "delay_feed_entitlement": "Transaction-level options flow if paid and configured",
                "pit_reliability": "Not validated as a decision input; no research artifact uses it",
                "fallback_behavior": "Chain/flow source resolution is explicit; no silent fallback",
                "mix_in_scan_or_outcome": "Not used in signal or outcome records",
                "recommended_lifecycle": "experimental",
                "recommended_role": "Archive from core MVP unless a defined strategy and adequate source are approved separately; true flow may return to Research Lab",
            },
            {
                "name": "tradier",
                "roles": ["options_chain_snapshot"],
                "production_runtime": False,
                "research_use": False,
                "credential_burden": "API key",
                "delay_feed_entitlement": "Option-chain snapshots; not transaction flow",
                "pit_reliability": "Not validated as a decision input",
                "fallback_behavior": "Explicit options source selection only",
                "mix_in_scan_or_outcome": "Not used in signal or outcome records",
                "recommended_lifecycle": "experimental",
                "recommended_role": "Archive from core MVP unless a defined options use case is approved; chain snapshots are not directional signal evidence",
            },
            {
                "name": "wikipedia",
                "roles": ["constituent_lists"],
                "production_runtime": True,
                "research_use": False,
                "credential_burden": "none; web scraping with user-agent header",
                "delay_feed_entitlement": "Current index constituents only; no historical PIT membership",
                "pit_reliability": "Not point-in-time; rebalancing drift and survivorship bias",
                "fallback_behavior": "Not a fallback for market data",
                "mix_in_scan_or_outcome": "Used only for watchlist preset refresh",
                "recommended_lifecycle": "specialized_reference",
                "recommended_role": "Continue as watchlist constituent source, refreshed explicitly, with no claim of historical accuracy",
            },
        ],
        "provider_recommendation": {
            "target_principle": "one authoritative provider per capability, with at most one explicit fallback",
            "notes": "Fallbacks must never silently convert delayed, partial, or differently sourced data into equivalent actionable evidence.",
            "mapping": {
                "ohlcv": {
                    "primary": "schwab",
                    "fallback": "alpaca (only as explicitly degraded intraday fallback with visible IEX/feed limitations)",
                    "research_fallback": "yahoo (daily/weekly research and fallback; not silent actionable intraday fallback)",
                },
                "premarket_bars": {
                    "primary": "yahoo",
                    "note": "Only Yahoo currently supports pre-market bars; this is a known capability gap, not a recommendation to treat Yahoo as equivalent to real-time OHLCV.",
                },
                "filings_fundamentals_shares": {
                    "primary": "sec_edgar",
                    "note": "Use acceptance-time controls and keep filing dates separate from known-at-time earnings schedules.",
                },
                "constituents": {
                    "primary": "wikipedia",
                    "note": "Point-in-time membership must be confirmed separately before any research production.",
                },
                "earnings": {
                    "primary": "(none verified)",
                    "current": "yahoo",
                    "note": "Yahoo earnings are current/prospective, not historical PIT. Unknown values must fail visibly; do not substitute SEC filing or actual release timestamps.",
                },
                "options": {
                    "status": "removed from core MVP",
                    "note": "Options Activity should be archived from primary navigation unless a defined strategy and adequate source are approved in a separate PR.",
                },
                "research_reference": {
                    "primary": "massive_polygon",
                    "note": "Retain for research/reference and data-family probes only.",
                },
                "global_brokerage": {
                    "status": "archived",
                    "note": "IBKR archived unless Gary later selects it as the intended brokerage or global-market platform.",
                },
            },
        },
        "dashboard_inventory": [
            {
                "tab": "Scanner",
                "user_problem": "Which stocks are currently scoring highest on technical conditions?",
                "data_and_logic": "Runs one of three timeframe scorers (intraday/short/long) over a watchlist and returns a 0-100 additive score with reasons.",
                "classification": "exploratory_scorer",
                "supporting_disposition": "Production scorers are legacy heuristics; no research program validated them as executable strategies.",
                "current_overstatement": "UI language treats high scores as 'setups' and the sidebar labels higher scores as 'higher conviction'.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "keep_but_relabel",
                "recommended_action": "Relabel as 'Scanner (exploratory)' and add evidence badges distinguishing signal, context, and unvalidated heuristic.",
            },
            {
                "tab": "Coil Detector",
                "user_problem": "Which stocks have appeared repeatedly without breaking out?",
                "data_and_logic": "Reads signal_history / scan_observations and scores persistence, active-session ratio, and score trend.",
                "classification": "context",
                "supporting_disposition": "Exploratory; coil_strength formula is a heuristic, not a validated edge.",
                "current_overstatement": "Help text describes coils as letting you 'get positioned before the obvious move'.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "move_to_research_lab",
                "recommended_action": "Move to Research Lab as 'Coil context'; keep the code and tests intact.",
            },
            {
                "tab": "Confluence",
                "user_problem": "Which stocks look strong across multiple timeframes?",
                "data_and_logic": "Weighted coverage-aware aggregation of the three unvalidated timeframe scores.",
                "classification": "context",
                "supporting_disposition": "VAL-002 and related score validation do not establish that confluence predicts executable outcomes.",
                "current_overstatement": "Caption calls results 'much higher conviction setups' and 'all timeframes aligned'.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "keep_but_relabel",
                "recommended_action": "Keep as context-only; replace 'conviction' language with 'alignment of exploratory scores' and show coverage/missing-timeframe metadata.",
            },
            {
                "tab": "Pattern Similarity",
                "user_problem": "Which stocks resemble historical run-up/decline shapes?",
                "data_and_logic": "Pearson similarity against mined fingerprints from a fixed universe.",
                "classification": "research_only",
                "supporting_disposition": "PATTERN-001 was rejected on holdout; production promotion is false.",
                "current_overstatement": "Help tab lists Pattern Match as a recommended third step in a first session.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "archive",
                "recommended_action": "Remove from primary navigation; preserve code, tests, and artifact bundle in Research Lab.",
            },
            {
                "tab": "Pre-Market",
                "user_problem": "Which stocks are gapping before the open and why?",
                "data_and_logic": "Pre-market bars, previous close, catalyst context, liquidity, and spread filters.",
                "classification": "event_detector",
                "supporting_disposition": "Gap scanner is source-aware and marks failures visibly; only Yahoo supports pre-market bars.",
                "current_overstatement": "Tier labels like 'large' and 'massive' gap can be read as trade recommendations.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "keep_but_relabel",
                "recommended_action": "Retain as event/context discovery; add badges showing gap is not an approved strategy entry.",
            },
            {
                "tab": "Options Activity",
                "user_problem": "Is there unusual options flow or chain activity?",
                "data_and_logic": "Resolves Unusual Whales (true flow), Tradier, or Yahoo chain snapshots; computes put/call balance.",
                "classification": "context",
                "supporting_disposition": "No defined strategy uses options data; no validated PIT options edge.",
                "current_overstatement": "Tab name implies actionability; most users will have no true-flow source configured.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "archive",
                "recommended_action": "Remove from primary navigation unless a separately approved strategy and source are defined.",
            },
            {
                "tab": "Alerts",
                "user_problem": "Notify me when thresholds are crossed.",
                "data_and_logic": "Cooldown policy, atomic claim, Discord/email delivery for coil, confluence, and gap thresholds.",
                "classification": "settings_infrastructure",
                "supporting_disposition": "Alert infrastructure is sound, but it currently fires on unvalidated heuristics.",
                "current_overstatement": "Alerts are presented as if coil/confluence/gap outputs are actionable thresholds.",
                "actionable": True,
                "outcome_measurement_valid": False,
                "recommended_disposition": "merge_into_workflow",
                "recommended_action": "Keep the delivery infrastructure; move configuration into a future Settings area and gate automatic actionable alerts to approved strategies only.",
            },
            {
                "tab": "Signal Journal",
                "user_problem": "Did my signals work?",
                "data_and_logic": "Compares signal close to 1/3/5-session later closes and computes win rate/expectancy.",
                "classification": "legacy_signal_telemetry",
                "supporting_disposition": "Uses generic horizons, not strategy-specific entry/stop/target/expiration; does not prove edge.",
                "current_overstatement": "Help text claims expectancy is 'the most important number' and positive expectancy means the strategy has edge.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "replace",
                "recommended_action": "Replace the primary Journal tab with a future executable-strategy journal; preserve existing SQLite rows as legacy_signal_telemetry.",
            },
            {
                "tab": "Weights",
                "user_problem": "Tune how many points each component contributes.",
                "data_and_logic": "User-editable Intraday/Short/Long weights persisted to ~/.tradex/weights.json.",
                "classification": "settings_infrastructure",
                "supporting_disposition": "Weights are unvalidated and can be post-hoc tuned on uncontrolled observations.",
                "current_overstatement": "Presentation as a tuning UI implies the user can improve the score without research control.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "archive",
                "recommended_action": "Remove from normal user workflow; future strategy parameters must be versioned and research-controlled.",
            },
            {
                "tab": "Help",
                "user_problem": "How do I use TradeX?",
                "data_and_logic": "In-app markdown documentation.",
                "classification": "settings_infrastructure",
                "supporting_disposition": "Currently recommends Pattern Match and Signal Journal as if they are validated workflows.",
                "current_overstatement": "Quick-start still lists Pattern Match as a recommended step.",
                "actionable": False,
                "outcome_measurement_valid": False,
                "recommended_disposition": "keep_but_relabel",
                "recommended_action": "Retain but rewrite inaccurate or overstated explanations; make evidence-state and research-status explicit.",
            },
        ],
        "strategy_evidence_inventory": [
            {
                "component": "Production intraday scorer",
                "evidence_state": "legacy_heuristic",
                "may_rank_candidates": True,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Additive 0-100 indicator; no validated executable edge.",
            },
            {
                "component": "Production short-term scorer",
                "evidence_state": "legacy_heuristic",
                "may_rank_candidates": True,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "VAL-002 did not authorize production changes; SHORT-001 is not supported.",
            },
            {
                "component": "Production long-term scorer",
                "evidence_state": "legacy_heuristic",
                "may_rank_candidates": True,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "LONG-001 was inconclusive.",
            },
            {
                "component": "Coil detector",
                "evidence_state": "exploratory",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Heuristic persistence metric; move to Research Lab.",
            },
            {
                "component": "Confluence",
                "evidence_state": "exploratory",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Coverage-aware aggregation of unvalidated scores; context only.",
            },
            {
                "component": "Premarket gaps",
                "evidence_state": "exploratory",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Event detector; not an approved strategy.",
            },
            {
                "component": "Options activity",
                "evidence_state": "exploratory",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Archive from primary workflow unless separately approved.",
            },
            {
                "component": "Pattern similarity / PATTERN-001",
                "evidence_state": "rejected",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Rejected on holdout; quarantined from production.",
            },
            {
                "component": "SHORT-001",
                "evidence_state": "not_supported",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "No candidate policy passed development/validation; context not promoted.",
            },
            {
                "component": "LONG-001",
                "evidence_state": "inconclusive",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Production long-term score vs 40-week MA baseline; no promotion.",
            },
            {
                "component": "INTRA-001",
                "evidence_state": "inconclusive",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Real-data study inconclusive; holdout not parsed.",
            },
            {
                "component": "VAL-002",
                "evidence_state": "inconclusive",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Score validation study complete; did not force a production change recommendation.",
            },
            {
                "component": "LONG-002",
                "evidence_state": "research_only",
                "may_rank_candidates": False,
                "may_use_actionable_labels": False,
                "may_generate_automatic_alerts": False,
                "notes": "Rapid-upside research program; design PR authorized, dataset construction and production promotion unauthorized; currently paused for MVP architecture work.",
            },
        ],
        "candidate_contract": {
            "purpose": "Keep distinct concepts separate before any candidate can be shown as Enter Now / Armed / Waitlist.",
            "fields": [
                "strategy_id",
                "strategy_version",
                "symbol",
                "security_identity_version",
                "decision_timestamp",
                "candidate_state",
                "setup_quality_score",
                "move_potential",
                "entry_readiness",
                "downside_risk",
                "data_confidence",
                "evidence_state",
                "human_readable_reasons",
                "missing_or_unknown_inputs",
                "provider_provenance",
                "entry_plan",
                "invalidation_stop",
                "target_or_expiration",
            ],
            "rules": [
                "A single 0-100 score is not probability, cross-strategy comparability, evidence strength, or actionability.",
                "setup_quality, move_potential, entry_readiness, downside/risk, and data_confidence are separate fields.",
                "missing_or_unknown_inputs are explicit and cannot be backfilled with current or later data.",
            ],
        },
        "journal_outcome_contract": {
            "current_state": "legacy_signal_telemetry",
            "why_current_invalid_for_strategy_proof": [
                "Uses signal close as reference, not the next executable entry fill.",
                "Measures later closes at generic 1/3/5-session horizons, not strategy-specific stop/target/expiration.",
                "Does not evaluate invalidation, stop, target, or expiration consistently.",
                "Expectancy formula is signal telemetry, not executable strategy expectancy.",
                "Encourages post-hoc threshold adjustment from uncontrolled observations.",
            ],
            "future_contract_fields": [
                "strategy_id_and_version",
                "candidate_id",
                "planned_entry",
                "realized_fill",
                "stop_price",
                "target_price",
                "expiration",
                "invalidation_rule",
                "exit_reason",
                "exit_fill",
                "slippage_and_costs",
                "net_return",
                "strategy_drawdown",
                "provider_provenance",
                "outcome_confidence",
            ],
            "notes": "Existing SQLite rows must be preserved and labeled legacy_signal_telemetry. No data migration in this PR.",
        },
        "target_navigation": [
            {
                "area": "Today",
                "purpose": "Enter Now, Armed, and Waitlist candidates with context badges.",
                "contains": ["ranked candidate list", "premarket context", "earnings context", "data confidence badges"],
            },
            {
                "area": "Candidate Detail",
                "purpose": "Deep-dive on one candidate.",
                "contains": ["setup", "readiness", "risk", "invalidation", "evidence", "missing data", "chart", "provenance"],
            },
            {
                "area": "Journal",
                "purpose": "Planned decisions and executable strategy outcomes.",
                "contains": ["planned trades", "fills", "stops", "targets", "strategy-specific results"],
            },
            {
                "area": "Research Lab",
                "purpose": "Experimental, rejected, inconclusive, shadow, and archived systems.",
                "contains": ["Pattern Similarity", "Coil context", "score validation", "LONG-001/SHORT-001/INTRA-001/LONG-002 artifacts", "parameter studies"],
            },
            {
                "area": "Settings",
                "purpose": "Providers, watchlists, alert delivery, diagnostics, read-only strategy config.",
                "contains": ["provider lifecycle", "alert channels", "watchlists", "diagnostics", "read-only strategy versions"],
            },
        ],
        "alert_boundary": [
            "Only separately approved actionable strategies may generate automatic actionable alerts.",
            "Research, rejected, inconclusive, archived, and legacy heuristic outputs cannot generate actionable alerts.",
            "Shadow strategies may record telemetry but may not send normal actionable alerts.",
            "Context and event detectors may be attached to an approved candidate but cannot independently imply a trade.",
            "Provider degradation or unknown mandatory data must prevent unsupported actionability.",
        ],
        "prospective_capture_recommendation": [
            "Capture earnings schedules as known at 8:30 p.m. and 9:00 a.m. America/New_York decision timestamps.",
            "Capture security classification and reference facts at decision timestamps.",
            "Record provider and request provenance for every candidate observation.",
            "Record missing/unknown status explicitly rather than leaving it implicit.",
        ],
        "rollout_plan": [
            {
                "order": 1,
                "pr": "Truthful UI/help labeling and evidence badges",
                "objective": "Add evidence-state badges to all existing tabs and rewrite Help to stop recommending rejected/inconclusive features.",
                "production_trading_impact": "None; labels only.",
                "requires_gary_approval": True,
                "dependencies": ["MVP-ARCH-001 approval"],
                "rollback": "Revert label/markdown changes; no data migration.",
            },
            {
                "order": 2,
                "pr": "Provider lifecycle/configuration simplification",
                "objective": "Make Schwab primary, Alpaca/Yahoo fallback roles explicit, archive IBKR default, and make unknown earnings fail visibly.",
                "production_trading_impact": "Could change default provider selection; no signal logic changes.",
                "requires_gary_approval": True,
                "dependencies": ["Step 1"],
                "rollback": "Restore previous defaults via .env or settings.",
            },
            {
                "order": 3,
                "pr": "Navigation consolidation",
                "objective": "Move Coil Detector, Pattern Similarity, and Options Activity to Research Lab; reorganize Settings.",
                "production_trading_impact": "None; UI navigation only.",
                "requires_gary_approval": True,
                "dependencies": ["Step 1"],
                "rollback": "Restore previous tab list in dashboard.py.",
            },
            {
                "order": 4,
                "pr": "Alert gating",
                "objective": "Gate automatic actionable alerts on approved strategy evidence-state; keep delivery infrastructure.",
                "production_trading_impact": "Reduces false alerts; requires approved strategy list.",
                "requires_gary_approval": True,
                "dependencies": ["Step 3"],
                "rollback": "Disable gating or restore previous alert threshold check.",
            },
            {
                "order": 5,
                "pr": "Candidate persistence contract",
                "objective": "Introduce candidate table/schema that stores the candidate contract fields.",
                "production_trading_impact": "Adds schema; no changes to existing signal_history.",
                "requires_gary_approval": True,
                "dependencies": ["Step 2"],
                "rollback": "Drop new table; existing tables untouched.",
            },
            {
                "order": 6,
                "pr": "Journal/outcome replacement",
                "objective": "Add executable strategy journal; keep legacy signal_history rows labeled legacy_signal_telemetry.",
                "production_trading_impact": "Replaces Signal Journal primary UI; does not delete data.",
                "requires_gary_approval": True,
                "dependencies": ["Step 5"],
                "rollback": "Restore Signal Journal tab; new journal table remains empty.",
            },
            {
                "order": 7,
                "pr": "Prospective PIT data capture",
                "objective": "Schedule lightweight capture of earnings, classification, and provider provenance at decision timestamps.",
                "production_trading_impact": "None until used by an approved strategy.",
                "requires_gary_approval": True,
                "dependencies": ["Step 2"],
                "rollback": "Disable capture job.",
            },
            {
                "order": 8,
                "pr": "Later resumption of LONG-002C design",
                "objective": "Resume LONG-002C design PR only after MVP architecture and candidate/journal contracts are approved.",
                "production_trading_impact": "None until a separate production PR is approved.",
                "requires_gary_approval": True,
                "dependencies": ["Step 5", "Step 6"],
                "rollback": "Continue pausing LONG-002C; no dataset built.",
            },
        ],
        "material_discrepancies_found": [
            "README.md LONG-002 'Current phase' still names LONG-002B-AMEND-001 even though LONG-002B-AMEND-002 is merged; this should be synchronized.",
            "Help tab quick-start recommends Pattern Match as step 3, but PATTERN-001 was rejected and pattern similarity is research-only.",
            "Signal Journal help text presents expectancy as proof of strategy edge, but the underlying outcome windows are generic 1/3/5-session signal telemetry.",
            "Coil Detector help text uses 'before the crowd sees them' and 'bigger potential release' language that implies a validated edge.",
            "Confluence tab caption calls the weighted score 'much higher conviction' though it is an aggregation of unvalidated heuristics.",
            "Options Activity tab label implies actionability, but no options source is configured by default and no strategy uses the output.",
            "Weights tab allows user tuning of component points persisted to ~/.tradex/weights.json without research versioning or validation.",
            "PROJECT-TRACKER current phase is LONG-002B-AMEND-002 and does not yet reflect Gary's pause for MVP architecture work.",
        ],
        "governance_invariants": [
            "No implementation, provider call, dashboard change, alert change, database migration, or production signal change occurs in this PR.",
            "No existing strategy is relabeled production_approved.",
            "LONG-002C design was authorized by PR #52 but is explicitly paused while MVP architecture work is completed.",
            "LONG-002C dataset construction remains unauthorized.",
            "Production promotion remains unauthorized.",
            "Final consolidation decisions remain pending Gary approval.",
            "Existing research artifacts and locked specifications are referenced, not modified.",
        ],
    }


def to_markdown(inv: dict[str, Any]) -> str:
    """Render the MVP-ARCH-001 inventory as a concise human-readable decision packet."""
    lines: list[str] = [
        "# MVP-ARCH-001: TradeX provider, strategy, and dashboard consolidation plan",
        "",
        f"**Artifact:** `{inv['artifact_id']}`",
        f"**Classification:** `{inv['classification']}`",
        f"**Decision status:** `{inv['decision_status']}`",
        f"**Starting `main` SHA:** `{inv['starting_main_sha']}`",
        f"**Prerequisite commit:** `{inv['prerequisite_commit']}` (merged PR #52)",
        "",
        "## Authorization boundary",
        "",
    ]
    for key, value in inv["authorization"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** `{value}`")

    ps = inv["product_summary"]
    lines.extend([
        "",
        "## Product diagnosis",
        "",
        ps["diagnosis"],
        "",
        "### Primary daily job",
        "",
        ps["primary_daily_job"],
        "",
        "### What Gary sees first",
        "",
        ps["first_screen"],
        "",
        "## Required product questions",
        "",
    ])
    for item in inv["product_questions"]:
        lines.append(f"1. **{item['question']}** {item['answer']}")

    lines.extend(["", "## Provider inventory", ""])
    for p in inv["provider_inventory"]:
        lines.append(f"### {p['name']}")
        lines.append(f"- **Roles:** {', '.join(p['roles'])}")
        lines.append(f"- **Production/runtime:** {'yes' if p['production_runtime'] else 'no'}")
        lines.append(f"- **Research use:** {'yes' if p['research_use'] else 'no'}")
        lines.append(f"- **Credential/operational burden:** {p['credential_burden']}")
        lines.append(f"- **Limitations:** {p['delay_feed_entitlement']}; {p['pit_reliability']}")
        lines.append(f"- **Fallback behavior:** {p['fallback_behavior']}")
        lines.append(f"- **Mix within scan/outcome:** {p['mix_in_scan_or_outcome']}")
        lines.append(f"- **Recommended lifecycle:** `{p['recommended_lifecycle']}`")
        lines.append(f"- **Recommended role:** {p['recommended_role']}")

    pr = inv["provider_recommendation"]
    lines.extend([
        "",
        "## Provider recommendation",
        "",
        f"**Target principle:** {pr['target_principle']}",
        f"**Notes:** {pr['notes']}",
        "",
    ])
    for capability, mapping in pr["mapping"].items():
        if "primary" in mapping:
            primary = mapping.get("primary", "")
            fallback = mapping.get("fallback", "")
            status = mapping.get("status", "")
            note = mapping.get("note", "")
            if primary:
                lines.append(f"- **{capability}:** primary `{primary}`")
                if fallback:
                    lines.append(f"  - fallback: {fallback}")
            elif status:
                lines.append(f"- **{capability}:** {status}")
            if note:
                lines.append(f"  - {note}")

    lines.extend(["", "## Dashboard inventory and recommendation", ""])
    for d in inv["dashboard_inventory"]:
        lines.append(f"### {d['tab']}")
        lines.append(f"- **User problem:** {d['user_problem']}")
        lines.append(f"- **Classification:** {d['classification']}")
        lines.append(f"- **Supporting research disposition:** {d['supporting_disposition']}")
        lines.append(f"- **Current overstatement:** {d['current_overstatement']}")
        lines.append(f"- **Actionable today:** {d['actionable']}")
        lines.append(f"- **Outcome measurement valid:** {d['outcome_measurement_valid']}")
        lines.append(f"- **Recommended disposition:** `{d['recommended_disposition']}`")
        lines.append(f"- **Recommended action:** {d['recommended_action']}")

    lines.extend(["", "## Strategy and evidence inventory", ""])
    lines.append("| Component | Evidence state | May rank | Actionable labels | Auto alerts | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for s in inv["strategy_evidence_inventory"]:
        lines.append(
            f"| {s['component']} | `{s['evidence_state']}` | {s['may_rank_candidates']} | "
            f"{s['may_use_actionable_labels']} | {s['may_generate_automatic_alerts']} | {s['notes']} |"
        )

    cc = inv["candidate_contract"]
    lines.extend([
        "",
        "## Candidate contract design",
        "",
        f"**Purpose:** {cc['purpose']}",
        "",
        "**Required fields:**",
        "",
    ])
    for field in cc["fields"]:
        lines.append(f"- `{field}`")
    lines.extend(["", "**Rules:**", ""])
    for rule in cc["rules"]:
        lines.append(f"- {rule}")

    jo = inv["journal_outcome_contract"]
    lines.extend([
        "",
        "## Journal and outcome contract",
        "",
        f"**Current state:** `{jo['current_state']}`",
        "",
        "**Why the current Signal Journal cannot prove an edge:**",
        "",
    ])
    for reason in jo["why_current_invalid_for_strategy_proof"]:
        lines.append(f"- {reason}")
    lines.extend(["", "**Future contract fields:**", ""])
    for field in jo["future_contract_fields"]:
        lines.append(f"- `{field}`")
    lines.append(f"\n**Notes:** {jo['notes']}")

    lines.extend(["", "## Target product workflow", ""])
    for area in inv["target_navigation"]:
        lines.append(f"### {area['area']}")
        lines.append(f"- **Purpose:** {area['purpose']}")
        lines.append(f"- **Contains:** {', '.join(area['contains'])}")

    lines.extend(["", "## Alert boundary", ""])
    for rule in inv["alert_boundary"]:
        lines.append(f"- {rule}")

    lines.extend(["", "## Prospective data capture recommendation", ""])
    for item in inv["prospective_capture_recommendation"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Rollout plan", ""])
    for step in inv["rollout_plan"]:
        lines.append(f"### {step['order']}. {step['pr']}")
        lines.append(f"- **Objective:** {step['objective']}")
        lines.append(f"- **Production/trading impact:** {step['production_trading_impact']}")
        lines.append(f"- **Requires Gary approval:** {step['requires_gary_approval']}")
        lines.append(f"- **Dependencies:** {', '.join(step['dependencies'])}")
        lines.append(f"- **Rollback:** {step['rollback']}")

    lines.extend(["", "## Material discrepancies found", ""])
    for d in inv["material_discrepancies_found"]:
        lines.append(f"- {d}")

    lines.extend(["", "## Governance invariants", ""])
    for g in inv["governance_invariants"]:
        lines.append(f"- {g}")

    lines.extend([
        "",
        "---",
        "",
        "*This packet is a versioned product-architecture decision document. It does not implement any consolidation, provider change, dashboard change, alert change, database migration, or production behavior change.*",
    ])
    return "\n".join(lines)


def write_inventory(inv: dict[str, Any], repo_root: Path | str) -> tuple[Path, Path]:
    """Write JSON and markdown artifacts deterministically."""
    root = Path(repo_root)
    md_path = root / "docs" / "product" / "MVP-ARCH-001.md"
    json_path = root / "docs" / "product" / "MVP-ARCH-001.json"
    json_path.write_text(json.dumps(inv, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(inv) + "\n", encoding="utf-8")
    return md_path, json_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate MVP-ARCH-001 consolidation decision packet")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root")
    args = parser.parse_args(argv)

    inv = build_inventory()
    md_path, json_path = write_inventory(inv, args.repo_root)
    print("MVP-ARCH-001 written to:")
    print(f"  {md_path}")
    print(f"  {json_path}")
    print(f"Decision status: {inv['decision_status']}")


if __name__ == "__main__":
    main()
