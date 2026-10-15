"""GatewayKit configuration loading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the gateway configuration cannot be loaded."""


@dataclass(frozen=True)
class GatewayConfig:
    port: int


def load_config(path: str) -> GatewayConfig:
    config_path = Path(path)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            document: Any = yaml.safe_load(config_file)
    except OSError as error:
        raise ConfigError(f"cannot read {config_path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {config_path}: {error}") from error

    try:
        port = document["gateway"]["port"]
    except (KeyError, TypeError) as error:
        raise ConfigError("gateway.port is required") from error

    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("gateway.port must be an integer from 1 to 65535")

    return GatewayConfig(port=port)

