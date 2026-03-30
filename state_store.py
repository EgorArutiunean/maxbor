import json
import logging
import os
from pathlib import Path
from typing import Any


def load_state(state_file: Path, logger: logging.Logger | None = None) -> dict[str, Any]:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            if logger:
                logger.warning("Failed to read %s, starting with empty state", state_file)
    return {"tg_offset": None}


def save_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_state_file = state_file.with_name(f"{state_file.name}.tmp")
    temp_state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_state_file, state_file)
