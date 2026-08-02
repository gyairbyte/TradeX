"""Allow ``python -m tradex.backtest``."""
from __future__ import annotations

import sys

from tradex.backtest.cli import main

if __name__ == "__main__":
    sys.exit(main())
