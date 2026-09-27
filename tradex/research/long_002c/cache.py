"""Persistent local response cache for historical market and reference data providers.

Ensures deterministic reproducibility, prevents repeated provider quota consumption,
records request/response hashes, and never stores credentials or tokens.
Cache storage lives under gitignored data/cache/long_002c/.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradex.research.long_002c.spec import REPO_ROOT

DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache" / "long_002c"


def sanitize_url(url: str) -> str:
    """Remove sensitive credential query parameters from URL for caching and logging."""
    sanitized = re.sub(r"apiKey=[^&]+", "apiKey=[REDACTED]", url)
    sanitized = re.sub(r"token=[^&]+", "token=[REDACTED]", sanitized)
    sanitized = re.sub(r"secret=[^&]+", "secret=[REDACTED]", sanitized)
    return sanitized


class ResponseCache:
    """File-based persistent cache storing provider responses with cryptographic provenance."""

    def __init__(self, cache_dir: Path | None = None, enabled: bool = True) -> None:
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, sanitized_url: str, request_fingerprint: str) -> str:
        h = hashlib.sha256(f"{sanitized_url}::{request_fingerprint}".encode()).hexdigest()
        return h

    def get(self, url: str, request_fingerprint: str) -> tuple[bytes | None, str | None, str | None]:
        """Retrieve cached response if available.

        Returns (response_bytes, response_sha256, retrieval_timestamp_utc) or (None, None, None).
        """
        if not self.enabled:
            return None, None, None

        sanitized = sanitize_url(url)
        key = self._cache_key(sanitized, request_fingerprint)
        body_file = self.cache_dir / f"{key}.bin"
        meta_file = self.cache_dir / f"{key}.meta.json"

        if body_file.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                body = body_file.read_bytes()
                resp_sha = meta.get("response_sha256")
                actual_sha = hashlib.sha256(body).hexdigest()
                if resp_sha == actual_sha:
                    return body, resp_sha, meta.get("retrieval_timestamp_utc")
            except Exception:  # noqa: BLE001
                return None, None, None

        return None, None, None

    def get_json(self, url: str, request_fingerprint: str) -> tuple[dict[str, Any] | list[Any] | None, str | None, str | None]:
        """Retrieve and parse JSON response from cache."""
        body, resp_sha, req_time = self.get(url, request_fingerprint)
        if body is None:
            return None, None, None
        try:
            return json.loads(body.decode("utf-8")), resp_sha, req_time
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None, None

    def has(self, url: str, request_fingerprint: str) -> bool:
        """Check if cached response exists."""
        if not self.enabled:
            return False
        sanitized = sanitize_url(url)
        key = self._cache_key(sanitized, request_fingerprint)
        return (self.cache_dir / f"{key}.bin").exists()

    def set(
        self,
        url: str,
        request_fingerprint: str,
        body: bytes | str,
        endpoint_pattern: str | None = None,
        retrieval_timestamp_utc: str | None = None,
    ) -> str:
        """Store response body and metadata in persistent cache."""
        if not self.enabled:
            raw_bytes = body.encode("utf-8") if isinstance(body, str) else body
            return hashlib.sha256(raw_bytes).hexdigest()

        sanitized = sanitize_url(url)
        key = self._cache_key(sanitized, request_fingerprint)
        body_file = self.cache_dir / f"{key}.bin"
        meta_file = self.cache_dir / f"{key}.meta.json"

        raw_bytes = body.encode("utf-8") if isinstance(body, str) else body
        resp_sha = hashlib.sha256(raw_bytes).hexdigest()
        ts_utc = retrieval_timestamp_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")

        meta = {
            "cache_version": "1.0",
            "sanitized_url": sanitized,
            "endpoint_pattern": endpoint_pattern or "",
            "request_fingerprint_sha256": request_fingerprint,
            "response_sha256": resp_sha,
            "retrieval_timestamp_utc": ts_utc,
            "byte_count": len(raw_bytes),
        }

        body_file.write_bytes(raw_bytes)
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return resp_sha
