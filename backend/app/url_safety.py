"""SSRF protection: refuse to fetch URLs that point at private or internal addresses.

What is SSRF?
    Server-Side Request Forgery. Our server fetches URLs that *users* type in. Without
    protection, a user could add http://127.0.0.1:8000/... or http://192.168.1.1/ and make
    OUR server talk to machines that only it can reach: the admin panel on localhost, the
    home router, a database on the private network, or the cloud "metadata" service at
    http://169.254.169.254/ that hands out the server's cloud credentials. The status code
    and response time we display would leak information about those internal systems.

The rule we enforce
    1. Only http and https.
    2. Resolve the hostname ourselves and reject the URL if ANY of the resolved addresses
       is not a public internet address (`ipaddress.ip_address(...).is_global`).
       "Any", not "the first": a hostname can resolve to several IPs and the HTTP client
       might pick a different one than we checked.

Tricky inputs this handles because we look at the *resolved IP*, not the text:
    http://localhost, http://[::1], http://2130706433 (127.0.0.1 written as a decimal
    number), http://0x7f.1, a public-looking hostname whose DNS points at 10.0.0.5, and
    IPv4-mapped IPv6 such as http://[::ffff:127.0.0.1].

KNOWN GAP: DNS rebinding (time-of-check vs time-of-use)
    We resolve the name here, and then httpx resolves it AGAIN when it connects. An
    attacker controlling a DNS server can answer "8.8.8.8" to our check and "127.0.0.1"
    a millisecond later to httpx (with a TTL of 0). Closing this gap properly means
    connecting to the exact IP we validated (a custom httpx transport that pins the IP
    while still sending the original Host header / TLS SNI), or routing all checks
    through an egress proxy that enforces the same rule. For a learning project we
    document it; see the README roadmap.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.config import settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeUrlError(ValueError):
    """Raised when a URL must not be fetched. The message is safe to show to users."""


def _is_public(ip: IPAddress) -> bool:
    # "::ffff:127.0.0.1" is an IPv6 address that really means the IPv4 address 127.0.0.1.
    # Unwrap it so we judge the address the connection will actually go to.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_global is False for private (10/8, 172.16/12, 192.168/16), loopback (127/8, ::1),
    # link-local (169.254/16 incl. the 169.254.169.254 metadata IP, fe80::/10),
    # carrier-grade NAT (100.64/10), unspecified (0.0.0.0, ::), reserved ranges, etc.
    return ip.is_global


def _resolve_host(host: str, port: int) -> list[IPAddress]:
    """Blocking DNS lookup. Returns every address the name resolves to."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[IPAddress] = []
    for _family, _type, _proto, _canonname, sockaddr in infos:
        # sockaddr[0] is the IP as text. IPv6 link-local addresses can carry a
        # "%interface" suffix (fe80::1%eth0) which ip_address() does not accept.
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        addresses.append(ipaddress.ip_address(raw_ip))
    return addresses


async def assert_url_is_safe(url: str) -> None:
    """Raise UnsafeUrlError unless `url` is http(s) and resolves only to public IPs."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http:// and https:// URLs can be monitored.")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("The URL has no hostname.")

    if settings.allow_private_urls:
        # Escape hatch for local development (monitoring http://127.0.0.1:8001 etc).
        return

    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:  # e.g. port 99999
        raise UnsafeUrlError("The URL has an invalid port.") from exc

    try:
        # socket.getaddrinfo is a *blocking* call: it can take seconds on a slow DNS server.
        # Called directly inside `async def`, it would freeze the whole event loop, so no
        # other request or scheduled check could run meanwhile. asyncio.to_thread runs it
        # in a worker thread and lets the event loop keep serving others while we wait.
        addresses = await asyncio.to_thread(_resolve_host, host, port)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeUrlError(f"Could not resolve hostname '{host}'.") from exc

    if not addresses:
        raise UnsafeUrlError(f"Could not resolve hostname '{host}'.")

    blocked = [ip for ip in addresses if not _is_public(ip)]
    if blocked:
        raise UnsafeUrlError(
            f"'{host}' resolves to a private or reserved address ({blocked[0]}). "
            "Only public internet addresses can be monitored."
        )
