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

    def test_agent_email_prefers_explicit_value(self):
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        self.assertEqual(api._agent_email(env_config, "agent@example.com"), "agent@example.com")

    def test_agent_email_falls_back_to_default(self):
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        self.assertEqual(api._agent_email(env_config, None), "default@example.com")

    def test_agent_email_is_none_without_default(self):
        self.assertIsNone(api._agent_email(ENV_CONFIG, None))

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

    async def test_post_sends_query_params(self):
        self.mock_api(httpx.Response(200, json={}))

        await api._post(ENV_CONFIG, "tickets/add_note", {"body": "Hi"}, {"ticket_number": "10"})

        self.assertEqual(
            str(self.request.url),
            "https://acme.desk365.io/apis/v3/tickets/add_note?ticket_number=10",
        )

    async def test_put_sends_auth_json_body_and_params(self):
        self.mock_api(httpx.Response(200, json={}))

        await api._put(ENV_CONFIG, "tickets/update", {"status": "Closed"}, {"ticket_number": "10"})

        self.assertEqual(self.request.method, "PUT")
        self.assertEqual(
            str(self.request.url),
            "https://acme.desk365.io/apis/v3/tickets/update?ticket_number=10",
        )
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")
        self.assertEqual(json.loads(self.request.content), {"status": "Closed"})

    async def test_put_raises_on_http_error(self):
        self.mock_api(httpx.Response(400, json={"status": 400, "error": "Bad Request"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api._put(ENV_CONFIG, "tickets/update", {})

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


class AddTicketReplyTests(ApiTestCase):
    async def test_returns_created_reply(self):
        reply = {"id": 1, "ticket_number": 1234, "body": "On it.", "to_email": "c@example.com"}
        self.mock_api(httpx.Response(200, json=reply))

        result = await api.add_ticket_reply(ENV_CONFIG, 1234, "On it.")

        self.assertEqual(result, reply)
        self.assertEqual(self.request.method, "POST")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/add_reply")
        self.assertEqual(dict(self.request.url.params), {"ticket_number": "1234"})

    async def test_sends_body_and_default_flags(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_reply(ENV_CONFIG, 1234, "<p>On it.</p>")

        self.assertEqual(
            json.loads(self.request.content),
            {"body": "<p>On it.</p>", "include_prev_ccs": 0, "include_prev_messages": 0},
        )

    async def test_maps_arguments_to_api_fields(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_reply(
            ENV_CONFIG,
            1234,
            "On it.",
            cc_emails=["a@example.com", "b@example.com"],
            bcc_emails=["c@example.com"],
            agent_email="agent@example.com",
            from_email="support@example.com",
            include_prev_ccs=True,
            include_prev_messages=True,
        )

        self.assertEqual(
            json.loads(self.request.content),
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

    async def test_uses_default_agent_email_when_unset(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        await api.add_ticket_reply(env_config, 1234, "On it.")

        self.assertEqual(json.loads(self.request.content)["agent_email"], "default@example.com")

    async def test_explicit_agent_email_overrides_default(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        await api.add_ticket_reply(env_config, 1234, "On it.", agent_email="agent@example.com")

        self.assertEqual(json.loads(self.request.content)["agent_email"], "agent@example.com")

    async def test_omits_empty_email_lists(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_reply(ENV_CONFIG, 1234, "On it.", cc_emails=[], bcc_emails=[])

        body = json.loads(self.request.content)
        self.assertNotIn("cc_emails", body)
        self.assertNotIn("bcc_emails", body)

    async def test_rejects_empty_body(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "body must not be empty"):
            await api.add_ticket_reply(ENV_CONFIG, 1234, " ")

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.add_ticket_reply(ENV_CONFIG, 99999, "On it.")


class AddTicketNoteTests(ApiTestCase):
    async def test_returns_created_note(self):
        note = {"id": 1, "ticket_number": 1234, "body": "Checked logs.", "private_note": 1}
        self.mock_api(httpx.Response(200, json=note))

        result = await api.add_ticket_note(ENV_CONFIG, 1234, "Checked logs.")

        self.assertEqual(result, note)
        self.assertEqual(self.request.method, "POST")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/add_note")
        self.assertEqual(dict(self.request.url.params), {"ticket_number": "1234"})

    async def test_notes_are_private_by_default(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_note(ENV_CONFIG, 1234, "Checked logs.")

        self.assertEqual(
            json.loads(self.request.content), {"body": "Checked logs.", "private_note": 1}
        )

    async def test_maps_arguments_to_api_fields(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_note(
            ENV_CONFIG,
            1234,
            "<p>Fixed.</p>",
            private=False,
            notify_emails=["a@example.com", "b@example.com"],
            agent_email="agent@example.com",
        )

        self.assertEqual(
            json.loads(self.request.content),
            {
                "body": "<p>Fixed.</p>",
                "private_note": 0,
                "notify_emails": "a@example.com,b@example.com",
                "agent_email": "agent@example.com",
            },
        )

    async def test_uses_default_agent_email_when_unset(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        await api.add_ticket_note(env_config, 1234, "Checked logs.")

        self.assertEqual(json.loads(self.request.content)["agent_email"], "default@example.com")

    async def test_explicit_agent_email_overrides_default(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))
        env_config = {**ENV_CONFIG, "DEFAULT_AGENT_EMAIL": "default@example.com"}

        await api.add_ticket_note(
            env_config, 1234, "Checked logs.", agent_email="agent@example.com"
        )

        self.assertEqual(json.loads(self.request.content)["agent_email"], "agent@example.com")

    async def test_omits_empty_notify_emails(self):
        self.mock_api(httpx.Response(200, json={"id": 1}))

        await api.add_ticket_note(ENV_CONFIG, 1234, "Checked logs.", notify_emails=[])

        self.assertNotIn("notify_emails", json.loads(self.request.content))

    async def test_rejects_empty_body(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "body must not be empty"):
            await api.add_ticket_note(ENV_CONFIG, 1234, "")

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.add_ticket_note(ENV_CONFIG, 99999, "Checked logs.")


class UpdateTicketTests(ApiTestCase):
    async def test_returns_updated_ticket(self):
        ticket = {"ticket_number": 1234, "status": "Closed"}
        self.mock_api(httpx.Response(200, json=ticket))

        result = await api.update_ticket(ENV_CONFIG, 1234, status="Closed")

        self.assertEqual(result, ticket)
        self.assertEqual(self.request.method, "PUT")
        self.assertEqual(self.request.url.path, "/apis/v3/tickets/update")
        self.assertEqual(dict(self.request.url.params), {"ticket_number": "1234"})

    async def test_sends_only_given_fields(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 1234}))

        await api.update_ticket(ENV_CONFIG, 1234, status="Pending", priority=20)

        self.assertEqual(json.loads(self.request.content), {"status": "Pending", "priority": 20})

    async def test_maps_arguments_to_api_field_names(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 1234}))

        await api.update_ticket(
            ENV_CONFIG,
            1234,
            contact_email="customer@example.com",
            subject="Refund request",
            description="<p>Charged twice.</p>",
            sla="Standard SLA",
            status="Open",
            priority=10,
            type="Question",
            assigned_to="agent@example.com",
            group="Billing",
            category="Billing",
            subcategory="Disputed Charge",
            custom_fields={"cf_Country": "USA"},
            add_watchers=["lead@example.com"],
            remove_watchers=["old-lead@example.com"],
            add_share_to=["manager@example.com"],
            remove_share_to=["old-manager@example.com"],
        )

        self.assertEqual(
            json.loads(self.request.content),
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

    async def test_sends_only_the_watcher_lists_given(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 1234}))

        await api.update_ticket(
            ENV_CONFIG, 1234, remove_watchers=["lead@example.com"], add_share_to=[]
        )

        self.assertEqual(
            json.loads(self.request.content), {"watchers": {"remove": ["lead@example.com"]}}
        )

    async def test_passes_unassign_value_through(self):
        self.mock_api(httpx.Response(200, json={"ticket_number": 1234}))

        await api.update_ticket(ENV_CONFIG, 1234, assigned_to="--", group="--")

        self.assertEqual(json.loads(self.request.content), {"assign_to": "--", "group": "--"})

    async def test_rejects_update_with_no_changes(self):
        self.mock_api(httpx.Response(200, json={}))

        for kwargs in [{}, {"custom_fields": {}}, {"add_watchers": [], "remove_share_to": []}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, "Nothing to update"):
                    await api.update_ticket(ENV_CONFIG, 1234, **kwargs)

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.update_ticket(ENV_CONFIG, 99999, status="Closed")


class ListContactsTests(ApiTestCase):
    async def test_returns_parsed_json(self):
        contacts = {"count": 1, "content": [{"name": "Jane Doe", "email": "jane@example.com"}]}
        self.mock_api(httpx.Response(200, json=contacts))

        result = await api.list_contacts(ENV_CONFIG)

        self.assertEqual(result, contacts)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/contacts")

    async def test_sends_default_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "content": []}))

        await api.list_contacts(ENV_CONFIG)

        self.assertEqual(
            dict(self.request.url.params),
            {"offset": "0", "order_by": "1", "order_type": "asc", "include_custom_fields": "0"},
        )

    async def test_converts_arguments_to_api_params(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "content": []}))

        await api.list_contacts(
            ENV_CONFIG,
            company="Example Corp",
            offset=30,
            order_by="email",
            order_type="desc",
            include_custom_fields=True,
        )

        self.assertEqual(
            dict(self.request.url.params),
            {
                "company": "Example Corp",
                "offset": "30",
                "order_by": "4",
                "order_type": "desc",
                "include_custom_fields": "1",
            },
        )

    async def test_maps_each_sort_field_to_its_code(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "content": []}))

        for order_by, code in [("name", "1"), ("title", "2"), ("company", "3"), ("email", "4")]:
            await api.list_contacts(ENV_CONFIG, order_by=order_by)
            self.assertEqual(self.requests[-1].url.params["order_by"], code)

    async def test_omits_empty_company(self):
        self.mock_api(httpx.Response(200, json={"count": 0, "content": []}))

        await api.list_contacts(ENV_CONFIG, company="")

        self.assertNotIn("company", self.request.url.params)

    async def test_rejects_unknown_sort_field(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "Unknown order_by: phone"):
            await api.list_contacts(ENV_CONFIG, order_by="phone")

        self.assertEqual(self.requests, [])

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(401, json={"status": 401, "error": "Unauthorized"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.list_contacts(ENV_CONFIG)


class GetContactDetailsTests(ApiTestCase):
    async def test_looks_up_by_primary_email(self):
        contact = {"name": "Jane Doe", "primary_email": "jane@example.com"}
        self.mock_api(httpx.Response(200, json=contact))

        result = await api.get_contact_details(ENV_CONFIG, "jane@example.com")

        self.assertEqual(result, contact)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/contacts/details")
        self.assertEqual(dict(self.request.url.params), {"primary_email": "jane@example.com"})

    async def test_looks_up_by_secondary_email(self):
        self.mock_api(httpx.Response(200, json={"name": "Jane Doe"}))

        await api.get_contact_details(ENV_CONFIG, "jane@other.example.com", secondary=True)

        self.assertEqual(
            dict(self.request.url.params), {"secondary_email": "jane@other.example.com"}
        )

    async def test_rejects_empty_email(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "email must not be empty"):
            await api.get_contact_details(ENV_CONFIG, " ")

        self.assertEqual(self.requests, [])

    async def test_raises_when_contact_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.get_contact_details(ENV_CONFIG, "nobody@example.com")

        self.assertEqual(error.exception.response.status_code, 404)


class ListKbArticlesTests(ApiTestCase):
    async def test_returns_article_titles(self):
        articles = {"count": 2, "article_titles": ["Reset your password", "Set up VPN"]}
        self.mock_api(httpx.Response(200, json=articles))

        result = await api.list_kb_articles(ENV_CONFIG)

        self.assertEqual(result, articles)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(str(self.request.url), "https://acme.desk365.io/apis/v3/kb/article/")
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(500, json={"status": 500, "error": "Server Error"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.list_kb_articles(ENV_CONFIG)


class GetKbArticleTests(ApiTestCase):
    async def test_requests_article_by_title(self):
        article = {"article_title": "Set up VPN", "article_content_text": "Open the app."}
        self.mock_api(httpx.Response(200, json=article))

        result = await api.get_kb_article(ENV_CONFIG, "Set up VPN")

        self.assertEqual(result, article)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/kb/article/details")
        self.assertEqual(dict(self.request.url.params), {"article_name": "Set up VPN"})

    async def test_encodes_special_characters_in_title(self):
        self.mock_api(httpx.Response(200, json={}))

        await api.get_kb_article(ENV_CONFIG, "How do I reset my password? (Mac & PC)")

        self.assertEqual(
            self.request.url.params["article_name"], "How do I reset my password? (Mac & PC)"
        )

    async def test_rejects_empty_title(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "title must not be empty"):
            await api.get_kb_article(ENV_CONFIG, "")

        self.assertEqual(self.requests, [])

    async def test_raises_when_article_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.get_kb_article(ENV_CONFIG, "No such article")

        self.assertEqual(error.exception.response.status_code, 404)


class ListLocationsTests(ApiTestCase):
    async def test_returns_locations(self):
        locations = {
            "total": 2,
            "locations": [
                {"location_name": "Main Office", "parent_location_name": ""},
                {"location_name": "Floor 2", "parent_location_name": "Main Office"},
            ],
        }
        self.mock_api(httpx.Response(200, json=locations))

        result = await api.list_locations(ENV_CONFIG)

        self.assertEqual(result, locations)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(
            str(self.request.url), "https://acme.desk365.io/apis/v3/asset_mgmt/locations"
        )
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_raises_on_http_error(self):
        self.mock_api(httpx.Response(403, json={"status": 403, "error": "Forbidden"}))

        with self.assertRaises(httpx.HTTPStatusError):
            await api.list_locations(ENV_CONFIG)


class GetLocationDetailsTests(ApiTestCase):
    async def test_requests_location_by_name(self):
        location = {"location_name": "Main Office", "contact_name": "Jane Doe"}
        self.mock_api(httpx.Response(200, json=location))

        result = await api.get_location_details(ENV_CONFIG, "Main Office")

        self.assertEqual(result, location)
        self.assertEqual(self.request.method, "GET")
        self.assertEqual(self.request.url.path, "/apis/v3/asset_mgmt/locations/details")
        self.assertEqual(dict(self.request.url.params), {"location_name": "Main Office"})
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_rejects_empty_location_name(self):
        self.mock_api(httpx.Response(200, json={}))

        with self.assertRaisesRegex(ValueError, "location_name must not be empty"):
            await api.get_location_details(ENV_CONFIG, "")

        self.assertEqual(self.requests, [])

    async def test_raises_when_location_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.get_location_details(ENV_CONFIG, "Nowhere")

        self.assertEqual(error.exception.response.status_code, 404)


class CreateLocationTests(ApiTestCase):
    async def test_returns_created_location(self):
        location = {"location_name": "Main Office", "parent_location_name": ""}
        self.mock_api(httpx.Response(201, json=location))

        result = await api.create_location(ENV_CONFIG, "Main Office")

        self.assertEqual(result, location)
        self.assertEqual(self.request.method, "POST")
        self.assertEqual(self.request.url.path, "/apis/v3/asset_mgmt/locations/create")
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_sends_only_name_by_default(self):
        self.mock_api(httpx.Response(201, json={}))

        await api.create_location(ENV_CONFIG, "Main Office")

        self.assertEqual(json.loads(self.request.content), {"location_name": "Main Office"})

    async def test_sends_all_given_fields(self):
        self.mock_api(httpx.Response(201, json={}))

        await api.create_location(
            ENV_CONFIG,
            "Floor 2",
            parent_location_name="Main Office",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
            contact_phone="+1-555-0100",
            location_address="1 Example St",
            location_city="Springfield",
            location_state="IL",
            location_country="USA",
            location_zipcode="62701",
        )

        self.assertEqual(
            json.loads(self.request.content),
            {
                "location_name": "Floor 2",
                "parent_location_name": "Main Office",
                "contact_name": "Jane Doe",
                "contact_email": "jane@example.com",
                "contact_phone": "+1-555-0100",
                "location_address": "1 Example St",
                "location_city": "Springfield",
                "location_state": "IL",
                "location_country": "USA",
                "location_zipcode": "62701",
            },
        )

    async def test_omits_empty_parent_location(self):
        self.mock_api(httpx.Response(201, json={}))

        await api.create_location(ENV_CONFIG, "Main Office", parent_location_name="")

        self.assertNotIn("parent_location_name", json.loads(self.request.content))

    async def test_accepts_values_at_max_length(self):
        self.mock_api(httpx.Response(201, json={}))

        await api.create_location(ENV_CONFIG, "x" * 128, location_address="y" * 250)

        self.assertEqual(len(self.requests), 1)

    async def test_rejects_values_over_max_length(self):
        self.mock_api(httpx.Response(201, json={}))

        with self.assertRaisesRegex(
            ValueError,
            r"Too long: location_name \(max 128 characters\), "
            r"contact_phone \(max 64 characters\)",
        ):
            await api.create_location(ENV_CONFIG, "x" * 129, contact_phone="1" * 65)

        self.assertEqual(self.requests, [])

    async def test_rejects_empty_location_name(self):
        self.mock_api(httpx.Response(201, json={}))

        with self.assertRaisesRegex(ValueError, "location_name must not be empty"):
            await api.create_location(ENV_CONFIG, " ")

        self.assertEqual(self.requests, [])

    async def test_raises_when_name_already_exists(self):
        self.mock_api(httpx.Response(409, json={"status": 409, "error": "Conflict"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.create_location(ENV_CONFIG, "Main Office")

        self.assertEqual(error.exception.response.status_code, 409)


class UpdateLocationTests(ApiTestCase):
    async def test_returns_updated_location(self):
        location = {"location_name": "Main Office", "contact_name": "Jane Doe"}
        self.mock_api(httpx.Response(200, json=location))

        result = await api.update_location(ENV_CONFIG, "Main Office", contact_name="Jane Doe")

        self.assertEqual(result, location)
        self.assertEqual(self.request.method, "PUT")
        self.assertEqual(self.request.url.path, "/apis/v3/asset_mgmt/locations/update")
        self.assertEqual(dict(self.request.url.params), {"location_name": "Main Office"})
        self.assertEqual(self.request.headers["Authorization"], "test-api-key")

    async def test_sends_only_given_fields(self):
        self.mock_api(httpx.Response(200, json={}))

        await api.update_location(ENV_CONFIG, "Main Office", location_city="Springfield")

        self.assertEqual(json.loads(self.request.content), {"location_city": "Springfield"})

    async def test_sends_new_name_as_location_name(self):
        self.mock_api(httpx.Response(200, json={}))

        await api.update_location(ENV_CONFIG, "Main Office", new_location_name="Head Office")

        self.assertEqual(dict(self.request.url.params), {"location_name": "Main Office"})
        self.assertEqual(json.loads(self.request.content), {"location_name": "Head Office"})

    async def test_sends_all_given_fields(self):
        self.mock_api(httpx.Response(200, json={}))

        await api.update_location(
            ENV_CONFIG,
            "Main Office",
            new_location_name="Head Office",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
            contact_phone="+1-555-0100",
            location_address="1 Example St",
            location_city="Springfield",
            location_state="IL",
            location_country="USA",
            location_zipcode="62701",
        )

        self.assertEqual(
            json.loads(self.request.content),
            {
                "location_name": "Head Office",
                "contact_name": "Jane Doe",
                "contact_email": "jane@example.com",
                "contact_phone": "+1-555-0100",
                "location_address": "1 Example St",
                "location_city": "Springfield",
                "location_state": "IL",
                "location_country": "USA",
                "location_zipcode": "62701",
            },
        )

    async def test_rejects_invalid_input(self):
        self.mock_api(httpx.Response(200, json={}))

        for location_name, kwargs, message in [
            ("", {"contact_name": "Jane Doe"}, "location_name must not be empty"),
            ("Main Office", {"new_location_name": " "}, "new_location_name must not be empty"),
            ("Main Office", {}, "Nothing to update"),
            ("Main Office", {"location_address": "x" * 251}, "location_address \\(max 250"),
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                await api.update_location(ENV_CONFIG, location_name, **kwargs)

        self.assertEqual(self.requests, [])

    async def test_raises_when_location_not_found(self):
        self.mock_api(httpx.Response(404, json={"status": 404, "error": "Not Found"}))

        with self.assertRaises(httpx.HTTPStatusError) as error:
            await api.update_location(ENV_CONFIG, "Nowhere", contact_name="Jane Doe")

        self.assertEqual(error.exception.response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
