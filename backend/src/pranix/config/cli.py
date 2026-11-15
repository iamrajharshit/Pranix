# SPDX-License-Identifier: AGPL-3.0-only
"""`pranix-ctl` (CFG-06): config check and engine self-test."""

from __future__ import annotations

import argparse
import sys

from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pranix-ctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config-check", help="validate configuration; prints secret names and fingerprints only")
    sub.add_parser("selftest", help="run the engine golden self-test")
    args = ap.parse_args(argv)

    if args.cmd == "config-check":
        s = Settings()
        for name, fp in s.secret_fingerprints().items():
            print(f"{name}: {fp}")
        problems = s.problems()
        for p in problems:
            print(f"ERROR {p}", file=sys.stderr)
        return 1 if problems else 0

    from ..ephemeris import selftest, swe

    swe.init(Settings().ephe_path)
    r = selftest.run()
    print("selftest", "ok" if r.ok else "FAILED " + ", ".join(r.failures), "mode", swe.mode())
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
