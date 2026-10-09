import json
import unittest
from unittest.mock import patch

import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from desk365_mcp import api, server


class ToolTests(unittest.IsolatedAsyncioTestCase):
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

    async def call_tool(self, name, arguments=None):
        async with Client(server.mcp) as client:
            return await client.call_tool(name, arguments or {})

    async def test_ping_returns_api_status(self):
        self.mock_api(httpx.Response(200, text="All good! Desk365 APIs are running fine"))

        result = await self.call_tool("ping")

        self.assertEqual(result.data, "All good! Desk365 APIs are running fine")
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://acme.desk365.io/apis/v3/ping")
        self.assertEqual(request.headers["Authorization"], "test-api-key")

    async def test_ping_raises_on_http_error(self):
        self.mock_api(httpx.Response(503, text="Service Unavailable"))

        with self.assertRaises(ToolError):
            await self.call_tool("ping")

    async def test_list_tickets_sends_default_params(self):
        tickets = {"count": 1, "tickets": [{"ticket_number": 10, "subject": "Printer not working"}]}
        self.mock_api(httpx.Response(200, json=tickets))

        result = await self.call_tool("list_tickets")

        self.assertEqual(result.structured_content, tickets)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/tickets")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            dict(request.url.params),
            {
                "ticket_count": "30",
                "offset": "0",
                "include_description": "0",
                "include_custom_fields": "0",
                "include_survey_details": "0",
                "order_by": "created_time",
                "order_type": "desc",
            },
        )

    async def test_list_tickets_converts_options_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))
        filters = {"status": ["Open", "Pending"], "custom_fields": {"cf_Country": ["USA"]}}

        await self.call_tool(
            "list_tickets",
            {
                "ticket_count": 100,
                "offset": 100,
                "include_description": True,
                "order_by": "updated_time",
                "order_type": "asc",
                "updated_since": "2026-10-01 00:00:00",
                "filters": filters,
            },
        )

        params = self.requests[0].url.params
        self.assertEqual(params["ticket_count"], "100")
        self.assertEqual(params["offset"], "100")
        self.assertEqual(params["include_description"], "1")
        self.assertEqual(params["order_by"], "updated_time")
        self.assertEqual(params["order_type"], "asc")
        self.assertEqual(params["updated_since"], "2026-10-01 00:00:00")
        self.assertEqual(json.loads(params["filters"]), filters)

    async def test_list_tickets_rejects_unsupported_ticket_count(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        with self.assertRaises(ToolError):
            await self.call_tool("list_tickets", {"ticket_count": 25})

        self.assertEqual(self.requests, [])

    async def test_list_tickets_raises_on_http_error(self):
        self.mock_api(httpx.Response(401, json={"status": 401, "error": "Unauthorized"}))

        with self.assertRaises(ToolError):
            await self.call_tool("list_tickets")


if __name__ == "__main__":
    unittest.main()
