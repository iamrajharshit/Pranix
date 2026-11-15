# SPDX-License-Identifier: AGPL-3.0-only
from datetime import date

from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight.library import Library
from pranix.insight.pipeline import InsightService
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Stub
from pranix.util.tokenbucket import TokenBucket

M = compute(GOLDEN, date(2026, 11, 14))
LIB = Library(allow_drafts=True)
GOOD = {
    "headline": "Warm Leo, steady Taurus Moon",
    "summary": "You meet life warmly and feel safe in calm.",
    "detail": "You meet the world warmly. " * 10,
    "sections": [{"kind": "strengths", "items": ["Warmth"]}],
}


def chain(*stubs: Stub) -> Chain:
    return Chain([Link(s, TokenBucket(600)) for s in stubs])


def test_ai_phrasing_is_used_and_cached() -> None:
    s = Stub(reply=GOOD)
    svc = InsightService(LIB, chain(s))
    c1 = svc.card("identity", M)
    c2 = svc.card("identity", M)
    assert c1["badge"] == "ai" and c1["headline"] == GOOD["headline"] and c1["prompt_version"] == "insight@1"
    assert c2 == c1 and s.calls == 1  # second card served from cache
    assert c1["fact_ids"] == svc.card("identity", M)["fact_ids"]


def test_bad_ai_output_keeps_the_curated_card() -> None:
    bad = {**GOOD, "summary": "You were born in 1984 and are lucky."}
    svc = InsightService(LIB, chain(Stub(reply=bad)))
    c = svc.card("identity", M)
    assert c["badge"] == "curated" and c["degraded"] is True and "1984" not in c["summary"]


def test_rate_limited_provider_falls_through_to_the_next() -> None:
    first, second = Stub(error="rate_limited"), Stub(reply=GOOD)
    svc = InsightService(LIB, chain(first, second))
    assert svc.card("identity", M)["badge"] == "ai" and first.calls == 1 and second.calls == 1
    svc.card("motive", M)
    assert first.calls == 1  # breaker open until Retry-After: not called again


def test_deterministic_modules_never_call_ai_and_no_keys_means_curated() -> None:
    s = Stub(reply=GOOD)
    svc = InsightService(LIB, chain(s))
    for m in ("birthstar", "nameletter", "deity", "colors", "days"):
        assert svc.card(m, M)["badge"] == "curated"
    assert s.calls == 0
    plain = InsightService(LIB, Chain([])).card("identity", M)
    assert plain["badge"] == "curated" and plain["degraded"] is False


def test_library_gap_gives_an_error_card() -> None:
    c = InsightService(Library(allow_drafts=False), Chain([])).card("identity", M)
    assert c["state"] == "error" and c["degraded"] is True
