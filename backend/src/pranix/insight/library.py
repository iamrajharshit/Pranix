# SPDX-License-Identifier: AGPL-3.0-only
"""Curated library (FR-LIB). Entries carry status draft|approved; production serves approved only
(FR-LIB-03). Development serves drafts so the dashboard has text before the owner's review."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Any

import yaml

FILES = ("signs", "nakshatras", "planets", "axis", "nature", "deities", "allies", "naming")


class LibraryGap(LookupError):
    """A needed entry is missing or not approved; the card degrades instead of failing."""


@cache
def _load(locale: str) -> Mapping[str, Any]:
    out: dict[str, Any] = {}
    for name in FILES:
        raw = resources.files("pranix.library").joinpath(locale, f"{name}.yaml").read_text(encoding="utf-8")
        out[name] = yaml.safe_load(raw)
    return out


class Library:
    def __init__(self, allow_drafts: bool, locale: str = "en") -> None:
        self.allow_drafts = allow_drafts
        self.data = _load(locale)

    def _ok(self, entry: Mapping[str, Any]) -> Mapping[str, Any]:
        status = entry.get("status")
        if status == "approved" or (self.allow_drafts and status == "draft"):
            return entry
        raise LibraryGap("entry not approved")

    def get(self, *path: str) -> Mapping[str, Any]:
        node: Any = self.data
        for p in path:
            if not isinstance(node, Mapping) or p not in node:
                raise LibraryGap("/".join(path))
            node = node[p]
        if not isinstance(node, Mapping):
            raise LibraryGap("/".join(path))
        return self._ok(node)

    def raw(self, *path: str) -> Any:
        """Unversioned helper text (labels inside a reviewed file)."""
        node: Any = self.data
        for p in path:
            node = node[p]
        return node

    def stats(self) -> dict[str, int]:
        counts = {"approved": 0, "draft": 0}

        def walk(n: Any) -> None:
            if isinstance(n, Mapping):
                if n.get("status") in counts:
                    counts[n["status"]] += 1
                for v in n.values():
                    walk(v)

        walk(self.data)
        return counts
