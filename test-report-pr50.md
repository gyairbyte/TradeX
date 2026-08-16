# Test Report: TradeX PR #50 (LONG-002B-AMEND-001)

## Summary
Credential-free, network-free verification of PR #50 (`devin/long-002b-core-data-feasibility`, head `3a03169c20e8c3bbb0c25151397bd968bcafecf9`) passed all requested checks. The focused amendment tests (`8 passed`), the full LONG-002B package (`49 passed`), module lint, `git diff --check`, the safe artifact bundle checksums/JSON validity, upstream spec SHA-256 cross-checks, preregistration/code commit ordering, and leakage scans all succeeded. The optional full `uv run pytest tests -q` regression produced `1639 passed, 3 failed`; the failures are the two pre-existing `tests/watchlists/test_refresh.py` tests plus the time-dependent `tests/earnings/test_calendar.py::test_get_next_earnings_yahoo_and_cache` hardcoded-date failure. No live provider probe was rerun and no commits were made.

## Command outputs and evidence

### Git sanity and scope
```text
$ git rev-parse HEAD
3a03169c20e8c3bbb0c25151397bd968bcafecf9

$ git diff --check
diff-check-ok

$ git diff --stat origin/main..HEAD
 .agents/skills/tradex-long-002b-testing/SKILL.md   |   89 +
 CLAUDE.md                                          |    5 +-
 README.md                                          |   28 +-
 docs/PROJECT-TRACKER.md                            |   23 +-
 docs/research/LONG-002B-AMEND-001.md               |  146 ++
 .../2026-08-16-200052/artifact_manifest.json       |   20 +
 .../2026-08-16-200052/checksums.sha256             |    5 +
 .../2026-08-16-200052/coverage_summary.csv         |    3 +
 .../2026-08-16-200052/data_quality_summary.csv     |    3 +
 .../2026-08-16-200052/feasibility_report.json      | 2031 ++++++++++++++++++++
 .../2026-08-16-200052/provider_contract_matrix.csv |   60 +
 .../specs/LONG-002B-AMEND-001-probe-v1.json        |  170 ++
 .../test_amendment_001.py                          |  377 +++
 .../long_002_data_feasibility/amendment_001.py     |  855 ++++++++
 .../research/long_002_data_feasibility/clients.py  |  139 +
 .../research/long_002_data_feasibility/report.py   |    3 +-
 16 files changed, 3947 insertions(+), 10 deletions(-)
```

### Focused amendment tests
```text
$ uv run pytest tests/research/long_002_data_feasibility/test_amendment_001.py -q
8 passed in 0.08s
```

### Full LONG-002B package tests
```text
$ uv run pytest tests/research/long_002_data_feasibility -q
49 passed in 12.56s
```

### Module lint
```text
$ uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility
All checks passed!
```

### Artifact bundle checksums
```text
$ cd docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052 && sha256sum -c checksums.sha256
feasibility_report.json: OK
provider_contract_matrix.csv: OK
coverage_summary.csv: OK
data_quality_summary.csv: OK
artifact_manifest.json: OK
```

### JSON validity, NaN/Infinity, manifest cross-check
```text
$ python3 - <<'PY'
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
feasibility_report.json valid and NaN/Infinity-free
artifact_manifest hash cross-check passed
```

### Upstream spec SHA-256s and artifact invariants
```text
$ sha256sum docs/research/specs/LONG-002-v1.json docs/research/specs/LONG-002B-probe-v1.json docs/research/specs/LONG-002B-data-contract-v1.json docs/research/specs/LONG-002B-AMEND-001-probe-v1.json
f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5  docs/research/specs/LONG-002-v1.json
002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98  docs/research/specs/LONG-002B-probe-v1.json
f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a  docs/research/specs/LONG-002B-data-contract-v1.json
38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7  docs/research/specs/LONG-002B-AMEND-001-probe-v1.json

$ python3 - <<'PY'
import json
from pathlib import Path

base = Path('docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052')
manifest = json.loads((base / 'artifact_manifest.json').read_text())
report = json.loads((base / 'feasibility_report.json').read_text())
assert report['long_002_spec_sha256'] == manifest['long_002_spec_sha256'] == 'f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5'
assert report['probe_spec_sha256'] == manifest['probe_spec_sha256'] == '38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7'
assert report['data_contract_sha256'] == manifest['data_contract_sha256'] == 'f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a'
assert report['task_id'] == manifest['task_id'] == 'LONG-002B-AMEND-001'
assert report['overall_disposition'] == manifest['overall_disposition'] == 'not_supported'
print('artifact manifest/report upstream SHA-256 invariants passed')
PY
artifact manifest/report upstream SHA-256 invariants passed
```

### Preregistration commit ordering
```text
$ git merge-base --is-ancestor 75fad17 f3552e382de7de2857af78d259eeee8ad8978453
$ echo 'prereg 75fad17 ancestor of code_commit_sha f3552e3'
prereg 75fad17 ancestor of code_commit_sha f3552e3

$ git merge-base --is-ancestor f3552e382de7de2857af78d259eeee8ad8978453 HEAD
$ echo 'code_commit_sha f3552e3 ancestor of HEAD'
code_commit_sha f3552e3 ancestor of HEAD
```

### Leakage scans
```text
$ rg '/home/ubuntu|/tmp/|~/.|api_key|secret|token|password|bearer|-----BEGIN' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true
(no output)

$ rg '"o":|"h":|"l":|"c":|"v":|"open":|"high":|"low":|"close":|"volume":|"bars": \[' docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/ 2>/dev/null || true
(no output)
```

### Optional full regression
```text
$ uv run pytest tests -q
3 failed, 1639 passed, 6 warnings in 786.76s (0:13:06)
EXIT:1

FAILED tests/earnings/test_calendar.py::test_get_next_earnings_yahoo_and_cache
FAILED tests/watchlists/test_refresh.py::test_fetch_market_caps_schwab_unconfigured_raises
FAILED tests/watchlists/test_refresh.py::test_schwab_liquidity_filter_degrades_gracefully
```

### Git status after verification
```text
$ git status --short
?? .agents/skills/tradex-long-002b-amend-001-testing/
?? test-plan-pr50.md
?? test-report-pr50.md
```

## Assertion results

- [PASS] `git rev-parse HEAD` = `3a03169c20e8c3bbb0c25151397bd968bcafecf9`
- [PASS] `git diff --check` clean
- [PASS] Diff stat against `origin/main` contains only the LONG-002B-AMEND-001 docs/specs/artifacts, `amendment_001.py`, `clients.py`, `report.py`, `test_amendment_001.py`, and doc syncs — no production trading code changed
- [PASS] `uv run pytest tests/research/long_002_data_feasibility/test_amendment_001.py -q` → `8 passed`
- [PASS] `uv run pytest tests/research/long_002_data_feasibility -q` → `49 passed`
- [PASS] `uv run ruff check tests/research/long_002_data_feasibility tradex/research/long_002_data_feasibility` → `All checks passed!`
- [PASS] `sha256sum -c checksums.sha256` inside `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-200052/` → all files `OK`
- [PASS] `feasibility_report.json` is valid JSON and NaN/Infinity-free
- [PASS] `artifact_manifest.json` file hashes match the actual bundle files
- [PASS] Upstream spec SHA-256s in `artifact_manifest.json` and `feasibility_report.json` match the locked files on disk
- [PASS] Preregistration commit `75fad17` is an ancestor of artifact `code_commit_sha` `f3552e3`; `f3552e3` is an ancestor of HEAD
- [PASS] No absolute paths, credentials, or raw OHLCV bar arrays leak from the artifact bundle
- [PASS] `uv run pytest tests -q` → `1639 passed, 3 failed`; failures are the two pre-existing watchlist tests plus the time-dependent `test_get_next_earnings_yahoo_and_cache` hardcoded-date failure
- [PASS] No live provider probe rerun; no commits made

## Issues / escalations
The artifact bundle does **not** contain a `preregistration_commit_sha` field. The `feasibility_report.json` and `artifact_manifest.json` only record `code_commit_sha` (`f3552e3...`), `long_002_spec_sha256`, `probe_spec_sha256`, and `data_contract_sha256`. The user requested confirming that `preregistration_commit_sha` predates `code_commit_sha`; since the field is absent, we verified the ordering via `git merge-base` on the preregistration commit `75fad17` instead. If the report is expected to include `preregistration_commit_sha`, that field should be added to the artifact JSON schema and `write_safe_artifacts`/`amendment_001.py`.
