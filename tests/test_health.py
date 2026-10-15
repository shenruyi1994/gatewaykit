"""Tests for GatewayKit's built-in health endpoint."""

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection

from gatewaykit.server import create_server


class HealthEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server(port=0, host="127.0.0.1")
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()

    def test_health_returns_status_and_integer_uptime(self) -> None:
        port = self.server.server_address[1]
        connection = HTTPConnection("127.0.0.1", port, timeout=1)
        self.addCleanup(connection.close)

        connection.request("GET", "/health")
        response = connection.getresponse()
        body = json.loads(response.read())

        self.assertEqual(response.status, HTTPStatus.OK)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(body["status"], "healthy")
        self.assertIsInstance(body["uptime_seconds"], int)
        self.assertGreaterEqual(body["uptime_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
