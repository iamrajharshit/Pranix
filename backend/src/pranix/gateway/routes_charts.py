# SPDX-License-Identifier: AGPL-3.0-only
"""Dasha timeline (FR-DSH-03, FR-UI-04) and server-rendered card images (D64)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from ..cardimg.render import CardImageInput, CardTextRejected
from ..ephemeris import dasha
from ..ephemeris.ruleset import load_ruleset
from ..insight.cards import MODULES
from .guest_store import GuestChart
from .problems import ProblemError
from .ratelimit import enforce

router = APIRouter(tags=["charts"])

# Labels and constellation accents mirror the dashboard design (canvas board 6).
CARD_LOOK: dict[str, tuple[str, str]] = {
    "identity": ("Who you are", "#F4C566"),
    "birthstar": ("Birth star", "#F4C566"),
    "nameletter": ("Naming syllable", "#F4C566"),
    "elements": ("Elemental nature", "#6FD6C9"),
    "doshas": ("Body-mind tendencies", "#6FD6C9"),
    "chakras": ("Energy centres", "#6FD6C9"),
    "motive": ("Core motive", "#A99CFF"),
    "season": ("Life season now", "#A99CFF"),
    "growth": ("Growth edges", "#A99CFF"),
    "deity": ("Your deity", "#F2A6C0"),
    "colors": ("Power colours", "#F2A6C0"),
    "days": ("Power days", "#F2A6C0"),
}


def _chart(request: Request, profile_id: str) -> GuestChart:
    item: GuestChart | None = request.app.state.guests.get(profile_id)
    if item is None:
        raise ProblemError(410, "CHART_EXPIRED", "This chart is no longer held on the server. It will be recalculated.")
    return item


@router.get("/v1/profiles/{profile_id}/dasha")
def dasha_periods(
    request: Request,
    profile_id: str,
    path: str | None = Query(default=None, pattern=r"^[A-Z][a-z](>[A-Z][a-z]){0,3}$"),
    cycle: int | None = Query(default=None, ge=1, le=dasha.MAX_CYCLE),
) -> list[dict[str, Any]]:
    """No path: the nine Mahadashas; path 'Ju>Ve': its nine children. Max depth five.
    cycle: which run of the 120-year sequence (D84); by default the one that contains today."""
    item = _chart(request, profile_id)
    m = item.master
    if not m["meta"]["birth_time_known"]:
        # Unknown time (D56): only when the chain is the same all day, and only levels one and two.
        if m["dasha"]["active_chain"] is None or (path and ">" in path):
            raise ProblemError(422, "BIRTH_TIME_REQUIRED", "This part of the timeline needs your birth time.")
    if item.seed is None:
        raise ProblemError(410, "CHART_EXPIRED", "This chart is no longer held on the server. It will be recalculated.")
    moon, birth = item.seed
    rs = load_ruleset()
    now = dasha.instant(datetime.now(UTC))
    try:
        periods = dasha.periods_at_path(rs, moon, birth, path, cycle or dasha.cycle_at(rs, moon, birth, now))
    except ValueError:
        raise ProblemError(422, "INVALID_REQUEST", "Some fields are missing or not valid: path") from None
    return [p.public_dict(now=now) for p in periods]  # D86 C1


@router.get("/v1/profiles/{profile_id}/cards/{module_id}.png")
def card_image(request: Request, profile_id: str, module_id: str) -> Response:
    enforce(request.app.state.limits["images"], request, request.app.state.settings.trust_proxy)
    if module_id not in MODULES:
        raise ProblemError(404, "CARD_NOT_AVAILABLE", "That card is not available as an image.")
    renderer = request.app.state.renderer
    if renderer is None:
        msg = "Card images are not available on this server."
        why = getattr(request.app.state, "renderer_problem", None)
        if why and request.app.state.settings.env != "prod":  # say what's missing while developing (runbook §6.2)
            msg += f" Missing here: {why}."
        raise ProblemError(503, "SERVICE_NOT_READY", msg, retry_after=60)
    item = _chart(request, profile_id)
    card = request.app.state.insights.cached_card(module_id, item.master)
    if card["state"] != "ready":
        raise ProblemError(404, "CARD_NOT_AVAILABLE", "This card cannot be saved as an image.")
    m = item.master
    label, accent = CARD_LOOK[module_id]
    star = m["nakshatra"]["name"] if module_id == "birthstar" and m["nakshatra"] else None
    deity = m["ishta_devta"]["main"].split(" ")[0] if module_id == "deity" and m["ishta_devta"] else None
    strip = re.compile(r"\{\{name\}\}, ")  # the name never appears on an image
    inp = CardImageInput(
        module_id,
        label,
        strip.sub("", card["headline"]),
        strip.sub("", card["summary"]),
        accent,
        star_key=star,
        deity_key=deity,
        source=card["badge"],
    )
    cache: dict[tuple[str, str, str], tuple[bytes, dict[str, str]]] = request.app.state.image_cache
    key = (profile_id, module_id, card["headline"] + card["summary"])
    hit = cache.get(key)
    if hit is None:
        try:
            hit = renderer.render(inp)
        except CardTextRejected:
            raise ProblemError(404, "CARD_NOT_AVAILABLE", "This card cannot be saved as an image.") from None
        if len(cache) > 256:
            cache.clear()
        cache[key] = hit
    png, headers = hit
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers={"ETag": headers["ETag"]})
    return Response(png, media_type="image/png", headers=headers)
