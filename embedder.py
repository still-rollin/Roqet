#!/usr/bin/env python3
"""Compatibility wrapper for `python3 embedder.py`."""

from roqet.embedder import main


if __name__ == "__main__":
    raise SystemExit(main())
