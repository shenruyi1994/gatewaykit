"""Actively monitor configured upstream targets."""

import socket
import threading
import time
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Dict, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

from gatewaykit.config import RouteConfig, UpstreamTarget


HealthKey = Tuple[RouteConfig, UpstreamTarget]


class HealthMonitor:
    def __init__(self, routes: Sequence[RouteConfig]) -> None:
        self._checks = tuple(
            (route, target)
            for route in routes
            if route.health_check is not None
            for target in route.upstream.targets
        )
        self._failures: Dict[HealthKey, int] = {}
        self._unhealthy: Set[HealthKey] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self._checks or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def is_healthy(self, route: RouteConfig, target: UpstreamTarget) -> bool:
        with self._lock:
            return (route, target) not in self._unhealthy

    def _run(self) -> None:
        next_checks = {key: 0.0 for key in self._checks}
        while not self._stop.is_set():
            now = time.monotonic()
            for route, target in self._checks:
                key = (route, target)
                if next_checks[key] <= now:
                    self._record_result(route, target, self._check(route, target))
                    next_checks[key] = time.monotonic() + route.health_check.interval

            wait = max(0.0, min(next_checks.values()) - time.monotonic())
            self._stop.wait(wait)

    def _check(self, route: RouteConfig, target: UpstreamTarget) -> bool:
        upstream = urlsplit(target.url)
        connection_class = HTTPSConnection if upstream.scheme == "https" else HTTPConnection
        timeout = min(route.timeout or 1.0, 1.0)
        connection = connection_class(upstream.hostname, upstream.port, timeout=timeout)
        try:
            connection.request("GET", route.health_check.path)
            response = connection.getresponse()
            response.read()
            return 200 <= response.status < 400
        except (HTTPException, OSError, socket.timeout):
            return False
        finally:
            connection.close()

    def _record_result(
        self,
        route: RouteConfig,
        target: UpstreamTarget,
        succeeded: bool,
    ) -> None:
        key = (route, target)
        with self._lock:
            if succeeded:
                self._failures[key] = 0
                self._unhealthy.discard(key)
                return

            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            if failures >= route.health_check.unhealthy_threshold:
                self._unhealthy.add(key)

