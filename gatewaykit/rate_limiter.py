"""In-memory fixed-window and sliding-window request limiting."""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Tuple

from gatewaykit.config import RateLimitConfig, RouteConfig


BucketKey = Tuple[str, str]


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._fixed_windows: Dict[BucketKey, Tuple[float, int]] = {}
        self._sliding_windows: Dict[BucketKey, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        route: RouteConfig,
        policy: RateLimitConfig,
        client_ip: str,
    ) -> RateLimitDecision:
        bucket = client_ip if policy.per == "ip" else "global"
        key = (route.path, bucket)
        now = self._clock()

        with self._lock:
            if policy.strategy == "fixed_window":
                return self._check_fixed_window(key, policy, now)
            return self._check_sliding_window(key, policy, now)

    def _check_fixed_window(
        self,
        key: BucketKey,
        policy: RateLimitConfig,
        now: float,
    ) -> RateLimitDecision:
        window_start, count = self._fixed_windows.get(key, (now, 0))
        if now >= window_start + policy.window:
            window_start, count = now, 0

        if count >= policy.requests:
            retry_after = math.ceil(window_start + policy.window - now)
            return RateLimitDecision(False, max(1, retry_after))

        self._fixed_windows[key] = (window_start, count + 1)
        return RateLimitDecision(True)

    def _check_sliding_window(
        self,
        key: BucketKey,
        policy: RateLimitConfig,
        now: float,
    ) -> RateLimitDecision:
        requests = self._sliding_windows.setdefault(key, deque())
        cutoff = now - policy.window
        while requests and requests[0] <= cutoff:
            requests.popleft()

        if len(requests) >= policy.requests:
            retry_after = math.ceil(requests[0] + policy.window - now)
            return RateLimitDecision(False, max(1, retry_after))

        requests.append(now)
        return RateLimitDecision(True)
