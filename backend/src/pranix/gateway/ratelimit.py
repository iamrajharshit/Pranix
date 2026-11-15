# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory token buckets per client and route group (NFR-SEC-08, Tier A).

State is per process and resets on restart, which is acceptable on the free tier (Runbook 4.4).
"""

from __future__ import annotations

from fastapi import Request

from ..util.tokenbucket import TokenBucket
from .problems import ProblemError

__all__ = ["TokenBucket", "client_key", "enforce"]


def client_key(request: Request, trust_proxy: bool) -> str:
    """Client IP. Behind Render's proxy the first X-Forwarded-For entry is the client."""
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(bucket: TokenBucket, request: Request, trust_proxy: bool) -> None:
    wait = bucket.take(client_key(request, trust_proxy))
    if wait is not None:
        raise ProblemError(
            429, "RATE_LIMITED", "Too many requests. Take a breath and try again shortly.", retry_after=wait
        )
