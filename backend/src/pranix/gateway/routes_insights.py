# SPDX-License-Identifier: AGPL-3.0-only
"""GET /v1/profiles/{id}/insights: Server-Sent Events (FR-DASH-06).

Events: `plan` {modules, chart_ref} first, then one `insight` per module (SSE id = module_id,
data carries chart_ref), then `done` {degraded}. Costs one rate-limit token whatever the
module count. On reconnect the client asks again with modules= the ones it did not receive.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import Executor
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
        card_events(service.card, plan, master, profile_id, request.app.state.card_pool),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def card_events(
    card: Callable[[str, Mapping[str, Any]], dict[str, Any]],
    plan: list[str],
    master: Mapping[str, Any],
    chart_ref: str,
    pool: Executor,
) -> AsyncIterator[str]:
    """The card stream: every card is handed to the shared card pool at once and sent as soon as it's ready.

    It waits on the event loop (asyncio), not in a request thread. A synchronous stream held one of the
    server's 40 request threads while it waited, so forty dashboards waiting on a slow model stalled every
    other request (bug bounty, 26 Nov). When the reader leaves (Start over, Back), cards still queued are
    cancelled and nothing waits for the ones already running; their results still fill the cache."""
    yield _event("plan", {"modules": plan, "chart_ref": chart_ref})
    futures = [asyncio.wrap_future(pool.submit(card, m, master)) for m in plan]
    degraded = False
    try:
        for next_done in asyncio.as_completed(futures):
            result = await next_done
            degraded = degraded or result["degraded"]
            yield _event("insight", {**result, "chart_ref": chart_ref}, result["module_id"])
        yield _event("done", {"degraded": degraded})
    finally:
        for f in futures:
            f.cancel()  # a queued card never starts; a running one finishes on its own thread
