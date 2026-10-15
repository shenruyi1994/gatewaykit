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

    def test_missing_file_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_config("does-not-exist.yaml")


if __name__ == "__main__":
    unittest.main()
