# SPDX-License-Identifier: AGPL-3.0-only
from datetime import UTC, datetime

import pytest
import swisseph as swe

from pranix.ephemeris.timeconv import BirthTimeError, julian_day_ut, to_utc


def test_india_offset() -> None:
    r = to_utc(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata")
    assert r.utc == datetime(1984, 12, 7, 18, 50, tzinfo=UTC)


def test_dst_gap_is_rejected() -> None:
    with pytest.raises(BirthTimeError) as e:
        to_utc(datetime(2021, 3, 14, 2, 30), "America/New_York")
    assert e.value.code == "NONEXISTENT_LOCAL_TIME"


def test_dst_fold_needs_a_choice() -> None:
    with pytest.raises(BirthTimeError) as e:
        to_utc(datetime(2021, 11, 7, 1, 30), "America/New_York")
    assert e.value.code == "AMBIGUOUS_LOCAL_TIME"
    assert [o["disambiguation"] for o in e.value.options] == ["earlier", "later"]
    early = to_utc(datetime(2021, 11, 7, 1, 30), "America/New_York", "earlier").utc
    late = to_utc(datetime(2021, 11, 7, 1, 30), "America/New_York", "later").utc
    assert (late - early).total_seconds() == 3600


def test_out_of_range() -> None:
    with pytest.raises(BirthTimeError):
        to_utc(datetime(1700, 1, 1), "UTC")


def test_julian_day_matches_swisseph() -> None:
    dt = datetime(1984, 12, 7, 18, 50, tzinfo=UTC)
    assert abs(julian_day_ut(dt) - swe.julday(1984, 12, 7, 18 + 50 / 60)) < 1e-9
