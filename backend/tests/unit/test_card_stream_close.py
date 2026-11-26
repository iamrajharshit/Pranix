# SPDX-License-Identifier: AGPL-3.0-only
"""The card stream must never freeze the server when the reader leaves mid-stream (owner, 26 Nov)."""

import threading
import time
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
    stream = card_events(slow_cards(release, started), PLAN, {}, "chart")
    assert next(stream).startswith("event: plan")
    assert next(stream).startswith("event: insight")  # one card arrived; three slow ones are still running
    t = time.perf_counter()
    stream.close()  # the reader left: the server closes the stream (on its event-loop thread)
    took = time.perf_counter() - t
    running = len(started)
    release.set()
    assert took < 0.5, f"closing waited {took:.1f} s for slow cards: every request would freeze"
    time.sleep(0.3)
    assert len(started) == running <= 5 and len(started) < len(PLAN)  # queued cards were cancelled, never run


def test_a_complete_stream_still_sends_every_card_and_done() -> None:
    def quick(module: str, master: Any) -> dict[str, Any]:
        return {"module_id": module, "degraded": module == "m3"}

    events = list(card_events(quick, PLAN, {}, "chart"))
    assert events[0].startswith("event: plan") and events[-1].startswith("event: done")
    assert sum(e.startswith("event: insight") for e in events) == 12
    assert '"degraded":true' in events[-1]
