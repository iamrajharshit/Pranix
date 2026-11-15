# SPDX-License-Identifier: AGPL-3.0-only
from datetime import date, datetime

import pytest

from pranix.ephemeris.master import BirthInput, compute
from pranix.ephemeris.selftest import GOLDEN
from pranix.insight import cards
from pranix.insight.library import Library
from pranix.insight.validators import check_card

LIB = Library(allow_drafts=True)
KNOWN = compute(GOLDEN, date(2026, 11, 14))
UNKNOWN = compute(
    BirthInput(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata", 18.5204, 73.8567, birth_time_known=False),
    date(2026, 11, 14),
)


@pytest.mark.parametrize("module", cards.MODULES)
@pytest.mark.parametrize("master", [KNOWN, UNKNOWN], ids=["known", "unknown"])
def test_every_card_is_valid(module: str, master: dict) -> None:
    c = cards.build(module, master, LIB)
    check_card(c, master["facts"])
    assert c["module_id"] == module and c["state"] in ("ready", "unavailable")


def test_known_cards() -> None:
    assert cards.build("identity", KNOWN, LIB)["headline"] == "Leo rising, Moon in Taurus"
    assert cards.build("deity", KNOWN, LIB)["headline"] == "Your deity: Gauri (Parvati)"
    assert cards.build("season", KNOWN, LIB)["headline"] == "Jupiter period, Venus sub-period"
    name = cards.build("nameletter", KNOWN, LIB)
    assert [e["ref"] for e in name["entries"]] == ["pada:1", "pada:2", "pada:3", "pada:4"]
    assert name["entries"][1]["tags"] == ["yours"] and name["entries"][1]["title"] == "Va (वा)"
    col = cards.build("colors", KNOWN, LIB)
    assert [e["ref"] for e in col["entries"]] == [s["name"] for s in KNOWN["colors"]["swatches"]]


def test_unknown_time_cards_are_certain_only() -> None:
    assert cards.build("deity", UNKNOWN, LIB)["state"] == "unavailable"
    assert cards.build("season", UNKNOWN, LIB)["reason"] == "BIRTH_TIME_REQUIRED"
    assert cards.build("birthstar", UNKNOWN, LIB)["headline"] == "Rohini or Mrigashira"
    name = cards.build("nameletter", UNKNOWN, LIB)
    assert not any("yours" in e["tags"] for e in name["entries"])
    assert any(s["kind"] == "variant" and "Mrigashira" in s["items"][0] for s in name["sections"])
    assert "rising" not in cards.build("identity", UNKNOWN, LIB)["headline"]
