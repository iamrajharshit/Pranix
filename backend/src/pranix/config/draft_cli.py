# SPDX-License-Identifier: AGPL-3.0-only
"""`pranix-ctl library draft` (D80): the configured AI (Gemma on the laptop) drafts the deeper
per-star, per-sign and per-planet entries that are still missing, as `status: draft`.

Nothing it writes is served in production until the owner approves it through the review sheet
(`library export-sheet` → decisions → `library import`). Existing entries are never replaced.
Every draft passes the same checks as an import, plus the entity check. No personal data is
involved at all: these are general texts about a star, sign or planet.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .settings import Settings

PROMPT_ID = "library-draft@3"
# Stems the owner flagged as auto-generated-sounding (review of batch 1, 25 Nov); a draft using one is redone.
BANNED_STEMS = ("you possess", "you have a natural gift", "invitations to", "in your professional life")


class DeepDraft(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    core: str = Field(min_length=1, max_length=240)
    gifts: str = Field(min_length=1, max_length=240)
    growth_edges: str = Field(min_length=1, max_length=240)
    at_work: str = Field(min_length=1, max_length=240)
    in_relationships: str = Field(min_length=1, max_length=240)
    practice: str = Field(min_length=1, max_length=240)


def seed(kind: str, key: str) -> dict[str, Any]:
    """What the approved library and tables already say about this key: the AI stays consistent with it."""
    from ..ephemeris.ruleset import load_ruleset
    from ..insight.library import Library

    lib, rs = Library(allow_drafts=True), load_ruleset()
    if kind == "nakshatra_deep":
        n = next(x for x in rs.nakshatras if x.name == key)
        e = lib.get("nakshatras", key)
        return {"star": key, "ruling_planet": n.lord, "deity": n.deity, "symbol": n.symbol,
                "library": {"essence": e["essence"], "strength": e["strength"], "watch": e["watch"]}}  # fmt: skip
    if kind == "sign_deep":
        e = lib.get("signs", key)
        lord = rs.sign_lords[rs.signs.index(key)]
        return {"sign": key, "ruling_planet": lord,
                "library": {k: e[k] for k in ("rising", "moon", "sun") if k in e}}  # fmt: skip
    e = lib.get("planets", key)
    return {"planet": key, "library": {k: e[k] for k in ("motive", "period", "gift", "edge") if k in e}}


def opener(text: str) -> str:
    """The first three words, lower-case, without punctuation: how a sentence starts."""
    words = [w.strip(".,;:!?\"'()").lower() for w in text.split()]
    return " ".join(w for w in words[:3] if w)


MAX_OPENER_USES = 2  # an opening may appear at most twice per field across a kind (owner review, 25 Nov)

# Small models ignore "don't start like X" but follow "start with Y". Each field has a bank of natural
# openings; every draft is given the least-used one, so openings spread evenly across all entries.
OPENER_BANK: dict[str, tuple[str, ...]] = {
    "core": ("At heart, you", "Your nature is", "There is something", "This star gives you", "You are someone who",
             "Deep down, you", "Your essence is", "Something in you", "By nature you", "Quietly, you",
             "Above all, you", "What defines you", "Your spirit is", "Inside you lives"),
    "gifts": ("What comes easily is", "Your gift is", "People rely on your", "A natural strength is", "You bring a",
              "One of your strengths", "Others notice your", "Your quiet power", "You shine through",
              "Where you excel is", "A gift you carry", "Your best quality", "It comes naturally", "You are gifted"),
    "growth_edges": ("Your edge is", "At times your", "Sometimes you may", "Growth comes when you",
                     "Watch for the moment", "Your challenge is", "It helps to notice", "When pushed, your",
                     "The lesson here", "Your growth lies", "Under pressure, you", "Now and then",
                     "Left unchecked, your", "Be gentle when"),
    "at_work": ("At work and in", "In work and study,", "Where you work and", "Your best work comes",
                "In your work and projects",
                "You work best when", "Colleagues and teachers notice", "In any task, you", "Given a goal, you",
                "In study and work", "Your working style", "Teams value your", "When you learn,", "At your desk,"),
    "in_relationships": ("With people you love,", "In close bonds,", "Those close to you", "In friendship and love,",
                         "With family and friends,", "In relationships, you", "The people near you",
                         "When you love someone,", "Close to home, you", "Your loved ones", "In love and friendship",
                         "Among friends, you", "With a partner, you", "People who know you"),
    "practice": ("Once this week,", "It can help to", "Each evening,", "Before you start something,",
                 "For a few minutes",
                 "This week,", "When you notice", "A small step is", "Every morning,", "Next time you",
                 "Once a day,", "Set aside a", "Today, try to", "Choose one moment"),
}  # fmt: skip


def usage(entries: dict[str, Any], fields: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """How many entries already start each field with each opening (reviewed or draft)."""
    out: dict[str, dict[str, int]] = {f: {} for f in fields}
    for e in entries.values():
        for f in fields:
            if isinstance(e, dict) and e.get(f):
                o = opener(str(e[f]))
                out[f][o] = out[f].get(o, 0) + 1
    return out


def assign(fields: tuple[str, ...], used: dict[str, dict[str, int]], spread: int) -> dict[str, str]:
    """The least-used opening of each field's bank; `spread` rotates ties so neighbours differ."""
    out = {}
    for f in fields:
        bank = OPENER_BANK[f]
        order = sorted(range(len(bank)), key=lambda i: (used[f].get(opener(bank[i]), 0), (i - spread) % len(bank)))
        out[f] = bank[order[0]]
    return out


LABEL_PREFIX = re.compile(r"^[A-Z][A-Za-z ]{0,30}:\s")  # "Try this: ..." duplicates the UI's own heading


def voice_problems(draft: dict[str, str], used: dict[str, dict[str, int]]) -> list[str]:
    """Flagged stems, a label prefix, or an opening already used MAX_OPENER_USES times in that field."""
    bad = []
    for f, text in draft.items():
        low = text.lower()
        if LABEL_PREFIX.match(text):
            bad.append(f"{f} starts with a label: '{text.split(':', 1)[0]}:'")
            continue
        stem = next((b for b in BANNED_STEMS if b in low), None)
        if stem:
            bad.append(f"{f}: '{stem}'")
        elif used.get(f, {}).get(opener(text), 0) >= MAX_OPENER_USES:
            bad.append(f"{f} starts like {MAX_OPENER_USES} other entries: '{opener(text)}'")
    return bad


def run(args: argparse.Namespace) -> int:
    import logging

    import structlog

    from ..ingest import library as intake
    from ..ingest.kinds import KINDS
    from ..insight.entities import unknown_entities
    from ..llmgw.build import insights_chain

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    from importlib import resources

    system = resources.files("pranix.prompts").joinpath(f"{PROMPT_ID}.md").read_text(encoding="utf-8")
    root: Path = args.root or intake.default_root()
    chain = insights_chain(Settings())
    if not chain.links:
        print("no AI provider configured (set PRANIX_LOCAL_LLM_URL for Gemma); nothing drafted")
        return 1
    todo = intake.missing_keys(root, args.kind)
    if args.key:
        todo = [k for k in todo if k in args.key]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"{args.kind}: {len(todo)} to draft with {chain.links[0].provider.name} (Ctrl+C stops; drafts so far are kept)"
    )
    made = failed = 0
    try:
        for i, key in enumerate(todo, start=1):
            facts = seed(args.kind, key)
            fields = KINDS[args.kind].fields
            used = usage(intake.load_all(root)[args.kind], fields)
            start = assign(fields, used, spread=i)
            ask = {"kind": args.kind, "facts": facts, "start_with": start}
            reason = ""
            started = time.perf_counter()
            for attempt in range(2):  # one retry, told what was wrong the first time
                if attempt and reason:
                    ask["fix_this"] = (
                        f"Your previous draft was rejected: {reason}. Write it again, and begin each field "
                        "with exactly the words given under start_with."
                    )
                user = json.dumps(ask, ensure_ascii=False)
                got: dict[str, str] = {}

                def accept(text: str, got: dict[str, str] = got) -> bool:
                    try:
                        d = DeepDraft.model_validate_json(text)
                    except ValueError:
                        return False
                    got.update(d.model_dump())
                    return True

                res = chain.generate(system, user, module=f"draft.{args.kind}", accept=accept)
                if res is None:
                    reason = "no valid answer"
                    continue
                # check against the facts only: the retry note quotes rejected names, which must not count as given
                names = unknown_entities(" ".join(got.values()), json.dumps(facts, ensure_ascii=False))
                if names:
                    reason = "UNKNOWN_ENTITY (" + ", ".join(names) + ")"
                    continue
                voice = voice_problems(got, used)
                if voice:
                    reason = "TEMPLATE_VOICE (" + "; ".join(voice[:2]) + ")"
                    continue
                issues = intake.add_draft(root, args.kind, key, got)
                if not issues:
                    reason = ""
                    break
                reason = "; ".join(str(x) for x in issues[:2])
            secs = time.perf_counter() - started
            if reason:
                failed += 1
                print(f"  [{i:>2}/{len(todo)}] {key:<16} {secs:6.1f} s  not drafted: {reason}", flush=True)
            else:
                made += 1
                print(f"  [{i:>2}/{len(todo)}] {key:<16} {secs:6.1f} s  drafted", flush=True)
    except KeyboardInterrupt:
        print("  stopped by you")
    print(f"drafted {made}, not drafted {failed}.")
    print(f"Next: pranix-ctl library export-sheet --kind {args.kind} --out review.csv")
    return 0 if failed == 0 else 1
