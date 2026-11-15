# SPDX-License-Identifier: AGPL-3.0-only
"""Place search and map-pin lookup (FR-GEO-01, D64)."""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

from ..geo.index import GeoIndex
from ..geo.tz import tz_at
from .problems import ProblemError
from .ratelimit import enforce

router = APIRouter(tags=["geo"])
log = structlog.get_logger()


RETRY_SECONDS = 10.0
_retry_lock = threading.Lock()


def geo_index(request: Request) -> GeoIndex:
    """The place index, loaded at startup; if it was missing then (e.g. built afterwards with
    tools/fetch_geonames.sh), retry opening it at most every RETRY_SECONDS instead of needing a restart."""
    state = request.app.state
    g: GeoIndex | None = state.geo
    if g is None:
        with _retry_lock:
            g = state.geo
            now = time.monotonic()
            if g is None and now - getattr(state, "geo_retry_at", float("-inf")) >= RETRY_SECONDS:
                state.geo_retry_at = now
                try:
                    g = state.geo = GeoIndex(state.settings.geo_db_path)
                except (OSError, sqlite3.Error):  # missing, or still being written
                    g = None
                else:
                    state.failures = [f for f in state.failures if f != "geo_index_missing"]
                    state.ready = not state.failures
                    log.info("geo.ready", places=g.count, late=True)
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
