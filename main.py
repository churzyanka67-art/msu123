"""Deployment entrypoint; run from the repository root with `python main.py`."""

import sys

from app.bot import main

if __name__ == "__main__":
    sys.exit(main())
