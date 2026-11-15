# SPDX-License-Identifier: AGPL-3.0-only
"""Angle helpers. All boundary decisions use exact rationals (ENG-05).

A float longitude is converted to an exact Fraction (no rounding), so a value that is
mathematically on a boundary is classified by the half-open rule [start, end).
"""

from __future__ import annotations

from fractions import Fraction

SIGN = Fraction(30)
NAKSHATRA = Fraction(40, 3)  # 13°20′
PADA = Fraction(10, 3)  # 3°20′ (also one navamsa)
FULL = Fraction(360)


def normalize(lon: float) -> float:
    """Map any longitude into [0, 360)."""
    x = lon % 360.0
    return 0.0 if x >= 360.0 else x


def _q(lon: float) -> Fraction:
    return Fraction(normalize(lon))


def sign_index(lon: float) -> int:
    return int(_q(lon) // SIGN)


def deg_in_sign(lon: float) -> float:
    return float(_q(lon) - sign_index(lon) * SIGN)


def nakshatra_index(lon: float) -> int:
    """0..26."""
    return int(_q(lon) // NAKSHATRA)


def pada(lon: float) -> int:
    """1..4 within the nakshatra."""
    q = _q(lon)
    return int((q - nakshatra_index(lon) * NAKSHATRA) // PADA) + 1


def d9_sign_index(lon: float) -> int:
    """Navamsa sign: floor(lon / 3°20′) mod 12 (FR-CAL-17)."""
    return int(_q(lon) // PADA) % 12


def whole_sign_house(sign: int, lagna_sign: int) -> int:
    """1..12, counted from the lagna sign."""
    return (sign - lagna_sign) % 12 + 1


def truncate_dm(deg: float) -> tuple[int, int]:
    """Degrees and minutes, truncated (never rounded), so 29.9999° shows 29°59′."""
    q = Fraction(deg)
    whole = int(q)
    minutes = int((q - whole) * 60)
    return whole, minutes


def format_dm(deg: float) -> str:
    d, m = truncate_dm(deg)
    return f"{d}°{m:02d}′"


def near_boundary(lon: float, tolerance: float) -> bool:
    """True if within `tolerance` degrees of a sign or nakshatra edge (FR-CAL-11)."""
    q = _q(lon)
    tol = Fraction(tolerance)
    for unit in (SIGN, NAKSHATRA):
        r = q % unit
        if r < tol or unit - r < tol:
            return True
    return False
