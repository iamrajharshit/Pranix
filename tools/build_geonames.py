#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the offline place index (FR-GEO-01) from GeoNames dumps.

Inputs (directory): cities500.txt, admin1CodesASCII.txt, countryInfo.txt
from https://download.geonames.org/export/dump/ (CC BY 4.0, attribution in NOTICE).
Output: SQLite with `places` (+ lat/lon indexes) and an FTS5 table `places_fts`.

The time zone stored for each place is computed from its coordinates with
timezonefinder (FR-GEO-03); GeoNames' own zone is kept only as a cross-check and
mismatches are counted.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import unicodedata
from pathlib import Path

from timezonefinder import TimezoneFinder


def fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cities", default="cities500.txt")
    args = ap.parse_args()

    countries: dict[str, str] = {}
    for line in (args.src / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            c = line.split("\t")
            countries[c[0]] = c[4]
    admin1: dict[str, str] = {}
    for line in (args.src / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
        if line:
            c = line.split("\t")
            admin1[c[0]] = c[1]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.unlink(missing_ok=True)
    db = sqlite3.connect(args.out)
    db.executescript(
        """
        PRAGMA journal_mode = OFF;
        CREATE TABLE places (id INTEGER PRIMARY KEY, name TEXT NOT NULL, admin1 TEXT, country TEXT NOT NULL,
                             lat REAL NOT NULL, lon REAL NOT NULL, tz TEXT NOT NULL, geonames_tz TEXT,
                             population INTEGER NOT NULL);
        CREATE VIRTUAL TABLE places_fts USING fts5(name, alt, region, tokenize = 'unicode61 remove_diacritics 2');
        """
    )
    tf = TimezoneFinder()
    rows = skipped = mismatch = 0
    with (args.src / args.cities).open(encoding="utf-8") as fh:
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) < 19 or c[6] != "P":
                continue
            gid, name, ascii_name, alts = int(c[0]), c[1], c[2], c[3]
            lat, lon = round(float(c[4]), 4), round(float(c[5]), 4)
            tz = tf.timezone_at(lng=lon, lat=lat)
            if not tz or tz.startswith("Etc/"):
                skipped += 1
                continue
            if c[17] and c[17] != tz:
                mismatch += 1
            alt_names = [a for a in alts.split(",") if a and a.isascii()][:20]
            region_name, country = admin1.get(f"{c[8]}.{c[10]}"), countries.get(c[8], c[8])
            db.execute(
                "INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?)",
                (gid, name, region_name, country, lat, lon, tz, c[17] or None, int(c[14] or 0)),
            )
            # Region and country are searchable too, so "Pune India" and "Paris France" work.
            db.execute("INSERT INTO places_fts(rowid, name, alt, region) VALUES (?,?,?,?)",
                       (gid, fold(f"{name} {ascii_name}"), fold(" ".join(alt_names)),
                        fold(f"{region_name or ''} {country}")))
            rows += 1
    db.executescript("CREATE INDEX places_lat ON places(lat); CREATE INDEX places_lon ON places(lon);"
                     "INSERT INTO places_fts(places_fts) VALUES('optimize'); VACUUM;")
    db.close()
    print(f"places={rows} skipped_no_land_tz={skipped} tz_mismatch_vs_geonames={mismatch}", file=sys.stderr)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
