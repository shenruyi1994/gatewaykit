"""GatewayKit's minimal inbound HTTP server."""

from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Sequence, Type

from gatewaykit.config import RouteConfig
from gatewaykit.router import find_route


def make_handler(
    started_at: float,
    routes: Sequence[RouteConfig],
) -> Type[BaseHTTPRequestHandler]:
    class GatewayHandler(BaseHTTPRequestHandler):
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

        def do_POST(self) -> None:
            self._handle_route()

        def do_PUT(self) -> None:
            self._handle_route()

        def do_PATCH(self) -> None:
            self._handle_route()

        def do_DELETE(self) -> None:
            self._handle_route()

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

            self.send_error(HTTPStatus.NOT_IMPLEMENTED, "proxying not implemented")

        def _write_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return GatewayHandler


def create_server(
    port: int,
    routes: Sequence[RouteConfig] = (),
    host: str = "",
) -> HTTPServer:
    started_at = time.monotonic()
    return HTTPServer((host, port), make_handler(started_at, routes))


def serve(port: int, routes: Sequence[RouteConfig] = ()) -> None:
    server = create_server(port, routes)
    print(f"GatewayKit listening on http://localhost:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
