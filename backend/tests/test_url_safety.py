"""SSRF protection: which URLs the backend refuses to fetch."""

import asyncio
import ipaddress

import pytest

from app import url_safety
from app.url_safety import UnsafeUrlError, resolve_safe_addresses


def resolve(url: str):
    return asyncio.run(resolve_safe_addresses(url))


@pytest.fixture
def dns(monkeypatch):
    """Make any hostname resolve to the addresses a test chooses."""

    def answer(*addresses: str) -> None:
        ips = [ipaddress.ip_address(a) for a in addresses]
        monkeypatch.setattr(url_safety, "_resolve_host", lambda host, port: ips)

    return answer


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1",
     "0.0.0.0", "::1", "fe80::1", "::ffff:127.0.0.1", "203.0.113.7"],
)
def test_private_and_reserved_addresses_are_refused(dns, address):
    dns(address)
    with pytest.raises(UnsafeUrlError, match="private or reserved"):
        resolve("https://looks-public.example/")


def test_one_bad_address_among_good_ones_is_enough_to_refuse(dns):
    dns("93.184.215.14", "127.0.0.1")
    with pytest.raises(UnsafeUrlError):
        resolve("https://mixed.example/")


def test_public_addresses_are_returned_once_each_in_order(dns):
    dns("93.184.215.14", "2606:2800:21f:cb07::1", "93.184.215.14")
    assert [str(ip) for ip in resolve("https://example.com/")] == ["93.184.215.14", "2606:2800:21f:cb07::1"]


@pytest.mark.parametrize("url", ["ftp://example.com/", "file:///etc/passwd", "javascript:alert(1)"])
def test_only_http_and_https(url):
    with pytest.raises(UnsafeUrlError, match="Only http"):
        resolve(url)


def test_names_that_dont_resolve_are_refused(monkeypatch):
    def fail(host, port):
        raise url_safety.socket.gaierror("no such name")

    monkeypatch.setattr(url_safety, "_resolve_host", fail)
    with pytest.raises(UnsafeUrlError, match="Could not resolve"):
        resolve("https://does-not-exist.example/")


def test_allow_private_urls_skips_the_check(override_settings, dns):
    dns("127.0.0.1")
    override_settings(allow_private_urls=True)
    assert resolve("http://localhost:8001/") == []
