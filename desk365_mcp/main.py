import argparse

from desk365_mcp.config import get_env_config
from desk365_mcp.server import run_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the desk365 MCP server.')
    parser.add_argument(
        '--stage',
        help='Load <stage>.env instead of .env (e.g. --stage dev loads dev.env).',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    env_config = get_env_config(args.stage)
    run_server(env_config)


if __name__ == "__main__":
    main()
