# Test Plan: TradeX PR #50 (LONG-002B-AMEND-001, branch `devin/long-002b-core-data-feasibility`)

## Scope
Credential-free, network-free verification of the LONG-002B-AMEND-001 bounded provider amendment on the PR head (currently `3a03169c20e8c3bbb0c25151397bd968bcafecf9`). Do **not** rerun the live provider probe. The live probe artifact bundle is at `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/`.

## Setup
- Repo: `/home/ubuntu/repos/TradeX`
- HEAD: `3a03169c20e8c3bbb0c25151397bd968bcafecf9` (fetched from `refs/pull/50/head`)
- `uv sync --extra dev --extra all` already completed
- No credentials or network calls required

## Assertions

### 1. Git sanity and scope
```bash
git rev-parse HEAD
git diff --check
git diff --stat origin/main..HEAD
```
- `HEAD` = `3a03169c20e8c3bbb0c25151397bd968bcafecf9`.
- `git diff --check` exits 0.
- The diff against `origin/main` contains only the LONG-002B-AMEND-001 docs/specs, `tradex/research/long_002_data_feasibility/amendment_001.py`, `clients.py`, `report.py`, `tests/research/long_002_data_feasibility/test_amendment_001.py`, and the safe artifact bundle — no production signal/screener/tracker/UI code.

### 2. Focused amendment tests
```bash
uv run pytest tests/research/long_002_data_feasibility/test_amendment_001.py -q
```
Expected: all tests pass (8 tests).

### 3. Full LONG-002B package tests
```bash
uv run pytest tests/research/long_002_data_feasibility -q
```
Expected: all tests pass (currently 49 collected: 41 base + 8 amendment).

### 4. Module lint
```bash
uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility
```
Expected: `All checks passed!`.

### 5. Artifact bundle checksum integrity
```bash
cd docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052
sha256sum -c checksums.sha256
```
Expected: every file reports `OK`.

### 6. Artifact bundle JSON validity and NaN/Infinity
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

### 8. Upstream spec SHA-256s match locked values
```bash
sha256sum docs/research/specs/LONG-002-v1.json \
  docs/research/specs/LONG-002B-probe-v1.json \
  docs/research/specs/LONG-002B-data-contract-v1.json \
  docs/research/specs/LONG-002B-AMEND-001-probe-v1.json
```
Expected:
- `LONG-002-v1.json` = `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5`
- `LONG-002B-probe-v1.json` = `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98`
- `LONG-002B-data-contract-v1.json` = `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a`
- `LONG-002B-AMEND-001-probe-v1.json` = `38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7`

Then compare these to `long_002_spec_sha256`, `data_contract_sha256`, and `probe_spec_sha256` in `artifact_manifest.json` and `feasibility_report.json`. The artifact's `probe_spec_sha256` must equal the amendment probe spec SHA-256.

### 9. Preregistration commit predates code commit
The preregistration commit for the amendment spec is `75fad17 chore(LONG-002B-AMEND-001): preregister amendment spec and human-readable report`. The artifact `code_commit_sha` is `f3552e382de7de2857af78d259eeee8ad8978453`.
```bash
git merge-base --is-ancestor 75fad17 f3552e382de7de2857af78d259eeee8ad8978453
git merge-base --is-ancestor f3552e382de7de2857af78d259eeee8ad8978453 HEAD
```
Expected: both exit 0. If the artifact report/manifest contain a `preregistration_commit_sha` field, it should also be an ancestor of `code_commit_sha`.

### 10. No leakage in the artifact bundle
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
Expected: a large pass count with only the two pre-existing `tests/watchlists/test_refresh.py` failures and, if present, the time-dependent `tests/earnings/test_calendar.py` hardcoded-date failure. Any other failure is a regression.

### 12. Git status after verification
```bash
git status --short
```
Expected: clean tracked tree; only untracked verification artifacts (test plan, report, and skill suggestion).

## Execution command summary
```bash
cd /home/ubuntu/repos/TradeX

git rev-parse HEAD
git diff --check
git diff --stat origin/main..HEAD

uv run pytest tests/research/long_002_data_feasibility/test_amendment_001.py -q
uv run pytest tests/research/long_002_data_feasibility -q
uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility

cd docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052
sha256sum -c checksums.sha256
cd /home/ubuntu/repos/TradeX

python3 - <<'PY'
import json, hashlib
from pathlib import Path

base = Path('docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052')
report_text = (base / 'feasibility_report.json').read_text()
json.loads(report_text)
assert 'NaN' not in report_text and 'Infinity' not in report_text and '-Infinity' not in report_text
print('feasibility_report.json valid and NaN/Infinity-free')

manifest = json.loads((base / 'artifact_manifest.json').read_text())
for fname, expected in manifest['files'].items():
    actual = hashlib.sha256((base / fname).read_bytes()).hexdigest()
    assert actual == expected
print('artifact_manifest hash cross-check passed')
PY

sha256sum docs/research/specs/LONG-002-v1.json docs/research/specs/LONG-002B-probe-v1.json docs/research/specs/LONG-002B-data-contract-v1.json docs/research/specs/LONG-002B-AMEND-001-probe-v1.json

git merge-base --is-ancestor 75fad17 f3552e382de7de2857af78d259eeee8ad8978453
git merge-base --is-ancestor f3552e382de7de2857af78d259eeee8ad8978453 HEAD

rg '/home/ubuntu|/tmp/|~/.|api_key|secret|token|password|bearer|-----BEGIN' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true
rg '"o":|"h":|"l":|"c":|"v":|"open":|"high":|"low":|"close":|"volume":|"bars": \[' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true

uv run pytest tests -q

git status --short
```

## Expected result
Focused amendment and full LONG-002B package tests pass, module lint is clean, `git diff --check` is clean, the artifact bundle checksums and JSON validity pass, upstream spec SHA-256s match, the preregistration commit predates the artifact code commit, no leakage is found, and the optional full regression produces only the known pre-existing failures. No live provider probe is rerun.
