"""Executable entrypoint for python -m tradex.research.daytrade_momentum."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
