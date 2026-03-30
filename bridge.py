import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from config import AppConfig
from health import HealthState
from max_client import MaxClient
from state_store import load_state, save_state
from telegram_client import TelegramClient


def normalize_tg_chat_target(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise RuntimeError("SOURCE_TG_CHAT is empty")

    if raw.lstrip("-").isdigit():
        return raw

    if raw.startswith("@"):
        return raw[1:].lower()

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        path = parsed.path.strip("/")
        if not path:
            raise RuntimeError(f"Invalid Telegram link: {raw}")
        return path.lower()

    return raw.strip("/").lower()


@dataclass
class BridgeStats:
    polls: int = 0
    updates_seen: int = 0
    channel_posts_seen: int = 0
    posts_filtered_out: int = 0
    media_groups_buffered: int = 0
    media_groups_flushed: int = 0
    posts_relayed: int = 0
    attachments_uploaded: int = 0
    relay_errors: int = 0


class BridgeService:
    def __init__(
        self,
        config: AppConfig,
        telegram: TelegramClient,
        max_client: MaxClient,
        logger: logging.Logger,
        health_state: HealthState | None = None,
    ) -> None:
        self.config = config
        self.telegram = telegram
        self.max_client = max_client
        self.logger = logger
        self.stats = BridgeStats()
        self.health_state = health_state
        self.stop_event = threading.Event()

    def request_shutdown(self, reason: str) -> None:
        if self.stop_event.is_set():
            return

        self.logger.info("[%s] Shutdown requested: %s", self.config.instance_name, reason)
        self.stop_event.set()
        if self.health_state is not None:
            self.health_state.mark_stopping()
        telegram_close = getattr(self.telegram, "close", None)
        if callable(telegram_close):
            telegram_close()
        max_close = getattr(self.max_client, "close", None)
        if callable(max_close):
            max_close()

    def post_matches_source(self, post: dict[str, Any]) -> bool:
        chat = post["chat"]
        source_target = normalize_tg_chat_target(self.config.source_tg_chat)

        if source_target.lstrip("-").isdigit():
            return int(chat["id"]) == int(source_target)

        username = (chat.get("username") or "").strip().lower()
        return username == source_target

    def get_post_text(self, post: dict[str, Any]) -> str:
        return (post.get("text") or post.get("caption") or "").strip()

    def ensure_attachment_size(
        self,
        file_size: int | None,
        *,
        kind: str,
        filename: str,
        post: dict[str, Any],
    ) -> None:
        if file_size is None:
            return

        if file_size > self.config.max_attachment_size_bytes:
            raise RuntimeError(
                "Attachment exceeds configured size limit: "
                f"kind={kind}, filename={filename}, size={file_size}, "
                f"limit={self.config.max_attachment_size_bytes}, "
                f"tg_message_id={post.get('message_id')}"
            )

    def extract_attachments_from_post(self, post: dict[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []

        if post.get("photo"):
            photo = post["photo"][-1]
            blob, filename, mime_type, file_size = self.telegram.download_file(photo["file_id"])
            self.ensure_attachment_size(
                file_size,
                kind="image",
                filename=filename or "photo.jpg",
                post=post,
            )
            attachments.append(
                self.max_client.upload_file("image", filename or "photo.jpg", blob, mime_type)
            )

        if post.get("document"):
            doc = post["document"]
            blob, filename, mime_type, file_size = self.telegram.download_file(doc["file_id"])
            resolved_filename = doc.get("file_name") or filename or "document.bin"
            self.ensure_attachment_size(
                file_size,
                kind="file",
                filename=resolved_filename,
                post=post,
            )
            attachments.append(
                self.max_client.upload_file(
                    "file",
                    resolved_filename,
                    blob,
                    doc.get("mime_type") or mime_type,
                )
            )

        if post.get("video"):
            video = post["video"]
            blob, filename, mime_type, file_size = self.telegram.download_file(video["file_id"])
            resolved_filename = filename or "video.mp4"
            self.ensure_attachment_size(
                file_size,
                kind="video",
                filename=resolved_filename,
                post=post,
            )
            attachments.append(
                self.max_client.upload_file(
                    "video",
                    resolved_filename,
                    blob,
                    video.get("mime_type") or mime_type,
                )
            )

        if post.get("audio"):
            audio = post["audio"]
            blob, filename, mime_type, file_size = self.telegram.download_file(audio["file_id"])
            resolved_filename = audio.get("file_name") or filename or "audio.mp3"
            self.ensure_attachment_size(
                file_size,
                kind="audio",
                filename=resolved_filename,
                post=post,
            )
            attachments.append(
                self.max_client.upload_file(
                    "audio",
                    resolved_filename,
                    blob,
                    audio.get("mime_type") or mime_type,
                )
            )

        if post.get("voice"):
            voice = post["voice"]
            blob, filename, mime_type, file_size = self.telegram.download_file(voice["file_id"])
            resolved_filename = filename or "voice.ogg"
            self.ensure_attachment_size(
                file_size,
                kind="audio",
                filename=resolved_filename,
                post=post,
            )
            attachments.append(
                self.max_client.upload_file(
                    "audio",
                    resolved_filename,
                    blob,
                    voice.get("mime_type") or mime_type,
                )
            )

        if post.get("animation"):
            animation = post["animation"]
            blob, filename, mime_type, file_size = self.telegram.download_file(animation["file_id"])
            resolved_filename = filename or "animation.mp4"
            self.ensure_attachment_size(
                file_size,
                kind="video",
                filename=resolved_filename,
                post=post,
            )
            attachments.append(
                self.max_client.upload_file(
                    "video",
                    resolved_filename,
                    blob,
                    animation.get("mime_type") or mime_type,
                )
            )

        return attachments

    def extract_attachments_from_posts(self, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []

        for post in posts:
            attachments.extend(self.extract_attachments_from_post(post))

        return attachments

    def get_posts_text(self, posts: list[dict[str, Any]]) -> str:
        for post in posts:
            text = self.get_post_text(post)
            if text:
                return text
        return ""

    def handle_channel_posts(self, posts: list[dict[str, Any]]) -> None:
        first_post = posts[0]
        chat_id = int(first_post["chat"]["id"])

        if not self.post_matches_source(first_post):
            self.stats.posts_filtered_out += len(posts)
            self.logger.info(
                "[%s] Post skipped by source filter: tg_chat=%s tg_msg=%s media_group=%s items=%s expected_source=%s",
                self.config.instance_name,
                chat_id,
                first_post.get("message_id"),
                first_post.get("media_group_id"),
                len(posts),
                self.config.source_tg_chat,
            )
            return

        text = self.get_posts_text(posts)
        attachments = self.extract_attachments_from_posts(posts)
        self.stats.attachments_uploaded += len(attachments)

        if not text and not attachments:
            text = "[Post without supported content]"

        try:
            result = self.max_client.send_message(text=text, attachments=attachments)
        except Exception as exc:
            self.stats.relay_errors += 1
            raise RuntimeError(
                "Failed to relay Telegram post to MAX: "
                f"tg_chat={chat_id}, tg_message_id={first_post.get('message_id')}, "
                f"media_group_id={first_post.get('media_group_id')}, error={exc}"
            ) from exc
        self.stats.posts_relayed += 1
        max_message = result.get("message", {})
        self.logger.info(
            "[%s] Repost complete: tg_chat=%s tg_msg=%s media_group=%s items=%s attachments=%s -> max_chat=%s max_mid=%s",
            self.config.instance_name,
            chat_id,
            first_post.get("message_id"),
            first_post.get("media_group_id"),
            len(posts),
            len(attachments),
            self.max_client.get_target_recipient().get("chat_id"),
            max_message.get("mid"),
        )

    def flush_ready_media_groups(
        self,
        pending_media_groups: dict[str, dict[str, Any]],
        *,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        ready_group_ids: list[str] = []

        for media_group_id, group in pending_media_groups.items():
            if force or now - group["updated_at"] >= self.config.media_group_wait_sec:
                ready_group_ids.append(media_group_id)

        for media_group_id in ready_group_ids:
            group = pending_media_groups.pop(media_group_id)
            posts = sorted(group["posts"], key=lambda item: item.get("message_id", 0))
            self.stats.media_groups_flushed += 1
            self.handle_channel_posts(posts)

    def process_update(
        self,
        update: dict[str, Any],
        pending_media_groups: dict[str, dict[str, Any]],
    ) -> int:
        self.stats.updates_seen += 1
        next_offset = update["update_id"] + 1

        if "channel_post" not in update:
            return next_offset

        self.stats.channel_posts_seen += 1
        post = update["channel_post"]
        media_group_id = post.get("media_group_id")

        if media_group_id:
            is_new_group = media_group_id not in pending_media_groups
            group = pending_media_groups.setdefault(
                media_group_id,
                {"posts": [], "updated_at": time.monotonic()},
            )
            group["posts"].append(post)
            group["updated_at"] = time.monotonic()
            if is_new_group:
                self.stats.media_groups_buffered += 1
            return next_offset

        self.handle_channel_posts([post])
        return next_offset

    def log_cycle_summary(
        self,
        pending_media_groups: dict[str, dict[str, Any]],
        *,
        current_offset: int | None,
    ) -> None:
        self.logger.info(
            "[%s] Cycle summary: polls=%s updates_seen=%s channel_posts_seen=%s relayed=%s filtered=%s relay_errors=%s attachments_uploaded=%s media_groups_buffered=%s media_groups_flushed=%s pending_media_groups=%s current_offset=%s",
            self.config.instance_name,
            self.stats.polls,
            self.stats.updates_seen,
            self.stats.channel_posts_seen,
            self.stats.posts_relayed,
            self.stats.posts_filtered_out,
            self.stats.relay_errors,
            self.stats.attachments_uploaded,
            self.stats.media_groups_buffered,
            self.stats.media_groups_flushed,
            len(pending_media_groups),
            current_offset,
        )

    def run(self) -> None:
        state = load_state(self.config.state_file, self.logger)
        pending_media_groups: dict[str, dict[str, Any]] = {}

        webhook_info = self.telegram.get_webhook_info()
        self.logger.info("[%s] Telegram webhook info: %s", self.config.instance_name, webhook_info)
        self.telegram.delete_webhook()
        webhook_info = self.telegram.get_webhook_info()
        self.logger.info("[%s] Telegram webhook info: %s", self.config.instance_name, webhook_info)
        self.logger.info(
            "[%s] Bridge instance started | hostname=%s | pid=%s | source_tg_chat=%s | target_max_chat=%s | state_file=%s",
            self.config.instance_name,
            socket.gethostname(),
            os.getpid(),
            self.config.source_tg_chat,
            self.config.target_max_chat,
            self.config.state_file,
        )
        self.logger.info("[%s] Telegram -> MAX bridge started", self.config.instance_name)
        if self.health_state is not None:
            self.health_state.mark_started()

        while not self.stop_event.is_set():
            try:
                self.stats.polls += 1
                if self.health_state is not None:
                    self.health_state.mark_poll()
                self.flush_ready_media_groups(pending_media_groups)
                updates = self.telegram.get_updates(state.get("tg_offset"))
                self.logger.info(
                    "[%s] Poll result: updates=%s current_offset=%s pending_media_groups=%s",
                    self.config.instance_name,
                    len(updates),
                    state.get("tg_offset"),
                    len(pending_media_groups),
                )

                for update in updates:
                    state["tg_offset"] = self.process_update(update, pending_media_groups)
                    save_state(self.config.state_file, state)

                if pending_media_groups:
                    if self.stop_event.wait(self.config.media_group_wait_sec):
                        break
                    self.flush_ready_media_groups(pending_media_groups)

                if updates or pending_media_groups:
                    self.log_cycle_summary(
                        pending_media_groups,
                        current_offset=state.get("tg_offset"),
                    )
                if self.health_state is not None:
                    self.health_state.mark_success()

            except requests.RequestException as exc:
                if self.health_state is not None:
                    self.health_state.mark_error(str(exc))
                if self.stop_event.is_set():
                    break
                self.logger.exception("[%s] Network error: %s", self.config.instance_name, exc)
                if self.stop_event.wait(5):
                    break
            except KeyboardInterrupt:
                self.request_shutdown("keyboard interrupt")
                break
            except Exception as exc:
                if self.health_state is not None:
                    self.health_state.mark_error(str(exc))
                self.logger.exception("[%s] Bridge loop error: %s", self.config.instance_name, exc)
                if self.stop_event.wait(5):
                    break

        if pending_media_groups:
            self.logger.info(
                "[%s] Flushing pending media groups during shutdown: groups=%s",
                self.config.instance_name,
                len(pending_media_groups),
            )
            self.flush_ready_media_groups(pending_media_groups, force=True)
