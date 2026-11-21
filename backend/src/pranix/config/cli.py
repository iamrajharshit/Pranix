# SPDX-License-Identifier: AGPL-3.0-only
"""`pranix-ctl` (CFG-06): config check, engine self-test and database migrations."""

from __future__ import annotations

import argparse
import sys

from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pranix-ctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config-check", help="validate configuration; prints secret names and fingerprints only")
    sub.add_parser("selftest", help="run the engine golden self-test")
    db = sub.add_parser("db", help="database migrations (needs PRANIX_DATABASE_URL)")
    db.add_argument("action", choices=["upgrade", "downgrade", "current"])
    db.add_argument("revision", nargs="?", default=None, help="target (default: head / -1)")
    args = ap.parse_args(argv)

    if args.cmd == "db":
        from ..store import migrate

        s = Settings()
        if s.database_url is None:
            print("ERROR PRANIX_DATABASE_URL is not set", file=sys.stderr)
            return 1
        url = s.database_url.get_secret_value()
        if args.action == "upgrade":
            migrate.upgrade(url, args.revision or "head")
        elif args.action == "downgrade":
            migrate.downgrade(url, args.revision or "-1")
        else:
            migrate.current(url)
        return 0

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
