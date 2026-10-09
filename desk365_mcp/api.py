import httpx


def _api_url(env_config: dict[str, str], path: str) -> str:
    return f'https://{env_config["SUBDOMAIN"]}.desk365.io/apis/v3/{path}'


def _headers(env_config: dict[str, str]) -> dict[str, str]:
    return {'Authorization': env_config['API_KEY']}


async def ping(env_config: dict[str, str]) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(_api_url(env_config, 'ping'), headers=_headers(env_config))
        response.raise_for_status()
        return response.text
