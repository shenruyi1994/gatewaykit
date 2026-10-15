"""Forward requests to a route's upstream service."""

from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import List, Tuple
from urllib.parse import urlsplit

from gatewaykit.config import RouteConfig


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    reason: str
    headers: List[Tuple[str, str]]
    body: bytes


def proxy_get(route: RouteConfig, request_target: str) -> UpstreamResponse:
    """Forward one GET request while preserving its path and query string."""
    upstream = urlsplit(route.upstream_url)
    if upstream.scheme == "http":
        connection_class = HTTPConnection
    elif upstream.scheme == "https":
        connection_class = HTTPSConnection
    else:
        raise ValueError(f"unsupported upstream scheme: {upstream.scheme}")

    if upstream.hostname is None:
        raise ValueError("upstream URL must include a hostname")

    connection = connection_class(upstream.hostname, upstream.port)
    try:
        connection.request("GET", request_target)
        response = connection.getresponse()
        return UpstreamResponse(
            status=response.status,
            reason=response.reason,
            headers=response.getheaders(),
            body=response.read(),
        )
    finally:
        connection.close()

