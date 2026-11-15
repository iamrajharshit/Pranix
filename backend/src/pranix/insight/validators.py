# SPDX-License-Identifier: AGPL-3.0-only
"""Guardrails on every text field of every card, curated or AI-phrased (Requirements §7.5).

NO_NUMERALS: digits and written-out percentages fail; chart names D1 and D9 are allowed.
Fear and medical-claim lexicons, the {{name}} placement rule, no other template tokens,
fact_ids must be a subset of the facts supplied, and length limits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

LIMITS = {"headline": 60, "summary": 280, "detail": 1000, "item": 160, "entries.title": 40, "entries.text": 400}
_ALLOWED = re.compile(r"\bD[19]\b")
_DIGIT = re.compile(r"\d")
_PERCENT = re.compile(r"\b(per ?cent|percentage)\b", re.I)
FEAR = re.compile(
    r"\b(doom\w*|curse\w*|cursed|death|die|dying|disaster\w*|catastroph\w*|danger\w*|"
    r"bad luck|unlucky|lucky|misfortune|punish\w*|evil|malefic|afflict\w*|dosha remed\w*|must wear|"
    r"you will (?:suffer|fail|lose))\b",
    re.I,
)
MEDICAL = re.compile(
    r"\b(diagnos\w*|cure\w*|treat(?:ment|s|ed)?|disease\w*|illness\w*|disorder\w*|medicin\w*|"
    r"medication\w*|dosage|prescri\w*|symptom\w*|therapy)\b",
    re.I,
)
_NAME = "{{name}}"
_TOKEN = re.compile(r"\{\{?[^}]*\}?\}")


class GuardrailError(ValueError):
    def __init__(self, rule: str, field: str) -> None:
        super().__init__(f"{rule}:{field}")
        self.rule, self.field = rule, field


def _texts(card: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for f in ("headline", "summary", "detail"):
        yield f, card.get(f) or ""
    for s in card.get("sections") or []:
        for it in s["items"]:
            yield f"sections.{s['kind']}", it
    for e in card.get("entries") or []:
        yield "entries.title", e["title"]
        yield "entries.text", e["text"]


def check_text(field: str, text: str) -> None:
    if _DIGIT.search(_ALLOWED.sub("", text)) or _PERCENT.search(text):
        raise GuardrailError("NO_NUMERALS", field)
    if FEAR.search(text):
        raise GuardrailError("FEAR_LEXICON", field)
    if MEDICAL.search(text):
        raise GuardrailError("MEDICAL_LEXICON", field)
    if _TOKEN.search(text.replace(_NAME, "")):
        raise GuardrailError("TEMPLATE_TOKEN", field)


def check_card(card: dict[str, Any], facts: Iterable[str]) -> None:
    names = 0
    for field, text in _texts(card):
        check_text(field, text)
        limit = LIMITS.get(field) or LIMITS.get(field.split(".")[0]) or LIMITS["item"]
        if len(text) > limit:
            raise GuardrailError("TOO_LONG", field)
        n = text.count(_NAME)
        names += n
        if n and not (text.startswith(_NAME + ", ") or re.search(r"[.!?] \{\{name\}\}, ", text)):
            raise GuardrailError("NAME_PLACEMENT", field)
    if names > 1:
        raise GuardrailError("NAME_TWICE", "card")
    if not set(card.get("fact_ids") or []) <= set(facts):
        raise GuardrailError("UNKNOWN_FACT", "fact_ids")
    if len(card.get("sections") or []) > 4 or any(len(s["items"]) > 3 for s in card.get("sections") or []):
        raise GuardrailError("TOO_MANY_ITEMS", "sections")
