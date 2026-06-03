#!/usr/bin/env python3
"""Compatibility wrapper for `python3 validate.py`."""

from roqet.validate import main


if __name__ == "__main__":
    raise SystemExit(main())
