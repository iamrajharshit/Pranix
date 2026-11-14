# SPDX-License-Identifier: AGPL-3.0-only
"""App factory. P0 serves only /healthz, /readyz and /version; feature routes arrive in P1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .. import __version__
from ..config.settings import get_settings
from ..ephemeris import selftest, swe
from ..ephemeris.master import SCHEMA_VERSION
from ..ephemeris.ruleset import load_ruleset
from ..obs.logging import configure

log = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    configure()
    state: dict[str, Any] = {"ready": False, "failures": []}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        swe.init(settings.ephe_path)
        result = selftest.run()
        state["ready"], state["failures"] = result.ok, result.failures
        log.info("selftest.result", ok=result.ok, failures=result.failures, ephemeris_mode=swe.mode())
        yield

    app = FastAPI(title="Pranix API", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        if state["ready"]:
            return JSONResponse({"status": "ready"})
        return JSONResponse({"status": "not_ready", "failures": state["failures"]}, status_code=503)

    @app.get("/version")
    def version() -> dict[str, Any]:
        rs = load_ruleset()
        return {
            "engine_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "ruleset": {"id": rs.id, "version": rs.version, "hash": rs.hash},
            "ephemeris_mode": swe.mode(),
            "feature_flags": {"chat": settings.feature_chat, "passkeys": settings.feature_passkeys},
        }

    return app


app = create_app()
