# SPDX-License-Identifier: AGPL-3.0-only
"""The shape of each reviewed library file under `library/en/inspect/` (plan section 5, D78)."""

from __future__ import annotations

import re
from dataclasses import dataclass

PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
HOUSES = tuple(f"house_{n}" for n in range(1, 13))
LORDS = tuple(f"lord_{n}" for n in range(1, 13))
_ID = re.compile(r"^[a-z][a-z0-9_.]*$")


@dataclass(frozen=True)
class Kind:
    name: str
    levels: tuple[tuple[str, ...] | None, ...]  # allowed keys per level; None = any id like "dispositor.cycle"
    fields: tuple[str, ...]
    max_len: int
    max_sentences: int

    def expected(self) -> list[tuple[str, ...]] | None:
        """Every key path the file must eventually hold, or None for open-ended files."""
        if any(level is None for level in self.levels):
            return None
        paths: list[tuple[str, ...]] = [()]
        for level in self.levels:
            assert level is not None
            paths = [(*p, k) for p in paths for k in level]
        return paths

    def valid_path(self, path: tuple[str, ...]) -> bool:
        if len(path) != len(self.levels):
            return False
        return all(
            (_ID.match(seg) is not None) if lv is None else seg in lv for seg, lv in zip(path, self.levels, strict=True)
        )


KINDS: dict[str, Kind] = {
    k.name: k
    for k in (
        Kind("houses", (HOUSES,), ("arena", "healthy", "growth"), 200, 2),
        Kind("planet_in_house", (PLANETS, HOUSES), ("text",), 240, 2),
        Kind("lord_in_house", (LORDS, HOUSES), ("text",), 240, 2),
        Kind("signals", (None,), ("text",), 200, 2),
        Kind("bridge", (None,), ("text",), 240, 2),
    )
}
