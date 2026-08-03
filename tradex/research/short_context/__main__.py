"""Entry point for ``python -m tradex.research.short_context``."""
from __future__ import annotations

import sys

from tradex.research.short_context.cli import main

if __name__ == "__main__":
    sys.exit(main())
