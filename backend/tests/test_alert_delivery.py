"""Sending to a channel: which failures are retried, and how long we wait."""

import asyncio

import httpx
import pytest

from app import alerts
from app.alerts import AlertDeliveryError, AlertStatus, ChannelResult, _overall_status

# Imported at collection time, before conftest replaces it with a recorder for each test.
from app.alerts import _post_with_retries as real_post


def run(codes, attempts=3, headers=None):
    """POST to a fake server answering with `codes` in turn. Returns (calls, waits, error)."""
    calls: list[int] = []
    waits: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        code = codes[len(calls)]
        calls.append(code)
        return httpx.Response(code, headers=headers or {})

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await real_post(client, "https://hooks.example/x", {"content": "hi"}, attempts)

    original_sleep = alerts.asyncio.sleep
    alerts.asyncio.sleep = no_wait
    try:
        asyncio.run(go())
        error = None
    except AlertDeliveryError as exc:
        error = str(exc)
    finally:
        alerts.asyncio.sleep = original_sleep
    return calls, waits, error


def test_success_first_time():
    assert run([204]) == ([204], [], None)


def test_server_errors_are_retried_with_growing_waits():
    assert run([500, 502, 200]) == ([500, 502, 200], [1.0, 2.0], None)


def test_gives_up_after_three_attempts():
    calls, _, error = run([500, 500, 500])
    assert len(calls) == 3 and error == "HTTP 500"


@pytest.mark.parametrize("code", [400, 401, 404])
def test_client_errors_are_not_retried(code):
    assert run([code]) == ([code], [], f"HTTP {code}")


def test_429_waits_as_long_as_asked_but_no_longer_than_30_seconds():
    assert run([429, 200], headers={"Retry-After": "7"})[1] == [7.0]
    assert run([429, 200], headers={"Retry-After": "600"})[1] == [30.0]


def test_errors_never_contain_the_url():
    _, _, error = run([401])
    assert "hooks.example" not in error


@pytest.mark.parametrize(
    ("oks", "status"),
    [([], AlertStatus.NO_CHANNELS), ([True, True], AlertStatus.SENT),
     ([True, False], AlertStatus.PARTIAL), ([False, False], AlertStatus.FAILED)],
)
def test_overall_status(oks, status):
    results = [ChannelResult(f"c{i}", ok, None if ok else "x") for i, ok in enumerate(oks)]
    assert _overall_status(results) is status
