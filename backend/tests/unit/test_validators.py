# SPDX-License-Identifier: AGPL-3.0-only
import pytest

from pranix.insight.validators import GuardrailError, check_card, check_text


def card(**kw: object) -> dict:
    c = {"headline": "Leo rising", "summary": "Warm and visible.", "detail": "", "sections": [], "fact_ids": []}
    c.update(kw)
    return c


@pytest.mark.parametrize("text", ["You were born in 1984.", "Fire at 39", "About forty per cent", "a percentage of"])
def test_no_numerals(text: str) -> None:
    with pytest.raises(GuardrailError) as e:
        check_text("summary", text)
    assert e.value.rule == "NO_NUMERALS"


def test_chart_names_are_allowed() -> None:
    check_text("summary", "Your D1 and D9 charts agree.")


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("A lucky day for you.", "FEAR_LEXICON"),
        ("This brings doom.", "FEAR_LEXICON"),
        ("You must wear red.", "FEAR_LEXICON"),
        ("Saffron can cure worry.", "MEDICAL_LEXICON"),
        ("A diagnosis of Pitta.", "MEDICAL_LEXICON"),
        ("Hello {sign}.", "TEMPLATE_TOKEN"),
    ],
)
def test_lexicons_and_tokens(text: str, rule: str) -> None:
    with pytest.raises(GuardrailError) as e:
        check_text("detail", text)
    assert e.value.rule == rule


def test_name_placement() -> None:
    check_card(card(summary="{{name}}, you meet the world warmly."), [])
    check_card(card(summary="You are warm. {{name}}, you shine."), [])
    for bad, rule in [("You are warm, {{name}}.", "NAME_PLACEMENT")]:
        with pytest.raises(GuardrailError) as e:
            check_card(card(summary=bad), [])
        assert e.value.rule == rule
    with pytest.raises(GuardrailError) as e:
        check_card(card(summary="{{name}}, hi.", detail="{{name}}, again."), [])
    assert e.value.rule == "NAME_TWICE"


def test_fact_ids_and_limits() -> None:
    with pytest.raises(GuardrailError):
        check_card(card(fact_ids=["moon.sign"]), ["sun.sign"])
    with pytest.raises(GuardrailError):
        check_card(card(headline="x" * 61), [])
    with pytest.raises(GuardrailError):
        check_card(card(sections=[{"kind": "strengths", "items": ["a", "b", "c", "d"]}]), [])
