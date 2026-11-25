# SPDX-License-Identifier: AGPL-3.0-only
"""`pranix-ctl library ...` and `pranix-ctl rules ...` (plan section 18)."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import library, rules
from .kinds import KINDS


def add_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    lib = sub.add_parser("library", help="reviewed library text: export a review sheet, import decisions, verify")
    ls = lib.add_subparsers(dest="action", required=True)
    e = ls.add_parser("export-sheet", help="list draft entries as a CSV review sheet")
    e.add_argument("--out", required=True, type=Path)
    e.add_argument("--kind", action="append", choices=sorted(KINDS))
    e.add_argument("--all", action="store_true", help="include approved entries too")
    i = ls.add_parser("import", help="apply the owner's decisions from a review sheet (dry run unless --write)")
    i.add_argument("sheet", type=Path)
    i.add_argument("--write", action="store_true")
    i.add_argument("--report", type=Path, help="write the diff report (markdown) here")
    ls.add_parser("verify", help="check every entry, the key layout and the manifest (CI gate)")
    d = ls.add_parser("draft", help="AI-draft missing deep entries as status: draft, for review (D80)")
    d.add_argument("--kind", required=True, choices=["nakshatra_deep", "sign_deep", "planet_deep"])
    d.add_argument("--key", action="append", help="only these keys, e.g. --key Rohini")
    d.add_argument("--limit", type=int, default=0, help="stop after this many new drafts (0 = all missing)")
    for p in (e, i, ls.choices["verify"], d):
        p.add_argument("--root", type=Path, default=None, help="library folder (default: the packaged one)")

    ru = sub.add_parser("rules", help="owner-approved rule tables")
    rs = ru.add_subparsers(dest="action", required=True)
    ri = rs.add_parser("import", help="apply the owner's decisions from a rule sheet (dry run unless --write)")
    ri.add_argument("sheet", type=Path)
    ri.add_argument("--write", action="store_true")
    ri.add_argument("--reviewed-on", help="date of the owner's approval, e.g. 2026-11-28")
    ri.add_argument("--report", type=Path)
    re_ = rs.add_parser("export-sheet", help="write the current tables as a review sheet")
    re_.add_argument("--out", required=True, type=Path)
    rs.add_parser("verify", help="check the ruleset file (CI gate)")
    for p in (ri, re_, rs.choices["verify"]):
        p.add_argument("--file", type=Path, default=None, help="ruleset file (default: the packaged one)")


def _emit(report_md: str, path: Path | None) -> None:
    print(report_md)
    if path:
        path.write_text(report_md, encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if args.cmd == "library":
        root = args.root or library.default_root()
        if args.action == "export-sheet":
            n = library.export_sheet(root, args.out, args.kind, args.all)
            print(f"wrote {n} rows to {args.out}")
            return 0
        rep = library.import_sheet(root, args.sheet, args.write) if args.action == "import" else library.verify(root)
        _emit(rep.markdown(), getattr(args, "report", None))
        return 0 if rep.ok else 1
    path = args.file or rules.default_path()
    if args.action == "export-sheet":
        print(f"wrote {rules.export_sheet(path, args.out)} rows to {args.out}")
        return 0
    if args.action == "import":
        rr = rules.import_sheet(path, args.sheet, args.reviewed_on, args.write)
    else:
        rr = rules.verify(path)
    _emit(rr.markdown(), getattr(args, "report", None))
    return 0 if rr.ok else 1
