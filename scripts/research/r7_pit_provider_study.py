"""
Research script for MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001.
Measures Yahoo and Massive compatibility on frozen PIT candidates.
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yfinance

from tradex.config import load_runtime_settings
from tradex.earnings.calendar import (
    EarningsDataUnavailableError,
    EarningsProviderLookupError,
    EarningsProviderResponseError,
    _fetch_from_yahoo,
)
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.massive_reference import MassiveReferenceClient
from tradex.pit.ops import load_universe_manifest

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-c2-readiness-a"
CANDIDATE_B_JSON = ARTIFACTS_DIR / "candidate-dow30.json"
CANDIDATE_C_JSON = ARTIFACTS_DIR / "candidate-dow30-sector-etfs.json"

STUDY_ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-provider-study-001"
STUDY_SPEC_JSON = STUDY_ARTIFACTS_DIR / "study_spec.json"
RESULTS_JSON = STUDY_ARTIFACTS_DIR / "results.json"


def get_git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def write_study_spec() -> None:
    """Writes the predefined machine-readable study specification."""
    logger.info("Writing study specification to %s", STUDY_SPEC_JSON)
    STUDY_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    spec = {
        "task_id": "MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001",
        "authorization_record": {
            "authorized_by": "Gary Yang",
            "authorized_on": "2026-09-10",
            "authorization_scope": "bounded_live_provider_compatibility_study_only",
            "authorization_source": "Gary replied 'continue' immediately after ChatGPT stated that the next prerequisite was the bounded live-provider compatibility study and that it required separate authorization."
        },
        "starting_main_sha": "d86f0b6322e13e6801e06fd5b8eda6cf57a1faca",
        "candidate_b": {
            "universe_id": "candidate-dow30",
            "universe_version": "2026-09-08-v1",
            "universe_hash": "173411d5854450294821e4dedbe5147278ccf248d8a21fc1973d81a41b9465b4"
        },
        "candidate_c": {
            "universe_id": "candidate-dow30-sector-etfs",
            "universe_version": "2026-09-08-v1",
            "universe_hash": "83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29"
        },
        "study_population": "Exact union of Candidate C (45 symbols). ETF vs equity classification is deterministic based on Candidate B membership.",
        "classification_rules": {
            "yahoo": {
                "date_returned": "KNOWN",
                "EarningsDataUnavailableError": "CLEAN_NO_USABLE_UPCOMING_DATE",
                "EarningsProviderResponseError": "RESPONSE_ERROR",
                "EarningsProviderLookupError": "TECHNICAL_ERROR"
            },
            "massive": "Preserve ReferenceObservationStatus exactly (KNOWN, UNAVAILABLE, AMBIGUOUS, ERROR)"
        },
        "provider_methods": {
            "yahoo": "tradex.earnings.calendar._fetch_from_yahoo(symbol)",
            "massive": "tradex.pit.massive_reference.MassiveReferenceClient.fetch_ticker_reference(symbol, capture_date)"
        },
        "pacing_rule": "Production massive pacing interval (~12.1 seconds). No concurrency.",
        "abort_rules": "Abort on missing credential, global auth/entitlement/rate-limit failures, local date mismatch with MARKET_TIMEZONE, or market-date rollover.",
        "no_retry_rule": "No study-level retries. One primary pass only.",
        "output_schema": {
            "artifact_schema_version": "integer",
            "task_id": "string",
            "protocol_commit_sha": "string",
            "starting_main_sha": "string",
            "study_started_at_utc": "string",
            "study_ended_at_utc": "string",
            "market_date": "string",
            "timezone": "string",
            "python_version": "string",
            "yfinance_version": "string",
            "provider_adapter_names": ["string"],
            "candidate_b_hash": "string",
            "candidate_c_hash": "string",
            "observations": "array of observation objects",
            "study_disposition": "string"
        },
        "predefined_conclusion_logic": [
            "completed_evidence_sufficient_for_next_decision (no provider technical/response contract errors)",
            "completed_provider_contract_review_required (completed run with any provider technical/response ERROR)",
            "incomplete_environment_or_provider_block (global environment/auth/entitlement/rate-limit/date-boundary abort)"
        ],
        "no_production_behavior": True
    }
    
    with open(STUDY_SPEC_JSON, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="TradeX R7 PIT Provider Compatibility Study")
    parser.add_argument("--execute-live", action="store_true", help="Execute the live provider calls")
    parser.add_argument("--confirm-task-id", type=str, help="Confirm the task ID to execute")
    parser.add_argument("--write-spec-only", action="store_true", help="Write study_spec.json and exit")
    args = parser.parse_args()

    if args.write_spec_only:
        write_study_spec()
        return

    if not args.execute_live or args.confirm_task_id != "MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001":
        logger.info("Live execution requires --execute-live and --confirm-task-id MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001")
        return

    # Check Date
    now_local = datetime.now()  # noqa: DTZ005
    now_ny = datetime.now(MARKET_TIMEZONE)
    if now_local.date() != now_ny.date():
        logger.error("Local system date (%s) != TradeX MARKET_TIMEZONE date (%s). Aborting.", now_local.date(), now_ny.date())
        sys.exit(1)

    study_started_at_utc = datetime.now(UTC)
    market_date = now_ny.date()
    
    logger.info("Loading manifests...")
    manifest_b = load_universe_manifest(CANDIDATE_B_JSON)
    manifest_c = load_universe_manifest(CANDIDATE_C_JSON)

    assert manifest_b.universe_hash == "173411d5854450294821e4dedbe5147278ccf248d8a21fc1973d81a41b9465b4"
    assert manifest_c.universe_hash == "83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29"
    assert len(manifest_b.symbols) == 30
    assert len(manifest_c.symbols) == 45
    
    b_symbols = set(manifest_b.symbols)
    c_symbols = manifest_c.symbols
    
    settings = load_runtime_settings()
    massive_api_key = settings.data.massive_api_key

    results = {
        "artifact_schema_version": 1,
        "task_id": args.confirm_task_id,
        "protocol_commit_sha": get_git_sha(),
        "starting_main_sha": "d86f0b6322e13e6801e06fd5b8eda6cf57a1faca",
        "study_started_at_utc": study_started_at_utc.isoformat(),
        "study_ended_at_utc": None,
        "market_date": market_date.isoformat(),
        "timezone": "America/New_York",
        "python_version": platform.python_version(),
        "yfinance_version": yfinance.__version__,
        "provider_adapter_names": ["tradex.earnings.calendar._fetch_from_yahoo", "tradex.pit.massive_reference.MassiveReferenceClient"],
        "candidate_b_hash": manifest_b.universe_hash,
        "candidate_c_hash": manifest_c.universe_hash,
        "observations": []
    }

    if not massive_api_key:
        logger.error("Massive credential is not configured. Aborting study.")
        results["study_disposition"] = "incomplete_environment_or_provider_block"
        study_ended_at_utc = datetime.now(UTC)
        results["study_ended_at_utc"] = study_ended_at_utc.isoformat()
        STUDY_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        sys.exit(1)

    massive_client = MassiveReferenceClient(settings=settings)

    # Perform one primary prospective pass over Candidate C
    abort_massive = False
    
    for symbol in sorted(c_symbols):
        security_class = "equity" if symbol in b_symbols else "etf"
        
        obs = {
            "symbol": symbol,
            "security_class": security_class,
            "yahoo_outcome": None,
            "yahoo_returned_date": None,
            "yahoo_elapsed_ms": None,
            "massive_observation_status": None,
            "massive_error_category": None,
            "massive_error_message": None,
            "massive_provider_type_code": None,
            "massive_provider_active": None,
            "massive_missing_fields": [],
            "massive_request_ids": [],
            "massive_elapsed_ms": None,
            "massive_attempted": True,
        }
        
        # Yahoo
        y_start = time.monotonic()
        try:
            res = _fetch_from_yahoo(symbol)
            obs["yahoo_outcome"] = "KNOWN"
            obs["yahoo_returned_date"] = res.isoformat()
        except EarningsDataUnavailableError:
            obs["yahoo_outcome"] = "CLEAN_NO_USABLE_UPCOMING_DATE"
        except EarningsProviderResponseError:
            obs["yahoo_outcome"] = "RESPONSE_ERROR"
        except EarningsProviderLookupError:
            obs["yahoo_outcome"] = "TECHNICAL_ERROR"
        except Exception:  # noqa: BLE001
            obs["yahoo_outcome"] = "TECHNICAL_ERROR"
            
        obs["yahoo_elapsed_ms"] = round((time.monotonic() - y_start) * 1000, 2)
        
        # Massive
        if abort_massive:
            obs["massive_attempted"] = False
        else:
            m_start = time.monotonic()
            m_res = massive_client.fetch_ticker_reference(symbol, market_date)
            obs["massive_elapsed_ms"] = round((time.monotonic() - m_start) * 1000, 2)
            obs["massive_observation_status"] = m_res.observation_status.name
            obs["massive_error_category"] = m_res.error_category
            obs["massive_error_message"] = m_res.error_message
            obs["massive_provider_type_code"] = m_res.provider_type_code
            obs["massive_provider_active"] = m_res.provider_active
            obs["massive_missing_fields"] = list(m_res.missing_fields)
            obs["massive_request_ids"] = list(m_res.request_ids)
            
            if m_res.error_category in ("MassiveAuthError", "MassiveEntitlementError", "MassiveRateLimitError"):
                logger.warning("Global massive error %s encountered on %s. Aborting further Massive calls.", m_res.error_category, symbol)
                abort_massive = True

        results["observations"].append(obs)

    study_ended_at_utc = datetime.now(UTC)
    results["study_ended_at_utc"] = study_ended_at_utc.isoformat()

    now_ny_end = datetime.now(MARKET_TIMEZONE)
    if now_ny_end.date() != market_date:
        logger.error("TradeX MARKET_TIMEZONE date rolled over during the experiment.")
        # We record it but it invalidates the run conceptually.
        results["market_date_rollover"] = True

    has_contract_error = any(
        obs["yahoo_outcome"] in ("TECHNICAL_ERROR", "RESPONSE_ERROR") or
        obs["massive_observation_status"] == "ERROR"
        for obs in results["observations"]
    )

    if abort_massive or results.get("market_date_rollover"):
        results["study_disposition"] = "incomplete_environment_or_provider_block"
    elif has_contract_error:
        results["study_disposition"] = "completed_provider_contract_review_required"
    else:
        results["study_disposition"] = "completed_evidence_sufficient_for_next_decision"
        
    STUDY_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info("Live execution complete.")

if __name__ == "__main__":
    main()
