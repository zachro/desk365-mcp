import unittest
from unittest.mock import patch

import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from desk365_mcp import api, server


class PingToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = patch.dict(server.env_config, {"API_KEY": "test-api-key", "SUBDOMAIN": "acme"})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.requests = []

    def mock_api(self, response):
        def handler(request):
            self.requests.append(request)
            return response

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        patcher = patch.object(
            api.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def call_ping(self):
        async with Client(server.mcp) as client:
            return await client.call_tool("ping")

    async def test_ping_returns_api_status(self):
        self.mock_api(httpx.Response(200, text="All good! Desk365 APIs are running fine"))

        result = await self.call_ping()

        self.assertEqual(result.data, "All good! Desk365 APIs are running fine")
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://acme.desk365.io/apis/v3/ping")
        self.assertEqual(request.headers["Authorization"], "test-api-key")

    async def test_ping_raises_on_http_error(self):
        self.mock_api(httpx.Response(503, text="Service Unavailable"))

        with self.assertRaises(ToolError):
            await self.call_ping()


if __name__ == "__main__":
    unittest.main()
