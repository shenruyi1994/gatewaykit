"""Tests for GatewayKit configuration loading."""

import tempfile
import unittest
from pathlib import Path

from gatewaykit.config import ConfigError, GatewayConfig, load_config


class ConfigTest(unittest.TestCase):
    def load_document(self, document: str) -> GatewayConfig:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "gateway.yaml"
            config_path.write_text(document, encoding="utf-8")
            return load_config(str(config_path))

    def assert_invalid_config(self, document: str, message: str) -> None:
        with self.assertRaisesRegex(ConfigError, message):
            self.load_document(document)

    def test_loads_gateway_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "gateway.yaml"
            config_path.write_text("gateway:\n  port: 9090\n", encoding="utf-8")

            config = load_config(str(config_path))

        self.assertEqual(config.port, 9090)

    def test_supplied_config_loads_all_routes(self) -> None:
        config_path = Path(__file__).parents[1] / "gateway.yaml"

        config = load_config(str(config_path))

        self.assertEqual(config.port, 8080)
        self.assertEqual(
            [route.path for route in config.routes],
            [
                "/api/users",
                "/api/orders",
                "/api/products",
                "/api/legacy",
                "/api/internal",
            ],
        )

    def test_loads_basic_route(self) -> None:
        document = """\
gateway:
  port: 8080
  global_timeout: 30s
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
        self.assertEqual(config.global_timeout, 30)
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

    def test_rejects_invalid_document_structure_and_ports(self) -> None:
        cases = (
            ("[]\n", "configuration root must be a mapping"),
            ("gateway: []\n", "gateway must be a mapping"),
            ("gateway: {}\n", "gateway.port is required"),
            ("gateway:\n  port: 0\n", "gateway.port must be an integer"),
            ("gateway:\n  port: '8080'\n", "gateway.port must be an integer"),
        )
        for document, message in cases:
            with self.subTest(document=document):
                self.assert_invalid_config(document, message)

    def test_rejects_invalid_durations(self) -> None:
        cases = (
            ("global_timeout: 30", "gateway.global_timeout must be a duration string"),
            ("global_timeout: 30seconds", "gateway.global_timeout must use ms, s, or m"),
            ("global_timeout: 0s", "gateway.global_timeout must be greater than zero"),
        )
        for field, message in cases:
            document = f"gateway:\n  port: 8080\n  {field}\n"
            with self.subTest(field=field):
                self.assert_invalid_config(document, message)

    def test_rejects_invalid_methods(self) -> None:
        base = """\
gateway:
  port: 8080
  routes:
    - path: /example
      methods: {methods}
      upstream:
        url: http://localhost:3001
"""
        cases = (
            ("[]", "methods must be a non-empty list"),
            ("[GET, 'BAD METHOD']", r"methods\[1\] must be a valid HTTP method token"),
            ("[GET, 123]", r"methods\[1\] must be a valid HTTP method token"),
        )
        for methods, message in cases:
            with self.subTest(methods=methods):
                self.assert_invalid_config(base.format(methods=methods), message)

    def test_accepts_custom_http_method_tokens(self) -> None:
        document = """\
gateway:
  port: 8080
  routes:
    - path: /cache
      methods: [PURGE]
      upstream:
        url: http://localhost:3001
"""

        route = self.load_document(document).routes[0]

        self.assertEqual(route.methods, ("PURGE",))

    def test_rejects_invalid_upstream_urls_and_targets(self) -> None:
        base = """\
gateway:
  port: 8080
  routes:
    - path: /example
      methods: [GET]
      upstream:
{upstream}
"""
        cases = (
            ("        url: localhost:3001", "scheme must be http or https"),
            ("        url: ftp://localhost:3001", "scheme must be http or https"),
            ("        url: http://", "must include a hostname"),
            ("        url: 'http://local host:3001'", "must not contain whitespace"),
            ("        url: http://localhost:invalid", "must be a valid URL"),
            ("        targets: []", "targets must be a non-empty list"),
            (
                "        targets:\n"
                "          - url: http://localhost:3001\n"
                "            weight: 0\n"
                "        balance: weighted_round_robin",
                "weight must be a positive integer",
            ),
            (
                "        targets:\n"
                "          - url: http://localhost:3001\n"
                "        balance: random",
                "balance must be round_robin or weighted_round_robin",
            ),
        )
        for upstream, message in cases:
            with self.subTest(upstream=upstream):
                self.assert_invalid_config(base.format(upstream=upstream), message)

    def test_rejects_invalid_rate_limits(self) -> None:
        base = """\
gateway:
  port: 8080
  global_rate_limit:
    requests: {requests}
    window: {window}
    strategy: {strategy}
    per: {per}
"""
        cases = (
            (0, "60s", "fixed_window", "ip", "requests must be a positive integer"),
            (10, "never", "fixed_window", "ip", "window must use ms, s, or m"),
            (
                10,
                "60s",
                "token_bucket",
                "ip",
                "strategy must be fixed_window or sliding_window",
            ),
            (10, "60s", "fixed_window", "user", "per must be ip or global"),
        )
        for requests, window, strategy, per, message in cases:
            with self.subTest(message=message):
                self.assert_invalid_config(
                    base.format(
                        requests=requests,
                        window=window,
                        strategy=strategy,
                        per=per,
                    ),
                    message,
                )

    def test_rejects_invalid_health_checks(self) -> None:
        base = """\
gateway:
  port: 8080
  routes:
    - path: /example
      methods: [GET]
      upstream:
        url: http://localhost:3001
      health_check:
        path: {path}
        interval: {interval}
        unhealthy_threshold: {threshold}
"""
        cases = (
            ("healthz", "30s", 3, "path must start with '/'"),
            ("/healthz", "soon", 3, "interval must use ms, s, or m"),
            ("/healthz", "30s", 0, "unhealthy_threshold must be a positive integer"),
        )
        for path, interval, threshold, message in cases:
            with self.subTest(message=message):
                self.assert_invalid_config(
                    base.format(
                        path=path,
                        interval=interval,
                        threshold=threshold,
                    ),
                    message,
                )

    def test_ignores_unknown_configuration_sections(self) -> None:
        document = """\
gateway:
  port: 8080
  future_gateway_option:
    enabled: true
  routes:
    - path: /example
      methods: [GET]
      upstream:
        url: http://localhost:3001
      retry:
        attempts: 3
      auth:
        type: future_auth_type
      future_route_option: ignored-for-forward-compatibility
"""

        config = self.load_document(document)

        self.assertEqual(config.port, 8080)
        self.assertEqual(config.routes[0].path, "/example")


if __name__ == "__main__":
    unittest.main()
