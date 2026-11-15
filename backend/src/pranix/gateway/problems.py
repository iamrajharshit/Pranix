# SPDX-License-Identifier: AGPL-3.0-only
"""application/problem+json errors (ERR-04): {code, message, retry_after, reset_at, request_id, options?}.

Messages are fixed text per code. Request values are never echoed back or logged, because
they can be birth data (LOG-02).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

MEDIA = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
        reset_at: str | None = None,
        options: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message
        self.retry_after, self.reset_at, self.options = retry_after, reset_at, options


def problem(
    status: int,
    code: str,
    message: str,
    *,
    retry_after: int | None = None,
    reset_at: str | None = None,
    options: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "retry_after": retry_after,
        "reset_at": reset_at,
        "request_id": uuid.uuid4().hex[:16],
    }
    if options is not None:
        body["options"] = options
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(body, status_code=status, media_type=MEDIA, headers=headers)


def install(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_: Request, e: ProblemError) -> JSONResponse:
        return problem(e.status, e.code, e.message, retry_after=e.retry_after, reset_at=e.reset_at, options=e.options)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError) -> JSONResponse:
        # Field names only, never the submitted values.
        fields = sorted({".".join(str(p) for p in err.get("loc", ())[1:]) for err in e.errors()})
        return problem(422, "INVALID_REQUEST", "Some fields are missing or not valid: " + ", ".join(fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(e.status_code, "HTTP_ERROR")
        return problem(e.status_code, code, "Not found." if e.status_code == 404 else "Request not allowed.")
