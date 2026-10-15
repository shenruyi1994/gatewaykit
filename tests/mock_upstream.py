"""A small upstream HTTP service used by the gateway tests."""

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockUpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._health_response()
            return
        self._echo_request()

    def do_POST(self) -> None:
        self._echo_request()

    def _health_response(self) -> None:
        status = self.server.health_status
        body = json.dumps(
            {"status": "healthy" if status == HTTPStatus.OK else "unhealthy"},
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _echo_request(self) -> None:
        if self.path.startswith("/slow"):
            time.sleep(0.1)

        content_length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(content_length).decode("utf-8")
        body = json.dumps(
            {
                "method": self.command,
                "path": self.path,
                "body": request_body,
                "content_type": self.headers.get("Content-Type"),
                "request_id": self.headers.get("X-Request-ID"),
                "upstream_port": self.server.server_address[1],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        pass


class MockUpstreamServer(HTTPServer):
    def __init__(self, address, health_status: HTTPStatus = HTTPStatus.OK) -> None:
        self.health_status = health_status
        super().__init__(address, MockUpstreamHandler)


def create_mock_upstream(
    health_status: HTTPStatus = HTTPStatus.OK,
) -> MockUpstreamServer:
    return MockUpstreamServer(("127.0.0.1", 0), health_status)


def main() -> None:
    server = MockUpstreamServer(("127.0.0.1", 3001))
    print("Mock upstream listening on http://localhost:3001", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
