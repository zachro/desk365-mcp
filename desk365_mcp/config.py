import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV_VARS = [
    'API_KEY',
    'SUBDOMAIN',
]
OPTIONAL_ENV_VARS = [
    'DEFAULT_AGENT_EMAIL',
]


def get_env_file(stage: str | None = None) -> Path:
    return PROJECT_ROOT / (f'{stage}.env' if stage else '.env')


def get_env_config(stage: str | None = None) -> dict[str, str]:
    env_file = get_env_file(stage)
    if stage and not env_file.is_file():
        raise FileNotFoundError(f'Env file for stage "{stage}" not found: {env_file}')
    load_dotenv(env_file)
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise ValueError(
            'Missing required environment variables: '
            f'{", ".join(missing)}. '
            f'Set them in {env_file} or as explicit environment variables.'
        )
    config = {var: os.environ[var] for var in REQUIRED_ENV_VARS}
    config.update({var: os.environ[var] for var in OPTIONAL_ENV_VARS if os.getenv(var)})
    return config
