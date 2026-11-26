# SPDX-License-Identifier: AGPL-3.0-only
"""Which address a rate limit counts against (bug bounty, 26 Nov).

A client writes whatever it likes at the left of X-Forwarded-For; only the entries our own proxies
add at the right can be believed. And one IPv6 home or phone owns a whole /64 of addresses, so a
limit keyed by the full address could be dodged by changing the last bits.
"""

from typing import Any

import pytest
from starlette.requests import Request

from pranix.gateway.ratelimit import client_key


def _req(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    scope: dict[str, Any] = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234)}
    return Request(scope)


def test_without_a_proxy_the_header_is_ignored() -> None:
    assert client_key(_req("198.51.100.7", "203.0.113.1"), trust_proxy=False) == "198.51.100.7"


def test_a_forged_left_entry_does_not_change_the_key() -> None:
    # A proxy that appends (Cloudflare, Render, nginx) turns "forged" into "forged, real".
    a = client_key(_req("10.0.0.2", "1.1.1.1, 198.51.100.7"), trust_proxy=True)
    b = client_key(_req("10.0.0.2", "2.2.2.2, 198.51.100.7"), trust_proxy=True)
    assert a == b == "198.51.100.7"


def test_caddy_single_entry_is_the_client() -> None:
    assert client_key(_req("172.18.0.3", "198.51.100.7"), trust_proxy=True) == "198.51.100.7"


def test_two_trusted_hops_take_the_second_from_the_right() -> None:
    r = _req("10.0.0.2", "6.6.6.6, 198.51.100.7, 10.0.0.9")
    assert client_key(r, trust_proxy=True, hops=2) == "198.51.100.7"


def test_fewer_entries_than_hops_falls_back_to_the_leftmost() -> None:
    assert client_key(_req("10.0.0.2", "198.51.100.7"), trust_proxy=True, hops=3) == "198.51.100.7"


@pytest.mark.parametrize(
    "xff", ["", " , ", "not-an-ip", "999.1.1.1", "x" * 5000], ids=["empty", "commas", "word", "bad-ip", "huge"]
)
def test_junk_header_uses_the_peer(xff: str) -> None:
    assert client_key(_req("198.51.100.7", xff), trust_proxy=True) == "198.51.100.7"


def test_ipv6_is_counted_per_slash_64() -> None:
    a = client_key(_req("2001:db8:1:2:aaaa::1"), trust_proxy=False)
    b = client_key(_req("2001:db8:1:2:ffff:ffff:ffff:ffff"), trust_proxy=False)
    c = client_key(_req("2001:db8:1:3::1"), trust_proxy=False)
    assert a == b == "2001:db8:1:2::/64" and c != a


def test_ipv4_mapped_ipv6_counts_as_the_ipv4_address() -> None:
    assert client_key(_req("::ffff:198.51.100.7"), trust_proxy=False) == "198.51.100.7"
