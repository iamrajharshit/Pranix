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
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .settings import Settings

PROMPT_ID = "library-draft@1"


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


def run(args: argparse.Namespace) -> int:
    import logging

    import structlog

    from ..ingest import library as intake
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
            user = json.dumps({"kind": args.kind, "facts": facts}, ensure_ascii=False)
            reason = ""
            started = time.perf_counter()
            for _attempt in range(2):  # one retry: a model's second try often passes
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
                names = unknown_entities(" ".join(got.values()), user)
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
