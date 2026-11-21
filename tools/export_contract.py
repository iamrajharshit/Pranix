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
import difflib
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


def _quantize(obj: object) -> object:
    """Floats to 6 decimals in the fixtures only: full-precision engine floats can differ in the
    last bits between CPUs and Python builds, which would make the drift gate flaky. Everything
    the screen shows (truncated degrees, signs, padas) is far coarser than a millionth."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _quantize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_quantize(v) for v in obj]
    return obj


def _dump(obj: object, quantize: bool = False) -> str:
    return json.dumps(_quantize(obj) if quantize else obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


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
        web / "__fixtures__" / "sample_1984.json": _dump(compute(GOLDEN, AS_OF), quantize=True),
        web / "__fixtures__" / "sample_1984_unknown_time.json": _dump(
            compute(dataclasses.replace(GOLDEN, birth_time_known=False), AS_OF), quantize=True
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
            old, new = (current or "").splitlines(), text.splitlines()
            diff = difflib.unified_diff(old, new, "committed", "now", n=1, lineterm="")
            print("\n".join(list(diff)[:40]))
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
