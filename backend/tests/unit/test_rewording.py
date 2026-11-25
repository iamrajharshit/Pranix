# SPDX-License-Identifier: AGPL-3.0-only
"""Background re-wording (D77): curated serves are re-worded later by the local model and cached."""

import time
from datetime import date
from typing import Any

from pranix.config.settings import Settings
from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight.library import Library
from pranix.insight.pipeline import InsightService
from pranix.insight.rewording import Job, Rewording
from pranix.llmgw import build
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import OpenAICompatible, Stub
from pranix.util.tokenbucket import TokenBucket

M = compute(GOLDEN, date(2026, 11, 14))
LIB = Library(allow_drafts=True)
GOOD = {
    "headline": "Warm Leo, steady Taurus Moon",
    "in_short": "You meet life warmly and feel safe in calm.",
    "what_it_means": "You meet the world warmly. " * 10,
    "strengths": ["Warmth"],
    "growth_edges": ["Letting others lead sometimes"],
    "in_daily_life": ["Start the day with one calm, unhurried task"],
    "reflect": "Where do you feel most at ease being seen?",
}


class Recording(Stub):
    """A stub that keeps every payload it was sent."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.users: list[str] = []

    def generate(self, system: str, user: str, timeout: float) -> tuple[str, Any]:
        self.users.append(user)
        return super().generate(system, user, timeout)


def chain(*stubs: Stub) -> Chain:
    return Chain([Link(s, TokenBucket(600)) for s in stubs])


def service(live: Stub, bg: Stub) -> InsightService:
    svc = InsightService(LIB, chain(live), background=chain(bg), reword_gap_s=0.0)
    assert svc.rewording is not None
    svc.rewording.autostart = False  # run_pending() drives it here
    return svc


def test_curated_serve_is_reworded_later_and_the_next_reader_gets_ai() -> None:
    live, bg = Recording(error="rate_limited"), Recording(reply=GOOD)
    svc = service(live, bg)
    first = svc.card("identity", M)
    assert first["badge"] == "curated" and first["degraded"] is True
    assert svc.rewording is not None and svc.rewording.stats.pending == 1
    assert svc.rewording.run_pending() == 1
    second = svc.card("identity", M)
    assert second["badge"] == "ai" and second["headline"] == GOOD["headline"]
    assert svc.rewording.stats.done == 1 and bg.calls == 1
    assert bg.users == live.users  # the background call sends exactly what the live call sent


def test_the_same_reading_is_queued_once() -> None:
    svc = service(Stub(error="down"), Stub(reply=GOOD))
    svc.card("identity", M)
    svc.card("identity", M)
    assert svc.rewording is not None and svc.rewording.stats.pending == 1


def test_a_refused_background_answer_gets_one_more_turn_then_is_dropped() -> None:
    bad = {**GOOD, "in_short": "You were born in a lucky year, nineteen eighty four, 1984."}
    bg = Stub(reply=bad)
    svc = service(Stub(error="down"), bg)
    svc.card("identity", M)
    assert svc.rewording is not None
    svc.rewording.run_pending()
    assert bg.calls == 2 and svc.rewording.stats.failed == 1 and svc.rewording.stats.pending == 0
    assert svc.card("identity", M)["badge"] == "curated"
    assert svc.rewording.stats.pending == 1  # a later curated serve may offer it again


def test_already_cached_job_is_skipped() -> None:
    bg = Stub(reply=GOOD)
    svc = service(Stub(error="down"), bg)
    svc.card("identity", M)
    assert svc.rewording is not None
    key = svc._key("identity", M)
    svc.cache.put(key, {"headline": "x"}, 60)  # a live call answered meanwhile
    svc.rewording.run_pending()
    assert bg.calls == 0


def test_full_list_drops_new_work() -> None:
    rw = Rewording(run=lambda j: None, store=lambda j, o: None, is_cached=lambda k: False, max_pending=1,
                   autostart=False)  # fmt: skip
    job = Job("identity", "k1", "{}", "", {}, ())
    assert rw.offer(job) is True
    assert rw.offer(Job("identity", "k2", "{}", "", {}, ())) is False
    assert rw.stats.dropped == 1


def test_worker_thread_fills_the_cache() -> None:
    svc = InsightService(LIB, chain(Stub(error="down")), background=chain(Stub(reply=GOOD)), reword_gap_s=0.0)
    svc.card("identity", M)
    deadline = time.monotonic() + 5
    while svc.cache.get(svc._key("identity", M)) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert svc.card("identity", M)["badge"] == "ai"
    assert svc.rewording is not None
    svc.rewording.stop()


def test_no_background_chain_means_no_rewording() -> None:
    assert InsightService(LIB, chain(Stub(error="down"))).rewording is None
    assert InsightService(LIB, chain(Stub(error="down")), background=Chain([])).rewording is None


def test_background_chain_shares_the_local_provider_and_bucket() -> None:
    s = Settings(local_llm_url="http://localhost:11434/v1")
    live = build.insights_chain(s)
    bg = build.background_chain(s, live)
    assert bg is not None and len(bg.links) == 1
    local = next(li for li in live.links if isinstance(li.provider, OpenAICompatible))
    assert bg.links[0].provider is local.provider and bg.links[0].bucket is local.bucket
    assert build.reword_gap_s(s) == 60.0 / s.local_llm_rpm


def test_background_chain_off_without_local_model_or_when_switched_off() -> None:
    assert build.background_chain(Settings(llm_chains="cloud"), Chain([])) is None
    s = Settings(local_llm_url="http://localhost:11434/v1", background_reword=False)
    assert build.background_chain(s, build.insights_chain(s)) is None
    f = Settings(llm_fake="ok")
    assert build.background_chain(f, build.insights_chain(f)) is None
