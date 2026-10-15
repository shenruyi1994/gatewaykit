"""Acceptance coverage for the non-negotiable gateway requirements."""

import json
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

from gatewaykit.config import load_config
from gatewaykit.server import create_server
from tests.mock_upstream import create_mock_upstream


class CoreRequirementsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = create_mock_upstream()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()

        document = f"""\
gateway:
  port: 8080
  global_timeout: 1s
  routes:
    - path: /different/widgets
      methods: [PUT]
      strip_prefix: false
      upstream:
        url: http://127.0.0.1:{self.upstream.server_address[1]}
"""
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "alternate.yaml"
            config_path.write_text(document, encoding="utf-8")
            self.config = load_config(str(config_path))

        self.server = create_server(
            port=0,
            routes=self.config.routes,
            host="127.0.0.1",
            global_timeout=self.config.global_timeout,
            global_rate_limit=self.config.global_rate_limit,
        )
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def request(self, method: str, path: str, body=None, headers=None):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=1,
        )
        self.addCleanup(connection.close)
        connection.request(method, path, body=body, headers=headers or {})
        return connection.getresponse()

    def test_alternate_config_satisfies_core_requirements(self) -> None:
        self.assertEqual(self.config.port, 8080)

        health = self.request("GET", "/health")
        health_body = json.loads(health.read())
        self.assertEqual(health.status, HTTPStatus.OK)
        self.assertEqual(health_body["status"], "healthy")
        self.assertIsInstance(health_body["uptime_seconds"], int)

        request_body = '{"name":"alternate"}'
        proxied = self.request(
            "PUT",
            "/different/widgets/123",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )
        proxied_body = json.loads(proxied.read())
        self.assertEqual(proxied.status, HTTPStatus.OK)
        self.assertEqual(proxied_body["method"], "PUT")
        self.assertEqual(proxied_body["path"], "/different/widgets/123")
        self.assertEqual(proxied_body["body"], request_body)

        disallowed = self.request("POST", "/different/widgets")
        disallowed.read()
        self.assertEqual(disallowed.status, HTTPStatus.METHOD_NOT_ALLOWED)

        unmatched = self.request("GET", "/api/users")
        unmatched.read()
        self.assertEqual(unmatched.status, HTTPStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
