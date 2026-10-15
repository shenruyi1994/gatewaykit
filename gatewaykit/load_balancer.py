"""Select an upstream target for each routed request."""

import threading
from typing import Callable, Dict

from gatewaykit.config import RouteConfig, UpstreamTarget


class LoadBalancer:
    def __init__(self) -> None:
        self._positions: Dict[RouteConfig, int] = {}
        self._lock = threading.Lock()

    def select_target(
        self,
        route: RouteConfig,
        is_healthy: Callable[[UpstreamTarget], bool] = lambda target: True,
    ) -> UpstreamTarget:
        targets = tuple(
            target for target in route.upstream.targets if is_healthy(target)
        )
        if not targets:
            raise NoHealthyTargets("no healthy upstream targets are available")
        if len(targets) == 1:
            return targets[0]

        with self._lock:
            position = self._positions.get(route, 0)
            self._positions[route] = position + 1

        if route.upstream.balance == "round_robin":
            return targets[position % len(targets)]

        if route.upstream.balance == "weighted_round_robin":
            slot = position % sum(target.weight for target in targets)
            for target in targets:
                if slot < target.weight:
                    return target
                slot -= target.weight

        raise ValueError("multiple upstream targets require a balancing strategy")


class NoHealthyTargets(RuntimeError):
    """Raised when all targets for a route are unhealthy."""
