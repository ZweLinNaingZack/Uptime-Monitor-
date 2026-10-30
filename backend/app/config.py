"""Application settings, read once from environment variables.

Why environment variables? The same code runs on your laptop and on a server; only the
configuration changes. Keeping secrets and machine-specific values out of the code is
one of the "twelve-factor app" rules.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Read a `.env` file (if one exists) into os.environ. Real environment variables win,
# so `set ALLOW_PRIVATE_URLS=1` in your shell overrides the file.
load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str]
    allow_private_urls: bool


settings = Settings(
    database_url=os.getenv("DATABASE_URL", "sqlite:///./uptime.db"),
    cors_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_private_urls=_env_bool("ALLOW_PRIVATE_URLS", default=False),
)
