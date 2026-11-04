"""HTTP endpoints for alert channels and alert history.

Channels are configured through environment variables, not through this API. There is no
login yet, so an endpoint that accepted a webhook URL would let anyone who can reach the
server redirect your alerts, or make the server POST to any address (SSRF). This API can
only report WHETHER a channel is set up. It never returns the secret itself.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import configured_channels, send_to_all_channels
from app.database import get_db
from app.models import AlertEvent, Monitor
from app.schemas import AlertChannelOut, AlertEventOut, AlertTestResultOut

router = APIRouter(prefix="/alerts", tags=["alerts"])

DbSession = Annotated[Session, Depends(get_db)]

_ALL_CHANNELS = ("discord", "telegram")
_TEST_MESSAGE = "✅ Test alert from Uptime Monitor. This channel is working."


@router.get("/channels", response_model=list[AlertChannelOut])
def list_channels() -> list[AlertChannelOut]:
    configured = configured_channels()
    return [AlertChannelOut(name=name, configured=name in configured) for name in _ALL_CHANNELS]


@router.post("/test", response_model=list[AlertTestResultOut])
async def send_test_alert() -> list[AlertTestResultOut]:
    if not configured_channels():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No alert channel is configured. Add one to backend/.env and restart the backend.",
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
