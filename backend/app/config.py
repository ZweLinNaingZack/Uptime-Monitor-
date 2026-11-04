"""Application settings, read once from environment variables.

Why environment variables? The same code runs on your laptop and on a server; only the
configuration changes. Keeping secrets and machine-specific values out of the code is
one of the "twelve-factor app" rules.
"""

import os
from dataclasses import dataclass, field

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
    # Alert channels. These values are SECRETS: anyone holding a Discord webhook URL or a
    # Telegram bot token can post as you. repr=False keeps them out of the text you get
    # from print(settings) or a logged traceback that shows this object.
    discord_webhook_url: str = field(default="", repr=False)
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = field(default="", repr=False)
    telegram_api_base: str = "https://api.telegram.org"


settings = Settings(
    database_url=os.getenv("DATABASE_URL", "sqlite:///./uptime.db"),
    cors_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_private_urls=_env_bool("ALLOW_PRIVATE_URLS", default=False),
    discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    # Only needed if you run your own Telegram Bot API server.
    telegram_api_base=os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").strip().rstrip("/"),
)
