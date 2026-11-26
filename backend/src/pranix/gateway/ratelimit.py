# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory token buckets per client and route group (NFR-SEC-08, Tier A).

State is per process and resets on restart, which is acceptable on the free tier (Runbook 4.4).
"""

from __future__ import annotations

import ipaddress

from fastapi import Request

from ..util.tokenbucket import TokenBucket
from .problems import ProblemError

__all__ = ["TokenBucket", "client_key", "enforce"]


def _normal(addr: str) -> str | None:
    """One key per client: an IPv4 address, or an IPv6 /64 (one home or phone owns a whole /64)."""
    try:
        ip = ipaddress.ip_address(addr.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


def client_key(request: Request, trust_proxy: bool, hops: int = 1) -> str:
    """The address a rate limit counts against (bug bounty, 26 Nov).

    Only entries our own proxies add at the right of X-Forwarded-For can be believed; a client can
    write anything at the left. With `hops` trusted proxies the client is the hops-th entry from the
    right. Caddy (D66) drops any incoming value and writes one entry, so one hop is the default.
    """
    peer = request.client.host if request.client else "unknown"
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")[:1024]
        entries = [e for e in (part.strip() for part in fwd.split(",")) if e]
        if entries:
            found = _normal(entries[-min(hops, len(entries))])
            if found:
                return found
    return _normal(peer) or peer


def enforce(bucket: TokenBucket, request: Request, trust_proxy: bool) -> None:
    hops = getattr(request.app.state.settings, "proxy_hops", 1)
    wait = bucket.take(client_key(request, trust_proxy, hops))
    if wait is not None:
        raise ProblemError(
            429, "RATE_LIMITED", "Too many requests. Take a breath and try again shortly.", retry_after=wait
        )
