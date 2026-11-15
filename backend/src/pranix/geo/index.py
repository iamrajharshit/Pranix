# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only GeoNames index in SQLite FTS5 (FR-GEO-01, D64 nearest place).

Built at image build time by tools/build_geonames.py; opened read-only and immutable.
Each thread gets its own connection (sqlite3 connections are not shared across threads).
"""

from __future__ import annotations

import math
import re
import sqlite3
import threading
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EARTH_KM = 6371.0088
_TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    admin1: str | None
    country: str
    lat: float
    lon: float
    tz: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fold(text: str) -> str:
    """Lower-case and strip accents so 'Bogotá' matches 'bogota'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


class GeoIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(str(self.path))
        self._local = threading.local()
        self.count = int(self._db().execute("SELECT COUNT(*) FROM places").fetchone()[0])

    def _db(self) -> sqlite3.Connection:
        db: sqlite3.Connection | None = getattr(self._local, "db", None)
        if db is None:
            db = sqlite3.connect(f"file:{self.path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
            db.row_factory = sqlite3.Row
            self._local.db = db
        return db

    @staticmethod
    def _row(r: sqlite3.Row) -> Place:
        return Place(f"geonames:{r['id']}", r["name"], r["admin1"], r["country"], r["lat"], r["lon"], r["tz"])

    def search(self, q: str, limit: int = 8) -> list[Place]:
        """Prefix match on every word, most populous first. [] when nothing matches."""
        tokens = _TOKEN.findall(fold(q))
        if not tokens:
            return []
        # Each token is letters only (regex above), so quoting is safe; '*' makes it a prefix query.
        match = " ".join(f'"{t}"*' for t in tokens[:5])
        rows = (
            self._db()
            .execute(
                "SELECT p.* FROM places_fts f JOIN places p ON p.id = f.rowid "
                "WHERE places_fts MATCH ? ORDER BY p.population DESC, p.name LIMIT ?",
                (match, max(1, min(limit, 10))),
            )
            .fetchall()
        )
        return [self._row(r) for r in rows]

    def get(self, place_id: str) -> Place | None:
        m = re.fullmatch(r"geonames:(\d{1,12})", place_id)
        if not m:
            return None
        r = self._db().execute("SELECT * FROM places WHERE id = ?", (int(m.group(1)),)).fetchone()
        return self._row(r) if r else None

    def nearest(self, lat: float, lon: float, max_km: float = 50.0) -> tuple[Place, float] | None:
        """Nearest place within max_km, using a bounding box on indexed lat/lon, then exact distance."""
        dlat = max_km / 111.0
        dlon = max_km / max(1e-6, 111.0 * math.cos(math.radians(min(89.0, abs(lat)))))
        rows = (
            self._db()
            .execute(
                "SELECT * FROM places WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? ORDER BY population DESC, id",
                (lat - dlat, lat + dlat, lon - dlon, lon + dlon),
            )
            .fetchall()
        )
        best: tuple[Place, float] | None = None
        for r in rows:
            d = haversine_km(lat, lon, r["lat"], r["lon"])
            # Rows come largest first, so an exact tie keeps the larger place (deterministic).
            if d <= max_km and (best is None or d < best[1] - 1e-9):
                best = (self._row(r), d)
        return best
