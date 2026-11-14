#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail if a source file lacks the SPDX header (NFR-LIC-01)."""

import pathlib
import sys

HEADER = "SPDX-License-Identifier: AGPL-3.0-only"
SUFFIXES = {".py", ".ts", ".tsx", ".yaml", ".yml", ".sh", ".toml"}
SKIP_DIRS = {".git", "node_modules", ".venv", "docs", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
missing = [
    p for p in root.rglob("*")
    if p.is_file() and p.suffix in SUFFIXES and not (set(p.parts) & SKIP_DIRS)
    and HEADER not in "".join(p.read_text(encoding="utf-8", errors="ignore").splitlines(True)[:3])
]
for p in missing:
    print(f"missing SPDX header: {p}")
sys.exit(1 if missing else 0)
