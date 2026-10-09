import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV_VARS = [
    'API_KEY'
]


def _get_env_config() -> dict[str, str]:
    load_dotenv()
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise ValueError(
            'Missing required environment variables: '
            f'{", ".join(missing)}'
            f'Set them in {PROJECT_ROOT / ".env"} or as explicit environment variables.'
        )
    return {var: os.environ[var] for var in REQUIRED_ENV_VARS}


ENV_CONFIG = _get_env_config()
