"""Entry point for `python -m tradex.research.intraday_data_probe`."""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
