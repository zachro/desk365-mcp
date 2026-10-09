import json
from typing import Any

import httpx


# Codes for the areas a default ticket search can look in.
SEARCH_FIELDS = {
    'subject': 1,
    'description': 2,
    'conversations': 3,
    'attachment_names': 4,
    'custom_fields': 5,
    'contacts_and_companies': 6,
}
SEARCH_ARCHIVED_TICKETS = 7
ADVANCED_SEARCH_FIELDS = ('subject', 'ticket_number')


def _api_url(env_config: dict[str, str], path: str) -> str:
    return f'https://{env_config["SUBDOMAIN"]}.desk365.io/apis/v3/{path}'


def _headers(env_config: dict[str, str]) -> dict[str, str]:
    return {'Authorization': env_config['API_KEY']}


def _flag(value: bool) -> str:
    return '1' if value else '0'


async def _get(
    env_config: dict[str, str], path: str, params: dict[str, str] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _api_url(env_config, path), headers=_headers(env_config), params=params
        )
        response.raise_for_status()
        return response


async def _post(env_config: dict[str, str], path: str, body: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _api_url(env_config, path), headers=_headers(env_config), json=body
        )
        response.raise_for_status()
        return response


async def ping(env_config: dict[str, str]) -> str:
    response = await _get(env_config, 'ping')
    return response.text


async def list_tickets(
    env_config: dict[str, str],
    ticket_count: int = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: str = 'created_time',
    order_type: str = 'desc',
    updated_since: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = {
        'ticket_count': str(ticket_count),
        'offset': str(offset),
        'include_description': _flag(include_description),
        'include_custom_fields': _flag(include_custom_fields),
        'include_survey_details': _flag(include_survey_details),
        'order_by': order_by,
        'order_type': order_type,
    }
    if updated_since:
        params['updated_since'] = updated_since
    if filters:
        params['filters'] = json.dumps(filters)

    response = await _get(env_config, 'tickets', params)
    return response.json()


async def get_ticket_details(env_config: dict[str, str], ticket_number: int) -> dict[str, Any]:
    response = await _get(env_config, 'tickets/details', {'ticket_number': str(ticket_number)})
    return response.json()


async def create_ticket(
    env_config: dict[str, str],
    email: str,
    subject: str,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
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
    # The create endpoint names these fields assign_to and sub_category, unlike
    # ticket responses, which use assigned_to and subcategory.
    body = {
        'email': email,
        'subject': subject,
        'description': description,
        'status': status,
        'priority': priority,
        'type': type,
        'assign_to': assigned_to,
        'group': group,
        'category': category,
        'sub_category': subcategory,
        'form_name': form_name,
        'custom_fields': custom_fields,
        'watchers': watchers,
        'share_to': share_to,
    }
    # Leave out unset fields so Desk365 applies the account's defaults.
    body = {key: value for key, value in body.items() if value is not None}
    response = await _post(env_config, 'tickets/create', body)
    return response.json()


async def get_ticket_conversations(
    env_config: dict[str, str],
    ticket_number: int,
    sort_by: str = 'earliest_on_top',
    include_contact_replies: bool = True,
    include_agent_replies: bool = True,
    include_private_notes: bool = True,
    include_public_notes: bool = True,
    include_forward_messages: bool = True,
) -> dict[str, Any]:
    params = {
        'ticket_number': str(ticket_number),
        'sort_by': sort_by,
        'include_contact_replies': _flag(include_contact_replies),
        'include_agent_replies': _flag(include_agent_replies),
        'include_private_notes': _flag(include_private_notes),
        'include_public_notes': _flag(include_public_notes),
        'include_forward_messages': _flag(include_forward_messages),
    }
    response = await _get(env_config, 'tickets/conversations', params)
    return response.json()


async def _search_tickets(
    env_config: dict[str, str],
    search_type: int,
    search_query: dict[str, Any],
    ticket_count: int,
    offset: int,
    include_description: bool,
    include_custom_fields: bool,
    include_survey_details: bool,
    order_by: str,
    include_merged: bool,
) -> dict[str, Any]:
    params = {
        'search_type': str(search_type),
        'search_query': json.dumps(search_query),
        'ticket_count': str(ticket_count),
        'offset': str(offset),
        'include_description': _flag(include_description),
        'include_custom_fields': _flag(include_custom_fields),
        'include_survey_details': _flag(include_survey_details),
        'order_by': order_by,
        'include_merged': _flag(include_merged),
    }
    response = await _get(env_config, 'tickets/search', params)
    return response.json()


async def search_tickets(
    env_config: dict[str, str],
    query: str,
    search_in: list[str] | None = None,
    include_archived: bool = False,
    ticket_count: int = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: str = 'relevance',
    include_merged: bool = True,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError('query must not be empty.')
    fields = search_in or list(SEARCH_FIELDS)
    unknown = [field for field in fields if field not in SEARCH_FIELDS]
    if unknown:
        raise ValueError(
            f'Unknown search_in fields: {", ".join(unknown)}. '
            f'Use any of: {", ".join(SEARCH_FIELDS)}.'
        )
    # Always send search_in explicitly so archived tickets are only searched on request.
    codes = sorted({SEARCH_FIELDS[field] for field in fields})
    if include_archived:
        codes.append(SEARCH_ARCHIVED_TICKETS)
    return await _search_tickets(
        env_config,
        search_type=1,
        search_query={'query': query, 'search_in': codes},
        ticket_count=ticket_count,
        offset=offset,
        include_description=include_description,
        include_custom_fields=include_custom_fields,
        include_survey_details=include_survey_details,
        order_by=order_by,
        include_merged=include_merged,
    )


async def advanced_search_tickets(
    env_config: dict[str, str],
    terms: dict[str, str],
    ticket_count: int = 30,
    offset: int = 0,
    include_description: bool = False,
    include_custom_fields: bool = False,
    include_survey_details: bool = False,
    order_by: str = 'relevance',
    include_merged: bool = True,
) -> dict[str, Any]:
    if not terms:
        raise ValueError('terms must contain at least one field to search.')
    unknown = [
        field for field in terms
        if field not in ADVANCED_SEARCH_FIELDS and not field.startswith('cf_')
    ]
    if unknown:
        raise ValueError(
            f'Unknown terms fields: {", ".join(unknown)}. '
            'Use subject, ticket_number or cf_<custom field name>.'
        )
    search_term = [{'query': query, 'search_in': [field]} for field, query in terms.items()]
    return await _search_tickets(
        env_config,
        search_type=2,
        search_query={'search_term': search_term},
        ticket_count=ticket_count,
        offset=offset,
        include_description=include_description,
        include_custom_fields=include_custom_fields,
        include_survey_details=include_survey_details,
        order_by=order_by,
        include_merged=include_merged,
    )
