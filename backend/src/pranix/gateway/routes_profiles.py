# SPDX-License-Identifier: AGPL-3.0-only
"""Guest charts: POST/GET/DELETE /v1/profiles (FR-GST-01, FR-INP, FR-AGE).

Nothing about the person is persisted or logged; only the derived Master JSON is kept in memory.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from ..contracts.birth import BirthInputModel, PlaceById
from ..ephemeris.master import BirthInput, compute, dasha_seed
from ..ephemeris.timeconv import MIN_YEAR, BirthTimeError
from ..geo.tz import tz_at
from .keys import chart_key, pepper
from .problems import ProblemError
from .ratelimit import enforce
from .routes_geo import geo_index

router = APIRouter(tags=["profiles"])
log = structlog.get_logger()

MESSAGES = {
    "AMBIGUOUS_LOCAL_TIME": "That time happened twice that day because the clocks changed. Choose earlier or later.",
    "NONEXISTENT_LOCAL_TIME": "That time did not exist that day because the clocks moved forward.",
    "OUT_OF_RANGE": "The birth date must be between 1800 and today.",
}


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February -> 1 March
        return d.replace(year=d.year + years, month=3, day=1)


def _resolve_place(request: Request, body: BirthInputModel) -> tuple[float, float, str]:
    if isinstance(body.place, PlaceById):
        p = geo_index(request).get(body.place.place_id)
        if p is None:
            raise ProblemError(422, "INVALID_PLACE", "We could not find that place. Search again or enter coordinates.")
        return p.lat, p.lon, p.tz
    lat, lon = round(body.place.lat, 4), round(body.place.lon, 4)
    tz = tz_at(lat, lon)  # server-derived; never trusted from the client
    if tz is None:
        raise ProblemError(422, "INVALID_PLACE", "Those coordinates have no land time zone.")
    return lat, lon, tz


def _check_date(local: datetime, tz: str) -> None:
    today = datetime.now(ZoneInfo(tz)).date()
    d = local.date()
    if d.year < MIN_YEAR or d > today:
        raise ProblemError(422, "OUT_OF_RANGE", MESSAGES["OUT_OF_RANGE"])
    if _add_years(d, 18) > today:
        raise ProblemError(422, "UNDER_AGE_PROFILE", "Charts are for people aged 18 or over.")


@router.post("/v1/profiles", status_code=201)
def create_profile(
    request: Request,
    body: BirthInputModel,
    x_age_confirmed: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    if x_age_confirmed != "true":
        raise ProblemError(412, "AGE_CONFIRMATION_REQUIRED", "Please confirm you are 18 or older first.")
    settings = request.app.state.settings
    enforce(request.app.state.limits["profiles"], request, settings.trust_proxy)
    started = time.perf_counter()

    try:
        local = datetime.strptime(body.local_datetime, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise ProblemError(422, "INVALID_REQUEST", "Some fields are missing or not valid: local_datetime") from None
    lat, lon, tz = _resolve_place(request, body)
    _check_date(local, tz)

    inp = BirthInput(local, tz, lat, lon, body.birth_time_known, body.time_accuracy, body.disambiguation, body.ruleset)
    try:
        master = compute(inp, datetime.now(UTC).date())
    except BirthTimeError as e:
        raise ProblemError(
            422, e.code, MESSAGES.get(e.code, "That birth time is not valid."), options=e.options or None
        ) from None

    key = chart_key(pepper(settings), inp)
    item = request.app.state.guests.put(master, key, dasha_seed(inp))
    log.info(
        "profile.created",
        chart_key=key,
        birth_time_known=inp.birth_time_known,
        ephemeris_mode=master["meta"]["ephemeris_mode"],
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return JSONResponse(
        {"profile_id": item.profile_id, "expires_at": item.expires_iso, "master": master}, status_code=201
    )


def _expired() -> ProblemError:
    return ProblemError(410, "CHART_EXPIRED", "This chart is no longer held on the server. It will be recalculated.")


@router.get("/v1/profiles/{profile_id}")
def get_profile(request: Request, profile_id: str) -> dict[str, Any]:
    item = request.app.state.guests.get(profile_id)
    if item is None:
        raise _expired()
    return {"profile_id": item.profile_id, "expires_at": item.expires_iso, "master": item.master}


@router.delete("/v1/profiles/{profile_id}", status_code=204)
def delete_profile(request: Request, profile_id: str) -> Response:
    request.app.state.guests.delete(profile_id)
    return Response(status_code=204)
