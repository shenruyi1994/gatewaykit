"""Match incoming request paths to configured routes."""

from typing import Optional, Sequence
from urllib.parse import urlsplit

from gatewaykit.config import RouteConfig


def find_route(request_target: str, routes: Sequence[RouteConfig]) -> Optional[RouteConfig]:
    """Return the most specific route matching the request target."""
    request_path = urlsplit(request_target).path
    matches = [route for route in routes if _matches(request_path, route.path)]
    return max(matches, key=lambda route: len(route.path), default=None)


def _matches(request_path: str, route_path: str) -> bool:
    if route_path == "/":
        return request_path.startswith("/")
    return request_path == route_path or request_path.startswith(f"{route_path}/")

