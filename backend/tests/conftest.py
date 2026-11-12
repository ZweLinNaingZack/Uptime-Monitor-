"""Shared test setup. pytest loads this file before any test module.

Three rules keep the tests fast and reliable:
1. Settings come from environment variables that are set HERE, before the app is imported,
   so your own backend/.env (with its real password and tokens) is never used.
2. No test touches the network. DNS lookups, website checks and alert sending are all
   replaced with fakes that the tests control.
3. Every test starts from an empty database and fresh rate limits.
"""

import ipaddress
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="uptime-tests-"))
TEST_PASSWORD = "test-password-123"
FRONTEND_ORIGIN = "http://localhost:3000"

# Every setting is given explicitly. python-dotenv never overrides a variable that already
# exists, even an empty one, so nothing from your real .env can leak in.
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "CORS_ORIGINS": FRONTEND_ORIGIN,
        "ALLOW_PRIVATE_URLS": "0",
        "ADMIN_PASSWORD": TEST_PASSWORD,
        "COOKIE_SECURE": "0",
        "ALERT_FAILURE_THRESHOLD": "2",
        "RETENTION_DAYS": "90",
        "DISCORD_WEBHOOK_URL": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "TELEGRAM_API_BASE": "https://api.telegram.org",
    }
)

# Only now is it safe to import the app.
from fastapi.testclient import TestClient  # noqa: E402

from app import alerts, config, services, url_safety  # noqa: E402
from app.checker import CheckResult  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.rate_limit import reset_all_limiters  # noqa: E402

PUBLIC_IP = ipaddress.ip_address("93.184.215.14")


# ---------- Fakes ----------


@dataclass
class FakeChecker:
    """Stands in for perform_check. Returns queued results, then "up" forever."""

    queue: list[CheckResult] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    async def __call__(self, url: str) -> CheckResult:
        self.urls.append(url)
        if self.queue:
            return self.queue.pop(0)
        return up()

    def then(self, *results: CheckResult) -> None:
        self.queue.extend(results)


def up(ms: int = 50) -> CheckResult:
    return CheckResult(is_up=True, status_code=200, response_ms=ms, error=None)


def down(code: int = 500) -> CheckResult:
    return CheckResult(is_up=False, status_code=code, response_ms=10, error=f"HTTP {code}")


@dataclass
class SentAlerts:
    """Records what would have been POSTed to Discord or Telegram."""

    posts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, client: object, url: str, payload: dict[str, Any], attempts: int) -> None:
        self.posts.append((url, payload))

    def texts(self) -> list[str]:
        return [str(p.get("content") or p.get("text")) for _url, p in self.posts]


# ---------- Fixtures ----------

_checker = FakeChecker()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """One app for the whole run. `with` runs the startup code: migrations and scheduler."""
    with pytest.MonkeyPatch.context() as mp:
        # Patched for the whole session, because the scheduler can run a check at any time.
        mp.setattr(services, "perform_check", _checker)
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def fresh_state(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Before every test: empty tables, zero rate limits, fake DNS and fake alert sending.

    It asks for `client` so the app (and with it the database migrations) always starts
    first, even when the very first test to run doesn't use the API.
    """
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    reset_all_limiters()
    _checker.queue.clear()
    _checker.urls.clear()
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host, port: [PUBLIC_IP])
    yield


@pytest.fixture
def checker() -> FakeChecker:
    return _checker


@pytest.fixture(autouse=True)
def sent(monkeypatch: pytest.MonkeyPatch) -> SentAlerts:
    recorder = SentAlerts()
    monkeypatch.setattr(alerts, "_post_with_retries", recorder)
    return recorder


@pytest.fixture(autouse=True)
def scheduled(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The API's calls to schedule a monitor, recorded instead of performed.

    A real job would run a check in the background at an unpredictable moment, and a test
    counting checks would then fail now and then. The scheduler has tests of its own.
    """
    from app.routers import monitors

    calls: list[int] = []
    monkeypatch.setattr(monitors, "schedule_monitor", lambda monitor_id, _interval: calls.append(monitor_id))
    monkeypatch.setattr(monitors, "unschedule_monitor", lambda monitor_id: None)
    return calls


def use_session(client: TestClient, token: str) -> TestClient:
    """Make the client send this session token from now on, like a browser holding it."""
    client.cookies.clear()
    client.cookies.set("uptime_session", token)
    return client


@pytest.fixture
def logged_in(client: TestClient) -> Iterator[TestClient]:
    response = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 204
    yield client
    client.cookies.clear()


@pytest.fixture
def override_settings() -> Iterator[Any]:
    """Change settings for one test. `settings` is frozen, so this goes around that on purpose."""
    original = dict(config.settings.__dict__)

    def apply(**changes: object) -> None:
        for name, value in changes.items():
            object.__setattr__(config.settings, name, value)

    yield apply
    for name, value in original.items():
        object.__setattr__(config.settings, name, value)
