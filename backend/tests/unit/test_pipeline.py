# SPDX-License-Identifier: AGPL-3.0-only
from datetime import date
from typing import Any

from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight.library import Library, LibraryGap
from pranix.insight.pipeline import InsightService
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Stub
from pranix.util.tokenbucket import TokenBucket

M = compute(GOLDEN, date(2026, 11, 14))
LIB = Library(allow_drafts=True)
GOOD = {  # the structured reading shape (D80)
    "headline": "Warm Leo, steady Taurus Moon",
    "in_short": "You meet life warmly and feel safe in calm.",
    "what_it_means": "You meet the world warmly. " * 10,
    "strengths": ["Warmth"],
    "growth_edges": ["Letting others lead sometimes"],
    "in_daily_life": ["Start the day with one calm, unhurried task"],
    "reflect": "Where do you feel most at ease being seen?",
}


def chain(*stubs: Stub) -> Chain:
    return Chain([Link(s, TokenBucket(600)) for s in stubs])


def test_ai_phrasing_is_used_and_cached() -> None:
    s = Stub(reply=GOOD)
    svc = InsightService(LIB, chain(s))
    c1 = svc.card("identity", M)
    c2 = svc.card("identity", M)
    assert c1["badge"] == "ai" and c1["headline"] == GOOD["headline"] and c1["prompt_version"] == "insight@3"
    assert c2 == c1 and s.calls == 1  # second card served from cache
    assert c1["fact_ids"] == svc.card("identity", M)["fact_ids"]


def test_bad_ai_output_keeps_the_curated_card() -> None:
    bad = {**GOOD, "in_short": "You were born in 1984 and are lucky."}
    svc = InsightService(LIB, chain(Stub(reply=bad)))
    c = svc.card("identity", M)
    assert c["badge"] == "curated" and c["degraded"] is True and "1984" not in c["summary"]


def test_rate_limited_provider_falls_through_to_the_next() -> None:
    first, second = Stub(error="rate_limited"), Stub(reply=GOOD)
    svc = InsightService(LIB, chain(first, second))
    assert svc.card("identity", M)["badge"] == "ai" and first.calls == 1 and second.calls == 1
    svc.card("motive", M)
    assert first.calls == 1  # breaker open until Retry-After: not called again


def test_no_keys_means_curated() -> None:
    plain = InsightService(LIB, Chain([])).card("identity", M)
    assert plain["badge"] == "curated" and plain["degraded"] is False


class GapLibrary(Library):
    """Production library with one entry missing (all entries are approved since D69)."""

    def get(self, *path: str) -> Any:
        if path[:1] == ("signs",):
            raise LibraryGap("/".join(path))
        return super().get(*path)


def test_library_gap_gives_an_error_card() -> None:
    c = InsightService(GapLibrary(allow_drafts=False), Chain([])).card("identity", M)
    assert c["state"] == "error" and c["degraded"] is True
