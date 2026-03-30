import unittest

from bridge import normalize_tg_chat_target
from max_client import normalize_max_target


class NormalizeTelegramTargetTests(unittest.TestCase):
    def test_accepts_numeric_chat_id(self) -> None:
        self.assertEqual(normalize_tg_chat_target("-100123456"), "-100123456")

    def test_accepts_username(self) -> None:
        self.assertEqual(normalize_tg_chat_target("@Example_Channel"), "example_channel")

    def test_accepts_link(self) -> None:
        self.assertEqual(
            normalize_tg_chat_target("https://t.me/Example_Channel/"),
            "example_channel",
        )

    def test_rejects_empty_value(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "SOURCE_TG_CHAT is empty"):
            normalize_tg_chat_target("   ")


class NormalizeMaxTargetTests(unittest.TestCase):
    def test_accepts_numeric_chat_id(self) -> None:
        self.assertEqual(normalize_max_target("12345"), "12345")

    def test_accepts_username(self) -> None:
        self.assertEqual(normalize_max_target("@ExampleChat"), "examplechat")

    def test_accepts_link(self) -> None:
        self.assertEqual(
            normalize_max_target("https://max.ru/ExampleChat/"),
            "examplechat",
        )

    def test_rejects_empty_value(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "TARGET_MAX_CHAT is empty"):
            normalize_max_target(" ")
