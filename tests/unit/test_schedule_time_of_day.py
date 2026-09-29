"""A control owed at a time of day: at the hour a person chose, in the install's zone, once a day.

`brain.ops.schedule.owed` takes the time and zone as an input, so every case here is decided over
fixed instants far from any wall clock, and the zone is one that is not UTC so a reading in the
wrong zone is off by hours rather than by nothing.

Task ids: M38.3.3.1
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from brain.console.configuration import setting_problem
from brain.ops.controls import Control, Invocation, Severity
from brain.ops.schedule import AtTime, owed, time_of_day
from brain.ops.schedule_runner import times_of_day

ZONE = ZoneInfo("Asia/Singapore")
SIX_PM = AtTime(at=time(18, 0), zone=ZONE)
#: 18:00 in Singapore is 10:00 UTC, on a day nobody's clock will reach.
TODAY_SIX_PM = datetime(2999, 3, 1, 10, 0, tzinfo=UTC)

DAILY = Control(
    name="evening_note",
    symbols=("brain.ops.schedule:owed",),
    guards="that a note is sent each evening",
    lost_silently="no note arrives, and nothing else says so",
    every=timedelta(days=1),
    severity=Severity.NOTICED,
    invoked_by=Invocation.IN_PROCESS,
    daily_at="INSTALL_DIGEST_TIME",
)


def due(now: datetime, last: datetime | None) -> list[str]:
    runs = {} if last is None else {DAILY.name: last}
    return [
        one.name for one in owed(now=now, last_run=runs, controls=(DAILY,), at={DAILY.name: SIX_PM})
    ]


def test_a_time_of_day_is_two_digits_a_colon_and_two_digits_on_the_24_hour_clock() -> None:
    """Delete this and `6pm` or `18:60` reaches the schedule, which reads it as no time at all."""
    assert time_of_day("18:00") == time(18, 0)
    assert time_of_day(" 07:05 ") == time(7, 5)
    for wrong in ("6pm", "18:60", "24:00", "1800", "8:00", ""):
        assert time_of_day(wrong) is None
    assert setting_problem("INSTALL_DIGEST_TIME", "18:00") == ""
    assert "HH:MM" in setting_problem("INSTALL_DIGEST_TIME", "6pm")


def test_a_control_that_has_never_run_waits_for_todays_hour_rather_than_running_at_once() -> None:
    """**Installed at ten, the digest arrives at six, not at ten.** Delete this and a fresh install
    posts a digest the moment the worker starts, and every morning after."""
    assert due(TODAY_SIX_PM - timedelta(hours=8), None) == []
    assert due(TODAY_SIX_PM, None) == ["evening_note"]
    (first,) = owed(
        now=TODAY_SIX_PM + timedelta(minutes=1),
        last_run={},
        controls=(DAILY,),
        at={DAILY.name: SIX_PM},
    )
    assert first.first_run and first.late_by == timedelta(0) and first.due_since == TODAY_SIX_PM


def test_it_is_owed_once_a_day_at_the_hour_and_not_again_until_the_next() -> None:
    """Delete this and the control runs on every tick after six, or at six plus a day after the
    last run, which drifts later with every slow tick."""
    yesterday = TODAY_SIX_PM - timedelta(days=1)
    assert due(TODAY_SIX_PM - timedelta(minutes=1), yesterday + timedelta(seconds=5)) == []
    assert due(TODAY_SIX_PM + timedelta(seconds=30), yesterday + timedelta(minutes=7)) == [
        "evening_note"
    ]
    assert due(TODAY_SIX_PM + timedelta(hours=3), TODAY_SIX_PM + timedelta(seconds=30)) == []
    (late,) = owed(
        now=TODAY_SIX_PM + timedelta(hours=2),
        last_run={DAILY.name: yesterday},
        controls=(DAILY,),
        at={DAILY.name: SIX_PM},
    )
    assert late.late_by == timedelta(hours=2) and not late.first_run


def test_the_hour_is_read_in_the_installs_zone_and_not_in_utc() -> None:
    """Delete this and a Singapore install gets its six o'clock digest at two in the morning."""
    utc_six = AtTime(at=time(18, 0), zone=ZoneInfo("UTC"))
    at_ten_utc = TODAY_SIX_PM + timedelta(minutes=1)
    assert due(at_ten_utc, None) == ["evening_note"]
    assert owed(now=at_ten_utc, last_run={}, controls=(DAILY,), at={DAILY.name: utc_six}) == ()


def test_a_control_not_named_is_owed_on_its_interval_as_before() -> None:
    """Delete this and adding a time of day to one control changes when every other one runs."""
    hourly = Control(
        name="hourly_thing",
        symbols=("brain.ops.schedule:owed",),
        guards="that a thing happens",
        lost_silently="it stops",
        every=timedelta(hours=1),
        severity=Severity.NOTICED,
        invoked_by=Invocation.IN_PROCESS,
    )
    assert [one.name for one in owed(now=TODAY_SIX_PM, last_run={}, controls=(hourly,), at={})] == [
        "hourly_thing"
    ]


def test_the_hour_comes_from_the_setting_and_falls_back_to_its_default() -> None:
    """Delete this and a value the Settings screen would refuse, set in an environment file,
    stops the digest instead of sending it at its default hour."""
    set_to = times_of_day(
        (DAILY,), env={"INSTALL_DIGEST_TIME": "07:30", "INSTALL_TIME_ZONE": "Asia/Singapore"}
    )
    assert set_to == {DAILY.name: AtTime(at=time(7, 30), zone=ZONE)}
    wrong = times_of_day((DAILY,), env={"INSTALL_DIGEST_TIME": "7.30pm"})
    assert wrong[DAILY.name].at == time(18, 0)


@pytest.mark.parametrize("zone", ["Europe/London", "America/New_York"])
def test_a_daylight_saving_change_moves_the_utc_instant_and_not_the_local_hour(zone: str) -> None:
    """Delete this and the digest arrives an hour off for half of every year in a zone with
    daylight saving."""
    at = AtTime(at=time(18, 0), zone=ZoneInfo(zone))
    for month in (1, 7):
        instant = datetime(2999, month, 15, 12, tzinfo=UTC)
        today, _ = at.latest(instant)
        assert today.astimezone(ZoneInfo(zone)).hour == 18
