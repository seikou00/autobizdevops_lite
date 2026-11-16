"""Read the board configuration for the fullstack knowledge sync hook."""

import json
from pathlib import Path


class BoardConfigError(Exception):
    """Raised when the board configuration cannot be read."""


def load_board_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BoardConfigError(
            f"invalid board_config.json: {path}:{exc.lineno}:{exc.colno}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise BoardConfigError(str(exc)) from exc
