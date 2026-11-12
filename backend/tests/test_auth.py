"""The login: what's locked, how sessions work, and the protections around them."""

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuthSession

from .conftest import FRONTEND_ORIGIN, TEST_PASSWORD, use_session

PROTECTED = [
    ("GET", "/monitors"), ("POST", "/monitors"), ("GET", "/monitors/1"), ("PATCH", "/monitors/1"),
    ("DELETE", "/monitors/1"), ("POST", "/monitors/1/check"), ("GET", "/monitors/1/checks"),
    ("GET", "/monitors/1/stats"), ("GET", "/alerts"), ("GET", "/alerts/channels"),
    ("POST", "/alerts/test"), ("PUT", "/alerts/channels/discord"),
    ("PUT", "/alerts/channels/telegram"), ("DELETE", "/alerts/channels/discord"),
]


def login(client, password=TEST_PASSWORD, **kw):
    return client.post("/auth/login", json={"password": password}, **kw)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_everything_needs_a_login(client, method, path):
    client.cookies.clear()
    assert client.request(method, path, json={}).status_code == 401


def test_health_is_open(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_without_a_password_set_everything_stays_locked(client, override_settings):
    override_settings(admin_password="")
    assert client.get("/monitors").status_code == 503
    response = login(client, "")
    assert response.status_code == 503 and "ADMIN_PASSWORD" in response.json()["detail"]


def test_login_sets_a_safe_cookie(client):
    response = login(client)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "secure" not in cookie  # off by default, so http://localhost works
    assert client.get("/monitors").status_code == 200
    client.cookies.clear()


def test_only_the_hash_of_the_token_is_stored(client):
    token = login(client).cookies["uptime_session"]
    with SessionLocal() as db:
        hashes = list(db.scalars(select(AuthSession.token_hash)))
    assert len(hashes) == 1 and len(hashes[0]) == 64 and token not in hashes
    client.cookies.clear()


def test_wrong_and_made_up_credentials(client):
    assert login(client, "wrong").status_code == 401
    assert use_session(client, "made-up").get("/monitors").status_code == 401
    client.cookies.clear()


def test_logout_ends_that_session_for_good(client):
    token = login(client).cookies["uptime_session"]
    assert client.post("/auth/logout").status_code == 204
    # Replaying the old token, as someone who had copied it would, still fails.
    assert use_session(client, token).get("/monitors").status_code == 401
    client.cookies.clear()


def test_expired_sessions_are_refused(client):
    login(client)
    with SessionLocal() as db:
        for session in db.scalars(select(AuthSession)):
            session.expires_at = session.created_at.replace(year=2000)
        db.commit()
    assert client.get("/monitors").status_code == 401
    client.cookies.clear()


def test_five_wrong_passwords_block_login_but_not_existing_sessions(logged_in):
    session_cookie = logged_in.cookies["uptime_session"]
    codes = [login(logged_in, "guess").status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    blocked = login(logged_in)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert use_session(logged_in, session_cookie).get("/monitors").status_code == 200


def test_requests_from_other_sites_are_refused(logged_in):
    evil = {"Origin": "https://evil.example"}
    assert logged_in.post("/monitors", json={"name": "x", "url": "https://e.example"}, headers=evil).status_code == 403
    assert login(logged_in, headers=evil).status_code == 403
    ours = logged_in.post("/monitors", json={"name": "x", "url": "https://e.example"}, headers={"Origin": FRONTEND_ORIGIN})
    assert ours.status_code == 201


def test_cors_lets_only_our_frontend_send_cookies(client):
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ours = client.options("/monitors", headers={"Origin": FRONTEND_ORIGIN, **preflight})
    assert ours.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert ours.headers["access-control-allow-credentials"] == "true"
    evil = client.options("/monitors", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in evil.headers
