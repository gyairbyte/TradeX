---
name: tradex-long-002b-amend-001-testing
description: Credential-free verification checklist for the LONG-002B-AMEND-001 bounded provider amendment, its deterministic tests, and safe artifact bundle.
---

# TradeX LONG-002B-AMEND-001 Testing Skill

Use this skill when verifying the LONG-002B-AMEND-001 amendment to the `tradex/research/long_002_data_feasibility/` package or the `docs/research/artifacts/LONG-002B-AMEND-001/` safe artifact bundles.

All verification must remain credential-free, network-free, and must not rerun the live provider probe.

## Standard verification steps

### 1. Git sanity and scope
```bash
cd /home/ubuntu/repos/TradeX
git rev-parse HEAD
git diff --check
git diff --stat origin/main..HEAD
```
- Confirm HEAD matches the requested PR head.
- `git diff --check` must exit 0.
- The diff against `origin/main` should contain only:
  - `docs/research/LONG-002B-AMEND-001.md`
  - `docs/research/specs/LONG-002B-AMEND-001-probe-v1.json`
  - `docs/research/artifacts/LONG-002B-AMEND-001/<run-id>/`
  - `tests/research/long_002_data_feasibility/test_amendment_001.py`
  - `tradex/research/long_002_data_feasibility/amendment_001.py`
  - `tradex/research/long_002_data_feasibility/clients.py`
  - `tradex/research/long_002_data_feasibility/report.py`
  - README/PROJECT-TRACKER/CLAUDE syncs
  - any pre-existing skill/testing artifact additions (e.g. `.agents/skills/tradex-long-002b-testing/SKILL.md`)
- No production signal, screener, tracker, UI, or fetcher files should change.

### 2. Amendment-focused tests
```bash
uv run pytest tests/research/long_002_data_feasibility/test_amendment_001.py -q
```
Expected: all tests pass (currently 8).

### 3. Full LONG-002B package tests
```bash
uv run pytest tests/research/long_002_data_feasibility -q
```
Expected: all tests pass (currently 49: 41 base + 8 amendment).

### 4. Module lint
```bash
uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility
```
Expected: `All checks passed!`.

### 5. Artifact bundle integrity
Inside the bundle directory (e.g. `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/`):
```bash
cd docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052
sha256sum -c checksums.sha256
```
Expected: every file reports `OK`.

### 6. JSON validity and no NaN/Infinity
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

### 7. Artifact manifest cross-check
```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path

base = Path('docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052')
manifest = json.loads((base / 'artifact_manifest.json').read_text())
for fname, expected in manifest['files'].items():
    actual = hashlib.sha256((base / fname).read_bytes()).hexdigest()
    assert actual == expected
print('artifact_manifest hash cross-check passed')
PY
```

### 8. Upstream spec SHA-256 verification
```bash
sha256sum docs/research/specs/LONG-002-v1.json \
  docs/research/specs/LONG-002B-probe-v1.json \
  docs/research/specs/LONG-002B-data-contract-v1.json \
  docs/research/specs/LONG-002B-AMEND-001-probe-v1.json
```
Expected values:
- `LONG-002-v1.json` = `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5`
- `LONG-002B-probe-v1.json` = `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98`
- `LONG-002B-data-contract-v1.json` = `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a`
- `LONG-002B-AMEND-001-probe-v1.json` = `38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7`

Then verify the artifact `feasibility_report.json` and `artifact_manifest.json` contain matching `long_002_spec_sha256`, `probe_spec_sha256`, and `data_contract_sha256`.

### 9. Preregistration commit ordering
The amendment spec was preregistered in commit `75fad17` (`chore(LONG-002B-AMEND-001): preregister amendment spec and human-readable report`). The artifact's `code_commit_sha` is `f3552e382de7de2857af78d259eeee8ad8978453`.
```bash
git merge-base --is-ancestor 75fad17 f3552e382de7de2857af78d259eeee8ad8978453
git merge-base --is-ancestor f3552e382de7de2857af78d259eeee8ad8978453 HEAD
```
Expected: both exit 0. If the artifact ever adds a `preregistration_commit_sha` field, that SHA should also be an ancestor of `code_commit_sha`.

### 10. No leakage
```bash
cd /home/ubuntu/repos/TradeX
rg '/home/ubuntu|/tmp/|~/.|api_key|secret|token|password|bearer|-----BEGIN' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true
rg '"o":|"h":|"l":|"c":|"v":|"open":|"high":|"low":|"close":|"volume":|"bars": \[' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true
```
Expected: no matches for absolute paths, credentials, or raw OHLCV bar arrays.

### 11. Optional full regression
```bash
uv run pytest tests -q
```
Expect the two pre-existing `tests/watchlists/test_refresh.py` failures (`test_fetch_market_caps_schwab_unconfigured_raises`, `test_schwab_liquidity_filter_degrades_gracefully`) and, if the run date is after the hardcoded fixture date, a `tests/earnings/test_calendar.py::test_get_next_earnings_yahoo_and_cache` failure. Any additional failure is a regression.

## Devin Secrets Needed
None. This skill is credential-free and network-free.
