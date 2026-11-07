"""The actual uptime check: one HTTP GET, timed, turned into a CheckResult.

This module knows nothing about the database or the scheduler. Keeping it "pure"
(URL in, result out) makes it easy to read and easy to test on its own.
"""

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.url_safety import IPAddress, UnsafeUrlError, resolve_safe_addresses

CHECK_TIMEOUT_SECONDS = 10.0
# Shorter than the whole check, so one dead address leaves time to try the next one.
CONNECT_TIMEOUT_SECONDS = 4.0
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
    try:
        # asyncio.timeout puts ONE deadline on the whole check (DNS + connect + response
        # headers). httpx's own timeout is per phase (connect, read, ...), so on its own a
        # slow server could take several times 10 s in total.
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            # Re-check on every run, not just when the monitor is created: DNS records can
            # change after the URL was accepted.
            addresses = await resolve_safe_addresses(url)

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(CHECK_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS),
                # A redirect could point at http://127.0.0.1/ and skip our SSRF check, so we
                # do not follow it. A 3xx response already proves the server is alive.
                follow_redirects=False,
                # Ignore HTTP_PROXY/HTTPS_PROXY env vars: a proxy would do its own DNS lookup,
                # which would make our IP check meaningless.
                trust_env=False,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                status, reason, elapsed_ms = await _get_status(client, url, addresses)
    except UnsafeUrlError as exc:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error=str(exc))
    except httpx.InvalidURL:
        return CheckResult(
            is_up=False, status_code=None, response_ms=None, error="The URL is not valid."
        )
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


async def _get_status(
    client: httpx.AsyncClient, url: str, addresses: list[IPAddress]
) -> tuple[int, str, int]:
    """GET the URL through the approved IPs. Returns (status, reason, milliseconds).

    Sites often publish several addresses, and some may not work from here (an IPv6 address
    on a network without IPv6, say), so a failed connection moves on to the next one. Only
    connection failures do: once a server answers, that answer is the result.
    """
    last_error: httpx.TransportError | None = None
    for target in _pinned_targets(url, addresses):
        started = time.perf_counter()
        try:
            # client.stream() returns as soon as the status line and headers arrive and
            # does NOT download the body. A monitored URL might be a 2 GB file.
            async with client.stream(
                "GET", target.url, headers=target.headers, extensions=target.extensions
            ) as response:
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                return response.status_code, response.reason_phrase, elapsed_ms
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
    assert last_error is not None  # the loop always has at least one target
    raise last_error


@dataclass(frozen=True)
class _Target:
    url: httpx.URL
    headers: dict[str, str]
    extensions: dict[str, str]


def _pinned_targets(url: str, addresses: list[IPAddress]) -> list[_Target]:
    """Build one request per approved IP that still looks like a request for the hostname.

    We put the IP in the URL so httpx has no name left to look up, then restore the name in
    the two places the server reads it:
    - The Host header tells the server which of its websites we want.
    - `sni_hostname` does the same during the TLS handshake. It is also the name the
      certificate is checked against, so HTTPS verification still protects us.
    """
    original = httpx.URL(url)
    if not addresses:
        return [_Target(url=original, headers={}, extensions={})]
    return [
        _Target(
            url=original.copy_with(host=str(ip)),
            headers={"Host": original.netloc.decode("ascii")},
            extensions={"sni_hostname": original.raw_host.decode("ascii")},
        )
        for ip in addresses
    ]


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
