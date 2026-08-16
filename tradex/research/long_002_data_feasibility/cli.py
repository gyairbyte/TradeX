"""CLI entry point for the LONG-002B data-feasibility probe."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .probe import run_probe
from .report import write_safe_artifacts


def _current_commit_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="LONG-002B data-feasibility probe")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root containing docs/research/specs",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Artifact bundle run ID (default timestamp)",
    )
    parser.add_argument(
        "--commit-sha",
        type=str,
        default=None,
        help="Code commit SHA to record in artifacts",
    )
    args = parser.parse_args(argv)

    report = run_probe(args.repo_root)
    commit_sha = args.commit_sha or _current_commit_sha()
    bundle = write_safe_artifacts(report, args.repo_root, run_id=args.run_id, code_commit_sha=commit_sha)
    print(f"LONG-002B bundle written to: {bundle}")
    print(f"Overall disposition: {report.overall_disposition}")
    print(f"Total HTTP requests: {report.total_http_requests}")


if __name__ == "__main__":
    main()
