"""Read-only local smoke test for the Schwab market-data provider.

This script requires a valid Schwab OAuth token and market-data app credentials
configured in a local .env file. It only calls Market Data endpoints; it never
accesses account balances, positions, orders, or any order-related endpoints.

Run locally after generating a token with scripts/schwab_oauth.py:
    uv run --extra schwab python scripts/schwab_smoke_test.py

Exit code:
    0 if all timeframes pass the provider contract.
    1 if any fetch fails or the contract is violated.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> Path | None:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    load_dotenv(env_path)
    load_dotenv()
    return env_path


def _require_env() -> tuple[str, str, str]:
    env_path = _load_env()
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
        sys.exit(1)

    if not os.path.exists(token_path):
        print(
            f"error: Schwab OAuth token not found at {token_path}. "
            "Run scripts/schwab_oauth.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    return key, secret, token_path


def _validate_contract(df) -> tuple[bool, list[str]]:
    """Return (ok, errors) for the canonical OHLCV provider contract."""
    import pandas as pd

    errors: list[str] = []
    if not isinstance(df, pd.DataFrame):
        errors.append("result is not a pandas DataFrame")
        return False, errors

    if list(df.columns) != ["open", "high", "low", "close", "volume"]:
        errors.append(f"unexpected columns: {list(df.columns)}")

    if not df.empty:
        if df.index.name != "datetime":
            errors.append(f"index name is {df.index.name!r}, expected 'datetime'")
        if df.index.tz is None:
            errors.append("index is not timezone-aware")
        if not df.index.is_monotonic_increasing:
            errors.append("index is not sorted oldest-to-newest")
        if not df.index.is_unique:
            errors.append("index contains duplicate timestamps")
        for col in ("open", "high", "low", "close", "volume"):
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append(f"column {col!r} is not numeric")

    return not errors, errors


def _report(symbol: str, timeframe: str, df) -> None:
    """Print a safe, non-secret summary of the result."""
    print("provider:    schwab")
    print(f"symbol:      {symbol}")
    print(f"timeframe:   {timeframe}")
    print(f"rows:        {len(df)}")
    if not df.empty:
        print(f"columns:     {list(df.columns)}")
        print(f"first:       {df.index.min()}")
        print(f"last:        {df.index.max()}")
        print(f"tz:          {df.index.tz}")
    print()


def main() -> int:
    _require_env()

    # Import only after environment is confirmed. This keeps the script runnable
    # only when schwab-py is installed.
    from tradex.data.fetcher import fetch

    symbol = os.environ.get("SCHWAB_SMOKE_SYMBOL", "SPY").strip().upper()
    failures = 0

    for timeframe in ("intraday", "short", "long"):
        try:
            df = fetch(symbol, timeframe, provider="schwab")
        except Exception as e:  # noqa: BLE001
            print(
                f"error fetching {symbol} {timeframe}: {e}",
                file=sys.stderr,
            )
            failures += 1
            continue

        _report(symbol, timeframe, df)
        ok, errors = _validate_contract(df)
        if not ok:
            for err in errors:
                print(f"contract violation: {err}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} smoke-test failure(s)", file=sys.stderr)
        return 1

    print("Schwab smoke test passed for all timeframes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
