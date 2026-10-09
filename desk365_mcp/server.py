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
async def search_tickets(
    query: str,
    search_in: list[
        Literal[
            'subject',
            'description',
            'conversations',
            'attachment_names',
            'custom_fields',
            'contacts_and_companies',
        ]
    ] | None = None,
    include_archived: bool = False,
    ticket_count: Literal[30, 50, 100] = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: Literal['relevance', 'created_time', 'updated_time'] = 'relevance',
    include_merged: bool = True,
) -> dict[str, Any]:
    """Full-text search for Desk365 tickets, sorted by relevance by default.

    Use this to find tickets by what they are about, e.g. "printer offline" or a
    contact's name. To find tickets by status, priority, assignee, group, category,
    contact email or date instead, use list_tickets with filters, which is cheaper.
    To require a match in specific fields at once (e.g. subject AND a custom field),
    use advanced_search_tickets.

    Each search costs 5 times as much of the Desk365 API rate limit as other calls
    (which can be as low as 100 calls per hour), so search once with a good query
    instead of many narrow ones.

    Query syntax: by default a ticket matches if it contains all the words, in any
    order, including word variations. For an exact phrase, include double quotes in
    the query itself: the query "error 504" with its quotes matches only that phrase.
    Put * before text to match words ending with it (*365 matches Desk365), or
    before and after to match words containing it (*pass* matches password).

    Returns {"count": <total matching tickets>, "tickets": [<ticket>, ...]} with the
    same ticket fields as list_tickets. At most 1,000 matching tickets can be paged
    through. To fetch the next page, call again with offset increased by
    ticket_count; stop once offset reaches count or 1,000.

    Coded values in results:
    - priority: Low=1, Medium=5, High=10, Urgent=20
    - source: Email=1, Microsoft Teams=5, Support Portal=6, Phone or Other=7,
      Web Form=12, Web Widget=13, API=15, Chat Widget (AI Agent)=16,
      Microsoft Teams (AI Agent)=17, Support Portal (AI Agent)=18

    Args:
        query: The text to search for.
        search_in: Where to look. subject also matches ticket numbers; conversations
            covers replies and notes; custom_fields covers text and paragraph custom
            fields; contacts_and_companies covers contact and company names. Leave
            unset to search all of them.
        include_archived: Also search archived tickets.
        ticket_count: Number of tickets per page. Only 30, 50 or 100 are allowed.
        offset: Number of tickets to skip, for paging. Start at 0.
        include_description: Include each ticket's description as HTML and plain text.
        include_custom_fields: Include the account's custom ticket fields.
        include_survey_details: Include the latest customer survey rating, when a
            survey was sent for the ticket.
        order_by: Sort by search relevance, creation time or last update time.
        include_merged: Include tickets that were merged into other tickets.
    """
    logger.info('Searching Desk365 tickets (query=%r, offset=%s)', query, offset)
    return await api.search_tickets(
        env_config,
        query,
        search_in=search_in,
        include_archived=include_archived,
        ticket_count=ticket_count,
        offset=offset,
        include_description=include_description,
        include_custom_fields=include_custom_fields,
        include_survey_details=include_survey_details,
        order_by=order_by,
        include_merged=include_merged,
    )


@mcp.tool
async def advanced_search_tickets(
    terms: dict[str, str],
    ticket_count: Literal[30, 50, 100] = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: Literal['relevance', 'created_time', 'updated_time'] = 'relevance',
    include_merged: bool = True,
) -> dict[str, Any]:
    """Search Desk365 tickets by text in specific fields, where every field must match.

    Use this when the user's request names particular fields, e.g. tickets whose
    subject mentions "VPN" and whose "Site" custom field contains "Denver". For a
    general text search, use search_tickets. For status, priority, assignee, group,
    category, contact email or date, use list_tickets with filters.

    Each search costs 5 times as much of the Desk365 API rate limit as other calls
    (which can be as low as 100 calls per hour).

    Query syntax for each term: a field matches if it contains all the words, in any
    order, including word variations. Wrap words in double quotes for an exact match.
    Put * before text to match words ending with it, or before and after to match
    words containing it (*pass* matches password).

    Returns {"count": <total matching tickets>, "tickets": [<ticket>, ...]} with the
    same ticket fields and coded values as list_tickets (e.g. priority Low=1,
    Medium=5, High=10, Urgent=20). At most 1,000 matching tickets can be paged
    through. To fetch the next page, call again with offset increased by
    ticket_count; stop once offset reaches count or 1,000.

    Args:
        terms: Maps each field to the text it must contain. A ticket is returned only
            if every field matches. Fields can be "subject", "ticket_number" (one
            number or several separated by commas, e.g. "130,131") or
            "cf_<field name>" for a text or paragraph custom field, using the name as
            it appears in get_ticket_details custom_fields. Example:
            {"subject": "VPN", "cf_Site": "Denver"}.
        ticket_count: Number of tickets per page. Only 30, 50 or 100 are allowed.
        offset: Number of tickets to skip, for paging. Start at 0.
        include_description: Include each ticket's description as HTML and plain text.
        include_custom_fields: Include the account's custom ticket fields.
        include_survey_details: Include the latest customer survey rating, when a
            survey was sent for the ticket.
        order_by: Sort by search relevance, creation time or last update time.
        include_merged: Include tickets that were merged into other tickets.
    """
    logger.info(
        'Advanced searching Desk365 tickets (fields=%s, offset=%s)', list(terms), offset
    )
    return await api.advanced_search_tickets(
        env_config,
        terms,
        ticket_count=ticket_count,
        offset=offset,
        include_description=include_description,
        include_custom_fields=include_custom_fields,
        include_survey_details=include_survey_details,
        order_by=order_by,
        include_merged=include_merged,
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
    conversation_count only says how many there are. Use get_ticket_conversations
    to read them.

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


@mcp.tool
async def get_ticket_conversations(
    ticket_number: int,
    sort_by: Literal['earliest_on_top', 'latest_on_top'] = 'earliest_on_top',
    include_contact_replies: bool = True,
    include_agent_replies: bool = True,
    include_private_notes: bool = True,
    include_public_notes: bool = True,
    include_forward_messages: bool = True,
) -> dict[str, Any]:
    """Get the conversation history of one Desk365 ticket: replies, notes and forwards.

    Use this to see what has happened on a ticket since it was opened, such as what
    the contact and agents have said or what agents noted. The ticket's original
    description is not included; get it from get_ticket_details.

    Returns {"count": <number of messages>, "agent_reply_count",
    "contact_reply_count", "public_note_count", "private_note_count",
    "forward_message_count", "conversations": [<message>, ...]}. Each message has id,
    type ("reply" or "note"), public_note, created_by (sender email), creator_name,
    sender_type ("agent" or "contact"), to_address, cc_address, bcc_address and
    notified_agents (comma-separated emails), body (HTML), body_text (plain text),
    attachments_count, attachments, created_on ("yyyy-mm-dd hh:mm:ss") and email
    bounce details. All messages are returned at once; there is no paging.

    Private notes are internal to agents. A message is a private note when its type
    is "note" and public_note is not true (public_note is null on replies). Treat
    any note as private unless public_note is true, and don't repeat private notes
    in anything meant for the contact, such as a drafted reply.

    Args:
        ticket_number: The ticket's number, as shown in Desk365 (e.g. 1234).
        sort_by: "earliest_on_top" for oldest message first, "latest_on_top" for
            newest first.
        include_contact_replies: Include replies from the contact.
        include_agent_replies: Include replies from agents.
        include_private_notes: Include agents' internal notes.
        include_public_notes: Include public notes.
        include_forward_messages: Include messages forwarded from the ticket.
    """
    logger.info('Getting Desk365 ticket conversations (ticket_number=%s)', ticket_number)
    return await api.get_ticket_conversations(
        env_config,
        ticket_number,
        sort_by=sort_by,
        include_contact_replies=include_contact_replies,
        include_agent_replies=include_agent_replies,
        include_private_notes=include_private_notes,
        include_public_notes=include_public_notes,
        include_forward_messages=include_forward_messages,
    )


@mcp.tool
async def create_ticket(
    email: str,
    subject: str,
    description: str | None = None,
    status: str | None = None,
    priority: Literal[1, 5, 10, 20] | None = None,
    type: str | None = None,
    assigned_to: str | None = None,
    group: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    form_name: str | None = None,
    custom_fields: dict[str, Any] | None = None,
    watchers: list[str] | None = None,
    share_to: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new Desk365 support ticket.

    This creates a real ticket that agents and the contact may see, so only call it
    when the user has asked for a ticket to be created, and confirm the subject,
    contact and any other details with them first if they are unclear. Each call
    creates another ticket, so don't retry after a success.

    Only email and subject are required. Leave other fields unset unless the user
    gives a value; Desk365 then applies the account's defaults (e.g. the default
    status and priority). Names such as status, type, group, category, subcategory
    and form_name must exactly match ones configured in the Desk365 account. If you
    are unsure of the valid names, look at existing tickets from list_tickets or
    get_ticket_details rather than guessing.

    Returns the created ticket with the same fields as get_ticket_details,
    including the new ticket_number to share with the user.

    Args:
        email: Email address of the contact (customer or requester) the ticket is for.
        subject: Short summary of the issue.
        description: Full description of the issue, as HTML (e.g. "<p>The printer
            on floor 2 shows a paper jam error.</p>"). Use <br> or <p> tags for
            line breaks.
        status: Ticket status, e.g. "Open" or "Pending". Defaults to the account's
            default status.
        priority: Low=1, Medium=5, High=10, Urgent=20.
        type: Ticket type, e.g. "Question" or "Incident".
        assigned_to: Email address of the agent to assign the ticket to.
        group: Name of the agent group to assign the ticket to.
        category: Ticket category name.
        subcategory: Ticket subcategory name. It must belong to the given category.
        form_name: Name of the ticket form to create the ticket with. Defaults to the
            account's default agent portal form. Some forms have their own custom
            fields.
        custom_fields: Values for the account's custom ticket fields, keyed by
            "cf_<field name>" with the field name's exact case, as they appear in
            get_ticket_details (e.g. {"cf_Country": "USA"}).
        watchers: Email addresses of agents to add as watchers.
        share_to: Email addresses of other contacts to share the ticket with.
    """
    logger.info('Creating Desk365 ticket (subject=%r)', subject)
    return await api.create_ticket(
        env_config,
        email=email,
        subject=subject,
        description=description,
        status=status,
        priority=priority,
        type=type,
        assigned_to=assigned_to,
        group=group,
        category=category,
        subcategory=subcategory,
        form_name=form_name,
        custom_fields=custom_fields,
        watchers=watchers,
        share_to=share_to,
    )


def run_server(config: dict[str, str]):
    env_config.update(config)
    mcp.run(transport='streamable-http', port=8000, path='/')
