#!/usr/bin/env python3
"""Compatibility wrapper for `python3 enrich.py`."""

from roqet.enrich import main


if __name__ == "__main__":
    raise SystemExit(main())
