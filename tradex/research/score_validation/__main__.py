"""CLI entry point for `python -m tradex.research.score_validation`."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
