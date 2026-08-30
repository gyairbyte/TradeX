"""One-shot command-line interface for point-in-time capture (MVP-ARCH-001-R7-PIT-001A).

Provides deterministic one-shot execution for capturing prospective point-in-time
earnings observations at canonical observation slots.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.massive_reference import sanitize_text
from tradex.pit.models import CaptureRunStatus, CaptureSlot
from tradex.pit.reference import capture_reference_snapshot
from tradex.pit.store import PITIdempotencyConflictError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradex.pit.capture",
        description="One-shot CLI for point-in-time prospective data capture.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    earnings_parser = subparsers.add_parser(
        "earnings",
        help="Capture prospective point-in-time earnings observations.",
    )
    earnings_parser.add_argument(
        "--slot",
        type=str,
        required=True,
        choices=["evening", "morning"],
        help="Observation slot ('evening' for 20:30 ET, 'morning' for 09:00 ET).",
    )
    earnings_parser.add_argument(
        "--symbols",
        type=str,
        required=True,
        help="Comma-separated list of symbols (e.g. AAPL,MSFT,NVDA).",
    )
    earnings_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Earnings provider source (defaults to configured source, e.g. 'yahoo').",
    )
    earnings_parser.add_argument(
        "--idempotency-key",
        type=str,
        default=None,
        help="Explicit idempotency key for this capture execution.",
    )
    earnings_parser.add_argument(
        "--capture-date",
        type=str,
        default=None,
        help="Optional ISO calendar date (YYYY-MM-DD); must match current ET date.",
    )
    earnings_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional path to signals.db SQLite database.",
    )

    ref_parser = subparsers.add_parser(
        "reference",
        help="Capture prospective point-in-time security/reference observations.",
    )
    ref_parser.add_argument(
        "--slot",
        type=str,
        required=True,
        choices=["evening", "morning"],
        help="Observation slot ('evening' for 20:30 ET, 'morning' for 09:00 ET).",
    )
    ref_parser.add_argument(
        "--symbols",
        type=str,
        required=True,
        help="Comma-separated list of symbols (e.g. AAPL,MSFT,NVDA).",
    )
    ref_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Reference provider source (defaults to 'massive').",
    )
    ref_parser.add_argument(
        "--idempotency-key",
        type=str,
        default=None,
        help="Explicit idempotency key for this capture execution.",
    )
    ref_parser.add_argument(
        "--capture-date",
        type=str,
        default=None,
        help="Optional ISO calendar date (YYYY-MM-DD); must match current ET date.",
    )
    ref_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional path to signals.db SQLite database.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "earnings":
        slot = CaptureSlot(args.slot)
        raw_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        if not raw_symbols:
            sys.stderr.write("Error: --symbols must contain at least one valid symbol.\n")
            return 1

        cap_date: date | None = None
        if args.capture_date:
            try:
                cap_date = date.fromisoformat(args.capture_date.strip())
            except ValueError:
                sys.stderr.write(
                    f"Error: Invalid --capture-date format '{args.capture_date}'; use YYYY-MM-DD.\n"
                )
                return 1

        try:
            result = capture_earnings_snapshot(
                symbols=raw_symbols,
                slot=slot,
                capture_date=cap_date,
                source=args.source,
                idempotency_key=args.idempotency_key,
                db_path=args.db_path,
            )
        except (ValueError, TypeError, PITIdempotencyConflictError) as exc:
            clean_err = sanitize_text(str(exc))
            sys.stderr.write(f"Capture error: {clean_err}\n")
            return 1
        except Exception:  # noqa: BLE001
            sys.stderr.write("Capture failed due to an unexpected internal error.\n")
            return 1

        run = result.run
        sys.stdout.write(
            f"Capture Run ID:       {run.capture_run_id}\n"
            f"Contract Version:     {run.contract_version}\n"
            f"Slot:                 {run.capture_slot.value}\n"
            f"Capture Date:         {run.capture_date.isoformat()}\n"
            f"Scheduled For:        {run.scheduled_for.isoformat()}\n"
            f"Requested At:         {run.requested_at.isoformat()}\n"
            f"Provider:             {run.requested_provider}\n"
            f"Requested Count:      {run.requested_n}\n"
            f"Known Count:          {run.known_n}\n"
            f"Unavailable Count:    {run.unavailable_n}\n"
            f"Error Count:          {run.error_n}\n"
            f"Status:               {run.status.value}\n"
        )

        if run.status == CaptureRunStatus.SUCCEEDED:
            return 0
        if run.status == CaptureRunStatus.PARTIAL:
            return 2
        return 1

    if args.subcommand == "reference":
        slot = CaptureSlot(args.slot)
        raw_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        if not raw_symbols:
            sys.stderr.write("Error: --symbols must contain at least one valid symbol.\n")
            return 1

        cap_date = None
        if args.capture_date:
            try:
                cap_date = date.fromisoformat(args.capture_date.strip())
            except ValueError:
                sys.stderr.write(
                    f"Error: Invalid --capture-date format '{args.capture_date}'; use YYYY-MM-DD.\n"
                )
                return 1

        try:
            ref_result = capture_reference_snapshot(
                symbols=raw_symbols,
                slot=slot,
                capture_date=cap_date,
                source=args.source,
                idempotency_key=args.idempotency_key,
                db_path=args.db_path,
            )
        except (ValueError, TypeError, PITIdempotencyConflictError) as exc:
            clean_err = sanitize_text(str(exc))
            sys.stderr.write(f"Capture error: {clean_err}\n")
            return 1
        except Exception:  # noqa: BLE001
            sys.stderr.write("Capture failed due to an unexpected internal error.\n")
            return 1

        ref_run = ref_result.run
        sys.stdout.write(
            f"Capture Run ID:       {ref_run.capture_run_id}\n"
            f"Contract Version:     {ref_run.contract_version}\n"
            f"Slot:                 {ref_run.capture_slot.value}\n"
            f"Capture Date:         {ref_run.capture_date.isoformat()}\n"
            f"Scheduled For:        {ref_run.scheduled_for.isoformat()}\n"
            f"Requested At:         {ref_run.requested_at.isoformat()}\n"
            f"Provider:             {ref_run.requested_provider}\n"
            f"Requested Count:      {ref_run.requested_n}\n"
            f"Known Count:          {ref_run.known_n}\n"
            f"Unavailable Count:    {ref_run.unavailable_n}\n"
            f"Ambiguous Count:      {ref_run.ambiguous_n}\n"
            f"Error Count:          {ref_run.error_n}\n"
            f"Status:               {ref_run.status.value}\n"
        )

        if ref_run.status == CaptureRunStatus.SUCCEEDED:
            return 0
        if ref_run.status == CaptureRunStatus.PARTIAL:
            return 2
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
