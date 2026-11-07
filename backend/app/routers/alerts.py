"""HTTP endpoints for alert channels and alert history.

Channels can be set up in `.env` or through this API, which is safe only because the whole
router requires a login. Even so, a stolen login must not turn this server into a tool for
POSTing to any address (SSRF), so the values have to match the real Discord and Telegram
formats below. The API can report WHETHER a channel is set up, but never returns its secret.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import channel_sources, configured_channels, send_to_all_channels
from app.database import get_db, utcnow
from app.models import AlertChannelSetting, AlertEvent, Monitor
from app.rate_limit import RateLimit
from app.schemas import (
    AlertChannelOut,
    AlertEventOut,
    AlertTestResultOut,
    DiscordChannelIn,
    TelegramChannelIn,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])

DbSession = Annotated[Session, Depends(get_db)]

_ALL_CHANNELS = ("discord", "telegram")
_TEST_MESSAGE = "✅ Test alert from Uptime Monitor. This channel is working."

# fullmatch, not search: the WHOLE value must fit. These patterns are what stop someone from
# saving a URL that points elsewhere, or a "token" that changes the path of the request.
_DISCORD_WEBHOOK = re.compile(
    r"https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"
)
_TELEGRAM_TOKEN = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")
_TELEGRAM_CHAT = re.compile(r"-?\d+|@[A-Za-z0-9_]{5,}")

_limit_channel_changes = RateLimit(limit=10, window_seconds=60)
# Each test sends real messages, so a stuck script mustn't be able to spam your channel.
_limit_test_alerts = RateLimit(limit=5, window_seconds=60)


def _channels_out() -> list[AlertChannelOut]:
    sources = channel_sources()
    return [
        AlertChannelOut(name=name, configured=name in sources, source=sources.get(name))
        for name in _ALL_CHANNELS
    ]


def _save_channel(db: Session, name: str, secret: str, chat_id: str | None = None) -> None:
    setting = db.get(AlertChannelSetting, name)
    if setting is None:
        setting = AlertChannelSetting(name=name, secret=secret)
        db.add(setting)
    setting.secret = secret
    setting.chat_id = chat_id
    setting.updated_at = utcnow()
    db.commit()


@router.get("/channels", response_model=list[AlertChannelOut])
def list_channels() -> list[AlertChannelOut]:
    return _channels_out()


@router.put(
    "/channels/discord",
    response_model=list[AlertChannelOut],
    dependencies=[Depends(_limit_channel_changes)],
)
def save_discord_channel(payload: DiscordChannelIn, db: DbSession) -> list[AlertChannelOut]:
    webhook_url = payload.webhook_url.strip()
    if not _DISCORD_WEBHOOK.fullmatch(webhook_url):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="That isn't a Discord webhook URL. It should start with "
            "https://discord.com/api/webhooks/.",
        )
    _save_channel(db, "discord", webhook_url)
    return _channels_out()


@router.put(
    "/channels/telegram",
    response_model=list[AlertChannelOut],
    dependencies=[Depends(_limit_channel_changes)],
)
def save_telegram_channel(payload: TelegramChannelIn, db: DbSession) -> list[AlertChannelOut]:
    bot_token, chat_id = payload.bot_token.strip(), payload.chat_id.strip()
    if not _TELEGRAM_TOKEN.fullmatch(bot_token):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="That isn't a Telegram bot token. BotFather gives you one like 123456:ABC-DEF...",
        )
    if not _TELEGRAM_CHAT.fullmatch(chat_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The chat ID should be a number, or a public channel name like @mychannel.",
        )
    _save_channel(db, "telegram", bot_token, chat_id)
    return _channels_out()


@router.delete(
    "/channels/{name}",
    response_model=list[AlertChannelOut],
    dependencies=[Depends(_limit_channel_changes)],
)
def remove_channel(name: str, db: DbSession) -> list[AlertChannelOut]:
    """Forget the dashboard's value. If `.env` also sets this channel, that value applies again."""
    setting = db.get(AlertChannelSetting, name)
    if setting is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="This channel has no dashboard settings to remove."
        )
    db.delete(setting)
    db.commit()
    return _channels_out()


@router.post(
    "/test", response_model=list[AlertTestResultOut], dependencies=[Depends(_limit_test_alerts)]
)
async def send_test_alert() -> list[AlertTestResultOut]:
    if not configured_channels():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No alert channel is set up yet. Add one above first.",
        )
    # attempts=1: when someone is watching a button, show a failure now instead of retrying.
    results = await send_to_all_channels(_TEST_MESSAGE, attempts=1)
    return [AlertTestResultOut(channel=r.channel, ok=r.ok, error=r.error) for r in results]


@router.get("", response_model=list[AlertEventOut])
def list_alert_events(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[AlertEventOut]:
    """Recent alerts, newest first, across all monitors."""
    stmt = (
        select(AlertEvent, Monitor.name)
        .join(Monitor, AlertEvent.monitor_id == Monitor.id)
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
        .limit(limit)
    )
    return [
        AlertEventOut(
            id=event.id,
            monitor_id=event.monitor_id,
            monitor_name=name,
            kind=event.kind,
            message=event.message,
            status=event.status,
            error=event.error,
            created_at=event.created_at,
            finished_at=event.finished_at,
        )
        for event, name in db.execute(stmt)
    ]
