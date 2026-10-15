"""Run GatewayKit using a YAML configuration file."""

import argparse

from gatewaykit.config import ConfigError, load_config
from gatewaykit.server import serve


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GatewayKit")
    parser.add_argument("config", help="path to the gateway YAML configuration")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as error:
        raise SystemExit(f"configuration error: {error}") from error

    serve(port=config.port, routes=config.routes)


if __name__ == "__main__":
    main()
