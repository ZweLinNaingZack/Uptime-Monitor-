"""The actual uptime check: one HTTP GET, timed, turned into a CheckResult.

This module knows nothing about the database or the scheduler. Keeping it "pure"
(URL in, result out) makes it easy to read and easy to test on its own.
"""

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.url_safety import UnsafeUrlError, assert_url_is_safe

CHECK_TIMEOUT_SECONDS = 10.0
USER_AGENT = "UptimeMonitor/0.1 (+self-hosted learning project)"


@dataclass(frozen=True)
class CheckResult:
    is_up: bool
    status_code: int | None
    response_ms: int | None
    error: str | None


async def perform_check(url: str) -> CheckResult:
    """GET `url` once and report whether it is up.

    Up   = we got a 2xx or 3xx response.
    Down = 4xx/5xx, timeout, refused connection, DNS failure, or blocked by SSRF rules.

    Why `async def`? While we wait up to 10 s for a slow website, the event loop can run
    other checks and answer API requests. With a normal blocking HTTP library, one slow
    site would stall everything (or need one thread per check).
    """
    started = time.perf_counter()
    try:
        # asyncio.timeout puts ONE deadline on the whole check (DNS + connect + response
        # headers). httpx's own timeout is per phase (connect, read, ...), so on its own a
        # slow server could take several times 10 s in total.
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            # Re-check on every run, not just when the monitor is created: DNS records can
            # change after the URL was accepted.
            await assert_url_is_safe(url)

            async with httpx.AsyncClient(
                timeout=CHECK_TIMEOUT_SECONDS,
                # A redirect could point at http://127.0.0.1/ and skip our SSRF check, so we
                # do not follow it. A 3xx response already proves the server is alive.
                follow_redirects=False,
                # Ignore HTTP_PROXY/HTTPS_PROXY env vars: a proxy would do its own DNS lookup,
                # which would make our IP check meaningless.
                trust_env=False,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                # client.stream() returns as soon as the status line and headers arrive and
                # does NOT download the body. A monitored URL might be a 2 GB file.
                async with client.stream("GET", url) as response:
                    elapsed_ms = round((time.perf_counter() - started) * 1000)
                    status = response.status_code
                    reason = response.reason_phrase
    except UnsafeUrlError as exc:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error=str(exc))
    except (TimeoutError, httpx.TimeoutException):
        return CheckResult(
            is_up=False,
            status_code=None,
            response_ms=None,
            error=f"Timed out after {CHECK_TIMEOUT_SECONDS:.0f} seconds.",
        )
    except httpx.ConnectError as exc:
        return CheckResult(
            is_up=False, status_code=None, response_ms=None, error=_describe_connect_error(exc)
        )
    except httpx.HTTPError as exc:
        # Any other transport/protocol problem (malformed response, TLS error mid-stream...).
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        return CheckResult(
            is_up=False, status_code=None, response_ms=None, error=f"Request failed: {detail}"
        )

    if 200 <= status < 400:
        return CheckResult(is_up=True, status_code=status, response_ms=elapsed_ms, error=None)

    return CheckResult(
        is_up=False,
        status_code=status,
        response_ms=elapsed_ms,
        error=f"HTTP {status} {reason or 'Error'}".strip(),
    )


def _describe_connect_error(exc: httpx.ConnectError) -> str:
    """Turn low-level socket errors into a sentence a user understands."""
    # httpx wraps the real OS error (often several layers deep, e.g. "All connection
    # attempts failed"). Walk the chain of `raise ... from ...` causes to find it.
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, ConnectionRefusedError):
            return "Connection refused: nothing is listening on that host and port."
        cause = cause.__cause__ or cause.__context__

    text = str(exc).lower()
    if "refused" in text or "10061" in text:  # 10061 = WSAECONNREFUSED on Windows
        return "Connection refused: nothing is listening on that host and port."
    if "certificate" in text or "ssl" in text:
        return f"TLS/SSL error: {exc}"
    if "getaddrinfo" in text or "name or service not known" in text or "11001" in text:
        return "DNS lookup failed: the hostname could not be resolved."
    return f"Connection failed: {exc}" if str(exc) else "Connection failed."
