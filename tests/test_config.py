import os
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class LoadConfigTests(unittest.TestCase):
    def test_load_config_uses_required_values_and_defaults(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "tg-token",
            "MAX_BOT_TOKEN": "max-token",
            "SOURCE_TG_CHAT": "@source_channel",
            "TARGET_MAX_CHAT": "@target_chat",
        }

        with patch("config.load_dotenv"):
            with patch.dict(os.environ, env, clear=True):
                loaded = config.load_config()

        self.assertEqual(loaded.telegram_bot_token, "tg-token")
        self.assertEqual(loaded.max_bot_token, "max-token")
        self.assertEqual(loaded.source_tg_chat, "@source_channel")
        self.assertEqual(loaded.target_max_chat, "@target_chat")
        self.assertEqual(loaded.instance_name, "maxbor")
        self.assertEqual(loaded.poll_timeout, 30)
        self.assertEqual(loaded.media_group_wait_sec, 1.5)
        self.assertEqual(loaded.max_attachment_size_bytes, 52428800)
        self.assertTrue(loaded.healthcheck_enabled)
        self.assertEqual(loaded.healthcheck_host, "0.0.0.0")
        self.assertEqual(loaded.healthcheck_port, 8080)
        self.assertEqual(loaded.healthcheck_stale_after_sec, 120)
        self.assertEqual(loaded.state_file, Path("state.json"))
        self.assertEqual(loaded.log_level, "INFO")

    def test_load_config_uses_overrides(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "tg-token",
            "MAX_BOT_TOKEN": "max-token",
            "SOURCE_TG_CHAT": "-100123",
            "TARGET_MAX_CHAT": "https://max.ru/example",
            "INSTANCE_NAME": "bridge-a",
            "POLL_TIMEOUT": "45",
            "MEDIA_GROUP_WAIT_SEC": "2.75",
            "MAX_ATTACHMENT_SIZE_BYTES": "1048576",
            "HEALTHCHECK_ENABLED": "false",
            "HEALTHCHECK_HOST": "127.0.0.1",
            "HEALTHCHECK_PORT": "9090",
            "HEALTHCHECK_STALE_AFTER_SEC": "45",
            "STATE_FILE": "/tmp/custom-state.json",
            "LOG_LEVEL": "debug",
        }

        with patch("config.load_dotenv"):
            with patch.dict(os.environ, env, clear=True):
                loaded = config.load_config()

        self.assertEqual(loaded.instance_name, "bridge-a")
        self.assertEqual(loaded.poll_timeout, 45)
        self.assertEqual(loaded.media_group_wait_sec, 2.75)
        self.assertEqual(loaded.max_attachment_size_bytes, 1048576)
        self.assertFalse(loaded.healthcheck_enabled)
        self.assertEqual(loaded.healthcheck_host, "127.0.0.1")
        self.assertEqual(loaded.healthcheck_port, 9090)
        self.assertEqual(loaded.healthcheck_stale_after_sec, 45)
        self.assertEqual(loaded.state_file, Path("/tmp/custom-state.json"))
        self.assertEqual(loaded.log_level, "DEBUG")

    def test_load_config_rejects_invalid_poll_timeout(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "tg-token",
            "MAX_BOT_TOKEN": "max-token",
            "SOURCE_TG_CHAT": "@source_channel",
            "TARGET_MAX_CHAT": "@target_chat",
            "POLL_TIMEOUT": "0",
        }

        with patch("config.load_dotenv"):
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(RuntimeError, "POLL_TIMEOUT must be greater than 0"):
                    config.load_config()
