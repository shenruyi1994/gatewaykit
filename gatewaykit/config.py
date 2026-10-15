"""GatewayKit configuration loading."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


DURATION_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m)$")


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
class HealthCheckConfig:
    path: str
    interval: float
    unhealthy_threshold: int


@dataclass(frozen=True)
class RateLimitConfig:
    requests: int
    window: float
    strategy: str
    per: str


@dataclass(frozen=True)
class RouteConfig:
    path: str
    methods: tuple[str, ...]
    strip_prefix: bool
    upstream: UpstreamConfig
    timeout: Optional[float]
    health_check: Optional[HealthCheckConfig]
    rate_limit: Optional[RateLimitConfig]


@dataclass(frozen=True)
class GatewayConfig:
    port: int
    routes: tuple[RouteConfig, ...]
    global_timeout: Optional[float]
    global_rate_limit: Optional[RateLimitConfig]


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
    global_timeout_document = gateway.get("global_timeout")
    global_timeout = (
        _parse_duration(global_timeout_document, "gateway.global_timeout")
        if global_timeout_document is not None
        else None
    )
    global_rate_limit_document = gateway.get("global_rate_limit")
    global_rate_limit = (
        _load_rate_limit(
            global_rate_limit_document,
            "gateway.global_rate_limit",
        )
        if global_rate_limit_document is not None
        else None
    )
    return GatewayConfig(
        port=port,
        routes=routes,
        global_timeout=global_timeout,
        global_rate_limit=global_rate_limit,
    )


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
    timeout_document = document.get("timeout")
    timeout = (
        _parse_duration(timeout_document, f"{location}.timeout")
        if timeout_document is not None
        else None
    )
    health_check_document = document.get("health_check")
    health_check = (
        _load_health_check(health_check_document, f"{location}.health_check")
        if health_check_document is not None
        else None
    )
    rate_limit_document = document.get("rate_limit")
    rate_limit = (
        _load_rate_limit(rate_limit_document, f"{location}.rate_limit")
        if rate_limit_document is not None
        else None
    )

    return RouteConfig(
        path=path,
        methods=tuple(method.upper() for method in methods),
        strip_prefix=strip_prefix,
        upstream=upstream,
        timeout=timeout,
        health_check=health_check,
        rate_limit=rate_limit,
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


def _parse_duration(value: Any, location: str) -> float:
    if not isinstance(value, str):
        raise ConfigError(f"{location} must be a duration string")

    match = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise ConfigError(f"{location} must use ms, s, or m units")

    amount = float(match.group(1))
    if amount <= 0:
        raise ConfigError(f"{location} must be greater than zero")

    unit = match.group(2)
    multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0}[unit]
    return amount * multiplier


def _load_health_check(document: Any, location: str) -> HealthCheckConfig:
    if not isinstance(document, dict):
        raise ConfigError(f"{location} must be a mapping")

    path = document.get("path")
    interval = _parse_duration(document.get("interval"), f"{location}.interval")
    threshold = document.get("unhealthy_threshold")

    if not isinstance(path, str) or not path.startswith("/"):
        raise ConfigError(f"{location}.path must start with '/'")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise ConfigError(f"{location}.unhealthy_threshold must be a positive integer")

    return HealthCheckConfig(
        path=path,
        interval=interval,
        unhealthy_threshold=threshold,
    )


def _load_rate_limit(document: Any, location: str) -> RateLimitConfig:
    if not isinstance(document, dict):
        raise ConfigError(f"{location} must be a mapping")

    requests = document.get("requests")
    if not isinstance(requests, int) or isinstance(requests, bool) or requests < 1:
        raise ConfigError(f"{location}.requests must be a positive integer")

    window = _parse_duration(document.get("window"), f"{location}.window")
    strategy = document.get("strategy")
    if strategy not in ("fixed_window", "sliding_window"):
        raise ConfigError(
            f"{location}.strategy must be fixed_window or sliding_window"
        )

    bucket_type = document.get("per")
    if bucket_type not in ("ip", "global"):
        raise ConfigError(f"{location}.per must be ip or global")

    return RateLimitConfig(
        requests=requests,
        window=window,
        strategy=strategy,
        per=bucket_type,
    )
