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
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    load_dotenv(env_path)

    key = os.environ.get("SCHWAB_APP_KEY", "").strip()
    secret = os.environ.get("SCHWAB_APP_SECRET", "").strip()
    token_path = os.path.expanduser(
        os.environ.get("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json")
    )

    if not key or not secret:
        print(
            f"error: SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in {env_path}",
            file=sys.stderr,
        )
        return 1

    try:
        from schwab.auth import client_from_manual_flow
    except ImportError:
        print(
            "error: schwab-py not installed. Run: uv pip install -e \".[schwab]\"",
            file=sys.stderr,
        )
        return 1

    print(f"[schwab-oauth] token will be written to: {token_path}")
    print(f"[schwab-oauth] callback URL:             https://127.0.0.1")
    print()

    client_from_manual_flow(
        api_key=key,
        app_secret=secret,
        callback_url="https://127.0.0.1",
        token_path=token_path,
    )

    print()
    print(f"[schwab-oauth] success — token saved to {token_path}")
    print("[schwab-oauth] next: switch DATA_PROVIDER=schwab in .env to use it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
