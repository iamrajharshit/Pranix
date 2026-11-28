# SPDX-License-Identifier: AGPL-3.0-only
"""Insight pipeline (Requirements §7.3): curated card first, then optional AI phrasing.

Every module (D80) gets a structured reading (insight.reading.CardReading) written by the AI from
de-identified facts (insight.facts) and the curated draft; Pydantic checks the shape, the guardrails
check every field, and the entity check rejects any planet, sign or star the facts did not contain.
Results are cached by (module, prompt version, locale, fact nodes), single-flight, so one call
serves every chart that shares those facts. Any guardrail failure keeps the curated card.

Background re-wording (D77): a reading served as curated because no provider could answer is
offered to `insight.rewording`, which asks the local model later and fills the same cache entry.
"""

from __future__ import annotations

import hashlib
import json
import threading
import weakref
from collections.abc import Callable, Mapping
from importlib import resources
from typing import Any

import structlog
from pydantic import ValidationError

from ..llmgw.chain import Chain
from ..llmgw.tasks import TASKS
from ..store.cache import CacheStore, MemoryCacheStore
from . import cards
from .entities import unknown_entities
from .facts import facts_for
from .knowledge import knowledge_for
from .library import Library, LibraryGap
from .reading import CardReading, draft_of, merge
from .rewording import Job, Rewording
from .validators import GuardrailError, check_card

log = structlog.get_logger()

PROMPT_ID = "insight@4"
SCHEMA_VERSION = "2"
CACHE_TTL = 30 * 86_400
SYSTEM_PROMPT = resources.files("pranix.prompts").joinpath(f"{PROMPT_ID}.md").read_text(encoding="utf-8")


def nodes(module: str, m: Mapping[str, Any]) -> dict[str, Any]:
    """The de-identified facts a module depends on (D80: facts.facts_for)."""
    return facts_for(module, m)


class InsightService:
    def __init__(
        self,
        lib: Library,
        chain: Chain,
        locale: str = "en",
        cache: CacheStore | None = None,
        background: Chain | None = None,
        reword_max: int = 200,
        reword_gap_s: float = 10.0,
    ) -> None:
        self.lib, self.chain, self.locale = lib, chain, locale
        self.cache: CacheStore = cache if cache is not None else MemoryCacheStore()
        # One lock per key while someone needs it: a weak map, so finished keys don't pile up for ever
        # (bug bounty, 26 Nov: a plain dict kept a lock for every card meaning ever asked for).
        self._flights: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
        self._flights_lock = threading.Lock()
        # Optional hook for tools (llm bench): told why an AI answer was rejected. Never given the text.
        self.on_reject: Callable[[str, str, str], None] | None = None
        # D77: the local model re-words curated serves later, one at a time. None = switched off.
        self.rewording: Rewording | None = None
        if background is not None and background.configured:
            bg = background
            self.rewording = Rewording(
                run=lambda job: self._attempt(job, bg),
                store=lambda job, out: self.cache.put(job.key, out, CACHE_TTL),
                is_cached=lambda key: self.cache.get(key) is not None,
                max_pending=reword_max,
                gap_s=reword_gap_s,
            )

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
                    job = self._job(module, key, master, curated)
                    hit = self._attempt(job, self.chain)
                    if hit is not None:
                        self.cache.put(key, hit, CACHE_TTL)
                    elif self.rewording is not None:
                        self.rewording.offer(job)
        if hit is None:
            return {**curated, "degraded": True}
        return {**curated, **hit, "badge": "ai", "prompt_version": PROMPT_ID}

    def cached_card(self, module: str, master: Mapping[str, Any]) -> dict[str, Any]:
        """Card for images: AI text only if already cached, otherwise curated. Never calls a provider (D64)."""
        try:
            curated = cards.build(module, master, self.lib)
            check_card(curated, master["facts"])
        except (LibraryGap, GuardrailError):
            return cards.error_card(module)
        if module in cards.SYNTHESIS and curated["state"] == "ready":
            hit = self.cache.get(self._key(module, master))
            if hit is not None:
                return {**curated, **hit, "badge": "ai", "prompt_version": PROMPT_ID}
        return curated

    def _key(self, module: str, master: Mapping[str, Any]) -> str:
        raw = json.dumps(
            [module, PROMPT_ID, SCHEMA_VERSION, self.locale, self.lib.version, nodes(module, master)], sort_keys=True
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _reject(self, module: str, rule: str, where: str) -> bool:
        # rule and field/name only: never the answer text (it may echo facts; rule 3 keeps logs clean)
        log.info("insight.rejected", module=module, rule=rule)
        if self.on_reject is not None:
            self.on_reject(module, rule, where)
        return False

    def _flight(self, key: str) -> Any:
        with self._flights_lock:
            lock = self._flights.get(key)
            if lock is None:
                lock = self._flights[key] = _KeyLock()
            return lock

    def _job(self, module: str, key: str, master: Mapping[str, Any], curated: dict[str, Any]) -> Job:
        """Everything one AI attempt needs, already de-identified, so it can also run later (D77)."""
        facts = nodes(module, master)
        draft = draft_of(curated)
        knowledge = knowledge_for(module, master, self.lib)
        payload: dict[str, Any] = {"module": module, "facts": facts, "draft": draft}
        if knowledge:
            payload["knowledge"] = knowledge  # reviewed background (D80): draw on it, never copy it whole
        user = json.dumps(payload, ensure_ascii=False)
        given = user + json.dumps(curated, ensure_ascii=False)  # names the AI may use
        return Job(module, key, user, given, curated, tuple(master["facts"]))

    def _attempt(self, job: Job, chain: Chain) -> dict[str, Any] | None:
        module, curated = job.module, job.curated
        out: dict[str, Any] = {}

        def accept(text: str) -> bool:
            try:
                reading = CardReading.model_validate_json(text)
                cand = merge(curated, reading)
                check_card({**curated, **cand}, job.fact_ids)
            except ValidationError as e:
                err = e.errors()[0]
                return self._reject(module, "SCHEMA", ".".join(str(x) for x in err["loc"]) or err["type"])
            except GuardrailError as e:
                return self._reject(module, e.rule, e.field)
            except (ValueError, KeyError, TypeError):
                return self._reject(module, "BAD_JSON", "")
            prose = " ".join([cand["headline"], cand["summary"], cand["detail"], cand["reflect"] or ""]
                             + [i for sec in cand["sections"] for i in sec["items"]])  # fmt: skip
            names = unknown_entities(prose, job.given)
            if names:
                return self._reject(module, "UNKNOWN_ENTITY", ", ".join(names))
            out.update(cand)
            return True

        result = chain.generate(SYSTEM_PROMPT, job.user, module=module, accept=accept, task=TASKS["card_reading"])
        return out if result is not None else None


class _KeyLock:
    """A lock that a weak map can hold (threading.Lock itself can't be weakly referenced)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> bool:
        return self._lock.acquire()

    def __exit__(self, *exc: object) -> None:
        self._lock.release()
