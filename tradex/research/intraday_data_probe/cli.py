"""Command-line interface for the INTRA-001B Schwab five-minute probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .probe import run_probe
from .report import write_probe_artifacts, write_probe_report
from .spec import load_probe_spec


def _schwab_py_version() -> str:
    try:
        import schwab
        return getattr(schwab, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def _strategy_spec_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pre_registration_commit() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _add_run_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[name-defined]
    parser = subparsers.add_parser("run", help="Execute the locked Schwab five-minute probe")
    parser.add_argument("--spec", required=True, help="Path to the locked probe spec JSON")
    parser.add_argument("--strategy-spec", required=True, help="Path to the locked INTRA-001 strategy spec JSON")
    parser.add_argument("--output-dir", required=True, help="Private output directory for full probe artifacts")
    parser.add_argument("--artifact-dir", default=None, help="Directory for the safe aggregate artifact bundle (inside repo)")
    parser.add_argument("--report-path", default="docs/research/INTRA-001B-SCHWAB-DATA-PROBE.md", help="Path to the human-readable probe report")
    parser.add_argument("--pre-registration-commit", default=None, help="SHA of the pre-registration commit")
    parser.set_defaults(func=_cmd_run)


def _cmd_run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).expanduser().resolve()
    strategy_spec_path = Path(args.strategy_spec).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    spec, spec_bytes = load_probe_spec(spec_path)
    strategy_spec_sha = _strategy_spec_sha256(strategy_spec_path)
    probe_spec_sha = hashlib.sha256(spec_bytes).hexdigest()
    pre_reg_commit = args.pre_registration_commit or _pre_registration_commit()

    report = run_probe(
        spec=spec,
        strategy_spec_sha256=strategy_spec_sha,
        probe_spec_sha256=probe_spec_sha,
        output_dir=output_dir,
        pre_registration_commit=pre_reg_commit,
        schwab_py_version=_schwab_py_version(),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")

    if args.artifact_dir:
        artifact_dir = Path(args.artifact_dir).expanduser().resolve()
        write_probe_artifacts(
            report=report,
            spec=spec,
            probe_spec_bytes=spec_bytes,
            strategy_spec_path=strategy_spec_path,
            output_dir=output_dir,
            artifact_dir=artifact_dir,
            pre_registration_commit=pre_reg_commit,
        )

    if args.report_path:
        write_probe_report(report, spec, probe_spec_sha, strategy_spec_sha, pre_reg_commit, Path(args.report_path))

    print(json.dumps(report.decision.to_dict(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tradex.research.intraday_data_probe")
    subparsers = parser.add_subparsers(dest="command")
    _add_run_parser(subparsers)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
