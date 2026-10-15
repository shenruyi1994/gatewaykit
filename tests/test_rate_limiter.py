"""Tests for config-driven request rate limiting."""

import unittest

from gatewaykit.config import (
    RateLimitConfig,
    RouteConfig,
    UpstreamConfig,
    UpstreamTarget,
)
from gatewaykit.rate_limiter import RateLimiter


def route(path: str = "/api/example") -> RouteConfig:
    return RouteConfig(
        path=path,
        methods=("GET",),
        strip_prefix=False,
        upstream=UpstreamConfig(
            targets=(UpstreamTarget("http://upstream", 1),),
            balance=None,
        ),
        timeout=None,
        health_check=None,
        rate_limit=None,
    )


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class RateLimiterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.limiter = RateLimiter(clock=self.clock)

    def test_fixed_window_resets_after_window_ends(self) -> None:
        policy = RateLimitConfig(2, 10, "fixed_window", "ip")
        example = route()

        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        blocked = self.limiter.check(example, policy, "client-a")
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after, 10)

        self.clock.now = 10
        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)

    def test_sliding_window_expires_individual_requests(self) -> None:
        policy = RateLimitConfig(2, 10, "sliding_window", "ip")
        example = route()

        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        self.clock.now = 4
        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        self.clock.now = 9
        self.assertFalse(self.limiter.check(example, policy, "client-a").allowed)

        self.clock.now = 10
        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)

    def test_ip_buckets_are_independent(self) -> None:
        policy = RateLimitConfig(1, 10, "fixed_window", "ip")
        example = route()

        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        self.assertFalse(self.limiter.check(example, policy, "client-a").allowed)
        self.assertTrue(self.limiter.check(example, policy, "client-b").allowed)

    def test_global_bucket_is_shared_by_clients(self) -> None:
        policy = RateLimitConfig(1, 10, "fixed_window", "global")
        example = route()

        self.assertTrue(self.limiter.check(example, policy, "client-a").allowed)
        self.assertFalse(self.limiter.check(example, policy, "client-b").allowed)

    def test_routes_have_independent_buckets(self) -> None:
        policy = RateLimitConfig(1, 10, "fixed_window", "global")

        self.assertTrue(self.limiter.check(route("/one"), policy, "client").allowed)
        self.assertTrue(self.limiter.check(route("/two"), policy, "client").allowed)


if __name__ == "__main__":
    unittest.main()
