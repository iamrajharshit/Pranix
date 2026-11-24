# SPDX-License-Identifier: AGPL-3.0-only
"""Entity check (D80): the AI may only name planets, signs and stars that it was given.

A model that writes "your Venus in Pisces" when the facts never mention Venus or Pisces has made
something up. Any such name in the answer that is absent from the facts and draft fails the answer.
"""

from __future__ import annotations

import re
from functools import cache

PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")


@cache
def vocabulary() -> tuple[re.Pattern[str], ...]:
    from ..ephemeris.ruleset import load_ruleset

    rs = load_ruleset()
    names = (*PLANETS, *rs.signs, *(n.name for n in rs.nakshatras))
    return tuple(re.compile(rf"\b{re.escape(n)}\b") for n in names)


def unknown_entities(answer: str, given: str) -> list[str]:
    """Names in `answer` that never appear in `given` (case-sensitive: these are proper names)."""
    out = []
    for rx in vocabulary():
        m = rx.search(answer)
        if m and not rx.search(given):
            out.append(m.group(0))
    return out
