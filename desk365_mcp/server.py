import logging
from typing import Any, Literal

from fastmcp import FastMCP

from desk365_mcp import api


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

mcp = FastMCP('desk365-mcp')
env_config: dict[str, str] = {}


@mcp.tool
async def ping() -> str:
    """Check whether the Desk365 API is up and reachable.

    Use this to diagnose connection problems, e.g. after another Desk365 tool fails.
    A successful ping does not confirm the API key is valid; it only shows the
    service is running.
    """
    logger.info('Pinging Desk365 API')
    return await api.ping(env_config)


@mcp.tool
async def list_tickets(
    ticket_count: Literal[30, 50, 100] = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: Literal['created_time', 'updated_time'] = 'created_time',
    order_type: Literal['asc', 'desc'] = 'desc',
    updated_since: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List Desk365 support tickets, newest first by default.

    Returns {"count": <total number of matching tickets>, "tickets": [<ticket>, ...]}.
    Each ticket includes ticket_number, subject, status, priority, type, source,
    contact_email, assigned_to, group, category, company_name, created_on,
    updated_on, due_date and SLA/duration fields.

    Paging: results come in pages of ticket_count. To fetch the next page, call again
    with offset increased by ticket_count; stop once offset reaches count. The
    Desk365 API is rate limited (as low as 100 calls per hour), so prefer filters
    and updated_since over paging through every ticket. Only request descriptions,
    custom fields or survey details when needed, since they make responses much
    larger.

    Coded values (used both in responses and in filters):
    - priority: Low=1, Medium=5, High=10, Urgent=20
    - source: Email=1, Microsoft Teams=5, Support Portal=6, Phone or Other=7,
      Web Form=12, Web Widget=13, API=15, Chat Widget (AI Agent)=16,
      Microsoft Teams (AI Agent)=17, Support Portal (AI Agent)=18
    - updated_by_type, closed_by_type: System=1, Agent=2, Contact=3
    - first_replied_duration, first_assigned_duration, resolved_duration and
      closed_duration are in minutes.

    Args:
        ticket_count: Number of tickets per page. Only 30, 50 or 100 are allowed.
        offset: Number of tickets to skip, for paging. Start at 0.
        include_description: Include each ticket's description as HTML and plain text.
        include_custom_fields: Include the account's custom ticket fields.
        include_survey_details: Include the latest customer survey rating, when a
            survey was sent for the ticket.
        order_by: Sort by creation time or last update time.
        order_type: "desc" for newest first, "asc" for oldest first.
        updated_since: Only return tickets with activity after this time. Format:
            "yyyy-mm-dd hh:mm:ss", e.g. "2026-10-01 00:00:00".
        filters: Only return matching tickets. A JSON object whose keys are any of
            status, priority, type, group, assigned_to, category, subcategory,
            source, contact or company_name. Each key maps to a list of strings, and a
            ticket matches if it has any value in the list. All filter values are
            strings, including priority and source codes (e.g. "10", not 10).
            assigned_to and contact take email addresses. Use "--" to match tickets
            with no value set. Custom dropdown fields go under
            "custom_fields": {"cf_<field name>": [...]}. Merged tickets are
            included unless you add "include_merged": 0. Example:
            {"status": ["Open", "Pending"], "priority": ["10", "20"],
            "assigned_to": ["agent@example.com"]}.
    """
    logger.info('Listing Desk365 tickets (count=%s, offset=%s)', ticket_count, offset)
    return await api.list_tickets(
        env_config,
        ticket_count=ticket_count,
        offset=offset,
        include_description=include_description,
        include_custom_fields=include_custom_fields,
        include_survey_details=include_survey_details,
        order_by=order_by,
        order_type=order_type,
        updated_since=updated_since,
        filters=filters,
    )


@mcp.tool
async def get_ticket_details(ticket_number: int) -> dict[str, Any]:
    """Get the full details of one Desk365 ticket by its ticket number.

    Use this when you need everything about a specific ticket, such as its
    description, which list_tickets leaves out by default. Ticket numbers come from
    list_tickets results or from the user (e.g. "ticket #1234" means 1234).

    Returns the ticket as an object with ticket_number, subject, description (HTML),
    description_text (plain text), status, priority, type, source, form_name,
    contact_email, contact_name, assigned_to, group, category, subcategory,
    company_name, department_name, sla, created_on, updated_on, updated_by,
    resolved_on, closed_on, closed_by, due_date, duration fields, custom_fields,
    attachments, watchers, share_to, conversation_count and associated_assets.
    Fields that don't apply yet (e.g. closed_on on an open ticket) are null.
    Timestamps use the format "yyyy-mm-dd hh:mm:ss".

    description_text strips all line breaks, so separate lines can run together
    (e.g. "Name: Jane DoePhone: 555-0100"). Read the HTML description when
    the ticket's layout matters. custom_fields is always included and maps
    "cf_<field name>" to a value, or null when the field is empty.

    The replies and notes in the ticket's conversation are not included;
    conversation_count only says how many there are.

    Coded values:
    - priority: Low=1, Medium=5, High=10, Urgent=20
    - source: Email=1, Microsoft Teams=5, Support Portal=6, Phone or Other=7,
      Web Form=12, Web Widget=13, API=15, Chat Widget (AI Agent)=16,
      Microsoft Teams (AI Agent)=17, Support Portal (AI Agent)=18
    - updated_by_type, closed_by_type: System=1, Agent=2, Contact=3
    - first_replied_duration, first_assigned_duration, resolved_duration and
      closed_duration are in minutes.

    Args:
        ticket_number: The ticket's number, as shown in Desk365 (e.g. 1234).
    """
    logger.info('Getting Desk365 ticket details (ticket_number=%s)', ticket_number)
    return await api.get_ticket_details(env_config, ticket_number)


def run_server(config: dict[str, str]):
    env_config.update(config)
    mcp.run(transport='streamable-http', port=8000, path='/')
