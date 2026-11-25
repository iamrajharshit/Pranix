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
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..ingest import guard
from .settings import Settings

PROMPT_ID = "library-draft@6"
REPAIR_PROMPT_ID = "library-repair@2"
# Stems the owner flagged as auto-generated-sounding (review of batch 1, 25 Nov); a draft using one is redone.
BANNED_STEMS = ("you possess", "you have a natural gift", "invitations to", "in your professional life",
                "you are defined by", "simply observe", "this gentle pause")  # fmt: skip


class DeepDraft(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    core: str = Field(min_length=1, max_length=240)
    gifts: str = Field(min_length=1, max_length=240)
    growth_edges: str = Field(min_length=1, max_length=240)
    at_work: str = Field(min_length=1, max_length=240)
    in_relationships: str = Field(min_length=1, max_length=240)
    practice: str = Field(min_length=1, max_length=240)


def seed(kind: str, key: str) -> dict[str, Any]:
    """What the approved library and tables already say about this key: the AI stays consistent with it.
    Only approved sources: the reviewed library and the owner-approved ruleset (vedic-core@1)."""
    from ..ephemeris.ruleset import load_ruleset
    from ..insight.library import Library

    lib, rs = Library(allow_drafts=True), load_ruleset()
    elements = rs.raw["elements"]
    if kind == "nakshatra_deep":
        n = next(x for x in rs.nakshatras if x.name == key)
        e = lib.get("nakshatras", key)
        return {"star": key, "ruling_planet": n.lord, "deity": n.deity, "symbol": n.symbol,
                "library": {"essence": e["essence"], "strength": e["strength"], "watch": e["watch"]}}  # fmt: skip
    if kind == "sign_deep":
        i = rs.signs.index(key)
        e = lib.get("signs", key)
        out: dict[str, Any] = {
            "sign": key,
            "element": elements["sign_element"][i % 4],
            "ruling_planet": rs.sign_lords[i],
            "exalted_here": [p for p, s in rs.exalted.items() if s == i] or None,
            "debilitated_here": [p for p, s in rs.debilitated.items() if s == i] or None,
            "library": {k: e[k] for k in ("rising", "moon", "sun") if e.get(k)},
        }
        return {k: v for k, v in out.items() if v}
    e = lib.get("planets", key)
    out = {
        "planet": key,
        "element": elements["planet_element"].get(key),
        "rules_signs": [rs.signs[i] for i in rs.own.get(key, ())] or None,
        "exalted_in": rs.signs[rs.exalted[key]] if key in rs.exalted else None,
        "debilitated_in": rs.signs[rs.debilitated[key]] if key in rs.debilitated else None,
        "library": {k: e[k] for k in ("motive", "period", "gift", "edge") if e.get(k)},
    }
    return {k: v for k, v in out.items() if v}


def opener(text: str) -> str:
    """The first three words, lower-case, without punctuation: how a sentence starts."""
    words = [w.strip(".,;:!?\"'()").lower() for w in text.split()]
    return " ".join(w for w in words[:3] if w)


MAX_OPENER_USES = 2  # an opening may appear at most twice per field across a kind (owner review, 25 Nov)

# Small models ignore "don't start like X" but follow "start with Y". Each field has a bank of natural
# openings; every draft is given the least-used one, so openings spread evenly across all entries.
OPENER_BANK: dict[str, tuple[str, ...]] = {
    "core": ("At heart, you", "Your nature is", "Your instinct is", "What drives you is", "You are someone who",
             "Deep down, you", "Your essence is", "You carry a", "By nature you", "You embody",
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
                "You work best when", "Colleagues and peers notice", "In any task, you", "Given a goal, you",
                "In study and work", "Your working style", "Teams value your", "Whatever you take on,",
                "In demanding roles,"),
    "in_relationships": ("With people you love,", "In close bonds,", "Those close to you", "In friendship and love,",
                         "With the people you love,", "In relationships, you", "The people near you",
                         "When you love someone,", "Close to home, you", "Your loved ones", "In love and friendship",
                         "With those dear to you,", "In your closest circle,", "People who know you"),
    "practice": ("Once this week,", "It can help to", "Each evening,", "Before you start something,",
                 "The next time you",
                 "This week,", "When you notice", "A small step is", "Every morning,", "Next time you",
                 "Once a day,", "Set aside a", "Today, try to", "Choose one moment"),
}  # fmt: skip


def words(text: str) -> list[str]:
    return [w for w in (t.strip(".,;:!?\"'()").lower() for t in text.split()) if w]


def openings_of(text: str, field: str) -> set[str]:
    """Every opening this text uses: each bank opening it begins with (any length), and its first
    three words. Comparing only three words missed two-word openings like "Quietly, you" (batch 3)."""
    w = words(text)
    keys = {" ".join(w[:3])}
    for option in OPENER_BANK.get(field, ()):
        ow = words(option)
        if w[: len(ow)] == ow:
            keys.add(" ".join(ow))
    return keys


def usage(entries: dict[str, Any], fields: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """How many entries already use each opening, per field (reviewed or draft)."""
    out: dict[str, dict[str, int]] = {f: {} for f in fields}
    for e in entries.values():
        for f in fields:
            if isinstance(e, dict) and e.get(f):
                for k in openings_of(str(e[f]), f):
                    out[f][k] = out[f].get(k, 0) + 1
    return out


def assign(fields: tuple[str, ...], used: dict[str, dict[str, int]], spread: int) -> dict[str, str]:
    """The least-used opening of each field's bank; `spread` rotates ties so neighbours differ."""
    out = {}
    for f in fields:
        bank = OPENER_BANK[f]
        ranked = sorted(((used[f].get(" ".join(words(o)), 0), (i - spread) % len(bank), o) for i, o in enumerate(bank)))
        out[f] = ranked[0][2]
    return out


_STOP = set("a an the and or of to in on at for with by your you yours this that these those is are be "
            "can may when what who it its as from into than then there their them they our more most "
            "one some each every all any not no so very".split())  # fmt: skip


def shared_phrases(draft: dict[str, str]) -> list[str]:
    """Two-word phrases of content words that appear in more than one field of the same draft
    ("unwavering loyalty" in both at_work and in_relationships, batch 3)."""
    seen: dict[str, str] = {}
    out = []
    for f, text in draft.items():
        w = words(text)
        for a, b in pairwise(w):
            if a in _STOP or b in _STOP or len(a) < 4 or len(b) < 4:
                continue
            pair = f"{a} {b}"
            if pair in seen and seen[pair] != f and pair not in out:
                out.append(pair)
            seen.setdefault(pair, f)
    return out


LABEL_PREFIX = re.compile(r"^[A-Z][A-Za-z ]{0,30}:\s")  # "Try this: ..." duplicates the UI's own heading


def voice_problems(
    draft: dict[str, str], used: dict[str, dict[str, int]], theme: frozenset[str] = frozenset()
) -> list[str]:
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
        else:
            over = sorted(k for k in openings_of(text, f) if used.get(f, {}).get(k, 0) >= MAX_OPENER_USES)
            if over:
                bad.append(f"{f} starts like {MAX_OPENER_USES} other entries: '{over[0]}'")
    bad += [f"same phrase in two fields: '{p}'" for p in shared_phrases(draft)]
    if len(draft) > 1:  # whole-entry checks (a single field is checked on its own during repair)
        bad += [f"same word in too many fields: '{w}'" for w in overused_words(draft, theme)]
        bad += [f"{f}: only one sentence" for f, t in draft.items() if guard.sentences(t) < MIN_SENTENCES]
        bad += [f"{f}: '{w}' twice" for f, t in draft.items() for w in repeated_within(t, theme)[:1]]
    return bad


MIN_SENTENCES = 2  # small models shrink fields to one sentence late in a run (owner's batch 5)
WORD_FIELD_LIMIT = 2  # a distinctive word may appear in at most two fields of one entry


def stem(word: str) -> str:
    """A rough stem so "rhythm" and "rhythmic", "inspire" and "inspiring" count as one word."""
    return word[:6]


def themes_of(kind: str, key: str) -> frozenset[str]:
    """Stems an entry is *about* (the Moon's emotions and feelings): exempt from the word-repeat checks,
    since the entry cannot avoid them (planets batch, 25 Nov: the Moon failed four drafts on them)."""
    return frozenset(stem(w) for w in THEME_WORDS.get((kind, key), ()))


def _watch(w: str) -> str | None:
    """The stem a word counts under, or None when it is too common to count. Short words in
    SHORT_WATCH ("deep", "deeper", "deeply") count too: Gemma leaned on them in five planet cores."""
    for short in SHORT_WATCH:
        if w.startswith(short) and len(w) <= len(short) + 2:
            return short
    if len(w) >= 6 and w not in _STOP and w not in _COMMON:
        return stem(w)
    return None


def overused_words(draft: dict[str, str], theme: frozenset[str] = frozenset()) -> list[str]:
    """Distinctive words (six letters or more, not stop words) found in more than WORD_FIELD_LIMIT fields."""
    where: dict[str, list[str]] = {}
    for f, text in draft.items():
        for w in {k for k in map(_watch, words(text)) if k and k not in theme}:
            where.setdefault(w, []).append(f)
    return sorted(w for w, fs in where.items() if len(fs) > WORD_FIELD_LIMIT)


THEME_WORDS: dict[tuple[str, str], tuple[str, ...]] = {("planet_deep", "Moon"): ("emotional", "feelings", "nurturing")}
_WITHIN_OK = {"about", "yourself"}  # fine to say twice in one field
SHORT_WATCH = ("deep",)  # short words that still count as distinctive
ACROSS_LIMIT = 3  # a distinctive word may appear in one field of at most three entries of a kind
_COMMON = set("nature others people around through feelings energy natural naturally "
              "yourself presence create creates".split())  # fmt: skip


def word_usage(entries: dict[str, Any], fields: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """How many entries of the kind already use each distinctive word, per field. Catches a batch
    whose practices all say "observe" even though each entry on its own reads fine."""
    out: dict[str, dict[str, int]] = {f: {} for f in fields}
    for e in entries.values():
        for f in fields:
            if isinstance(e, dict) and e.get(f):
                for w in _distinct(str(e[f])):
                    out[f][w] = out[f].get(w, 0) + 1
    return out


def _distinct(text: str) -> set[str]:
    return {k for k in map(_watch, words(text)) if k}


def repeated_within(text: str, theme: frozenset[str] = frozenset()) -> list[str]:
    """Words used twice inside one field ("necessary shifts ... necessary evolution"). Stricter than
    the across-field check: any word of four letters or more counts, common ones too, because a
    reader hears "others ... others", "need ... need", "small ... small" (planets review, 25 Nov)."""
    seen: dict[str, int] = {}
    for w in words(text):
        k = stem(w) if len(w) >= 4 and w not in _STOP and w not in _WITHIN_OK else None
        if k and k not in theme:
            seen[k] = seen.get(k, 0) + 1
    return sorted(w for w, n in seen.items() if n > 1)


def bad_fields(
    draft: dict[str, str],
    used: dict[str, dict[str, int]],
    across: dict[str, dict[str, int]] | None = None,
    theme: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Each field that fails the voice check, with why. For a phrase shared by two fields, the later
    field is the one to reword."""
    out: dict[str, str] = {}
    for f, text in draft.items():
        problems = voice_problems({f: text}, used, theme)
        if problems:
            out[f] = problems[0]
    for phrase in shared_phrases(draft):
        holders = [f for f, t in draft.items() if phrase in " ".join(words(t))]
        if len(holders) > 1 and holders[-1] not in out:
            out[holders[-1]] = f"same phrase as another field: '{phrase}'"
    for w in overused_words(draft, theme):
        holders = [f for f, t in draft.items() if any(_watch(x) == w for x in words(t))]
        for f in holders[WORD_FIELD_LIMIT:]:
            out.setdefault(f, f"same word in too many fields: '{w}'")
    for f, text in draft.items():
        if guard.sentences(text) < MIN_SENTENCES:
            out.setdefault(f, "only one sentence: write two")
        twice = repeated_within(text, theme)
        if twice:
            out.setdefault(f, f"same word twice in one field: '{twice[0]}'")
        worn = sorted(w for w in _distinct(text) - theme if (across or {}).get(f, {}).get(w, 0) >= ACROSS_LIMIT)
        if worn:
            out.setdefault(f, f"word already used in this field by {ACROSS_LIMIT} entries: '{worn[0]}'")
    return out


class Repaired(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=240)


def repair_field(chain: Any, field: str, text: str, begin_with: str, reason: str) -> str | None:
    """Ask for just this one field again, beginning with the given words. A small model follows a
    one-sentence rewrite far more reliably than a whole new draft (owner's batch 5, 25 Nov)."""
    from importlib import resources

    system = resources.files("pranix.prompts").joinpath(f"{REPAIR_PROMPT_ID}.md").read_text(encoding="utf-8")
    avoid = list(BANNED_STEMS)
    if "same phrase" in reason or "same word" in reason or "twice" in reason:
        avoid.append(reason.split("'")[1])
    user = json.dumps(
        {"field": field, "text": text, "begin_with": begin_with, "avoid": avoid, "sentences": MIN_SENTENCES},
        ensure_ascii=False,
    )
    got: list[str] = []

    def accept(raw: str) -> bool:
        try:
            new = Repaired.model_validate_json(raw).text
        except ValueError:
            return False
        if words(new)[: len(words(begin_with))] != words(begin_with):
            return False  # it ignored the opening again
        if guard.sentences(new) < MIN_SENTENCES:
            return False
        got.append(new)
        return True

    return got[0] if chain.generate(system, user, module="draft.repair", accept=accept) is not None else None


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
            have = intake.load_all(root)[args.kind]
            used = usage(have, fields)
            across = word_usage(have, fields)
            theme = themes_of(args.kind, key)
            start = assign(fields, used, spread=i)
            ask = {"kind": args.kind, "facts": facts, "start_with": start}
            reason = ""
            started = time.perf_counter()
            for attempt in range(3):  # two retries, each told what was wrong the time before
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
                # reword just the failing fields (up to two rounds) before redrafting the whole star
                for _round in range(2):
                    bad = bad_fields(got, used, across, theme)
                    if not bad:
                        break
                    for f, why in bad.items():
                        opening = assign((f,), used, spread=i + _round + 1)[f]
                        fixed = repair_field(chain, f, got[f], opening, why)
                        if fixed:
                            got[f] = fixed
                voice = voice_problems(got, used, theme)
                if voice:
                    reason = "TEMPLATE_VOICE (" + "; ".join(voice[:2]) + ")"
                    continue
                names = unknown_entities(" ".join(got.values()), json.dumps(facts, ensure_ascii=False))
                if names:
                    reason = "UNKNOWN_ENTITY (" + ", ".join(names) + ")"
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
