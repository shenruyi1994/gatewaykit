"""Tests for matching request paths to configured routes."""

import unittest

from gatewaykit.config import RouteConfig, UpstreamConfig, UpstreamTarget
from gatewaykit.router import find_route


def route(path: str) -> RouteConfig:
    return RouteConfig(
        path=path,
        methods=("GET",),
        strip_prefix=False,
        upstream=UpstreamConfig(
            targets=(UpstreamTarget("http://localhost:3001", 1),),
            balance=None,
        ),
        timeout=None,
        health_check=None,
        rate_limit=None,
    )


class RouterTest(unittest.TestCase):
    def test_matches_exact_path_and_child_path(self) -> None:
        users = route("/api/users")

        self.assertIs(find_route("/api/users", (users,)), users)
        self.assertIs(find_route("/api/users/123?details=true", (users,)), users)

    def test_does_not_match_similar_prefix(self) -> None:
        users = route("/api/users")

        self.assertIsNone(find_route("/api/users-old", (users,)))

    def test_prefers_most_specific_matching_route(self) -> None:
        api = route("/api")
        users = route("/api/users")

        self.assertIs(find_route("/api/users/123", (api, users)), users)


if __name__ == "__main__":
    unittest.main()
