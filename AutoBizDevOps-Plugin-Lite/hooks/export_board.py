#!/usr/bin/env python3
"""Validate the canonical config and export board.json for host integration."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board_core.cli import execute
from board_core.runtime import CONFIG_PATH, ROOT, atomic_write, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查导出副本，无写入")
    args = parser.parse_args()

    def export():
        load_config()
        source = CONFIG_PATH.read_text(encoding="utf-8")
        target = ROOT / "board.json"
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != source:
                raise ValueError("board.json 与配置源不一致，请执行 hooks/export_board.py")
        else:
            atomic_write(target, source)
        return {"ok": True, "boardPath": str(target)}
    return execute(export)


if __name__ == "__main__":
    raise SystemExit(main())
