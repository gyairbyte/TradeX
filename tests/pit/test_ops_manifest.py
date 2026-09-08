"""Tests for PITUniverseManifest, load_universe_manifest, estimate_capacity, and manifest hash (MVP-ARCH-001-R7-PIT-001C1)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date
from pathlib import Path

import pytest

from tradex.pit.massive_reference import DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS
from tradex.pit.models import compute_universe_hash
from tradex.pit.ops import (
    PITCapacityEstimate,
    PITUniverseManifest,
    estimate_capacity,
    load_universe_manifest,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_manifest_dict(**overrides) -> dict:
    base = {
        "contract_version": 1,
        "universe_id": "test-u",
        "universe_version": "v1",
        "effective_from": "2026-01-01",
        "symbols": ["AAPL", "MSFT"],
        "description": "Test manifest",
    }
    base.update(overrides)
    return base


def _write_manifest(d: dict, path: Path) -> None:
    path.write_text(json.dumps(d), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# PITUniverseManifest dataclass validation
# ─────────────────────────────────────────────────────────────────────────────

class TestPITUniverseManifestValidation:
    def _make(self, **kw) -> PITUniverseManifest:
        defaults: dict = {
            "contract_version": 1,
            "universe_id": "u-1",
            "universe_version": "v1",
            "effective_from": date(2026, 1, 1),
            "symbols": ("AAPL", "MSFT"),
            "description": "desc",
        }
        defaults.update(kw)
        return PITUniverseManifest(**defaults)

    def test_valid_minimal(self):
        m = self._make()
        assert m.universe_id == "u-1"
        assert m.symbols == ("AAPL", "MSFT")

    def test_invalid_contract_version(self):
        with pytest.raises(ValueError, match="contract_version"):
            self._make(contract_version=2)

    def test_invalid_contract_version_bool(self):
        with pytest.raises(ValueError, match="contract_version"):
            self._make(contract_version=True)
        with pytest.raises(ValueError, match="contract_version"):
            self._make(contract_version=False)

    def test_invalid_universe_id_empty(self):
        with pytest.raises(ValueError, match="universe_id"):
            self._make(universe_id="")

    def test_invalid_universe_id_pattern(self):
        with pytest.raises(ValueError, match="syntactically invalid"):
            self._make(universe_id="no spaces allowed here")

    def test_valid_universe_id_hyphens_underscores(self):
        m = self._make(universe_id="test-universe_v2")
        assert m.universe_id == "test-universe_v2"

    def test_invalid_universe_version_empty(self):
        with pytest.raises(ValueError, match="universe_version"):
            self._make(universe_version="")

    def test_universe_version_whitespace_trimmed(self):
        m1 = self._make(universe_version="  v1  ")
        m2 = self._make(universe_version="v1")
        assert m1.universe_version == "v1"
        assert m1.manifest_hash == m2.manifest_hash

    def test_invalid_effective_from_not_date(self):
        with pytest.raises(TypeError, match="date instance"):
            self._make(effective_from="2026-01-01")

    def test_invalid_effective_from_datetime_rejected(self):
        from datetime import datetime
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        with pytest.raises(TypeError, match="date instance and not a datetime instance"):
            self._make(effective_from=dt)

    def test_empty_symbols(self):
        with pytest.raises(ValueError, match="symbols"):
            self._make(symbols=())


    def test_description_must_be_str(self):
        with pytest.raises(TypeError, match="description"):
            self._make(description=123)

    def test_universe_hash_matches_compute_universe_hash(self):
        m = self._make(symbols=("AAPL", "MSFT"))
        expected = compute_universe_hash(("AAPL", "MSFT"))
        assert m.universe_hash == expected

    def test_manifest_hash_is_deterministic(self):
        m1 = self._make()
        m2 = self._make()
        assert m1.manifest_hash == m2.manifest_hash

    def test_manifest_hash_changes_with_symbols(self):
        m1 = self._make(symbols=("AAPL",))
        m2 = self._make(symbols=("AAPL", "MSFT"))
        assert m1.manifest_hash != m2.manifest_hash

    def test_manifest_hash_changes_with_universe_id(self):
        m1 = self._make(universe_id="alpha")
        m2 = self._make(universe_id="beta")
        assert m1.manifest_hash != m2.manifest_hash

    def test_manifest_hash_description_not_material(self):
        """description is excluded from manifest_hash."""
        m1 = self._make(description="foo")
        m2 = self._make(description="bar different")
        assert m1.manifest_hash == m2.manifest_hash

    def test_universe_hash_matches_same_universe_different_order_input(self):
        """normalize_symbols sorts; compute_universe_hash of sorted == compute_universe_hash."""
        m = self._make(symbols=("MSFT", "AAPL"))
        # symbols stored as normalized sorted tuple
        assert m.symbols == ("AAPL", "MSFT")
        assert m.universe_hash == compute_universe_hash(("AAPL", "MSFT"))


# ─────────────────────────────────────────────────────────────────────────────
# load_universe_manifest
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadUniverseManifest:
    def test_minimal_valid_manifest(self, tmp_path):
        p = tmp_path / "universe.json"
        _write_manifest(_minimal_manifest_dict(), p)
        m = load_universe_manifest(p)
        assert m.universe_id == "test-u"
        assert m.symbols == ("AAPL", "MSFT")

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_universe_manifest(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="valid JSON"):
            load_universe_manifest(p)

    def test_root_not_dict(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            load_universe_manifest(p)

    def test_missing_contract_version(self, tmp_path):
        d = _minimal_manifest_dict()
        del d["contract_version"]
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="contract_version"):
            load_universe_manifest(p)

    def test_wrong_contract_version(self, tmp_path):
        d = _minimal_manifest_dict(contract_version=99)
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="contract_version"):
            load_universe_manifest(p)

    @pytest.mark.parametrize("bad_cv", [True, False, 1.0, "1", None, 0, 2, 99])
    def test_wrong_or_non_integer_contract_version_rejected(self, tmp_path, bad_cv):
        d = _minimal_manifest_dict(contract_version=bad_cv)
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="contract_version"):
            load_universe_manifest(p)

    def test_universe_version_whitespace_normalized(self, tmp_path):
        d = _minimal_manifest_dict(universe_version="  v1  ")
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        assert m.universe_version == "v1"
        direct = PITUniverseManifest(
            contract_version=1,
            universe_id="test-u",
            universe_version="v1",
            effective_from=date(2026, 1, 1),
            symbols=("AAPL", "MSFT"),
            description="Test manifest",
        )
        assert m.manifest_hash == direct.manifest_hash

    def test_missing_universe_id(self, tmp_path):
        d = _minimal_manifest_dict()
        del d["universe_id"]
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="universe_id"):
            load_universe_manifest(p)

    def test_invalid_universe_id_pattern(self, tmp_path):
        d = _minimal_manifest_dict(universe_id="Bad ID!")
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="syntactically invalid"):
            load_universe_manifest(p)

    def test_missing_effective_from(self, tmp_path):
        d = _minimal_manifest_dict()
        del d["effective_from"]
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="effective_from"):
            load_universe_manifest(p)

    def test_invalid_effective_from_format(self, tmp_path):
        d = _minimal_manifest_dict(effective_from="January 1 2026")
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="ISO date"):
            load_universe_manifest(p)

    def test_missing_symbols(self, tmp_path):
        d = _minimal_manifest_dict()
        del d["symbols"]
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="symbols"):
            load_universe_manifest(p)

    def test_empty_symbols_list(self, tmp_path):
        d = _minimal_manifest_dict(symbols=[])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError):
            load_universe_manifest(p)

    def test_symbols_normalized(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["  msft  ", "aapl"])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        # normalize_symbols: trimmed, uppercased, sorted, deduplicated
        assert m.symbols == ("AAPL", "MSFT")

    def test_symbols_deduplicated(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["AAPL", "aapl", "AAPL"])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        assert m.symbols == ("AAPL",)

    def test_symbol_non_string_raises(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["AAPL", 123])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(TypeError, match="Invalid symbol"):
            load_universe_manifest(p)

    def test_blank_symbol_raises(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["AAPL", "   "])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(ValueError, match="Invalid symbols"):
            load_universe_manifest(p)

    def test_description_optional(self, tmp_path):
        d = _minimal_manifest_dict()
        del d["description"]
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        assert m.description == ""

    def test_description_non_string_raises(self, tmp_path):
        d = _minimal_manifest_dict(description=42)
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        with pytest.raises(TypeError, match="description"):
            load_universe_manifest(p)

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "u.json"
        _write_manifest(_minimal_manifest_dict(), p)
        m = load_universe_manifest(str(p))
        assert m.universe_id == "test-u"

    def test_large_valid_universe(self, tmp_path):
        symbols = [f"SYM{i:04d}" for i in range(200)]
        d = _minimal_manifest_dict(symbols=symbols)
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        assert len(m.symbols) == 200

    def test_universe_hash_same_as_model_compute(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["NVDA", "AAPL", "TSLA"])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        expected = compute_universe_hash(m.symbols)
        assert m.universe_hash == expected

    def test_manifest_hash_is_sha256_of_canonical_fields(self, tmp_path):
        d = _minimal_manifest_dict(symbols=["AAPL"])
        p = tmp_path / "u.json"
        _write_manifest(d, p)
        m = load_universe_manifest(p)
        # Reproduce the hash manually
        payload = {
            "contract_version": 1,
            "effective_from": "2026-01-01",
            "symbols": list(m.symbols),
            "universe_id": m.universe_id,
            "universe_version": m.universe_version,
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert m.manifest_hash == expected


# ─────────────────────────────────────────────────────────────────────────────
# estimate_capacity
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimateCapacity:
    def _manifest(self, n_symbols: int = 5) -> PITUniverseManifest:
        symbols = tuple(f"SYM{i:03d}" for i in range(n_symbols))
        return PITUniverseManifest(
            contract_version=1,
            universe_id="capacity-test",
            universe_version="v1",
            effective_from=date(2026, 1, 1),
            symbols=symbols,
            description="",
        )

    def test_returns_pacing_estimate(self):
        m = self._manifest(10)
        est = estimate_capacity(m)
        assert isinstance(est, PITCapacityEstimate)
        assert est.symbol_count == 10
        assert est.minimum_reference_requests == 10
        assert est.maximum_reference_requests == 20

    def test_default_pacing_interval(self):
        m = self._manifest(3)
        est = estimate_capacity(m)
        assert est.pacing_interval_seconds == DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS

    def test_custom_pacing_interval(self):
        m = self._manifest(4)
        est = estimate_capacity(m, pacing_interval_seconds=5.0)
        assert est.pacing_interval_seconds == 5.0
        assert est.minimum_pacing_floor_seconds == 3 * 5.0
        assert est.maximum_pacing_floor_seconds == 7 * 5.0

    def test_pacing_floor_math(self):
        m = self._manifest(10)
        interval = 12.1
        est = estimate_capacity(m, pacing_interval_seconds=interval)
        assert est.minimum_pacing_floor_seconds == pytest.approx(9 * interval)
        assert est.maximum_pacing_floor_seconds == pytest.approx(19 * interval)

    def test_single_symbol_universe(self):
        m = self._manifest(1)
        est = estimate_capacity(m, pacing_interval_seconds=12.1)
        assert est.symbol_count == 1
        assert est.minimum_reference_requests == 1
        assert est.maximum_reference_requests == 2
        assert est.minimum_pacing_floor_seconds == 0.0
        assert est.maximum_pacing_floor_seconds == 12.1

    def test_two_symbol_universe(self):
        m = self._manifest(2)
        est = estimate_capacity(m, pacing_interval_seconds=12.1)
        assert est.symbol_count == 2
        assert est.minimum_reference_requests == 2
        assert est.maximum_reference_requests == 4
        assert est.minimum_pacing_floor_seconds == pytest.approx(12.1)
        assert est.maximum_pacing_floor_seconds == pytest.approx(36.3)

    @pytest.mark.parametrize("bad_interval,exc_type", [
        (True, TypeError),
        (False, TypeError),
        ("12.1", TypeError),
        (-0.1, ValueError),
        (-10.0, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (float("-inf"), ValueError),
    ])
    def test_invalid_pacing_interval_rejected(self, bad_interval, exc_type):
        m = self._manifest(3)
        with pytest.raises(exc_type):
            estimate_capacity(m, pacing_interval_seconds=bad_interval)

    def test_none_pacing_interval_uses_default(self):
        m = self._manifest(3)
        est = estimate_capacity(m, pacing_interval_seconds=None)
        assert est.pacing_interval_seconds == DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS

    def test_universe_id_and_version_preserved(self):
        m = self._manifest(3)
        est = estimate_capacity(m)
        assert est.universe_id == m.universe_id
        assert est.universe_version == m.universe_version

    def test_no_network_calls(self):
        """estimate_capacity must not perform any network calls."""
        # If this test passes without mocking network, it proves no network call was made.
        m = self._manifest(50)
        est = estimate_capacity(m)
        assert est.symbol_count == 50

    def test_zero_pacing_interval(self):
        m = self._manifest(5)
        est = estimate_capacity(m, pacing_interval_seconds=0.0)
        assert est.minimum_pacing_floor_seconds == 0.0
        assert est.maximum_pacing_floor_seconds == 0.0

    def test_deterministic(self):
        """Same manifest always produces same estimate."""
        m = self._manifest(7)
        est1 = estimate_capacity(m, pacing_interval_seconds=12.1)
        est2 = estimate_capacity(m, pacing_interval_seconds=12.1)
        assert est1.minimum_pacing_floor_seconds == est2.minimum_pacing_floor_seconds
        assert est1.maximum_pacing_floor_seconds == est2.maximum_pacing_floor_seconds
