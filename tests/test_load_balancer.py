"""Tests for upstream target selection."""

import unittest

from gatewaykit.config import RouteConfig, UpstreamConfig, UpstreamTarget
from gatewaykit.load_balancer import LoadBalancer, NoHealthyTargets


def route(balance: str, first_weight: int = 1) -> RouteConfig:
    return RouteConfig(
        path="/api/products",
        methods=("GET",),
        strip_prefix=True,
        upstream=UpstreamConfig(
            targets=(
                UpstreamTarget("http://first", first_weight),
                UpstreamTarget("http://second", 1),
            ),
            balance=balance,
        ),
        timeout=None,
        health_check=None,
    )


class LoadBalancerTest(unittest.TestCase):
    def test_round_robin_alternates_targets(self) -> None:
        products = route("round_robin")
        balancer = LoadBalancer()

        selected = [balancer.select_target(products).url for _ in range(4)]

        self.assertEqual(
            selected,
            ["http://first", "http://second", "http://first", "http://second"],
        )

    def test_weighted_round_robin_honors_target_weights(self) -> None:
        products = route("weighted_round_robin", first_weight=3)
        balancer = LoadBalancer()

        selected = [balancer.select_target(products).url for _ in range(8)]

        self.assertEqual(
            selected,
            [
                "http://first",
                "http://first",
                "http://first",
                "http://second",
                "http://first",
                "http://first",
                "http://first",
                "http://second",
            ],
        )

    def test_unhealthy_target_is_skipped(self) -> None:
        products = route("weighted_round_robin", first_weight=3)
        balancer = LoadBalancer()

        selected = balancer.select_target(
            products,
            is_healthy=lambda target: target.url == "http://second",
        )

        self.assertEqual(selected.url, "http://second")

    def test_all_unhealthy_targets_raise_no_healthy_targets(self) -> None:
        products = route("weighted_round_robin", first_weight=3)
        balancer = LoadBalancer()

        with self.assertRaises(NoHealthyTargets):
            balancer.select_target(products, is_healthy=lambda target: False)


if __name__ == "__main__":
    unittest.main()
