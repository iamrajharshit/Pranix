# SPDX-License-Identifier: AGPL-3.0-only
"""Intake guardrails for library text. They sit on top of the runtime ones (insight.validators):
NO_NUMERALS, fear, medical and template-token checks are reused, then the stricter authoring rules
from the plan are added: D75 labels, no predictions, no placeholders, one or two sentences."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..insight.validators import GuardrailError, check_text

BANNED_LABELS = re.compile(r"\b(maraka|badhaka|guru[ -]?chandal|mrita)\b", re.I)  # D75
PLACEHOLDER = re.compile(r"\b(todo|tbd|xxx|fixme|lorem)\b|\[[^\]]*\]|<[^>]*>|\.\.\.|…", re.I)
PREDICTION = re.compile(
    r"\b(guarantee\w*|definitely|certainly|inevitabl\w*|destined|fated|"
    r"you will (?:meet|marry|get|become|earn|win|find|receive|gain))\b",
    re.I,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Issue:
    rule: str
    where: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.rule} at {self.where}" + (f": {self.detail}" if self.detail else "")


def sentences(text: str) -> int:
    return len([s for s in _SENTENCE_END.split(text.strip()) if s])


def check(where: str, text: str, *, max_len: int, max_sentences: int) -> list[Issue]:
    """Every rule that fails, not just the first, so the owner sees all problems at once."""
    issues: list[Issue] = []
    if not text:
        return [Issue("EMPTY", where)]
    if text != " ".join(text.split()):
        issues.append(Issue("WHITESPACE", where, "use single spaces and one line"))
    try:
        check_text(where, text)
    except GuardrailError as e:
        issues.append(Issue(e.rule, where))
    if "{{" in text or "}}" in text:
        issues.append(Issue("TEMPLATE_TOKEN", where, "library text takes no tokens; the name is added in the browser"))
    for rule, rx in (("BANNED_LABEL", BANNED_LABELS), ("PLACEHOLDER", PLACEHOLDER), ("PREDICTION", PREDICTION)):
        m = rx.search(text)
        if m:
            issues.append(Issue(rule, where, m.group(0)))
    if len(text) > max_len:
        issues.append(Issue("TOO_LONG", where, f"{len(text)} > {max_len} characters"))
    if sentences(text) > max_sentences:
        issues.append(Issue("TOO_MANY_SENTENCES", where, f"{sentences(text)} > {max_sentences}"))
    if text[-1] not in ".!?":
        issues.append(Issue("END_PUNCTUATION", where))
    return issues
