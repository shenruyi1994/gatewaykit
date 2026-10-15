"""Forward requests to a route's upstream service."""

import socket
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import List, Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

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


class UpstreamError(RuntimeError):
    """Raised when an upstream request fails at the HTTP transport layer."""


class UpstreamTimeout(UpstreamError):
    """Raised when an upstream does not respond within its configured timeout."""


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    reason: str
    headers: List[Tuple[str, str]]
    body: bytes


def proxy_request(
    route: RouteConfig,
    upstream_url: str,
    method: str,
    request_target: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
) -> UpstreamResponse:
    """Forward one request while preserving its method, target, and body."""
    upstream = urlsplit(upstream_url)
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

    upstream_target = _upstream_target(route, request_target)
    connection = connection_class(
        upstream.hostname,
        upstream.port,
        timeout=route.timeout,
    )
    try:
        connection.request(
            method,
            upstream_target,
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
    except socket.timeout as error:
        raise UpstreamTimeout(f"upstream request timed out: {error}") from error
    except (HTTPException, OSError) as error:
        raise UpstreamError(f"upstream request failed: {error}") from error
    finally:
        connection.close()


def _upstream_target(route: RouteConfig, request_target: str) -> str:
    if not route.strip_prefix:
        return request_target

    target = urlsplit(request_target)
    stripped_path = target.path[len(route.path) :] or "/"
    return urlunsplit(("", "", stripped_path, target.query, ""))
