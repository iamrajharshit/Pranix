# SPDX-License-Identifier: AGPL-3.0-only
"""D80: every card gets a structured AI reading; the engine still chooses what each card shows."""

import dataclasses
import json
import re
from datetime import date
from typing import Any

import pytest

from pranix.ephemeris.master import compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight import cards
from pranix.insight.entities import unknown_entities
from pranix.insight.facts import facts_for
from pranix.insight.library import Library
from pranix.insight.pipeline import InsightService
from pranix.insight.reading import CardReading, draft_of, merge
from pranix.llmgw.chain import Chain, Link
from pranix.llmgw.providers import Fake, Stub
from pranix.util.tokenbucket import TokenBucket

KNOWN = compute(GOLDEN, date(2026, 11, 14))
UNKNOWN = compute(dataclasses.replace(GOLDEN, birth_time_known=False), date(2026, 11, 14))
LIB = Library(allow_drafts=True)


def svc(provider: Any) -> InsightService:
    return InsightService(LIB, Chain([Link(provider, TokenBucket(10_000))]))


def reading(**over: Any) -> dict[str, Any]:
    base = {
        "headline": "Born under Rohini",
        "in_short": "Rohini gives you a steady, growing kind of warmth.",
        "what_it_means": "You build slowly and well. " * 12,
        "strengths": ["Patience", "Warmth", "Care for beauty"],
        "growth_edges": ["Letting go when something is complete"],
        "in_daily_life": ["Tend one small growing thing this week"],
        "reflect": "What in your life is quietly growing right now?",
    }
    return {**base, **over}


@pytest.mark.parametrize("master", [KNOWN, UNKNOWN], ids=["time known", "time unknown"])
def test_every_ready_card_gets_a_structured_ai_reading(master: Any) -> None:
    s = svc(Fake("ok"))
    for module in cards.MODULES:
        c = s.card(module, master)
        if c["state"] != "ready":
            continue
        assert c["badge"] == "ai" and c["prompt_version"] == "insight@3", module


def test_rule_selected_cards_keep_engine_content() -> None:
    s = svc(Stub(reply=reading(headline="Sounds of Rohini")))
    curated = cards.build("nameletter", KNOWN, LIB)
    c = s.card("nameletter", KNOWN)
    assert c["badge"] == "ai" and c["entries"] == curated["entries"]  # syllables never AI-written
    assert [s["kind"] for s in c["sections"]][:3] == ["strengths", "growth_edges", "in_daily_life"]
    assert {"kind": "tradition", "items": curated["sections"][0]["items"]} in c["sections"]  # factual kept
    assert c["reflect"] == "What in your life is quietly growing right now?"
    colours = svc(Stub(reply=reading(headline="Your colours"))).card("colors", KNOWN)
    assert colours["entries"] == cards.build("colors", KNOWN, LIB)["entries"]
    assert colours["fact_ids"] == cards.build("colors", KNOWN, LIB)["fact_ids"]


def test_an_unknown_planet_sign_or_star_is_rejected() -> None:
    bad = reading(what_it_means="Your Venus in Pisces softens everything. " * 6)
    c = svc(Stub(reply=bad)).card("birthstar", KNOWN)
    assert c["badge"] == "curated" and c["degraded"] is True
    assert unknown_entities("Rohini and the Moon", "Rohini Moon") == []
    assert unknown_entities("Your Mars in Leo", "Leo") == ["Mars"]
    assert unknown_entities("Hasta or Chitra", "Hasta") == ["Chitra"]


def test_unknown_time_star_options_are_passed_never_chosen() -> None:
    f = facts_for("birthstar", UNKNOWN)
    assert "star" not in f and len(f["star_options"]) == 2
    a, b = f["star_options"]
    # a reading that names only one of the two stars still passes the entity check (both were given);
    # the prompt asks for both, and the curated draft says both
    assert draft_of(cards.build("birthstar", UNKNOWN, LIB))["headline"] == f"{a} or {b}"


@pytest.mark.parametrize("master", [KNOWN, UNKNOWN], ids=["time known", "time unknown"])
def test_facts_are_de_identified_and_digit_free(master: Any) -> None:
    for module in cards.MODULES:
        c = cards.build(module, master, LIB)
        if c["state"] != "ready":
            continue
        text = json.dumps(facts_for(module, master))
        assert not re.search(r"\d", text), (module, text)
        for banned in ("Pune", "1984", "lat", "lon", "name", "pronoun"):
            assert banned not in text, (module, banned)


def test_reading_model_shapes_and_limits() -> None:
    r = CardReading.model_validate(reading(strengths=["a", "b", "c", "d"], extra_key="ignored"))
    assert r.strengths == ["a", "b", "c"]
    with pytest.raises(ValueError):
        CardReading.model_validate(reading(headline="x" * 61))
    with pytest.raises(ValueError):
        CardReading.model_validate(reading(in_short=""))
    with pytest.raises(ValueError):
        CardReading.model_validate(reading(in_daily_life=["x" * 161]))
    merged = merge(cards.build("birthstar", KNOWN, LIB), CardReading.model_validate(reading(reflect="")))
    assert merged["reflect"] is None and len(merged["sections"]) <= 6


def test_guardrails_cover_the_new_fields() -> None:
    assert svc(Stub(reply=reading(reflect="Will you be lucky in 2027?"))).card("identity", KNOWN)["badge"] == "curated"
    assert svc(Stub(reply=reading(growth_edges=["A cursed habit"]))).card("identity", KNOWN)["badge"] == "curated"


def test_fake_failure_modes_fall_back_to_curated() -> None:
    for mode in ("numerals", "fear", "unknown_fact", "invalid_json", "down"):
        c = svc(Fake(mode)).card("deity", KNOWN)
        assert c["badge"] == "curated" and c["degraded"] is True, mode


def test_rejections_report_the_rule_never_the_text() -> None:
    seen: list[tuple[str, str, str]] = []
    s = svc(Stub(reply=reading(what_it_means="Your Venus in Pisces softens everything. " * 6)))
    s.on_reject = lambda m, rule, where: seen.append((m, rule, where))
    s.card("birthstar", KNOWN)
    assert seen == [("birthstar", "UNKNOWN_ENTITY", "Venus, Pisces")]
    seen.clear()
    s2 = svc(Stub(reply=reading(headline="x" * 61)))
    s2.on_reject = lambda m, rule, where: seen.append((m, rule, where))
    s2.card("identity", KNOWN)
    assert seen == [("identity", "SCHEMA", "headline")]
