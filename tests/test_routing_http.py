"""HTTP-level tests for route and method resolution."""

import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection

from gatewaykit.config import RouteConfig
from gatewaykit.server import create_server


class RoutingHTTPTest(unittest.TestCase):
    def setUp(self) -> None:
        users_route = RouteConfig(
            path="/api/users",
            methods=("GET",),
            strip_prefix=False,
            upstream_url="http://localhost:3001",
        )
        self.server = create_server(
            port=0,
            routes=(users_route,),
            host="127.0.0.1",
        )
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def request(self, method: str, path: str):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=1,
        )
        self.addCleanup(connection.close)
        connection.request(method, path)
        return connection.getresponse()

    def test_unmatched_path_returns_404(self) -> None:
        response = self.request("GET", "/not-configured")
        response.read()

        self.assertEqual(response.status, HTTPStatus.NOT_FOUND)

    def test_disallowed_method_returns_405_and_allow_header(self) -> None:
        response = self.request("POST", "/api/users")
        response.read()

        self.assertEqual(response.status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertEqual(response.getheader("Allow"), "GET")

    def test_allowed_route_is_ready_for_proxying(self) -> None:
        response = self.request("GET", "/api/users/123")
        response.read()

        self.assertEqual(response.status, HTTPStatus.NOT_IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
