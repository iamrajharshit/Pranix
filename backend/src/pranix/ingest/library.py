# SPDX-License-Identifier: AGPL-3.0-only
"""Library intake: review sheet (CSV) -> reviewed YAML under `library/en/reviewed/`.

Loop: Claude drafts entries as `status: draft` YAML -> `export_sheet` lists them -> the owner fills
`decision` (approve / edit / reject / hold) -> `import_sheet` validates *everything* first and writes
only if there are no errors (all or nothing) -> `manifest.json` records a content hash.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import guard, sheet, yamlio
from .kinds import KINDS, Kind

MANIFEST = "manifest.json"
SHEET_COLUMNS = ("key", "field", "draft", "decision", "edited", "note")
Data = dict[str, dict[str, Any]]  # kind -> nested mapping


def default_root() -> Path:
    from .. import library as lib_pkg

    return Path(lib_pkg.__file__).parent / "en" / "reviewed"


# ---------- loading and walking ----------


def load_all(root: Path) -> Data:
    data: Data = {}
    for name in KINDS:
        p = root / f"{name}.yaml"
        data[name] = yamlio.load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return data


def walk(kind: Kind, node: dict[str, Any], prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Yield (path, entry) for every node down to the entry level; malformed nodes come through as-is."""
    if len(prefix) == len(kind.levels):
        yield prefix, node
        return
    for k, v in node.items():
        if isinstance(v, dict) and len(prefix) + 1 < len(kind.levels):
            yield from walk(kind, v, (*prefix, str(k)))
        else:
            yield (*prefix, str(k)), v


def entry_at(node: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = node
    for seg in path:
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------- report ----------


@dataclass
class Change:
    key: str
    decision: str
    before: dict[str, str]
    after: dict[str, str]
    note: str = ""


@dataclass
class Report:
    title: str
    source: str = ""
    rows: int = 0
    errors: list[guard.Issue] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    content_hash: str = ""
    written: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    def markdown(self) -> str:
        by = {d: [c for c in self.changes if c.decision == d] for d in ("approve", "edit", "reject")}
        out = [f"# {self.title}", ""]
        if self.source:
            out.append(
                f"Sheet: `{self.source}`, {self.rows} rows. Result: **{'OK' if self.ok else 'FAILED'}**"
                + ("" if not self.ok else (" (written)" if self.written else " (dry run: nothing written)"))
            )
        out += [
            "",
            "| Approved | Edited | Rejected (back to draft) | On hold |",
            "|---|---|---|---|",
            f"| {len(by['approve'])} | {len(by['edit'])} | {len(by['reject'])} | {len(self.held)} |",
            "",
        ]
        if self.errors:
            out += [f"## Errors ({len(self.errors)}), nothing was written", ""]
            out += [f"- {e}" for e in self.errors] + [""]
        for label, d in (
            ("Edited by the owner", "edit"),
            ("Approved as drafted", "approve"),
            ("Rejected: needs a new draft", "reject"),
        ):
            if by[d]:
                out += [f"## {label}", ""]
                for c in by[d]:
                    if d == "edit":
                        out += [f"- `{c.key}`"] + [
                            f"  - was: {c.before[f]}\n  - now: {c.after[f]}"
                            for f in c.after
                            if c.before.get(f) != c.after[f]
                        ]
                    else:
                        out.append(f"- `{c.key}`" + (f": {c.note}" if c.note else ""))
                out.append("")
        if self.coverage:
            out += ["## Coverage", "", "| File | Approved | Draft | Missing | Expected |", "|---|---|---|---|---|"]
            for name, cov in self.coverage.items():
                exp = cov["expected"]
                out.append(
                    f"| {name} | {cov['approved']} | {cov['draft']} | {'open' if exp is None else cov['missing']} | "
                    f"{'open' if exp is None else exp} |"
                )
            out.append("")
        if self.content_hash:
            out += [f"Library content hash: `{self.content_hash}`", ""]
        return "\n".join(out)


# ---------- checks shared by import and verify ----------


def _entry_issues(kind: Kind, path: tuple[str, ...], entry: Any) -> list[guard.Issue]:
    where = f"{kind.name}/{'/'.join(path)}"
    if not kind.valid_path(path):
        return [guard.Issue("INVALID_KEY", where)]
    if not isinstance(entry, dict):
        return [guard.Issue("BAD_ENTRY", where, "expected a mapping")]
    issues: list[guard.Issue] = []
    if entry.get("status") not in ("draft", "approved"):
        issues.append(guard.Issue("BAD_STATUS", where, str(entry.get("status"))))
    extra = set(entry) - {"status", *kind.fields}
    missing = set(kind.fields) - set(entry)
    if extra or missing:
        issues.append(guard.Issue("BAD_FIELDS", where, f"extra={sorted(extra)} missing={sorted(missing)}"))
    for f in kind.fields:
        if isinstance(entry.get(f), str):
            issues += guard.check(f"{where}.{f}", entry[f], max_len=kind.max_len, max_sentences=kind.max_sentences)
    return issues


def _coverage(data: Data) -> dict[str, dict[str, Any]]:
    cov: dict[str, dict[str, Any]] = {}
    for name, kind in KINDS.items():
        counts = {"approved": 0, "draft": 0}
        for _, e in walk(kind, data[name]):
            if isinstance(e, dict) and e.get("status") in counts:
                counts[e["status"]] += 1
        exp = kind.expected()
        have = sum(counts.values())
        cov[name] = {**counts, "expected": None if exp is None else len(exp),
                     "missing": None if exp is None else max(len(exp) - have, 0)}  # fmt: skip
    return cov


# ---------- manifest ----------


def _render(name: str, data: dict[str, Any]) -> str:
    return yamlio.dump(data, [f"{name}: written by `pranix-ctl library import`.",
                              "Change text through the review sheet, not by hand (plan section 18)."])  # fmt: skip


def build_manifest(files: dict[str, bytes], data: Data) -> dict[str, Any]:
    hashes = {n: _hash(b) for n, b in sorted(files.items())}
    approved = sum(c["approved"] for c in _coverage(data).values())
    draft = sum(c["draft"] for c in _coverage(data).values())
    content = _hash("\n".join(f"{n}:{h}" for n, h in hashes.items()).encode())
    return {"schema": 1, "files": hashes, "counts": {"approved": approved, "draft": draft}, "content_hash": content}


def _manifest_text(m: dict[str, Any]) -> str:
    return json.dumps(m, indent=2, sort_keys=True) + "\n"


def _write_atomic(path: Path, content: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def _write_all(root: Path, data: Data) -> str:
    root.mkdir(parents=True, exist_ok=True)
    files = {f"{n}.yaml": _render(n, d).encode("utf-8") for n, d in data.items() if d}
    for name, content in files.items():
        _write_atomic(root / name, content)
    m = build_manifest(files, data)
    _write_atomic(root / MANIFEST, _manifest_text(m).encode())
    return str(m["content_hash"])


# ---------- new drafts (D80: written by `pranix-ctl library draft`) ----------


def missing_keys(root: Path, kind_name: str) -> list[str]:
    """Keys of a one-level kind with no entry yet, in the kind's own order."""
    kind = KINDS[kind_name]
    level = kind.levels[0]
    if len(kind.levels) != 1 or level is None:
        raise ValueError(f"{kind_name} is not a one-level kind")
    have = load_all(root)[kind_name]
    return [k for k in level if k not in have]


def add_draft(root: Path, kind_name: str, key: str, fields: dict[str, str]) -> list[guard.Issue]:
    """Add one new `status: draft` entry and refresh the manifest. Never replaces an existing entry,
    so nothing reviewed is ever overwritten. Returns the problems (and writes nothing) if any check fails."""
    kind = KINDS[kind_name]
    data = load_all(root)
    if key in data[kind_name]:
        return [guard.Issue("EXISTS", f"{kind_name}/{key}", "already drafted or reviewed; not replaced")]
    entry = {"status": "draft", **{f: fields.get(f, "") for f in kind.fields}}
    issues = _entry_issues(kind, (key,), entry)
    if issues:
        return issues
    data[kind_name][key] = entry
    ordered = {k: data[kind_name][k] for k in (kind.levels[0] or ()) if k in data[kind_name]}
    data[kind_name] = ordered
    _write_all(root, data)
    return []


# ---------- export ----------


def export_sheet(root: Path, out: Path, kinds: list[str] | None = None, include_all: bool = False) -> int:
    data = load_all(root)
    rows: list[dict[str, str]] = []
    for name in kinds or list(KINDS):
        kind = KINDS[name]
        for path, entry in walk(kind, data[name]):
            if not isinstance(entry, dict) or (entry.get("status") == "approved" and not include_all):
                continue
            for f in kind.fields:
                rows.append({"key": f"{name}/{'/'.join(path)}", "field": f, "draft": str(entry.get(f, "")),
                             "decision": "", "edited": "", "note": ""})  # fmt: skip
    sheet.write_rows(out, SHEET_COLUMNS, rows)
    return len(rows)


# ---------- import ----------


def import_sheet(root: Path, sheet_path: Path, write: bool = False) -> Report:
    rep = Report("Library import report", source=sheet_path.name)
    try:
        rows = sheet.read_rows(sheet_path, ("key", "field", "draft", "decision"))
    except sheet.SheetError as e:
        rep.errors.append(guard.Issue("BAD_SHEET", sheet_path.name, str(e)))
        return rep
    rep.rows = len(rows)
    data = load_all(root)
    new = copy.deepcopy(data)

    groups: dict[tuple[str, tuple[str, ...]], dict[str, dict[str, str]]] = {}
    for i, r in enumerate(rows, start=2):
        parts = r["key"].split("/")
        if parts[0] not in KINDS:
            rep.errors.append(guard.Issue("UNKNOWN_KIND", f"row {i}", r["key"]))
            continue
        kind, path = KINDS[parts[0]], tuple(parts[1:])
        if not kind.valid_path(path) or not isinstance(entry_at(data[kind.name], path), dict):
            rep.errors.append(guard.Issue("UNKNOWN_KEY", f"row {i}", r["key"]))
            continue
        if r["field"] not in kind.fields:
            rep.errors.append(guard.Issue("UNKNOWN_FIELD", f"row {i}", f"{r['key']} / {r['field']}"))
            continue
        g = groups.setdefault((kind.name, path), {})
        if r["field"] in g:
            rep.errors.append(guard.Issue("DUPLICATE_ROW", f"row {i}", f"{r['key']} / {r['field']}"))
            continue
        g[r["field"]] = r

    for (kname, path), frows in groups.items():
        kind, key = KINDS[kname], f"{kname}/{'/'.join(path)}"
        entry = entry_at(new[kname], path)
        # Decisions are per field (owner, 25 Nov: six independent fields are reviewed one by one).
        # approve + edit -> the entry goes live with the edits; any reject -> edits kept, entry stays
        # draft for a new draft; any hold (no reject) -> edits kept, status unchanged.
        try:
            dec = {f: sheet.decision_of(r["decision"]) for f, r in frows.items()}
        except sheet.SheetError as e:
            rep.errors.append(guard.Issue("BAD_DECISION", key, str(e)))
            continue
        if set(dec.values()) == {"hold"}:
            rep.held.append(key)
            continue
        before = {f: str(entry.get(f, "")) for f in kind.fields}
        if set(frows) != set(kind.fields):
            rep.errors.append(guard.Issue("MISSING_FIELD_ROW", key, f"needs rows for {', '.join(kind.fields)}"))
            continue
        stale = [f for f, r in frows.items() if sheet.squash(r["draft"]) != sheet.squash(before[f])]
        if stale:
            rep.errors.append(
                guard.Issue("STALE_SHEET", key, "text changed since the sheet was exported: " + ", ".join(stale))
            )
            continue
        edits = {f: sheet.squash(r.get("edited", "")) for f, r in frows.items() if sheet.squash(r.get("edited", ""))}
        bad = [
            guard.Issue("EDIT_WITH_APPROVE", f"{key}.{f}", "text in the edited column: use the decision edit")
            for f in kind.fields
            if dec[f] == "approve" and f in edits
        ]
        bad += [guard.Issue("EDIT_EMPTY", f"{key}.{f}", "decision edit but nothing in the edited column")
                for f in kind.fields if dec[f] == "edit" and f not in edits]  # fmt: skip
        if bad:
            rep.errors += bad
            continue
        note = "; ".join(r["note"] for r in frows.values() if r.get("note"))
        after = {**before, **{f: t for f, t in edits.items() if dec[f] == "edit"}}
        problems = [
            i
            for f in kind.fields
            if after[f] != before[f] or "reject" not in dec.values()
            for i in guard.check(f"{key}.{f}", after[f], max_len=kind.max_len, max_sentences=kind.max_sentences)
        ]
        if problems:
            rep.errors += problems
            continue
        entry.update(after)
        if "reject" in dec.values():
            entry["status"] = "draft"
            decision = "reject"
        elif "hold" in dec.values():
            rep.held.append(key)
            decision = "edit" if after != before else "hold"
        else:
            entry["status"] = "approved"
            decision = "edit" if after != before else "approve"
        if decision == "hold":
            continue
        rep.changes.append(Change(key, decision, before, after, note))

    # the final state must be clean as a whole, whatever was untouched
    for kname, kind in KINDS.items():
        for path, node in walk(kind, new[kname]):
            rep.errors += _entry_issues(kind, path, node)
    rep.errors = list(dict.fromkeys(rep.errors))
    rep.coverage = _coverage(new)

    if rep.ok:
        files = {f"{n}.yaml": _render(n, d).encode() for n, d in new.items() if d}
        rep.content_hash = str(build_manifest(files, new)["content_hash"])
        if write:
            rep.content_hash = _write_all(root, new)
            rep.written = True
    return rep


# ---------- verify (CI gate) ----------


def verify(root: Path) -> Report:
    rep = Report("Library verify")
    if not root.exists():
        return rep  # nothing imported yet
    data = load_all(root)
    for name, kind in KINDS.items():
        for path, e in walk(kind, data[name]):
            rep.errors += _entry_issues(kind, path, e)
    rep.coverage = _coverage(data)
    files = {p.name: p.read_bytes() for p in sorted(root.glob("*.yaml"))}
    unknown = [n for n in files if n.removesuffix(".yaml") not in KINDS]
    rep.errors += [guard.Issue("UNKNOWN_FILE", n) for n in unknown]
    mpath = root / MANIFEST
    if files and not mpath.exists():
        rep.errors.append(guard.Issue("MANIFEST_MISSING", MANIFEST, "run the importer with --write"))
    elif mpath.exists():
        want = build_manifest({n: b for n, b in files.items() if n not in unknown}, data)
        have = json.loads(mpath.read_text(encoding="utf-8"))
        if have != want:
            rep.errors.append(guard.Issue("MANIFEST_STALE", MANIFEST, "files changed outside the importer"))
        rep.content_hash = str(want["content_hash"])
    return rep
