import json
import unittest
from unittest.mock import patch

import httpx

from desk365_mcp import api


ENV_CONFIG = {"API_KEY": "test-api-key", "SUBDOMAIN": "acme"}


class HelperTests(unittest.TestCase):
    def test_api_url_uses_subdomain_and_v3_path(self):
        self.assertEqual(
            api._api_url(ENV_CONFIG, "tickets/details"),
            "https://acme.desk365.io/apis/v3/tickets/details",
        )

    def test_headers_send_api_key_as_authorization(self):
        self.assertEqual(api._headers(ENV_CONFIG), {"Authorization": "test-api-key"})

    def test_flag_converts_bool_to_api_string(self):
        self.assertEqual(api._flag(True), "1")
        self.assertEqual(api._flag(False), "0")


class ApiTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
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

    @property
    def request(self):
        self.assertEqual(len(self.requests), 1)
        return self.requests[0]


class RequestTests(ApiTestCase):
    async def test_get_sends_auth_and_params(self):
        self.mock_api(httpx.Response(200, text="ok"))

        response = await api._get(ENV_CONFIG, "tickets", {"offset": "30"})

        self.assertEqual(response.text, "ok")
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(str(self.request.url), "https://acme.desk365.io/apis/v3/tickets?offset=30")
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_post_sends_auth_and_json_body(self):
        self.mock_api(httpx.Response(200, json={}))

        await api._post(ENV_CONFIG, "tickets/create", {"subject": "Help"})

        self.assertEqual(self.request.method, "POST")
        self.assertEqual(str(self.request.url), "https://acme.desk365.io/apis/v3/tickets/create")
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")
        self.assertEqual(self.request.headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(self.request.content), {"subject": "Help"})

    async def test_get_raises_on_http_error(self):
        self.mock_api(httpx.Response(401, json={"status": 401, "error": "Unauthorized"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api._get(ENV_CONFIG, "tickets")

        self.assertEqual(error.exception.response.status_code, 401)

    async def test_post_raises_on_http_error(self):
        self.mock_api(httpx.Response(500, json={"status": 500, "error": "Server Error"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api._post(ENV_CONFIG, "tickets/create", {})

        self.assertEqual(error.exception.response.status_code, 500)


class PingTests(ApiTestCase):
    async def test_returns_response_text(self):
        self.mock_api(httpx.Response(200, text="All good! Desk365 APIs are running fine"))

        result = await api.ping(ENV_CONFIG)

        self.assertEqual(result, "All good! Desk365 APIs are running fine")
        self.assertEqual(self.request.url.path, "/apis/v3/ping")

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(503, text="Service Unavailable"))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.ping(ENV_CONFIG)


class ListTicketsTests(ApiTestCase):
    async def test_returns_parsed_json(self):
        tickets = {"count": 1, "tickets": [{"ticket_number": 10}]}
        self.mock_api(httpx.Response(200, json=tickets))

        result = await api.list_tickets(ENV_CONFIG)

        self.assertEqual(result, tickets)
        self.assertEqual(self.request.url.path, "/apis/v3/tickets")

    async def test_sends_default_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.list_tickets(ENV_CONFIG)

        self.assertEqual(
            dict(self.request.url.params),
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

    async def test_converts_arguments_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))
        filters = {
            "status": ["Open"],
            "type": ["Customer's \"Request\""],
            "custom_fields": {"cf_Country": ["USA"]},
            "include_merged": 0,
        }

        await api.list_tickets(
            ENV_CONFIG,
            ticket_count=50,
            offset=50,
            include_description=True,
            include_custom_fields=True,
            include_survey_details=True,
            order_by="updated_time",
            order_type="asc",
            updated_since="2026-10-01 00:00:00",
            filters=filters,
        )

        params = self.request.url.params
        self.assertEqual(params["ticket_count"], "50")
        self.assertEqual(params["offset"], "50")
        self.assertEqual(params["include_description"], "1")
        self.assertEqual(params["include_custom_fields"], "1")
        self.assertEqual(params["include_survey_details"], "1")
        self.assertEqual(params["order_by"], "updated_time")
        self.assertEqual(params["order_type"], "asc")
        self.assertEqual(params["updated_since"], "2026-10-01 00:00:00")
        self.assertEqual(json.loads(params["filters"]), filters)

    async def test_omits_empty_updated_since_and_filters(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.list_tickets(ENV_CONFIG, updated_since="", filters={})

        self.assertNotIn("updated_since", self.request.url.params)
        self.assertNotIn("filters", self.request.url.params)

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(403, json={"status": 403, "error": "Forbidden"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.list_tickets(ENV_CONFIG)


class GetTicketDetailsTests(ApiTestCase):
    async def test_requests_ticket_by_number(self):
        ticket = {"ticket_number": 1234, "subject": "Printer not working"}
        self.mock_api(httpx.Response(200, json=ticket))

        result = await api.get_ticket_details(ENV_CONFIG, 1234)

        self.assertEqual(result, ticket)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/details")
        self.assertEqual(dict(self.request.url.params), {"ticket_number": "1234"})

    async def test_raises_when_ticket_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.get_ticket_details(ENV_CONFIG, 99999)

        self.assertEqual(error.exception.response.status_code, 404)


class GetTicketConversationsTests(ApiTestCase):
    async def test_returns_parsed_json(self):
        conversations = {
            "count": 1,
            "conversations": [
                {"id": 1, "type": "reply", "sender_type": "contact", "body_text": "Any update?"}
            ],
        }
        self.mock_api(httpx.Response(200, json=conversations))

        result = await api.get_ticket_conversations(ENV_CONFIG, 1234)

        self.assertEqual(result, conversations)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/conversations")

    async def test_sends_default_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "conversations": []}))

        await api.get_ticket_conversations(ENV_CONFIG, 1234)

        self.assertEqual(
            dict(self.request.url.params),
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

    async def test_converts_arguments_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "conversations": []}))

        await api.get_ticket_conversations(
            ENV_CONFIG,
            1234,
            sort_by="latest_on_top",
            include_contact_replies=False,
            include_agent_replies=False,
            include_private_notes=False,
            include_public_notes=False,
            include_forward_messages=False,
        )

        self.assertEqual(
            dict(self.request.url.params),
            {
                "ticket_number": "1234",
                "sort_by": "latest_on_top",
                "include_contact_replies": "0",
                "include_agent_replies": "0",
                "include_private_notes": "0",
                "include_public_notes": "0",
                "include_forward_messages": "0",
            },
        )

    async def test_raises_when_ticket_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.get_ticket_conversations(ENV_CONFIG, 99999)

        self.assertEqual(error.exception.response.status_code, 404)


SEARCH_DEFAULT_PARAMS = {
    "ticket_count": "30",
    "offset": "0",
    "include_description": "0",
    "include_custom_fields": "0",
    "include_survey_details": "0",
    "order_by": "relevance",
    "include_merged": "1",
}


class SearchTicketsTests(ApiTestCase):
    async def test_returns_parsed_json(self):
        results = {"count": 1, "tickets": [{"ticket_number": 10, "subject": "Printer offline"}]}
        self.mock_api(httpx.Response(200, json=results))

        result = await api.search_tickets(ENV_CONFIG, "printer offline")

        self.assertEqual(result, results)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/search")

    async def test_searches_all_fields_except_archived_by_default(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.search_tickets(ENV_CONFIG, "printer offline")

        params = dict(self.request.url.params)
        self.assertEqual(params.pop("search_type"), "1")
        self.assertEqual(
            json.loads(params.pop("search_query")),
            {"query": "printer offline", "search_in": [1, 2, 3, 4, 5, 6]},
        )
        self.assertEqual(params, SEARCH_DEFAULT_PARAMS)

    async def test_maps_search_in_names_to_codes(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.search_tickets(
            ENV_CONFIG,
            "invoice",
            search_in=["contacts_and_companies", "conversations", "subject", "subject"],
        )

        search_query = json.loads(self.request.url.params["search_query"])
        self.assertEqual(search_query["search_in"], [1, 3, 6])

    async def test_include_archived_adds_archived_code(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.search_tickets(ENV_CONFIG, "invoice", search_in=["subject"], include_archived=True)

        search_query = json.loads(self.request.url.params["search_query"])
        self.assertEqual(search_query["search_in"], [1, 7])

    async def test_converts_arguments_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.search_tickets(
            ENV_CONFIG,
            '"error 504"',
            ticket_count=100,
            offset=200,
            include_description=True,
            include_custom_fields=True,
            include_survey_details=True,
            order_by="updated_time",
            include_merged=False,
        )

        params = dict(self.request.url.params)
        self.assertEqual(json.loads(params.pop("search_query"))["query"], '"error 504"')
        self.assertEqual(
            params,
            {
                "search_type": "1",
                "ticket_count": "100",
                "offset": "200",
                "include_description": "1",
                "include_custom_fields": "1",
                "include_survey_details": "1",
                "order_by": "updated_time",
                "include_merged": "0",
            },
        )

    async def test_rejects_empty_query(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "query must not be empty"):
            await api.search_tickets(ENV_CONFIG, "  ")

        self.assertEqual(self.requests, [])

    async def test_rejects_unknown_search_in_field(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "Unknown search_in fields: notes"):
            await api.search_tickets(ENV_CONFIG, "invoice", search_in=["subject", "notes"])

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(429, json={"status": 429, "error": "Too Many Requests"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.search_tickets(ENV_CONFIG, "invoice")


class AdvancedSearchTicketsTests(ApiTestCase):
    async def test_returns_parsed_json(self):
        results = {"count": 1, "tickets": [{"ticket_number": 130}]}
        self.mock_api(httpx.Response(200, json=results))

        result = await api.advanced_search_tickets(ENV_CONFIG, {"ticket_number": "130"})

        self.assertEqual(result, results)
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/search")

    async def test_builds_one_search_term_per_field(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.advanced_search_tickets(
            ENV_CONFIG,
            {"subject": "VPN", "ticket_number": "130,131", "cf_Site": "Denver"},
        )

        params = dict(self.request.url.params)
        self.assertEqual(params.pop("search_type"), "2")
        self.assertEqual(
            json.loads(params.pop("search_query")),
            {
                "search_term": [
                    {"query": "VPN", "search_in": ["subject"]},
                    {"query": "130,131", "search_in": ["ticket_number"]},
                    {"query": "Denver", "search_in": ["cf_Site"]},
                ]
            },
        )
        self.assertEqual(params, SEARCH_DEFAULT_PARAMS)

    async def test_converts_arguments_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "tickets": []}))

        await api.advanced_search_tickets(
            ENV_CONFIG,
            {"subject": "VPN"},
            ticket_count=50,
            offset=50,
            include_description=True,
            order_by="created_time",
            include_merged=False,
        )

        params = self.request.url.params
        self.assertEqual(params["ticket_count"], "50")
        self.assertEqual(params["offset"], "50")
        self.assertEqual(params["include_description"], "1")
        self.assertEqual(params["order_by"], "created_time")
        self.assertEqual(params["include_merged"], "0")

    async def test_rejects_empty_terms(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "at least one field"):
            await api.advanced_search_tickets(ENV_CONFIG, {})

        self.assertEqual(self.requests, [])

    async def test_rejects_unsupported_fields(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "Unknown terms fields: description, status"):
            await api.advanced_search_tickets(
                ENV_CONFIG, {"subject": "VPN", "description": "x", "status": "Open"}
            )

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(400, json={"status": 400, "error": "Bad Request"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.advanced_search_tickets(ENV_CONFIG, {"subject": "VPN"})


class CreateTicketTests(ApiTestCase):
    async def test_returns_created_ticket(self):
        created = {"ticket_number": 101, "subject": "Help"}
        self.mock_api(httpx.Response(200, json=created))

        result = await api.create_ticket(ENV_CONFIG, email="customer@example.com", subject="Help")

        self.assertEqual(result, created)
        self.assertEqual(self.request.method, "POST")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/create")

    async def test_sends_only_required_fields_by_default(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 101}))

        await api.create_ticket(ENV_CONFIG, email="customer@example.com", subject="Help")

        self.assertEqual(
            json.loads(self.request.content),
            {"email": "customer@example.com", "subject": "Help"},
        )

    async def test_maps_arguments_to_api_field_names(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 102}))

        await api.create_ticket(
            ENV_CONFIG,
            email="customer@example.com",
            subject="Refund request",
            description="<p>Charged twice.</p>",
            status="Open",
            priority=10,
            type="Question",
            assigned_to="agent@example.com",
            group="Billing",
            category="Billing",
            subcategory="Disputed Charge",
            form_name="Create Ticket",
            custom_fields={"cf_Country": "USA"},
            watchers=["lead@example.com"],
            share_to=["manager@example.com"],
        )

        self.assertEqual(
            json.loads(self.request.content),
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

    async def test_keeps_falsy_values_that_are_not_none(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 103}))

        await api.create_ticket(
            ENV_CONFIG,
            email="customer@example.com",
            subject="Help",
            description="",
            custom_fields={"cf_Country": None},
            watchers=[],
        )

        self.assertEqual(
            json.loads(self.request.content),
            {
                "email": "customer@example.com",
                "subject": "Help",
                "description": "",
                "custom_fields": {"cf_Country": None},
                "watchers": [],
            },
        )

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(400, json={"status": 400, "error": "Bad Request"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.create_ticket(ENV_CONFIG, email="customer@example.com", subject="Help")


if __name__ == "__main__":
    unittest.main()
