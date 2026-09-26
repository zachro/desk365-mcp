import logging

from fastmcp import FastMCP

from config import ENV_CONFIG


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

mcp = FastMCP('desk365-mcp')


def run_server():
    mcp.run(transport='streamable-http', port=8000, path='/')


if __name__ == '__main__':
    run_server()
