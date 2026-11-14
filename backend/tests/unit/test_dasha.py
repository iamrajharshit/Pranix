# SPDX-License-Identifier: AGPL-3.0-only
import itertools
from datetime import UTC, datetime
from fractions import Fraction

import pytest

from pranix.ephemeris import dasha
from pranix.ephemeris.ruleset import load_ruleset

RS = load_ruleset()
BIRTH = dasha.instant(datetime(1984, 12, 7, 18, 50, tzinfo=UTC))
MOON = 44.4  # Taurus 14°24′, Rohini


def test_year_is_exactly_31557600_seconds() -> None:
    assert dasha.year_seconds(RS) == 31_557_600


def test_cycle_is_120_years_and_contiguous() -> None:
    mahas = dasha.mahadashas(RS, MOON, BIRTH)
    assert len(mahas) == 9 and mahas[0].from_birth and mahas[0].start == BIRTH
    assert mahas[-1].end - mahas[0].full_start == 120 * dasha.year_seconds(RS)
    for a, b in itertools.pairwise(mahas):
        assert a.end == b.start


def test_children_sum_exactly_to_parent_at_every_level() -> None:
    p = dasha.mahadashas(RS, MOON, BIRTH)[3]
    for _ in range(4):
        kids = dasha.children(RS, p)
        assert kids[0].start == p.full_start and kids[-1].end == p.end
        assert sum((k.end - k.start for k in kids), Fraction(0)) == p.length
        p = kids[2]
    with pytest.raises(ValueError):
        dasha.children(RS, p)


def test_path_lookup() -> None:
    kids = dasha.periods_at_path(RS, MOON, BIRTH, "Ju>Ve")
    assert next(k.lord for k in kids) == "Venus" and kids[0].path == "Ju>Ve>Ve"
    with pytest.raises(ValueError):
        dasha.periods_at_path(RS, MOON, BIRTH, "Xx")
