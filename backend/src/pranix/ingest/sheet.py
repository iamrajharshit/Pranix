# SPDX-License-Identifier: AGPL-3.0-only
"""Review sheets are plain CSV (UTF-8). In Excel or Google Sheets use "Save as CSV UTF-8".

Library sheet columns: key, field, draft, decision, edited, note
Rule sheet columns:    table, key, value, decision, edited, note
Column names are matched case-insensitively; extra columns are ignored.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Literal

Decision = Literal["approve", "edit", "reject", "hold"]

_WORDS: dict[str, Decision] = {
    "approve": "approve", "approved": "approve", "ok": "approve", "yes": "approve", "y": "approve", "✅": "approve",
    "edit": "edit", "edited": "edit", "change": "edit", "changed": "edit",
    "reject": "reject", "rejected": "reject", "no": "reject", "redo": "reject", "❌": "reject",
    "hold": "hold", "skip": "hold", "later": "hold", "?": "hold", "": "hold",
}  # fmt: skip


class SheetError(ValueError):
    pass


def decision_of(raw: str) -> Decision:
    word = (raw or "").strip().lower()
    if word not in _WORDS:
        raise SheetError(f"unknown decision {raw!r} (use approve, edit, reject or hold)")
    return _WORDS[word]


def squash(text: str) -> str:
    """Collapse whitespace so a sheet round trip through Excel never looks like a change."""
    return " ".join((text or "").split())


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    sample = raw[:2048]
    dialect = csv.excel_tab if sample.count("\t") > sample.count(",") else csv.excel
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if reader.fieldnames is None:
        raise SheetError("the sheet is empty")
    names = {(n or "").strip().lower(): n for n in reader.fieldnames}
    missing = [c for c in required if c not in names]
    if missing:
        raise SheetError("missing column(s): " + ", ".join(missing))
    rows: list[dict[str, str]] = []
    for r in reader:
        row = {k: (r.get(orig) or "").strip() for k, orig in names.items() if k}
        if any(row.values()):
            rows.append(row)
    return rows


def write_rows(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    path.write_bytes(("﻿" + buf.getvalue()).encode("utf-8"))  # BOM so Excel opens UTF-8 correctly
