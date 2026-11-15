# SPDX-License-Identifier: AGPL-3.0-only
"""Place search and map-pin lookup (FR-GEO-01, D64)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ..geo.index import GeoIndex
from ..geo.tz import tz_at
from .problems import ProblemError
from .ratelimit import enforce

router = APIRouter(tags=["geo"])


def geo_index(request: Request) -> GeoIndex:
    g: GeoIndex | None = request.app.state.geo
    if g is None:
        raise ProblemError(503, "SERVICE_NOT_READY", "Place search is not available yet.", retry_after=30)
    return g


@router.get("/v1/places")
def search_places(
    request: Request, q: str = Query(min_length=2, max_length=80), limit: int = Query(default=8, ge=1, le=10)
) -> list[dict[str, Any]]:
    """Offline autocomplete; [] when nothing matches."""
    enforce(request.app.state.limits["places"], request, request.app.state.settings.trust_proxy)
    return [p.to_dict() for p in geo_index(request).search(q, limit)]


@router.get("/v1/places/nearest")
def nearest_place(
    request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)
) -> dict[str, Any]:
    """Nearest place within 50 km or null; tz always from the coordinates."""
    enforce(request.app.state.limits["places"], request, request.app.state.settings.trust_proxy)
    lat, lon = round(lat, 4), round(lon, 4)
    tz = tz_at(lat, lon)
    if tz is None:
        raise ProblemError(422, "OCEAN_OR_NO_TZ", "That point has no land time zone. Pick a point on land.")
    hit = geo_index(request).nearest(lat, lon)
    return {"place": hit[0].to_dict() if hit else None, "tz": tz, "distance_km": round(hit[1]) if hit else None}
