# SPDX-License-Identifier: AGPL-3.0-only
"""The structured reading every card gets (D80): one Pydantic model for all twelve modules.

The AI fills `CardReading` from the engine's facts and the curated draft; Pydantic checks the
shape and lengths, then `merge()` lays it onto the curated card. Engine-chosen content (which star,
deity, colours, days, syllables) and the factual sections stay exactly as the card builder made them.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]

# Sections that carry engine facts or reviewed custom; the AI never rewrites them.
FACTUAL_SECTIONS = ("about_star", "tradition", "variant", "other_forms")
AI_SECTIONS = ("strengths", "growth_edges", "in_daily_life")


class CardReading(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    headline: str = Field(min_length=1, max_length=60)
    in_short: str = Field(min_length=1, max_length=280)
    what_it_means: str = Field(min_length=1, max_length=1000)
    strengths: list[Item] = Field(default_factory=list, max_length=3)
    growth_edges: list[Item] = Field(default_factory=list, max_length=3)
    in_daily_life: list[Item] = Field(default_factory=list, max_length=3)
    reflect: str = Field(default="", max_length=200)

    @field_validator("strengths", "growth_edges", "in_daily_life", mode="before")
    @classmethod
    def _cap(cls, v: Any) -> Any:
        # models sometimes give four items; keep the first three rather than rejecting a good answer
        return list(v)[:3] if isinstance(v, list) else v


def _items(card: dict[str, Any], *kinds: str) -> list[str]:
    out: list[str] = []
    for s in card.get("sections") or []:
        if s["kind"] in kinds:
            out += s["items"]
    return out[:3]


def draft_of(curated: dict[str, Any]) -> dict[str, Any]:
    """The curated card in the reading shape: the AI's starting point (and the fake provider's echo)."""
    return {
        "headline": curated["headline"],
        "in_short": curated["summary"],
        "what_it_means": curated["detail"] or curated["summary"],
        "strengths": _items(curated, "strengths", "qualities_to_grow"),
        "growth_edges": _items(curated, "watch_points"),
        "in_daily_life": _items(curated, "try_this", "practice", "how_to_use", "ideas_for_the_day", "this_season"),
        "reflect": "",
    }


def merge(curated: dict[str, Any], r: CardReading) -> dict[str, Any]:
    """Card fields the AI may set. Everything else (entries, fact_ids, state, art) stays curated."""
    sections = [{"kind": k, "items": list(getattr(r, k))} for k in AI_SECTIONS if getattr(r, k)]
    sections += [s for s in curated.get("sections") or [] if s["kind"] in FACTUAL_SECTIONS]
    return {
        "headline": r.headline,
        "summary": r.in_short,
        "detail": r.what_it_means,
        "sections": sections[:6],
        "reflect": r.reflect or None,
    }
