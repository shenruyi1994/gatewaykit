"""GatewayKit's minimal inbound HTTP server."""

from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Optional, Sequence, Tuple, Type

from gatewaykit.config import RateLimitConfig, RouteConfig
from gatewaykit.health import HealthMonitor
from gatewaykit.load_balancer import LoadBalancer, NoHealthyTargets
from gatewaykit.proxy import (
    UpstreamError,
    UpstreamResponse,
    UpstreamTimeout,
    proxy_request,
)
from gatewaykit.rate_limiter import RateLimiter
from gatewaykit.router import find_route


RESPONSE_HEADERS_NOT_FORWARDED = {
    "connection",
    "date",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "server",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
DEFAULT_UPSTREAM_TIMEOUT = 30.0


def make_handler(
    started_at: float,
    routes: Sequence[RouteConfig],
    health_monitor: HealthMonitor,
    global_timeout: Optional[float],
    global_rate_limit: Optional[RateLimitConfig],
    log_requests: bool,
) -> Type[BaseHTTPRequestHandler]:
    load_balancer = LoadBalancer()
    rate_limiter = RateLimiter()

    class GatewayHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            if log_requests:
                super().log_message(format, *args)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] == "/health":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "healthy",
                        "uptime_seconds": int(time.monotonic() - started_at),
                    },
                )
                return

            self._handle_route()

        def __getattr__(self, name: str):
            if name.startswith("do_"):
                return self._handle_route
            raise AttributeError(name)

        def _handle_route(self) -> None:
            route = find_route(self.path, routes)
            if route is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            if self.command not in route.methods:
                self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
                self.send_header("Allow", ", ".join(route.methods))
                self.end_headers()
                return

            rate_limit = route.rate_limit or global_rate_limit
            if rate_limit is not None:
                decision = rate_limiter.check(
                    route,
                    rate_limit,
                    self.client_address[0],
                )
                if not decision.allowed:
                    self._write_json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {"error": "rate_limit_exceeded"},
                        headers={"Retry-After": str(decision.retry_after)},
                    )
                    return

            body_is_valid, body = self._read_request_body()
            if not body_is_valid:
                return

            try:
                target = load_balancer.select_target(
                    route,
                    is_healthy=lambda candidate: health_monitor.is_healthy(
                        route,
                        candidate,
                    ),
                )
                response = proxy_request(
                    route=route,
                    upstream_url=target.url,
                    method=self.command,
                    request_target=self.path,
                    headers=dict(self.headers.items()),
                    body=body,
                    timeout=(
                        route.timeout
                        if route.timeout is not None
                        else global_timeout or DEFAULT_UPSTREAM_TIMEOUT
                    ),
                )
            except NoHealthyTargets:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "no_healthy_upstreams"},
                )
                return
            except UpstreamTimeout:
                self._write_json(
                    HTTPStatus.GATEWAY_TIMEOUT,
                    {"error": "gateway_timeout"},
                )
                return
            except UpstreamError:
                self._write_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "bad_gateway"},
                )
                return
            self._write_upstream_response(response)

        def _read_request_body(self) -> Tuple[bool, Optional[bytes]]:
            content_length_header = self.headers.get("Content-Length")
            if content_length_header is None:
                return True, None

            try:
                content_length = int(content_length_header)
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
                return False, None

            if content_length < 0:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
                return False, None
            return True, self.rfile.read(content_length)

        def _write_upstream_response(self, response: UpstreamResponse) -> None:
            self.send_response(response.status, response.reason)
            for name, value in response.headers:
                if name.lower() not in RESPONSE_HEADERS_NOT_FORWARDED:
                    self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        def _write_json(
            self,
            status: HTTPStatus,
            payload: object,
            headers: Optional[dict[str, str]] = None,
        ) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return GatewayHandler


class GatewayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, *args, health_monitor: HealthMonitor, **kwargs) -> None:
        self.health_monitor = health_monitor
        super().__init__(*args, **kwargs)
        self.health_monitor.start()

    def server_close(self) -> None:
        self.health_monitor.stop()
        super().server_close()


def create_server(
    port: int,
    routes: Sequence[RouteConfig] = (),
    host: str = "",
    global_timeout: Optional[float] = None,
    global_rate_limit: Optional[RateLimitConfig] = None,
    log_requests: bool = True,
) -> HTTPServer:
    started_at = time.monotonic()
    health_monitor = HealthMonitor(routes)
    return GatewayHTTPServer(
        (host, port),
        make_handler(
            started_at,
            routes,
            health_monitor,
            global_timeout,
            global_rate_limit,
            log_requests,
        ),
        health_monitor=health_monitor,
    )


def serve(
    port: int,
    routes: Sequence[RouteConfig] = (),
    global_timeout: Optional[float] = None,
    global_rate_limit: Optional[RateLimitConfig] = None,
) -> None:
    server = create_server(
        port,
        routes,
        global_timeout=global_timeout,
        global_rate_limit=global_rate_limit,
    )
    print(f"GatewayKit listening on http://localhost:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
