# SPDX-License-Identifier: AGPL-3.0-only
"""Structured JSON logging with a scrubber (LOG-01, LOG-02).

Personal data must never be logged. Callers should not pass it in the first place; the
scrubber is the safety net: it drops blocked keys and redacts values that look like
emails, ISO dates or coordinate pairs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

BLOCKED_KEYS = frozenset(
    {
        "dob",
        "date_of_birth",
        "tob",
        "time_of_birth",
        "local_datetime",
        "birth",
        "lat",
        "lon",
        "latitude",
        "longitude",
        "place",
        "place_label",
        "name",
        "pronouns",
        "email",
        "inputs_echo",
        "token",
        "cookie",
        "sid",
        "authorization",
        "password",
        "prompt",
        "response",
        "body",
    }
)
_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"),
    re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"),
)
REDACTED = "[redacted]"


def scrub(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    out: dict[str, Any] = {}
    for k, v in event.items():
        if k.lower() in BLOCKED_KEYS:
            out[k] = REDACTED
        elif isinstance(v, str) and k != "timestamp":
            for p in _PATTERNS:
                v = p.sub(REDACTED, v)
            out[k] = v
        else:
            out[k] = v
    return out


def configure(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            scrub,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        # No file argument: always print to the current sys.stdout (never a stream captured at startup).
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
