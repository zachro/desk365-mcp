import logging

from fastmcp import FastMCP

from desk365_mcp import api


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

mcp = FastMCP('desk365-mcp')
env_config: dict[str, str] = {}


@mcp.tool
async def ping() -> str:
    """Check whether the Desk365 API is up and reachable."""
    logger.info('Tool called: ping')
    return await api.ping(env_config)


def run_server(config: dict[str, str]):
    env_config.update(config)
    mcp.run(transport='streamable-http', port=8000, path='/')
