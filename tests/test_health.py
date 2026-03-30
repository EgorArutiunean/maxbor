import logging
import time
import unittest
import urllib.error
import urllib.request

from health import HealthServer, HealthState


class HealthTests(unittest.TestCase):
    def test_health_state_transitions_to_unhealthy_when_stale(self) -> None:
        state = HealthState(stale_after_sec=1)
        state.mark_started()
        state.mark_success()
        time.sleep(1.1)

        snapshot = state.snapshot()

        self.assertFalse(snapshot["healthy"])
        self.assertTrue(snapshot["stale"])

    def test_health_server_serves_healthz(self) -> None:
        state = HealthState(stale_after_sec=60)
        state.mark_started()
        server = HealthServer(
            host="127.0.0.1",
            port=18080,
            logger=logging.getLogger("health-test"),
            get_snapshot=state.snapshot,
        )
        server.start()
        self.addCleanup(server.stop)

        with urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=3) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn('"healthy": true', body)

    def test_health_server_returns_503_when_stopping(self) -> None:
        state = HealthState(stale_after_sec=60)
        state.mark_started()
        state.mark_stopping()
        server = HealthServer(
            host="127.0.0.1",
            port=18081,
            logger=logging.getLogger("health-test"),
            get_snapshot=state.snapshot,
        )
        server.start()
        self.addCleanup(server.stop)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen("http://127.0.0.1:18081/healthz", timeout=3)

        self.assertEqual(ctx.exception.code, 503)
