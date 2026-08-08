"""Command-line interface for the INTRA-001B one-year dataset build."""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .dataset import (
    run_build_universe,
    run_fetch_ohlcv,
    run_fetch_reference,
    run_finalize,
    run_plan,
    run_validate,
)
from .spec import load_dataset_plan

REPO_ROOT = Path(__file__).resolve().parents[3]


def _current_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _current_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _resolve_commit(ref: str) -> str:
    if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
        return ref
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        raise ValueError(f"Could not resolve commit {ref!r}")


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    try:
        subprocess.check_output(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _massive_key() -> str:
    return os.environ.get("MASSIVE_API_KEY", "")


def _alpaca_keys() -> tuple[str, str]:
    return os.environ.get("ALPACA_API_KEY", ""), os.environ.get("ALPACA_SECRET_KEY", "")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", required=True, help="Path to INTRA-001B-dataset-v1.json")
    parser.add_argument("--output-dir", required=True, help="Private local dataset root")
    parser.add_argument("--starting-main-sha", default="", help="Approved starting main SHA")
    parser.add_argument("--pre-registration-commit", default="", help="Pre-registration commit SHA")


def _cmd_plan(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    run_plan(plan, Path(args.output_dir), pre_registration_commit=args.pre_registration_commit)
    print(json.dumps({"estimated_resources": plan.estimated_resources}, indent=2))
    return 0


def _cmd_fetch_reference(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    key = _massive_key()
    if not key:
        print("MASSIVE_API_KEY not configured", file=sys.stderr)
        return 1
    run_fetch_reference(plan, Path(args.output_dir), key)
    return 0


def _cmd_build_universe(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    api_key, secret_key = _alpaca_keys()
    if not api_key or not secret_key:
        print("ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured", file=sys.stderr)
        return 1
    run_build_universe(plan, Path(args.output_dir), api_key, secret_key)
    return 0


def _cmd_fetch_ohlcv(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    api_key, secret_key = _alpaca_keys()
    if not api_key or not secret_key:
        print("ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured", file=sys.stderr)
        return 1
    run_fetch_ohlcv(plan, Path(args.output_dir), api_key, secret_key)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    summary = run_validate(plan, Path(args.output_dir))
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    plan, _ = load_dataset_plan(args.spec)
    pre_reg = args.pre_registration_commit or _current_head()
    head = _current_head()
    pre_reg_full = _resolve_commit(pre_reg)
    if not _is_ancestor(pre_reg_full, head):
        print(
            f"Pre-registration commit {pre_reg_full} is not an ancestor of current head {head}",
            file=sys.stderr,
        )
        return 1
    t0 = time.time()
    decision = run_finalize(
        plan,
        Path(args.output_dir),
        Path(args.artifact_dir),
        starting_main_sha=args.starting_main_sha or head,
        branch=_current_branch(),
        live_run_head=head,
        pre_registration_commit=pre_reg_full,
        runtime_seconds=time.time() - t0,
    )
    print(json.dumps({"disposition": decision.disposition, "artifact_path": str(Path(args.artifact_dir))}, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tradex.research.intraday_dataset")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="Validate and lock the dataset plan")
    _add_common(p)
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("fetch-reference", help="Fetch Massive reference snapshots")
    _add_common(p)
    p.set_defaults(func=_cmd_fetch_reference)

    p = sub.add_parser("build-universe", help="Build monthly PIT universes")
    _add_common(p)
    p.set_defaults(func=_cmd_build_universe)

    p = sub.add_parser("fetch-ohlcv", help="Fetch Alpaca SIP 5Min OHLCV")
    _add_common(p)
    p.set_defaults(func=_cmd_fetch_ohlcv)

    p = sub.add_parser("validate", help="Validate data quality")
    _add_common(p)
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("finalize", help="Generate safe artifact bundle")
    _add_common(p)
    p.add_argument("--artifact-dir", required=True, help="Repository-relative safe artifact directory")
    p.set_defaults(func=_cmd_finalize)

    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
