# SPDX-License-Identifier: AGPL-3.0-only
from fractions import Fraction

from pranix.ephemeris import angles


def classical_d9(lon: Fraction) -> int:
    """Movable signs start from themselves, fixed from the 9th, dual from the 5th."""
    sign = int(lon // 30)
    k = int((lon - 30 * sign) / angles.PADA)
    start = {0: sign, 1: (sign + 8) % 12, 2: (sign + 4) % 12}[sign % 3]
    return (start + k) % 12


def test_d9_formula_equals_classical_rule_on_all_108_slices() -> None:
    for s in range(12):
        for k in range(9):
            for offset in (Fraction(0), Fraction(1, 1000), angles.PADA - Fraction(1, 1000)):
                lon = 30 * s + k * angles.PADA + offset
                assert angles.d9_sign_index(float(lon)) == classical_d9(Fraction(float(lon)))


def test_half_open_boundaries() -> None:
    assert angles.sign_index(30.0) == 1
    assert angles.nakshatra_index(40 / 3) in (0, 1)  # float 13.333.. is just below or at the edge
    assert angles.nakshatra_index(13.34) == 1
    assert angles.pada(0.0) == 1
    assert angles.sign_index(359.9999999) == 11
    assert angles.sign_index(360.0) == 0


def test_truncation_never_rounds_up() -> None:
    assert angles.truncate_dm(29.99999) == (29, 59)
    assert angles.format_dm(20.2999) == "20°17′"
    assert angles.format_dm(6.0) == "6°00′"


def test_whole_sign_house() -> None:
    assert angles.whole_sign_house(4, 4) == 1
    assert angles.whole_sign_house(3, 4) == 12


def test_near_boundary() -> None:
    assert angles.near_boundary(29.995, 0.01)
    assert not angles.near_boundary(15.0, 0.01)
