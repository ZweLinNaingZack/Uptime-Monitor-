"""Login: one shared password, and a session cookie that proves you entered it.

The flow:
1. POST /auth/login with the password. If it's right, we create a long random token, save
   its hash in `auth_sessions`, and give the browser the token in a cookie.
2. The browser sends that cookie with every request. `require_login` hashes it and looks it
   up. A match that hasn't expired means you're logged in.
3. POST /auth/logout deletes the row, so that token never works again.

The cookie's settings each block a specific attack:
- HttpOnly: JavaScript can't read it, so a script injected into a page can't steal it.
- SameSite=Lax: browsers leave it off POST/PATCH/DELETE requests started by other sites.
- Secure (COOKIE_SECURE=1): it's only ever sent over HTTPS, so nobody on the network sees it.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, utcnow
from app.models import AuthSession

# The frontend's proxy.ts checks for this cookie name too.
SESSION_COOKIE = "uptime_session"
SESSION_LIFETIME = timedelta(days=7)

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Failing closed: with no password set, the API stays locked rather than open to everyone.
NO_PASSWORD_MESSAGE = "No password is set. Add ADMIN_PASSWORD to backend/.env and restart the backend."


def _hash_token(token: str) -> str:
    # A plain, fast hash is fine here because the token is 256 random bits, far too many to
    # guess. Slow hashes such as bcrypt exist for passwords, which people choose badly.
    return hashlib.sha256(token.encode()).hexdigest()


def password_is_correct(password: str) -> bool:
    # compare_digest takes the same time wherever the first difference is. With `==`, an
    # attacker could time many guesses and work out the password one character at a time.
    return hmac.compare_digest(password.encode(), settings.admin_password.encode())


def create_session(db: Session, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_hash_token(token), expires_at=utcnow() + SESSION_LIFETIME))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def end_session(db: Session, response: Response, token: str | None) -> None:
    if token:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
        if session is not None:
            db.delete(session)
            db.commit()
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/"
    )


def require_trusted_origin(request: Request) -> None:
    """Refuse changes requested by a page from a site we don't recognise.

    SameSite doesn't cover everything, because every port on localhost counts as the same
    site. Browsers add an Origin header to these requests and page scripts can't fake it.
    Requests with no Origin (curl, or our own Next.js server) aren't from a browser page,
    so there's no logged-in victim to protect, and they still need a valid cookie.
    """
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin and origin not in settings.cors_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This origin is not allowed.")


def require_login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """A dependency that protects an endpoint: it raises unless you're logged in."""
    require_trusted_origin(request)
    if not settings.admin_password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_PASSWORD_MESSAGE)
    if session_cookie:
        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == _hash_token(session_cookie),
                AuthSession.expires_at > utcnow(),
            )
        )
        if session is not None:
            return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Please log in.")

