import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    max_bot_token: str
    source_tg_chat: str
    target_max_chat: str
    instance_name: str
    poll_timeout: int
    media_group_wait_sec: float
    max_attachment_size_bytes: int
    healthcheck_enabled: bool
    healthcheck_host: str
    healthcheck_port: int
    healthcheck_stale_after_sec: int
    state_file: Path
    log_level: str

    def __post_init__(self) -> None:
        if not self.telegram_bot_token.strip():
            raise RuntimeError("TELEGRAM_BOT_TOKEN must not be empty")

        if not self.max_bot_token.strip():
            raise RuntimeError("MAX_BOT_TOKEN must not be empty")

        if not self.source_tg_chat.strip():
            raise RuntimeError("SOURCE_TG_CHAT must not be empty")

        if not self.target_max_chat.strip():
            raise RuntimeError("TARGET_MAX_CHAT must not be empty")

        if not self.instance_name.strip():
            raise RuntimeError("INSTANCE_NAME must not be empty")

        if self.poll_timeout <= 0:
            raise RuntimeError("POLL_TIMEOUT must be greater than 0")

        if self.media_group_wait_sec <= 0:
            raise RuntimeError("MEDIA_GROUP_WAIT_SEC must be greater than 0")

        if self.max_attachment_size_bytes <= 0:
            raise RuntimeError("MAX_ATTACHMENT_SIZE_BYTES must be greater than 0")

        if not self.healthcheck_host.strip():
            raise RuntimeError("HEALTHCHECK_HOST must not be empty")

        if self.healthcheck_port <= 0:
            raise RuntimeError("HEALTHCHECK_PORT must be greater than 0")

        if self.healthcheck_stale_after_sec <= 0:
            raise RuntimeError("HEALTHCHECK_STALE_AFTER_SEC must be greater than 0")

        if not self.log_level.strip():
            raise RuntimeError("LOG_LEVEL must not be empty")


def load_config() -> AppConfig:
    load_dotenv()

    return AppConfig(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        max_bot_token=os.environ["MAX_BOT_TOKEN"],
        source_tg_chat=os.environ["SOURCE_TG_CHAT"],
        target_max_chat=os.environ["TARGET_MAX_CHAT"],
        instance_name=os.getenv("INSTANCE_NAME", "maxbor"),
        poll_timeout=int(os.getenv("POLL_TIMEOUT", "30")),
        media_group_wait_sec=float(os.getenv("MEDIA_GROUP_WAIT_SEC", "1.5")),
        max_attachment_size_bytes=int(os.getenv("MAX_ATTACHMENT_SIZE_BYTES", "52428800")),
        healthcheck_enabled=os.getenv("HEALTHCHECK_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        healthcheck_host=os.getenv("HEALTHCHECK_HOST", "0.0.0.0"),
        healthcheck_port=int(os.getenv("HEALTHCHECK_PORT", "8080")),
        healthcheck_stale_after_sec=int(os.getenv("HEALTHCHECK_STALE_AFTER_SEC", "120")),
        state_file=Path(os.getenv("STATE_FILE", "state.json")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
