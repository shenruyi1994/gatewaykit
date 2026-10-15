"""Tests for GatewayKit configuration loading."""

import tempfile
import unittest
from pathlib import Path

from gatewaykit.config import ConfigError, load_config


class ConfigTest(unittest.TestCase):
    def test_loads_gateway_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "gateway.yaml"
            config_path.write_text("gateway:\n  port: 9090\n", encoding="utf-8")

            config = load_config(str(config_path))

        self.assertEqual(config.port, 9090)

    def test_loads_basic_route(self) -> None:
        document = """\
gateway:
  port: 8080
  routes:
    - path: /api/users
      methods: [GET, POST]
      strip_prefix: false
      upstream:
        url: http://localhost:3001
"""
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "gateway.yaml"
            config_path.write_text(document, encoding="utf-8")

            config = load_config(str(config_path))

        self.assertEqual(len(config.routes), 1)
        route = config.routes[0]
        self.assertEqual(route.path, "/api/users")
        self.assertEqual(route.methods, ("GET", "POST"))
        self.assertFalse(route.strip_prefix)
        self.assertEqual(route.upstream_url, "http://localhost:3001")

    def test_missing_file_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_config("does-not-exist.yaml")


if __name__ == "__main__":
    unittest.main()
