"""HTTP-level tests for route and method resolution."""

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection

from gatewaykit.config import RouteConfig
from gatewaykit.server import create_server
from tests.mock_upstream import create_mock_upstream


class RoutingHTTPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = create_mock_upstream()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()

        users_route = RouteConfig(
            path="/api/users",
            methods=("GET",),
            strip_prefix=False,
            upstream_url=f"http://127.0.0.1:{self.upstream.server_address[1]}",
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

    def test_allowed_get_is_forwarded_to_upstream(self) -> None:
        response = self.request("GET", "/api/users/123?details=true")
        body = json.loads(response.read())

        self.assertEqual(response.status, HTTPStatus.OK)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(body["method"], "GET")
        self.assertEqual(body["path"], "/api/users/123?details=true")


if __name__ == "__main__":
    unittest.main()
