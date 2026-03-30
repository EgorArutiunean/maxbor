import logging
import signal

from bridge import BridgeService
from config import load_config
from health import HealthServer, HealthState
from max_client import MaxClient
from telegram_client import TelegramClient


def main() -> None:
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logger = logging.getLogger("maxbor_bridge")

    telegram = TelegramClient(
        bot_token=config.telegram_bot_token,
        poll_timeout=config.poll_timeout,
    )
    max_client = MaxClient(
        bot_token=config.max_bot_token,
        target_chat=config.target_max_chat,
        instance_name=config.instance_name,
        logger=logger,
    )
    health_state = HealthState(stale_after_sec=config.healthcheck_stale_after_sec)
    service = BridgeService(
        config=config,
        telegram=telegram,
        max_client=max_client,
        logger=logger,
        health_state=health_state,
    )
    health_server: HealthServer | None = None

    def handle_signal(signum: int, _frame: object) -> None:
        service.request_shutdown(f"signal {signum}")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if config.healthcheck_enabled:
        health_server = HealthServer(
            host=config.healthcheck_host,
            port=config.healthcheck_port,
            logger=logger,
            get_snapshot=health_state.snapshot,
        )
        health_server.start()

    try:
        service.run()
    finally:
        if health_server is not None:
            health_server.stop()


if __name__ == "__main__":
    main()
