"""Locked spec and data-contract loading for LONG-002B."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_of_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()


def load_probe_spec(repo_root: Path | str | None = None) -> tuple[dict[str, Any], str]:
    """Return the probe spec dict and its SHA-256."""
    root = Path(repo_root or ".")
    path = root / "docs" / "research" / "specs" / "LONG-002B-probe-v1.json"
    raw = path.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict):
        raise TypeError("Probe spec must be a JSON object")
    return spec, hashlib.sha256(raw).hexdigest()


def load_data_contract(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Return the data contract dict."""
    root = Path(repo_root or ".")
    path = root / "docs" / "research" / "specs" / "LONG-002B-data-contract-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def long_002_spec_sha256(repo_root: Path | str | None = None) -> str:
    root = Path(repo_root or ".")
    return sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002-v1.json")
