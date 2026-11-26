# SPDX-License-Identifier: AGPL-3.0-only
"""I5 wiring: approved Inspector library lines on every panel (D78), from facts the engine computed."""

import json
from pathlib import Path

import pytest

from pranix.ephemeris.ruleset import load_ruleset
from pranix.insight import inspect_text
from pranix.insight.inspect_text import RANK, _bridge, with_text
from pranix.insight.library import REVIEWED, Library
from pranix.insight.validators import check_text
from pranix.jyotish import build_set
from pranix.jyotish.bundle import InspectionBundle

FIX = Path(__file__).parents[3] / "web" / "src" / "__fixtures__"
KNOWN = json.loads((FIX / "sample_1984.json").read_text())
UNKNOWN = json.loads((FIX / "sample_1984_unknown_time.json").read_text())
RS = load_ruleset()


def dressed(chart: str, master: dict = KNOWN, allow: bool = False):  # type: ignore[no-untyped-def]
    return with_text(build_set(master, chart, RS), allow_drafts=allow)  # type: ignore[arg-type]


def ids(b: InspectionBundle) -> list[tuple[str, str]]:
    return [(x.group, x.id) for x in b.lines]


def test_sample_panels_get_the_lines_their_facts_call_for() -> None:
    d1 = dressed("d1")
    assert ids(d1.bundles["planet:Jupiter"]) == [
        ("summary", "planet_in_house"),
        ("placement", "dignity.own"),
        ("with", "conjunction"),
        ("chain", "dispositor.final"),  # Jupiter in its own sign ends its own chain
        ("other", "bridge.softer_in_d9"),  # own in D1, enemy in D9
    ]
    assert ("other", "bridge.debilitated_in_d9") in ids(d1.bundles["planet:Mars"])  # exalted, then debilitated
    assert ("chain", "dispositor.exchange") in ids(d1.bundles["planet:Venus"])  # Venus and Saturn
    seven = d1.bundles["house:7"]
    assert ids(seven) == [
        ("lord", "lord_in_house"),
        ("lord", "bridge.lord_in_other_chart"),
        ("occupants", "house.empty"),
        ("lookedby", "aspect.none"),  # nothing looks at house seven
    ]
    assert seven.about is not None and seven.about.arena.startswith("The seventh house is partnership")
    assert seven.lines[0].text.startswith("With the lord of the seventh house in the third")  # Saturn in the third
    d9 = dressed("d9")
    assert ("rules", "lord.rising") in ids(d9.bundles["planet:Venus"])  # D9 Libra rising, ruled by Venus
    assert ("chain", "dispositor.cycle") in ids(d9.bundles["planet:Venus"])


@pytest.mark.parametrize("chart", ["d1", "d9"])
def test_every_line_is_approved_library_text_through_the_guardrails(chart: str) -> None:
    s = dressed(chart)
    for key, b in s.bundles.items():
        assert len({x.id for x in b.lines}) == len(b.lines), key  # no line twice on one panel
        for x in b.lines:
            check_text(f"{key}.{x.id}", x.text)
        if b.target.kind == "house":
            assert b.about is not None and b.lines, key  # every house has its about text and lord line
        else:
            assert b.lines[0].id == "planet_in_house" and b.about is None, key


def test_sign_level_has_no_house_lines_and_never_guesses() -> None:
    s = dressed("d1", UNKNOWN)
    for b in s.bundles.values():
        found = {x.id for x in b.lines}
        assert not found & {"planet_in_house", "conjunction", "lord.rising"} and not any(
            i.startswith("bridge.") for i in found
        )


def test_unapproved_entries_are_never_served(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = json.loads(json.dumps(inspect_text._inspect_lib("en")))
    lib["houses"]["house_7"]["status"] = "draft"
    lib["signals"]["house.empty"]["status"] = "draft"
    monkeypatch.setattr(inspect_text, "_inspect_lib", lambda locale="en": lib)
    seven = dressed("d1").bundles["house:7"]
    assert seven.about is None and "house.empty" not in {x.id for x in seven.lines}
    local = dressed("d1", allow=True).bundles["house:7"]  # PRANIX_LIBRARY_ALLOW_DRAFTS, local only
    assert local.about is not None and "house.empty" in {x.id for x in local.lines}


def test_inspector_entries_do_not_touch_the_card_library_version() -> None:
    """The card library's version is in every card's AI cache key; Inspector text must not change it."""
    assert not set(REVIEWED) & set(inspect_text.INSPECT_KINDS)
    v = Library(allow_drafts=False).version
    dressed("d1")
    assert Library(allow_drafts=False).version == v


@pytest.mark.parametrize(
    ("d1", "d9", "want"),
    [
        ("own", "enemy", "bridge.softer_in_d9"),
        ("enemy", "friend", "bridge.stronger_in_d9"),
        ("neutral", "neutral", "bridge.same_dignity"),
        ("debilitated", "friend", "bridge.debilitated_supported"),
        ("debilitated", "exalted", "bridge.exalted_in_d9"),
        ("friend", "own", "bridge.own_in_d9"),
        ("exalted", "debilitated", "bridge.debilitated_in_d9"),
    ],
)
def test_bridge_choice_reads_the_same_from_either_chart(d1: str, d9: str, want: str) -> None:
    s1, s9 = build_set(KNOWN, "d1", RS), build_set(KNOWN, "d9", RS)
    b1, b9 = s1.bundles["planet:Moon"], s9.bundles["planet:Moon"]
    assert b1.placement and b1.other_chart and b9.placement and b9.other_chart
    no_varg = {"vargottama": False}
    from_d1 = b1.model_copy(
        update={
            "placement": b1.placement.model_copy(update={"dignity": d1, **no_varg}),
            "other_chart": b1.other_chart.model_copy(update={"dignity": d9, "change": "changed"}),
        }
    )
    from_d9 = b9.model_copy(
        update={
            "placement": b9.placement.model_copy(update={"dignity": d9, **no_varg}),
            "other_chart": b9.other_chart.model_copy(update={"dignity": d1, "change": "changed"}),
        }
    )
    assert _bridge(from_d1) == _bridge(from_d9) == want
    assert set(RANK) == {"exalted", "own", "friend", "neutral", "enemy", "debilitated"}
