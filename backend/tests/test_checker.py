"""perform_check: one GET, judged up or down, sent only to the IPs that passed the SSRF check.

httpx.MockTransport answers requests from a function instead of the network, so these tests
can see exactly what was sent and decide how the "server" responds.
"""

import asyncio
import ipaddress

import httpx
import pytest

from app import checker, url_safety


@pytest.fixture
def server(monkeypatch):
    """Route every request perform_check makes to a fake server. Returns the request log."""
    requests: list[httpx.Request] = []
    behaviour = {"status": 200, "refuse": set()}

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host in behaviour["refuse"]:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(behaviour["status"])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)
    )
    return requests, behaviour


def check(url: str):
    return asyncio.run(checker.perform_check(url))


@pytest.mark.parametrize(("status", "is_up"), [(200, True), (204, True), (301, True), (404, False), (503, False)])
def test_2xx_and_3xx_are_up(server, status, is_up):
    server[1]["status"] = status
    result = check("https://example.com/")
    assert result.is_up is is_up
    assert result.status_code == status
    assert result.response_ms is not None


def test_request_goes_to_the_approved_ip_with_the_real_name(server):
    requests, _ = server
    check("https://example.com:8443/path?q=1")
    request = requests[0]
    assert request.url.host == "93.184.215.14"  # the IP from conftest's fake DNS
    assert request.url.port == 8443 and request.url.path == "/path" and request.url.query == b"q=1"
    assert request.headers["host"] == "example.com:8443"
    # The name TLS uses for SNI and for checking the certificate.
    assert request.extensions["sni_hostname"] == "example.com"


def test_a_dead_address_falls_through_to_the_next(server, monkeypatch):
    requests, behaviour = server
    ips = [ipaddress.ip_address("2606:2800::1"), ipaddress.ip_address("93.184.215.14")]
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host, port: ips)
    behaviour["refuse"].add("2606:2800::1")
    assert check("https://example.com/").is_up
    assert [r.url.host for r in requests] == ["2606:2800::1", "93.184.215.14"]


def test_all_addresses_dead_is_down(server):
    server[1]["refuse"].add("93.184.215.14")
    result = check("https://example.com/")
    assert not result.is_up and result.status_code is None
    assert result.error.startswith("Connection refused")


def test_blocked_url_is_down_without_any_request(server, monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host, port: [ipaddress.ip_address("127.0.0.1")])
    result = check("https://sneaky.example/")
    assert not result.is_up and "private or reserved" in result.error
    assert server[0] == []


def test_redirects_are_not_followed(server):
    requests, behaviour = server
    behaviour["status"] = 302
    assert check("https://example.com/").status_code == 302
    assert len(requests) == 1
