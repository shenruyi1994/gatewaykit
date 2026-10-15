"""GatewayKit configuration loading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the gateway configuration cannot be loaded."""


@dataclass(frozen=True)
class RouteConfig:
    path: str
    methods: tuple[str, ...]
    strip_prefix: bool
    upstream_url: str


@dataclass(frozen=True)
class GatewayConfig:
    port: int
    routes: tuple[RouteConfig, ...]


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
        gateway = document["gateway"]
        port = gateway["port"]
    except (KeyError, TypeError) as error:
        raise ConfigError("gateway.port is required") from error

    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("gateway.port must be an integer from 1 to 65535")

    routes_document = gateway.get("routes", [])
    if not isinstance(routes_document, list):
        raise ConfigError("gateway.routes must be a list")

    routes = tuple(_load_route(route, index) for index, route in enumerate(routes_document))
    return GatewayConfig(port=port, routes=routes)


def _load_route(document: Any, index: int) -> RouteConfig:
    location = f"gateway.routes[{index}]"
    if not isinstance(document, dict):
        raise ConfigError(f"{location} must be a mapping")

    path = document.get("path")
    methods = document.get("methods")
    strip_prefix = document.get("strip_prefix", False)
    upstream = document.get("upstream")
    upstream_url = upstream.get("url") if isinstance(upstream, dict) else None

    if not isinstance(path, str) or not path.startswith("/"):
        raise ConfigError(f"{location}.path must start with '/'")
    if not isinstance(methods, list) or not methods or not all(
        isinstance(method, str) for method in methods
    ):
        raise ConfigError(f"{location}.methods must be a non-empty list of strings")
    if not isinstance(strip_prefix, bool):
        raise ConfigError(f"{location}.strip_prefix must be a boolean")
    if not isinstance(upstream_url, str) or not upstream_url:
        raise ConfigError(f"{location}.upstream.url is required")

    return RouteConfig(
        path=path,
        methods=tuple(method.upper() for method in methods),
        strip_prefix=strip_prefix,
        upstream_url=upstream_url,
    )
