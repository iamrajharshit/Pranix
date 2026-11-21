#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Export what the frontend compiles and tests against (F1, plan section 15.1).

Writes, from the running code (never by hand):
  web/src/api/openapi.json                 the app's OpenAPI document
  web/src/__fixtures__/sample_1984.json    engine output for the invented sample chart
  web/src/__fixtures__/sample_1984_unknown_time.json   the same birth with the time unknown

`--check` writes nothing and exits 1 if any file is out of date (CI drift gate). The fixtures
use a fixed `as_of` date so they change only when the engine, rulesets or contract change.
Needs the Swiss Ephemeris files (tools/fetch_ephe.sh), like CI.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
os.environ.setdefault("PRANIX_EPHE_PATH", str(ROOT / "data" / "ephe"))
os.environ.setdefault("PRANIX_ENV", "test")

AS_OF = date(2026, 11, 14)  # the reference date used across docs and tests


def _dump(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def outputs() -> dict[Path, str]:
    from pranix.ephemeris import swe
    from pranix.ephemeris.master import compute
    from pranix.ephemeris.selftest import GOLDEN
    from pranix.gateway.app import create_app

    if swe.init(os.environ["PRANIX_EPHE_PATH"]) != "swieph":
        sys.exit("export_contract: Swiss Ephemeris files missing; run tools/fetch_ephe.sh first")
    web = ROOT / "web" / "src"
    return {
        web / "api" / "openapi.json": _dump(create_app().openapi()),
        web / "__fixtures__" / "sample_1984.json": _dump(compute(GOLDEN, AS_OF)),
        web / "__fixtures__" / "sample_1984_unknown_time.json": _dump(
            compute(dataclasses.replace(GOLDEN, birth_time_known=False), AS_OF)
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if a committed file is out of date")
    args = ap.parse_args()
    stale = []
    for path, text in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("Out of date (run: python tools/export_contract.py, then npm run gen:api in web/):")
        for p in stale:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
