# SPDX-License-Identifier: AGPL-3.0-only
"""Charts on days when the clocks change at midnight (bug bounty, 26 Nov).

The unknown-time rule (D56) and the deity check read the first and last second of the birth day.
They used to ask for local 00:00:00 and 23:59:59 as wall times, which some days don't have (clocks
jump at midnight) or have twice (clocks go back at midnight). Every chart on such a day failed,
even an ordinary afternoon birth, with "that time did not exist". São Paulo did this every year
until 2019; Havana, Santiago and Asunción still do.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pranix.ephemeris.master import BirthInput, compute
from pranix.ephemeris.timeconv import BirthTimeError, day_bounds_utc

AS_OF = date(2026, 11, 14)
SP = ("America/Sao_Paulo", -23.55, -46.63)

DAYS = [
    # (zone, day, what happens)
    ("America/Sao_Paulo", date(2018, 11, 4), "jumps forward at midnight"),
    ("America/Sao_Paulo", date(2019, 2, 16), "goes back at midnight at the end of this day"),
    ("America/Havana", date(2024, 3, 10), "jumps forward at midnight"),
    ("America/Santiago", date(2023, 9, 3), "jumps forward at midnight"),
    ("America/Asuncion", date(2023, 10, 1), "jumps forward at midnight"),
    ("Europe/London", date(2021, 3, 28), "ordinary changeover at one in the morning"),
    ("Asia/Kolkata", date(1984, 12, 8), "no change"),
]


@pytest.mark.parametrize(("zone", "day", "why"), DAYS, ids=[f"{z}-{d}" for z, d, _ in DAYS])
def test_day_bounds_are_the_first_and_last_second_of_the_local_day(zone: str, day: date, why: str) -> None:
    tz = ZoneInfo(zone)
    start, end = day_bounds_utc(day, zone)
    assert start.astimezone(tz).date() == day and end.astimezone(tz).date() == day
    # nothing of this day lies outside the bounds: a second before and after is another day
    assert (start - timedelta(seconds=1)).astimezone(tz).date() < day
    assert (end + timedelta(seconds=1)).astimezone(tz).date() > day
    assert start.tzinfo is UTC and end.tzinfo is UTC


def test_a_day_that_never_happened_is_refused() -> None:
    # Samoa skipped 30 December 2011 when it moved across the date line.
    with pytest.raises(BirthTimeError) as e:
        day_bounds_utc(date(2011, 12, 30), "Pacific/Apia")
    assert e.value.code == "NONEXISTENT_LOCAL_TIME"


@pytest.mark.parametrize("known", [True, False], ids=["time-known", "time-unknown"])
@pytest.mark.parametrize("day", [date(2018, 11, 4), date(2019, 2, 16)], ids=["jump-forward", "go-back"])
def test_charts_on_midnight_changeover_days_compute(day: date, known: bool) -> None:
    zone, lat, lon = SP
    inp = BirthInput(
        datetime.combine(day, datetime.min.time()).replace(hour=14), zone, lat, lon, birth_time_known=known
    )
    m = compute(inp.canonical(), AS_OF)
    assert m["nakshatra"] is not None or m["flags"]["time_sensitive"]


def test_unknown_time_is_still_certain_only_on_an_ordinary_day() -> None:
    """The same answer as before the fix where nothing odd happens (golden behaviour kept)."""
    inp = BirthInput(datetime(1984, 12, 8, 12), "Asia/Kolkata", 18.5204, 73.8567, birth_time_known=False)
    start, end = day_bounds_utc(date(1984, 12, 8), "Asia/Kolkata")
    assert start == datetime(1984, 12, 7, 18, 30, tzinfo=UTC)
    assert end == datetime(1984, 12, 8, 18, 29, 59, tzinfo=UTC)
    assert compute(inp.canonical(), AS_OF)["d1"]["lagna"] is None


NOON_DAYS = [
    ("America/Chicago", date(1883, 11, 18), 41.88, -87.63),  # railway time: noon happened twice
    ("America/Anchorage", date(1867, 10, 19), 61.22, -149.90),  # Alaska moved across the date line
    ("Africa/Khartoum", date(2000, 1, 15), 15.50, 32.56),  # noon was skipped
]


@pytest.mark.parametrize(("zone", "day", "lat", "lon"), NOON_DAYS, ids=[z for z, *_ in NOON_DAYS])
def test_unknown_time_works_on_days_when_noon_was_skipped_or_doubled(
    zone: str, day: date, lat: float, lon: float
) -> None:
    inp = BirthInput(
        datetime.combine(day, datetime.min.time()).replace(hour=12), zone, lat, lon, birth_time_known=False
    )
    m = compute(inp.canonical(), AS_OF)
    assert m["d1"]["lagna"] is None and m["d9"] is None
