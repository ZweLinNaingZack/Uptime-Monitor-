"""Alerts: decide when a monitor changed state, and tell Discord and/or Telegram.

The module has three parts, from simplest to most involved:
1. Pure decisions (`decide_alert`, `build_message`): plain data in, plain data out.
2. Channels (`send_discord`, `send_telegram`): one HTTP POST each, with retries.
3. Delivery (`dispatch_alert`): background tasks that send a saved AlertEvent and record
   what happened.

THE MOST IMPORTANT RULE IN THIS FILE: never put a webhook URL or bot token in a log line,
an error message, or an API response. Both are passwords that happen to look like URLs.
Exception text from HTTP libraries can contain the full URL, so errors here are built
only from status codes and exception class names, never from `str(exc)`.

The one place they are stored besides `.env` is the alert_channel_settings table, because
channels set up in the dashboard have to be readable when it's time to send.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, utcnow
from app.models import AlertChannelSetting, AlertEvent

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 8.0
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0  # waits 1 s, then 2 s
MAX_RETRY_AFTER_SECONDS = 30.0
# Discord rejects messages over 2000 characters and Telegram over 4096.
MAX_MESSAGE_LENGTH = 1900
# An alert this old is no longer useful ("down" from yesterday may be long fixed).
PENDING_ALERT_MAX_AGE = timedelta(hours=1)


class AlertKind(StrEnum):
    DOWN = "down"
    RECOVERED = "recovered"


class AlertStatus(StrEnum):
    PENDING = "pending"  # saved, not delivered yet
    SENT = "sent"  # every configured channel accepted it
    PARTIAL = "partial"  # at least one channel accepted it, at least one failed
    FAILED = "failed"  # no channel accepted it
    NO_CHANNELS = "no_channels"  # recorded, but no channel is configured


# ---------- 1. Pure decisions ----------


def decide_alert(
    previous_state: str | None, is_up: bool, consecutive_failures: int = 1, threshold: int = 1
) -> AlertKind | None:
    """Should this check result trigger an alert?

    Alert on CHANGES, not on every failed check, or a site that is down for an hour at a
    30-second interval would send you 120 messages. A failure only counts as a change once
    `threshold` checks in a row have failed, so one network blip stays quiet.

        previous     now                    alert
        None or up   up                     none
        None or up   down, below threshold  none       might be a blip
        None or up   down, at threshold     DOWN
        down         down                   none       you already know
        down         up                     RECOVERED
    """
    if is_up:
        return AlertKind.RECOVERED if previous_state == "down" else None
    if previous_state == "down" or consecutive_failures < threshold:
        return None
    return AlertKind.DOWN


def build_message(
    kind: AlertKind,
    name: str,
    url: str,
    checked_at: datetime,
    error: str | None = None,
    response_ms: int | None = None,
) -> str:
    """The alert text. Sent as plain text, so a monitor's name can't inject formatting."""
    timestamp = checked_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    if kind is AlertKind.DOWN:
        lines = [f"🔴 DOWN: {name}", url, f"Reason: {error or 'Unknown error'}", timestamp]
    else:
        detail = f"Response time: {response_ms} ms" if response_ms is not None else "Responding again"
        lines = [f"🟢 RECOVERED: {name}", url, detail, timestamp]
    message = "\n".join(lines)
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 1] + "…"
    return message


# ---------- 2. Channels ----------


class AlertDeliveryError(Exception):
    """A channel refused a message. The text is safe to store and show: it has no secrets."""


async def _post_with_retries(
    client: httpx.AsyncClient, url: str, payload: dict[str, object], attempts: int
) -> None:
    """POST JSON, retrying only failures that might go away on their own."""
    failure = "unknown error"
    for attempt in range(attempts):
        delay = RETRY_BACKOFF_SECONDS * 2**attempt
        try:
            response = await client.post(url, json=payload)
        except httpx.TransportError as exc:  # timeout, DNS, refused connection...
            failure = f"network error ({type(exc).__name__})"
        else:
            if response.is_success:
                return
            failure = f"HTTP {response.status_code}"
            if response.status_code == 429:
                # "Too many requests": the server says how long to wait. Respect it.
                delay = _retry_after_seconds(response, default=delay)
            elif response.status_code < 500:
                # 400/401/404 mean a wrong URL, token or chat ID. Retrying can't fix that.
                raise AlertDeliveryError(failure)
        if attempt + 1 < attempts:
            await asyncio.sleep(delay)
    raise AlertDeliveryError(failure)


def _retry_after_seconds(response: httpx.Response, default: float) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", default))
    except ValueError:
        return default
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


async def send_discord(
    client: httpx.AsyncClient, webhook_url: str, text: str, attempts: int = MAX_ATTEMPTS
) -> None:
    payload = {
        "content": text,
        # Without this, a monitor named "@everyone" would ping your whole server.
        "allowed_mentions": {"parse": []},
    }
    await _post_with_retries(client, webhook_url, payload, attempts)


async def send_telegram(
    client: httpx.AsyncClient, bot_token: str, chat_id: str, text: str, attempts: int = MAX_ATTEMPTS
) -> None:
    url = f"{settings.telegram_api_base}/bot{bot_token}/sendMessage"
    # No parse_mode: Telegram treats the text literally, so characters like "_" in a URL
    # can't break the message or inject formatting.
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    await _post_with_retries(client, url, payload, attempts)


Sender = Callable[[httpx.AsyncClient, str, int], Awaitable[None]]


def channel_sources() -> dict[str, str]:
    """Which channels are set up, and where from: {"telegram": "dashboard", ...}."""
    with SessionLocal() as db:
        saved = set(db.scalars(select(AlertChannelSetting.name)))
    sources: dict[str, str] = {}
    if "discord" in saved:
        sources["discord"] = "dashboard"
    elif settings.discord_webhook_url:
        sources["discord"] = "env"
    if "telegram" in saved:
        sources["telegram"] = "dashboard"
    elif settings.telegram_bot_token and settings.telegram_chat_id:
        sources["telegram"] = "env"
    return sources


def configured_channels() -> dict[str, Sender]:
    """The channels with complete settings, by name. Dashboard values override `.env`.

    The database is read on every call, so saving a new channel in the dashboard works
    straight away, without a restart.
    """
    with SessionLocal() as db:
        saved = {row.name: row for row in db.scalars(select(AlertChannelSetting))}

    channels: dict[str, Sender] = {}
    discord_url = saved["discord"].secret if "discord" in saved else settings.discord_webhook_url
    if discord_url:

        async def discord_sender(client: httpx.AsyncClient, text: str, attempts: int) -> None:
            await send_discord(client, discord_url, text, attempts)

        channels["discord"] = discord_sender

    if "telegram" in saved:
        bot_token, chat_id = saved["telegram"].secret, saved["telegram"].chat_id or ""
    else:
        bot_token, chat_id = settings.telegram_bot_token, settings.telegram_chat_id
    if bot_token and chat_id:

        async def telegram_sender(client: httpx.AsyncClient, text: str, attempts: int) -> None:
            await send_telegram(client, bot_token, chat_id, text, attempts)

        channels["telegram"] = telegram_sender
    return channels


@dataclass(frozen=True)
class ChannelResult:
    channel: str
    ok: bool
    error: str | None


async def send_to_all_channels(text: str, attempts: int = MAX_ATTEMPTS) -> list[ChannelResult]:
    """Send to every configured channel at once. One failing never blocks the other."""
    channels = configured_channels()
    async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS, follow_redirects=False) as client:
        # return_exceptions=True: collect failures as values instead of stopping at the first.
        outcomes = await asyncio.gather(
            *(send(client, text, attempts) for send in channels.values()),
            return_exceptions=True,
        )

    results: list[ChannelResult] = []
    for name, outcome in zip(channels, outcomes, strict=True):
        if isinstance(outcome, AlertDeliveryError):
            results.append(ChannelResult(name, False, str(outcome)))
        elif isinstance(outcome, Exception):
            # Unexpected, e.g. a malformed URL in .env. Only the class name: see top of file.
            results.append(ChannelResult(name, False, type(outcome).__name__))
        elif isinstance(outcome, BaseException):
            raise outcome  # task cancellation at shutdown: let it propagate
        else:
            results.append(ChannelResult(name, True, None))
    return results


# ---------- 3. Delivery of saved events ----------

# asyncio only keeps a WEAK reference to running tasks, so a task nobody else references
# can be garbage-collected before it finishes. This set keeps them alive.
_delivery_tasks: set[asyncio.Task[None]] = set()


def dispatch_alert(event_id: int) -> None:
    """Start delivering an event in the background and return immediately.

    The caller may be the "Check now" endpoint. Retries can take many seconds, and a slow
    Discord must not make the user's button (or the next scheduled check) wait for it.
    """
    task = asyncio.create_task(_deliver(event_id))
    _delivery_tasks.add(task)
    task.add_done_callback(_on_delivery_done)


def _on_delivery_done(task: asyncio.Task[None]) -> None:
    _delivery_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("Alert delivery crashed: %s", type(task.exception()).__name__)


async def _deliver(event_id: int) -> None:
    # Same three steps as run_check_for_monitor: read, then the slow network part with no
    # database session open, then a fresh session to save the outcome.
    with SessionLocal() as db:
        event = db.get(AlertEvent, event_id)
        if event is None:
            return  # its monitor was deleted, and the event with it
        message = event.message

    results = await send_to_all_channels(message) if configured_channels() else []

    with SessionLocal() as db:
        event = db.get(AlertEvent, event_id)
        if event is None:
            return  # deleted while we were sending
        event.status = _overall_status(results)
        failures = [f"{r.channel}: {r.error}" for r in results if not r.ok]
        event.error = "; ".join(failures) or None
        event.finished_at = utcnow()
        db.commit()
    logger.info("Alert %s finished with status %s", event_id, _overall_status(results))


def _overall_status(results: list[ChannelResult]) -> AlertStatus:
    if not results:
        return AlertStatus.NO_CHANNELS
    delivered = sum(r.ok for r in results)
    if delivered == len(results):
        return AlertStatus.SENT
    return AlertStatus.PARTIAL if delivered else AlertStatus.FAILED


def resume_pending_alerts() -> int:
    """Called at startup: finish alerts interrupted by a crash or restart. Returns the count.

    An event could be sent twice if the server stopped after Discord accepted it but
    before we saved "sent". That is deliberate: a duplicate alert beats a lost one.
    """
    cutoff = utcnow() - PENDING_ALERT_MAX_AGE
    to_send: list[int] = []
    with SessionLocal() as db:
        pending = db.scalars(select(AlertEvent).where(AlertEvent.status == AlertStatus.PENDING))
        for event in pending:
            if event.created_at < cutoff:
                event.status = AlertStatus.FAILED
                event.error = "Expired: the server was offline for too long to send it."
                event.finished_at = utcnow()
            else:
                to_send.append(event.id)
        db.commit()
    for event_id in to_send:
        dispatch_alert(event_id)
    return len(to_send)


async def drain_alerts(timeout: float = 5.0) -> None:
    """Called at shutdown: give in-flight alerts a moment to finish.

    Anything still running is cancelled and stays "pending", so the next startup sends it.
    """
    if not _delivery_tasks:
        return
    tasks = list(_delivery_tasks)
    _done, still_running = await asyncio.wait(tasks, timeout=timeout)
    for task in still_running:
        task.cancel()
    if still_running:
        await asyncio.gather(*still_running, return_exceptions=True)
