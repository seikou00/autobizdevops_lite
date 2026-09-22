#!/usr/bin/env python3
"""Compatibility entrypoint for existing update_checkpoint callers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board_core.cli import update_main

if __name__ == "__main__":
    raise SystemExit(update_main())
