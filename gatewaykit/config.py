"""GatewayKit configuration loading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(ValueError):
    """Raised when the gateway configuration cannot be loaded."""


@dataclass(frozen=True)
class UpstreamTarget:
    url: str
    weight: int


@dataclass(frozen=True)
class UpstreamConfig:
    targets: tuple[UpstreamTarget, ...]
    balance: Optional[str]


@dataclass(frozen=True)
class RouteConfig:
    path: str
    methods: tuple[str, ...]
    strip_prefix: bool
    upstream: UpstreamConfig


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
    upstream_document = document.get("upstream")

    if not isinstance(path, str) or not path.startswith("/"):
        raise ConfigError(f"{location}.path must start with '/'")
    if not isinstance(methods, list) or not methods or not all(
        isinstance(method, str) for method in methods
    ):
        raise ConfigError(f"{location}.methods must be a non-empty list of strings")
    if not isinstance(strip_prefix, bool):
        raise ConfigError(f"{location}.strip_prefix must be a boolean")
    upstream = _load_upstream(upstream_document, f"{location}.upstream")

    return RouteConfig(
        path=path,
        methods=tuple(method.upper() for method in methods),
        strip_prefix=strip_prefix,
        upstream=upstream,
    )


def _load_upstream(document: Any, location: str) -> UpstreamConfig:
    if not isinstance(document, dict):
        raise ConfigError(f"{location} must be a mapping")

    url = document.get("url")
    targets_document = document.get("targets")
    if url is not None and targets_document is not None:
        raise ConfigError(f"{location} cannot contain both url and targets")

    if url is not None:
        if not isinstance(url, str) or not url:
            raise ConfigError(f"{location}.url must be a non-empty string")
        return UpstreamConfig(
            targets=(UpstreamTarget(url=url, weight=1),),
            balance=None,
        )

    if not isinstance(targets_document, list) or not targets_document:
        raise ConfigError(f"{location}.targets must be a non-empty list")

    targets = tuple(
        _load_target(target, index, location)
        for index, target in enumerate(targets_document)
    )
    balance = document.get("balance")
    if balance not in ("round_robin", "weighted_round_robin"):
        raise ConfigError(
            f"{location}.balance must be round_robin or weighted_round_robin"
        )
    return UpstreamConfig(targets=targets, balance=balance)


def _load_target(document: Any, index: int, location: str) -> UpstreamTarget:
    target_location = f"{location}.targets[{index}]"
    if not isinstance(document, dict):
        raise ConfigError(f"{target_location} must be a mapping")

    url = document.get("url")
    weight = document.get("weight", 1)
    if not isinstance(url, str) or not url:
        raise ConfigError(f"{target_location}.url must be a non-empty string")
    if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
        raise ConfigError(f"{target_location}.weight must be a positive integer")
    return UpstreamTarget(url=url, weight=weight)
