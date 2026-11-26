# SPDX-License-Identifier: AGPL-3.0-only
"""Chart Inspector data: GET /v1/profiles/{id}/inspect/{chart} (plan §8, D81, I1).

One call returns every target of one chart, so clicks never wait on the network. The set is built in
milliseconds from the held Master JSON and is deterministic, so its hash is the ETag (304 on a match).
Nothing about the person is logged: only the chart, the level, the count and the time taken.
"""

from __future__ import annotations

import time
from typing import Literal

import structlog
from fastapi import APIRouter, Header, Request, Response

from ..ephemeris.ruleset import load_ruleset
from ..insight.inspect_text import with_text
from ..jyotish import InspectionSet, build_set
from .problems import ProblemError
from .ratelimit import enforce
from .routes_charts import _chart

router = APIRouter(tags=["inspect"])
log = structlog.get_logger()


@router.get("/v1/profiles/{profile_id}/inspect/{chart}", response_model=InspectionSet)
def inspect_chart(
    request: Request,
    response: Response,
    profile_id: str,
    chart: Literal["d1", "d9"],
    if_none_match: str | None = Header(default=None),
) -> InspectionSet | Response:
    settings = request.app.state.settings
    if not settings.feature_inspect:
        raise ProblemError(404, "NOT_FOUND", "This feature is not switched on.")
    enforce(request.app.state.limits["inspect"], request, settings.trust_proxy)
    item = _chart(request, profile_id)
    started = time.perf_counter()
    try:
        data = with_text(
            build_set(
                item.master,
                chart,
                load_ruleset(
                    item.master["meta"]["ruleset"]["id"] + "@" + str(item.master["meta"]["ruleset"]["version"])
                ),
            )
        )
    except ValueError:
        raise ProblemError(422, "BIRTH_TIME_REQUIRED", "The D9 chart needs your birth time.") from None
    etag = data.etag()
    log.info(
        "inspect.built",
        chart=chart,
        level=data.level,
        targets=len(data.bundles),
        ms=round((time.perf_counter() - started) * 1000, 2),
    )
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return data
