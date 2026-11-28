# SPDX-License-Identifier: AGPL-3.0-only
"""The body-size cap holds however the body arrives (bug bounty, 26 Nov).

The old middleware read only the Content-Length header, so a chunked upload (no Content-Length)
or a header that understates the body went straight through to the route and its JSON parser.
"""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from spa_client import TestClient

from pranix.gateway.app import MAX_BODY_BYTES, BodyLimit, create_app

SAMPLE = {"place": {"place_id": "geonames:100001"}, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _chunks(total: int, size: int = 1024) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b" " * n


def test_chunked_body_over_the_cap_is_refused(client: TestClient) -> None:
    # httpx sends a generator body with Transfer-Encoding: chunked and no Content-Length.
    r = client.post(
        "/v1/profiles",
        content=_chunks(MAX_BODY_BYTES * 4),
        headers={"Content-Type": "application/json", "X-Age-Confirmed": "true"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_chunked_body_under_the_cap_still_works(client: TestClient) -> None:
    raw = json.dumps(SAMPLE).encode()
    r = client.post(
        "/v1/profiles",
        content=iter([raw[:10], raw[10:]]),
        headers={"Content-Type": "application/json", "X-Age-Confirmed": "true"},
    )
    assert r.status_code == 201


def test_a_header_that_understates_the_body_cannot_slip_past() -> None:
    """Raw ASGI: the header says 10 bytes, the body keeps coming. The app must never see it."""
    seen: list[int] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        body = b""
        while True:
            m = await receive()
            body += m.get("body", b"")
            if not m.get("more_body"):
                break
        seen.append(len(body))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    chunk = b"x" * 1024
    messages = [{"type": "http.request", "body": chunk, "more_body": True} for _ in range(20)]
    messages.append({"type": "http.request", "body": b"", "more_body": False})
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"content-length", b"10")]}
    asyncio.run(BodyLimit(app)(scope, receive, send))
    assert seen == []
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("value", [b"99999999", b"-1", b"abc"])
def test_bad_or_huge_content_length_is_refused_up_front(value: bytes) -> None:
    calls: list[int] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        calls.append(1)

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        raise AssertionError("the body must not be read")

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"content-length", value)]}
    asyncio.run(BodyLimit(app)(scope, receive, send))
    assert calls == []
    assert sent[0]["status"] in (400, 413)
