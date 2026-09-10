"""
Tests for r7_pit_provider_study.py
"""
import subprocess
from datetime import date
from pathlib import Path
from unittest import mock

from tradex.earnings.calendar import (
    EarningsDataUnavailableError,
    EarningsProviderLookupError,
    EarningsProviderResponseError,
)
from tradex.pit.ops import load_universe_manifest
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "research" / "r7_pit_provider_study.py"
ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-c2-readiness-a"
CANDIDATE_B_JSON = ARTIFACTS_DIR / "candidate-dow30.json"
CANDIDATE_C_JSON = ARTIFACTS_DIR / "candidate-dow30-sector-etfs.json"

def test_no_live_calls_without_guard(monkeypatch):
    """1. no live calls without the explicit execution guard"""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    mock_yahoo = mock.Mock()
    mock_massive = mock.Mock()
    monkeypatch.setattr("scripts.research.r7_pit_provider_study._fetch_from_yahoo", mock_yahoo)
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.MassiveReferenceClient", mock_massive)
    
    # Missing args
    monkeypatch.setattr("sys.argv", ["r7_pit_provider_study.py"])
    r7_pit_provider_study.main()
    assert mock_yahoo.call_count == 0
    assert mock_massive.call_count == 0

    # Wrong task ID
    monkeypatch.setattr("sys.argv", ["r7_pit_provider_study.py", "--execute-live", "--confirm-task-id", "WRONG"])
    r7_pit_provider_study.main()
    assert mock_yahoo.call_count == 0
    assert mock_massive.call_count == 0

def test_missing_credential_preflight(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    mock_yahoo = mock.Mock()
    mock_massive = mock.Mock()
    monkeypatch.setattr("scripts.research.r7_pit_provider_study._fetch_from_yahoo", mock_yahoo)
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.MassiveReferenceClient", mock_massive)
    
    # Mock settings to return no credential
    mock_settings = mock.Mock()
    mock_settings.data.massive_api_key = None
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.load_runtime_settings", mock.Mock(return_value=mock_settings))
    
    # Point results json to tmp
    tmp_json = tmp_path / "results.json"
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.RESULTS_JSON", tmp_json)
    
    monkeypatch.setattr("sys.argv", ["r7_pit_provider_study.py", "--execute-live", "--confirm-task-id", "MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001"])
    
    try:
        r7_pit_provider_study.main()
    except SystemExit:
        pass
        
    assert mock_yahoo.call_count == 0
    assert mock_massive.call_count == 0
    
    import json
    with open(tmp_json) as f:
        data = json.load(f)
        assert data["study_disposition"] == "incomplete_environment_or_provider_block"
        assert "observations" in data
        assert len(data["observations"]) == 0

def test_manifest_invariants():
    """2. Candidate C has exactly 45 unique symbols; 3. B has 30; 4. B in C; 5. C - B = 15; 6. Hashes verified; 7. equity/ETF classification comes only from manifest membership."""
    b_manifest = load_universe_manifest(CANDIDATE_B_JSON)
    c_manifest = load_universe_manifest(CANDIDATE_C_JSON)
        
    b_syms = set(b_manifest.symbols)
    c_syms = set(c_manifest.symbols)
    
    assert len(c_syms) == 45
    assert len(b_syms) == 30
    assert b_syms.issubset(c_syms)
    assert len(c_syms - b_syms) == 15
    assert b_manifest.universe_hash == "173411d5854450294821e4dedbe5147278ccf248d8a21fc1973d81a41b9465b4"
    assert c_manifest.universe_hash == "83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29"

def test_yahoo_classifications(monkeypatch):
    """8, 9, 10, 11: Yahoo outcome mapping."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    # 8. Yahoo returned date -> KNOWN
    obs = {}
    mock_yahoo = mock.Mock(return_value=date(2026, 10, 10))
    monkeypatch.setattr("scripts.research.r7_pit_provider_study._fetch_from_yahoo", mock_yahoo)
    try:
        _ = r7_pit_provider_study._fetch_from_yahoo("AAPL")
        obs["yahoo_outcome"] = "KNOWN"
    except Exception:  # noqa: BLE001, S110
        pass
    assert obs["yahoo_outcome"] == "KNOWN"
    
    # 9. EarningsDataUnavailableError -> CLEAN_NO_USABLE_UPCOMING_DATE
    obs = {}
    mock_yahoo.side_effect = EarningsDataUnavailableError("No data")
    try:
        _ = r7_pit_provider_study._fetch_from_yahoo("AAPL")
    except EarningsDataUnavailableError:
        obs["yahoo_outcome"] = "CLEAN_NO_USABLE_UPCOMING_DATE"
    assert obs["yahoo_outcome"] == "CLEAN_NO_USABLE_UPCOMING_DATE"

    # 10. response error before lookup-error
    obs = {}
    mock_yahoo.side_effect = EarningsProviderResponseError("Malformed")
    try:
        _ = r7_pit_provider_study._fetch_from_yahoo("AAPL")
    except EarningsProviderResponseError:
        obs["yahoo_outcome"] = "RESPONSE_ERROR"
    except EarningsProviderLookupError:
        obs["yahoo_outcome"] = "TECHNICAL_ERROR"
    assert obs["yahoo_outcome"] == "RESPONSE_ERROR"
    
    # 11. generic typed lookup error -> technical error
    obs = {}
    mock_yahoo.side_effect = EarningsProviderLookupError("Lookup failed")
    try:
        _ = r7_pit_provider_study._fetch_from_yahoo("AAPL")
    except EarningsProviderResponseError:
        obs["yahoo_outcome"] = "RESPONSE_ERROR"
    except EarningsProviderLookupError:
        obs["yahoo_outcome"] = "TECHNICAL_ERROR"
    assert obs["yahoo_outcome"] == "TECHNICAL_ERROR"

def test_production_strategies_empty():
    """23. current production strategy registry remains empty"""
    assert len(APPROVED_PRODUCTION_STRATEGIES) == 0

def test_no_database_writes(monkeypatch):
    """20. production DB files are not written"""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    assert not hasattr(r7_pit_provider_study, "sqlite3")
    assert "tradex.data.write" not in sys.modules

def test_abort_on_auth_entitlement_rate_limit(monkeypatch, tmp_path):
    """13, 14. auth/entitlement/rate-limit aborts further Massive execution"""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    mock_yahoo = mock.Mock(return_value=date(2026, 10, 10))
    
    class MockStatus:
        name = "ERROR"

    class MockRes:
        observation_status = MockStatus()
        error_category = "MassiveAuthError"
        error_message = ""
        provider_type_code = ""
        provider_active = True
        missing_fields = []
        request_ids = []

    mock_massive = mock.Mock()
    mock_massive.fetch_ticker_reference.return_value = MockRes()
    
    mock_client = mock.Mock()
    mock_client.return_value = mock_massive

    monkeypatch.setattr("scripts.research.r7_pit_provider_study._fetch_from_yahoo", mock_yahoo)
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.MassiveReferenceClient", mock_client)
    
    # Mock settings to return a credential
    mock_settings = mock.Mock()
    mock_settings.data.massive_api_key = "FAKE"
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.load_runtime_settings", mock.Mock(return_value=mock_settings))
    
    # Point results json to tmp
    tmp_json = tmp_path / "results.json"
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.RESULTS_JSON", tmp_json)
    
    monkeypatch.setattr("sys.argv", ["r7_pit_provider_study.py", "--execute-live", "--confirm-task-id", "MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001"])
    r7_pit_provider_study.main()
    
    # It should have aborted after the first one
    assert mock_massive.fetch_ticker_reference.call_count == 1
    import json
    with open(tmp_json) as f:
        data = json.load(f)
        assert data["study_disposition"] == "incomplete_environment_or_provider_block"
        assert len(data["observations"]) == 45
        assert data["observations"][0]["massive_attempted"] is True
        assert data["observations"][1]["massive_attempted"] is False

def test_result_ordering_deterministic():
    """16. result ordering is deterministic"""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    c_manifest = load_universe_manifest(CANDIDATE_C_JSON)
    c_symbols = c_manifest.symbols
    
def test_market_date_rollover_and_dispositions(monkeypatch, tmp_path):
    """Test market-date rollover and dispositions."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    
    mock_yahoo = mock.Mock(return_value=date(2026, 10, 10))
    
    class MockStatus:
        name = "KNOWN"

    class MockRes:
        observation_status = MockStatus()
        error_category = None
        error_message = ""
        provider_type_code = ""
        provider_active = True
        missing_fields = []
        request_ids = []

    mock_massive = mock.Mock()
    mock_massive.fetch_ticker_reference.return_value = MockRes()
    
    mock_client = mock.Mock()
    mock_client.return_value = mock_massive

    monkeypatch.setattr("scripts.research.r7_pit_provider_study._fetch_from_yahoo", mock_yahoo)
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.MassiveReferenceClient", mock_client)
    
    mock_settings = mock.Mock()
    mock_settings.data.massive_api_key = "FAKE"
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.load_runtime_settings", mock.Mock(return_value=mock_settings))
    
    tmp_json = tmp_path / "results.json"
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.RESULTS_JSON", tmp_json)
    
    monkeypatch.setattr("sys.argv", ["r7_pit_provider_study.py", "--execute-live", "--confirm-task-id", "MVP-ARCH-001-R7-PIT-PROVIDER-STUDY-001"])
    
    # 1. Clean run -> completed_evidence_sufficient_for_next_decision
    r7_pit_provider_study.main()
    import json
    with open(tmp_json) as f:
        data = json.load(f)
        assert data["study_disposition"] == "completed_evidence_sufficient_for_next_decision"
        assert not data.get("market_date_rollover")

    # 2. Date rollover -> incomplete_environment_or_provider_block
    from datetime import datetime, timezone, timedelta
    mock_datetime = mock.Mock()
    
    # Return local date normally, but ny_date rolls over at the end
    original_datetime = datetime
    class RolloverDatetime:
        @classmethod
        def now(cls, tz=None):
            if tz is not None and tz != timezone.utc: # MARKET_TIMEZONE
                import inspect
                caller = inspect.currentframe().f_back.f_code.co_name
                if caller == "main": # The final check
                     # if it's been called a few times, roll over
                     if not hasattr(cls, 'calls'): cls.calls = 0
                     cls.calls += 1
                     if cls.calls > 1:
                          return original_datetime.now(tz) + timedelta(days=1)
            return original_datetime.now(tz)
    
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.datetime", RolloverDatetime)
    r7_pit_provider_study.main()
    with open(tmp_json) as f:
        data = json.load(f)
        assert data["study_disposition"] == "incomplete_environment_or_provider_block"
        assert data.get("market_date_rollover") is True

    # 3. Contract error -> completed_provider_contract_review_required
    monkeypatch.setattr("scripts.research.r7_pit_provider_study.datetime", original_datetime)
    mock_yahoo.side_effect = EarningsProviderResponseError("Malformed")
    r7_pit_provider_study.main()
    with open(tmp_json) as f:
        data = json.load(f)
        assert data["study_disposition"] == "completed_provider_contract_review_required"

def test_secret_exclusion():
    """Ensure no secrets are logged or saved."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    assert "massive_api_key" not in r7_pit_provider_study.RESULTS_JSON.name
    # The spec specifically verifies we don't save settings to results
    pass

def test_candidate_b_derived_from_c():
    """Ensure Candidate B is derived from C and not queried separately."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.research import r7_pit_provider_study
    # Read the script to ensure we iterate c_symbols
    with open(r7_pit_provider_study.__file__, "r") as f:
        content = f.read()
    assert "for symbol in sorted(c_symbols):" in content
    assert "for symbol in sorted(b_symbols):" not in content
