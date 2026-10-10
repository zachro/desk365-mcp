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
# Maximum lengths Desk365 accepts for location fields.
LOCATION_FIELD_LIMITS = {
    'location_name': 128,
    'parent_location_name': 128,
    'contact_name': 128,
    'contact_email': 128,
    'contact_phone': 64,
    'location_address': 250,
    'location_city': 100,
    'location_state': 100,
    'location_country': 100,
    'location_zipcode': 64,
}
# Codes for the fields contacts can be sorted by.
CONTACT_SORT_FIELDS = {
    'name': 1,
    'title': 2,
    'company': 3,
    'email': 4,
}


def _api_url(env_config: dict[str, str], path: str) -> str:
    return f'https://{env_config["SUBDOMAIN"]}.desk365.io/apis/v3/{path}'


def _headers(env_config: dict[str, str]) -> dict[str, str]:
    return {'Authorization': env_config['API_KEY']}


def _flag(value: bool) -> str:
    return '1' if value else '0'


def _agent_email(env_config: dict[str, str], agent_email: str | None) -> str | None:
    # With no agent email at all, Desk365 attributes the message to the API key's owner.
    return agent_email or env_config.get('DEFAULT_AGENT_EMAIL')


async def _get(
    env_config: dict[str, str], path: str, params: dict[str, str] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _api_url(env_config, path), headers=_headers(env_config), params=params
        )
        response.raise_for_status()
        return response


async def _post(
    env_config: dict[str, str],
    path: str,
    body: dict[str, Any],
    params: dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _api_url(env_config, path), headers=_headers(env_config), json=body, params=params
        )
        response.raise_for_status()
        return response


async def _put(
    env_config: dict[str, str],
    path: str,
    body: dict[str, Any],
    params: dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        response = await client.put(
            _api_url(env_config, path), headers=_headers(env_config), json=body, params=params
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


async def add_ticket_reply(
    env_config: dict[str, str],
    ticket_number: int,
    body: str,
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    agent_email: str | None = None,
    from_email: str | None = None,
    include_prev_ccs: bool = False,
    include_prev_messages: bool = False,
) -> dict[str, Any]:
    if not body.strip():
        raise ValueError('body must not be empty.')
    payload = {
        'body': body,
        'cc_emails': ','.join(cc_emails) if cc_emails else None,
        'bcc_emails': ','.join(bcc_emails) if bcc_emails else None,
        'agent_email': _agent_email(env_config, agent_email),
        'from_email': from_email,
        'include_prev_ccs': int(include_prev_ccs),
        'include_prev_messages': int(include_prev_messages),
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    response = await _post(
        env_config, 'tickets/add_reply', payload, {'ticket_number': str(ticket_number)}
    )
    return response.json()


async def add_ticket_note(
    env_config: dict[str, str],
    ticket_number: int,
    body: str,
    private: bool = True,
    notify_emails: list[str] | None = None,
    agent_email: str | None = None,
) -> dict[str, Any]:
    if not body.strip():
        raise ValueError('body must not be empty.')
    payload = {
        'body': body,
        'private_note': int(private),
        'notify_emails': ','.join(notify_emails) if notify_emails else None,
        'agent_email': _agent_email(env_config, agent_email),
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    response = await _post(
        env_config, 'tickets/add_note', payload, {'ticket_number': str(ticket_number)}
    )
    return response.json()


def _add_remove(add: list[str] | None, remove: list[str] | None) -> dict[str, list[str]] | None:
    changes = {'add': add, 'remove': remove}
    changes = {key: value for key, value in changes.items() if value}
    return changes or None


async def update_ticket(
    env_config: dict[str, str],
    ticket_number: int,
    contact_email: str | None = None,
    subject: str | None = None,
    description: str | None = None,
    sla: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    type: str | None = None,
    assigned_to: str | None = None,
    group: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    custom_fields: dict[str, Any] | None = None,
    add_watchers: list[str] | None = None,
    remove_watchers: list[str] | None = None,
    add_share_to: list[str] | None = None,
    remove_share_to: list[str] | None = None,
) -> dict[str, Any]:
    # Like the create endpoint, the update endpoint uses assign_to and sub_category.
    body = {
        'contact_email': contact_email,
        'subject': subject,
        'description': description,
        'sla': sla,
        'status': status,
        'priority': priority,
        'type': type,
        'assign_to': assigned_to,
        'group': group,
        'category': category,
        'sub_category': subcategory,
        'custom_fields': custom_fields or None,
        'watchers': _add_remove(add_watchers, remove_watchers),
        'share_to': _add_remove(add_share_to, remove_share_to),
    }
    # Desk365 leaves any field missing from the body unchanged.
    body = {key: value for key, value in body.items() if value is not None}
    if not body:
        raise ValueError('Nothing to update: set at least one field to change.')
    response = await _put(
        env_config, 'tickets/update', body, {'ticket_number': str(ticket_number)}
    )
    return response.json()


async def list_contacts(
    env_config: dict[str, str],
    company: str | None = None,
    offset: int = 0,
    order_by: str = 'name',
    order_type: str = 'asc',
    include_custom_fields: bool = False,
) -> dict[str, Any]:
    if order_by not in CONTACT_SORT_FIELDS:
        raise ValueError(
            f'Unknown order_by: {order_by}. Use any of: {", ".join(CONTACT_SORT_FIELDS)}.'
        )
    params = {
        'offset': str(offset),
        'order_by': str(CONTACT_SORT_FIELDS[order_by]),
        'order_type': order_type,
        'include_custom_fields': _flag(include_custom_fields),
    }
    if company:
        params['company'] = company
    response = await _get(env_config, 'contacts', params)
    return response.json()


async def get_contact_details(
    env_config: dict[str, str], email: str, secondary: bool = False
) -> dict[str, Any]:
    if not email.strip():
        raise ValueError('email must not be empty.')
    param = 'secondary_email' if secondary else 'primary_email'
    response = await _get(env_config, 'contacts/details', {param: email})
    return response.json()


async def list_kb_articles(env_config: dict[str, str]) -> dict[str, Any]:
    response = await _get(env_config, 'kb/article/')
    return response.json()


async def get_kb_article(env_config: dict[str, str], title: str) -> dict[str, Any]:
    if not title.strip():
        raise ValueError('title must not be empty.')
    response = await _get(env_config, 'kb/article/details', {'article_name': title})
    return response.json()


async def list_locations(env_config: dict[str, str]) -> dict[str, Any]:
    response = await _get(env_config, 'asset_mgmt/locations')
    return response.json()


async def get_location_details(env_config: dict[str, str], location_name: str) -> dict[str, Any]:
    if not location_name.strip():
        raise ValueError('location_name must not be empty.')
    response = await _get(
        env_config, 'asset_mgmt/locations/details', {'location_name': location_name}
    )
    return response.json()


def _check_location_fields(fields: dict[str, str | None]) -> None:
    too_long = [
        f'{name} (max {LOCATION_FIELD_LIMITS[name]} characters)'
        for name, value in fields.items()
        if value is not None and len(value) > LOCATION_FIELD_LIMITS[name]
    ]
    if too_long:
        raise ValueError(f'Too long: {", ".join(too_long)}.')


async def create_location(
    env_config: dict[str, str],
    location_name: str,
    parent_location_name: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    location_address: str | None = None,
    location_city: str | None = None,
    location_state: str | None = None,
    location_country: str | None = None,
    location_zipcode: str | None = None,
) -> dict[str, Any]:
    if not location_name.strip():
        raise ValueError('location_name must not be empty.')
    body = {
        'location_name': location_name,
        'parent_location_name': parent_location_name or None,
        'contact_name': contact_name,
        'contact_email': contact_email,
        'contact_phone': contact_phone,
        'location_address': location_address,
        'location_city': location_city,
        'location_state': location_state,
        'location_country': location_country,
        'location_zipcode': location_zipcode,
    }
    body = {key: value for key, value in body.items() if value is not None}
    _check_location_fields(body)
    response = await _post(env_config, 'asset_mgmt/locations/create', body)
    return response.json()


async def update_location(
    env_config: dict[str, str],
    location_name: str,
    new_location_name: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    location_address: str | None = None,
    location_city: str | None = None,
    location_state: str | None = None,
    location_country: str | None = None,
    location_zipcode: str | None = None,
) -> dict[str, Any]:
    if not location_name.strip():
        raise ValueError('location_name must not be empty.')
    if new_location_name is not None and not new_location_name.strip():
        raise ValueError('new_location_name must not be empty.')
    body = {
        'location_name': new_location_name,
        'contact_name': contact_name,
        'contact_email': contact_email,
        'contact_phone': contact_phone,
        'location_address': location_address,
        'location_city': location_city,
        'location_state': location_state,
        'location_country': location_country,
        'location_zipcode': location_zipcode,
    }
    # Desk365 only changes the fields present in the body.
    body = {key: value for key, value in body.items() if value is not None}
    if not body:
        raise ValueError('Nothing to update: set at least one field to change.')
    _check_location_fields(body)
    response = await _put(
        env_config, 'asset_mgmt/locations/update', body, {'location_name': location_name}
    )
    return response.json()
