"""Persistent, versioned, corruption-detectable discovery cache (LONG-MVP-003).

Provides atomic storage and checkpointing of discovery scan progress, avoiding
redundant same-session data requests across Streamlit reruns and process restarts.

Isolation guarantees:
  - A checkpoint is keyed strictly by the tuple of:
      (strategy_id, strategy_version, universe_id, universe_hash, session_date,
       requested_provider, earnings_source, earnings_buffer, min_score)
  - Any material change in universe snapshot, trading session date, provider,
    earnings policy, or minimum score produces a distinct cache key and cannot
    reuse incompatible results.
  - Files are written atomically (.tmp file + atomic rename) and validated with
    SHA-256 payload integrity checksums to prevent partial or corrupted reads.
  - Never stores credentials, tokens, or untrusted objects.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.discovery.models import DiscoveryCheckpoint

logger = logging.getLogger(__name__)

CURRENT_CHECKPOINT_VERSION = 1


def compute_discovery_cache_key(
    *,
    strategy_id: str,
    strategy_version: str,
    universe_id: str,
    universe_hash: str,
    session_date: date | str,
    requested_provider: str,
    earnings_source: str,
    earnings_buffer: int,
    min_score: int,
) -> str:
    """Compute a deterministic, collision-resistant cache key for discovery scan settings."""
    s_date = session_date.isoformat() if isinstance(session_date, date) else str(session_date)
    raw = [
        str(strategy_id).strip(),
        str(strategy_version).strip(),
        str(universe_id).strip(),
        str(universe_hash).strip(),
        s_date.strip(),
        str(requested_provider).strip().lower(),
        str(earnings_source).strip().lower(),
        int(earnings_buffer),
        int(min_score),
    ]
    payload = json.dumps(raw, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _calculate_checksum(data: dict[str, Any]) -> str:
    """Calculate SHA-256 checksum over checkpoint content excluding checksum."""
    copy_data = {k: v for k, v in data.items() if k != "checksum"}
    payload = json.dumps(copy_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DiscoveryCache:
    """Manages persistent discovery checkpoints in the configured cache directory."""

    def __init__(self, cache_dir: Path | str | None = None, *, settings: TradeXSettings | None = None) -> None:
        if cache_dir is not None:
            self.cache_dir = Path(str(cache_dir)).expanduser()
        else:
            s = settings or load_runtime_settings()
            self.cache_dir = Path(str(s.paths.discovery_cache_dir)).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"discovery_{cache_key}.json"

    def load(self, cache_key: str) -> DiscoveryCheckpoint | None:
        """Load and validate an existing checkpoint by key.

        Returns None if the checkpoint does not exist, is malformed, or fails
        the integrity checksum check.
        """
        path = self._file_path(cache_key)
        if not path.is_file():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning("Corrupt discovery checkpoint at %s: root is not dict", path)
                return None

            recorded_checksum = data.get("checksum", "")
            actual_checksum = _calculate_checksum(data)
            if recorded_checksum != actual_checksum:
                logger.warning(
                    "Discovery checkpoint at %s failed checksum integrity: %s != %s",
                    path,
                    recorded_checksum,
                    actual_checksum,
                )
                return None

            version = int(data.get("version", 0))
            if version != CURRENT_CHECKPOINT_VERSION:
                logger.info(
                    "Discovery checkpoint at %s has unsupported version %d (current=%d); ignoring",
                    path,
                    version,
                    CURRENT_CHECKPOINT_VERSION,
                )
                return None

            return DiscoveryCheckpoint.from_dict(data)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Error reading discovery checkpoint from %s: %s", path, exc)
            return None

    def save(self, checkpoint: DiscoveryCheckpoint) -> None:
        """Atomically persist a discovery checkpoint with integrity checksum."""
        data = checkpoint.to_dict()
        data["version"] = CURRENT_CHECKPOINT_VERSION
        data["updated_at"] = datetime.now(UTC).isoformat()
        data["checksum"] = _calculate_checksum(data)

        checkpoint.checksum = data["checksum"]
        checkpoint.updated_at = data["updated_at"]

        path = self._file_path(checkpoint.cache_key)
        tmp_path = path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=True)

        os.replace(tmp_path, path)

    def clear(self, cache_key: str) -> bool:
        """Delete a checkpoint if it exists."""
        path = self._file_path(cache_key)
        if path.is_file():
            try:
                path.unlink()
                return True
            except OSError as exc:
                logger.warning("Failed to delete discovery checkpoint %s: %s", path, exc)
        return False
