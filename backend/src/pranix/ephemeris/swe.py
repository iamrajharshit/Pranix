# SPDX-License-Identifier: AGPL-3.0-only
"""The only module that touches pyswisseph.

Swiss Ephemeris keeps its settings (ephemeris path, sidereal mode) in thread-local
storage: a new thread starts with the library defaults (Fagan/Bradley, not Lahiri).
So the mode is detected once per process, every thread applies the settings before
its first calculation, and every call holds a process-wide lock (ENG-01, ENG-02).
Sidereal Lahiri is applied by the library via FLG_SIDEREAL; this code never
subtracts the ayanamsa itself (D55).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import swisseph as swe

from .angles import normalize

PLANETS: tuple[tuple[str, int], ...] = (
    ("Sun", swe.SUN),
    ("Moon", swe.MOON),
    ("Mars", swe.MARS),
    ("Mercury", swe.MERCURY),
    ("Jupiter", swe.JUPITER),
    ("Venus", swe.VENUS),
    ("Saturn", swe.SATURN),
    ("Rahu", swe.MEAN_NODE),
)
BODY_ORDER: tuple[str, ...] = (*tuple(p for p, _ in PLANETS), "Ketu")

EphemerisMode = Literal["swieph", "moshier"]

_lock = threading.Lock()
_state: dict[str, object] = {}
_thread = threading.local()


@dataclass(frozen=True)
class Body:
    id: str
    longitude: float  # sidereal, [0, 360)
    speed: float  # degrees per day
    retrograde: bool


def init(ephe_path: str | None = None) -> EphemerisMode:
    """Initialise once. Returns the mode actually in effect."""
    with _lock:
        if "mode" in _state:
            return _state["mode"]  # type: ignore[return-value]
        path = ephe_path or os.environ.get("PRANIX_EPHE_PATH", "")
        _state["path"] = path if path and Path(path).is_dir() else ""
        _apply_thread_settings()
        # Probe: if the .se1 files are missing the library silently falls back to Moshier.
        _, ret = swe.calc_ut(2451545.0, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SIDEREAL)
        mode: EphemerisMode = "swieph" if ret & swe.FLG_SWIEPH else "moshier"
        _state["mode"] = mode
        _state["flags"] = (swe.FLG_SWIEPH if mode == "swieph" else swe.FLG_MOSEPH) | swe.FLG_SIDEREAL | swe.FLG_SPEED
        _state["version"] = swe.version
        return mode


def _apply_thread_settings() -> None:
    """Call with _lock held. Idempotent per thread."""
    if getattr(_thread, "ready", False):
        return
    if _state.get("path"):
        swe.set_ephe_path(str(_state["path"]))
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    _thread.ready = True


def mode() -> EphemerisMode:
    return init()


def library_version() -> str:
    init()
    return str(_state["version"])


def bodies(jd_ut: float) -> list[Body]:
    """Sidereal positions of the nine grahas. Ketu = Rahu + 180°; nodes always retrograde."""
    init()
    flags = int(_state["flags"])  # type: ignore[call-overload]
    out: list[Body] = []
    with _lock:
        _apply_thread_settings()
        for name, code in PLANETS:
            xx, _ = swe.calc_ut(jd_ut, code, flags)
            lon, speed = normalize(xx[0]), xx[3]
            out.append(Body(name, lon, speed, retrograde=(name == "Rahu") or speed < 0))
    rahu = out[-1]
    out.append(Body("Ketu", normalize(rahu.longitude + 180.0), rahu.speed, retrograde=True))
    return out


def ascendant(jd_ut: float, lat: float, lon: float) -> float:
    """Sidereal ascendant via houses_ex with whole-sign system and FLG_SIDEREAL."""
    init()
    with _lock:
        _apply_thread_settings()
        _, ascmc = swe.houses_ex(jd_ut, lat, lon, b"W", swe.FLG_SIDEREAL)
    return normalize(ascmc[0])


def ayanamsa(jd_ut: float) -> float:
    init()
    with _lock:
        _apply_thread_settings()
        return float(swe.get_ayanamsa_ut(jd_ut))
