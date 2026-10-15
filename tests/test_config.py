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
  global_rate_limit:
    requests: 100
    window: 60s
    strategy: fixed_window
    per: ip
  routes:
    - path: /api/users
      methods: [GET, POST]
      strip_prefix: false
      upstream:
        url: http://localhost:3001
      rate_limit:
        requests: 30
        window: 60s
        strategy: sliding_window
        per: ip
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
        self.assertEqual(route.upstream.targets[0].url, "http://localhost:3001")
        self.assertEqual(route.upstream.targets[0].weight, 1)
        self.assertIsNone(route.upstream.balance)
        self.assertIsNone(route.timeout)
        self.assertIsNone(route.health_check)
        self.assertEqual(route.rate_limit.requests, 30)
        self.assertEqual(route.rate_limit.window, 60)
        self.assertEqual(route.rate_limit.strategy, "sliding_window")
        self.assertEqual(route.rate_limit.per, "ip")
        self.assertEqual(config.global_rate_limit.requests, 100)
        self.assertEqual(config.global_rate_limit.window, 60)
        self.assertEqual(config.global_rate_limit.strategy, "fixed_window")
        self.assertEqual(config.global_rate_limit.per, "ip")

    def test_loads_multiple_upstream_targets(self) -> None:
        document = """\
gateway:
  port: 8080
  routes:
    - path: /api/products
      methods: [GET]
      strip_prefix: true
      upstream:
        targets:
          - url: http://localhost:3003
            weight: 3
          - url: http://localhost:3004
            weight: 1
        balance: weighted_round_robin
      timeout: 50ms
      health_check:
        path: /healthz
        interval: 20ms
        unhealthy_threshold: 2
"""
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "gateway.yaml"
            config_path.write_text(document, encoding="utf-8")

            route = load_config(str(config_path)).routes[0]

        self.assertEqual(
            [(target.url, target.weight) for target in route.upstream.targets],
            [("http://localhost:3003", 3), ("http://localhost:3004", 1)],
        )
        self.assertEqual(route.upstream.balance, "weighted_round_robin")
        self.assertEqual(route.timeout, 0.05)
        self.assertEqual(route.health_check.path, "/healthz")
        self.assertEqual(route.health_check.interval, 0.02)
        self.assertEqual(route.health_check.unhealthy_threshold, 2)
        self.assertIsNone(route.rate_limit)

    def test_missing_file_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_config("does-not-exist.yaml")


if __name__ == "__main__":
    unittest.main()
