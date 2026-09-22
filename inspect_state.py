#!/usr/bin/env python3
from board_core.cli import inspect_main
from board_core.inspect import run_payload


def build_run_context(workspace, feature, config):
    """Adapter used by the original knowledge renderer to resolve node policies."""
    return run_payload(workspace, feature, config), config

if __name__ == "__main__":
    raise SystemExit(inspect_main())
