"""Logging in and out. These are the only API endpoints that don't require a login."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import (
    NO_PASSWORD_MESSAGE,
    SESSION_COOKIE,
    create_session,
    end_session,
    password_is_correct,
    require_trusted_origin,
)
from app.config import settings
from app.database import get_db
from app.rate_limit import SlidingWindowLimiter, client_ip
from app.schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_trusted_origin)])

DbSession = Annotated[Session, Depends(get_db)]

# Only WRONG passwords count, so logging in normally can never lock you out. Five guesses
# every five minutes makes guessing even a mediocre password take years.
_failed_logins = SlidingWindowLimiter(limit=5, window_seconds=300)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginIn, request: Request, response: Response, db: DbSession) -> None:
    if not settings.admin_password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_PASSWORD_MESSAGE)
    ip = client_ip(request)
    _failed_logins.check(ip)
    if not password_is_correct(payload.password):
        _failed_logins.record(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong password.")
    _failed_logins.reset(ip)
    create_session(db, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    end_session(db, response, session_cookie)
