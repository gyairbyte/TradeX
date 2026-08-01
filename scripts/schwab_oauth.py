"""One-time OAuth bootstrap for the Schwab data provider.

Run from an interactive terminal:
    .venv/bin/python scripts/schwab_oauth.py

Steps:
1. Reads SCHWAB_APP_KEY / SCHWAB_APP_SECRET / SCHWAB_TOKEN_PATH from .env.
2. Prints an authorization URL — open it in any browser.
3. Log in with your Schwab brokerage credentials, click Allow.
4. Browser will redirect to https://127.0.0.1/?code=... and show a connection
   error (expected — no local server is listening). Copy the ENTIRE URL from
   the address bar and paste it at the prompt.
5. Token is written to SCHWAB_TOKEN_PATH (default ~/.tradex_schwab_token.json).

Token is good for ~7 days; refresh happens automatically for ~90 days; after
that, re-run this script.

Safety notes:
- Never commit .env or the token file.
- The token path must be outside this repository.
- The script refuses to overwrite an existing token unless confirmed.
- The token file is created with 0o600 permissions where supported.
- No secrets, tokens, or credentials are printed.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path | None:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").is_dir():
            return parent
    return None


def _assert_token_path_outside_repo(token_path: Path) -> None:
    repo_root = _repo_root()
    if repo_root is None:
        return
    resolved = token_path.expanduser().resolve()
    if resolved.is_relative_to(repo_root):
        raise ValueError(
            f"SCHWAB_TOKEN_PATH must not be inside the repository: {resolved}\n"
            f"Set it to a location outside {repo_root}, "
            "e.g. ~/.tradex_schwab_token.json"
        )


def _set_secure_permissions(path: Path) -> None:
    """Set restrictive permissions on the token file where the OS supports it."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except (OSError, NotImplementedError):
        pass


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    load_dotenv(env_path)
    load_dotenv()

    key = os.environ.get("SCHWAB_APP_KEY", "").strip()
    secret = os.environ.get("SCHWAB_APP_SECRET", "").strip()
    token_path = Path(
        os.path.expanduser(
            os.environ.get("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json")
        )
    )

    if not key or not secret:
        print(
            f"error: SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in {env_path}",
            file=sys.stderr,
        )
        return 1

    try:
        _assert_token_path_outside_repo(token_path)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        from schwab.auth import client_from_manual_flow
    except ImportError:
        print(
            "error: schwab-py not installed. Run: uv pip install -e \".[schwab]\"",
            file=sys.stderr,
        )
        return 1

    if token_path.exists():
        print(f"warning: token file already exists: {token_path}")
        answer = input("Overwrite? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted. Existing token kept.")
            return 0

    token_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[schwab-oauth] token will be written to: {token_path}")
    print("[schwab-oauth] callback URL:             https://127.0.0.1")
    print()

    try:
        client_from_manual_flow(
            api_key=key,
            app_secret=secret,
            callback_url="https://127.0.0.1",
            token_path=token_path,
        )
    except Exception as e:  # noqa: BLE001
        print(f"error: OAuth flow failed: {e}", file=sys.stderr)
        return 1

    _set_secure_permissions(token_path)

    print()
    print(f"[schwab-oauth] success — token saved to {token_path}")
    print("[schwab-oauth] next: switch DATA_PROVIDER=schwab in .env to use it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
