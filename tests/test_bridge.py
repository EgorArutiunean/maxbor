import logging
import unittest
from pathlib import Path

from bridge import BridgeService
from config import AppConfig
from health import HealthState


class FakeTelegramClient:
    def __init__(self) -> None:
        self.download_calls: list[str] = []

    def download_file(self, file_id: str) -> tuple[bytes, str, str | None, int | None]:
        self.download_calls.append(file_id)
        return b"blob", f"{file_id}.bin", "application/octet-stream", 128


class FakeMaxClient:
    def __init__(self) -> None:
        self.upload_calls: list[tuple[str, str]] = []
        self.sent_messages: list[dict] = []

    def upload_file(
        self,
        kind: str,
        filename: str,
        blob: bytes,
        mime_type: str | None,
    ) -> dict:
        self.upload_calls.append((kind, filename))
        return {"type": kind, "payload": {"token": filename}}

    def send_message(self, text: str | None, attachments: list[dict] | None = None) -> dict:
        self.sent_messages.append({"text": text, "attachments": attachments})
        return {"message": {"mid": "mid-1"}}

    def get_target_recipient(self) -> dict[str, int]:
        return {"chat_id": 777}


class BridgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        config = AppConfig(
            telegram_bot_token="tg-token",
            max_bot_token="max-token",
            source_tg_chat="@source_channel",
            target_max_chat="@target_chat",
            instance_name="maxbor",
            poll_timeout=30,
            media_group_wait_sec=1.5,
            max_attachment_size_bytes=1024,
            healthcheck_enabled=True,
            healthcheck_host="127.0.0.1",
            healthcheck_port=8080,
            healthcheck_stale_after_sec=120,
            state_file=Path("state.json"),
            log_level="INFO",
        )
        self.telegram = FakeTelegramClient()
        self.max_client = FakeMaxClient()
        self.health_state = HealthState(stale_after_sec=120)
        self.service = BridgeService(
            config=config,
            telegram=self.telegram,
            max_client=self.max_client,
            logger=logging.getLogger("bridge-test"),
            health_state=self.health_state,
        )

    def test_post_matches_source_by_username(self) -> None:
        post = {"chat": {"id": -1001, "username": "Source_Channel"}}

        self.assertTrue(self.service.post_matches_source(post))

    def test_get_posts_text_prefers_first_non_empty_text(self) -> None:
        posts = [
            {"text": "", "caption": ""},
            {"caption": "caption text"},
            {"text": "later text"},
        ]

        self.assertEqual(self.service.get_posts_text(posts), "caption text")

    def test_extract_attachments_from_post_maps_supported_types(self) -> None:
        post = {
            "photo": [{"file_id": "photo-small"}, {"file_id": "photo-large"}],
            "document": {"file_id": "document-id", "file_name": "report.pdf"},
            "video": {"file_id": "video-id", "mime_type": "video/mp4"},
            "audio": {"file_id": "audio-id", "file_name": "track.mp3"},
            "voice": {"file_id": "voice-id", "mime_type": "audio/ogg"},
            "animation": {"file_id": "animation-id", "mime_type": "video/mp4"},
        }

        attachments = self.service.extract_attachments_from_post(post)

        self.assertEqual(len(attachments), 6)
        self.assertEqual(
            self.telegram.download_calls,
            [
                "photo-large",
                "document-id",
                "video-id",
                "audio-id",
                "voice-id",
                "animation-id",
            ],
        )
        self.assertEqual(
            self.max_client.upload_calls,
            [
                ("image", "photo-large.bin"),
                ("file", "report.pdf"),
                ("video", "video-id.bin"),
                ("audio", "track.mp3"),
                ("audio", "voice-id.bin"),
                ("video", "animation-id.bin"),
            ],
        )

    def test_flush_ready_media_groups_sends_sorted_group(self) -> None:
        captured_posts: list[list[int]] = []

        def capture(posts: list[dict]) -> None:
            captured_posts.append([post["message_id"] for post in posts])

        self.service.handle_channel_posts = capture  # type: ignore[method-assign]
        pending_media_groups = {
            "album-1": {
                "posts": [
                    {"message_id": 3},
                    {"message_id": 1},
                    {"message_id": 2},
                ],
                "updated_at": 0.0,
            }
        }

        self.service.flush_ready_media_groups(pending_media_groups, force=True)

        self.assertEqual(captured_posts, [[1, 2, 3]])
        self.assertEqual(pending_media_groups, {})
        self.assertEqual(self.service.stats.media_groups_flushed, 1)

    def test_extract_attachments_rejects_oversized_file(self) -> None:
        self.telegram.download_file = lambda file_id: (  # type: ignore[method-assign]
            b"blob",
            "huge.bin",
            "application/octet-stream",
            5000,
        )
        post = {
            "message_id": 77,
            "document": {"file_id": "document-id", "file_name": "report.pdf"},
        }

        with self.assertRaisesRegex(RuntimeError, "Attachment exceeds configured size limit"):
            self.service.extract_attachments_from_post(post)

    def test_process_update_returns_next_offset_for_non_channel_updates(self) -> None:
        next_offset = self.service.process_update({"update_id": 99}, {})

        self.assertEqual(next_offset, 100)

    def test_process_update_buffers_media_group_without_sending(self) -> None:
        pending_media_groups: dict[str, dict] = {}
        update = {
            "update_id": 10,
            "channel_post": {
                "message_id": 5,
                "media_group_id": "album-1",
                "chat": {"id": -1001, "username": "source_channel"},
            },
        }

        next_offset = self.service.process_update(update, pending_media_groups)

        self.assertEqual(next_offset, 11)
        self.assertIn("album-1", pending_media_groups)
        self.assertEqual(len(pending_media_groups["album-1"]["posts"]), 1)
        self.assertEqual(self.service.stats.updates_seen, 1)
        self.assertEqual(self.service.stats.channel_posts_seen, 1)
        self.assertEqual(self.service.stats.media_groups_buffered, 1)

    def test_handle_channel_posts_counts_filtered_posts(self) -> None:
        post = {"message_id": 9, "chat": {"id": -2002, "username": "other_channel"}}

        self.service.handle_channel_posts([post])

        self.assertEqual(self.service.stats.posts_filtered_out, 1)
        self.assertEqual(self.max_client.sent_messages, [])

    def test_handle_channel_posts_counts_relayed_posts_and_attachments(self) -> None:
        post = {
            "message_id": 10,
            "chat": {"id": -1001, "username": "source_channel"},
            "text": "hello",
            "document": {"file_id": "document-id", "file_name": "report.pdf"},
        }

        self.service.handle_channel_posts([post])

        self.assertEqual(self.service.stats.posts_relayed, 1)
        self.assertEqual(self.service.stats.attachments_uploaded, 1)

    def test_request_shutdown_sets_stop_event_and_health_state(self) -> None:
        self.service.request_shutdown("test stop")

        self.assertTrue(self.service.stop_event.is_set())
        self.assertTrue(self.health_state.snapshot()["shutting_down"])
