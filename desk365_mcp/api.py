import json
from typing import Any

import httpx


def _api_url(env_config: dict[str, str], path: str) -> str:
    return f'https://{env_config["SUBDOMAIN"]}.desk365.io/apis/v3/{path}'


def _headers(env_config: dict[str, str]) -> dict[str, str]:
    return {'Authorization': env_config['API_KEY']}


def _flag(value: bool) -> str:
    return '1' if value else '0'


async def ping(env_config: dict[str, str]) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(_api_url(env_config, 'ping'), headers=_headers(env_config))
        response.raise_for_status()
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

    async with httpx.AsyncClient() as client:
        response = await client.get(
            _api_url(env_config, 'tickets'), headers=_headers(env_config), params=params
        )
        response.raise_for_status()
        return response.json()
