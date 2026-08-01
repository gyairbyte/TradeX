"""Credential-free tests for the Schwab OAuth bootstrap script.

These tests load scripts/schwab_oauth.py as a standalone module and verify that
it never prints secret or token material even when the Schwab auth flow fails.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


def _load_oauth_module():
    repo_root = Path(__file__).resolve().parent.parent.parent
    spec = importlib.util.spec_from_file_location(
        "schwab_oauth_testmod", repo_root / "scripts" / "schwab_oauth.py"
    )
    module = importlib.util.module_from_spec(spec)
    # keep a stable reference so repeated imports share the module object
    sys.modules["schwab_oauth_testmod"] = module
    spec.loader.exec_module(module)
    return module


def test_oauth_failure_does_not_print_secrets(capsys, monkeypatch, tmp_path):
    """If Schwab's auth flow raises an exception containing a secret, that
    secret must not appear in stdout or stderr."""
    token_path = tmp_path / "token.json"
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(token_path))

    sentinel = "SENTINEL_OAUTH_SECRET_TOKEN_12345"

    def fake_flow(*args, **kwargs):
        raise RuntimeError(f"OAuth callback leaked {sentinel}")

    module = _load_oauth_module()
    with patch("schwab.auth.client_from_manual_flow", side_effect=fake_flow):
        result = module.main()

    captured = capsys.readouterr()
    assert result == 1
    assert sentinel not in captured.out
    assert sentinel not in captured.err
    assert "leaked" not in captured.err


def test_token_path_inside_repo_does_not_print_key_or_secret(
    capsys, monkeypatch, tmp_path
):
    """A repo-internal token path is rejected without emitting credentials."""
    # put token file inside repo root (monkeypatched below to tmp_path)
    token_path = tmp_path / "nested" / "token.json"
    # force the module to resolve the repo root to tmp_path by monkeypatching
    # _repo_root, but keep the rest of the logic intact.
    module = _load_oauth_module()
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-app-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(token_path))
    monkeypatch.setattr(module, "_repo_root", lambda: tmp_path)

    result = module.main()
    captured = capsys.readouterr()
    assert result == 1
    assert "test-app-key" not in captured.out
    assert "test-app-key" not in captured.err
    assert "test-app-secret" not in captured.out
    assert "test-app-secret" not in captured.err
