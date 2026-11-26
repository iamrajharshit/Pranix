# SPDX-License-Identifier: AGPL-3.0-only
"""The card stream must never freeze the server (owner, 26 Nov; bug bounty, 26 Nov).

- Leaving mid-stream must not wait for slow cards (#54).
- Waiting for cards must not hold a request thread: it runs on the event loop, on a shared bounded pool.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pranix.gateway.routes_insights import card_events

PLAN = [f"m{i}" for i in range(12)]


def slow_cards(release: threading.Event, started: list[str]):  # type: ignore[no-untyped-def]
    def card(module: str, master: Any) -> dict[str, Any]:
        started.append(module)
        if module != "m0":
            release.wait(30)  # a local model: each card waits its turn for minutes
        return {"module_id": module, "degraded": False}

    return card


def test_closing_mid_stream_returns_at_once_and_cancels_queued_cards() -> None:
    release, started = threading.Event(), []  # type: ignore[var-annotated]
    pool = ThreadPoolExecutor(max_workers=4)

    async def run() -> float:
        stream = card_events(slow_cards(release, started), PLAN, {}, "chart", pool)
        assert (await anext(stream)).startswith("event: plan")
        assert (await anext(stream)).startswith("event: insight")  # one card arrived; slow ones still running
        t = time.perf_counter()
        await stream.aclose()  # the reader left
        return time.perf_counter() - t

    took = asyncio.run(run())
    running = len(started)
    release.set()
    pool.shutdown(wait=True)
    assert took < 0.5, f"closing waited {took:.1f} s for slow cards: every request would freeze"
    assert running == len(started) <= 5 and len(started) < len(PLAN)  # queued cards were cancelled, never run


def test_a_complete_stream_still_sends_every_card_and_done() -> None:
    def quick(module: str, master: Any) -> dict[str, Any]:
        return {"module_id": module, "degraded": module == "m3"}

    async def run() -> list[str]:
        with ThreadPoolExecutor(max_workers=4) as pool:
            return [e async for e in card_events(quick, PLAN, {}, "chart", pool)]

    events = asyncio.run(run())
    assert events[0].startswith("event: plan") and events[-1].startswith("event: done")
    assert sum(e.startswith("event: insight") for e in events) == 12
    assert '"degraded":true' in events[-1]


def test_many_waiting_streams_hold_no_threads_and_share_one_bounded_pool() -> None:
    """Forty dashboards waiting on a slow model used to hold forty request threads."""
    release = threading.Event()
    pool = ThreadPoolExecutor(max_workers=8)
    before = threading.active_count()

    def card(module: str, master: Any) -> dict[str, Any]:
        release.wait(30)
        return {"module_id": module, "degraded": False}

    async def run() -> int:
        streams = [card_events(card, PLAN, {}, f"c{i}", pool) for i in range(40)]
        for st in streams:
            await anext(st)  # each reader got its plan and now waits for cards
        waiters = [asyncio.ensure_future(anext(st)) for st in streams]
        await asyncio.sleep(0.3)
        busy = threading.active_count() - before
        release.set()
        await asyncio.gather(*waiters)
        for st in streams:
            await st.aclose()
        return busy

    busy = asyncio.run(run())
    pool.shutdown(wait=True)
    assert busy <= 8 + 2, f"{busy} threads for 40 waiting streams: the pool must stay bounded"
