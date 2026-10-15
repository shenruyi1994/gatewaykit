"""HTTP-level tests for product upstream health checks."""

import json
import threading
import time
import unittest
from http import HTTPStatus
from http.client import HTTPConnection

from gatewaykit.config import (
    HealthCheckConfig,
    RouteConfig,
    UpstreamConfig,
    UpstreamTarget,
)
from gatewaykit.server import create_server
from tests.mock_upstream import create_mock_upstream


class ProductHealthCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = create_mock_upstream(HTTPStatus.SERVICE_UNAVAILABLE)
        self.addCleanup(self.primary.server_close)
        self.addCleanup(self.primary.shutdown)
        threading.Thread(target=self.primary.serve_forever, daemon=True).start()

        self.secondary = create_mock_upstream()
        self.addCleanup(self.secondary.server_close)
        self.addCleanup(self.secondary.shutdown)
        threading.Thread(target=self.secondary.serve_forever, daemon=True).start()

        self.primary_target = UpstreamTarget(
            f"http://127.0.0.1:{self.primary.server_address[1]}",
            3,
        )
        self.secondary_target = UpstreamTarget(
            f"http://127.0.0.1:{self.secondary.server_address[1]}",
            1,
        )
        self.products_route = RouteConfig(
            path="/api/products",
            methods=("GET",),
            strip_prefix=True,
            upstream=UpstreamConfig(
                targets=(self.primary_target, self.secondary_target),
                balance="weighted_round_robin",
            ),
            timeout=0.2,
            health_check=HealthCheckConfig(
                path="/healthz",
                interval=0.02,
                unhealthy_threshold=2,
            ),
            rate_limit=None,
        )
        self.server = create_server(
            port=0,
            routes=(self.products_route,),
            host="127.0.0.1",
        )
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def request(self):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=1,
        )
        self.addCleanup(connection.close)
        connection.request("GET", "/api/products/123")
        return connection.getresponse()

    def wait_until(self, predicate) -> None:
        deadline = time.monotonic() + 1
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("health monitor did not reach the expected state")
            time.sleep(0.01)

    def test_unhealthy_product_target_is_skipped_and_can_recover(self) -> None:
        monitor = self.server.health_monitor
        self.wait_until(
            lambda: not monitor.is_healthy(
                self.products_route,
                self.primary_target,
            )
        )

        response = self.request()
        body = json.loads(response.read())
        self.assertEqual(response.status, HTTPStatus.OK)
        self.assertEqual(body["upstream_port"], self.secondary.server_address[1])

        self.primary.health_status = HTTPStatus.OK
        self.wait_until(
            lambda: monitor.is_healthy(
                self.products_route,
                self.primary_target,
            )
        )

        response = self.request()
        body = json.loads(response.read())
        self.assertEqual(body["upstream_port"], self.primary.server_address[1])

    def test_all_unhealthy_product_targets_return_503(self) -> None:
        self.secondary.health_status = HTTPStatus.SERVICE_UNAVAILABLE
        monitor = self.server.health_monitor
        self.wait_until(
            lambda: not monitor.is_healthy(
                self.products_route,
                self.primary_target,
            )
            and not monitor.is_healthy(
                self.products_route,
                self.secondary_target,
            )
        )

        response = self.request()
        body = json.loads(response.read())

        self.assertEqual(response.status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(body, {"error": "no_healthy_upstreams"})


if __name__ == "__main__":
    unittest.main()
