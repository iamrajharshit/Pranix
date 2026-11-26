# SPDX-License-Identifier: AGPL-3.0-only
"""GET /v1/profiles/{id}/insights: Server-Sent Events (FR-DASH-06).

Events: `plan` {modules, chart_ref} first, then one `insight` per module (SSE id = module_id,
data carries chart_ref), then `done` {degraded}. Costs one rate-limit token whatever the
module count. On reconnect the client asks again with modules= the ones it did not receive.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..insight.cards import MODULES
from .problems import ProblemError
from .ratelimit import enforce

router = APIRouter(tags=["insights"])


def _event(name: str, data: dict[str, Any], event_id: str | None = None) -> str:
    head = f"event: {name}\n" + (f"id: {event_id}\n" if event_id else "")
    return head + "data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n\n"


@router.get("/v1/profiles/{profile_id}/insights")
def stream_insights(
    request: Request,
    profile_id: str,
    modules: str | None = Query(default=None, max_length=200),
    locale: str = Query(default="en", pattern="^en$"),
) -> StreamingResponse:
    enforce(request.app.state.limits["insights"], request, request.app.state.settings.trust_proxy)
    item = request.app.state.guests.get(profile_id)
    if item is None:
        raise ProblemError(410, "CHART_EXPIRED", "This chart is no longer held on the server. It will be recalculated.")
    wanted = [m for m in (modules.split(",") if modules else MODULES) if m]
    unknown = [m for m in wanted if m not in MODULES]
    if unknown:
        raise ProblemError(422, "INVALID_REQUEST", "Some fields are missing or not valid: modules")
    plan = [m for m in MODULES if m in wanted]
    service = request.app.state.insights
    master = item.master

    return StreamingResponse(
        card_events(service.card, plan, master, profile_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def card_events(
    card: Callable[[str, Mapping[str, Any]], dict[str, Any]],
    plan: list[str],
    master: Mapping[str, Any],
    chart_ref: str,
) -> Iterator[str]:
    """The card stream. Cards are worked out four at a time and sent as each one is ready.

    The reader can leave mid-stream (Start over, Back). This generator is then closed on the server's
    event-loop thread, so closing must never wait for a slow card: with a local model a card can take
    minutes in line, and waiting froze every request (owner's laptop, 26 Nov: the oracle screen after
    building charts two or three times). Queued cards are cancelled; running ones finish on their own
    threads, and their results still fill the cache for next time."""
    yield _event("plan", {"modules": plan, "chart_ref": chart_ref})
    degraded = False
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cards")
    try:
        futures = {pool.submit(card, m, master): m for m in plan}
        for f in as_completed(futures):
            result = f.result()
            degraded = degraded or result["degraded"]
            yield _event("insight", {**result, "chart_ref": chart_ref}, result["module_id"])
        yield _event("done", {"degraded": degraded})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
