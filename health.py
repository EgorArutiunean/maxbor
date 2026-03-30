import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


@dataclass
class HealthSnapshot:
    status: str
    started_at: float
    last_poll_at: float | None = None
    last_success_at: float | None = None
    last_error_at: float | None = None
    last_error: str | None = None
    shutting_down: bool = False


class HealthState:
    def __init__(self, stale_after_sec: int) -> None:
        self._stale_after_sec = stale_after_sec
        self._lock = threading.Lock()
        self._snapshot = HealthSnapshot(
            status="starting",
            started_at=time.time(),
        )

    def mark_started(self) -> None:
        with self._lock:
            self._snapshot.status = "ok"
            self._snapshot.last_success_at = time.time()

    def mark_poll(self) -> None:
        with self._lock:
            self._snapshot.last_poll_at = time.time()

    def mark_success(self) -> None:
        with self._lock:
            self._snapshot.status = "ok"
            self._snapshot.last_success_at = time.time()
            self._snapshot.last_error = None
            self._snapshot.last_error_at = None

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._snapshot.status = "degraded"
            self._snapshot.last_error = message
            self._snapshot.last_error_at = time.time()

    def mark_stopping(self) -> None:
        with self._lock:
            self._snapshot.status = "stopping"
            self._snapshot.shutting_down = True

    def snapshot(self) -> dict:
        with self._lock:
            snapshot = HealthSnapshot(**asdict(self._snapshot))

        now = time.time()
        freshness_ts = snapshot.last_poll_at or snapshot.last_success_at or snapshot.started_at
        is_stale = (
            freshness_ts is not None
            and now - freshness_ts > self._stale_after_sec
        )
        healthy = not snapshot.shutting_down and snapshot.status in {"starting", "ok"} and not is_stale

        data = asdict(snapshot)
        data["healthy"] = healthy
        data["stale"] = is_stale
        data["now"] = now
        data["freshness_ts"] = freshness_ts
        data["stale_after_sec"] = self._stale_after_sec
        return data


class HealthServer:
    def __init__(
        self,
        host: str,
        port: int,
        logger: logging.Logger,
        get_snapshot: Callable[[], dict],
    ) -> None:
        self.host = host
        self.port = port
        self.logger = logger
        self._get_snapshot = get_snapshot
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        snapshot_getter = self._get_snapshot
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/healthz":
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.end_headers()
                    return

                payload = snapshot_getter()
                status = HTTPStatus.OK if payload["healthy"] else HTTPStatus.SERVICE_UNAVAILABLE
                body = json.dumps(payload).encode("utf-8")

                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("Health server: " + format, *args)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="health-server",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("Health server started: http://%s:%s/healthz", self.host, self.port)

    def stop(self) -> None:
        if self._httpd is None:
            return

        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.logger.info("Health server stopped")
