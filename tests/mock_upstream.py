"""A small upstream HTTP service used by the gateway tests."""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockUpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._echo_request()

    def do_POST(self) -> None:
        self._echo_request()

    def _echo_request(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(content_length).decode("utf-8")
        body = json.dumps(
            {
                "method": self.command,
                "path": self.path,
                "body": request_body,
                "content_type": self.headers.get("Content-Type"),
                "request_id": self.headers.get("X-Request-ID"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def create_mock_upstream() -> HTTPServer:
    return HTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
