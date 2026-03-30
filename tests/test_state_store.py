import logging
import unittest
from pathlib import Path
from uuid import uuid4

from state_store import load_state, save_state


class StateStoreTests(unittest.TestCase):
    def make_workspace_path(self, suffix: str) -> Path:
        path = Path("tests_artifacts") / f"{uuid4().hex}-{suffix}"
        self.addCleanup(self.cleanup_path, path)
        return path

    def cleanup_path(self, path: Path) -> None:
        if path.is_file():
            path.unlink(missing_ok=True)
            return

        if path.exists():
            for item in sorted(path.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    item.rmdir()
            path.rmdir()

    def test_load_state_returns_default_when_file_is_missing(self) -> None:
        state_file = self.make_workspace_path("missing.json")

        state = load_state(state_file)

        self.assertEqual(state, {"tg_offset": None})

    def test_save_state_and_load_state_roundtrip(self) -> None:
        state_file = self.make_workspace_path("nested") / "state.json"
        payload = {"tg_offset": 42}

        save_state(state_file, payload)
        state = load_state(state_file)

        self.assertEqual(state, payload)
        self.assertFalse(state_file.with_name("state.json.tmp").exists())

    def test_load_state_returns_default_for_invalid_json(self) -> None:
        state_file = self.make_workspace_path("broken") / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{broken", encoding="utf-8")
        logger = logging.getLogger("state-store-test")

        with self.assertLogs(logger, level="WARNING") as logs:
            state = load_state(state_file, logger)

        self.assertEqual(state, {"tg_offset": None})
        self.assertIn("starting with empty state", logs.output[0])
