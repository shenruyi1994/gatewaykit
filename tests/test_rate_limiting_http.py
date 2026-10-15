"""HTTP-level tests for global defaults and route rate-limit overrides."""

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection

from gatewaykit.config import (
    RateLimitConfig,
    RouteConfig,
    UpstreamConfig,
    UpstreamTarget,
)
from gatewaykit.server import create_server
from tests.mock_upstream import create_mock_upstream


class RateLimitingHTTPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = create_mock_upstream()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()

        upstream = UpstreamConfig(
            targets=(
                UpstreamTarget(
                    f"http://127.0.0.1:{self.upstream.server_address[1]}",
                    1,
                ),
            ),
            balance=None,
        )
        users = RouteConfig(
            path="/api/users",
            methods=("GET",),
            strip_prefix=False,
            upstream=upstream,
            timeout=None,
            health_check=None,
            rate_limit=RateLimitConfig(1, 60, "sliding_window", "ip"),
        )
        products = RouteConfig(
            path="/api/products",
            methods=("GET",),
            strip_prefix=False,
            upstream=upstream,
            timeout=None,
            health_check=None,
            rate_limit=None,
        )
        self.server = create_server(
            port=0,
            routes=(users, products),
            host="127.0.0.1",
            global_rate_limit=RateLimitConfig(2, 60, "fixed_window", "ip"),
        )
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def request(self, path: str):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=1,
        )
        self.addCleanup(connection.close)
        connection.request("GET", path)
        return connection.getresponse()

    def test_route_override_takes_precedence_over_global_default(self) -> None:
        allowed = self.request("/api/users")
        allowed.read()
        blocked = self.request("/api/users")
        body = json.loads(blocked.read())

        self.assertEqual(allowed.status, HTTPStatus.OK)
        self.assertEqual(blocked.status, HTTPStatus.TOO_MANY_REQUESTS)
        self.assertEqual(blocked.getheader("Retry-After"), "60")
        self.assertEqual(body, {"error": "rate_limit_exceeded"})

    def test_route_without_override_inherits_global_default(self) -> None:
        for _ in range(2):
            response = self.request("/api/products")
            response.read()
            self.assertEqual(response.status, HTTPStatus.OK)

        blocked = self.request("/api/products")
        body = json.loads(blocked.read())

        self.assertEqual(blocked.status, HTTPStatus.TOO_MANY_REQUESTS)
        self.assertEqual(body, {"error": "rate_limit_exceeded"})


if __name__ == "__main__":
    unittest.main()
