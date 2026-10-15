"""Forward requests to a route's upstream service."""

from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from gatewaykit.config import RouteConfig


REQUEST_HEADERS_NOT_FORWARDED = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    reason: str
    headers: List[Tuple[str, str]]
    body: bytes


def proxy_request(
    route: RouteConfig,
    method: str,
    request_target: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
) -> UpstreamResponse:
    """Forward one request while preserving its method, target, and body."""
    upstream = urlsplit(route.upstream_url)
    if upstream.scheme == "http":
        connection_class = HTTPConnection
    elif upstream.scheme == "https":
        connection_class = HTTPSConnection
    else:
        raise ValueError(f"unsupported upstream scheme: {upstream.scheme}")

    if upstream.hostname is None:
        raise ValueError("upstream URL must include a hostname")

    forwarded_headers = {
        name: value
        for name, value in headers.items()
        if name.lower() not in REQUEST_HEADERS_NOT_FORWARDED
    }

    connection = connection_class(upstream.hostname, upstream.port)
    try:
        connection.request(
            method,
            request_target,
            body=body,
            headers=forwarded_headers,
        )
        response = connection.getresponse()
        return UpstreamResponse(
            status=response.status,
            reason=response.reason,
            headers=response.getheaders(),
            body=response.read(),
        )
    finally:
        connection.close()
