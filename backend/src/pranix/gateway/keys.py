# SPDX-License-Identifier: AGPL-3.0-only
"""chart_key = HMAC(pepper, canonical inputs)[:16] (LOG-03): correlates log lines for the same
chart without containing birth data. Name and pronouns are never part of it (FR-INP-08)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

import structlog

from ..config.settings import Settings
from ..ephemeris.master import BirthInput

log = structlog.get_logger()
_dev_pepper: bytes | None = None


def pepper(settings: Settings) -> bytes:
    """The configured pepper; in dev/test a random per-process one (with a warning) if blank."""
    global _dev_pepper
    if settings.chart_key_pepper is not None:
        return settings.chart_key_pepper.get_secret_value().encode()
    if settings.env == "prod":
        raise RuntimeError("PRANIX_CHART_KEY_PEPPER is required in prod")
    if _dev_pepper is None:
        _dev_pepper = secrets.token_bytes(32)
        log.warning("config.dev_pepper", detail="chart_key pepper not set; using a random one for this run")
    return _dev_pepper


def chart_key(p: bytes, inp: BirthInput) -> str:
    c = inp.canonical()
    msg = "|".join(
        [
            c.local_datetime.isoformat(),
            c.tz,
            f"{c.lat:.4f}",
            f"{c.lon:.4f}",
            str(c.birth_time_known),
            c.time_accuracy or "",
            c.disambiguation or "",
            c.ruleset,
        ]
    )
    return hmac.new(p, msg.encode(), hashlib.sha256).hexdigest()[:16]
