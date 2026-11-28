# SPDX-License-Identifier: AGPL-3.0-only
"""A test client that behaves like our page: it sends the CSRF header (D85) on every request.

Tests that check the CSRF refusal itself use fastapi.testclient.TestClient directly."""

from typing import Any

from fastapi.testclient import TestClient as _Base

SPA = {"X-Requested-With": "pranix-spa"}


class TestClient(_Base):
    def __init__(self, app: Any, *args: Any, headers: dict[str, str] | None = None, **kw: Any) -> None:
        super().__init__(app, *args, headers={**SPA, **(headers or {})}, **kw)
