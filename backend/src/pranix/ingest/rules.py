# SPDX-License-Identifier: AGPL-3.0-only
"""Rule-table intake: rule review sheet (CSV) -> `rulesets/jyotish-core@1.yaml` (plan 4.7, FR-REV-05).

Only values the owner approved or edited are written. Each table has a parser that accepts the sheet's
text and returns the typed value, so a typo ("5,7,13") fails before it reaches the file.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import guard, sheet, yamlio
from .kinds import HOUSES, PLANETS

RULESET = "jyotish-core@1"
SHEET_COLUMNS = ("table", "key", "value", "decision", "edited", "note")
_ID = re.compile(r"^[a-z][a-z0-9_.]*$")
_CATEGORIES = {"kendra", "trikona", "dusthana", "upachaya", "neutral"}  # no maraka or badhaka (D75)
_NATURES = {"benefic", "malefic", "neutral", "conditional"}


class RuleError(ValueError):
    pass


def _items(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[;,]", text) if t.strip()]


def _aspects(text: str) -> list[int]:
    nums = sorted({int(t) for t in _items(text)})  # ValueError -> caught by caller
    if not nums or any(n < 2 or n > 12 for n in nums):
        raise RuleError("offsets are the nth house counted from the planet, 2 to 12 (7 is the opposite house)")
    return nums


def _categories(text: str) -> list[str]:
    cats = sorted(set(_items(text.lower())))
    bad = [c for c in cats if c not in _CATEGORIES]
    if not cats or bad:
        raise RuleError(f"categories must be from {sorted(_CATEGORIES)}; got {bad or 'nothing'}")
    return cats


def _nature(text: str) -> str:
    t = text.strip().lower()
    if t not in _NATURES:
        raise RuleError(f"nature must be one of {sorted(_NATURES)}")
    return t


def _priority(text: str) -> int:
    n = int(text.strip())
    if not 1 <= n <= 100:
        raise RuleError("priority is 1 to 100")
    return n


def _ids(text: str) -> list[str]:
    ids = sorted(set(_items(text)))
    if not ids or any(not _ID.match(i) for i in ids):
        raise RuleError("signal ids look like dispositor.cycle")
    return ids


@dataclass(frozen=True)
class Table:
    keys: tuple[str, ...] | None  # allowed keys; None = any signal id
    parse: Callable[[str], Any]


TABLES: dict[str, Table] = {
    "graha_drishti": Table(PLANETS, _aspects),  # D72: Rahu and Ketu get 5, 7, 9
    "house_categories": Table(HOUSES, _categories),
    "natural_nature": Table(PLANETS, _nature),
    "signal_priority": Table(None, _priority),
    "suppression": Table(None, _ids),
}


def default_path() -> Path:
    from .. import rulesets

    return Path(rulesets.__file__).parent / f"{RULESET}.yaml"


def _load(path: Path) -> dict[str, Any]:
    return yamlio.load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _parse(table: str, key: str, text: str) -> tuple[Any, guard.Issue | None]:
    spec = TABLES[table]
    where = f"{table}/{key}"
    if spec.keys is not None and key not in spec.keys:
        return None, guard.Issue("UNKNOWN_KEY", where)
    if spec.keys is None and not _ID.match(key):
        return None, guard.Issue("INVALID_KEY", where, "signal ids look like dispositor.cycle")
    try:
        return spec.parse(text), None
    except (RuleError, ValueError) as e:
        return None, guard.Issue("BAD_VALUE", where, str(e))


def check_tables(tables: dict[str, Any]) -> list[guard.Issue]:
    """Schema and cross-table checks for a whole file (used by import and verify)."""
    issues: list[guard.Issue] = []
    for table, rows in tables.items():
        if table not in TABLES:
            issues.append(guard.Issue("UNKNOWN_TABLE", table))
            continue
        for key, val in rows.items():
            text = ",".join(map(str, val)) if isinstance(val, list) else str(val)
            _, issue = _parse(table, key, text)
            if issue:
                issues.append(issue)
    prio = set(tables.get("signal_priority", {}))
    for sig, targets in tables.get("suppression", {}).items():
        if prio and sig not in prio:
            issues.append(guard.Issue("UNRANKED_SIGNAL", f"suppression/{sig}", "add it to signal_priority first"))
        issues += [guard.Issue("UNRANKED_SIGNAL", f"suppression/{sig}", t) for t in targets if prio and t not in prio]
    return issues


@dataclass
class RuleReport:
    errors: list[guard.Issue]
    added: list[str]
    changed: list[tuple[str, Any, Any]]
    skipped: list[str]
    content_hash: str = ""
    written: bool = False
    rows: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def markdown(self) -> str:
        out = ["# Rules import report", "", f"{self.rows} rows. Result: **{'OK' if self.ok else 'FAILED'}**"
               + ("" if not self.ok else (" (written)" if self.written else " (dry run: nothing written)")), "",
               "| Added | Changed | Not approved (left out) |", "|---|---|---|",
               f"| {len(self.added)} | {len(self.changed)} | {len(self.skipped)} |", ""]  # fmt: skip
        if self.errors:
            out += [f"## Errors ({len(self.errors)}), nothing was written", ""] + [f"- {e}" for e in self.errors] + [""]
        if self.changed:
            out += ["## Changed values", ""] + [f"- `{k}`: {a} -> {b}" for k, a, b in self.changed] + [""]
        if self.added:
            out += ["## Added", ""] + [f"- `{k}`" for k in self.added] + [""]
        if self.content_hash:
            out += [f"Ruleset content hash: `{self.content_hash}`", ""]
        return "\n".join(out)


def import_sheet(path: Path, sheet_path: Path, reviewed_on: str | None = None, write: bool = False) -> RuleReport:
    rep = RuleReport([], [], [], [])
    try:
        rows = sheet.read_rows(sheet_path, ("table", "key", "value", "decision"))
    except sheet.SheetError as e:
        rep.errors.append(guard.Issue("BAD_SHEET", sheet_path.name, str(e)))
        return rep
    rep.rows = len(rows)
    doc = _load(path)
    tables: dict[str, dict[str, Any]] = copy.deepcopy(doc.get("tables", {}))
    seen: set[tuple[str, str]] = set()
    for i, r in enumerate(rows, start=2):
        table, key = r["table"], r["key"]
        where = f"row {i} {table}/{key}"
        if table not in TABLES:
            rep.errors.append(guard.Issue("UNKNOWN_TABLE", where))
            continue
        if (table, key) in seen:
            rep.errors.append(guard.Issue("DUPLICATE_ROW", where))
            continue
        seen.add((table, key))
        try:
            decision = sheet.decision_of(r["decision"])
        except sheet.SheetError as e:
            rep.errors.append(guard.Issue("BAD_DECISION", where, str(e)))
            continue
        if decision in ("hold", "reject"):
            rep.skipped.append(f"{table}/{key}")
            continue
        edited = sheet.squash(r.get("edited", ""))
        if decision == "approve" and edited:
            rep.errors.append(guard.Issue("EDIT_WITH_APPROVE", where, "use the decision edit"))
            continue
        if decision == "edit" and not edited:
            rep.errors.append(guard.Issue("EDIT_EMPTY", where))
            continue
        value, issue = _parse(table, key, edited or r["value"])
        if issue:
            rep.errors.append(guard.Issue(issue.rule, where, issue.detail))
            continue
        old = tables.setdefault(table, {}).get(key)
        if old is None:
            rep.added.append(f"{table}/{key}")
        elif old != value:
            rep.changed.append((f"{table}/{key}", old, value))
        tables[table][key] = value
    rep.errors += check_tables(tables)
    rep.errors = list(dict.fromkeys(rep.errors))
    if not rep.ok:
        return rep
    meta = {"id": "jyotish-core", "version": 1, "status": "PARTIAL" if _incomplete(tables) else "COMPLETE",
            "reviewed_by": "owner", "reviewed_at": reviewed_on or doc.get("reviewed_at") or "unreviewed"}  # fmt: skip
    ordered = {t: dict(sorted(tables[t].items(), key=lambda kv: _order(t, kv[0]))) for t in TABLES if tables.get(t)}
    header = [
        f"{RULESET}: owner-approved rule tables for the Chart Inspector (plan 4.7, D72, D73, D75).",
        "Written by `pranix-ctl rules import`. Any change needs a golden-snapshot diff",
        "and owner approval (FR-REV-05).",
        "graha_drishti: nth house counted from the planet (its own house is the 1st); whole-house, no orbs;",
        "read in D1 and inside D9; with no birth time the same counts apply by sign (D81 4).",
    ]
    text = yamlio.dump({**meta, "tables": ordered}, header)
    rep.content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    if write:
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        rep.written = True
    return rep


def _order(table: str, key: str) -> tuple[int, str]:
    keys = TABLES[table].keys
    return (keys.index(key), key) if keys and key in keys else (999, key)


def _incomplete(tables: dict[str, Any]) -> bool:
    """PARTIAL until every fixed-key table is present and full (a missing table counts, plan 4.7)."""
    return any(TABLES[t].keys is not None and set(tables.get(t, {})) != set(TABLES[t].keys or ()) for t in TABLES)


def export_sheet(path: Path, out: Path) -> int:
    tables = _load(path).get("tables", {})
    rows = [
        {
            "table": t,
            "key": k,
            "value": ",".join(map(str, v)) if isinstance(v, list) else str(v),
            "decision": "",
            "edited": "",
            "note": "",
        }
        for t, entries in tables.items()
        for k, v in entries.items()
    ]
    sheet.write_rows(out, SHEET_COLUMNS, rows)
    return len(rows)


def verify(path: Path) -> RuleReport:
    rep = RuleReport([], [], [], [])
    if path.exists():
        rep.errors = check_tables(_load(path).get("tables", {}))
    return rep
