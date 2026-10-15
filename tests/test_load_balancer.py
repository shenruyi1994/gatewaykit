"""Tests for upstream target selection."""

import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

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
        rate_limit=None,
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

    def test_weighted_selection_is_consistent_under_concurrency(self) -> None:
        products = route("weighted_round_robin", first_weight=3)
        balancer = LoadBalancer()

        with ThreadPoolExecutor(max_workers=8) as executor:
            selected = list(
                executor.map(
                    lambda _: balancer.select_target(products).url,
                    range(80),
                )
            )

        self.assertEqual(
            Counter(selected),
            Counter({"http://first": 60, "http://second": 20}),
        )


if __name__ == "__main__":
    unittest.main()
