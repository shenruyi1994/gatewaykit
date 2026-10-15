"""Select an upstream target for each routed request."""

from typing import Dict

from gatewaykit.config import RouteConfig, UpstreamTarget


class LoadBalancer:
    def __init__(self) -> None:
        self._positions: Dict[RouteConfig, int] = {}

    def select_target(self, route: RouteConfig) -> UpstreamTarget:
        targets = route.upstream.targets
        if len(targets) == 1:
            return targets[0]

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

