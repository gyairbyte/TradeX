"""Command-line interface for the INTRA-001B-REFERENCE-V3 probe."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from tradex.config import load_runtime_settings

from .probe import run_reference_probe
from .report import write_reference_probe_artifacts
from .spec import load_probe_spec, sha256_of_file


def main() -> int:
    parser = argparse.ArgumentParser(description="INTRA-001B-REFERENCE-V3 reference provider probe")
    parser.add_argument("--spec", default="docs/research/specs/INTRA-001B-reference-probe-v3.json")
    parser.add_argument("--v1-pre-registration-commit", required=True)
    parser.add_argument("--v2-pre-registration-commit", required=True)
    parser.add_argument("--v3-pre-registration-commit", required=True)
    parser.add_argument("--starting-main-sha", required=True)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--final-head", default=None)
    parser.add_argument("--only-provider", choices=["alpha_vantage", "massive"], default=None)
    parser.add_argument(
        "--output-dir",
        default="docs/research/artifacts/INTRA-001B-REFERENCE-V3",
    )
    parser.add_argument(
        "--private-output-dir",
        default=os.environ.get(
            "TRADEX_RESEARCH_DATA_DIR",
            str(Path.home() / ".tradex" / "research"),
        ) + "/INTRA-001B/reference-provider-probe-v3",
    )
    args = parser.parse_args()

    spec, raw_spec = load_probe_spec(args.spec)
    probe_spec_sha256 = sha256_of_file(args.spec)

    # Also persist raw spec to private dir for audit but not safe bundle.
    private_dir = Path(args.private_output_dir).expanduser().resolve()
    private_dir.mkdir(parents=True, exist_ok=True)
    private_spec = private_dir / "probe_spec.lock.json"
    private_spec.write_bytes(raw_spec)

    settings = load_runtime_settings()

    result, decision = run_reference_probe(
        spec,
        settings,
        v1_pre_registration_commit=args.v1_pre_registration_commit,
        v2_pre_registration_commit=args.v2_pre_registration_commit,
        v3_pre_registration_commit=args.v3_pre_registration_commit,
        probe_spec_sha256=probe_spec_sha256,
        starting_main_sha=args.starting_main_sha,
        branch=args.branch,
        final_head=args.final_head,
        only_provider=args.only_provider,
    )

    output_dir = Path(args.output_dir)
    run_id = decision.ran_at[:19].replace("T", "-").replace(":", "")
    bundle_dir = output_dir / run_id
    write_reference_probe_artifacts(
        spec,
        decision,
        result,
        bundle_dir,
        probe_spec_raw=raw_spec,
    )

    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    print(f"Artifacts written to: {bundle_dir}")
    return 0
