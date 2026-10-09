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

    async def test_search_tickets_sends_default_params(self):
        results = {"count": 1, "tickets": [{"ticket_number": 10, "subject": "Printer offline"}]}
        self.mock_api(httpx.Response(200, json=results))

        result = await self.call_tool("search_tickets", {"query": "printer offline"})

        self.assertEqual(result.structured_content, results)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/tickets/search")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        params = dict(request.url.params)
        self.assertEqual(
            json.loads(params.pop("search_query")),
            {"query": "printer offline", "search_in": [1, 2, 3, 4, 5, 6]},
        )
        self.assertEqual(
            params,
            {
                "search_type": "1",
                "ticket_count": "30",
                "offset": "0",
                "include_description": "0",
                "include_custom_fields": "0",
                "include_survey_details": "0",
                "order_by": "relevance",
                "include_merged": "1",
            },
        )

    async def test_search_tickets_converts_options_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await self.call_tool(
            "search_tickets",
            {
                "query": "invoice",
                "search_in": ["subject", "conversations"],
                "include_archived": True,
                "ticket_count": 50,
                "offset": 50,
                "include_description": True,
                "order_by": "created_time",
                "include_merged": False,
            },
        )

        params = self.requests[0].url.params
        self.assertEqual(
            json.loads(params["search_query"]), {"query": "invoice", "search_in": [1, 3, 7]}
        )
        self.assertEqual(params["ticket_count"], "50")
        self.assertEqual(params["offset"], "50")
        self.assertEqual(params["include_description"], "1")
        self.assertEqual(params["order_by"], "created_time")
        self.assertEqual(params["include_merged"], "0")

    async def test_search_tickets_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [
            {},
            {"query": ""},
            {"query": "invoice", "search_in": ["notes"]},
            {"query": "invoice", "ticket_count": 25},
            {"query": "invoice", "order_by": "priority"},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("search_tickets", arguments)

        self.assertEqual(self.requests, [])

    async def test_search_tickets_raises_on_http_error(self):
        self.mock_api(httpx.Response(429, json={"status": 429, "error": "Too Many Requests"}))

        with self.assertRaises(ToolError):
            await self.call_tool("search_tickets", {"query": "invoice"})

    async def test_advanced_search_tickets_sends_search_terms(self):
        results = {"count": 1, "tickets": [{"ticket_number": 130}]}
        self.mock_api(httpx.Response(200, json=results))

        result = await self.call_tool(
            "advanced_search_tickets",
            {"terms": {"subject": "VPN", "cf_Site": "Denver"}, "order_by": "updated_time"},
        )

        self.assertEqual(result.structured_content, results)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/tickets/search")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        params = dict(request.url.params)
        self.assertEqual(
            json.loads(params.pop("search_query")),
            {
                "search_term": [
                    {"query": "VPN", "search_in": ["subject"]},
                    {"query": "Denver", "search_in": ["cf_Site"]},
                ]
            },
        )
        self.assertEqual(
            params,
            {
                "search_type": "2",
                "ticket_count": "30",
                "offset": "0",
                "include_description": "0",
                "include_custom_fields": "0",
                "include_survey_details": "0",
                "order_by": "updated_time",
                "include_merged": "1",
            },
        )

    async def test_advanced_search_tickets_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [
            {},
            {"terms": {}},
            {"terms": {"status": "Open"}},
            {"terms": {"subject": "VPN"}, "ticket_count": 25},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("advanced_search_tickets", arguments)

        self.assertEqual(self.requests, [])

    async def test_advanced_search_tickets_raises_on_http_error(self):
        self.mock_api(httpx.Response(400, json={"status": 400, "error": "Bad Request"}))

        with self.assertRaises(ToolError):
            await self.call_tool("advanced_search_tickets", {"terms": {"subject": "VPN"}})

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

    async def test_get_ticket_conversations_sends_default_params(self):
        conversations = {
            "count": 1,
            "conversations": [
                {
                    "id": 1,
                    "type": "note",
                    "public_note": False,
                    "sender_type": "agent",
                    "body_text": "On it.",
                }
            ],
        }
        self.mock_api(httpx.Response(200, json=conversations))

        result = await self.call_tool("get_ticket_conversations", {"ticket_number": 1234})

        self.assertEqual(result.structured_content, conversations)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/tickets/conversations")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            dict(request.url.params),
            {
                "ticket_number": "1234",
                "sort_by": "earliest_on_top",
                "include_contact_replies": "1",
                "include_agent_replies": "1",
                "include_private_notes": "1",
                "include_public_notes": "1",
                "include_forward_messages": "1",
            },
        )

    async def test_get_ticket_conversations_converts_options_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "conversations": []}))

        await self.call_tool(
            "get_ticket_conversations",
            {
                "ticket_number": 1234,
                "sort_by": "latest_on_top",
                "include_private_notes": False,
                "include_forward_messages": False,
            },
        )

        params = self.requests[0].url.params
        self.assertEqual(params["sort_by"], "latest_on_top")
        self.assertEqual(params["include_contact_replies"], "1")
        self.assertEqual(params["include_agent_replies"], "1")
        self.assertEqual(params["include_private_notes"], "0")
        self.assertEqual(params["include_public_notes"], "1")
        self.assertEqual(params["include_forward_messages"], "0")

    async def test_get_ticket_conversations_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaises(ToolError):
            await self.call_tool("get_ticket_conversations")
        with self.assertRaises(ToolError):
            await self.call_tool(
                "get_ticket_conversations", {"ticket_number": 1234, "sort_by": "newest"}
            )

        self.assertEqual(self.requests, [])

    async def test_get_ticket_conversations_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("get_ticket_conversations", {"ticket_number": 99999})

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

    async def test_add_ticket_reply_posts_reply(self):
        reply = {"id": 1, "ticket_number": 1234, "body": "On it."}
        self.mock_api(httpx.Response(200, json=reply))

        result = await self.call_tool("add_ticket_reply", {"ticket_number": 1234, "body": "On it."})

        self.assertEqual(result.structured_content, reply)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/apis/v3/tickets/add_reply")
        self.assertEqual(dict(request.url.params), {"ticket_number": "1234"})
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            json.loads(request.content),
            {"body": "On it.", "include_prev_ccs": 0, "include_prev_messages": 0},
        )

    async def test_add_ticket_reply_maps_options_to_api_fields(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await self.call_tool(
            "add_ticket_reply",
            {
                "ticket_number": 1234,
                "body": "On it.",
                "cc_emails": ["a@example.com", "b@example.com"],
                "bcc_emails": ["c@example.com"],
                "agent_email": "agent@example.com",
                "from_email": "support@example.com",
                "include_prev_ccs": True,
                "include_prev_messages": True,
            },
        )

        self.assertEqual(
            json.loads(self.requests[0].content),
            {
                "body": "On it.",
                "cc_emails": "a@example.com,b@example.com",
                "bcc_emails": "c@example.com",
                "agent_email": "agent@example.com",
                "from_email": "support@example.com",
                "include_prev_ccs": 1,
                "include_prev_messages": 1,
            },
        )

    async def test_add_ticket_reply_uses_default_agent_email(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        server.env_config["DEFAULT_AGENT_EMAIL"] = "default@example.com"

        await self.call_tool("add_ticket_reply", {"ticket_number": 1234, "body": "On it."})
        await self.call_tool(
            "add_ticket_reply",
            {"ticket_number": 1234, "body": "On it.", "agent_email": "agent@example.com"},
        )

        self.assertEqual(json.loads(self.requests[0].content)["agent_email"], "default@example.com")
        self.assertEqual(json.loads(self.requests[1].content)["agent_email"], "agent@example.com")

    async def test_add_ticket_reply_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [
            {"body": "On it."},
            {"ticket_number": 1234},
            {"ticket_number": 1234, "body": ""},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("add_ticket_reply", arguments)

        self.assertEqual(self.requests, [])

    async def test_add_ticket_reply_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("add_ticket_reply", {"ticket_number": 99999, "body": "On it."})

    async def test_add_ticket_note_posts_private_note_by_default(self):
        note = {"id": 1, "ticket_number": 1234, "body": "Checked logs.", "private_note": 1}
        self.mock_api(httpx.Response(200, json=note))

        result = await self.call_tool(
            "add_ticket_note", {"ticket_number": 1234, "body": "Checked logs."}
        )

        self.assertEqual(result.structured_content, note)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/apis/v3/tickets/add_note")
        self.assertEqual(dict(request.url.params), {"ticket_number": "1234"})
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            json.loads(request.content), {"body": "Checked logs.", "private_note": 1}
        )

    async def test_add_ticket_note_maps_options_to_api_fields(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await self.call_tool(
            "add_ticket_note",
            {
                "ticket_number": 1234,
                "body": "Fixed.",
                "private": False,
                "notify_emails": ["a@example.com"],
                "agent_email": "agent@example.com",
            },
        )

        self.assertEqual(
            json.loads(self.requests[0].content),
            {
                "body": "Fixed.",
                "private_note": 0,
                "notify_emails": "a@example.com",
                "agent_email": "agent@example.com",
            },
        )

    async def test_add_ticket_note_uses_default_agent_email(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        server.env_config["DEFAULT_AGENT_EMAIL"] = "default@example.com"

        await self.call_tool("add_ticket_note", {"ticket_number": 1234, "body": "Checked."})
        await self.call_tool(
            "add_ticket_note",
            {"ticket_number": 1234, "body": "Checked.", "agent_email": "agent@example.com"},
        )

        self.assertEqual(json.loads(self.requests[0].content)["agent_email"], "default@example.com")
        self.assertEqual(json.loads(self.requests[1].content)["agent_email"], "agent@example.com")

    async def test_add_ticket_note_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [
            {"body": "Checked logs."},
            {"ticket_number": 1234},
            {"ticket_number": 1234, "body": "  "},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("add_ticket_note", arguments)

        self.assertEqual(self.requests, [])

    async def test_add_ticket_note_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("add_ticket_note", {"ticket_number": 99999, "body": "Checked."})

    async def test_update_ticket_puts_given_fields(self):
        ticket = {"ticket_number": 1234, "status": "Resolved"}
        self.mock_api(httpx.Response(200, json=ticket))

        result = await self.call_tool(
            "update_ticket", {"ticket_number": 1234, "status": "Resolved"}
        )

        self.assertEqual(result.structured_content, ticket)
        request = self.requests[0]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.url.path, "/apis/v3/tickets/update")
        self.assertEqual(dict(request.url.params), {"ticket_number": "1234"})
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(json.loads(request.content), {"status": "Resolved"})

    async def test_update_ticket_maps_fields_to_api_names(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 1234}))

        await self.call_tool(
            "update_ticket",
            {
                "ticket_number": 1234,
                "contact_email": "customer@example.com",
                "subject": "Refund request",
                "description": "<p>Charged twice.</p>",
                "sla": "Standard SLA",
                "status": "Open",
                "priority": 10,
                "type": "Question",
                "assigned_to": "agent@example.com",
                "group": "Billing",
                "category": "Billing",
                "subcategory": "Disputed Charge",
                "custom_fields": {"cf_Country": "USA"},
                "add_watchers": ["lead@example.com"],
                "remove_watchers": ["old-lead@example.com"],
                "add_share_to": ["manager@example.com"],
                "remove_share_to": ["old-manager@example.com"],
            },
        )

        self.assertEqual(
            json.loads(self.requests[0].content),
            {
                "contact_email": "customer@example.com",
                "subject": "Refund request",
                "description": "<p>Charged twice.</p>",
                "sla": "Standard SLA",
                "status": "Open",
                "priority": 10,
                "type": "Question",
                "assign_to": "agent@example.com",
                "group": "Billing",
                "category": "Billing",
                "sub_category": "Disputed Charge",
                "custom_fields": {"cf_Country": "USA"},
                "watchers": {"add": ["lead@example.com"], "remove": ["old-lead@example.com"]},
                "share_to": {
                    "add": ["manager@example.com"],
                    "remove": ["old-manager@example.com"],
                },
            },
        )

    async def test_update_ticket_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [
            {"status": "Closed"},
            {"ticket_number": 1234},
            {"ticket_number": 1234, "priority": 3},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("update_ticket", arguments)

        self.assertEqual(self.requests, [])

    async def test_update_ticket_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("update_ticket", {"ticket_number": 99999, "status": "Closed"})

    async def test_list_contacts_sends_default_params(self):
        contacts = {"count": 1, "content": [{"name": "Jane Doe", "email": "jane@example.com"}]}
        self.mock_api(httpx.Response(200, json=contacts))

        result = await self.call_tool("list_contacts")

        self.assertEqual(result.structured_content, contacts)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/apis/v3/contacts")
        self.assertEqual(request.headers["Authorization"], "test-api-key")
        self.assertEqual(
            dict(request.url.params),
            {"offset": "0", "order_by": "1", "order_type": "asc", "include_custom_fields": "0"},
        )

    async def test_list_contacts_converts_options_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "content": []}))

        await self.call_tool(
            "list_contacts",
            {
                "company": "Example Corp",
                "offset": 60,
                "order_by": "company",
                "order_type": "desc",
                "include_custom_fields": True,
            },
        )

        self.assertEqual(
            dict(self.requests[0].url.params),
            {
                "company": "Example Corp",
                "offset": "60",
                "order_by": "3",
                "order_type": "desc",
                "include_custom_fields": "1",
            },
        )

    async def test_list_contacts_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [{"order_by": "phone"}, {"order_type": "up"}]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("list_contacts", arguments)

        self.assertEqual(self.requests, [])

    async def test_list_contacts_raises_on_http_error(self):
        self.mock_api(httpx.Response(401, json={"status": 401, "error": "Unauthorized"}))

        with self.assertRaises(ToolError):
            await self.call_tool("list_contacts")

    async def test_get_contact_details_looks_up_by_email(self):
        contact = {"name": "Jane Doe", "primary_email": "jane@example.com"}
        self.mock_api(httpx.Response(200, json=contact))

        result = await self.call_tool("get_contact_details", {"email": "jane@example.com"})
        await self.call_tool(
            "get_contact_details", {"email": "jane@other.example.com", "secondary": True}
        )

        self.assertEqual(result.structured_content, contact)
        self.assertEqual(self.requests[0].url.path, "/apis/v3/contacts/details")
        self.assertEqual(self.requests[0].headers["Authorization"], "test-api-key")
        self.assertEqual(dict(self.requests[0].url.params), {"primary_email": "jane@example.com"})
        self.assertEqual(
            dict(self.requests[1].url.params), {"secondary_email": "jane@other.example.com"}
        )

    async def test_get_contact_details_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for arguments in [{}, {"email": ""}]:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.call_tool("get_contact_details", arguments)

        self.assertEqual(self.requests, [])

    async def test_get_contact_details_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(ToolError):
            await self.call_tool("get_contact_details", {"email": "nobody@example.com"})


if __name__ == "__main__":
    unittest.main()
