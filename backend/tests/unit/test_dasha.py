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


# D84 (owner, 28 Nov): after 120 years the sequence starts again.


def test_second_cycle_continues_the_first_exactly() -> None:
    one = dasha.mahadashas(RS, MOON, BIRTH)
    two = dasha.mahadashas(RS, MOON, BIRTH, 2)
    assert [p.lord for p in two] == [p.lord for p in one]  # same order, from the birth star's lord
    assert two[0].full_start == one[-1].end  # no gap, no overlap
    assert two[0].start == two[0].full_start and not two[0].from_birth  # only cycle one is clipped
    assert two[-1].end - two[0].start == dasha.cycle_seconds(RS) == 120 * dasha.year_seconds(RS)
    assert all(p.cycle == 2 for p in two)


@pytest.mark.parametrize("years", [0, 50, 99, 119, 121, 150, 240, 300])
def test_there_is_always_a_current_period(years: int) -> None:
    at = BIRTH + years * dasha.year_seconds(RS) + 1
    chain = dasha.active_chain(RS, MOON, BIRTH, at)
    assert len(chain) == dasha.MAX_DEPTH
    assert all(p.start <= at < p.end for p in chain)


def test_first_cycle_output_is_unchanged() -> None:
    """Charts inside their first cycle get byte-identical answers: no 'cycle' key appears."""
    for p in dasha.mahadashas(RS, MOON, BIRTH) + dasha.children(RS, dasha.mahadashas(RS, MOON, BIRTH)[0]):
        assert "cycle" not in p.to_dict()
    later = dasha.mahadashas(RS, MOON, BIRTH, 2)
    assert later[0].to_dict()["cycle"] == 2
    assert dasha.children(RS, later[0])[0].cycle == 2


def test_cycle_at_and_paths_within_a_cycle() -> None:
    end_of_one = dasha.mahadashas(RS, MOON, BIRTH)[-1].end
    assert dasha.cycle_at(RS, MOON, BIRTH, end_of_one - 1) == 1
    assert dasha.cycle_at(RS, MOON, BIRTH, end_of_one) == 2
    kids = dasha.periods_at_path(RS, MOON, BIRTH, "Ju", 2)
    assert kids[0].start >= end_of_one and kids[0].cycle == 2
    with pytest.raises(ValueError):
        dasha.mahadashas(RS, MOON, BIRTH, dasha.MAX_CYCLE + 1)
