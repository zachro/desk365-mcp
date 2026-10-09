import logging

from fastmcp import FastMCP


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

mcp = FastMCP('desk365-mcp')
env_config: dict[str, str] = {}


def run_server(config: dict[str, str]):
    env_config.update(config)
    mcp.run(transport='streamable-http', port=8000, path='/')
