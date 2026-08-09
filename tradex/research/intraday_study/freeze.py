"""Record evaluation-code freeze state before validation/holdout."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class FreezeError(Exception):
    """Raised when the evaluation code cannot be frozen or verified."""


@dataclass(frozen=True)
class FreezeRecord:
    """Immutable record of the evaluation code used for a study."""

    evaluation_code_sha: str
    repository_clean: bool
    frozen_at: datetime
    spec_sha256: str
    amendment_sha256: str | None
    dataset_plan_sha256: str | None
    tracked_files: list[str]


def _git(*args: str, cwd: Path | None = None) -> str:
    cmd = ["git", *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FreezeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _clean_worktree(repo_root: Path) -> bool:
    """Return True if there are no uncommitted changes in the working tree."""
    try:
        status = _git("status", "--porcelain", cwd=repo_root)
        return status == ""
    except FreezeError:
        return False


def _list_tracked_files(repo_root: Path) -> list[str]:
    """Return the list of files tracked by git."""
    out = _git("ls-files", cwd=repo_root)
    return [line for line in out.splitlines() if line]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_files(file_paths: list[Path]) -> dict[str, str]:
    """Return a mapping of relative-path -> SHA-256 for a list of files."""
    digests: dict[str, str] = {}
    for p in file_paths:
        if p.is_file():
            rel = str(p)
            digests[rel] = sha256_of_file(p)
    return digests


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_evaluation_code(
    repo_root: Path,
    spec_sha256: str,
    *,
    amendment_sha256: str | None = None,
    dataset_plan_sha256: str | None = None,
) -> FreezeRecord:
    """Record the current git HEAD and file hashes as the frozen evaluation code."""
    repo_root = Path(repo_root).expanduser().resolve()
    head = _git("rev-parse", "HEAD", cwd=repo_root)
    if not head:
        raise FreezeError("cannot determine git HEAD")
    clean = _clean_worktree(repo_root)
    tracked = _list_tracked_files(repo_root)
    return FreezeRecord(
        evaluation_code_sha=head,
        repository_clean=clean,
        frozen_at=datetime.now(UTC),
        spec_sha256=spec_sha256,
        amendment_sha256=amendment_sha256,
        dataset_plan_sha256=dataset_plan_sha256,
        tracked_files=tracked,
    )


def verify_frozen_evaluation_code(
    repo_root: Path,
    record: FreezeRecord,
) -> bool:
    """Verify the current git HEAD matches the frozen record."""
    head = _git("rev-parse", "HEAD", cwd=repo_root)
    return head == record.evaluation_code_sha


def freeze_record_to_dict(record: FreezeRecord) -> dict[str, Any]:
    return {
        "evaluation_code_sha": record.evaluation_code_sha,
        "repository_clean": record.repository_clean,
        "frozen_at": record.frozen_at.isoformat(),
        "spec_sha256": record.spec_sha256,
        "amendment_sha256": record.amendment_sha256,
        "dataset_plan_sha256": record.dataset_plan_sha256,
        "tracked_files": record.tracked_files,
    }


def load_freeze_record(path: Path) -> FreezeRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FreezeRecord(
        evaluation_code_sha=data["evaluation_code_sha"],
        repository_clean=data["repository_clean"],
        frozen_at=datetime.fromisoformat(data["frozen_at"]),
        spec_sha256=data["spec_sha256"],
        amendment_sha256=data.get("amendment_sha256"),
        dataset_plan_sha256=data.get("dataset_plan_sha256"),
        tracked_files=data.get("tracked_files", []),
    )
