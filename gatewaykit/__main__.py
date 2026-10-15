"""Run GatewayKit on its required default port."""

from gatewaykit.server import serve


def main() -> None:
    serve(port=8080)


if __name__ == "__main__":
    main()
