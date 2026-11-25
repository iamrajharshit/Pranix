# SPDX-License-Identifier: AGPL-3.0-only
"""Curated library (FR-LIB). Entries carry status draft|approved; production serves approved only
(FR-LIB-03). Development serves drafts so the dashboard has text before the owner's review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Any

import yaml

FILES = ("signs", "nakshatras", "planets", "axis", "nature", "deities", "allies", "naming")
# Deeper knowledge behind the readings (D80), drafted by Gemma and reviewed field by field by the owner.
# Optional: a kind with no file yet simply has no entries.
REVIEWED = ("nakshatra_deep", "sign_deep", "planet_deep")


class LibraryGap(LookupError):
    """A needed entry is missing or not approved; the card degrades instead of failing."""


@cache
def _load(locale: str) -> Mapping[str, Any]:
    out: dict[str, Any] = {}
    for name in FILES:
        raw = resources.files("pranix.library").joinpath(locale, f"{name}.yaml").read_text(encoding="utf-8")
        out[name] = yaml.safe_load(raw)
    folder = resources.files("pranix.library").joinpath(locale, "reviewed")
    for name in REVIEWED:
        f = folder.joinpath(f"{name}.yaml")
        out[name] = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.is_file() else {}
    return out


class Library:
    def __init__(self, allow_drafts: bool, locale: str = "en") -> None:
        self.allow_drafts = allow_drafts
        self.data = _load(locale)
        # Content version: part of every AI cache key, so approving or editing an entry retires
        # stale cached text automatically (plan section 18).
        raw = json.dumps([locale, allow_drafts, self.data], sort_keys=True, ensure_ascii=False, default=str)
        self.version = hashlib.sha256(raw.encode()).hexdigest()[:16]

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

    def deep(self, kind: str, key: str) -> dict[str, str] | None:
        """A reviewed deep entry without its status, or None if it is missing or not servable."""
        try:
            entry = self.get(kind, key)
        except LibraryGap:
            return None
        return {k: str(v) for k, v in entry.items() if k != "status"}

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
