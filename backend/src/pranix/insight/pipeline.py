# SPDX-License-Identifier: AGPL-3.0-only
"""Insight pipeline (Requirements §7.3): curated card first, then optional AI phrasing.

For synthesis modules the AI only re-words the curated draft, given de-identified facts.
Results are cached by (module, prompt version, locale, fact nodes), single-flight, so one call
serves every chart that shares those facts. Any guardrail failure keeps the curated card.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from importlib import resources
from typing import Any

from ..llmgw.chain import Chain
from . import cards
from .library import Library, LibraryGap
from .validators import GuardrailError, check_card

PROMPT_ID = "insight@1"
SCHEMA_VERSION = "1"
CACHE_TTL = 30 * 86_400
SYSTEM_PROMPT = resources.files("pranix.prompts").joinpath(f"{PROMPT_ID}.md").read_text(encoding="utf-8")


def nodes(module: str, m: Mapping[str, Any]) -> dict[str, Any]:
    """The de-identified facts a module depends on (never date, time, place, name or numbers)."""
    ident = m["identity"]
    if module == "identity":
        return {
            "rising": ident["lagna"]["sign"] if ident["lagna"] else None,
            "moon": ident["moon"]["sign"] if ident["moon"] else None,
            "sun": ident["sun"]["sign"] if ident["sun"] else None,
        }
    if module == "elements":
        pct = m["elements"]["percent"]
        order = sorted(pct, key=lambda k: (-pct[k], k))
        return {"strongest": order[:2], "quietest": order[-1]}
    if module == "doshas":
        return {"pattern": m["doshas"]["label"], "leading": m["doshas"]["dominant"]}
    if module == "chakras":
        return {c["id"]: c["class"] for c in m["chakras"]}
    if module == "motive":
        axis = m["purpose"]["rahu_ketu_axis"]
        return {"soul_planet": m["purpose"]["atmakaraka"], "growth_house": axis["rahu_house"] if axis else None}
    if module == "season":
        chain = m["dasha"]["active_chain"]
        return {"period": chain[0]["lord"], "sub_period": chain[1]["lord"] if len(chain) > 1 else None}
    if module == "growth":
        axis = m["purpose"]["rahu_ketu_axis"]
        return {
            "quiet_centres": [c["id"] for c in m["chakras"] or [] if c["class"] == "low_activity"],
            "growth_house": axis["rahu_house"] if axis else None,
            "soul_planet": m["purpose"]["atmakaraka"],
        }
    raise ValueError(module)


class _TTLCache:
    def __init__(self, ttl: float, max_items: int = 5_000, clock: Callable[[], float] = time.time) -> None:
        self.ttl, self.max_items, self.clock = ttl, max_items, clock
        self._d: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, k: str) -> dict[str, Any] | None:
        with self._lock:
            v = self._d.get(k)
            if v is None or v[0] <= self.clock():
                self._d.pop(k, None)
                return None
            self._d.move_to_end(k)
            return v[1]

    def put(self, k: str, val: dict[str, Any]) -> None:
        with self._lock:
            self._d[k] = (self.clock() + self.ttl, val)
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)


class InsightService:
    def __init__(self, lib: Library, chain: Chain, locale: str = "en") -> None:
        self.lib, self.chain, self.locale = lib, chain, locale
        self.cache = _TTLCache(CACHE_TTL)
        self._flights: dict[str, threading.Lock] = {}
        self._flights_lock = threading.Lock()

    def card(self, module: str, master: Mapping[str, Any]) -> dict[str, Any]:
        try:
            curated = cards.build(module, master, self.lib)
            check_card(curated, master["facts"])
        except (LibraryGap, GuardrailError):
            return cards.error_card(module)
        if module not in cards.SYNTHESIS or curated["state"] != "ready" or not self.chain.configured:
            return curated
        key = self._key(module, master)
        hit = self.cache.get(key)
        if hit is None:
            with self._flight(key):  # single-flight: one call per key at a time
                hit = self.cache.get(key)
                if hit is None:
                    hit = self._phrase(module, master, curated)
                    if hit is not None:
                        self.cache.put(key, hit)
        if hit is None:
            return {**curated, "degraded": True}
        return {**curated, **hit, "badge": "ai", "prompt_version": PROMPT_ID}

    def _key(self, module: str, master: Mapping[str, Any]) -> str:
        raw = json.dumps([module, PROMPT_ID, SCHEMA_VERSION, self.locale, nodes(module, master)], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _flight(self, key: str) -> threading.Lock:
        with self._flights_lock:
            return self._flights.setdefault(key, threading.Lock())

    def _phrase(self, module: str, master: Mapping[str, Any], curated: dict[str, Any]) -> dict[str, Any] | None:
        draft = {k: curated[k] for k in ("headline", "summary", "detail", "sections")}
        user = json.dumps({"module": module, "facts": nodes(module, master), "draft": draft}, ensure_ascii=False)
        kinds = {s["kind"] for s in curated["sections"]}
        out: dict[str, Any] = {}

        def accept(text: str) -> bool:
            try:
                data = json.loads(text)
                cand = {
                    "headline": str(data["headline"]),
                    "summary": str(data["summary"]),
                    "detail": str(data["detail"]),
                    "sections": [
                        {"kind": s["kind"], "items": [str(i) for i in s["items"]][:3]}
                        for s in data.get("sections", [])
                        if s.get("kind") in kinds
                    ][:4],
                }
                check_card({**curated, **cand}, master["facts"])
            except (ValueError, KeyError, TypeError, GuardrailError):
                return False
            out.update(cand)
            return True

        result = self.chain.generate(SYSTEM_PROMPT, user, module=module, accept=accept)
        return out if result is not None else None
