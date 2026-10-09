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

    async def test_get_ticket_details_requests_ticket_by_number(self):
        ticket = {"ticket_number": 1234, "subject": "Printer not working", "priority": 10}
        self.mock_api(httpx.Response(200, json=ticket))

        result = await self.call_tool("get_ticket_details", {"ticket_number": 1234})

        self.assertEqual(result.structured_content, ticket)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/tickets/details")
        self.assertEqual(dict(request.url.params), {"ticket_number": "1234"})
        self.assertEqual(request.headers["Authorization"], "test-api-key")

    async def test_get_ticket_details_requires_ticket_number(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaises(ToolError):
            await self.call_tool("get_ticket_details")

        self.assertEqual(self.requests, [])

    async def test_get_ticket_details_raises_when_ticket_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("get_ticket_details", {"ticket_number": 99999})

    async def test_create_ticket_posts_only_given_fields(self):
        created = {"ticket_number": 101, "subject": "Printer not working", "status": "Open"}
        self.mock_api(httpx.Response(200, json=created))

        result = await self.call_tool(
            "create_ticket", {"email": "customer@example.com", "subject": "Printer not working"}
        )

        self.assertEqual(result.structured_content, created)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/apis/v3/tickets/create")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            json.loads(request.content),
            {"email": "customer@example.com", "subject": "Printer not working"},
        )

    async def test_create_ticket_maps_fields_to_api_names(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 102}))

        await self.call_tool(
            "create_ticket",
            {
                "email": "customer@example.com",
                "subject": "Refund request",
                "description": "<p>Charged twice.</p>",
                "status": "Open",
                "priority": 10,
                "type": "Question",
                "assigned_to": "agent@example.com",
                "group": "Billing",
                "category": "Billing",
                "subcategory": "Disputed Charge",
                "form_name": "Create Ticket",
                "custom_fields": {"cf_Country": "USA"},
                "watchers": ["lead@example.com"],
                "share_to": ["manager@example.com"],
            },
        )

        self.assertEqual(
            json.loads(self.requests[0].content),
            {
                "email": "customer@example.com",
                "subject": "Refund request",
                "description": "<p>Charged twice.</p>",
                "status": "Open",
                "priority": 10,
                "type": "Question",
                "assign_to": "agent@example.com",
                "group": "Billing",
                "category": "Billing",
                "sub_category": "Disputed Charge",
                "form_name": "Create Ticket",
                "custom_fields": {"cf_Country": "USA"},
                "watchers": ["lead@example.com"],
                "share_to": ["manager@example.com"],
            },
        )

    async def test_create_ticket_requires_email_and_subject(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaises(ToolError):
            await self.call_tool("create_ticket", {"subject": "No contact"})
        with self.assertRaises(ToolError):
            await self.call_tool("create_ticket", {"email": "customer@example.com"})

        self.assertEqual(self.requests, [])

    async def test_create_ticket_rejects_unknown_priority(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaises(ToolError):
            await self.call_tool(
                "create_ticket",
                {"email": "customer@example.com", "subject": "Help", "priority": 3},
            )

        self.assertEqual(self.requests, [])

    async def test_create_ticket_raises_on_http_error(self):
        self.mock_api(httpx.Response(400, json={"status": 400, "error": "Bad Request"}))

        with self.assertRaises(ToolError):
            await self.call_tool(
                "create_ticket", {"email": "customer@example.com", "subject": "Help"}
            )


if __name__ == "__main__":
    unittest.main()
