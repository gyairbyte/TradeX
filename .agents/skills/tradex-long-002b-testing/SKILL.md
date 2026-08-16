---
name: tradex-long-002b-testing
description: Credential-free verification checklist for the LONG-002B core data feasibility research package, its bounded probe artifacts, and the PIT fundamentals correction.
---

# TradeX LONG-002B Testing Skill

Use this skill when verifying changes to the `tradex/research/long_002_data_feasibility/` package or the `docs/research/artifacts/LONG-002B/` safe artifact bundles.

All verification must remain credential-free, network-free, and must not rerun the live provider probe.

## Standard verification steps

### 1. Git sanity and scope
```bash
cd /home/ubuntu/repos/TradeX
git rev-parse HEAD
git diff --check
git diff --stat HEAD^
```
- Confirm HEAD matches the requested PR head.
- `git diff --check` must exit 0.
- The diff stat should contain only `tradex/research/long_002_data_feasibility/`, `tests/research/long_002_data_feasibility/`, `docs/research/LONG-002B-DATA-FEASIBILITY.md`, `README.md`, `docs/PROJECT-TRACKER.md`, and `docs/research/artifacts/LONG-002B/YYYY-MM-DD-HHMMSS/` bundles.

### 2. Focused test suite
```bash
uv run pytest tests/research/long_002_data_feasibility -q
```
Expected: all tests pass (currently 41).

### 3. Module lint
```bash
uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility
```
Expected: `All checks passed!`.

### 4. Artifact bundle integrity
Inside the bundle directory (e.g. `docs/research/artifacts/LONG-002B/2026-08-13-044204/`):
```bash
cd docs/research/artifacts/LONG-002B/2026-08-13-044204
sha256sum -c checksums.sha256
```
Expected: every file reports `OK`.

### 5. JSON validity and no NaN/Infinity
```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path('feasibility_report.json')
text = p.read_text()
json.loads(text)
assert 'NaN' not in text and 'Infinity' not in text and '-Infinity' not in text
print('feasibility_report.json valid and NaN/Infinity-free')
PY
```

### 6. No leakage
```bash
cd /home/ubuntu/repos/TradeX
rg '/home/ubuntu|/tmp/|~/.|api_key|secret|token|password|bearer|-----BEGIN' docs/research/artifacts/LONG-002B/2026-08-13-044204/ 2>/dev/null || true
rg '"o":|"h":|"l":|"c":|"v":|"open":|"high":|"low":|"close":|"volume":|"bars": \[' docs/research/artifacts/LONG-002B/2026-08-13-044204/ 2>/dev/null || true
```
Expected: no matches for absolute paths, credentials, or raw OHLCV bar arrays.

### 7. Artifact manifest cross-check
```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path

base = Path('docs/research/artifacts/LONG-002B/2026-08-13-044204')
manifest = json.loads((base / 'artifact_manifest.json').read_text())
for fname, expected in manifest['files'].items():
    actual = hashlib.sha256((base / fname).read_bytes()).hexdigest()
    assert actual == expected
print('artifact_manifest hash cross-check passed')
PY
```

### 8. Optional full regression
```bash
uv run pytest tests -q
```
Expect the two pre-existing `tests/watchlists/test_refresh.py` failures (`test_fetch_market_caps_schwab_unconfigured_raises`, `test_schwab_liquidity_filter_degrades_gracefully`); any additional failure is a regression.

## Devin Secrets Needed
None. This skill is credential-free and network-free.
